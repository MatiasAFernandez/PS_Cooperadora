"""Consumo del contrato interno de identidad y permisos (SPEC-002 / T02)."""

from identidad.services import has_capability, resolve_actor

__all__ = ["has_capability", "resolve_actor"]
