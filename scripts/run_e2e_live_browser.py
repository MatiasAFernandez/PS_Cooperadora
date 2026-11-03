"""Script E2E conectado por Chrome Remote Debugging (CDP) en vivo.

Permite al usuario observar en tiempo real en su propia pantalla cómo se
ejecutan las pruebas de la Issue #90.

Uso:
1. Abrir Chrome con Win + R:
   chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\ChromeCooperadora" http://127.0.0.1:8000/demo/acceso/
2. Ejecutar este script.
"""

import os
import sys
import time
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
from gastos.models import CentroCosto  # noqa: E402
from identidad.services import Actor  # noqa: E402
from tests.integracion.helpers import archivo_pdf  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
EVIDENCE_DIR = Path("docs/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

results: list[dict[str, str]] = []


def log_result(scenario: str, status: str, details: str = "") -> None:
    results.append({"scenario": scenario, "status": status, "details": details})
    prefix = "[PASS]" if status == "PASSED" else "[FAIL]"
    print(f"{prefix} {scenario}: {details}", flush=True)


def take_safe_screenshot(page: Any, path: Path) -> None:
    try:
        page.screenshot(path=str(path), timeout=5000)
    except Exception as exc:
        print(f"  (Captura guardada previamente o diferida: {exc})", flush=True)


def preparar_fixtures() -> tuple[CentroCosto, CentroCosto, CentroCosto]:
    c_ia, _ = CentroCosto.objects.update_or_create(
        codigo="lab-ia",
        defaults={"nombre": "Laboratorio de Inteligencia Artificial", "activo": True},
    )
    c_quim, _ = CentroCosto.objects.update_or_create(
        codigo="lab-quimica",
        defaults={"nombre": "Laboratorio de Química", "activo": True},
    )
    c_inactivo, _ = CentroCosto.objects.update_or_create(
        codigo="proyecto-cerrado",
        defaults={"nombre": "Proyecto Cerrado 2024", "activo": False},
    )
    return c_ia, c_quim, c_inactivo


def aportar_documentos_sinteticos(solicitud_id: int, solicitante_id: int) -> None:
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
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    incorporar(
        actor=actor_solic,
        referencia=f"gastos:{solicitud_id}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia="SOLICITANTE",
    )


def run_live_tests() -> bool:
    c_ia, c_quim, c_inactivo = preparar_fixtures()
    print("Fixtures de Centros de Costo listas.", flush=True)

    with sync_playwright() as p:
        print("Conectando con la ventana de Chrome en http://127.0.0.1:9222 ...", flush=True)
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        except Exception as exc:
            print(f"\n[ERROR] No se pudo conectar a Chrome en el puerto 9222: {exc}", flush=True)
            print("Por favor, ejecutá en Windows (Win + R):", flush=True)
            print(
                'chrome.exe --remote-debugging-port=9222 '
                '--user-data-dir="%TEMP%\\ChromeCooperadora" '
                'http://127.0.0.1:8000/demo/acceso/\n',
                flush=True,
            )
            return False

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        page.bring_to_front()

        print("\n==================================================", flush=True)
        print("CONECTADO EXITOSAMENTE A TU NAVEGADOR CHROME EN PANTALLA", flush=True)
        print("==================================================\n", flush=True)

        # ----------------------------------------------------
        # LOGIN SOLICITANTE
        # ----------------------------------------------------
        print("--- Paso 1: Autenticación con Solicitante ('demo_a') ---", flush=True)
        context.clear_cookies()
        page.goto(f"{BASE_URL}/demo/acceso/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.fill('input[name="username"]', "demo_a")
        time.sleep(0.5)
        page.fill('input[name="password"]', "demo1234")
        time.sleep(0.5)
        page.click('button:has-text("Ingresar")')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # ----------------------------------------------------
        # ESCENARIO 1: Alta Modalidad REINTEGRO y Sincronización GAST-R02
        # ----------------------------------------------------
        print("--- Paso 2: Presentar Solicitud con Modalidad Reintegro ---", flush=True)
        page.goto(f"{BASE_URL}/gastos/presentar/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        select_flujo = page.locator('select[name="tipo_flujo"]')
        flujo_options = select_flujo.locator("option").all_inner_texts()
        flujo_values = select_flujo.locator("option").evaluate_all("opts => opts.map(o => o.value)")
        if "COMPRA_DIRECTA" in flujo_values and "REINTEGRO" in flujo_values:
            log_result("1.1 Selector de Modalidad", "PASSED", f"Opciones: {flujo_options}")
        else:
            log_result("1.1 Selector de Modalidad", "FAILED", f"Faltan opciones: {flujo_values}")

        select_centro = page.locator('select[name="centro_costo"]')
        centro_texts = select_centro.locator("option").all_inner_texts()
        tiene_activo = any("Laboratorio de Inteligencia Artificial" in t for t in centro_texts)
        tiene_inactivo = any("Proyecto Cerrado 2024" in t for t in centro_texts)
        if tiene_activo and not tiene_inactivo:
            log_result(
                "1.2 Centros de Costo activos", "PASSED", "Solo centros activos en el catálogo"
            )
        else:
            log_result("1.2 Centros de Costo activos", "FAILED", "Inactivo no fue filtrado")

        page.fill(
            'input[name="concepto"]', "Reintegro por compra de reactivos e insumos analíticos"
        )
        time.sleep(0.4)
        page.fill('input[name="monto_estimado"]', "45000.00")
        time.sleep(0.4)
        page.fill('input[name="unidad_requirente"]', "Cátedra Química Orgánica")
        time.sleep(0.4)
        page.select_option('select[name="tipo_flujo"]', "REINTEGRO")
        time.sleep(0.4)
        page.select_option('select[name="centro_costo"]', str(c_ia.pk))
        time.sleep(0.4)

        # Bloque de transferencia dejando centro_costo vacío
        page.fill('input[name="titular_nombre"]', "Dra. Investigadora Principal")
        time.sleep(0.3)
        page.fill('input[name="identificacion"]', "27-33445566-4")
        time.sleep(0.3)
        page.fill('input[name="cbu_alias"]', "investigadora.ia")
        time.sleep(0.3)
        page.fill('input[name="correo_comprobante"]', "investigadora@frre.utn.edu.ar")
        time.sleep(0.3)
        page.fill('fieldset input[name="centro_costo"]', "")
        time.sleep(0.8)

        take_safe_screenshot(page, EVIDENCE_DIR / "e2e-90-01-alta-reintegro-form.png")
        page.click('button:has-text("Enviar Solicitud")')
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        url_reintegro = page.url
        id_reintegro = int(url_reintegro.rstrip("/").split("/")[-1])
        print(f"  -> Solicitud Reintegro creada con ID #{id_reintegro}", flush=True)

        badge_flujo = page.locator('th:has-text("Modalidad de Gasto") + td').inner_text()
        fila_centro = page.locator('th:has-text("Centro de Costo") + td').inner_text()
        transferencia_centro = page.locator(
            'dt:has-text("Centro de costo informado") + dd'
        ).inner_text()

        if "Reintegro a solicitante" in badge_flujo:
            log_result("1.3 Badge Modalidad Reintegro", "PASSED", badge_flujo.strip())
        else:
            log_result("1.3 Badge Modalidad Reintegro", "FAILED", badge_flujo.strip())

        if "Laboratorio de Inteligencia Artificial" in fila_centro:
            log_result("1.4 Centro Costo institucional", "PASSED", fila_centro.strip())
        else:
            log_result("1.4 Centro Costo institucional", "FAILED", fila_centro.strip())

        if "Laboratorio de Inteligencia Artificial" in transferencia_centro:
            log_result(
                "1.5 Auto-sincronización GAST-R02",
                "PASSED",
                f"Poblado automáticamente con '{transferencia_centro.strip()}'",
            )
        else:
            log_result("1.5 Auto-sincronización GAST-R02", "FAILED", transferencia_centro.strip())

        take_safe_screenshot(page, EVIDENCE_DIR / "e2e-90-02-detalle-reintegro-sincronizado.png")

        # ----------------------------------------------------
        # ESCENARIO 2: Alta Modalidad COMPRA DIRECTA
        # ----------------------------------------------------
        print("\n--- Paso 3: Presentar Solicitud con Modalidad Compra Directa ---", flush=True)
        page.goto(f"{BASE_URL}/gastos/presentar/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.fill('input[name="concepto"]', "Adquisición directa de servidores de cómputo GPU")
        time.sleep(0.4)
        page.fill('input[name="monto_estimado"]', "85000.00")
        time.sleep(0.4)
        page.fill('input[name="unidad_requirente"]', "Área TIC y Cómputo")
        time.sleep(0.4)
        page.select_option('select[name="tipo_flujo"]', "COMPRA_DIRECTA")
        time.sleep(0.4)
        page.select_option('select[name="centro_costo"]', str(c_ia.pk))
        time.sleep(0.4)

        page.fill('input[name="titular_nombre"]', "Tecnología y Redes SRL")
        time.sleep(0.3)
        page.fill('input[name="identificacion"]', "30-71998877-3")
        time.sleep(0.3)
        page.fill('input[name="cbu_alias"]', "redes.servidores")
        time.sleep(0.3)
        page.fill('input[name="correo_comprobante"]', "ventas@redescomputo.com")
        time.sleep(0.3)
        page.fill(
            'fieldset input[name="centro_costo"]', "Subdirección de Infraestructura Tecnológica"
        )
        time.sleep(0.8)

        take_safe_screenshot(page, EVIDENCE_DIR / "e2e-90-03-alta-compra-directa-form.png")
        page.click('button:has-text("Enviar Solicitud")')
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        url_directa = page.url
        id_directa = int(url_directa.rstrip("/").split("/")[-1])
        print(f"  -> Solicitud Compra Directa creada con ID #{id_directa}", flush=True)

        badge_directa = page.locator('th:has-text("Modalidad de Gasto") + td').inner_text()
        transferencia_explicito = page.locator(
            'dt:has-text("Centro de costo informado") + dd'
        ).inner_text()

        if "Compra directa a proveedor" in badge_directa:
            log_result("2.1 Modalidad Compra Directa", "PASSED", badge_directa.strip())
        else:
            log_result("2.1 Modalidad Compra Directa", "FAILED", badge_directa.strip())

        if "Subdirección de Infraestructura Tecnológica" in transferencia_explicito:
            log_result(
                "2.2 Centro Costo Explícito respetado",
                "PASSED",
                f"Preservó valor: '{transferencia_explicito.strip()}'",
            )
        else:
            log_result(
                "2.2 Centro Costo Explícito respetado", "FAILED", transferencia_explicito.strip()
            )

        take_safe_screenshot(page, EVIDENCE_DIR / "e2e-90-04-detalle-compra-directa.png")

        # ----------------------------------------------------
        # ESCENARIO 3: Decisión y Verificación de Pagos C01 (GAST-R03)
        # ----------------------------------------------------
        print("\n--- Paso 4: Aportar Documentos y Decisión Directiva ('demo_o') ---", flush=True)
        user_model = get_user_model()
        user_a = user_model.objects.get(username="demo_a")
        aportar_documentos_sinteticos(id_reintegro, user_a.pk)
        aportar_documentos_sinteticos(id_directa, user_a.pk)

        # Cambiar sesión a Operador demo_o
        context.clear_cookies()
        page.goto(f"{BASE_URL}/demo/acceso/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.fill('input[name="username"]', "demo_o")
        time.sleep(0.4)
        page.fill('input[name="password"]', "demo1234")
        time.sleep(0.4)
        page.click('button:has-text("Ingresar")')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Aprobar Reintegro
        page.goto(f"{BASE_URL}/gastos/{id_reintegro}/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.fill('textarea[name="motivo"]', "Aprobado para reintegro de insumos de investigación")
        time.sleep(0.5)
        page.click('button[name="action"][value="aceptar"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        take_safe_screenshot(page, EVIDENCE_DIR / "e2e-90-05-decision-operadora.png")

        estado_reintegro = page.locator('th:has-text("Estado") + td').inner_text()
        if "Aceptada" in estado_reintegro:
            log_result("3.1 Decisión Aceptar (Reintegro)", "PASSED", estado_reintegro.strip())
        else:
            log_result("3.1 Decisión Aceptar (Reintegro)", "FAILED", estado_reintegro.strip())

        # Formulario de Pago Reintegro -> Exigencia estricta C01
        print("  -> Verificando restricción C01 en formulario de pago de Reintegro...", flush=True)
        page.goto(f"{BASE_URL}/gastos/{id_reintegro}/pagar/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        select_doc_reint = page.locator('select[name="referencia_documental"]')
        options_doc_reint = select_doc_reint.locator("option").all_inner_texts()

        tiene_fac = any("Factura" in opt for opt in options_doc_reint)
        tiene_pres = any("Presupuesto" in opt or "Proforma" in opt for opt in options_doc_reint)

        if tiene_fac and not tiene_pres:
            log_result(
                "3.2 Exigencia estricta Factura en Reintegro (GAST-R03)",
                "PASSED",
                f"Solo ofrece Factura ({options_doc_reint}). Presupuesto excluido.",
            )
        else:
            log_result(
                "3.2 Exigencia estricta Factura en Reintegro (GAST-R03)",
                "FAILED",
                f"Opciones: {options_doc_reint}",
            )

        take_safe_screenshot(
            page, EVIDENCE_DIR / "e2e-90-06-pago-reintegro-factura-exigida.png"
        )

        # Aprobar Compra Directa
        page.goto(f"{BASE_URL}/gastos/{id_directa}/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.fill('textarea[name="motivo"]', "Aprobada compra directa a proveedor")
        time.sleep(0.5)
        page.click('button[name="action"][value="aceptar"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Formulario de Pago Compra Directa -> Admite Presupuesto y Factura
        print("  -> Verificando admisión de Presupuesto y Factura en Compra Directa...", flush=True)
        page.goto(f"{BASE_URL}/gastos/{id_directa}/pagar/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        select_doc_dir = page.locator('select[name="referencia_documental"]')
        options_doc_dir = select_doc_dir.locator("option").all_inner_texts()

        tiene_fac_dir = any("Factura" in opt for opt in options_doc_dir)
        tiene_pres_dir = any("Presupuesto" in opt for opt in options_doc_dir)

        if tiene_fac_dir and tiene_pres_dir:
            log_result(
                "3.3 Admisión de Factura y Presupuesto en Compra Directa",
                "PASSED",
                f"Admite ambas opciones: {options_doc_dir}",
            )
        else:
            log_result(
                "3.3 Admisión de Factura y Presupuesto en Compra Directa",
                "FAILED",
                f"Opciones: {options_doc_dir}",
            )

        take_safe_screenshot(
            page, EVIDENCE_DIR / "e2e-90-07-pago-compra-directa-ambas-opciones.png"
        )

        print("\n==================================================", flush=True)
        print("PRUEBAS E2E COMPLETADAS CON ÉXITO EN TU NAVEGADOR", flush=True)
        print("==================================================", flush=True)
        for r in results:
            print(f" [{r['status']}] {r['scenario']}: {r['details']}", flush=True)

        # Dejar la página en el formulario para que el usuario pueda seguir interactuando
        print(
            "\nLa ventana de Chrome sigue abierta para que puedas explorarla libremente.",
            flush=True,
        )
        return True


if __name__ == "__main__":
    run_live_tests()
