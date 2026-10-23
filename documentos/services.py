"""Incorporación, reemplazo y lectura; cada versión conserva sus bytes y metadatos."""

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction

from comunes.models import Circuito
from comunes.services import registrar_cabecera_gasto
from identidad.services import Actor, has_capability

from .acceso import (
    DocumentoNoVisible,
    bloquear_facturacion_abierta,
    destino_visible,
    documentos_visibles,
)
from .models import Documento
from .policy import ArchivoInvalido, ArchivoValidado, validar_archivo

TIPOS_POR_CIRCUITO = {
    Circuito.GASTO: {
        Documento.Tipo.PRESUPUESTO_PROFORMA: {Documento.Procedencia.SOLICITANTE},
        Documento.Tipo.FACTURA_PROVEEDOR: {
            Documento.Procedencia.SOLICITANTE,
            Documento.Procedencia.INTERNO_COOPERADORA,
        },
        Documento.Tipo.TICKET_NO_FISCAL: {
            Documento.Procedencia.SOLICITANTE,
            Documento.Procedencia.INTERNO_COOPERADORA,
        },
        Documento.Tipo.COMPROBANTE_PAGO: {Documento.Procedencia.EXTERNO_BANCO},
        Documento.Tipo.CONSTANCIA_RETENCION_ATP: {Documento.Procedencia.EXTERNO_ATP},
    },
    Circuito.FACTURACION: {
        Documento.Tipo.FACTURA_EMITIDA_XUBIO: {Documento.Procedencia.EXTERNO_XUBIO},
        Documento.Tipo.NOTA_CREDITO_XUBIO: {Documento.Procedencia.EXTERNO_XUBIO},
        Documento.Tipo.NOTA_DEBITO_XUBIO: {Documento.Procedencia.EXTERNO_XUBIO},
        Documento.Tipo.COMPROBANTE_COBRO: {
            Documento.Procedencia.SOLICITANTE,
            Documento.Procedencia.EXTERNO_BANCO,
        },
    },
}

# Compatibilidad de entrada para clientes del primer tramo. La migración
# convierte sólo estos códigos conocidos; nunca interpreta documentos antiguos.
TIPOS_ANTERIORES = {
    "PRESUPUESTO": Documento.Tipo.PRESUPUESTO_PROFORMA,
    "TICKET_PROVEEDOR": Documento.Tipo.TICKET_NO_FISCAL,
    "FACTURA_EMITIDA": Documento.Tipo.FACTURA_EMITIDA_XUBIO,
    "NOTA_CREDITO": Documento.Tipo.NOTA_CREDITO_XUBIO,
    "NOTA_DEBITO": Documento.Tipo.NOTA_DEBITO_XUBIO,
}
TIPOS_ELEGIBLES_PAGO_GASTOS = frozenset(
    {
        Documento.Tipo.FACTURA_PROVEEDOR,
        Documento.Tipo.PRESUPUESTO_PROFORMA,
    }
)


class AlmacenamientoNoDisponible(OSError):
    """La escritura privada falló; se intentó compensar cualquier archivo creado."""


def almacenamiento() -> FileSystemStorage:
    raiz = Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
    raiz_estatica = Path(settings.STATIC_ROOT).resolve()
    if raiz == raiz_estatica or raiz_estatica in raiz.parents:
        raise ImproperlyConfigured("DOCUMENT_STORAGE_ROOT no puede estar bajo STATIC_ROOT.")
    return FileSystemStorage(location=raiz, base_url=None)


def _exigir(actor: Actor | None, capacidad: str) -> None:
    if not has_capability(actor, capacidad):
        raise PermissionDenied("Capacidad documental insuficiente.")


def _validar_clasificacion(actor: Actor, circuito: str, tipo: str, procedencia: str) -> None:
    if tipo not in Documento.Tipo.values or procedencia not in Documento.Procedencia.values:
        raise ArchivoInvalido("Tipo documental o procedencia no admitidos.")
    capacidad_global = (
        "gastos.consultar_todas" if circuito == Circuito.GASTO else "facturacion.consultar_todas"
    )
    if has_capability(actor, capacidad_global):
        if procedencia == Documento.Procedencia.SOLICITANTE:
            raise PermissionDenied("El personal no puede declarar procedencia del solicitante.")
    elif procedencia != Documento.Procedencia.SOLICITANTE or tipo not in {
        Documento.Tipo.PRESUPUESTO_PROFORMA,
        Documento.Tipo.FACTURA_PROVEEDOR,
        Documento.Tipo.TICKET_NO_FISCAL,
        Documento.Tipo.COMPROBANTE_COBRO,
    }:
        raise PermissionDenied("El solicitante no puede declarar ese tipo o procedencia.")
    if procedencia not in TIPOS_POR_CIRCUITO[circuito].get(tipo, set()):
        raise ArchivoInvalido("Tipo y procedencia incompatibles con el circuito.")


