"""Catálogo fijo y servicio administrativo de perfiles para cuentas locales (SPEC-026)."""

from dataclasses import dataclass
from typing import Any

from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from identidad.administracion_cuentas import (
    CAPACIDAD_ADMINISTRAR,
    bloquear_y_revalidar_administracion,
    existen_otros_admins_habilitados,
    grupos_admin_locales,
    validar_motivo_administrativo,
)
from identidad.models import CambioPerfilesCuentaLocal, CuentaLocal
from identidad.services import GROUP_CAPABILITIES, Actor, has_capability

SALT_REFERENCIA_PERFILES = "identidad.perfiles_usuarios.referencia_perfiles.v1"


@dataclass(frozen=True, slots=True)
class PerfilCatalogo:
    """Definición de un perfil administrable del catálogo fijo."""

    clave: str
    nombre: str
    descripcion: str
    grupo: str


PERFILES_CATALOGO: tuple[PerfilCatalogo, ...] = (
    PerfilCatalogo(
        clave="solicitante",
        nombre="Solicitante",
        descripcion=(
            "Presentación y consulta propia de ambos circuitos y documentación propia "
            "según permisos actuales."
        ),
        grupo="local_solicitante",
    ),
    PerfilCatalogo(
        clave="administracion_cuentas",
        nombre="Administración de cuentas",
        descripcion="Gestión de cuentas locales.",
        grupo="local_administracion",
    ),
    PerfilCatalogo(
        clave="configuracion_formularios",
        nombre="Configuración de formularios",
        descripcion="Configuración mediante gestion.configurar.",
        grupo="demo_administracion",
    ),
    PerfilCatalogo(
        clave="operacion_gastos",
        nombre="Operación de gastos",
        descripcion="Consulta global y decisión de gastos.",
        grupo="demo_operadora",
    ),
    PerfilCatalogo(
        clave="registro_pagos",
        nombre="Registro de pagos",
        descripcion="Registro de pagos externos.",
        grupo="demo_gastos_pago",
    ),
    PerfilCatalogo(
        clave="lectura_gastos",
        nombre="Lectura global de gastos",
        descripcion="Consulta global de gastos.",
        grupo="demo_lectura",
    ),
    PerfilCatalogo(
        clave="operacion_facturacion",
        nombre="Operación de facturación",
        descripcion="Consulta global, observación y registro externo de facturas/cobros.",
        grupo="demo_facturacion_operadora",
    ),
    PerfilCatalogo(
        clave="lectura_facturacion",
        nombre="Lectura global de facturación",
        descripcion="Consulta global de facturación.",
        grupo="demo_facturacion_lectura",
    ),
    PerfilCatalogo(
        clave="aporte_documental",
        nombre="Aporte documental",
        descripcion="Incorporación según las autorizaciones por objeto vigentes.",
        grupo="demo_documentos_aporte",
    ),
    PerfilCatalogo(
        clave="revision_documental",
        nombre="Revisión documental",
        descripcion="Revisión documental.",
        grupo="demo_documentos_revision",
    ),
    PerfilCatalogo(
        clave="consulta_documental",
        nombre="Consulta documental",
        descripcion="Consulta de metadatos.",
        grupo="demo_documentos_metadatos",
    ),
    PerfilCatalogo(
        clave="descarga_documental",
        nombre="Descarga documental",
        descripcion="Recuperación/descarga autorizada.",
        grupo="demo_documentos_descarga",
    ),
    PerfilCatalogo(
        clave="verificacion_cobros",
        nombre="Verificación de cobros",
        descripcion="Verificación de cobros.",
        grupo="demo_verificacion_cobros",
    ),
    PerfilCatalogo(
        clave="cierre_facturacion",
        nombre="Cierre y regularización de facturación",
        descripcion="Cierre, anulación y actualización de respaldo.",
        grupo="demo_resolucion_facturacion",
    ),
)

PERFILES_POR_CLAVE: dict[str, PerfilCatalogo] = {p.clave: p for p in PERFILES_CATALOGO}
CLAVE_POR_GRUPO: dict[str, str] = {p.grupo: p.clave for p in PERFILES_CATALOGO}
GRUPOS_GESTIONADOS: frozenset[str] = frozenset(CLAVE_POR_GRUPO)


def perfiles_gestionados_usuario(user: Any) -> list[str]:
    """Devuelve las claves ordenadas de perfiles del catálogo asignados al usuario."""
    nombres = user.groups.values_list("name", flat=True)
    return sorted(CLAVE_POR_GRUPO[nombre] for nombre in nombres if nombre in CLAVE_POR_GRUPO)


def grupos_ajenos_usuario(user: Any) -> list[str]:
    """Devuelve los nombres ordenados de grupos fuera del catálogo que posee el usuario."""
    nombres = user.groups.values_list("name", flat=True)
    return sorted(nombre for nombre in nombres if nombre not in GRUPOS_GESTIONADOS)


def generar_referencia_perfiles(cuenta: CuentaLocal) -> str:
    """Genera una referencia firmada con el PK y las claves gestionadas actuales."""
    payload = {
        "pk": cuenta.pk,
        "perfiles": perfiles_gestionados_usuario(cuenta.user),
    }
    return signing.dumps(payload, salt=SALT_REFERENCIA_PERFILES)


def _validar_perfiles_solicitados(perfiles: Any) -> list[str]:
    """Valida tipo, unicidad y pertenencia al catálogo de la selección solicitada."""
    if isinstance(perfiles, (str, bytes)) or not isinstance(
        perfiles, (list, tuple, set, frozenset)
    ):
        raise ValidationError("La selección de perfiles no tiene un formato válido.")

    claves: list[str] = []
    for item in perfiles:
        if not isinstance(item, str):
            raise ValidationError("Cada perfil seleccionado debe ser una clave de texto válida.")
        claves.append(item)

    if len(set(claves)) != len(claves):
        raise ValidationError("La selección contiene perfiles duplicados.")

    desconocidos = sorted(clave for clave in claves if clave not in PERFILES_POR_CLAVE)
    if desconocidos:
        raise ValidationError("La selección incluye perfiles no reconocidos.")

    return sorted(claves)


