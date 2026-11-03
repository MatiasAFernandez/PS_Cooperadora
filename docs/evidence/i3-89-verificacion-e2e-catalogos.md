# Informe de Verificación E2E y Evidencia Visual — Issue #89

- **Incremento:** I3 (Cierre técnico de Gastos y Pagos).
- **Issue:** [#89 — Modelos CentroCosto y ParametroOperativo con fallback determinista y gestión administrativa](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/89).
- **Rama verificada:** `feat/89-catalogos-parametros`.
- **Rol:** Lead QA Engineer & Browser Automation Specialist.
- **Fecha de ejecución:** 03/11/2026.
- **Motor de Automatización:** Playwright 1.64.1 sobre Google Chrome 156.0 (Headless & Responsive Viewports).
- **Base de Datos:** PostgreSQL 16 sobre loopback (127.0.0.1:5432).

---

## 1. Resumen Ejecutivo de la Ejecución

Se completó la verificación funcional y visual de punta a punta (End-to-End) en navegador real, abarcando navegación, control de acceso por capacidades, alta y baja lógica de catálogos y parametrización impositiva con persistencia.

| ID Caso | Escenario | Resultado | Evidencia Generada |
|---|---|---|---|
| **E2E-89-01** | Control de acceso: Botón "Catálogos y Parámetros" oculto para solicitante estándar (`demo_a`) | **PASSED** | `docs/evidence/e2e-89-01-solicitante-sin-boton.png` |
| **E2E-89-02** | Seguridad: Denegación de acceso directo URL `/gastos/catalogos/` con HTTP 403 Forbidden | **PASSED** | `docs/evidence/e2e-89-02-solicitante-403-forbidden.png` |
| **E2E-89-03** | Autorización: Botón "Catálogos y Parámetros" visible para operador de gestión (`demo_o`) | **PASSED** | `docs/evidence/e2e-89-03-operador-boton-visible.png` |
| **E2E-89-04** | Navegación e inspección inicial de `/gastos/catalogos/` | **PASSED** | `docs/evidence/e2e-89-04-pantalla-catalogos-inicial.png` |
| **E2E-89-05** | Alta de Centro de Costo (`lab-ia` / `Laboratorio de Inteligencia Artificial`) con estado Activo | **PASSED** | `docs/evidence/e2e-89-05-alta-centro-costo-exito.png` |
| **E2E-89-06** | Baja Lógica (Toggle): Transición de estado a "Inactivo" sin eliminación física de la BD | **PASSED** | `docs/evidence/e2e-89-06-toggle-baja-logica-inactivo.png` |
| **E2E-89-07** | Reactivación (Toggle): Transición de retorno a "Activo" | **PASSED** | `docs/evidence/e2e-89-07-toggle-reactivacion-activo.png` |
| **E2E-89-08** | Verificación de valores de fallback impositivo ATP ($90.000,00 y 3,50%) | **PASSED** | `docs/evidence/e2e-89-08-parametros-atp-fallback.png` |
| **E2E-89-09** | Actualización y persistencia de Parámetros ATP ($95.000,00 y 4,00%) tras recarga | **PASSED** | `docs/evidence/e2e-89-09-parametros-atp-actualizados.png` |
| **E2E-89-10** | Inspección de diseño responsivo en viewport mobile (375x812) | **PASSED** | `docs/evidence/e2e-89-10-responsivo-mobile-catalogos.png` |
| **E2E-89-11** | Inspección de diseño responsivo en viewport tablet (768x1024) | **PASSED** | `docs/evidence/e2e-89-11-responsivo-tablet-catalogos.png` |

**Resultado consolidado:** 11 / 11 verificaciones aprobadas (**100% Passed**).

---

## 2. Detalle de Pruebas por Escenario

### Escenario 1: Navegación y Control de Acceso (Seguridad)
1. **Comportamiento en UI:**
   - Se inició sesión con el usuario `demo_a` (solicitante estándar docente/investigador, con capacidades `gastos.presentar` y `gastos.consultar_propias`, sin `gastos.decidir` ni `gastos.registrar_pago`).
   - Al navegar a `http://127.0.0.1:8000/gastos/`, el encabezado de acciones presenta únicamente el botón *"Nueva Solicitud"*. El botón *"Catálogos y Parámetros"* está completamente ausente del árbol DOM.
2. **Denegación de URL directa:**
   - Se forzó la navegación directa a `http://127.0.0.1:8000/gastos/catalogos/`.
   - El middleware y la vista `GestionCatalogosView` ejecutaron `_puede_administrar_catalogos(actor)`, arrojando `PermissionDenied`, respondiendo el servidor con código **HTTP 403 Forbidden**.

### Escenario 2: Gestión de Catálogos (Operador / Directivo)
1. **Autorización y Navegación:**
   - Se inició sesión con el usuario `demo_o` (operadora de gestión con capabilities `gastos.decidir` y `gastos.registrar_pago`).
   - El botón *"Catálogos y Parámetros"* se renderiza correctamente con estilo secundario accesible `#6c757d`.
   - Al hacer clic, navega a la pantalla de administración operativa.
2. **Alta de Centro de Costo:**
   - Formulario completado con código `lab-ia`, nombre `Laboratorio de Inteligencia Artificial` y casilla `activo=True`.
   - El sistema procesó la solicitud POST `action="crear_centro"`, redirigió exitosamente mediante PRG (*Post/Redirect/Get*) y mostró el mensaje verde de confirmación: *"Centro de costo 'Laboratorio de Inteligencia Artificial' creado exitosamente."*.
   - La tabla listó la nueva fila con código `lab-ia`, nombre en negrita y badge verde `Activo`.
3. **Baja Lógica y Reactivación:**
   - Se accionó el botón *"Desactivar"*. La vista `CentroCostoToggleActivoView` invirtió el flag booleano a `False` sin eliminar la fila ni romper la integridad referencial.
   - El badge cambió a `Inactivo` (rojo) y la acción disponible pasó a *"Activar"*.
   - Al accionar *"Activar"*, el centro retornó a `Activo` sin duplicaciones.

### Escenario 3: Parametrización Impositiva Retención ATP
1. **Fallback determinista:**
   - En ausencia de registros previos en la tabla `gastos_parametrooperativo`, el servicio resolvió de forma segura los valores por defecto definidos en código: Base Imponible `$90.000,00` y Alícuota `3,50%`.
2. **Actualización y Persistencia:**
   - Se modificaron los campos a Base `$95000.00` y Alícuota `4.00%`, enviando el formulario POST con `action="actualizar_atp"`.
   - El servidor persistió las claves `ATP_BASE_IMPONIBLE` y `ATP_ALICUOTA_DEFECTO` asociando la auditoría de `modificado_por` al actor `demo_o`.
   - Se ejecutó recarga forzada de la página (`page.reload()`), confirmando la persistencia exacta de los nuevos valores.

---

## 3. Observaciones de UX/UI, Consola JS y Diseño Responsivo

1. **Inconsistencias de JavaScript:**
   - Se monitorizó en vivo la consola de Chrome (`page.on('console')`) y excepciones de página (`page.on('pageerror')`).
   - **Resultado:** **0 excepciones de JavaScript no capturadas**. No se encontraron scripts rotos ni dependencias ausentes.
2. **Ajuste Responsivo Implementado:**
   - **Diagnóstico:** Los formularios de alta y parámetros utilizaban grillas CSS inline con 2 columnas fijas (`grid-template-columns: 1fr 1fr` y `1fr 2fr`), lo cual en dispositivos móviles estrechos (<600px) reducía excesivamente el ancho de los inputs numéricos. Asimismo, tablas anchas podían generar desborde horizontal.
   - **Mejora aplicada:** Se incorporaron las clases `.catalog-form-grid-2`, `.catalog-form-grid-1-2` y el contenedor `.catalog-table-container` con media query `@media (max-width: 600px)` en `templates/gastos/gestion_catalogos.html`. En pantallas móviles, los campos se apilan fluidamente a 1 columna y la tabla cuenta con desplazamiento horizontal protegido sin romper el layout base de 800px.
   - **Comprobación:** Las capturas `e2e-89-10-responsivo-mobile-catalogos.png` y `e2e-89-11-responsivo-tablet-catalogos.png` acreditan la legibilidad y correcta disposición táctil.
3. **Mapeo de Rutas URL:**
   - Se habilitó la ruta amigable `/gastos/catalogos/` en `gastos/urls.py` apuntando a `GestionCatalogosView.as_view()` para compatibilizar la navegación directa solicitada con la ruta estándar canónica `/gastos/administracion/catalogos/`.

---

## 4. Índice de Evidencias Digitales

Todas las capturas de pantalla de alta fidelidad se encuentran alojadas en `docs/evidence/`:

- `docs/evidence/e2e-89-01-solicitante-sin-boton.png` — Listado de gastos sin botón de administración para solicitante.
- `docs/evidence/e2e-89-02-solicitante-403-forbidden.png` — HTTP 403 Forbidden ante intento de acceso no autorizado.
- `docs/evidence/e2e-89-03-operador-boton-visible.png` — Listado de gastos con botón visible para operadora/directivo.
- `docs/evidence/e2e-89-04-pantalla-catalogos-inicial.png` — Vista inicial del panel de catálogos y parámetros.
- `docs/evidence/e2e-89-05-alta-centro-costo-exito.png` — Alta de centro de costo `lab-ia` con mensaje de confirmación y badge Activo.
- `docs/evidence/e2e-89-06-toggle-baja-logica-inactivo.png` — Baja lógica confirmada con badge Inactivo y botón Activar.
- `docs/evidence/e2e-89-07-toggle-reactivacion-activo.png` — Reactivación confirmada con badge Activo.
- `docs/evidence/e2e-89-08-parametros-atp-fallback.png` — Inspección de valores fallback ($90.000,00 y 3,50%).
- `docs/evidence/e2e-89-09-parametros-atp-actualizados.png` — Valores persistidos tras recarga ($95.000,00 y 4,00%).
- `docs/evidence/e2e-89-10-responsivo-mobile-catalogos.png` — Vista adaptada a smartphone (375x812).
- `docs/evidence/e2e-89-11-responsivo-tablet-catalogos.png` — Vista adaptada a tablet (768x1024).
