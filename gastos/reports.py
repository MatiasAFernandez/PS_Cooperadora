"""Servicio y DTOs de agregación del Reporte Directivo Cuatrimestral (GAST-R08)."""

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import Count, Exists, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce, ExtractYear
from django.utils import timezone

from documentos.models import Documento, RevisionDocumento
from gastos.models import (
    CentroCosto,
    EstadoSolicitud,
    PagoExterno,
    SolicitudGasto,
    TipoFlujoGasto,
)

CERO = Decimal("0.00")
CIEN = Decimal("100.00")
CENTAVO_PORCENTUAL = Decimal("0.01")
CORTE_ANIO = "ANIO"
CORTES_REPORTE = frozenset({"ANIO", "C1", "C2", "C3", "MES_ANT"})
MODALIDAD_COMPRA_DIRECTA = TipoFlujoGasto.COMPRA_DIRECTA.value
MODALIDAD_REINTEGRO = TipoFlujoGasto.REINTEGRO.value
MESES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _condicion_compromiso() -> Q:
    """Solicitud aceptada que todavía no tiene pago registrado."""
    return Q(
        estado=EstadoSolicitud.ACEPTADA,
        pago_externo__isnull=True,
    )


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
    porcentaje_bruto_grafico: Decimal = CERO
    porcentaje_atp_grafico: Decimal = CERO


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
    cantidad_comprometida: int = 0
    monto_comprometido: Decimal = CERO
    porcentaje_gasto: Decimal = CERO
    porcentaje_bruto_grafico: Decimal = CERO
    porcentaje_atp_grafico: Decimal = CERO


@dataclass(frozen=True)
class TotalesReporteDTO:
    """Métricas globales agregadas para el corte y la modalidad indicados."""

    cantidad_solicitudes: int
    monto_solicitado: Decimal
    cantidad_pagos: int
    monto_erogado_bruto: Decimal
    monto_retencion_atp: Decimal
    monto_neto_transferido: Decimal
    cantidad_comprometida: int = 0
    monto_comprometido: Decimal = CERO
    porcentaje_gasto: Decimal = CERO
    cantidad_pagos_atp: int = 0


@dataclass(frozen=True)
class ReporteCuatrimestralDTO:
    """DTO integral del reporte cuatrimestral directivo."""

    anio: int
    anios_disponibles: tuple[int, ...]
    cuatrimestres: tuple[MetricasCuatrimestreDTO, ...]
    centros_costo: tuple[MetricasCentroCostoDTO, ...]
    totales: TotalesReporteDTO
    corte: str = CORTE_ANIO
    modalidad: str = ""
    periodo_label: str = ""


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


def _normalizar_corte(corte: str | None) -> str:
    """Devuelve un corte admitido; un valor ausente o inválido cae en el anual."""
    valor = (corte or "").strip().upper()
    return valor if valor in CORTES_REPORTE else CORTE_ANIO


def _normalizar_modalidad(modalidad: str | None) -> str | None:
    """Devuelve la modalidad admitida o None cuando no corresponde filtrar."""
    valor = (modalidad or "").strip().upper()
    if valor in (MODALIDAD_COMPRA_DIRECTA, MODALIDAD_REINTEGRO):
        return valor
    return None


def _mes_anterior(hoy: date) -> tuple[date, date]:
    """Rango real del mes calendario inmediatamente anterior a ``hoy``."""
    fin = hoy.replace(day=1) - timedelta(days=1)
    inicio = fin.replace(day=1)
    return inicio, fin


def _resolver_anio(
    anio: int | None,
    anios_disponibles: tuple[int, ...],
    *,
    predeterminado: int | None = None,
) -> int:
    """Conserva la selección histórica de año y sus fallbacks defensivos."""
    if anio is not None and anio in anios_disponibles:
        return anio
    if anio is not None and 2000 <= anio <= 2100:
        return anio
    if anio is None and predeterminado is not None:
        return predeterminado
    if anios_disponibles:
        return anios_disponibles[0]
    return timezone.localdate().year


