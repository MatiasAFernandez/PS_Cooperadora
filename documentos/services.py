"""Operaciones documentales con autorización por acción y por trámite."""

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction

from gastos.queries import visible_expenses
from identidad.services import Actor, has_capability

from .models import Documento
from .policy import ArchivoInvalido, validar_archivo

TIPOS_POR_CIRCUITO = {
    "gastos": {
        Documento.Tipo.PRESUPUESTO: {Documento.Procedencia.SOLICITANTE},
        Documento.Tipo.FACTURA_PROVEEDOR: {
            Documento.Procedencia.SOLICITANTE,
            Documento.Procedencia.INTERNO_COOPERADORA,
        },
        Documento.Tipo.TICKET_PROVEEDOR: {
            Documento.Procedencia.SOLICITANTE,
            Documento.Procedencia.INTERNO_COOPERADORA,
        },
        Documento.Tipo.COMPROBANTE_PAGO: {Documento.Procedencia.EXTERNO_BANCO},
        Documento.Tipo.CONSTANCIA_RETENCION_ATP: {Documento.Procedencia.EXTERNO_ATP},
    },
    "facturacion": {
        Documento.Tipo.FACTURA_EMITIDA: {Documento.Procedencia.EXTERNO_XUBIO},
        Documento.Tipo.NOTA_CREDITO: {Documento.Procedencia.EXTERNO_XUBIO},
        Documento.Tipo.NOTA_DEBITO: {Documento.Procedencia.EXTERNO_XUBIO},
        Documento.Tipo.COMPROBANTE_COBRO: {
            Documento.Procedencia.SOLICITANTE,
            Documento.Procedencia.EXTERNO_BANCO,
        },
    },
}

TIPOS_APORTABLES_SOLICITANTE = {
    Documento.Tipo.PRESUPUESTO,
    Documento.Tipo.FACTURA_PROVEEDOR,
    Documento.Tipo.TICKET_PROVEEDOR,
    Documento.Tipo.COMPROBANTE_COBRO,
}

# El puerto C01 de gastos admite factura, presupuesto y proforma como respaldo
# de pago. Un ticket puede conservarse en el trámite, pero no ofrece una opción
# elegible para ese puerto. El adaptador real se incorporará en #22/#28.
TIPOS_ELEGIBLES_PAGO_GASTOS = frozenset({
    Documento.Tipo.FACTURA_PROVEEDOR,
    Documento.Tipo.PRESUPUESTO,
})


class DocumentoNoVisible(LookupError):
    pass


class AlmacenamientoNoDisponible(OSError):
    pass


def almacenamiento() -> FileSystemStorage:
    """Ubicación privada configurable, sin URL pública ni MEDIA_URL."""
    raiz = Path(settings.DOCUMENT_STORAGE_ROOT).resolve()
    raiz_estatica = Path(settings.STATIC_ROOT).resolve()
    if raiz == raiz_estatica or raiz_estatica in raiz.parents:
        raise ImproperlyConfigured("DOCUMENT_STORAGE_ROOT no puede estar bajo STATIC_ROOT.")
    return FileSystemStorage(location=raiz, base_url=None)


def _gasto_visible(actor: Actor | None, referencia: str):
    if not isinstance(referencia, str) or not referencia.startswith("gastos:"):
        raise DocumentoNoVisible("Trámite inexistente o no visible.")
    identificador = referencia.split(":", 1)[1]
    if (
        not identificador.isascii()
        or not identificador.isdecimal()
        or identificador.startswith("0")
    ):
        raise DocumentoNoVisible("Trámite inexistente o no visible.")
    solicitud = visible_expenses(actor).filter(pk=int(identificador)).first()
    if solicitud is None:
        raise DocumentoNoVisible("Trámite inexistente o no visible.")
    return solicitud


def _exigir(actor: Actor | None, capacidad: str) -> None:
    if not has_capability(actor, capacidad):
        raise PermissionDenied("Capacidad documental insuficiente.")


def _validar_clasificacion(actor: Actor, tipo: str, procedencia: str) -> None:
    if tipo not in Documento.Tipo.values or procedencia not in Documento.Procedencia.values:
        raise ArchivoInvalido("Tipo documental o procedencia no admitidos.")

    es_personal = has_capability(actor, "gastos.consultar_todas")
    if es_personal:
        if procedencia == Documento.Procedencia.SOLICITANTE:
            raise PermissionDenied("El personal no puede declarar procedencia del solicitante.")
    elif (
        procedencia != Documento.Procedencia.SOLICITANTE
        or tipo not in TIPOS_APORTABLES_SOLICITANTE
    ):
        raise PermissionDenied("El solicitante no puede declarar ese tipo o procedencia.")

    if procedencia not in TIPOS_POR_CIRCUITO["gastos"].get(tipo, set()):
        raise ArchivoInvalido("Tipo y procedencia incompatibles con el circuito.")


def incorporar(
    *, actor: Actor | None, referencia: str, archivo: object, tipo: str, procedencia: str
) -> Documento:
    solicitud = _gasto_visible(actor, referencia)
    _exigir(actor, "documentos.incorporar")
    _validar_clasificacion(actor, tipo, procedencia)
    validado = validar_archivo(archivo)
    ruta = f"documentos/{uuid.uuid4().hex}"
    storage = almacenamiento()
    guardado = None
    try:
        with transaction.atomic():
            guardado = storage.save(ruta, ContentFile(validado.contenido))
            return Documento.objects.create(
                solicitud_gasto=solicitud,
                tipo=tipo,
                procedencia=procedencia,
                archivo=guardado,
                nombre_original=validado.nombre,
                formato=validado.formato,
                tamano=len(validado.contenido),
                sha256=validado.sha256,
                autor_id=actor.subject_id,
            )
    except Exception as exc:
        # Una transacción SQL no revierte los bytes. El UUID evita colisiones de
        # nombres; limpiar ambos nombres cubre un fallo después de escribir.
        for nombre in {ruta, guardado} - {None}:
            try:
                storage.delete(nombre)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise AlmacenamientoNoDisponible("No se pudo guardar el archivo.") from exc
        raise


def listar(*, actor: Actor | None, referencia: str):
    solicitud = _gasto_visible(actor, referencia)
    _exigir(actor, "documentos.consultar_metadatos")
    return Documento.objects.filter(solicitud_gasto=solicitud).order_by("id")


def obtener(*, actor: Actor | None, documento_id: int, capacidad: str) -> Documento:
    _exigir(actor, capacidad)
    documento = (
        Documento.objects.filter(solicitud_gasto__in=visible_expenses(actor), pk=documento_id)
        .select_related("solicitud_gasto")
        .first()
    )
    if documento is None:
        raise DocumentoNoVisible("Documento inexistente o no visible.")
    return documento


def metadatos(documento: Documento) -> dict:
    """Respuesta sin nombre físico del archivo ni ruta de almacenamiento."""
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
    }
