"""Matriz compartida de autorización y consultas filtradas de avisos por tipo."""

from __future__ import annotations

import operator
from functools import reduce

from django.db.models import Exists, OuterRef, Q, QuerySet

from avisos.models import Aviso, TipoAviso
from gastos.models import DecisionGasto, SolicitudGasto
from gastos.queries import visible_expenses
from identidad.services import Actor, has_capability

CAPACIDAD_CONSULTAR_PROPIAS = "gastos.consultar_propias"
CAPACIDAD_CONSULTAR_TODAS = "gastos.consultar_todas"
CAPACIDAD_DECIDIR = "gastos.decidir"

TIPOS_AVISO_ADMITIDOS: tuple[str, ...] = (
    TipoAviso.NUEVA_SOLICITUD_GASTO,
    TipoAviso.DECISION_SOLICITUD_GASTO,
)


def puede_acceder_bandeja_avisos(actor: Actor | None) -> bool:
    """Indica si el actor posee al menos una capacidad de consulta de Gastos."""
    if actor is None:
        return False
    return has_capability(actor, CAPACIDAD_CONSULTAR_PROPIAS) or has_capability(
        actor, CAPACIDAD_CONSULTAR_TODAS
    )


def evaluar_autorizacion_aviso(
    *,
    tipo: str,
    actor: Actor | None,
    destinatario_id: int,
    solicitud: SolicitudGasto,
    decision: DecisionGasto | None = None,
) -> tuple[bool, str]:
    """Evalúa la matriz de autorización para recibir o emitir un aviso por tipo."""
    if tipo == TipoAviso.NUEVA_SOLICITUD_GASTO:
        if destinatario_id == solicitud.solicitante_id:
            return False, "autor_excluido"
        if (
            actor is None
            or actor.subject_id != destinatario_id
            or not has_capability(actor, CAPACIDAD_CONSULTAR_TODAS)
            or not has_capability(actor, CAPACIDAD_DECIDIR)
        ):
            return False, "sin_permisos"
        return True, ""

    if tipo == TipoAviso.DECISION_SOLICITUD_GASTO:
        if decision is None:
            return False, "decision_inexistente"
        if decision.solicitud_id != solicitud.pk:
            return False, "decision_inconsistente"
        if actor is None or actor.subject_id != destinatario_id:
            return False, "sin_permisos"
        if solicitud.solicitante_id != destinatario_id:
            return False, "no_titular"
        if not visible_expenses(actor).filter(pk=solicitud.pk).exists():
            return False, "sin_permisos"
        return True, ""

    return False, "tipo_desconocido"


def avisos_autorizados_queryset(actor: Actor | None) -> QuerySet[Aviso]:
    """Devuelve los avisos del actor autorizados por destinatario, tipo y visibilidad."""
    if actor is None:
        return Aviso.objects.none()

    filtros_tipo: list[Q] = []

    if has_capability(actor, CAPACIDAD_CONSULTAR_TODAS) and has_capability(
        actor, CAPACIDAD_DECIDIR
    ):
        autor_es_titular = Exists(
            SolicitudGasto.objects.filter(
                pk=OuterRef("solicitud_id"),
                solicitante_id=actor.subject_id,
            )
        )
        filtros_tipo.append(
            Q(tipo=TipoAviso.NUEVA_SOLICITUD_GASTO, decision_id__isnull=True)
            & ~autor_es_titular
        )

    if puede_acceder_bandeja_avisos(actor):
        visibles_ids = visible_expenses(actor).values("pk")
        decision_valida = Exists(
            DecisionGasto.objects.filter(
                pk=OuterRef("decision_id"),
                solicitud_id=OuterRef("solicitud_id"),
                solicitud__solicitante_id=actor.subject_id,
                solicitud_id__in=visibles_ids,
            )
        )
        filtros_tipo.append(
            Q(tipo=TipoAviso.DECISION_SOLICITUD_GASTO, decision_id__isnull=False)
            & decision_valida
        )

    if not filtros_tipo:
        return Aviso.objects.none()

    return (
        Aviso.objects.filter(destinatario_id=actor.subject_id)
        .filter(reduce(operator.or_, filtros_tipo))
        .order_by("-creada_en", "-pk")
    )