def _resolver_periodo(corte: str, anio: int, hoy: date) -> tuple[date, date, str]:
    """Devuelve inicio, fin y etiqueta legible del corte solicitado.

    ``MES_ANT`` se calcula con el mes calendario anterior real a ``hoy``; el
    año seleccionado sigue rigiendo la serie anual de cuatrimestres.
    """
    if corte == "C1":
        inicio, fin = date(anio, 1, 1), date(anio, 4, 30)
        etiqueta = f"1° Cuatrimestre {anio}"
    elif corte == "C2":
        inicio, fin = date(anio, 5, 1), date(anio, 8, 31)
        etiqueta = f"2° Cuatrimestre {anio}"
    elif corte == "C3":
        inicio, fin = date(anio, 9, 1), date(anio, 12, 31)
        etiqueta = f"3° Cuatrimestre {anio}"
    elif corte == "MES_ANT":
        inicio, fin = _mes_anterior(hoy)
        nombre_mes = MESES_ES[inicio.month - 1].capitalize()
        return (
            inicio,
            fin,
            (
                f"Mes anterior ({nombre_mes} {inicio.year}: "
                f"{inicio:%d/%m/%Y} al {fin:%d/%m/%Y})"
            ),
        )
    else:
        inicio, fin = date(anio, 1, 1), date(anio, 12, 31)
        etiqueta = f"Año completo {anio}"

    return (
        inicio,
        fin,
        f"{etiqueta} ({inicio:%d/%m/%Y} al {fin:%d/%m/%Y})",
    )


def _agregar_solicitudes(queryset: Any) -> dict[str, Any]:
    """Agrega cantidad, monto solicitado y compromiso sin pago."""
    return queryset.aggregate(
        cantidad=Count("id"),
        monto=Coalesce(Sum("monto_estimado"), CERO),
        cantidad_comprometida=Count(
            "id",
            filter=_condicion_compromiso(),
        ),
        monto_comprometido=Coalesce(
            Sum("monto_estimado", filter=_condicion_compromiso()),
            CERO,
        ),
    )


def _agregar_pagos(queryset: Any) -> dict[str, Any]:
    """Agrega cantidad, bruto, retención ATP, neto y pagos alcanzados por ATP."""
    return queryset.aggregate(
        cantidad=Count("id"),
        bruto=Coalesce(Sum("monto_bruto"), CERO),
        atp=Coalesce(Sum("monto_retencion_atp"), CERO),
        neto=Coalesce(Sum("importe"), CERO),
        cantidad_atp=Count("id", filter=Q(monto_retencion_atp__gt=0)),
    )


def _porcentaje_participacion(parte: Decimal, total: Decimal) -> Decimal:
    """Porcentaje decimal (0–100) de una parte sobre un total."""
    if total <= CERO:
        return CERO
    return (parte / total * CIEN).quantize(
        CENTAVO_PORCENTUAL,
        rounding=ROUND_HALF_UP,
    )


def _porcentaje_grafico(valor: Decimal, maximo: Decimal) -> Decimal:
    """Porcentaje decimal (0–100) relativo al máximo de su serie."""
    if maximo <= CERO:
        return CERO
    porcentaje = (valor / maximo * CIEN).quantize(
        CENTAVO_PORCENTUAL,
        rounding=ROUND_HALF_UP,
    )
    if porcentaje < CERO:
        return CERO
    if porcentaje > CIEN:
        return CIEN
    return porcentaje


def _subquery_factura_valida() -> Any:
    """Factura vigente con última revisión no rechazada, para una solicitud.

    Replica las reglas de ``verificar_deuda_documental_solicitante`` sin
    recorrer solicitantes ni solicitudes: una factura reemplazada no cuenta y
    la última revisión (por id) debe ser aceptada, observada o inexistente.
    Los documentos sin solicitud directa se asocian por su trámite base.
    """
    ultima_revision = RevisionDocumento.objects.filter(
        documento=OuterRef("pk")
    ).order_by("-id")
    return (
        Documento.objects.filter(
            tipo=Documento.Tipo.FACTURA_PROVEEDOR,
            sucesor__isnull=True,
        )
        .annotate(
            ultimo_resultado=Subquery(
                ultima_revision.values("resultado")[:1]
            )
        )
        .filter(
            Q(ultimo_resultado__isnull=True)
            | Q(
                ultimo_resultado__in=(
                    RevisionDocumento.Resultado.ACEPTADO,
                    RevisionDocumento.Resultado.OBSERVADO,
                )
            )
        )
        .filter(
            Q(solicitud_gasto_id=OuterRef("pk"))
            | (
                Q(solicitud_gasto_id__isnull=True)
                & Q(tramite_base_id=OuterRef("tramite_base_id"))
            )
        )
    )