def incorporar(
    *,
    actor: Actor | None,
    referencia: str,
    archivo: object,
    tipo: str,
    procedencia: str,
    reemplaza_id: int | None = None,
    _escrituras=None,
) -> Documento:
    """Valida antes de escribir y compensa fallos internos de BD/almacenamiento.

    Los consumidores futuros no deben anidar esta carga en una transacción más
    amplia sin resolver su rollback exterior (pendiente explícito de #28).
    """
    destino = destino_visible(actor, referencia)
    _exigir(actor, "documentos.incorporar")
    tipo = TIPOS_ANTERIORES.get(tipo, tipo)
    _validar_clasificacion(actor, destino.ref.circuito, tipo, procedencia)
    validado = archivo if isinstance(archivo, ArchivoValidado) else validar_archivo(archivo)
    ruta = f"documentos/{uuid.uuid4().hex}"
    storage = almacenamiento()
    guardado = None
    try:
        with transaction.atomic():
            base = registrar_cabecera_gasto(destino.gasto) if destino.gasto else destino.base
            bloquear_facturacion_abierta(base)
            # La revalidación cubre cambios de titular entre consulta y bloqueo.
            destino_visible(actor, referencia)
            anterior = None
            if reemplaza_id is not None:
                anterior = obtener(
                    actor=actor, documento_id=reemplaza_id, capacidad="documentos.incorporar"
                )
                if anterior.tramite_base_id != base.pk or anterior.tipo != tipo:
                    raise ArchivoInvalido("El reemplazo debe conservar trámite y tipo.")
                bloquear_serie(anterior)
                if Documento.objects.filter(reemplaza=anterior).exists():
                    raise ArchivoInvalido("La versión ya fue reemplazada.")
            if _escrituras is not None:
                _escrituras.registrar(storage, ruta)
            guardado = storage.save(ruta, ContentFile(validado.contenido))
            if _escrituras is not None:
                _escrituras.registrar(storage, guardado)
            return Documento.objects.create(
                solicitud_gasto=destino.gasto,
                tramite_base=base,
                tipo=tipo,
                procedencia=procedencia,
                archivo=guardado,
                nombre_original=validado.nombre,
                formato=validado.formato,
                tamano=len(validado.contenido),
                sha256=validado.sha256,
                autor_id=actor.subject_id,
                serie=anterior.serie if anterior else uuid.uuid4(),
                version=anterior.version + 1 if anterior else 1,
                reemplaza=anterior,
            )
    except Exception as exc:
        if _escrituras is not None:
            # La operación exterior conserva la excepción y compensa tras rollback.
            raise
        for nombre in {ruta, guardado} - {None}:
            try:
                storage.delete(nombre)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise AlmacenamientoNoDisponible("No se pudo guardar el archivo.") from exc
        raise


def bloquear_serie(documento: Documento) -> None:
    """Todos los reemplazos y verificaciones C01 bloquean la misma fila raíz."""
    Documento.objects.select_for_update().get(serie=documento.serie, version=1)


def listar(*, actor: Actor | None, referencia: str):
    destino = destino_visible(actor, referencia)
    _exigir(actor, "documentos.consultar_metadatos")
    # La lectura de un gasto nuevo sin cabecera devuelve vacío, sin crear filas.
    return documentos_visibles(actor).filter(tramite_base=destino.base).order_by("id")


def obtener(*, actor: Actor | None, documento_id: int, capacidad: str) -> Documento:
    _exigir(actor, capacidad)
    documento = documentos_visibles(actor).filter(pk=documento_id).first()
    if documento is None:
        raise DocumentoNoVisible("Documento inexistente o no visible.")
    return documento


def metadatos(documento: Documento) -> dict:
    """Expone identidad y versión lógica, nunca la ruta física del archivo."""
    return {
        "id": documento.pk,
        "tramite": documento.referencia_tramite,
        "tipo": documento.tipo,
        "procedencia": documento.procedencia,
        "nombre": documento.nombre_original,
        "formato": documento.formato,
        "tamano": documento.tamano,
        "autor_id": documento.autor_id,
        "fecha_incorporacion": documento.fecha_incorporacion.isoformat(),
        "version": documento.version,
    }
