"""Autorización y vigencia de la excepción por urgencia en Gastos."""

from datetime import datetime
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from gastos.auth import has_capability
from gastos.models import ExcepcionDeudaDocumental
from identidad.services import Actor, actor_para_usuario

DIAS_VIGENCIA_SUGERIDA = 7
MAX_CARACTERES_MOTIVO = ExcepcionDeudaDocumental._meta.get_field("motivo").max_length


def puede_gestionar_excepciones_deuda(actor: Actor | None) -> bool:
    return (
        settings.DEMO_IDENTITY_ENABLED
        and has_capability(actor, "gastos.consultar_todas")
        and has_capability(actor, "gastos.gestionar_excepciones_deuda")
    )


def puede_recibir_excepcion_deuda(titular: Any) -> bool:
    return has_capability(actor_para_usuario(titular), "gastos.presentar")


def bloquear_titular_excepcion(titular_id: int) -> Any:
    # Serializa concesiones, revocaciones y presentaciones del mismo titular.
    return get_user_model().objects.select_for_update(no_key=True).get(pk=titular_id)


def excepcion_deuda_vigente(
    titular_id: int, *, instante: datetime | None = None
) -> ExcepcionDeudaDocumental | None:
    if not settings.DEMO_IDENTITY_ENABLED:
        return None
    ahora = instante if instante is not None else timezone.now()
    return ExcepcionDeudaDocumental.objects.filter(
        titular_id=titular_id,
        otorgada_en__lte=ahora,
        vence_en__gt=ahora,
        revocada_en__isnull=True,
    ).first()


def _motivo_valido(motivo: str) -> str:
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Ingresá el motivo.")
    if len(motivo) > MAX_CARACTERES_MOTIVO:
        raise ValidationError(f"El motivo admite hasta {MAX_CARACTERES_MOTIVO} caracteres.")
    return motivo


@transaction.atomic
def otorgar_excepcion_deuda(
    *, actor: Actor, titular_id: int, motivo: str, vence_en: datetime
) -> ExcepcionDeudaDocumental:
    if not puede_gestionar_excepciones_deuda(actor):
        raise PermissionDenied("No tenés permiso para otorgar excepciones de Gastos.")
    motivo = _motivo_valido(motivo)
    titular = bloquear_titular_excepcion(titular_id)
    if not puede_recibir_excepcion_deuda(titular):
        raise ValidationError("Esta cuenta no puede presentar solicitudes de Gastos.")

    ahora = timezone.now()
    if not timezone.is_aware(vence_en) or vence_en <= ahora:
        raise ValidationError("Elegí una fecha y hora de vencimiento futuras.")
    if excepcion_deuda_vigente(titular_id, instante=ahora) is not None:
        raise ValidationError("Ya hay una excepción vigente para este titular.")
    return ExcepcionDeudaDocumental.objects.create(
        titular=titular,
        otorgada_por_id=actor.subject_id,
        otorgada_en=ahora,
        vence_en=vence_en,
        motivo=motivo,
    )


@transaction.atomic
def revocar_excepcion_deuda(
    *, actor: Actor, titular_id: int, excepcion_id: int, motivo: str
) -> None:
    if not puede_gestionar_excepciones_deuda(actor):
        raise PermissionDenied("No tenés permiso para revocar excepciones de Gastos.")
    motivo = _motivo_valido(motivo)
    bloquear_titular_excepcion(titular_id)

    ahora = timezone.now()
    excepcion = excepcion_deuda_vigente(titular_id, instante=ahora)
    if excepcion is None or excepcion.pk != excepcion_id:
        raise ValidationError("La excepción seleccionada ya no está vigente.")
    excepcion.revocada_por_id = actor.subject_id
    excepcion.revocada_en = ahora
    excepcion.motivo_revocacion = motivo
    excepcion.save(update_fields=["revocada_por", "revocada_en", "motivo_revocacion"])
