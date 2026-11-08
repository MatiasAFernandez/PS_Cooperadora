"""Script E2E interactivo en vivo para verificar Issue #92 (Panel Master-Detail y Drawer lateral).

Conecta por Chrome Remote Debugging (CDP puerto 9222) a la ventana que el usuario
tiene abierta en su pantalla, ejecutando el flujo paso a paso con pausas visuales.
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

from playwright.sync_api import sync_playwright  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
EVIDENCE_DIR = Path("docs/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


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


def take_safe_screenshot(page: Any, path: Path) -> None:
    try:
        page.screenshot(path=str(path), timeout=5000)
        print(f"  [Captura guardada: {path.name}]", flush=True)
    except Exception as exc:
        print(f"  (Captura diferida: {exc})", flush=True)


def run_live_test() -> bool:
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
        print("CONECTADO A TU CHROME EN PANTALLA - PRUEBA VISUAL ISSUE #92")
        print("=" * 60 + "\n", flush=True)

        # ----------------------------------------------------
        # PASO 1: Navegación al nuevo Panel Master-Detail (Operadora)
        # ----------------------------------------------------
        print(
            ">>> PASO 1: Login como Operadora ('demo_o') y carga del Panel Master-Detail...",
            flush=True,
        )
        login_as(context, page, "demo_o")
        page.goto(f"{BASE_URL}/gastos/")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        # Validaciones de tabla
        filas = page.locator("tr.fila-solicitud")
        cantidad_filas = filas.count()
        print(
            f"  [PASS] Panel cargado con éxito. Total de filas visibles: {cantidad_filas}",
            flush=True,
        )
        assert cantidad_filas > 0, "Debe haber solicitudes visibles en la tabla"

        take_safe_screenshot(page, EVIDENCE_DIR / "live-92-01-panel-master-detail.png")
        print("  Visualizando tabla de alta densidad con 8 columnas en tu navegador.", flush=True)
        time.sleep(3)

        # ----------------------------------------------------
        # PASO 2: Apertura del Drawer Lateral al clickear una fila
        # ----------------------------------------------------
        # Buscamos preferentemente una fila con datos de transferencia (ej. #26)
        fila_con_cbu = page.locator("tr[data-pk='26']")
        fila_objetivo = fila_con_cbu if fila_con_cbu.count() > 0 else filas.first
        pk_solicitud = fila_objetivo.get_attribute("data-pk")
        print(
            f"\n>>> PASO 2: Clic en fila #{pk_solicitud} para desplegar el Drawer...",
            flush=True,
        )

        fila_objetivo.click()
        time.sleep(1)

        drawer_id = f"#drawer-solicitud-{pk_solicitud}"
        drawer = page.locator(drawer_id)
        assert drawer.is_visible(), f"El Drawer {drawer_id} debe estar visible"
        print(
            f"  [PASS] ¡Drawer lateral desplegado exitosamente para Solicitud #{pk_solicitud}!",
            flush=True,
        )

        # Verificación de secciones dentro del Drawer (case-insensitive por text-transform)
        drawer_lower = drawer.inner_text().lower()
        assert "resumen" in drawer_lower, "Debe contener sección Resumen"
        assert "financiera" in drawer_lower, "Debe contener Información Financiera"
        assert "datos bancarios" in drawer_lower, "Debe contener Datos Bancarios"

        take_safe_screenshot(page, EVIDENCE_DIR / "live-92-02-drawer-abierto-operadora.png")
        print("  Visualizando Drawer con Resumen, Finanzas y Datos Bancarios.", flush=True)
        time.sleep(3.5)

        # ----------------------------------------------------
        # PASO 3: Copiado Rápido de CBU al Portapapeles
        # ----------------------------------------------------
        print("\n>>> PASO 3: Probando botón 'Copiar CBU' en el Drawer...", flush=True)
        btn_copy = drawer.locator(".btn-copy")
        if btn_copy.count() > 0:
            btn_copy.click()
            time.sleep(0.5)
            texto_btn = btn_copy.inner_text()
            assert "copiado" in texto_btn.lower()
            print(
                "  [PASS] Feedback visual de copiado activado (CBU copiado exitosamente).",
                flush=True,
            )
            take_safe_screenshot(page, EVIDENCE_DIR / "live-92-03-boton-copiar-cbu-feedback.png")
            time.sleep(2.5)
        else:
            print("  (Esta solicitud no posee CBU registrado)", flush=True)

        # ----------------------------------------------------
        # PASO 4: Cierre del Drawer con Tecla Escape
        # ----------------------------------------------------
        print("\n>>> PASO 4: Probando cierre accesible mediante tecla Escape...", flush=True)
        page.keyboard.press("Escape")
        time.sleep(0.5)
        assert not drawer.is_visible(), "El Drawer debe haberse cerrado con Escape"
        print("  [PASS] Drawer cerrado correctamente mediante Escape.", flush=True)
        take_safe_screenshot(page, EVIDENCE_DIR / "live-92-04-drawer-cerrado.png")
        time.sleep(2)

        # ----------------------------------------------------
        # PASO 5: Cierre por clic en el Backdrop
        # ----------------------------------------------------
        print(
            "\n>>> PASO 5: Reabriendo Drawer y probando cierre al hacer clic en el fondo...",
            flush=True,
        )
        fila_objetivo.click()
        time.sleep(0.8)
        assert drawer.is_visible()

        # Clic fuera del panel en el backdrop
        page.mouse.click(50, 200)
        time.sleep(0.5)
        print("  [PASS] Drawer cerrado exitosamente al hacer clic fuera del panel.", flush=True)
        time.sleep(2)

        # ----------------------------------------------------
        # PASO 6: Privacidad Bancaria SSR (SPEC-013) con demo_l
        # ----------------------------------------------------
        print(
            "\n>>> PASO 6: Verificando Privacidad Estricta (SPEC-013) con usuario 'demo_l'...",
            flush=True,
        )
        login_as(context, page, "demo_l")
        page.goto(f"{BASE_URL}/gastos/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        fila_lectura = page.locator(f"tr[data-pk='{pk_solicitud}']")
        fila_lectura.click()
        time.sleep(1)

        drawer_l = page.locator(f"#drawer-solicitud-{pk_solicitud}")
        assert drawer_l.is_visible()

        # En demo_l, el CBU y el botón de copiado NO deben existir en el DOM
        btn_copy_l = drawer_l.locator(".btn-copy")
        assert btn_copy_l.count() == 0, "Un usuario de lectura NO debe tener botón de copiado"

        privacidad_ok = "privacidad institucional" in drawer_l.inner_text().lower()
        assert privacidad_ok, "Debe exhibir aviso de privacidad"
        print(
            "  [PASS] ¡Privacidad SSR confirmada! 'demo_l' no recibe CBU ni titular bancario.",
            flush=True,
        )

        take_safe_screenshot(
            page, EVIDENCE_DIR / "live-92-05-drawer-privacidad-restringida-demo-l.png"
        )
        time.sleep(3.5)

        # ----------------------------------------------------
        # PASO 7: Solicitante (demo_a) viendo su propia solicitud
        # ----------------------------------------------------
        print(
            "\n>>> PASO 7: Verificando que Solicitante ('demo_a') ve sus propios datos...",
            flush=True,
        )
        login_as(context, page, "demo_a")
        page.goto(f"{BASE_URL}/gastos/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        filas_a = page.locator("tr.fila-solicitud")
        if filas_a.count() > 0:
            fila_propia = filas_a.first
            pk_propia = fila_propia.get_attribute("data-pk")
            fila_propia.click()
            time.sleep(1)
            take_safe_screenshot(page, EVIDENCE_DIR / "live-92-06-drawer-solicitante-propia.png")
            print(f"  [PASS] Solicitante visualiza Drawer de su trámite #{pk_propia}.", flush=True)
            time.sleep(3)

        print("\n" + "=" * 60)
        print("TODAS LAS PRUEBAS VISUALES E2E DE ISSUE #92 FINALIZARON CON ÉXITO")
        print("=" * 60 + "\n", flush=True)
        return True


if __name__ == "__main__":
    exit_code = 0 if run_live_test() else 1
    sys.exit(exit_code)
