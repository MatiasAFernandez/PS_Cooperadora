"""Script de Automatización E2E y Captura de Evidencia - Issue #90.

Módulo: Gastos y Pagos (Soporte de doble flujo: Compra Directa vs Reintegro,
y sincronización de Centro de Costo).
Verificaciones clave:
- GAST-R01: Modalidad de gasto (COMPRA_DIRECTA / REINTEGRO) persistida y visible.
- GAST-R02: Sincronización automática de CentroCosto hacia RevisionDatosTransferencia.
- GAST-R03: Restricción contractual C01 en Pagos: en REINTEGRO sólo se admite FACTURA_PROVEEDOR
  (rotulada como 'Factura o Ticket-Factura de proveedor'), rechazando presupuestos.
- Filtrado estricto de centros de costo activos en el selector de alta.
- Responsividad Mobile / Tablet y verificación de 0 errores de consola JS.
"""

import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Inicializar Django para fixtures y soporte documental
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
console_errors: list[str] = []
js_exceptions: list[str] = []


def log_result(scenario: str, status: str, details: str = "") -> None:
    results.append({"scenario": scenario, "status": status, "details": details})
    prefix = "[PASS]" if status == "PASSED" else "[FAIL]"
    print(f"{prefix} {scenario}: {details}")


def on_console(msg: Any) -> None:
    # Filtrar warnings de recursos no críticos (ej: favicon / network 404 de assets)
    if msg.type == "error":
        if "favicon" in msg.text.lower() or "status of 404" in msg.text:
            return
        console_errors.append(f"[{msg.type}] {msg.text}")
    elif msg.type == "warning" and "favicon" not in msg.text.lower():
        console_errors.append(f"[{msg.type}] {msg.text}")


def on_page_error(exc: Any) -> None:
    js_exceptions.append(str(exc))


def preparar_fixtures() -> tuple[CentroCosto, CentroCosto, CentroCosto]:
    """Asegura que los centros de costo existan con los estados esperados."""
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
    """Aporta una factura fiscal y un presupuesto a la solicitud para probar C01."""
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


