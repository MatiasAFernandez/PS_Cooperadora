"""Consultas y filtrado de gastos según el contrato de identidad."""

from typing import Any

from django.db.models import QuerySet

from gastos.auth import has_capability
from gastos.models import SolicitudGasto


def visible_expenses(actor: Any) -> QuerySet[SolicitudGasto]:
    """Retorna las solicitudes visibles para el actor especificado.

    - gastos.consultar_todas: devuelve todas las solicitudes.
    - gastos.consultar_propias: devuelve exclusivamente las solicitudes propias del actor.
    - Sin esas capacidades o sin actor: devuelve una consulta vacía.
    """
    if actor is None:
        return SolicitudGasto.objects.none()

    if has_capability(actor, "gastos.consultar_todas"):
        return SolicitudGasto.objects.all()

    if has_capability(actor, "gastos.consultar_propias"):
        return SolicitudGasto.objects.filter(solicitante_id=actor.subject_id)

    return SolicitudGasto.objects.none()
