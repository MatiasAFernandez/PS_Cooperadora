"""Revisión autorizada y serializada por versión, con historial append-only."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from identidad.services import has_capability

from .acceso import documentos_visibles
from .models import Documento, RevisionDocumento
from .services import bloquear_serie, obtener


class ConflictoRevision(Exception):
    """La versión fue reemplazada o alguien ya revisó el documento."""


def ultima_revision(documento):
    return documento.revisiones.order_by("-id").first()


def version_aceptada(documento):
    """Conformidad de la versión vigente; el circuito decide qué pendiente satisface."""
    revision = ultima_revision(documento)
    return (
        revision is not None
        and revision.resultado == RevisionDocumento.Resultado.ACEPTADO
        and not Documento.objects.filter(reemplaza=documento).exists()
    )


def consultar_revision(*, actor, documento_id):
    documento = obtener(
        actor=actor, documento_id=documento_id, capacidad="documentos.consultar_metadatos"
    )
    return documento, documento.revisiones.select_related("documento__tramite_base").all()


def revisar(*, actor, documento_id, resultado, motivo, revision_esperada):
    # La autoridad de revisar es independiente de lectura, aporte y pago.
    if not has_capability(actor, "documentos.revisar"):
        raise PermissionDenied("No tenés permiso para revisar documentos.")
    documento = obtener(
        actor=actor, documento_id=documento_id, capacidad="documentos.consultar_metadatos"
    )
    if resultado not in RevisionDocumento.Resultado.values:
        raise ValidationError("Resultado de revisión inválido.")
    if not isinstance(motivo, str) or len(motivo) > 2000 or "\x00" in motivo:
        raise ValidationError("El motivo debe ser texto de hasta 2000 caracteres.")
    motivo = motivo.strip()
    if resultado != RevisionDocumento.Resultado.ACEPTADO and not motivo:
        raise ValidationError("Indicá un motivo para observar o rechazar.")
    if type(revision_esperada) is not int or revision_esperada < 0:
        raise ValidationError("Recargá la página para obtener una revisión válida.")
    with transaction.atomic():
        # Mismo bloqueo que reemplazo/C01, sin adquirir después un bloqueo de gasto.
        bloquear_serie(documento)
        if not documentos_visibles(actor).filter(pk=documento.pk).exists():
            from .acceso import DocumentoNoVisible

            raise DocumentoNoVisible("Documento inexistente o no visible.")
        actual = ultima_revision(documento)
        if (
            Documento.objects.filter(reemplaza=documento).exists()
            or (actual.pk if actual else 0) != revision_esperada
        ):
            raise ConflictoRevision("El documento cambió. Recargá la página.")
        if actual and actual.resultado == resultado and actual.motivo == motivo:
            raise ConflictoRevision("Ese resultado ya está registrado.")
        # La revisión es también el hecho de historial: una sola escritura atómica.
        return RevisionDocumento.objects.create(
            documento=documento, resultado=resultado, motivo=motivo, actor_id=actor.subject_id
        )
