"""Servicio de desactivación y reactivación administrativa de cuentas locales (SPEC-025)."""

from importlib import import_module
from typing import Any

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore as DbSessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from identidad.administracion_cuentas import (
    CAPACIDAD_ADMINISTRAR,
    bloquear_y_revalidar_administracion,
    es_admin_local_habilitado,
    existen_otros_admins_habilitados,
    validar_motivo_administrativo,
)
from identidad.administracion_cuentas import (
    grupos_admin_locales as _grupos_admin_locales,
)
from identidad.models import CambioActividadCuentaLocal, CuentaLocal
from identidad.services import Actor, has_capability

# Conservar el acceso al helper previo durante la extracción del protocolo común.
_es_admin_local_habilitado = es_admin_local_habilitado


def _validar_parametros(activar: Any, actividad_esperada: Any, motivo: Any) -> str:
    """Valida tipos booleanos estrictos y el motivo obligatorio."""
    if not isinstance(activar, bool):
        raise ValidationError("El parámetro activar debe ser un valor booleano.")
    if not isinstance(actividad_esperada, bool):
        raise ValidationError("El parámetro actividad_esperada debe ser un valor booleano.")
    return validar_motivo_administrativo(motivo)


def _revocar_sesiones_usuario(user_id: int) -> None:
    """Elimina las sesiones vigentes en base de datos pertenecientes al usuario objetivo."""
    session_module = import_module(settings.SESSION_ENGINE)
    session_store_cls = getattr(session_module, "SessionStore", None)
    if session_store_cls is None or not issubclass(session_store_cls, DbSessionStore):
        raise ImproperlyConfigured(
            "La revocación de sesiones requiere el motor de sesiones en base de datos."
        )

    target_id_str = str(user_id)
    claves_a_eliminar: list[str] = []
    sesiones_vigentes = (
        Session.objects.filter(expire_date__gt=timezone.now())
        .only("session_key", "session_data")
        .iterator()
    )
    for sesion in sesiones_vigentes:
        datos = sesion.get_decoded()
        auth_user_id = datos.get(SESSION_KEY)
        if auth_user_id is not None and str(auth_user_id) == target_id_str:
            claves_a_eliminar.append(sesion.session_key)

    if claves_a_eliminar:
        Session.objects.filter(session_key__in=claves_a_eliminar).delete()


def cambiar_actividad_cuenta(
    actor: Actor | None,
    cuenta_id: int,
    activar: bool,
    motivo: str,
    actividad_esperada: bool,
) -> tuple[CuentaLocal, CambioActividadCuentaLocal | None]:
    """Desactiva o reactiva una CuentaLocal bajo bloqueo y registra el evento de actividad.

    Exige ``identidad.administrar_cuentas`` antes de consultar la base y revalida al
    actor, al objetivo y el mínimo de administradores locales habilitados bajo bloqueos
    ordenados (``User`` antes que ``CuentaLocal``). Si la cuenta ya posee el estado
    solicitado, retorna sin modificar ni crear evento (no-op).
    """
    if not has_capability(actor, CAPACIDAD_ADMINISTRAR) or actor is None:
        raise PermissionDenied("No posee capacidad para administrar cuentas.")

    motivo_limpio = _validar_parametros(activar, actividad_esperada, motivo)
    if not _grupos_admin_locales():
        raise PermissionDenied("No existen grupos habilitados para administrar cuentas.")

    with transaction.atomic():
        contexto = bloquear_y_revalidar_administracion(actor, cuenta_id)
        actor_user = contexto.actor_user
        target_user = contexto.target_user
        target_cuenta = contexto.target_cuenta

        actividad_actual = bool(target_user.is_active)
        if actividad_actual == activar:
            return target_cuenta, None

        if actividad_actual != actividad_esperada:
            raise ValidationError(
                "La actividad de la cuenta cambió desde que abrió la confirmación. "
                "Recargue la ficha e intente nuevamente."
            )

        if not activar:
            if target_user.pk == actor_user.pk:
                raise ValidationError("No puede desactivar su propia cuenta.")

            if not existen_otros_admins_habilitados(contexto, excluir_user_id=target_user.pk):
                raise ValidationError(
                    "Debe permanecer al menos una cuenta de administración local habilitada."
                )

        target_user.is_active = activar
        target_user.save(update_fields=["is_active"])
        target_cuenta.refresh_from_db()

        evento = CambioActividadCuentaLocal.objects.create(
            cuenta=target_cuenta,
            autor=actor_user,
            motivo=motivo_limpio,
            actividad_anterior=actividad_actual,
            actividad_nueva=activar,
        )
        _revocar_sesiones_usuario(target_user.pk)
        return target_cuenta, evento
