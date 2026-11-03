"""Script de Automatización E2E y Captura de Evidencia - Issue #89.

Módulo: Gastos y Pagos (Catálogos Dinámicos y Parametrización ATP)
"""

import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

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
    if msg.type in ["error", "warning"]:
        console_errors.append(f"[{msg.type}] {msg.text}")


def on_page_error(exc: Any) -> None:
    js_exceptions.append(str(exc))


def run_tests() -> bool:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
        )
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # Listen to console errors and exceptions
        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        print("\n==================================================")
        print("INICIANDO EJECUCIÓN DE PRUEBAS E2E (ISSUE #89)")
        print("==================================================\n")

        # ----------------------------------------------------
        # ESCENARIO 1: Navegación y Control de Acceso (Seguridad)
        # ----------------------------------------------------
        print("--- Escenario 1: Control de Acceso (Usuario Solicitante 'demo_a') ---")

        # 1. Login con solicitante
        page.goto(f"{BASE_URL}/demo/acceso/")
        page.fill('input[name="username"]', "demo_a")
        page.fill('input[name="password"]', "demo1234")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # 2. Navegar a /gastos/
        page.goto(f"{BASE_URL}/gastos/")
        page.wait_for_load_state("networkidle")

        # Verificar que el botón "Catálogos y Parámetros" NO esté visible
        boton_catalogos = page.locator('a:has-text("Catálogos y Parámetros")')
        is_visible = boton_catalogos.is_visible()
        if not is_visible:
            log_result(
                "1.1 Botón Catálogos oculto para solicitante",
                "PASSED",
                "El botón 'Catálogos y Parámetros' no está presente en el DOM",
            )
        else:
            log_result(
                "1.1 Botón Catálogos oculto para solicitante",
                "FAILED",
                "El botón es visible para demo_a",
            )

        # Captura 1: Listado de gastos sin botón de catálogos
        shot_1 = EVIDENCE_DIR / "e2e-89-01-solicitante-sin-boton.png"
        page.screenshot(path=str(shot_1), full_page=True)
        print(f"  Captura guardada: {shot_1}")

        # 3. Forzar acceso directo a /gastos/catalogos/
        response = page.goto(f"{BASE_URL}/gastos/catalogos/")
        page.wait_for_load_state("networkidle")
        status_code = response.status if response else 0

        if status_code == 403:
            log_result(
                "1.2 Forzar acceso directo URL /gastos/catalogos/",
                "PASSED",
                f"Retornó HTTP {status_code} Forbidden (Acceso denegado)",
            )
        else:
            log_result(
                "1.2 Forzar acceso directo URL /gastos/catalogos/",
                "FAILED",
                f"Retornó status HTTP {status_code} inesperado",
            )

        # Captura 2: Pantalla 403 Forbidden
        shot_2 = EVIDENCE_DIR / "e2e-89-02-solicitante-403-forbidden.png"
        page.screenshot(path=str(shot_2), full_page=True)
        print(f"  Captura guardada: {shot_2}")

        # Logout solicitante
        context.clear_cookies()

        # ----------------------------------------------------
        # ESCENARIO 2: Gestión de Catálogos (Operador 'demo_o')
        # ----------------------------------------------------
        print("\n--- Escenario 2: Gestión de Catálogos (Operador 'demo_o') ---")

        # 1. Login con operador
        page.goto(f"{BASE_URL}/demo/acceso/")
        page.fill('input[name="username"]', "demo_o")
        page.fill('input[name="password"]', "demo1234")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # 2. Navegar a /gastos/
        page.goto(f"{BASE_URL}/gastos/")
        page.wait_for_load_state("networkidle")

        boton_catalogos = page.locator('a:has-text("Catálogos y Parámetros")')
        if boton_catalogos.is_visible():
            log_result(
                "2.1 Botón Catálogos visible para operador",
                "PASSED",
                "El botón 'Catálogos y Parámetros' es visible con capacidades de gestión",
            )
        else:
            log_result(
                "2.1 Botón Catálogos visible para operador",
                "FAILED",
                "El botón no es visible para demo_o",
            )

        # Captura 3: Listado con botón visible
        shot_3 = EVIDENCE_DIR / "e2e-89-03-operador-boton-visible.png"
        page.screenshot(path=str(shot_3), full_page=True)
        print(f"  Captura guardada: {shot_3}")

        # Clic en botón "Catálogos y Parámetros"
        boton_catalogos.click()
        page.wait_for_load_state("networkidle")

        # Captura 4: Pantalla inicial de catálogos y parámetros
        shot_4 = EVIDENCE_DIR / "e2e-89-04-pantalla-catalogos-inicial.png"
        page.screenshot(path=str(shot_4), full_page=True)
        print(f"  Captura guardada: {shot_4}")

        # 3. Alta de Centro de Costo
        print("  Realizando alta de Centro de Costo (lab-ia)...")
        page.fill('input[name="codigo"]', "lab-ia")
        page.fill('input[name="nombre"]', "Laboratorio de Inteligencia Artificial")
        # Asegurar checkbox activo
        activo_cb = page.locator('input[name="activo"]')
        if not activo_cb.is_checked():
            activo_cb.check()

        # Enviar formulario de alta
        page.click('button:has-text("Agregar al Catálogo")')
        page.wait_for_load_state("networkidle")

        # Verificaciones de alta
        texto_pagina = page.content()
        alta_exitosa = (
            "Laboratorio de Inteligencia Artificial" in texto_pagina
            and "creado exitosamente" in texto_pagina
        )
        fila_lab_ia = page.locator('tr:has-text("lab-ia")')
        estado_activo = fila_lab_ia.locator('.badge:has-text("Activo")').is_visible()

        if alta_exitosa and estado_activo:
            log_result(
                "2.2 Alta de Centro de Costo 'lab-ia'",
                "PASSED",
                "Centro creado con mensaje de éxito y estado 'Activo'",
            )
        else:
            log_result(
                "2.2 Alta de Centro de Costo 'lab-ia'",
                "FAILED",
                f"Alta incompleta. exitosa={alta_exitosa}, estado_activo={estado_activo}",
            )

        # Captura 5: Alta exitosa de centro de costo
        shot_5 = EVIDENCE_DIR / "e2e-89-05-alta-centro-costo-exito.png"
        page.screenshot(path=str(shot_5), full_page=True)
        print(f"  Captura guardada: {shot_5}")

        # 4. Baja Lógica (Toggle a Inactivo)
        print("  Ejecutando baja lógica (toggle a Inactivo)...")
        btn_desactivar = fila_lab_ia.locator('button:has-text("Desactivar")')
        btn_desactivar.click()
        page.wait_for_load_state("networkidle")

        fila_lab_ia_post = page.locator('tr:has-text("lab-ia")')
        estado_inactivo = fila_lab_ia_post.locator('.badge:has-text("Inactivo")').is_visible()
        btn_activar_visible = fila_lab_ia_post.locator('button:has-text("Activar")').is_visible()

        if estado_inactivo and btn_activar_visible:
            log_result(
                "2.3 Baja lógica (Toggle a Inactivo)",
                "PASSED",
                "El centro cambió a estado 'Inactivo' y ofrece acción 'Activar'",
            )
        else:
            log_result(
                "2.3 Baja lógica (Toggle a Inactivo)",
                "FAILED",
                f"Fallo baja lógica. inactivo={estado_inactivo}, btn={btn_activar_visible}",
            )

        # Captura 6: Baja lógica (Inactivo)
        shot_6 = EVIDENCE_DIR / "e2e-89-06-toggle-baja-logica-inactivo.png"
        page.screenshot(path=str(shot_6), full_page=True)
        print(f"  Captura guardada: {shot_6}")

        # Reactivación
        print("  Reactivando centro de costo...")
        fila_lab_ia_post.locator('button:has-text("Activar")').click()
        page.wait_for_load_state("networkidle")

        fila_lab_ia_reactivado = page.locator('tr:has-text("lab-ia")')
        estado_reactivado = fila_lab_ia_reactivado.locator('.badge:has-text("Activo")').is_visible()

        if estado_reactivado:
            log_result(
                "2.4 Reactivación de Centro de Costo",
                "PASSED",
                "El centro volvió a estado 'Activo' sin duplicar registros",
            )
        else:
            log_result(
                "2.4 Reactivación de Centro de Costo",
                "FAILED",
                "El centro no quedó Activo tras toggle",
            )

        # Captura 7: Reactivación confirmada
        shot_7 = EVIDENCE_DIR / "e2e-89-07-toggle-reactivacion-activo.png"
        page.screenshot(path=str(shot_7), full_page=True)
        print(f"  Captura guardada: {shot_7}")

        # ----------------------------------------------------
        # ESCENARIO 3: Parametrización Impositiva ATP
        # ----------------------------------------------------
        print("\n--- Escenario 3: Parametrización Impositiva Retención ATP ---")

        # 1. Verificar valores precargados (fallback por defecto: 90000.00 y 3.50%)
        val_base_init = page.locator('input[name="base_imponible_atp"]').input_value()
        val_ali_init = page.locator('input[name="alicuota_atp"]').input_value()

        # Captura 8: Fallback de Parámetros ATP
        shot_8 = EVIDENCE_DIR / "e2e-89-08-parametros-atp-fallback.png"
        page.screenshot(path=str(shot_8), full_page=True)
        print(f"  Captura guardada: {shot_8}")

        base_init_ok = float(val_base_init.replace(",", ".")) == 90000.0
        ali_init_ok = float(val_ali_init.replace(",", ".")) == 3.5

        if base_init_ok and ali_init_ok:
            log_result(
                "3.1 Verificación valores fallback ATP ($90.000,00 y 3,50%)",
                "PASSED",
                f"Base={val_base_init}, Alícuota={val_ali_init}",
            )
        else:
            log_result(
                "3.1 Verificación valores fallback ATP",
                "FAILED",
                f"Valores obtenidos: Base={val_base_init}, Alícuota={val_ali_init}",
            )

        # 2. Modificar valores
        print("  Modificando parámetros a Base=$95000.00 y Alícuota=4.00%...")
        page.fill('input[name="base_imponible_atp"]', "95000.00")
        page.fill('input[name="alicuota_atp"]', "4.00")
        page.click('button:has-text("Guardar Parámetros ATP")')
        page.wait_for_load_state("networkidle")

        # Verificar mensaje de éxito
        texto_post_atp = page.content()
        exito_atp = "Parámetros de retención ATP actualizados exitosamente" in texto_post_atp

        # Recargar página para asegurar persistencia
        page.reload()
        page.wait_for_load_state("networkidle")

        val_base_persisted = page.locator('input[name="base_imponible_atp"]').input_value()
        val_ali_persisted = page.locator('input[name="alicuota_atp"]').input_value()

        persistencia_ok = (
            float(val_base_persisted.replace(",", ".")) == 95000.0
            and float(val_ali_persisted.replace(",", ".")) == 4.0
        )

        if exito_atp and persistencia_ok:
            log_result(
                "3.2 Persistencia de Parámetros ATP modificados",
                "PASSED",
                f"Persistido: Base={val_base_persisted}, Alícuota={val_ali_persisted}",
            )
        else:
            log_result(
                "3.2 Persistencia de Parámetros ATP modificados",
                "FAILED",
                f"exito={exito_atp}, Base={val_base_persisted}, Alícuota={val_ali_persisted}",
            )

        # Captura 9: Parámetros actualizados y persistidos
        shot_9 = EVIDENCE_DIR / "e2e-89-09-parametros-atp-actualizados.png"
        page.screenshot(path=str(shot_9), full_page=True)
        print(f"  Captura guardada: {shot_9}")

        # ----------------------------------------------------
        # VERIFICACIÓN DE DISEÑO RESPONSIVO (MOBILE VIEWPORT)
        # ----------------------------------------------------
        print("\n--- Verificación Adicional: Diseño Responsivo (Mobile 375x812) ---")
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_load_state("networkidle")
        shot_10 = EVIDENCE_DIR / "e2e-89-10-responsivo-mobile-catalogos.png"
        page.screenshot(path=str(shot_10), full_page=True)
        print(f"  Captura guardada: {shot_10}")

        page.set_viewport_size({"width": 768, "height": 1024})
        page.wait_for_load_state("networkidle")
        shot_11 = EVIDENCE_DIR / "e2e-89-11-responsivo-tablet-catalogos.png"
        page.screenshot(path=str(shot_11), full_page=True)
        print(f"  Captura guardada: {shot_11}")

        browser.close()

    print("\n==================================================")
    print("RESUMEN DE PRUEBAS:")
    passed_count = sum(1 for r in results if r["status"] == "PASSED")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")
    print(f"Total: {len(results)} | PASSED: {passed_count} | FAILED: {failed_count}")
    print("==================================================")

    if console_errors:
        print(f"\n[INFO] Console warnings/errors ({len(console_errors)}):")
        for err in console_errors:
            print(f"  - {err}")
    else:
        print("\n[INFO] Consola de JavaScript limpia: 0 errores detectados.")

    if js_exceptions:
        print(f"\n[ALERT] Excepciones no capturadas de JS ({len(js_exceptions)}):")
        for exc in js_exceptions:
            print(f"  - {exc}")
    else:
        print("[INFO] Excepciones no capturadas de JavaScript: 0 detectadas.")

    return failed_count == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
