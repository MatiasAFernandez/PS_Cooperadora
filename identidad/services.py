"""Contrato interno de identidad y capacidades para la demostración I1."""

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user
from django.http import HttpRequest

GROUP_CAPABILITIES: dict[str, frozenset[str]] = {
    "demo_solicitante": frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    "demo_operadora": frozenset({"gastos.consultar_todas", "gastos.decidir"}),
    "demo_lectura": frozenset({"gastos.consultar_todas"}),
}
KNOWN_CAPABILITIES = frozenset().union(*GROUP_CAPABILITIES.values())


@dataclass(frozen=True, slots=True)
class Actor:
    """Sujeto local y capacidades calculadas para una petición."""

    subject_id: int
    capabilities: frozenset[str]


def resolve_actor(request: HttpRequest) -> Actor | None:
    """Resolver una sesión Django válida sólo si el adaptador de demo está habilitado."""
    if not settings.DEMO_IDENTITY_ENABLED or not hasattr(request, "session"):
        return None

    # get_user comprueba el backend y el hash de sesión; no acepta request.actor
    # ni valores enviados en parámetros, formularios o cabeceras.
    user = get_user(request)
    if not user.is_authenticated or not user.is_active:
        return None

    # Consultar la base en cada petición: una revocación de grupo no debe quedar
    # fijada en la sesión ni en un caché de permisos de Django.
    group_names = user.groups.values_list("name", flat=True)
    capabilities = frozenset().union(
        *(GROUP_CAPABILITIES[name] for name in group_names if name in GROUP_CAPABILITIES)
    )
    return Actor(subject_id=user.pk, capabilities=capabilities)


def has_capability(actor: Actor | None, code: str) -> bool:
    """Comprobar un código conocido sin permisos implícitos de staff o superusuario."""
    return (
        isinstance(actor, Actor)
        and isinstance(code, str)
        and code in KNOWN_CAPABILITIES
        and code in actor.capabilities
    )