def obtener_pendientes_actuales_gastos() -> dict[str, Any]:
    """Recuentos globales al día de pendientes documentales, por modalidad.

    No dependen del período ni del año elegido. ``sin_factura`` aplica sólo a
    compras directas pagadas y usa las mismas reglas de deuda documental
    vigentes, sin calcular mora ni cierre. ``sin_atp`` cuenta pagos con
    retención positiva y constancia pendiente. ``monto`` suma el bruto pagado
    en el primer caso y la retención ATP en el segundo; ``por_modalidad``
    desglosa la cantidad.
    """
    factura_valida = _subquery_factura_valida()
    sin_factura = (
        SolicitudGasto.objects.filter(
            tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
            pago_externo__isnull=False,
        )
        .annotate(tiene_factura_valida=Exists(factura_valida))
        .filter(tiene_factura_valida=False)
        .aggregate(
            cantidad=Count("id"),
            monto=Coalesce(Sum("pago_externo__monto_bruto"), CERO),
        )
    )
    sin_atp = PagoExterno.objects.filter(
        monto_retencion_atp__gt=CERO,
        constancia_atp__isnull=True,
    ).aggregate(
        cantidad=Count("id"),
        monto=Coalesce(Sum("monto_retencion_atp"), CERO),
        cantidad_compra_directa=Count(
            "id",
            filter=Q(solicitud__tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA),
        ),
        cantidad_reintegro=Count(
            "id",
            filter=Q(solicitud__tipo_flujo=TipoFlujoGasto.REINTEGRO),
        ),
    )

    cantidad_sin_factura = sin_factura["cantidad"] or 0
    return {
        "sin_factura": {
            "cantidad": cantidad_sin_factura,
            "monto": sin_factura["monto"] or CERO,
            "por_modalidad": {
                MODALIDAD_COMPRA_DIRECTA: cantidad_sin_factura,
                MODALIDAD_REINTEGRO: 0,
            },
        },
        "sin_atp": {
            "cantidad": sin_atp["cantidad"] or 0,
            "monto": sin_atp["monto"] or CERO,
            "por_modalidad": {
                MODALIDAD_COMPRA_DIRECTA: sin_atp["cantidad_compra_directa"] or 0,
                MODALIDAD_REINTEGRO: sin_atp["cantidad_reintegro"] or 0,
            },
        },
    }


