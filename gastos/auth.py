"""Consumo del contrato interno de identidad y permisos (SPEC-002 / T02)."""

import importlib.util
from typing import Any


def resolve_actor(request: Any) -> Any:
    """Resuelve el actor para la petición actual delegando en identidad.services.

    Si el componente identidad no está disponible (T02 pendiente), retorna None de forma segura.
    No recurre a identidades alternativas ni oculta errores internos del adaptador.
    """
    try:
        spec = importlib.util.find_spec("identidad.services")
        if spec is None:
            return None
        module = importlib.import_module("identidad.services")
        return module.resolve_actor(request)
    except ModuleNotFoundError as exc:
        if exc.name in ("identidad", "identidad.services"):
            return None
        raise


def has_capability(actor: Any, code: str) -> bool:
    """Verifica si el actor posee una capacidad determinada delegando en identidad.services.

    Si el componente identidad no está disponible o el actor es None, retorna False.
    No evalúa capacidades localmente ni oculta errores internos del adaptador.
    """
    if actor is None:
        return False

    try:
        spec = importlib.util.find_spec("identidad.services")
        if spec is None:
            return False
        module = importlib.import_module("identidad.services")
        return module.has_capability(actor, code)
    except ModuleNotFoundError as exc:
        if exc.name in ("identidad", "identidad.services"):
            return False
        raise
