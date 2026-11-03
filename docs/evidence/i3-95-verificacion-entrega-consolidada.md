# Informe de Verificación Integral y Evidencia Consolidada — Incremento I3

- **Incremento:** I3 — Cierre técnico de Gastos: Doble Flujo, ATP, Catálogos, Alertas y UX Compacta.
- **Issue de Cierre:** [#95 — Verificación integral, regresión suite completa (>650 tests) y entrega I3](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/95).
- **Rama de Cierre:** `chore/95-verificacion-entrega-i3` → `main`.
- **Responsable:** Franco Damián Sánchez (Gastos y Pagos).
- **Revisión de Contratos y Arquitectura:** Matías Alejandro Fernández / Gemini Argon.
- **Fecha de Verificación:** 03 de Noviembre de 2026.
- **Entorno de Verificación:** Linux Kali / Python 3.14.6 / Django 5.2.17 / PostgreSQL 18.6 / Playwright 1.50.0 sobre Chromium 150.0.
- **Estado de la Suite:** **784 passed in 132.77s (100% verde)**, `ruff check .` limpio, `muestra_entrega.py` determinista aprobada (3/3 passed).

---

## 1. Resumen Ejecutivo del Incremento I3

El Incremento I3 consolida todas las necesidades operativas, contables y ergonómicas detectadas en la demostración del 29/10/2026 con las autoridades de la Asociación Cooperadora de la UTN Facultad Regional Resistencia (Marcos Valussi y Elvia). 

A través de 7 GitHub Issues atómicas (#89 a #95), se alcanzaron los siguientes hitos:
1. **Catálogos dinámicos y parámetros operativos con fallback (#89):** Modelos `CentroCosto` y `ParametroOperativo` administrables por el personal operativo sin tocar modelos compartidos y garantizando continuidad con fallback en código en ausencia de registros.
2. **Doble flujo operativo (#90):** Distinción formal e inmutable entre *Compra Institucional Directa a Proveedor* (`COMPRA_DIRECTA`) y *Reintegro de Gastos Menores* (`REINTEGRO`), con sincronización automática de Centro de Costo hacia `RevisionDatosTransferencia` y restricción contractual C01 en reintegros (exclusivamente `FACTURA_PROVEEDOR`).
3. **Parametrización y cálculo de Retención ATP Chaco (#91):** Deducción impositiva en servidor con CheckConstraint SQL de base de datos ($\text{Neto} = \text{Bruto} - \text{Retención ATP}$), alícuotas sugeridas por base imponible y firma retrocompatible para pagos externos.
4. **Rediseño visual ergonómico de alta densidad (#92):** Listado expandido a 1140px con 8 columnas, tipografía Montserrat, Drawer lateral para inspección rápida en menos de un clic, copiado de CBU/alias con feedback visual y **privacidad estricta en servidor (SSR)** según `SPEC-013`.
5. **Política preventiva y control determinista de comprobantes adeudados (#93):** Banners preventivos de aviso con 15 días de margen de gracia y bloqueo estricto de nuevas solicitudes para solicitantes con mora reiterada (> 2 trámites vencidos) mediante `DeudaDocumentalBloqueoError`.
6. **Reportería directiva agregada (#94):** Dashboard ejecutivo cuatrimestral (C1, C2, C3) y por centro de costo institucional, garantizando agregación contable exacta sin duplicaciones por producto cartesiano en JOINs SQL y protegido por `gastos.consultar_todas`.
7. **Verificación integral y congelamiento (#95):** Regresión completa de 784 pruebas en verde, verificación de muestra de entrega sin alteración de hashes SHA-256 y evidencia visual E2E en navegador real.

---

## 2. Matriz de Cobertura de Requisitos SPEC-020

| Regla Canónica | Descripción | Issue | Componente Técnico | Estado |
|---|---|---|---|---|
| **GAST-R01** | Modalidad de Gasto tipificada (`COMPRA_DIRECTA` / `REINTEGRO`) | #90 | `SolicitudGasto.tipo_flujo`, selector en alta y badges en UI | **CUMPLIDO** |
| **GAST-R02** | Sincronización automática de Centro de Costo hacia transferencia | #90 | `RevisionDatosTransferencia.centro_costo = centro_costo.nombre` | **CUMPLIDO** |
| **GAST-R03** | Restricción C01 para Reintegros (sólo `FACTURA_PROVEEDOR`) | #90 | `tipos_documento_admitidos_para_flujo()`, `c01.py` y selector GET/POST | **CUMPLIDO** |
| **GAST-R04** | Deducción ATP y CheckConstraint SQL ($\text{Neto} = \text{Bruto} - \text{Retención}$) | #91 | `CheckConstraint(pago_externo_identidad_neto_atp)` en `PagoExterno` | **CUMPLIDO** |
| **GAST-R05** | Firma retrocompatible de `registrar_pago_externo` | #91 | Argumentos opcionales `monto_bruto`, `monto_retencion_atp`, `referencia_atp` | **CUMPLIDO** |
| **GAST-R06** | Privacidad SSR en Drawer lateral según `SPEC-013` | #92 | `puede_consultar_datos_transferencia(actor, solicitud)`, copiado rápido | **CUMPLIDO** |
| **GAST-R07** | Banners preventivos y bloqueo por mora documental (> 15 días, > 2 trámites) | #93 | `verificar_deuda_documental_solicitante()`, `DeudaDocumentalBloqueoError` | **CUMPLIDO** |
| **GAST-R08** | Reportería directiva agregada por cuatrimestre y centro de costo | #94 | `gastos.reports.obtener_reporte_cuatrimestral_gastos`, vista protegida | **CUMPLIDO** |

---

## 3. Registro Consolidado de Pruebas E2E y Evidencia Visual

Se ejecutaron pruebas automatizadas sobre navegador Chromium real (Playwright 1.50.0 / Headless 1280x900 con escala 1.5x) para validar visual y funcionalmente el comportamiento de las pantallas y micro-interacciones.

| ID Caso | Escenario Evaluado | Issue | Resultado | Evidencia Visual Generada |
|---|---|---|---|---|
| **E2E-89-01 a 11** | Alta, baja lógica y toggle de Centros de Costo; persistencia de parámetros ATP | #89 | **PASSED** (11/11) | `docs/evidence/e2e-89-01` a `e2e-89-11` |
| **E2E-90-01 a 09** | Alta con doble flujo, sincronización de centro y pago de reintegro exigiendo factura | #90 | **PASSED** (9/9) | `docs/evidence/e2e-90-01` a `e2e-90-09` |
| **E2E-91-01** | Formulario de pago con retención ATP sugerida y cálculo reactivo en cliente | #91 | **PASSED** | `docs/evidence/e2e-91-01-pago-retencion-atp-form.png` |
| **E2E-91-02** | Detalle de solicitud pagada con desglose contable (Bruto, Retención ATP, Neto) | #91 | **PASSED** | `docs/evidence/e2e-91-02-detalle-gasto-pagado-atp.png` |
| **E2E-92-01** | Listado de alta densidad (1140px, Montserrat) y apertura fluida de Drawer lateral | #92 | **PASSED** | `docs/evidence/e2e-92-01-panel-compacto-drawer-abierto.png` |
| **E2E-92-02** | Privacidad SSR en Drawer: Ocultamiento estricto de CBU para usuarios no autorizados | #92 | **PASSED** | `docs/evidence/e2e-92-02-privacidad-cbu-drawer.png` |
| **E2E-93-01** | Banner preventivo amarillo para solicitante con trámite en período de gracia (5 días) | #93 | **PASSED** | `docs/evidence/e2e-93-01-alerta-deuda-documental-banner.png` |
| **E2E-93-02** | Banner crítico rojo y bloqueo de formulario de alta por acumulación de mora (> 2 trámites) | #93 | **PASSED** | `docs/evidence/e2e-93-02-bloqueo-alta-por-deuda.png` |
| **E2E-94-01** | Dashboard directivo con 4 tarjetas KPI y tabla cuatrimestral (C1, C2, C3) con `.font-tabular` | #94 | **PASSED** | `docs/evidence/e2e-94-01-reporte-cuatrimestral-kpis.png` |
| **E2E-94-02** | Desglose por Centro de Costo institucional y fila de respaldo histórico | #94 | **PASSED** | `docs/evidence/e2e-94-02-reporte-desglose-centros-costo.png` |
| **E2E-94-03** | Control de acceso: Denegación de reporte directivo a solicitante común (HTTP 403) | #94 | **PASSED** | Validado en suite E2E |

**Total de verificaciones visuales y de interacción:** **29 / 29 pruebas aprobadas (100% Passed)**, con 0 excepciones no controladas de JavaScript.

---

## 4. Verificación de Regresión Completa y Calidad de Código

### 4.1. Suite Automatizada de Pruebas (`pytest`)
- **Total de pruebas ejecutadas:** **784 pruebas**.
- **Tiempo de ejecución:** 132.77 segundos.
- **Resultado:** **784 passed, 0 failed, 0 skipped, 0 warnings**.
- **Distribución de pruebas:**
  - Facturación y cobros: 183 pruebas.
  - Gastos, flujos, ATP y reportería: 375 pruebas.
  - Identidad y documentos: 124 pruebas.
  - Integración y contratos cruzados: 102 pruebas.

### 4.2. Verificación de Muestra Determinista (`muestra_entrega.py`)
- Comando ejecutado: `python -m pytest tests/integracion/test_muestra_entrega.py -v`
- Casos verificados:
  - `test_muestra_verifica_hechos_y_detecta_bytes_alterados`: PASSED.
  - `test_muestra_no_crea_en_demo_deshabilitada`: PASSED.
  - `test_muestra_no_agrega_datos_a_base_con_usuarios`: PASSED.
- **Huellas SHA-256:** Preservadas idénticas para comunes, documentos, facturación y gastos.

### 4.3. Verificación de Linter y Estilo (`ruff`)
- Comando ejecutado: `.venv/bin/ruff check .`
- **Resultado:** `All checks passed!` (cero observaciones de estilo o imports).

### 4.4. Integridad de Modelos y Migraciones (`manage.py`)
- `python manage.py check`: `System check identified no issues (0 silenced)`.
- `python manage.py makemigrations --check --dry-run`: `No changes detected` (árbol de migraciones 100% sincronizado con PostgreSQL).

---

## 5. Conclusión y Dictamen de Entrega del Incremento I3

El Incremento I3 cumple íntegramente con los requisitos funcionales, impositivos, contables y visuales comprometidos en [SPEC-020](../specs/020-franco-doble-flujo-atp-ux.md), respetando de forma irrestricta los límites modulares del sistema y las directrices de Calidad 2026.

El código se encuentra consolidado y listo para congelamiento y presentación formal en la carpeta académica de la Práctica Profesional Supervisada (PPS).
