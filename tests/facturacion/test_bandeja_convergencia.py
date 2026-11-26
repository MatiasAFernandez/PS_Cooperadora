"""Regresión de Incremento 7: convergencia de /facturacion/ con el sistema visual."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import Client
from django.urls import reverse

from facturacion.forms import FiltroFacturacionForm
from facturacion.workflow import (
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _presentar(escenario, datos, actor="a", **cambios):
    return presentar_solicitud_facturacion(
        actor=escenario.actores[actor],
        datos=dict(datos, **cambios),
        token_presentacion=emitir_token(escenario.actores[actor]),
    )


def _observar(escenario, solicitud):
    return observar_solicitud_facturacion(
        actor=escenario.actores["o"],
        numero_publico=solicitud.pk,
        motivo="Precisá el concepto",
        version_esperada=solicitud.version_concurrencia,
    )


def test_tabs_y_contadores_por_rol(escenario, datos):
    for _ in range(4):
        _presentar(escenario, datos)
    for _ in range(3):
        obs = _presentar(escenario, datos)
        _observar(escenario, obs)

    lista_url = reverse("facturacion:lista")

    # Operadora ve Todas (sin contador A2) y Requieren atención (4 sin recorte a 3)
    op = Client()
    op.force_login(escenario.usuarios["o"])
    html_op = op.get(lista_url).content.decode()
    assert ">Todas</a>" in html_op
    assert 'data-bandeja-tab="atencion"' in html_op
    assert '<span class="bandeja-tab-count bandeja-tab-count--attn">4</span>' in html_op

    html_op_atn = op.get(lista_url, {"atencion": "1"}).content.decode()
    assert html_op_atn.count('data-resumen="') == 4
    assert "maxHeight" not in html_op
    assert "Constatar Ingreso" not in html_op_atn
    assert "Ver Detalle" not in html_op_atn

    # Solicitante ve las 3 observadas sin recorte a 2
    sol = Client()
    sol.force_login(escenario.usuarios["a"])
    html_sol = sol.get(lista_url).content.decode()
    assert ">Todas</a>" in html_sol
    assert '<span class="bandeja-tab-count bandeja-tab-count--attn">3</span>' in html_sol
    html_sol_atn = sol.get(lista_url, {"atencion": "1"}).content.decode()
    assert html_sol_atn.count('data-resumen="') == 3
    assert "Corregir solicitud" in html_sol_atn

    # Lectura no ve pestañas e ignora ?atencion=1
    lec = Client()
    lec.force_login(escenario.usuarios["l"])
    resp_lec = lec.get(lista_url, {"atencion": "1"})
    html_lec = resp_lec.content.decode()
    assert resp_lec.context["ofrece_atencion"] is False
    assert resp_lec.context["solo_atencion"] is False
    assert "data-bandeja-tabs" not in html_lec
    assert html_lec.count('data-resumen="') == 7
    assert "Ver detalle" in html_lec


def test_aviso_proximidad_cierre_solo_para_solicitante(escenario, datos, monkeypatch):
    from facturacion.models import SolicitudFacturacion

    s = _presentar(escenario, datos, nombre_receptor="Receptor Cierre S.A.")
    _observar(escenario, s)
    # 1° del mes frente a día 26 => aplica proximidad_cierre
    SolicitudFacturacion.objects.filter(pk=s.pk).update(
        fecha_presentacion=datetime(2026, 11, 1, 12, tzinfo=UTC)
    )
    monkeypatch.setattr("facturacion.atencion.proximidad_cierre", lambda sol, hoy=None: True)

    sol = Client()
    sol.force_login(escenario.usuarios["a"])
    html_sol = sol.get(reverse("facturacion:lista"), {"atencion": "1"}).content.decode()
    assert "Se aproxima el cierre de mes: completá la acción pendiente." in html_sol

    # Operadora en un trámite pendiente propio nunca ve aviso de cierre de mes en su bandeja
    _presentar(escenario, datos, actor="b", nombre_receptor="Otro Receptor")
    op = Client()
    op.force_login(escenario.usuarios["o"])
    html_op = op.get(reverse("facturacion:lista"), {"atencion": "1"}).content.decode()
    assert "Se aproxima el cierre de mes" not in html_op


def test_preservacion_filtros_entre_tabs_quitar_y_bandeja_retorno(escenario, datos):
    s = _presentar(
        escenario,
        datos,
        nombre_solicitante="Ing. Laura Gómez",
        email_envio_factura="facturas.litoral@example.invalid",
        nombre_receptor="Metalúrgica Litoral S.A.",
        importe_factura="195000.00",
    )
    observada = _presentar(escenario, datos, nombre_receptor="Observada Litoral")
    _observar(escenario, observada)

    op = Client()
    op.force_login(escenario.usuarios["o"])
    lista_url = reverse("facturacion:lista")

    # Busca en Todas con estado OBSERVADA (incompatible con atención de Operadora) y page=2
    resp = op.get(lista_url, {"q": "Litoral", "estado": "OBSERVADA", "page": "2"})
    assert resp.status_code == 200
    assert resp.context["tiene_filtros_activos"] is True
    assert resp.context["limpiar_filtros_url"] == lista_url

    parsed_atn = urlparse(resp.context["url_tab_atencion"])
    qs_atn = parse_qs(parsed_atn.query)
    assert qs_atn.get("atencion") == ["1"]
    assert qs_atn.get("q") == ["Litoral"]
    assert "estado" not in qs_atn
    assert "page" not in qs_atn

    # En Requieren atención con filtro compatible, Quitar filtros limpia dentro de atención
    resp_atn = op.get(lista_url, {"atencion": "1", "q": "Litoral", "estado": "PRESENTADA"})
    assert resp_atn.context["limpiar_filtros_url"] == f"{lista_url}?atencion=1"
    parsed_todas = urlparse(resp_atn.context["url_tab_todas"])
    qs_todas = parse_qs(parsed_todas.query)
    assert "atencion" not in qs_todas
    assert qs_todas.get("q") == ["Litoral"]
    assert qs_todas.get("estado") == ["PRESENTADA"]

    # Tabla distingue solicitante vs email de envío, formato ARS y enlace ?bandeja=
    html = resp_atn.content.decode()
    assert "Ing. Laura Gómez" in html
    assert 'title="facturas.litoral@example.invalid"' in html
    assert "Envío: facturas.litoral@example.invalid" in html
    assert "$ 195.000,00" in html
    fila = html.split(f'<tr data-resumen="{s.pk}">', 1)[1].split("</tr>", 1)[0]
    assert 'data-abrir-resumen="' in fila
    assert "<tr data-resumen=" in html and 'tabindex="0"' not in fila
    assert "bandeja=" in html

    # Detalle preserva ?bandeja= en Volver a solicitudes
    retorno = "atencion=1&q=Litoral"
    det_html = op.get(
        reverse("facturacion:detalle", args=[s.pk]), {"bandeja": retorno}
    ).content.decode()
    assert f'href="{lista_url}?atencion=1&amp;q=Litoral"' in det_html


def test_orden_campos_filtro_y_busqueda_con_numeral(escenario, datos):
    assert list(FiltroFacturacionForm().fields) == [
        "q",
        "estado",
        "periodo",
        "dia",
        "mes",
        "anio",
    ]
    s = _presentar(escenario, datos)
    op = Client()
    op.force_login(escenario.usuarios["o"])
    resp = op.get(reverse("facturacion:lista"), {"q": f"#{s.pk}"})
    assert [item.pk for item in resp.context["pagina"]] == [s.pk]
