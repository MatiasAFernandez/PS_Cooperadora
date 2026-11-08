"""Pruebas end-to-end en navegador aislado para los ajustes de UX de pago documentado #15."""

from typing import Any

import pytest
from django.test.client import Client
from django.urls import reverse
from playwright.sync_api import sync_playwright

from gastos.contracts import OpcionDocumental
from gastos.models import EstadoSolicitud
from tests.soporte_pagos import pdf_comprobante

CAPS_PAGO_UI = (
    "gastos.consultar_todas",
    "gastos.registrar_pago",
    "documentos.ver_metadatos",
    "documentos.consultar_metadatos",
    "documentos.incorporar",
)


@pytest.fixture
def actor_pago(actor_factory: Any, monkeypatch: Any) -> Any:
    user, actor = actor_factory(CAPS_PAGO_UI)
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    return user, actor


@pytest.fixture
def opcion_pago() -> OpcionDocumental:
    return OpcionDocumental(
        referencia_documental="doc-opaco-1",
        tipo_documento="factura",
        etiqueta="Factura B 0001-00000123 (Vigente)",
    )


@pytest.mark.django_db(transaction=True)
def test_recorrido_1_detalle_y_alta_sin_respaldo(
    live_server: Any,
    solicitud_factory: Any,
    actor_pago: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """Recorrido 1: Detalle y alta sin opciones documentales vigentes."""
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(opciones=[])
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    client = Client()
    client.force_login(user)
    session_cookie = client.cookies["sessionid"]

    host = live_server.url.split("://")[1].split(":")[0]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        context.add_cookies([
            {
                "name": "sessionid",
                "value": session_cookie.value,
                "domain": host,
                "path": "/",
            }
        ])
        page = context.new_page()

        # 1. Visitar detalle
        page.goto(f"{live_server.url}{reverse('gastos:detalle', kwargs={'pk': solicitud.pk})}")
        page.wait_for_load_state("domcontentloaded")

        # Verificar aviso junto al acceso en tarjeta Pago externo
        pago_section = page.locator("#pago-externo")
        assert pago_section.locator("text=Sin respaldo comercial elegible").is_visible()
        btn_pagar = pago_section.locator("a:has-text('Registrar pago externo')")
        assert btn_pagar.is_visible()

        # Verificar enlace unificado a documentos con estilo azul
        link_doc = page.locator("a:has-text('Cargar o reemplazar respaldo comercial')")
        assert link_doc.is_visible()
        assert "btn" in (link_doc.get_attribute("class") or "")

        # 2. Navegar a alta de pago
        btn_pagar.click()
        page.wait_for_load_state("domcontentloaded")

        # Verificar resumen lateral con fila Respaldo comercial y chip ámbar Falta cargar
        sum_respaldo = page.locator("#rp-sum-respaldo")
        assert sum_respaldo.is_visible()
        assert "Falta cargar" in sum_respaldo.inner_text()

        # Verificar select vacío y label ocultos
        assert not page.locator("select[name='referencia_documental']").is_visible()
        assert not page.locator("label[for='id_referencia_documental']").is_visible()

        # Verificar aviso arriba del submit deshabilitado
        aviso_faltante = page.locator("#rp-aviso-respaldo-faltante")
        assert aviso_faltante.is_visible()
        assert "Se necesita un respaldo comercial vigente" in aviso_faltante.inner_text()

        # Botón submit deshabilitado
        submit_btn = page.locator("button[type='submit']:has-text('Registrar pago externo')")
        assert submit_btn.is_disabled()

        # CTA unificado a documentos con estilo azul
        cta_doc = page.locator(
            ".rp-section:has-text('Respaldo comercial') "
            "a:has-text('Cargar o reemplazar respaldo comercial')"
        )
        assert cta_doc.is_visible()
        assert "btn" in (cta_doc.get_attribute("class") or "")

        browser.close()


@pytest.mark.django_db(transaction=True)
def test_recorrido_2_alta_interactiva_novalidate_y_correcciones(
    live_server: Any,
    solicitud_factory: Any,
    actor_pago: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
    tmp_path: Any,
) -> None:
    """Recorrido 2: Alta interactiva con novalidate, errores en tarjeta, foco y corrección."""
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(opciones=[opcion_pago])
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    client = Client()
    client.force_login(user)
    session_cookie = client.cookies["sessionid"]

    host = live_server.url.split("://")[1].split(":")[0]

    # Archivo PDF temporal sintético
    pdf_path = tmp_path / "comprobante_bancario.pdf"
    pdf_path.write_bytes(pdf_comprobante().read())

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        context.add_cookies([
            {
                "name": "sessionid",
                "value": session_cookie.value,
                "domain": host,
                "path": "/",
            }
        ])
        page = context.new_page()

        page.goto(f"{live_server.url}{reverse('gastos:pagar', kwargs={'pk': solicitud.pk})}")
        page.wait_for_load_state("domcontentloaded")

        # 1. Verificar select visible y resumen lateral reflejando la opción
        select_doc = page.locator("select[name='referencia_documental']")
        assert select_doc.is_visible()
        sum_respaldo = page.locator("#rp-sum-respaldo")
        assert sum_respaldo.is_visible()
        assert opcion_pago.etiqueta in sum_respaldo.inner_text()

        # Completar fecha para aislar el error de comprobante bancario
        page.click("#btn-fecha-hoy")

        # 2. Submit inválido: sin comprobante bancario
        submit_btn = page.locator("button[type='submit']:has-text('Registrar pago externo')")
        submit_btn.click()

        # Verificar error visible en tarjeta vía setEstadoDocumento
        banco_status = page.locator("#rp-banco-status")
        assert banco_status.is_visible()
        assert "rp-error" in (banco_status.get_attribute("class") or "")
        assert "Seleccioná el comprobante bancario" in banco_status.inner_text()

        # Verificar aviso junto al botón submit
        submit_notice = page.locator("#rp-submit-error-notice")
        assert submit_notice.is_visible()
        assert "Seleccioná el comprobante bancario" in submit_notice.inner_text()

        # Verificar que el foco está en el botón/label accesible, no en el input oculto
        focused_tag = page.evaluate(
            "() => document.activeElement ? document.activeElement.tagName.toLowerCase() : ''"
        )
        focused_id = page.evaluate(
            "() => document.activeElement ? document.activeElement.id : ''"
        )
        assert focused_tag in ("label", "button")
        assert focused_id == "rp-banco-label"

        # 3. Corregir archivo bancario sin otro submit
        file_input = page.locator("#id_comprobante_bancario")
        file_input.set_input_files(str(pdf_path))
        page.wait_for_timeout(300)

        # El estado de error de la tarjeta debe haberse limpiado
        assert not banco_status.is_visible()

        # El aviso junto al botón submit debe haberse ocultado sin otro submit
        assert not submit_notice.is_visible()

        browser.close()
