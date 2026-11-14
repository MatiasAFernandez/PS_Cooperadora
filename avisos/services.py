"""Servicios de generación de avisos web internos para Gastos."""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from avisos.models import Aviso, EstadoIntencionCorreo, IntencionCorreo, TipoAviso
from avisos.permisos import evaluar_autorizacion_aviso
from gastos.models import DecisionGasto, EventoPagoExterno, SolicitudGasto
from identidad.services import actor_para_usuario

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
        autorizado, _ = evaluar_autorizacion_aviso(
            tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
            actor=actor,
            destinatario_id=user.pk,
            solicitud=solicitud,
        )
        if autorizado:
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


def generar_aviso_decision_gasto(
    decision_id: int,
    *,
    preparar_correo: bool = False,
) -> int:
    """Genera un aviso persistente e idempotente para una decisión de gasto existente."""
    try:
        decision = DecisionGasto.objects.select_related("solicitud").get(pk=decision_id)
    except DecisionGasto.DoesNotExist as exc:
        raise DecisionGasto.DoesNotExist(
            f"No existe la decisión de gasto #{decision_id}."
        ) from exc

    solicitud = decision.solicitud
    titular = (
        User.objects.filter(pk=solicitud.solicitante_id)
        .select_related("cuenta_local")
        .prefetch_related("groups")
        .first()
    )
    if titular is None:
        return 0

    group_names = [group.name for group in titular.groups.all()]
    actor = actor_para_usuario(titular, group_names=group_names)
    autorizado, _ = evaluar_autorizacion_aviso(
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        actor=actor,
        destinatario_id=titular.pk,
        solicitud=solicitud,
        decision=decision,
    )
    if not autorizado:
        return 0

    habilitar_correo = preparar_correo and bool(
        getattr(settings, "AVISOS_EMAIL_ENABLED", False)
    )
    with transaction.atomic():
        aviso, creado = Aviso.objects.get_or_create(
            destinatario=titular,
            tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
            decision_id=decision.pk,
            defaults={"solicitud_id": solicitud.pk},
        )
        if creado and habilitar_correo:
            IntencionCorreo.objects.create(
                aviso=aviso,
                estado=EstadoIntencionCorreo.PENDIENTE,
            )
        return int(creado)


def programar_aviso_decision_gasto(decision_id: int) -> None:
    """Programa la generación del aviso de decisión para tras confirmar la transacción."""

    def _ejecutar() -> None:
        try:
            with transaction.atomic():
                generar_aviso_decision_gasto(decision_id, preparar_correo=True)
        except Exception:
            logger.error(
                "No se pudo generar el aviso de decisión para decision_id=%s",
                decision_id,
            )
            return

        if not getattr(settings, "AVISOS_EMAIL_ENABLED", False):
            return

        try:
            from avisos.correo import enviar_correos_decision_gasto

            enviar_correos_decision_gasto(decision_id)
        except Exception:
            logger.error(
                "No se pudo ejecutar el envío de correo para decision_id=%s",
                decision_id,
            )

    transaction.on_commit(_ejecutar)


def generar_aviso_pago_externo(
    evento_pago_id: int,
    *,
    preparar_correo: bool = False,
) -> int:
    """Genera un aviso persistente e idempotente para un evento de pago externo."""
    try:
        evento = EventoPagoExterno.objects.select_related("pago__solicitud").get(
            pk=evento_pago_id
        )
    except EventoPagoExterno.DoesNotExist as exc:
        raise EventoPagoExterno.DoesNotExist(
            f"No existe el evento de pago externo #{evento_pago_id}."
        ) from exc

    solicitud = evento.pago.solicitud
    titular = (
        User.objects.filter(pk=solicitud.solicitante_id)
        .select_related("cuenta_local")
        .prefetch_related("groups")
        .first()
    )
    if titular is None:
        return 0

    group_names = [group.name for group in titular.groups.all()]
    actor = actor_para_usuario(titular, group_names=group_names)
    autorizado, _ = evaluar_autorizacion_aviso(
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        actor=actor,
        destinatario_id=titular.pk,
        solicitud=solicitud,
        evento_pago=evento,
    )
    if not autorizado:
        return 0

    habilitar_correo = preparar_correo and bool(
        getattr(settings, "AVISOS_EMAIL_ENABLED", False)
    )
    with transaction.atomic():
        aviso, creado = Aviso.objects.get_or_create(
            destinatario=titular,
            tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
            evento_pago_id=evento.pk,
            defaults={"solicitud_id": solicitud.pk},
        )
        if creado and habilitar_correo:
            IntencionCorreo.objects.create(
                aviso=aviso,
                estado=EstadoIntencionCorreo.PENDIENTE,
            )
        return int(creado)


def programar_aviso_pago_externo(evento_pago_id: int) -> None:
    """Programa la generación del aviso de pago externo tras confirmar la transacción."""

    def _ejecutar() -> None:
        try:
            with transaction.atomic():
                generar_aviso_pago_externo(evento_pago_id, preparar_correo=True)
        except Exception:
            logger.error(
                "No se pudo generar el aviso de pago externo para evento_pago_id=%s",
                evento_pago_id,
            )
            return

        if not getattr(settings, "AVISOS_EMAIL_ENABLED", False):
            return

        try:
            from avisos.correo import enviar_correos_pago_externo

            enviar_correos_pago_externo(evento_pago_id)
        except Exception:
            logger.error(
                "No se pudo ejecutar el envío de correo para evento_pago_id=%s",
                evento_pago_id,
            )

    transaction.on_commit(_ejecutar)
