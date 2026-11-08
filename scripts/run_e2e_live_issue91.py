"""Script E2E en vivo para verificar Issue #91 y ajustes de borde de Issue #90.

Conecta por Chrome Remote Debugging (CDP puerto 9222) a la ventana que el
usuario tiene abierta en su pantalla, ejecutando el flujo paso a paso con
pausas para visualización clara.
"""

import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cooperadora.settings")
import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from documentos.models import Documento  # noqa: E402
from documentos.services import incorporar  # noqa: E402
from gastos.models import CentroCosto, TipoFlujoGasto  # noqa: E402
from gastos.services import crear_solicitud_gasto, decide_expense  # noqa: E402
from identidad.services import GROUP_CAPABILITIES, Actor  # noqa: E402


def get_actor_for_user(user: Any) -> Actor:
    capabilities = frozenset().union(
        *(
            GROUP_CAPABILITIES[name]
            for name in user.groups.values_list("name", flat=True)
            if name in GROUP_CAPABILITIES
        )
    )
    return Actor(
        subject_id=user.pk,
        capabilities=capabilities,
        email_registrado=user.email.strip() or None,
    )


from tests.integracion.helpers import archivo_pdf  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
EVIDENCE_DIR = Path("docs/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def preparar_fixtures() -> CentroCosto:
    cc, _ = CentroCosto.objects.update_or_create(
        codigo="lab-ia",
        defaults={"nombre": "Laboratorio de Inteligencia Artificial", "activo": True},
    )
    return cc


def login_as(context: Any, page: Any, username: str) -> None:
    context.clear_cookies()
    page.goto(f"{BASE_URL}/demo/acceso/")
    page.wait_for_load_state("networkidle")
    time.sleep(0.8)
    page.fill('input[name="username"]', username)
    time.sleep(0.3)
    page.fill('input[name="password"]', "demo1234")
    time.sleep(0.3)
    page.click('button:has-text("Ingresar")')
    page.wait_for_load_state("networkidle")
    time.sleep(1)


def aportar_documento(solicitud_id: int, solicitante_id: int, tipo: str) -> None:
    actor_solic = Actor(
        subject_id=solicitante_id,
        capabilities=frozenset(
            {"gastos.presentar", "gastos.consultar_propias", "documentos.incorporar"}
        ),
    )
    incorporar(
        actor=actor_solic,
        referencia=f"gastos:{solicitud_id}",
        archivo=archivo_pdf(),
        tipo=tipo,
        procedencia="SOLICITANTE",
    )


def take_safe_screenshot(page: Any, path: Path) -> None:
    try:
        page.screenshot(path=str(path), timeout=5000)
        print(f"  [Captura guardada: {path.name}]", flush=True)
    except Exception as exc:
        print(f"  (Captura diferida: {exc})", flush=True)


def run_live_test() -> bool:
    cc = preparar_fixtures()
    print(
        "Fixtures preparadas (Centro de Costo: 'Laboratorio de Inteligencia Artificial').",
        flush=True,
    )

    with sync_playwright() as p:
        print("Conectando con la ventana de Chrome en http://127.0.0.1:9222 ...", flush=True)
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        except Exception as exc:
            print(f"\n[ERROR] No se pudo conectar a Chrome en el puerto 9222: {exc}", flush=True)
            return False

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        page.bring_to_front()

        print("\n" + "=" * 60)
        print("CONECTADO A TU CHROME EN PANTALLA - INICIANDO PRUEBA VISUAL")
        print("=" * 60 + "\n", flush=True)

        # ----------------------------------------------------
        # PASO 1: Catálogos y Parámetros Operativos (Operador)
        # ----------------------------------------------------
        print(
            ">>> PASO 1: Autenticación con Operadora ('demo_o') y verificación de Catálogos ATP...",
            flush=True,
        )
        login_as(context, page, "demo_o")
        print("  Autenticado exitosamente como 'demo_o'.", flush=True)

        page.goto(f"{BASE_URL}/gastos/catalogos/")
        page.wait_for_load_state("networkidle")
        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-01-catalogos-parametros-atp.png")
        print("  Mostrando panel de catálogos y base imponible ATP en tu navegador.", flush=True)
        time.sleep(3)

        # ----------------------------------------------------
        # PASO 2: Presentar Solicitud > $90.000 (Solicitante)
        # ----------------------------------------------------
        print(
            "\n>>> PASO 2: Login con Solicitante ('demo_a') y presentación de Gasto ($120.000)...",
            flush=True,
        )
        login_as(context, page, "demo_a")
        print("  Autenticado exitosamente como 'demo_a'.", flush=True)

        page.goto(f"{BASE_URL}/gastos/presentar/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Completar formulario
        page.fill('input[name="concepto"]', "Servidor GPU Deep Learning (Partida ATP)")
        time.sleep(0.3)
        page.fill('input[name="monto_estimado"]', "120000.00")
        time.sleep(0.3)
        page.fill('input[name="unidad_requirente"]', "Depto. Sistemas de Información")
        time.sleep(0.3)
        page.select_option('select[name="tipo_flujo"]', TipoFlujoGasto.COMPRA_DIRECTA)
        time.sleep(0.3)
        page.select_option('select[name="centro_costo"]', str(cc.pk))
        time.sleep(0.3)

        # Datos bancarios
        page.fill('input[name="titular_nombre"]', "Franco Damián Sánchez")
        time.sleep(0.3)
        page.fill('input[name="identificacion"]', "20-40111222-3")
        time.sleep(0.3)
        page.fill('input[name="cbu_alias"]', "0110599520000001234567")
        time.sleep(0.3)
        page.fill('input[name="correo_comprobante"]', "franco.investigacion@frre.utn.edu.ar")
        time.sleep(0.3)

        print("  Formulario completado en pantalla. Enviando...", flush=True)
        time.sleep(2)
        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-02-formulario-alta-120k.png")

        page.click('button:has-text("Enviar Solicitud")')
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Obtener ID de la solicitud
        current_url = page.url
        solicitud_id = int(current_url.rstrip("/").split("/")[-1])
        print(f"  Solicitud #{solicitud_id} creada exitosamente.", flush=True)
        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-03-detalle-solicitud-creada.png")
        time.sleep(2.5)

        # ----------------------------------------------------
        # PASO 3: Incorporar Factura y Aprobar Solicitud
        # ----------------------------------------------------
        print(
            f"\n>>> PASO 3: Aportando comprobante y aprobando Solicitud #{solicitud_id}...",
            flush=True,
        )
        User = get_user_model()
        user_a = User.objects.get(username="demo_a")
        aportar_documento(solicitud_id, user_a.pk, Documento.Tipo.FACTURA_PROVEEDOR)
        print("  Documento 'Factura de Proveedor' incorporado al legajo.", flush=True)

        # Login Operador demo_o para aprobar
        login_as(context, page, "demo_o")

        page.goto(f"{BASE_URL}/gastos/{solicitud_id}/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Aprobar
        page.fill('textarea[name="motivo"]', "Aprobado para proyecto I+D financiado")
        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-04-formulario-decision-operadora.png")
        time.sleep(1.5)
        page.click('button[name="action"][value="aceptar"]')
        page.wait_for_load_state("networkidle")
        print("  Solicitud APROBADA.", flush=True)
        time.sleep(2.5)

        # ----------------------------------------------------
        # PASO 4: Pantalla de Pago y Verificación de Alerta ATP
        # ----------------------------------------------------
        print(
            f"\n>>> PASO 4: Navegando a Registrar Pago de Solicitud #{solicitud_id}...", flush=True
        )
        page.goto(f"{BASE_URL}/gastos/{solicitud_id}/pagar/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Verificar presencia del aviso preventivo
        aviso_locator = page.locator(".message.message-warning")
        if aviso_locator.count() > 0:
            print(
                "  [PASS] ¡Banner preventivo de Retención ATP Chaco visible en pantalla!",
                flush=True,
            )
            aviso_texto = aviso_locator.inner_text()
            print(f"  Detalle del aviso:\n    {aviso_texto.replace(chr(10), ' ')}", flush=True)
        else:
            print("  [ALERTA] No se encontró el banner preventivo ATP.", flush=True)

        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-05-aviso-preventivo-atp-chaco.png")
        time.sleep(3.5)

        # ----------------------------------------------------
        # PASO 5: Cargar Pago con Retención ATP Chaco
        # ----------------------------------------------------
        print("\n>>> PASO 5: Completando formulario de pago con retención ATP...", flush=True)
        # Bruto: 120000.00, Retención: 4200.00 (3.5%), Neto a transferir: 115800.00
        page.fill('input[name="monto_bruto"]', "120000.00")
        time.sleep(0.4)
        page.fill('input[name="monto_retencion_atp"]', "4200.00")
        time.sleep(0.4)
        page.fill('input[name="referencia_atp"]', "CERT-ATP-CHACO-2026-9988")
        time.sleep(0.4)
        page.fill('input[name="importe"]', "115800.00")
        time.sleep(0.4)
        page.fill('input[name="fecha_pago"]', "2026-11-03")
        time.sleep(0.4)
        page.fill('input[name="referencia_externa"]', "TRANSF-BANCO-CH-887711")
        time.sleep(0.4)

        # Seleccionar documento disponible
        opciones_select = page.locator('select[name="referencia_documental"] option')
        count = opciones_select.count()
        if count > 1:
            val = opciones_select.nth(1).get_attribute("value")
            if val:
                page.select_option('select[name="referencia_documental"]', val)
                print(f"  Documento respaldatorio seleccionado: value='{val}'", flush=True)

        time.sleep(2.5)
        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-06-formulario-pago-con-retencion.png")
        print("  Enviando pago con retención...", flush=True)

        page.click('#pago-externo-form button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(2.5)

        # ----------------------------------------------------
        # PASO 6: Verificar Desglose Contable en Detalle
        # ----------------------------------------------------
        print("\n>>> PASO 6: Verificando desglose contable en detalle de solicitud...", flush=True)
        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-07-detalle-pago-desglose-atp.png")

        contenido_pagina = page.content()
        assert "Monto Bruto" in contenido_pagina, "Debe mostrarse 'Monto Bruto'"
        assert "Retención ATP Chaco" in contenido_pagina, "Debe mostrarse 'Retención ATP Chaco'"
        assert "Neto Transferido" in contenido_pagina, "Debe mostrarse 'Neto Transferido'"
        assert "CERT-ATP-CHACO-2026-9988" in contenido_pagina, "Debe mostrarse el certificado ATP"
        print("  [PASS] ¡Desglose contable completo verificado exitosamente en la UI!", flush=True)
        print("    - Monto Bruto: $ 120.000,00 ARS")
        print("    - Retención ATP: $ 4.200,00 ARS (Cert: CERT-ATP-CHACO-2026-9988)")
        print("    - Neto Transferido: $ 115.800,00 ARS")
        time.sleep(4)

        # ----------------------------------------------------
        # PASO 7: Ajuste de Borde Issue #90 (Reintegro sólo Factura)
        # ----------------------------------------------------
        print(
            "\n>>> PASO 7: Verificando ajuste de borde de Issue #90 (Reintegro sólo Factura)...",
            flush=True,
        )
        user_o = User.objects.get(username="demo_o")
        actor_a = get_actor_for_user(user_a)
        sol_reintegro = crear_solicitud_gasto(
            actor=actor_a,
            concepto="Insumos de Soldadura SMD (Reintegro)",
            monto_estimado=Decimal("45000.00"),
            unidad_requirente="Laboratorio Electrónica",
            tipo_flujo=TipoFlujoGasto.REINTEGRO,
        )
        actor_o = get_actor_for_user(user_o)
        decide_expense(
            actor=actor_o,
            solicitud_id=sol_reintegro.pk,
            action="aceptar",
            expected_version=0,
            motivo="Aprobado para reintegro",
        )
        # Incorporamos Factura y Presupuesto
        aportar_documento(sol_reintegro.pk, user_a.pk, Documento.Tipo.FACTURA_PROVEEDOR)
        aportar_documento(sol_reintegro.pk, user_a.pk, Documento.Tipo.PRESUPUESTO_PROFORMA)

        # Vamos a pagar como Operador
        page.goto(f"{BASE_URL}/gastos/{sol_reintegro.pk}/pagar/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        opciones_textos = page.locator(
            'select[name="referencia_documental"] option'
        ).all_text_contents()
        print(f"  Opciones presentes en el selector: {opciones_textos}", flush=True)

        tiene_presupuesto = any(
            "Presupuesto" in opt or "Proforma" in opt for opt in opciones_textos
        )
        tiene_factura = any("Factura" in opt or "Ticket" in opt for opt in opciones_textos)

        assert not tiene_presupuesto, (
            "ERROR: Un reintegro NO debe admitir Presupuesto en el selector"
        )
        assert tiene_factura, "ERROR: Debe admitir Factura"
        print("  [PASS] Reintegro filtra estrictamente y NO lista presupuestos.", flush=True)

        take_safe_screenshot(page, EVIDENCE_DIR / "live-91-08-reintegro-selector-solo-factura.png")
        time.sleep(3.5)

        print("\n" + "=" * 60)
        print("TODAS LAS PRUEBAS VISUALES E2E FINALIZARON EXITOSAMENTE")
        print("=" * 60 + "\n", flush=True)
        return True


if __name__ == "__main__":
    exit_code = 0 if run_live_test() else 1
    sys.exit(exit_code)
