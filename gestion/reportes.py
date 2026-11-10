"""Resumen de cohortes de solicitudes; importes monetarios siempre separados."""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Prefetch
from django.utils import timezone

from facturacion.models import ComprobanteExterno, SolicitudFacturacion
from facturacion.models_cobros import CobroExterno


def reporte_facturacion(anio, cuatrimestre=None, orden="cantidad"):
    mes = (cuatrimestre - 1) * 4 + 1 if cuatrimestre else 1
    hasta_mes = mes + 4 if cuatrimestre else 13
    inicio = date(anio, mes, 1)
    fin = date(anio + 1, 1, 1) if hasta_mes == 13 else date(anio, hasta_mes, 1)
    solicitudes = (
        SolicitudFacturacion.objects.operativas()
        .filter(
            fecha_presentacion__date__gte=inicio,
            fecha_presentacion__date__lt=fin,
        )
        .select_related("tramite_base")
        .prefetch_related(
            Prefetch("comprobantes", queryset=ComprobanteExterno.objects.all()),
            Prefetch(
                "cobros",
                queryset=CobroExterno.objects.select_related("verificacion__rectificacion"),
            ),
        )
    )
    from facturacion.choices import CentroCosto

    from .formularios import configuracion

    etiquetas_centros = dict(CentroCosto.choices)
    from .models import VersionFormulario

    for campos_historicos in (
        VersionFormulario.objects.filter(configuracion__circuito="FACTURACION")
        .order_by("revision")
        .values_list("campos", flat=True)
    ):
        for campo in campos_historicos:
            if campo["clave"] == "centro_costo":
                etiquetas_centros.update(dict(campo["opciones"]))
    for campo in configuracion("FACTURACION")[1]:
        if campo["clave"] == "centro_costo":
            etiquetas_centros.update(dict(campo["opciones"]))
    cero = Decimal("0.00")
    total = dict(
        cantidad=0,
        anuladas=0,
        solicitado=cero,
        neto=cero,
        confirmado=cero,
        facturas=0,
        suma_facturas=cero,
    )
    grupos = {
        "centros": defaultdict(lambda: dict(cantidad=0, solicitado=cero, neto=cero)),
        "correos": defaultdict(lambda: dict(cantidad=0, solicitado=cero, neto=cero)),
    }
    periodos = defaultdict(lambda: dict(cantidad=0, solicitado=cero, neto=cero))
    for solicitud in solicitudes:
        if solicitud.estado == "ANULADA":
            total["anuladas"] += 1
            continue
        total["cantidad"] += 1
        total["solicitado"] += solicitud.importe_factura
        neto = sum(
            (
                -c.importe if c.tipo == "NOTA_CREDITO" else c.importe
                for c in solicitud.comprobantes.all()
            ),
            cero,
        )
        total["neto"] += neto
        for comprobante in solicitud.comprobantes.all():
            if comprobante.tipo == "FACTURA":
                total["facturas"] += 1
                total["suma_facturas"] += comprobante.importe
        total["confirmado"] += sum(
            (c.importe for c in solicitud.cobros.all() if c.resultado == "CONFIRMADO"), cero
        )
        filas = [
            grupos["centros"][solicitud.centro_costo or "Sin centro asignado"],
            grupos["correos"][solicitud.correo_solicitante],
            periodos[(timezone.localtime(solicitud.fecha_presentacion).month - 1) // 4 + 1],
        ]
        for fila in filas:
            fila["cantidad"] += 1
            fila["solicitado"] += solicitud.importe_factura
            fila["neto"] += neto
    for destino, numerador, denominador in (
        ("promedio_solicitud", "solicitado", "cantidad"),
        ("promedio_factura", "suma_facturas", "facturas"),
    ):
        total[destino] = (
            (total[numerador] / total[denominador]).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if total[denominador]
            else cero
        )
    for grupo, filas in grupos.items():
        total[grupo] = sorted(
            (
                dict(nombre=etiquetas_centros.get(k, k) if grupo == "centros" else k, **v)
                for k, v in filas.items()
            ),
            key=lambda f: (-f[orden], f["nombre"]),
        )
    total["periodos"] = [dict(nombre=f"Cuatrimestre {k}", **periodos[k]) for k in sorted(periodos)]
    return total
