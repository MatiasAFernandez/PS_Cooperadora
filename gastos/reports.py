"""Servicio y DTOs de agregación para el Reporte Directivo Cuatrimestral (Issue #94 / GAST-R08)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce, ExtractYear
from django.utils import timezone

from gastos.models import CentroCosto, PagoExterno, SolicitudGasto


@dataclass(frozen=True)
class MetricasCuatrimestreDTO:
    """Métricas consolidadas para un cuatrimestre del año calendario."""

    cuatrimestre: int
    etiqueta: str
    fecha_inicio: date
    fecha_fin: date
    cantidad_solicitudes: int
    monto_solicitado: Decimal
    cantidad_pagos: int
    monto_erogado_bruto: Decimal
    monto_retencion_atp: Decimal
    monto_neto_transferido: Decimal


@dataclass(frozen=True)
class MetricasCentroCostoDTO:
    """Métricas acumuladas para un Centro de Costo institucional o fila sin asignar."""

    centro_costo_id: int | None
    codigo: str
    nombre: str
    activo: bool
    cantidad_solicitudes: int
    monto_solicitado: Decimal
    cantidad_pagos: int
    monto_erogado_bruto: Decimal
    monto_retencion_atp: Decimal
    monto_neto_transferido: Decimal


@dataclass(frozen=True)
class TotalesReporteDTO:
    """Métricas globales agregadas para el año calendario."""

    cantidad_solicitudes: int
    monto_solicitado: Decimal
    cantidad_pagos: int
    monto_erogado_bruto: Decimal
    monto_retencion_atp: Decimal
    monto_neto_transferido: Decimal


@dataclass(frozen=True)
class ReporteCuatrimestralDTO:
    """DTO integral del reporte cuatrimestral directivo."""

    anio: int
    anios_disponibles: tuple[int, ...]
    cuatrimestres: tuple[MetricasCuatrimestreDTO, ...]
    centros_costo: tuple[MetricasCentroCostoDTO, ...]
    totales: TotalesReporteDTO


def obtener_anios_disponibles_gastos() -> tuple[int, ...]:
    """Obtiene los años con actividad registrada en gastos o el año en curso."""
    anio_actual = timezone.localdate().year
    anios_solicitudes = set(
        SolicitudGasto.objects.annotate(y=ExtractYear("fecha_creacion")).values_list(
            "y", flat=True
        )
    )
    anios_pagos = set(
        PagoExterno.objects.annotate(y=ExtractYear("fecha_pago")).values_list(
            "y", flat=True
        )
    )
    todos = {int(y) for y in (anios_solicitudes | anios_pagos | {anio_actual}) if y is not None}
    return tuple(sorted(todos, reverse=True))


def obtener_reporte_cuatrimestral_gastos(anio: int | None = None) -> ReporteCuatrimestralDTO:
    """Calcula las métricas agregadas por cuatrimestre y centro de costo para el año dado."""
    anios_disponibles = obtener_anios_disponibles_gastos()
    anio_actual = timezone.localdate().year

    if anio is None or anio not in anios_disponibles:
        if anio is not None and 2000 <= anio <= 2100:
            anio_elegido = anio
        elif anios_disponibles:
            anio_elegido = anios_disponibles[0]
        else:
            anio_elegido = anio_actual
    else:
        anio_elegido = anio

    # 1. Definición canónica de los 3 Cuatrimestres
    rangos_cuatrimestres = (
        (1, "C1 (Enero – Abril)", date(anio_elegido, 1, 1), date(anio_elegido, 4, 30)),
        (2, "C2 (Mayo – Agosto)", date(anio_elegido, 5, 1), date(anio_elegido, 8, 31)),
        (3, "C3 (Septiembre – Diciembre)", date(anio_elegido, 9, 1), date(anio_elegido, 12, 31)),
    )

    cero = Decimal("0.00")
    cuatrimestres_dto: list[MetricasCuatrimestreDTO] = []

    for num, etiqueta, inicio, fin in rangos_cuatrimestres:
        solic_agg = SolicitudGasto.objects.filter(
            fecha_creacion__date__range=(inicio, fin)
        ).aggregate(
            cant=Count("id"),
            monto=Coalesce(Sum("monto_estimado"), cero),
        )

        pagos_agg = PagoExterno.objects.filter(
            fecha_pago__range=(inicio, fin)
        ).aggregate(
            cant=Count("id"),
            bruto=Coalesce(Sum("monto_bruto"), cero),
            atp=Coalesce(Sum("monto_retencion_atp"), cero),
            neto=Coalesce(Sum("importe"), cero),
        )

        cuatrimestres_dto.append(
            MetricasCuatrimestreDTO(
                cuatrimestre=num,
                etiqueta=etiqueta,
                fecha_inicio=inicio,
                fecha_fin=fin,
                cantidad_solicitudes=solic_agg["cant"] or 0,
                monto_solicitado=solic_agg["monto"],
                cantidad_pagos=pagos_agg["cant"] or 0,
                monto_erogado_bruto=pagos_agg["bruto"],
                monto_retencion_atp=pagos_agg["atp"],
                monto_neto_transferido=pagos_agg["neto"],
            )
        )

    # Totales anuales consolidados
    totales = TotalesReporteDTO(
        cantidad_solicitudes=sum(c.cantidad_solicitudes for c in cuatrimestres_dto),
        monto_solicitado=sum(c.monto_solicitado for c in cuatrimestres_dto),
        cantidad_pagos=sum(c.cantidad_pagos for c in cuatrimestres_dto),
        monto_erogado_bruto=sum(c.monto_erogado_bruto for c in cuatrimestres_dto),
        monto_retencion_atp=sum(c.monto_retencion_atp for c in cuatrimestres_dto),
        monto_neto_transferido=sum(c.monto_neto_transferido for c in cuatrimestres_dto),
    )

    # 2. Agrupación por Centro de Costo para el año completo
    fecha_inicio_anio = date(anio_elegido, 1, 1)
    fecha_fin_anio = date(anio_elegido, 12, 31)

    solicitudes_cc_agg = {
        row["centro_costo"]: row
        for row in (
            SolicitudGasto.objects.filter(
                fecha_creacion__date__range=(fecha_inicio_anio, fecha_fin_anio)
            )
            .values("centro_costo")
            .annotate(
                cant=Count("id"),
                monto=Coalesce(Sum("monto_estimado"), cero),
            )
        )
    }

    pagos_cc_agg = {
        row["solicitud__centro_costo"]: row
        for row in (
            PagoExterno.objects.filter(
                fecha_pago__range=(fecha_inicio_anio, fecha_fin_anio)
            )
            .values("solicitud__centro_costo")
            .annotate(
                cant=Count("id"),
                bruto=Coalesce(Sum("monto_bruto"), cero),
                atp=Coalesce(Sum("monto_retencion_atp"), cero),
                neto=Coalesce(Sum("importe"), cero),
            )
        )
    }

    centros_costo_dto: list[MetricasCentroCostoDTO] = []
    centros_existentes = list(CentroCosto.objects.order_by("codigo", "nombre"))

    for cc in centros_existentes:
        s_data = solicitudes_cc_agg.get(cc.pk, {})
        p_data = pagos_cc_agg.get(cc.pk, {})

        centros_costo_dto.append(
            MetricasCentroCostoDTO(
                centro_costo_id=cc.pk,
                codigo=cc.codigo,
                nombre=cc.nombre,
                activo=cc.activo,
                cantidad_solicitudes=s_data.get("cant", 0),
                monto_solicitado=s_data.get("monto", cero),
                cantidad_pagos=p_data.get("cant", 0),
                monto_erogado_bruto=p_data.get("bruto", cero),
                monto_retencion_atp=p_data.get("atp", cero),
                monto_neto_transferido=p_data.get("neto", cero),
            )
        )

    # Fila de respaldo para solicitudes históricas o sin centro de costo asignado
    sin_cc_sol = solicitudes_cc_agg.get(None, {})
    sin_cc_pago = pagos_cc_agg.get(None, {})
    centros_costo_dto.append(
        MetricasCentroCostoDTO(
            centro_costo_id=None,
            codigo="-",
            nombre="Sin centro de costo asignado / Histórico",
            activo=True,
            cantidad_solicitudes=sin_cc_sol.get("cant", 0),
            monto_solicitado=sin_cc_sol.get("monto", cero),
            cantidad_pagos=sin_cc_pago.get("cant", 0),
            monto_erogado_bruto=sin_cc_pago.get("bruto", cero),
            monto_retencion_atp=sin_cc_pago.get("atp", cero),
            monto_neto_transferido=sin_cc_pago.get("neto", cero),
        )
    )

    return ReporteCuatrimestralDTO(
        anio=anio_elegido,
        anios_disponibles=anios_disponibles,
        cuatrimestres=tuple(cuatrimestres_dto),
        centros_costo=tuple(centros_costo_dto),
        totales=totales,
    )
