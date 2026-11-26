"""Pruebas UX/UI de Reportes Directivos (Incremento 9B · Bloque 1)."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from gastos.models import EstadoSolicitud, PagoExterno, SolicitudGasto
from tests.soporte_gastos import crear_gasto_sintetico

pytestmark = pytest.mark.django_db(transaction=True)


def test_reporte_gastos_sin_salto_de_url_tabs_segmentadas_y_eje_y(escenario):
    """Desde /gestion/reportes/gastos/ el formulario conserva request.path, sin botón duplicado."""
    solicitante = escenario.usuarios["a"]
    solicitud = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Compra reporte 9B",
        monto_estimado=Decimal("120000.00"),
        estado=EstadoSolicitud.ACEPTADA,
    )
    SolicitudGasto.objects.filter(pk=solicitud.pk).update(
        fecha_creacion=datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    )
    PagoExterno.objects.create(
        solicitud=solicitud,
        importe=Decimal("115800.00"),
        moneda="ARS",
        fecha_pago=date(2026, 3, 15),
        referencia_externa="TRF-9B-01",
        referencia_documental="doc-9b-01",
        huella_idempotencia="huella-9b-01",
        monto_bruto=Decimal("120000.00"),
        monto_retencion_atp=Decimal("4200.00"),
        referencia_atp="ATP-9B-01",
    )

    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url_gestion = reverse("gestion:reporte_gastos")
    resp = cliente.get(url_gestion, {"anio": 2026})
    assert resp.status_code == 200
    html = resp.content.decode()

    assert f'action="{url_gestion}"' in html
    assert f'href="{url_gestion}" class="btn ghost" id="btnResetFiltros"' in html
    assert 'class="ui-tabs-segmented"' in html
    assert html.index('<h1 class="rep-title"') < html.index('class="gestion-tabs"')
    assert "Reporte directivo de gastos" in html
    assert "Reporte Directivo de Gastos" not in html
    assert "Ir al listado de gastos" not in html
    # Eje Y del gráfico vertical poblado desde el servidor (sin JS)
    assert "<span>$ 120.000,00</span>" in html
    assert "<span>$ 60.000,00</span>" in html
    assert "<span>$ 0,00</span>" in html
    # Proporción real de ATP (4200 / 120000 = 3.50 %) sobre el bruto del cuatrimestre
    assert "height: 3.50%;" in html
    assert "height: calc(100% - 3.50%);" in html
    # Sin colores inline de arcoíris en KPIs ni tabla; negrita conservada en Bruto Pagado
    assert 'style="color:var(--blue)' not in html
    assert 'style="color:var(--warn)' not in html
    assert 'style="color:var(--ok)' not in html
    assert "rep-col-bruto" in html
    assert "cc-cell-val" in html
    assert "rep-money" in html
    assert "TOTAL DEL PERÍODO" in html

    # La ruta directa /gastos/reportes/cuatrimestral/ también conserva su propio request.path
    url_directa = reverse("gastos:reporte_cuatrimestral")
    html_directo = cliente.get(url_directa, {"anio": 2026}).content.decode()
    assert f'action="{url_directa}"' in html_directo


def test_reporte_facturacion_usa_tabs_segmentadas_ars_y_font_tabular(escenario, datos):
    from facturacion.workflow import emitir_token, presentar_solicitud_facturacion

    s = presentar_solicitud_facturacion(
        actor=escenario.actores["a"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url = reverse("gestion:reporte_facturacion")
    resp = cliente.get(url, {"anio": s.fecha_presentacion.year})
    assert resp.status_code == 200
    html = resp.content.decode()

    assert 'class="gestion-tabs"' in html
    assert 'class="ui-tabs-segmented"' in html
    assert html.index('<h1 class="rep-title">') < html.index('class="gestion-tabs"')
    assert 'class="fac-chevron"' in html
    assert "Reporte de facturación · PS Cooperadora" in html
    assert "Reporte de Facturación" not in html
    assert "$ 100,25" in html
    assert 'class="num font-tabular"' in html


def test_css_reportes_encapsulado_sin_fugas_ni_legacy():
    for rel in ("css/reporte_cuatrimestral.css", "gestion/reporte_facturacion.css"):
        ruta = Path(settings.BASE_DIR) / "static" / rel
        contenido = re.sub(r"/\*.*?\*/", "", ruta.read_text(encoding="utf-8"), flags=re.S)
        assert ":root" not in contenido, rel
        assert "!important" not in contenido, rel
        assert "Montserrat" not in contenido, rel
        assert "#090979" not in contenido, rel
        assert "#084298" not in contenido, rel
        assert "--ref-" not in contenido, rel
        assert "@media print" in contenido, rel
