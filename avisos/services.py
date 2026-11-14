"""Servicios de generación de avisos web internos para Gastos."""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from avisos.models import Aviso, EstadoIntencionCorreo, IntencionCorreo, TipoAviso
from gastos.models import SolicitudGasto
from identidad.services import actor_para_usuario, has_capability

logger = logging.getLogger(__name__)
User = get_user_model()


def _destinatarios_nueva_solicitud(solicitud: SolicitudGasto) -> list:
    """Devuelve usuarios activos autorizados a recibir el aviso de nueva solicitud."""
    usuarios = (
        User.objects.filter(is_active=True)
        .exclude(pk=solicitud.solicitante_id)
        .select_related("cuenta_local")
        .prefetch_related("groups")
        .order_by("pk")
    )
    destinatarios = []
    for user in usuarios:
        group_names = [group.name for group in user.groups.all()]
        actor = actor_para_usuario(user, group_names=group_names)
        if has_capability(actor, "gastos.consultar_todas") and has_capability(
            actor, "gastos.decidir"
        ):
            destinatarios.append(user)
    return destinatarios


def generar_aviso_nueva_solicitud(
    solicitud_id: int,
    *,
    preparar_correo: bool = False,
) -> int:
    """Genera avisos persistentes e idempotentes para una solicitud de gasto existente."""
    try:
        solicitud = SolicitudGasto.objects.get(pk=solicitud_id)
    except SolicitudGasto.DoesNotExist as exc:
        raise SolicitudGasto.DoesNotExist(
            f"No existe la solicitud de gasto #{solicitud_id}."
        ) from exc

    destinatarios = _destinatarios_nueva_solicitud(solicitud)
    if not destinatarios:
        return 0

    habilitar_correo = preparar_correo and bool(
        getattr(settings, "AVISOS_EMAIL_ENABLED", False)
    )
    with transaction.atomic():
        creados = 0
        for user in destinatarios:
            aviso, creado = Aviso.objects.get_or_create(
                destinatario=user,
                tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
                solicitud_id=solicitud.pk,
            )
            if creado and habilitar_correo:
                IntencionCorreo.objects.create(
                    aviso=aviso,
                    estado=EstadoIntencionCorreo.PENDIENTE,
                )
            creados += int(creado)
        return creados


def programar_aviso_nueva_solicitud(solicitud_id: int) -> None:
    """Programa la generación de avisos para ejecutarse tras confirmar la transacción."""

    def _ejecutar() -> None:
        try:
            with transaction.atomic():
                generar_aviso_nueva_solicitud(solicitud_id, preparar_correo=True)
        except Exception:
            logger.error(
                "No se pudo generar el aviso de nueva solicitud para solicitud_id=%s",
                solicitud_id,
            )
            return

        if not getattr(settings, "AVISOS_EMAIL_ENABLED", False):
            return

        try:
            from avisos.correo import enviar_correos_nueva_solicitud

            enviar_correos_nueva_solicitud(solicitud_id)
        except Exception:
            logger.error(
                "No se pudo ejecutar el envío de correo para solicitud_id=%s",
                solicitud_id,
            )

    transaction.on_commit(_ejecutar)
