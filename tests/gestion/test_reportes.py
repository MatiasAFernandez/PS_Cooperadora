from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from facturacion.workflow import (
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)
from gestion.reportes import reporte_facturacion
from tests.facturacion.test_cierre import cobro, factura

pytestmark = pytest.mark.django_db(transaction=True)


def test_periodos_separan_limites_locales_y_conservan_centavos(escenario, datos):
    # 01/04 01:30 UTC todavía es 31/03 en Buenos Aires.
    fechas = [
        "2025-12-31T12:00:00-03:00",
        "2026-04-01T01:30:00+00:00",
        "2026-04-01T12:00:00-03:00",
        "2026-04-30T12:00:00-03:00",
        "2026-05-01T12:00:00-03:00",
        "2026-12-31T23:59:59-03:00",
        "2027-01-01T00:00:00-03:00",
    ]
    for fecha in fechas:
        with patch("facturacion.workflow.timezone.now", return_value=datetime.fromisoformat(fecha)):
            presentar_solicitud_facturacion(
                actor=escenario.actores["a"],
                datos=datos,
                token_presentacion=emitir_token(escenario.actores["a"]),
            )
    for trimestre, cantidad in enumerate([1, 3, 0, 1], start=1):
        reporte = reporte_facturacion(2026, trimestre=trimestre)
        assert reporte["cantidad"] == cantidad
        assert reporte["solicitado"] == Decimal("100.25") * cantidad
    for cuatrimestre, cantidad in enumerate([3, 1, 1], start=1):
        assert reporte_facturacion(2026, cuatrimestre)["cantidad"] == cantidad
    anual = reporte_facturacion(2026)
    assert anual["cantidad"] == 5
    assert [fila["cantidad"] for fila in anual["periodos"]] == [3, 1, 1]
    segundo = reporte_facturacion(2026, trimestre=2)
    assert [fila["cantidad"] for fila in segundo["periodos"]] == [2, 1, 0]
    assert anual["inicio"] == date(2026, 1, 1)
    assert anual["fin"] == date(2026, 12, 31)
    assert reporte_facturacion(2024, trimestre=1)["fin"] == date(2024, 3, 31)


def test_graficos_y_seguimiento_cuadran_con_los_tramites(escenario, datos):
    def presentar():
        actor = escenario.actores["a"]
        return presentar_solicitud_facturacion(
            actor=actor, datos=datos, token_presentacion=emitir_token(actor)
        )

    parcial, excedente, nota, sin_factura, observada = [presentar() for _ in range(5)]
    factura(escenario, parcial, numero=1)
    factura(escenario, excedente, numero=2, importe="60.10")
    factura(escenario, nota, numero=3, importe="10.00")
    factura(escenario, nota, tipo="NOTA_CREDITO", numero=4, importe="15.00")
    cobro(escenario, parcial, importe="40.10", operacion="SINTETICO-PARCIAL")
    cobro(escenario, parcial, importe="20.00", operacion="SINTETICO-PENDIENTE", confirmar=False)
    cobro(escenario, excedente, importe="65.10", operacion="SINTETICO-EXCEDENTE")
    cobro(escenario, nota, importe="1.00", operacion="SINTETICO-NETO-NEGATIVO")
    observar_solicitud_facturacion(
        actor=escenario.actores["o"], numero_publico=observada.pk,
        motivo="Observación sintética", version_esperada=observada.version_concurrencia,
    )
    cliente = Client()
    cliente.force_login(escenario.usuarios["l"])
    url = reverse("gestion:reporte_facturacion")
    anio = timezone.localdate(sin_factura.fecha_presentacion).year
    respuesta = cliente.get(url, {"anio": anio, "orden": "neto"})
    assert respuesta.status_code == 200
    reporte = respuesta.context["reporte"]
    assert reporte["facturas"] == 3
    assert reporte["neto"] == Decimal("155.35")
    assert reporte["confirmado"] == Decimal("106.20")
    assert reporte["promedio_factura"] == Decimal("56.78")
    assert reporte["mediana_factura"] == Decimal("60.10")
    assert reporte["saldo_por_confirmar"] == Decimal("60.15")
    assert reporte["tramites_con_saldo"] == 1
    assert reporte["excedente_confirmado"] == Decimal("6.00")
    assert reporte["tramites_con_excedente"] == 2
    assert [fila["cantidad"] for fila in reporte["pendientes_operador"]] == [1, 1]
    assert reporte["pendientes_solicitante"][0]["cantidad"] == 1
    assert reporte["pendientes_solicitante"][0]["dias"] == 0
    assert sum(fila["facturas"] for fila in reporte["periodos"]) == 3
    assert sum(fila["confirmado"] for fila in reporte["periodos"]) == Decimal("106.20")
    assert reporte["ranking_centros"]["filas"][0]["valor"] == Decimal("155.35")
    html = respuesta.content.decode()
    assert 'id="evolucion"' in html and 'id="demanda"' in html and 'id="seguimiento"' in html
    assert f"periodo=anio&amp;anio={anio}&amp;estado=PRESENTADA" in html
    assert "Ver cifras por período" in html
    cliente.force_login(escenario.usuarios["a"])
    assert cliente.get(url, {"anio": anio}).status_code == 403


def test_reporte_presenta_pestanas_filtros_y_limpieza(escenario):
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url = reverse("gestion:reporte_facturacion")
    respuesta = cliente.get(url, {"anio": 2024, "trimestre": 2, "orden": "neto"})
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert html.index('class="gestion-tabs"') < html.index('<h1 class="rep-title">')
    assert "Aplicar filtros" not in html
    assert "data-filtros-reporte" in html
    assert f'href="{url}" class="btn ghost">Limpiar filtros' in html
    assert 'name="trimestre" value="2"' in html
    assert 'name="cuatrimestre"' not in html
    assert '?anio=2024&amp;cuatrimestre=3&amp;orden=neto' in html
    assert '?anio=2024&amp;trimestre=4&amp;orden=neto' in html
    assert 'aria-current="page">2° Trim.' in html
    assert "01/04/2024 al 30/06/2024" in html
    limpio = cliente.get(url)
    assert limpio.context["anio"] == timezone.localdate().year
    assert limpio.context["orden"] == "cantidad"
    assert limpio.context["trimestre"] is None
    assert limpio.context["cuatrimestre"] is None


@pytest.mark.parametrize("filtros", [
    {"trimestre": "5"}, {"trimestre": "0"}, {"trimestre": "texto"},
    {"cuatrimestre": "4"}, {"cuatrimestre": "1", "trimestre": "1"},
    {"anio": "2101"}, {"orden": "desconocido"},
])
def test_reporte_rechaza_periodos_invalidos_y_permite_limpiar(escenario, filtros):
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    respuesta = cliente.get(reverse("gestion:reporte_facturacion"), filtros)
    assert respuesta.status_code == 400
    assert "Limpiar filtros" in respuesta.content.decode()
    assert "reporte" not in respuesta.context