def obtener_reporte_cuatrimestral_gastos(
    anio: int | None = None,
    corte: str | None = None,
    modalidad: str | None = None,
    *,
    centro_costo_id: int | None = None,
) -> ReporteCuatrimestralDTO:
    """Calcula las métricas del corte, modalidad y centro indicados.

    ``reporte.cuatrimestres`` conserva la serie anual (C1–C3) del año elegido
    y aplica los filtros de modalidad y centro. Los totales y el desglose por
    centro también aplican el corte. Sin parámetros se conserva el reporte anual.
    """
    if isinstance(anio, str):
        try:
            anio = int(anio)
        except (TypeError, ValueError):
            anio = None

    anios_disponibles = obtener_anios_disponibles_gastos()
    corte_normalizado = _normalizar_corte(corte)
    modalidad_normalizada = _normalizar_modalidad(modalidad)
    hoy = timezone.localdate()

    anio_predeterminado = None
    if corte_normalizado == "MES_ANT" and anio is None:
        anio_predeterminado = _mes_anterior(hoy)[0].year
    anio_elegido = _resolver_anio(
        anio,
        anios_disponibles,
        predeterminado=anio_predeterminado,
    )
    inicio, fin, periodo_label = _resolver_periodo(
        corte_normalizado,
        anio_elegido,
        hoy,
    )

    solicitudes = SolicitudGasto.objects.all()
    pagos = PagoExterno.objects.all()
    if modalidad_normalizada is not None:
        solicitudes = solicitudes.filter(tipo_flujo=modalidad_normalizada)
        pagos = pagos.filter(solicitud__tipo_flujo=modalidad_normalizada)
    if centro_costo_id is not None:
        solicitudes = solicitudes.filter(centro_costo_id=centro_costo_id)
        pagos = pagos.filter(solicitud__centro_costo_id=centro_costo_id)

    solicitudes_periodo = solicitudes.filter(fecha_creacion__date__range=(inicio, fin))
    pagos_periodo = pagos.filter(fecha_pago__range=(inicio, fin))
    solicitudes_agg = _agregar_solicitudes(solicitudes_periodo)
    pagos_agg = _agregar_pagos(pagos_periodo)

    solicitudes_por_centro = {
        fila["centro_costo"]: fila
        for fila in solicitudes_periodo.values("centro_costo").annotate(
            cantidad=Count("id"),
            monto=Coalesce(Sum("monto_estimado"), CERO),
            cantidad_comprometida=Count(
                "id",
                filter=_condicion_compromiso(),
            ),
            monto_comprometido=Coalesce(
                Sum("monto_estimado", filter=_condicion_compromiso()),
                CERO,
            ),
        )
    }
    pagos_por_centro = {
        fila["solicitud__centro_costo"]: fila
        for fila in pagos_periodo.values("solicitud__centro_costo").annotate(
            cantidad=Count("id"),
            bruto=Coalesce(Sum("monto_bruto"), CERO),
            atp=Coalesce(Sum("monto_retencion_atp"), CERO),
            neto=Coalesce(Sum("importe"), CERO),
        )
    }

    centros_existentes = CentroCosto.objects.order_by("codigo", "nombre")
    if centro_costo_id is not None:
        centros_existentes = centros_existentes.filter(pk=centro_costo_id)
    fuentes_centro = [
        (
            centro,
            solicitudes_por_centro.get(centro.pk, {}),
            pagos_por_centro.get(centro.pk, {}),
        )
        for centro in centros_existentes
    ]
    if centro_costo_id is None:
        fuentes_centro.append(
            (
                None,
                solicitudes_por_centro.get(None, {}),
                pagos_por_centro.get(None, {}),
            )
        )

    centros_costo_dto: list[MetricasCentroCostoDTO] = []
    for centro, sol_data, pago_data in fuentes_centro:
        centros_costo_dto.append(
            MetricasCentroCostoDTO(
                centro_costo_id=centro.pk if centro else None,
                codigo=centro.codigo if centro else "-",
                nombre=(
                    centro.nombre
                    if centro
                    else "Sin centro de costo asignado / Histórico"
                ),
                activo=centro.activo if centro else True,
                cantidad_solicitudes=sol_data.get("cantidad", 0),
                monto_solicitado=sol_data.get("monto", CERO),
                cantidad_pagos=pago_data.get("cantidad", 0),
                monto_erogado_bruto=pago_data.get("bruto", CERO),
                monto_retencion_atp=pago_data.get("atp", CERO),
                monto_neto_transferido=pago_data.get("neto", CERO),
                cantidad_comprometida=sol_data.get("cantidad_comprometida", 0),
                monto_comprometido=sol_data.get("monto_comprometido", CERO),
            )
        )

    total_bruto = pagos_agg["bruto"]
    max_bruto_centro = max(
        (dto.monto_erogado_bruto for dto in centros_costo_dto),
        default=CERO,
    )
    max_atp_centro = max(
        (dto.monto_retencion_atp for dto in centros_costo_dto),
        default=CERO,
    )
    centros_costo_dto = [
        replace(
            dto,
            porcentaje_gasto=_porcentaje_participacion(
                dto.monto_erogado_bruto,
                total_bruto,
            ),
            porcentaje_bruto_grafico=_porcentaje_grafico(
                dto.monto_erogado_bruto,
                max_bruto_centro,
            ),
            porcentaje_atp_grafico=_porcentaje_grafico(
                dto.monto_retencion_atp,
                max_atp_centro,
            ),
        )
        for dto in centros_costo_dto
    ]

    rangos_cuatrimestres = (
        (
            1,
            "C1 (Enero – Abril)",
            date(anio_elegido, 1, 1),
            date(anio_elegido, 4, 30),
        ),
        (
            2,
            "C2 (Mayo – Agosto)",
            date(anio_elegido, 5, 1),
            date(anio_elegido, 8, 31),
        ),
        (
            3,
            "C3 (Septiembre – Diciembre)",
            date(anio_elegido, 9, 1),
            date(anio_elegido, 12, 31),
        ),
    )

    cuatrimestres_dto: list[MetricasCuatrimestreDTO] = []
    for numero, etiqueta, inicio_c, fin_c in rangos_cuatrimestres:
        solicitudes_cuatrimestre = solicitudes.filter(
            fecha_creacion__date__range=(inicio_c, fin_c)
        )
        pagos_cuatrimestre = pagos.filter(fecha_pago__range=(inicio_c, fin_c))
        solicitudes_c_agg = _agregar_solicitudes(solicitudes_cuatrimestre)
        pagos_c_agg = _agregar_pagos(pagos_cuatrimestre)
        cuatrimestres_dto.append(
            MetricasCuatrimestreDTO(
                cuatrimestre=numero,
                etiqueta=etiqueta,
                fecha_inicio=inicio_c,
                fecha_fin=fin_c,
                cantidad_solicitudes=solicitudes_c_agg["cantidad"] or 0,
                monto_solicitado=solicitudes_c_agg["monto"],
                cantidad_pagos=pagos_c_agg["cantidad"] or 0,
                monto_erogado_bruto=pagos_c_agg["bruto"],
                monto_retencion_atp=pagos_c_agg["atp"],
                monto_neto_transferido=pagos_c_agg["neto"],
            )
        )

    max_bruto_cuatrimestre = max(
        (dto.monto_erogado_bruto for dto in cuatrimestres_dto),
        default=CERO,
    )
    max_atp_cuatrimestre = max(
        (dto.monto_retencion_atp for dto in cuatrimestres_dto),
        default=CERO,
    )
    cuatrimestres_dto = [
        replace(
            dto,
            porcentaje_bruto_grafico=_porcentaje_grafico(
                dto.monto_erogado_bruto,
                max_bruto_cuatrimestre,
            ),
            porcentaje_atp_grafico=_porcentaje_grafico(
                dto.monto_retencion_atp,
                max_atp_cuatrimestre,
            ),
        )
        for dto in cuatrimestres_dto
    ]

    totales = TotalesReporteDTO(
        cantidad_solicitudes=solicitudes_agg["cantidad"] or 0,
        monto_solicitado=solicitudes_agg["monto"],
        cantidad_pagos=pagos_agg["cantidad"] or 0,
        monto_erogado_bruto=pagos_agg["bruto"],
        monto_retencion_atp=pagos_agg["atp"],
        monto_neto_transferido=pagos_agg["neto"],
        cantidad_comprometida=solicitudes_agg["cantidad_comprometida"] or 0,
        monto_comprometido=solicitudes_agg["monto_comprometido"],
        porcentaje_gasto=_porcentaje_participacion(
            pagos_agg["bruto"],
            pagos_agg["bruto"],
        ),
        cantidad_pagos_atp=pagos_agg["cantidad_atp"] or 0,
    )

    return ReporteCuatrimestralDTO(
        anio=anio_elegido,
        anios_disponibles=anios_disponibles,
        cuatrimestres=tuple(cuatrimestres_dto),
        centros_costo=tuple(centros_costo_dto),
        totales=totales,
        corte=corte_normalizado,
        modalidad=modalidad_normalizada or "",
        periodo_label=periodo_label,
    )
