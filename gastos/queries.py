"""Consultas y filtrado de gastos según el contrato de identidad."""

from typing import Any

from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery

from documentos.models import Documento, RevisionDocumento
from gastos.auth import has_capability
from gastos.models import SolicitudGasto, TipoFlujoGasto


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


def compras_directas_con_deuda_documental() -> QuerySet[SolicitudGasto]:
    """Compras pagadas y abiertas sin una factura vigente en revisión o aceptada."""
    ultima_revision = RevisionDocumento.objects.filter(
        documento_id=OuterRef("pk")
    ).order_by("-id")
    facturas_vigentes = Documento.objects.filter(
        tipo=Documento.Tipo.FACTURA_PROVEEDOR, sucesor__isnull=True,
    ).filter(
        Q(solicitud_gasto_id=OuterRef("pk"))
        | Q(solicitud_gasto_id__isnull=True, tramite_base_id=OuterRef("tramite_base_id"))
    )
    facturas_validas = facturas_vigentes.alias(
        ultimo_resultado=Subquery(ultima_revision.values("resultado")[:1])
    ).filter(
        Q(ultimo_resultado__isnull=True) | Q(ultimo_resultado=RevisionDocumento.Resultado.ACEPTADO)
    )
    return (
        SolicitudGasto.objects.filter(
            tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
            pago_externo__isnull=False,
            cierre__isnull=True,
        )
        .filter(~Exists(facturas_validas))
        .annotate(factura_para_corregir=Exists(facturas_vigentes))
    )
