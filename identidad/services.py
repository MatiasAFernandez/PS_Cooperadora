"""Contrato interno de identidad y capacidades para los circuitos de la aplicación."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user
from django.http import HttpRequest

GROUP_CAPABILITIES: dict[str, frozenset[str]] = {
    "demo_administracion": frozenset({"gestion.configurar"}),
    "demo_solicitante": frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    "demo_operadora": frozenset({"gastos.consultar_todas", "gastos.decidir"}),
    "demo_lectura": frozenset({"gastos.consultar_todas"}),
    "demo_gastos_pago": frozenset({"gastos.registrar_pago"}),
    "demo_facturacion_solicitante": frozenset(
        {
            "facturacion.presentar",
            "facturacion.consultar_propias",
            "facturacion.corregir",
            "facturacion.informar_cobro",
        }
    ),
    "demo_facturacion_lectura": frozenset({"facturacion.consultar_todas"}),
    "demo_facturacion_operadora": frozenset(
        {
            "facturacion.consultar_todas",
            "facturacion.observar",
            "facturacion.registrar_factura_externa",
            "facturacion.registrar_cobro",
        }
    ),
    "demo_documentos_aporte": frozenset({"documentos.incorporar"}),
    "demo_documentos_revision": frozenset({"documentos.revisar"}),
    "demo_verificacion_cobros": frozenset({"facturacion.verificar_cobro"}),
    "demo_resolucion_facturacion": frozenset(
        {
            "facturacion.cerrar",
            "facturacion.anular",
            "facturacion.actualizar_respaldo",
        }
    ),
    "demo_documentos_metadatos": frozenset(
        {"documentos.consultar_metadatos", "documentos.ver_metadatos"}
    ),
    "demo_documentos_descarga": frozenset(
        {"documentos.recuperar_contenido", "documentos.descargar"}
    ),
    "local_solicitante": frozenset(
        {
            "gastos.presentar",
            "gastos.consultar_propias",
            "facturacion.presentar",
            "facturacion.consultar_propias",
            "facturacion.corregir",
            "facturacion.informar_cobro",
            "documentos.incorporar",
            "documentos.consultar_metadatos",
            "documentos.ver_metadatos",
            "documentos.recuperar_contenido",
            "documentos.descargar",
        }
    ),
    "local_administracion": frozenset({"identidad.administrar_cuentas"}),
}
KNOWN_CAPABILITIES = frozenset().union(*GROUP_CAPABILITIES.values())


@dataclass(frozen=True, slots=True)
class Actor:
    """Sujeto local y capacidades calculadas para una petición."""

    subject_id: int
    capabilities: frozenset[str]
    email_registrado: str | None = None


def actor_para_usuario(
    user: Any,
    *,
    group_names: Iterable[str] | None = None,
) -> Actor | None:
    """Construir Actor para un usuario activo según adaptadores y reglas vigentes."""
    local_enabled = getattr(settings, "LOCAL_IDENTITY_ENABLED", False)
    demo_enabled = getattr(settings, "DEMO_IDENTITY_ENABLED", False)
    if not local_enabled and not demo_enabled:
        return None

    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return None

    # Import diferido de CuentaLocal para evitar dependencias circulares
    from identidad.models import CuentaLocal

    # El descriptor reverso cachea la cuenta (o su ausencia) en este usuario.
    # Así request.user.cuenta_local en las plantillas no repite la consulta,
    # mientras cada petición vuelve a comprobar el estado en la base.
    cuenta = getattr(user, "cuenta_local", None)

    resolved_group_names = (
        user.groups.values_list("name", flat=True) if group_names is None else group_names
    )

    if cuenta is not None:
        # Si el usuario tiene CuentaLocal, SOLO LOCAL_IDENTITY_ENABLED y estado
        # APROBADA con correo verificado autorizan al Actor. Sin fallback a demo.
        if not local_enabled:
            return None
        if cuenta.email_verificado_en is None:
            return None
        if cuenta.estado != CuentaLocal.Estado.APROBADA:
            return None

        capabilities = frozenset().union(
            *(
                GROUP_CAPABILITIES[name]
                for name in resolved_group_names
                if name in GROUP_CAPABILITIES
            )
        )
        return Actor(
            subject_id=user.pk,
            capabilities=capabilities,
            email_registrado=cuenta.email.strip() or None,
        )

    # Si NO tiene CuentaLocal, únicamente DEMO_IDENTITY_ENABLED autoriza como antes
    if not demo_enabled:
        return None

    # demo legado NO puede obtener local_* capabilities aunque se le agregue
    # el grupo local_administracion
    capabilities = frozenset().union(
        *(
            GROUP_CAPABILITIES[name]
            for name in resolved_group_names
            if name in GROUP_CAPABILITIES and not name.startswith("local_")
        )
    )
    capabilities = frozenset(
        c for c in capabilities if not c.startswith("identidad.") and not c.startswith("local_")
    )
    return Actor(
        subject_id=user.pk,
        capabilities=capabilities,
        email_registrado=user.email.strip() or None,
    )


def resolve_actor(request: HttpRequest) -> Actor | None:
    """Resolver una sesión Django válida según adaptadores habilitados."""
    if not hasattr(request, "session"):
        return None

    local_enabled = getattr(settings, "LOCAL_IDENTITY_ENABLED", False)
    demo_enabled = getattr(settings, "DEMO_IDENTITY_ENABLED", False)
    if not local_enabled and not demo_enabled:
        return None

    # get_user comprueba el backend y el hash de sesión; no acepta request.actor
    # ni valores enviados en parámetros, formularios o cabeceras.
    user = get_user(request)
    if not user.is_authenticated or not user.is_active:
        return None

    # Reutilizar en la misma petición el usuario ya verificado evita una segunda
    # consulta cuando la plantilla accede a request.user (base y navegación).
    request.user = user
    return actor_para_usuario(user)


def has_capability(actor: Actor | None, code: str) -> bool:
    """Comprobar un código conocido sin permisos implícitos de staff o superusuario."""
    return (
        isinstance(actor, Actor)
        and isinstance(code, str)
        and code in KNOWN_CAPABILITIES
        and code in actor.capabilities
    )
