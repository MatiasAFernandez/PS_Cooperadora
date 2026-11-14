"""Resumen de cohortes de solicitudes; importes monetarios siempre separados."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from django.db.models import OuterRef, Prefetch, Subquery
from django.utils import timezone
from django.utils.dates import MONTHS

from facturacion.models import ComprobanteExterno, EventoFacturacion, SolicitudFacturacion
from facturacion.models_cobros import CobroExterno
from facturacion.seguimiento import importes_cobro

CERO = Decimal("0.00")
CENTAVO = Decimal("0.01")


def _fila_importes():
    return dict(cantidad=0, solicitado=CERO, neto=CERO)


def _registrar_pendiente(fila, desde):
    fila["cantidad"] += 1
    if desde and (fila["desde"] is None or desde < fila["desde"]):
        fila["desde"] = desde


def _escala_barras(filas, claves):
    """Posiciones en porcentaje con un cero común, incluso con netos negativos."""
    valores = [fila[clave] for fila in filas for clave in claves]
    minimo = min(0, min(valores, default=0))
    maximo = max(0, max(valores, default=0))
    amplitud = Decimal(maximo - minimo) or Decimal(1)

    def posicion(valor):
        return (Decimal(valor - minimo) * 100 / amplitud).quantize(CENTAVO)

    cero = posicion(0)
    barras = []
    for fila in filas:
        grupo = []
        for clave in claves:
            valor = fila[clave]
            extremo = posicion(valor)
            grupo.append(dict(valor=valor, inicio=min(cero, extremo), largo=abs(extremo - cero)))
        barras.append(grupo)
    return dict(cero=cero, minimo=minimo, maximo=maximo), barras


def _grafico(filas, series):
    escala, barras = _escala_barras(filas, [clave for clave, _, _ in series])
    return dict(
        **escala,
        series=series,
        grupos=[
            dict(nombre=fila["nombre"], barras=[
                dict(barra, color=serie[2], etiqueta=serie[1])
                for barra, serie in zip(grupo, series, strict=True)
            ])
            for fila, grupo in zip(filas, barras, strict=True)
        ],
    )


def _ranking(filas, orden):
    primeras = filas[:5]
    escala, barras = _escala_barras(primeras, [orden])
    return dict(
        cero=escala["cero"],
        filas=[
            dict(barra[0], nombre=fila["nombre"])
            for fila, barra in zip(primeras, barras, strict=True)
        ],
    )


def reporte_facturacion(anio, cuatrimestre=None, orden="cantidad", *, trimestre=None):
    meses = 3 if trimestre else 4 if cuatrimestre else 12
    mes = ((trimestre or cuatrimestre or 1) - 1) * meses + 1
    hasta_mes = mes + meses
    inicio = date(anio, mes, 1)
    fin = date(anio + 1, 1, 1) if hasta_mes == 13 else date(anio, hasta_mes, 1)
    observacion = EventoFacturacion.objects.filter(
        solicitud_id=OuterRef("pk"), tipo_evento="OBSERVACION"
    ).order_by("-fecha_hora", "-pk")
    solicitudes = (
        SolicitudFacturacion.objects.operativas()
        .filter(
            fecha_presentacion__date__gte=inicio,
            fecha_presentacion__date__lt=fin,
        )
        .annotate(fecha_observacion=Subquery(observacion.values("fecha_hora")[:1]))
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
    total = dict(
        inicio=inicio,
        fin=fin - timedelta(days=1),
        cantidad=0,
        anuladas=0,
        solicitado=CERO,
        neto=CERO,
        confirmado=CERO,
        facturas=0,
        suma_facturas=CERO,
        saldo_por_confirmar=CERO,
        excedente_confirmado=CERO,
        tramites_con_saldo=0,
        tramites_con_excedente=0,
    )
    grupos = {clave: defaultdict(_fila_importes) for clave in ("centros", "correos")}
    mensual = bool(cuatrimestre or trimestre)
    etiquetas = (
        {m: str(MONTHS[m]).capitalize()[:3] for m in range(mes, hasta_mes)}
        if mensual else {c: f"{c}° Cuatr." for c in range(1, 4)}
    )
    periodos = {
        clave: dict(_fila_importes(), nombre=etiqueta, facturas=0, confirmado=CERO)
        for clave, etiqueta in etiquetas.items()
    }
    pendientes = {
        "facturar": dict(nombre="Solicitudes por facturar", estado="PRESENTADA", color="azul"),
        "verificar": dict(nombre="Cobros por verificar", estado="", color="ambar"),
        "subsanar": dict(nombre="Observaciones por subsanar", estado="OBSERVADA", color="azul"),
    }
    for fila in pendientes.values():
        fila.update(cantidad=0, desde=None)
    importes_facturas = []
    for solicitud in solicitudes:
        if solicitud.estado == "ANULADA":
            total["anuladas"] += 1
            continue
        total["cantidad"] += 1
        total["solicitado"] += solicitud.importe_factura
        comprobantes = list(solicitud.comprobantes.all())
        cobros = list(solicitud.cobros.all())
        importes = importes_cobro(comprobantes, cobros)
        neto, confirmado = importes["neto"], importes["confirmado"]
        facturas = [c.importe for c in comprobantes if c.tipo == "FACTURA"]
        importes_facturas.extend(facturas)
        total["facturas"] += len(facturas)
        total["suma_facturas"] += sum(facturas, CERO)
        total["neto"] += neto
        total["confirmado"] += confirmado
        fecha = timezone.localtime(solicitud.fecha_presentacion)
        periodo = periodos[fecha.month if mensual else (fecha.month - 1) // 4 + 1]
        periodo["facturas"] += len(facturas)
        periodo["confirmado"] += confirmado
        filas = [
            grupos["centros"][solicitud.centro_costo or "Sin centro asignado"],
            grupos["correos"][solicitud.correo_solicitante],
            periodo,
        ]
        for fila in filas:
            fila["cantidad"] += 1
            fila["solicitado"] += solicitud.importe_factura
            fila["neto"] += neto
        if solicitud.estado == "CERRADA":
            continue
        if solicitud.estado == "OBSERVADA":
            _registrar_pendiente(pendientes["subsanar"], solicitud.fecha_observacion)
        elif not facturas:
            _registrar_pendiente(pendientes["facturar"], solicitud.fecha_presentacion)
        for cobro in cobros:
            if cobro.resultado == "PENDIENTE":
                _registrar_pendiente(pendientes["verificar"], cobro.fecha_registro)
        if facturas:
            saldo = importes["restante"]
            exceso = max(confirmado - max(neto, CERO), CERO)
            total["saldo_por_confirmar"] += saldo
            total["excedente_confirmado"] += exceso
            total["tramites_con_saldo"] += saldo > 0
            total["tramites_con_excedente"] += exceso > 0
    for destino, numerador, denominador in (
        ("promedio_solicitud", "solicitado", "cantidad"),
        ("promedio_factura", "suma_facturas", "facturas"),
    ):
        total[destino] = (
            (total[numerador] / total[denominador]).quantize(
                CENTAVO, rounding=ROUND_HALF_UP
            )
            if total[denominador]
            else CERO
        )
    total["mediana_factura"] = (
        median(importes_facturas).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if importes_facturas else None
    )
    for grupo, filas in grupos.items():
        total[grupo] = sorted(
            (
                dict(nombre=etiquetas_centros.get(k, k) if grupo == "centros" else k, **v)
                for k, v in filas.items()
            ),
            key=lambda f: (-f[orden], f["nombre"]),
        )
    total["periodos"] = list(periodos.values())
    total["volumen"] = _grafico(total["periodos"], [
        ("cantidad", "Solicitudes", "azul"),
        ("facturas", "Facturas vinculadas", "celeste"),
    ])
    total["importes"] = _grafico(total["periodos"], [
        ("solicitado", "Solicitado", "celeste"),
        ("neto", "Facturado neto", "azul"),
        ("confirmado", "Cobrado confirmado", "verde"),
    ])
    total["ranking_centros"] = _ranking(total["centros"], orden)
    total["ranking_correos"] = _ranking(total["correos"], orden)
    maximo = max(fila["cantidad"] for fila in pendientes.values()) or 1
    hoy = timezone.localdate()
    for fila in pendientes.values():
        fila["largo"] = fila["cantidad"] * 100 // maximo
        desde = fila["desde"]
        fila["dias"] = max(0, (hoy - timezone.localdate(desde)).days) if desde else None
    total["pendientes_operador"] = [pendientes["facturar"], pendientes["verificar"]]
    total["pendientes_solicitante"] = [pendientes["subsanar"]]
    return total
