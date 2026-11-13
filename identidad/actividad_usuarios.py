"""Servicio de desactivación y reactivación administrativa de cuentas locales (SPEC-025)."""

from importlib import import_module
from typing import Any

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.sessions.backends.db import SessionStore as DbSessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from identidad.models import CambioActividadCuentaLocal, CuentaLocal
from identidad.services import GROUP_CAPABILITIES, Actor, has_capability

CAPACIDAD_ADMINISTRAR = "identidad.administrar_cuentas"
MAX_LEN_MOTIVO = 2000


def _grupos_admin_locales() -> tuple[str, ...]:
    """Obtiene los nombres de grupos reconocidos que otorgan identidad.administrar_cuentas."""
    return tuple(
        sorted(
            nombre
            for nombre, capacidades in GROUP_CAPABILITIES.items()
            if CAPACIDAD_ADMINISTRAR in capacidades
        )
    )


def _validar_parametros(activar: Any, actividad_esperada: Any, motivo: Any) -> str:
    """Valida tipos booleanos estrictos y el motivo obligatorio."""
    if not isinstance(activar, bool):
        raise ValidationError("El parámetro activar debe ser un valor booleano.")
    if not isinstance(actividad_esperada, bool):
        raise ValidationError("El parámetro actividad_esperada debe ser un valor booleano.")
    if not isinstance(motivo, str):
        raise ValidationError("El motivo es obligatorio.")

    motivo_limpio = motivo.strip()
    if not motivo_limpio:
        raise ValidationError("El motivo es obligatorio.")
    if len(motivo_limpio) > MAX_LEN_MOTIVO:
        raise ValidationError(f"El motivo no debe superar los {MAX_LEN_MOTIVO} caracteres.")
    return motivo_limpio


def _es_admin_local_habilitado(
    user: Any,
    cuenta: CuentaLocal | None,
    admin_group_user_ids: set[int],
) -> bool:
    """Comprueba si una cuenta local puede ejercer actualmente administración de cuentas."""
    return (
        user is not None
        and bool(user.is_active)
        and cuenta is not None
        and cuenta.estado == CuentaLocal.Estado.APROBADA
        and cuenta.email_verificado_en is not None
        and user.pk in admin_group_user_ids
    )


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
    grupos_admin = _grupos_admin_locales()
    if not grupos_admin:
        raise PermissionDenied("No existen grupos habilitados para administrar cuentas.")

    user_model = get_user_model()

    with transaction.atomic():
        target_user_id = (
            CuentaLocal.objects.filter(pk=cuenta_id).values_list("user_id", flat=True).first()
        )
        if target_user_id is None:
            raise ValidationError("La cuenta local no existe.")

        candidatos_admin_pks = list(
            user_model.objects.filter(
                cuenta_local__isnull=False,
                groups__name__in=grupos_admin,
            )
            .values_list("pk", flat=True)
            .distinct()
        )

        # Bloquear User en orden estable de PK (sin DISTINCT) antes que CuentaLocal.
        user_pks_bloqueo = sorted(set(candidatos_admin_pks) | {actor.subject_id, target_user_id})
        usuarios_bloqueados = {
            u.pk: u
            for u in user_model.objects.select_for_update()
            .filter(pk__in=user_pks_bloqueo)
            .order_by("pk")
        }
        cuentas_bloqueadas = {
            c.user_id: c
            for c in CuentaLocal.objects.select_for_update()
            .filter(user_id__in=user_pks_bloqueo)
            .order_by("pk")
        }
        admin_group_user_ids = set(
            user_model.objects.filter(
                pk__in=user_pks_bloqueo,
                groups__name__in=grupos_admin,
            ).values_list("pk", flat=True)
        )

        actor_user = usuarios_bloqueados.get(actor.subject_id)
        actor_cuenta = cuentas_bloqueadas.get(actor.subject_id)
        if not _es_admin_local_habilitado(actor_user, actor_cuenta, admin_group_user_ids):
            raise PermissionDenied("No posee capacidad vigente para administrar cuentas.")

        target_user = usuarios_bloqueados.get(target_user_id)
        target_cuenta = cuentas_bloqueadas.get(target_user_id)
        if target_user is None or target_cuenta is None:
            raise ValidationError("La cuenta local no existe.")

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

            otros_admins_habilitados = [
                uid
                for uid in user_pks_bloqueo
                if uid != target_user.pk
                and _es_admin_local_habilitado(
                    usuarios_bloqueados.get(uid),
                    cuentas_bloqueadas.get(uid),
                    admin_group_user_ids,
                )
            ]
            if not otros_admins_habilitados:
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