def _decodificar_referencia_perfiles(referencia: Any) -> tuple[int, list[str]]:
    """Valida la firma y estructura de la referencia de perfiles."""
    if not isinstance(referencia, str) or not referencia.strip():
        raise ValidationError(
            "Falta la referencia del formulario. Recargue la ficha e intente nuevamente."
        )

    try:
        payload = signing.loads(referencia, salt=SALT_REFERENCIA_PERFILES)
    except signing.BadSignature as exc:
        raise ValidationError(
            "La referencia del formulario es inválida o fue alterada. "
            "Recargue la ficha e intente nuevamente."
        ) from exc

    if not isinstance(payload, dict):
        raise ValidationError(
            "La referencia del formulario es inválida. Recargue la ficha e intente nuevamente."
        )

    pk = payload.get("pk")
    perfiles_ref = payload.get("perfiles")
    if (
        not isinstance(pk, int)
        or isinstance(pk, bool)
        or not isinstance(perfiles_ref, list)
        or any(
            not isinstance(clave, str) or clave not in PERFILES_POR_CLAVE for clave in perfiles_ref
        )
        or len(set(perfiles_ref)) != len(perfiles_ref)
    ):
        raise ValidationError(
            "La referencia del formulario no es válida. Recargue la ficha e intente nuevamente."
        )

    return pk, sorted(perfiles_ref)


def cambiar_perfiles_cuenta(
    actor: Actor | None,
    cuenta_id: int,
    perfiles: list[str] | tuple[str, ...] | set[str] | frozenset[str],
    motivo: str,
    referencia: str,
) -> tuple[CuentaLocal, CambioPerfilesCuentaLocal | None]:
    """Actualiza los perfiles gestionados de una CuentaLocal bajo bloqueo y registra historia.

    Exige ``identidad.administrar_cuentas`` antes de consultar la base, conserva todo grupo
    ajeno al catálogo, impide cambios propios con mutación y protege al último administrador
    local habilitado bajo el mismo protocolo de bloqueo que ``cambiar_actividad_cuenta``.
    """
    if not has_capability(actor, CAPACIDAD_ADMINISTRAR) or actor is None:
        raise PermissionDenied("No posee capacidad para administrar cuentas.")

    perfiles_solicitados = _validar_perfiles_solicitados(perfiles)
    motivo_limpio = validar_motivo_administrativo(motivo)
    ref_pk, ref_perfiles = _decodificar_referencia_perfiles(referencia)

    if not grupos_admin_locales():
        raise PermissionDenied("No existen grupos habilitados para administrar cuentas.")

    with transaction.atomic():
        contexto = bloquear_y_revalidar_administracion(actor, cuenta_id)
        actor_user = contexto.actor_user
        target_user = contexto.target_user
        target_cuenta = contexto.target_cuenta

        if ref_pk != target_cuenta.pk:
            raise ValidationError(
                "La referencia del formulario no corresponde a esta cuenta. "
                "Recargue la ficha e intente nuevamente."
            )

        grupos_actuales = set(target_user.groups.values_list("name", flat=True))
        perfiles_actuales = sorted(
            CLAVE_POR_GRUPO[nombre] for nombre in grupos_actuales if nombre in CLAVE_POR_GRUPO
        )

        if perfiles_actuales == perfiles_solicitados:
            return target_cuenta, None

        if ref_perfiles != perfiles_actuales:
            raise ValidationError(
                "Los perfiles de la cuenta cambiaron desde que abrió el formulario. "
                "Recargue la ficha para revisar los perfiles actuales antes de guardar."
            )

        if target_user.pk == actor_user.pk:
            raise ValidationError("No puede modificar sus propios perfiles.")

        grupos_solicitados = {PERFILES_POR_CLAVE[clave].grupo for clave in perfiles_solicitados}
        grupos_conservados = grupos_actuales - GRUPOS_GESTIONADOS
        grupos_finales = grupos_conservados | grupos_solicitados
        capacidades_finales = frozenset().union(
            *(GROUP_CAPABILITIES[g] for g in grupos_finales if g in GROUP_CAPABILITIES)
        )

        if (
            target_user.pk in contexto.admin_group_user_ids
            and CAPACIDAD_ADMINISTRAR not in capacidades_finales
            and not existen_otros_admins_habilitados(contexto, excluir_user_id=target_user.pk)
        ):
            raise ValidationError(
                "Debe permanecer al menos una cuenta de administración local habilitada."
            )

        grupos_actuales_gestionados = grupos_actuales & GRUPOS_GESTIONADOS
        grupos_a_quitar = grupos_actuales_gestionados - grupos_solicitados
        grupos_a_agregar = grupos_solicitados - grupos_actuales_gestionados

        if grupos_a_quitar:
            target_user.groups.remove(*Group.objects.filter(name__in=grupos_a_quitar))
        if grupos_a_agregar:
            objetos_agregar = [
                Group.objects.get_or_create(name=nombre)[0] for nombre in sorted(grupos_a_agregar)
            ]
            target_user.groups.add(*objetos_agregar)

        evento = CambioPerfilesCuentaLocal.objects.create(
            cuenta=target_cuenta,
            autor=actor_user,
            motivo=motivo_limpio,
            perfiles_anteriores=perfiles_actuales,
            perfiles_nuevos=perfiles_solicitados,
        )
        target_cuenta.refresh_from_db()
        return target_cuenta, evento
