"""Filtros sobre un queryset previamente limitado por permisos."""

from decimal import Decimal

from django.db.models import (
    Case,
    DecimalField,
    Exists,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from .models import CobroExterno, ComprobanteExterno


def filtrar_solicitudes(consulta, form):
    if not form.is_valid():
        return consulta.none()
    consulta = form.filtrar_fecha(consulta, "fecha_presentacion")
    texto = form.cleaned_data["q"]
    if texto:
        criterio = (
            Q(nombre_solicitante__icontains=texto)
            | Q(nombre_receptor__icontains=texto)
            | Q(cuit_receptor__icontains=texto)
            | Q(detalle_factura__icontains=texto)
        )
        if texto.isascii() and texto.isdigit() and len(texto) <= 18:
            consulta = consulta.con_numero_solicitante()
            criterio = Q(_numero_solicitante=int(texto)) | Q(cuit_receptor=texto)
        consulta = consulta.filter(criterio)
    estado = form.cleaned_data["estado"]
    if not estado:
        return consulta
    if estado in {"OBSERVADA", "CERRADA", "ANULADA"}:
        return consulta.filter(estado=estado)
    comprobantes = ComprobanteExterno.objects.filter(solicitud_id=OuterRef("pk"))
    consulta = consulta.filter(estado="PRESENTADA").annotate(
        tiene_factura=Exists(comprobantes.filter(tipo="FACTURA")),
    )
    if estado == "PRESENTADA":
        return consulta.filter(tiene_factura=False)
    decimal = DecimalField(max_digits=24, decimal_places=2)
    neto = (
        comprobantes.order_by()
        .values("solicitud_id")
        .annotate(
            total=Sum(
                Case(
                    When(tipo="NOTA_CREDITO", then=-F("importe")),
                    default=F("importe"),
                    output_field=decimal,
                )
            )
        )
        .values("total")
    )
    confirmado = (
        CobroExterno.objects.filter(
            solicitud_id=OuterRef("pk"),
            verificacion__resultado="CONFIRMADO",
        )
        .order_by()
        .values("solicitud_id")
        .annotate(total=Sum("importe"))
        .values("total")
    )
    consulta = consulta.filter(tiene_factura=True).annotate(
        neto_filtro=Coalesce(
            Subquery(neto, output_field=decimal), Value(Decimal("0.00")), output_field=decimal
        ),
        confirmado_filtro=Coalesce(
            Subquery(confirmado, output_field=decimal), Value(Decimal("0.00")), output_field=decimal
        ),
    )
    cubierta = Q(neto_filtro__gte=0, confirmado_filtro__gte=F("neto_filtro"))
    return consulta.filter(cubierta if estado == "COBRADA_EN_REVISION" else ~cubierta)
