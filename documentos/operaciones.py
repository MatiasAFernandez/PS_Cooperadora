"""Compensación de archivos de operaciones exteriores y recuperación explícita tras caída.

El manifiesto privado se escribe antes del storage. No ofrece atomicidad distribuida;
un commit incierto se reconcilia conservando todos los archivos referenciados en BD.
"""

import json
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path

from django.db import connection, transaction

from .models import Documento

logger = logging.getLogger(__name__)


class TransaccionAnidadaNoPermitidaError(RuntimeError):
    pass


class RegistroEscrituras:
    def __init__(self, storage):
        self.storage = storage
        self.rutas = []
        self.estado = "activa"
        self.manifiesto = Path(storage.location) / ".operaciones" / f"{uuid.uuid4().hex}.json"
        self.guardar()

    def guardar(self):
        self.manifiesto.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.manifiesto.with_suffix(".tmp")
        temporal.write_text(
            json.dumps({"estado": self.estado, "rutas": self.rutas}),
            encoding="utf-8",
        )
        temporal.replace(self.manifiesto)

    def registrar(self, storage, ruta):
        if Path(storage.location).resolve() != Path(self.storage.location).resolve():
            raise RuntimeError("El almacenamiento cambió durante la operación.")
        if ruta not in self.rutas:
            self.rutas.append(ruta)
            self.guardar()

    def terminar(self):
        try:
            self.manifiesto.unlink(missing_ok=True)
        except OSError:
            logger.exception("No se pudo retirar el manifiesto documental confirmado.")

    def compensar(self):
        self.estado = "pendiente"
        try:
            self.guardar()
            for ruta in self.rutas:
                # También protege el caso de resultado incierto de commit.
                if not Documento.objects.filter(archivo=ruta).exists():
                    self.storage.delete(ruta)
            self.terminar()
        except Exception:
            logger.exception("Limpieza documental pendiente; conservar manifiesto privado.")


@contextmanager
def operacion_documental():
    from .services import almacenamiento

    if connection.in_atomic_block or not connection.get_autocommit():
        raise TransaccionAnidadaNoPermitidaError(
            "El servicio debe ser dueño de la transacción exterior."
        )
    registro = RegistroEscrituras(almacenamiento())
    try:
        with transaction.atomic():
            yield registro
            registro.estado = "confirmando"
            registro.guardar()
    except Exception:
        if registro.estado == "confirmando":
            # El servidor podría haber confirmado antes de perder la conexión.
            registro.estado = "incierta"
            try:
                registro.guardar()
            except OSError:
                logger.exception(
                    "Conservar manifiesto para reconciliación con aplicación detenida."
                )
        else:
            registro.compensar()
        raise
    else:
        registro.terminar()
