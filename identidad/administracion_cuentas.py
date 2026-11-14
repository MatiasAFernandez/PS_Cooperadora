"""Protocolo compartido de bloqueo y revalidación para administración de cuentas locales."""

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError

from identidad.models import CuentaLocal
from identidad.services import GROUP_CAPABILITIES, Actor

CAPACIDAD_ADMINISTRAR = "identidad.administrar_cuentas"
MAX_LEN_MOTIVO = 2000


@dataclass(frozen=True, slots=True)
class ContextoAdministracionCuenta:
    """Estado bloqueado y revalidado del actor, objetivo y candidatos administrativos."""

    actor_user: Any
    actor_cuenta: CuentaLocal
    target_user: Any
    target_cuenta: CuentaLocal
    user_pks_bloqueo: list[int]
    usuarios_bloqueados: dict[int, Any]
    cuentas_bloqueadas: dict[int, CuentaLocal]
    admin_group_user_ids: set[int]


def grupos_admin_locales() -> tuple[str, ...]:
    """Obtiene los nombres de grupos reconocidos que otorgan identidad.administrar_cuentas."""
    return tuple(
        sorted(
            nombre
            for nombre, capacidades in GROUP_CAPABILITIES.items()
            if CAPACIDAD_ADMINISTRAR in capacidades
        )
    )


def validar_motivo_administrativo(motivo: Any) -> str:
    """Valida y normaliza un motivo administrativo obligatorio de hasta 2000 caracteres."""
    if not isinstance(motivo, str):
        raise ValidationError("El motivo es obligatorio.")

    motivo_limpio = motivo.strip()
    if not motivo_limpio:
        raise ValidationError("El motivo es obligatorio.")
    if len(motivo_limpio) > MAX_LEN_MOTIVO:
        raise ValidationError(f"El motivo no debe superar los {MAX_LEN_MOTIVO} caracteres.")
    return motivo_limpio


def es_admin_local_habilitado(
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


def bloquear_y_revalidar_administracion(
    actor: Actor,
    cuenta_id: int,
) -> ContextoAdministracionCuenta:
    """Bloquea en orden estable User -> CuentaLocal y revalida al actor y objetivo.

    Debe ejecutarse dentro de ``transaction.atomic()``.
    """
    grupos_admin = grupos_admin_locales()
    if not grupos_admin:
        raise PermissionDenied("No existen grupos habilitados para administrar cuentas.")

    user_model = get_user_model()
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
    if not es_admin_local_habilitado(actor_user, actor_cuenta, admin_group_user_ids):
        raise PermissionDenied("No posee capacidad vigente para administrar cuentas.")

    target_user = usuarios_bloqueados.get(target_user_id)
    target_cuenta = cuentas_bloqueadas.get(target_user_id)
    if target_user is None or target_cuenta is None:
        raise ValidationError("La cuenta local no existe.")

    return ContextoAdministracionCuenta(
        actor_user=actor_user,
        actor_cuenta=actor_cuenta,
        target_user=target_user,
        target_cuenta=target_cuenta,
        user_pks_bloqueo=user_pks_bloqueo,
        usuarios_bloqueados=usuarios_bloqueados,
        cuentas_bloqueadas=cuentas_bloqueadas,
        admin_group_user_ids=admin_group_user_ids,
    )


def existen_otros_admins_habilitados(
    contexto: ContextoAdministracionCuenta,
    *,
    excluir_user_id: int,
) -> bool:
    """Indica si queda al menos otro administrador local habilitado distinto del excluido."""
    return any(
        uid != excluir_user_id
        and es_admin_local_habilitado(
            contexto.usuarios_bloqueados.get(uid),
            contexto.cuentas_bloqueadas.get(uid),
            contexto.admin_group_user_ids,
        )
        for uid in contexto.user_pks_bloqueo
    )
