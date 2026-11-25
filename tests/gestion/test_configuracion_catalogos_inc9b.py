"""Pruebas UX/UI y flujo de Configuración y Catálogos (Incremento 9B · Bloque 2)."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from gastos.models import CentroCosto
from gastos.services import obtener_alicuota_atp, obtener_base_imponible_atp

pytestmark = pytest.mark.django_db(transaction=True)


def test_configuracion_gasto_badges_tabs_atp_y_details_cerrado_por_defecto(administrador):
    CentroCosto.objects.create(codigo="lab-01", nombre="Laboratorio 01", activo=True)
    cliente = Client()
    cliente.force_login(administrador.user)
    url = reverse("gestion:configuracion", args=["GASTO"])
    resp = cliente.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()

    assert 'class="ui-tabs-segmented"' in html
    # Badges migrados a status-pill (sin badge crudo invisible)
    assert '<span class="badge">' not in html
    assert "status-pill status-info" in html
    assert "status-pill status-success" in html
    assert "Esencial · protegido" in html
    # <details> de Catálogos cerrado por defecto al entrar sin query ni error
    assert '<details class="card gestion-card gestion-catalogos-details">' in html
    assert '<details class="card gestion-card gestion-catalogos-details" open>' not in html
    # Copy de alícuota ATP sin contradicción (referencia manual, nunca automático)
    assert "Alícuota de referencia ATP (%)" in html
    assert "se carga manualmente" in html
    assert "aplicado por defecto" not in html
    # Encabezado Acciones alineado a la derecha
    assert 'class="catalog-th-actions"' in html


def test_catalogos_desde_configuracion_guarda_con_seccion_y_reabre_details(administrador):
    cliente = Client()
    cliente.force_login(administrador.user)
    url_config = reverse("gestion:configuracion", args=["GASTO"])
    url_esperada = f"{url_config}?seccion=catalogos"
    url_catalogos = reverse("gastos:gestion_catalogos")

    # 1. Crear centro desde Configuración -> redirige a ?seccion=catalogos y abre <details>
    resp = cliente.post(
        url_catalogos,
        {
            "action": "crear_centro",
            "next": url_esperada,
            "codigo": "lab-inc9b",
            "nombre": "Laboratorio Inc 9B",
            "activo": "on",
        },
    )
    assert resp.status_code == 302
    assert resp.url == url_esperada
    html_tras_guardar = cliente.get(resp.url).content.decode()
    assert '<details class="card gestion-card gestion-catalogos-details" open>' in html_tras_guardar
    assert "Laboratorio Inc 9B" in html_tras_guardar
    assert "flash-messages" in html_tras_guardar

    # 2. Toggle activo desde Configuración -> vuelve a ?seccion=catalogos
    centro = CentroCosto.objects.get(codigo="lab-inc9b")
    resp_toggle = cliente.post(
        reverse("gastos:centro_costo_toggle", kwargs={"pk": centro.pk}),
        {"next": url_esperada},
    )
    assert resp_toggle.status_code == 302
    assert resp_toggle.url == url_esperada
    centro.refresh_from_db()
    assert centro.activo is False

    # 3. Actualizar ATP desde Configuración -> vuelve a ?seccion=catalogos
    resp_atp = cliente.post(
        url_catalogos,
        {
            "action": "actualizar_atp",
            "next": url_esperada,
            "base_imponible_atp": "125000.00",
            "alicuota_atp": "3.75",
        },
    )
    assert resp_atp.status_code == 302
    assert resp_atp.url == url_esperada
    assert obtener_base_imponible_atp() == Decimal("125000.00")
    assert obtener_alicuota_atp() == Decimal("3.75")


def test_catalogos_post_invalido_desde_configuracion_rerenderiza_configuracion_400(administrador):
    cliente = Client()
    cliente.force_login(administrador.user)
    url_config = reverse("gestion:configuracion", args=["GASTO"])
    url_next = f"{url_config}?seccion=catalogos"
    url_catalogos = reverse("gastos:gestion_catalogos")

    resp = cliente.post(
        url_catalogos,
        {
            "action": "actualizar_atp",
            "next": url_next,
            "base_imponible_atp": "-50",
            "alicuota_atp": "150",
        },
    )
    assert resp.status_code == 400
    html = resp.content.decode()
    assert '<details class="card gestion-card gestion-catalogos-details" open>' in html
    assert "Formulario de gastos" in html
    assert "errorlist" in html

    # Un next externo malicioso se descarta y cae al listado directo de catálogos
    resp_externo = cliente.post(
        url_catalogos,
        {
            "action": "actualizar_atp",
            "next": "https://externo.invalid/robar",
            "base_imponible_atp": "95000.00",
            "alicuota_atp": "3.50",
        },
    )
    assert resp_externo.status_code == 302
    assert resp_externo.url == url_catalogos


def test_campo_y_catalogos_directo_incluyen_page_back_y_sin_boton_duplicado(
    escenario, administrador
):
    cliente = Client()
    cliente.force_login(administrador.user)

    html_campo = cliente.get(reverse("gestion:campo_nuevo", args=["GASTO"])).content.decode()
    assert 'class="page-back page-back--arrow"' in html_campo
    assert "(Opcional)" in html_campo

    html_fact = cliente.get(
        reverse("gestion:configuracion", args=["FACTURACION"])
    ).content.decode()
    assert 'class="ui-tabs-segmented"' in html_fact
    assert "Formulario de facturación" in html_fact

    cliente.force_login(escenario.usuarios["o"])
    html_cat = cliente.get(reverse("gastos:gestion_catalogos")).content.decode()
    assert "Ir al listado de gastos" not in html_cat
    # Operadora sin gestion.configurar no ve pestañas vacías
    assert 'class="gestion-tabs"' not in html_cat


def test_css_gestion_y_catalogos_limpios_sin_legacy_ni_important():
    for rel in ("gestion/gestion.css", "gastos/css/gestion_catalogos.css"):
        ruta = Path(settings.BASE_DIR) / "static" / rel
        contenido = re.sub(r"/\*.*?\*/", "", ruta.read_text(encoding="utf-8"), flags=re.S)
        assert ":root" not in contenido, rel
        assert "!important" not in contenido, rel
        assert "--ref-" not in contenido, rel
        assert "#090979" not in contenido, rel
        assert "#084298" not in contenido, rel
        assert "Montserrat" not in contenido, rel