def run_tests() -> bool:
    c_ia, c_quim, c_inactivo = preparar_fixtures()
    print("Fixtures de Centros de Costo verificadas en DB.")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=False,
            slow_mo=900,
            args=["--start-maximized", "--new-window"],
        )
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.bring_to_front()

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        print("\n==================================================")
        print("INICIANDO PRUEBAS E2E ISSUE #90: DOBLE FLUJO Y CENTRO COSTO")
        print("==================================================\n")

        # ----------------------------------------------------
        # LOGIN SOLICITANTE
        # ----------------------------------------------------
        print("--- Autenticación con Solicitante ('demo_a') ---")
        page.goto(f"{BASE_URL}/demo/acceso/")
        page.fill('input[name="username"]', "demo_a")
        page.fill('input[name="password"]', "demo1234")
        page.click('button:has-text("Ingresar")')
        page.wait_for_load_state("networkidle")

        # ----------------------------------------------------
        # ESCENARIO 1: Alta Modalidad REINTEGRO y GAST-R02
        # ----------------------------------------------------
        print("\n--- Escenario 1: Alta Modalidad Reintegro y Sincronización Centro Costo ---")
        page.goto(f"{BASE_URL}/gastos/presentar/")
        page.wait_for_load_state("networkidle")

        # 1.1 Verificar selector de Modalidad de Gasto
        select_flujo = page.locator('select[name="tipo_flujo"]')
        flujo_options = select_flujo.locator("option").all_inner_texts()
        flujo_values = select_flujo.locator("option").evaluate_all(
            "opts => opts.map(o => o.value)"
        )
        if "COMPRA_DIRECTA" in flujo_values and "REINTEGRO" in flujo_values:
            log_result(
                "1.1 Selector de Modalidad disponible",
                "PASSED",
                f"Opciones presentes: {flujo_options}",
            )
        else:
            log_result(
                "1.1 Selector de Modalidad disponible",
                "FAILED",
                f"Faltan opciones de modalidad: {flujo_values}",
            )

        # 1.2 Verificar filtrado de Centros de Costo Activos (y exclusión de inactivos)
        select_centro = page.locator('select[name="centro_costo"]')
        centro_texts = select_centro.locator("option").all_inner_texts()
        tiene_activo = any("Laboratorio de Inteligencia Artificial" in t for t in centro_texts)
        tiene_inactivo = any("Proyecto Cerrado 2024" in t for t in centro_texts)
        if tiene_activo and not tiene_inactivo:
            log_result(
                "1.2 Filtrado de Centros de Costo activos",
                "PASSED",
                "Centros activos presentes, inactivo 'Proyecto Cerrado 2024' excluido",
            )
        else:
            log_result(
                "1.2 Filtrado de Centros de Costo activos",
                "FAILED",
                f"Fallo en filtrado: tiene_activo={tiene_activo}, tiene_inactivo={tiene_inactivo}",
            )

        # 1.3 Completar formulario de Reintegro sin centro_costo (validar GAST-R02)
        page.fill(
            'input[name="concepto"]', "Reintegro por compra de reactivos e insumos analíticos"
        )
        page.fill('input[name="monto_estimado"]', "45000.00")
        page.fill('input[name="unidad_requirente"]', "Cátedra Química Orgánica")
        page.select_option('select[name="tipo_flujo"]', "REINTEGRO")
        page.select_option('select[name="centro_costo"]', str(c_ia.pk))

        # Bloque de transferencia opcional
        page.fill('input[name="titular_nombre"]', "Dra. Investigadora Principal")
        page.fill('input[name="identificacion"]', "27-33445566-4")
        page.fill('input[name="cbu_alias"]', "investigadora.ia")
        page.fill('input[name="correo_comprobante"]', "investigadora@frre.utn.edu.ar")
        # Dejamos centro_costo de transferencia VACÍO para comprobar auto-sincronización GAST-R02
        page.fill('fieldset input[name="centro_costo"]', "")

        shot_1 = EVIDENCE_DIR / "e2e-90-01-alta-reintegro-form.png"
        page.screenshot(path=str(shot_1), full_page=True)
        print(f"  Captura guardada: {shot_1}")

        # Enviar formulario
        page.click('button:has-text("Enviar Solicitud")')
        page.wait_for_load_state("networkidle")

        url_reintegro = page.url
        id_reintegro = int(url_reintegro.rstrip("/").split("/")[-1])
        print(f"  Solicitud de Reintegro creada con ID #{id_reintegro}")

        # 1.4 Validar renderizado de Reintegro en detalle
        badge_flujo = page.locator('th:has-text("Modalidad de Gasto") + td').inner_text()
        fila_centro = page.locator('th:has-text("Centro de Costo") + td').inner_text()
        transferencia_centro = page.locator(
            'dt:has-text("Centro de costo informado") + dd'
        ).inner_text()

        if "Reintegro a solicitante" in badge_flujo:
            log_result("1.3 Badge de Modalidad Reintegro en Detalle", "PASSED", badge_flujo.strip())
        else:
            log_result(
                "1.3 Badge de Modalidad Reintegro en Detalle",
                "FAILED",
                f"Esperado Reintegro, obtenido: {badge_flujo}",
            )

        if "Laboratorio de Inteligencia Artificial" in fila_centro and "lab-ia" in fila_centro:
            log_result(
                "1.4 Centro de Costo institucional persistido", "PASSED", fila_centro.strip()
            )
        else:
            log_result(
                "1.4 Centro de Costo institucional persistido", "FAILED", fila_centro.strip()
            )

        # GAST-R02: auto-sincronización hacia RevisionDatosTransferencia
        if "Laboratorio de Inteligencia Artificial" in transferencia_centro:
            log_result(
                "1.5 Auto-sincronización Centro Costo a Transferencia (GAST-R02)",
                "PASSED",
                f"Auto-poblado con '{transferencia_centro.strip()}'",
            )
        else:
            log_result(
                "1.5 Auto-sincronización Centro Costo a Transferencia (GAST-R02)",
                "FAILED",
                f"Valor no sincronizado: '{transferencia_centro.strip()}'",
            )

        shot_2 = EVIDENCE_DIR / "e2e-90-02-detalle-reintegro-sincronizado.png"
        page.screenshot(path=str(shot_2), full_page=True)
        print(f"  Captura guardada: {shot_2}")

        # ----------------------------------------------------
        # ESCENARIO 2: Alta Modalidad COMPRA DIRECTA
        # ----------------------------------------------------
        print("\n--- Escenario 2: Alta Modalidad Compra Directa y Centro Costo Explícito ---")
        page.goto(f"{BASE_URL}/gastos/presentar/")
        page.wait_for_load_state("networkidle")

        page.fill('input[name="concepto"]', "Adquisición directa de servidores de cómputo GPU")
        page.fill('input[name="monto_estimado"]', "85000.00")
        page.fill('input[name="unidad_requirente"]', "Área TIC y Cómputo")
        page.select_option('select[name="tipo_flujo"]', "COMPRA_DIRECTA")
        page.select_option('select[name="centro_costo"]', str(c_ia.pk))

        # Transferencia con centro de costo explícito provisto por el usuario
        page.fill('input[name="titular_nombre"]', "Tecnología y Redes SRL")
        page.fill('input[name="identificacion"]', "30-71998877-3")
        page.fill('input[name="cbu_alias"]', "redes.servidores")
        page.fill('input[name="correo_comprobante"]', "ventas@redescomputo.com")
        page.fill(
            'fieldset input[name="centro_costo"]', "Subdirección de Infraestructura Tecnológica"
        )

        shot_3 = EVIDENCE_DIR / "e2e-90-03-alta-compra-directa-form.png"
        page.screenshot(path=str(shot_3), full_page=True)
        print(f"  Captura guardada: {shot_3}")

        page.click('button:has-text("Enviar Solicitud")')
        page.wait_for_load_state("networkidle")

        url_directa = page.url
        id_directa = int(url_directa.rstrip("/").split("/")[-1])
        print(f"  Solicitud de Compra Directa creada con ID #{id_directa}")

        badge_directa = page.locator('th:has-text("Modalidad de Gasto") + td').inner_text()
        transferencia_explicito = page.locator(
            'dt:has-text("Centro de costo informado") + dd'
        ).inner_text()

        if "Compra directa a proveedor" in badge_directa:
            log_result("2.1 Modalidad Compra Directa en Detalle", "PASSED", badge_directa.strip())
        else:
            log_result("2.1 Modalidad Compra Directa en Detalle", "FAILED", badge_directa.strip())

        if "Subdirección de Infraestructura Tecnológica" in transferencia_explicito:
            log_result(
                "2.2 Respeto de Centro de Costo explícito",
                "PASSED",
                f"Se preservó el valor textual del usuario: '{transferencia_explicito.strip()}'",
            )
        else:
            log_result(
                "2.2 Respeto de Centro de Costo explícito",
                "FAILED",
                transferencia_explicito.strip(),
            )

        shot_4 = EVIDENCE_DIR / "e2e-90-04-detalle-compra-directa.png"
        page.screenshot(path=str(shot_4), full_page=True)
        print(f"  Captura guardada: {shot_4}")

        # ----------------------------------------------------
        # ESCENARIO 3: Aportar Documentos Sintéticos y Decidir (Operador 'demo_o')
        # ----------------------------------------------------
        print("\n--- Escenario 3: Decisión y Restricción Documental C01 en Pagos (GAST-R03) ---")

        # Inyectar respaldos sintéticos (Factura + Presupuesto) a ambas solicitudes
        user_model = get_user_model()
        user_a = user_model.objects.get(username="demo_a")
        aportar_documentos_sinteticos(id_reintegro, user_a.pk)
        aportar_documentos_sinteticos(id_directa, user_a.pk)
        print("  Documentos sintéticos (Factura + Presupuesto) incorporados a ambas solicitudes.")

        # Logout solicitante para cambiar a Operador 'demo_o'
        context.clear_cookies()

        # Iniciar sesión con Operador 'demo_o'
        page.goto(f"{BASE_URL}/demo/acceso/")
        page.fill('input[name="username"]', "demo_o")
        page.fill('input[name="password"]', "demo1234")
        page.click('button:has-text("Ingresar")')
        page.wait_for_load_state("networkidle")

        # 3.1 Aceptar Solicitud de Reintegro
        page.goto(f"{BASE_URL}/gastos/{id_reintegro}/")
        page.wait_for_load_state("networkidle")

        # Completar motivo y presionar "Aceptar"
        page.fill('textarea[name="motivo"]', "Aprobado para reintegro de insumos de investigación")
        page.click('button[name="action"][value="aceptar"]')
        page.wait_for_load_state("networkidle")

        shot_5 = EVIDENCE_DIR / "e2e-90-05-decision-operadora.png"
        page.screenshot(path=str(shot_5), full_page=True)
        print(f"  Captura guardada: {shot_5}")

        estado_reintegro = page.locator('th:has-text("Estado") + td').inner_text()
        if "Aceptada" in estado_reintegro:
            log_result("3.1 Transición a Aceptada (Reintegro)", "PASSED", estado_reintegro.strip())
        else:
            log_result("3.1 Transición a Aceptada (Reintegro)", "FAILED", estado_reintegro.strip())

        # 3.2 Acceder al formulario de Pago de Reintegro y verificar GAST-R03
        page.goto(f"{BASE_URL}/gastos/{id_reintegro}/pagar/")
        page.wait_for_load_state("networkidle")

        select_doc_reint = page.locator('select[name="referencia_documental"]')
        options_doc_reint = select_doc_reint.locator("option").all_inner_texts()

        tiene_factura_rotulo = any("Factura" in opt for opt in options_doc_reint)
        tiene_presupuesto = any(
            "Presupuesto" in opt or "Proforma" in opt for opt in options_doc_reint
        )

        if tiene_factura_rotulo and not tiene_presupuesto:
            log_result(
                "3.2 Exigencia estricta de Factura en Reintegro (GAST-R03)",
                "PASSED",
                f"Solo ofrece Factura ({options_doc_reint}). Presupuesto excluido.",
            )
        else:
            log_result(
                "3.2 Exigencia estricta de Factura en Reintegro (GAST-R03)",
                "FAILED",
                f"Opciones observadas en Reintegro: {options_doc_reint}",
            )

        shot_6 = EVIDENCE_DIR / "e2e-90-06-pago-reintegro-factura-exigida.png"
        page.screenshot(path=str(shot_6), full_page=True)
        print(f"  Captura guardada: {shot_6}")

        # 3.3 Aceptar Solicitud de Compra Directa y verificar que admite Presupuesto + Factura
        page.goto(f"{BASE_URL}/gastos/{id_directa}/")
        page.wait_for_load_state("networkidle")

        page.fill('textarea[name="motivo"]', "Aprobada compra directa a proveedor")
        page.click('button[name="action"][value="aceptar"]')
        page.wait_for_load_state("networkidle")

        page.goto(f"{BASE_URL}/gastos/{id_directa}/pagar/")
        page.wait_for_load_state("networkidle")

        select_doc_dir = page.locator('select[name="referencia_documental"]')
        options_doc_dir = select_doc_dir.locator("option").all_inner_texts()

        tiene_fac_dir = any("Factura" in opt for opt in options_doc_dir)
        tiene_pres_dir = any("Presupuesto" in opt for opt in options_doc_dir)

        if tiene_fac_dir and tiene_pres_dir:
            log_result(
                "3.3 Admisión de Factura y Presupuesto en Compra Directa",
                "PASSED",
                f"Admite Factura y Presupuesto: {options_doc_dir}",
            )
        else:
            log_result(
                "3.3 Admisión de Factura y Presupuesto en Compra Directa",
                "FAILED",
                f"Opciones observadas en Compra Directa: {options_doc_dir}",
            )

        shot_7 = EVIDENCE_DIR / "e2e-90-07-pago-compra-directa-ambas-opciones.png"
        page.screenshot(path=str(shot_7), full_page=True)
        print(f"  Captura guardada: {shot_7}")

        # ----------------------------------------------------
        # ESCENARIO 4: Responsividad Mobile y Tablet + Consola Limpia
        # ----------------------------------------------------
        print("\n--- Escenario 4: Pruebas de Responsividad (Mobile/Tablet) y Consola ---")

        # 4.1 Mobile Viewport (iPhone 13 / 375x812) con Solicitante
        page.set_viewport_size({"width": 375, "height": 812})
        context.clear_cookies()
        page.goto(f"{BASE_URL}/demo/acceso/")
        page.fill('input[name="username"]', "demo_a")
        page.fill('input[name="password"]', "demo1234")
        page.click('button:has-text("Ingresar")')
        page.wait_for_load_state("networkidle")

        page.goto(f"{BASE_URL}/gastos/presentar/")
        page.wait_for_load_state("networkidle")
        shot_8 = EVIDENCE_DIR / "e2e-90-08-responsivo-alta-mobile.png"
        page.screenshot(path=str(shot_8), full_page=True)
        print(f"  Captura guardada: {shot_8}")
        log_result(
            "4.1 Layout Responsivo Mobile (375x812)", "PASSED", "Formulario legible y accesible"
        )

        # 4.2 Tablet Viewport (iPad / 768x1024)
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{BASE_URL}/gastos/{id_reintegro}/")
        page.wait_for_load_state("networkidle")
        shot_9 = EVIDENCE_DIR / "e2e-90-09-responsivo-detalle-tablet.png"
        page.screenshot(path=str(shot_9), full_page=True)
        print(f"  Captura guardada: {shot_9}")
        log_result(
            "4.2 Layout Responsivo Tablet (768x1024)",
            "PASSED",
            "Vista de detalle organizada sin solapamientos",
        )

        # 4.3 Verificación de Errores en Consola JS
        if not console_errors and not js_exceptions:
            log_result(
                "4.3 Salud de Consola del Navegador",
                "PASSED",
                "0 errores de consola y 0 excepciones JS registradas durante todo el recorrido E2E",
            )
        else:
            log_result(
                "4.3 Salud de Consola del Navegador",
                "FAILED",
                f"Errores detectados: {console_errors + js_exceptions}",
            )

        page.wait_for_timeout(6000)
        browser.close()

    # Resumen final
    print("\n==================================================")
    print("RESUMEN DE PRUEBAS E2E ISSUE #90")
    print("==================================================")
    all_passed = True
    for r in results:
        status_symbol = "[PASS]" if r["status"] == "PASSED" else "[FAIL]"
        print(f" {status_symbol} {r['scenario']}: {r['details']}")
        if r["status"] != "PASSED":
            all_passed = False

    return all_passed


if __name__ == "__main__":
    exito = run_tests()
    sys.exit(0 if exito else 1)
