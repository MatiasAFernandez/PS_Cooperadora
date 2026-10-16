"""Recuperación explícita de operaciones interrumpidas, con la aplicación detenida."""

import json
from pathlib import Path, PurePosixPath

from django.core.management.base import BaseCommand, CommandError

from documentos.operaciones import RegistroEscrituras
from documentos.services import almacenamiento


class Command(BaseCommand):
    help = "Reconcilia manifiestos privados; requiere detener las escrituras de la aplicación."

    def add_arguments(self, parser):
        parser.add_argument("--aplicacion-detenida", action="store_true")

    def handle(self, *args, **options):
        if not options["aplicacion_detenida"]:
            raise CommandError("Detené las escrituras y usá --aplicacion-detenida.")
        storage = almacenamiento()
        carpeta = Path(storage.location) / ".operaciones"
        for manifiesto in sorted(carpeta.glob("*.json")):
            try:
                contenido = json.loads(manifiesto.read_text(encoding="utf-8"))
                rutas = contenido["rutas"]
                if not isinstance(rutas, list):
                    raise ValueError
                for ruta in rutas:
                    if not isinstance(ruta, str):
                        raise ValueError
                    partes = PurePosixPath(ruta).parts
                    if (
                        len(partes) != 2
                        or partes[0] != "documentos"
                        or (partes[1] in {".", ".."} or "\\" in ruta)
                    ):
                        raise ValueError
            except (ValueError, KeyError, OSError) as exc:
                raise CommandError("Manifiesto inválido; requiere revisión privada.") from exc
            registro = object.__new__(RegistroEscrituras)
            registro.storage, registro.rutas = storage, rutas
            registro.manifiesto = manifiesto
            registro.compensar()
        self.stdout.write("Reconciliación finalizada; revisar los errores pendientes del registro.")
