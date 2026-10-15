"""Operaciones documentales con autorización por acción y por trámite."""

import re
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction

from gastos.queries import visible_expenses
from identidad.services import Actor, has_capability

from .models import Documento
from .policy import ArchivoInvalido, validar_archivo


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
    if not isinstance(referencia, str) or not re.fullmatch(r"gastos:[1-9][0-9]*", referencia):
        raise DocumentoNoVisible("Trámite inexistente o no visible.")
    solicitud = visible_expenses(actor).filter(pk=int(referencia.split(":", 1)[1])).first()
    if solicitud is None:
        raise DocumentoNoVisible("Trámite inexistente o no visible.")
    return solicitud


def _exigir(actor: Actor | None, capacidad: str) -> None:
    if not has_capability(actor, capacidad):
        raise DocumentoNoVisible("Documento inexistente o no visible.")


def _etiqueta(valor: str | None, campo: str) -> str:
    if not isinstance(valor, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", valor):
        raise ArchivoInvalido(f"{campo} inválido.")
    return valor


def incorporar(
    *, actor: Actor | None, referencia: str, archivo: object, tipo: str, procedencia: str
) -> Documento:
    solicitud = _gasto_visible(actor, referencia)
    _exigir(actor, "documentos.incorporar")
    tipo = _etiqueta(tipo, "Tipo documental")
    procedencia = _etiqueta(procedencia, "Procedencia")
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
    _exigir(actor, "documentos.ver_metadatos")
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
