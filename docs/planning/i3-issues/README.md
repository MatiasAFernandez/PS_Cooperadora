# Incremento I3 — Cierre técnico de Gastos: Doble Flujo, ATP, Catálogos y UX Compacta

- **Período de ejecución:** 03/11/2026 al 08/11/2026.
- **Responsable principal:** Franco Damián Sánchez (Gastos y Pagos).
- **Revisión de interfaces comunes:** Matías Alejandro Fernández.
- **Especificación canónica:** [SPEC-019](../../specs/019-franco-doble-flujo-atp-ux.md).
- **Base técnica inicial:** `main` en commit `0880dee` (con PR #75 y #86 integradas, suite de 601 pruebas en verde).
- **Estado metodológico:** Aprobado con ajustes por la auditoría técnica externa (Gemini Argon).

---

## 1. Visión general del incremento

El incremento I3 cierra las necesidades operativas de la Asociación Cooperadora relevadas y validadas en la demostración del 29/10/2026:
1. Convivencia formal de **Compra Institucional Directa a Proveedor** (con presupuesto previo y factura posterior) y **Reintegro** (con factura previa rendida por el solicitante).
2. Parametrización en base de datos de la **retención impositiva de ATP** (con fallback a $90.000 y alícuota de 3,5%) y cálculo estricto del monto neto bancario transferido con constancia de retención asociada.
3. Administración ligera de **Centros de Costo** sin sobreingeniería de formularios, sincronizado con los datos de transferencia.
4. Rediseño ergonómico del listado a un **panel compacto Master-Detail con Drawer lateral** para procesar 20–30 solicitudes semanales sin scroll vertical infinito y con copiado rápido de CBU/alias protegido por permisos de `SPEC-013`.
5. Política preventiva de **comprobantes adeudados** con advertencias visuales y control determinista.
6. **Reportería directiva** agregada por cuatrimestre y por centro de costo.

---

## 2. Matriz de GitHub Issues (Tareas Atómicas)

| Nro | ID Local | Título | Depende de | Esfuerzo / Prueba | Prioridad |
|---|---|---|---|---|---|
| [**#89**](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/89) | `I3-01` | `feat(gastos): modelos CentroCosto y ParametroOperativo con fallback determinista y gestión administrativa` | Ninguna (`main`) | Pruebas de modelos, helper con fallback en Python y vista administrativa protegida | MUST |
| [**#90**](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/90) | `I3-02` | `feat(gastos): soporte de doble flujo (Compra Directa vs Reintegro) y sincronización de Centro de Costo` | #89 | Pruebas de tipificación en alta, sincronización con transferencia y contrato C01 para pagos | MUST |
| [**#91**](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/91) | `I3-03` | `feat(gastos): parametrización y cálculo de retención ATP con CheckConstraint SQL y firma compatible` | #89, #90 | Pruebas de CheckConstraint con `models.F`, cálculo neto, compatibilidad de firma y guardas inmutables | MUST |
| [**#92**](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/92) | `I3-04` | `feat(gastos/ui): panel compacto Master-Detail con Drawer lateral, ancho expandido y privacidad bancaria` | #90, #91 | Pruebas de renderizado de drawer, permisos `SPEC-013`, ancho 1140px y optimización contra N+1 | MUST |
| [**#93**](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/93) | `I3-05` | `feat(gastos): política de advertencias visuales y control determinista por comprobantes adeudados` | #90 | Pruebas deterministas con fecha inyectable, banners en listado y excepción `DeudaDocumentalBloqueoError` | MUST |
| [**#94**](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/94) | `I3-06` | `feat(gastos): reportería directiva agregada por cuatrimestre y centro de costo` | #89, #90 | Pruebas de agregación ORM por cuatrimestre (C1, C2, C3) y autorización con `gastos.consultar_todas` | MUST |
| [**#95**](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/95) | `I3-07` | `chore(gastos): verificación integral, regresión suite completa (>650 tests) y entrega I3` | #89 a #94 | Ejecución de suite completa, `muestra_entrega crear/verificar`, `ruff check` y actualización de docs | MUST |

---

## 3. Detalle de Issues y Criterios de Cierre

### Issue #89 — Modelos CentroCosto y ParametroOperativo con fallback determinista (`feat/89-catalogos-parametros`)

- **Objetivo:** Definir en `gastos/models.py` (aislado de `comunes/` y SPEC-014) los modelos `CentroCosto` y `ParametroOperativo`.
- **Ajustes de auditoría:**
  - `CentroCosto(codigo, nombre, activo)`: Soporte para alta y baja lógica.
  - `ParametroOperativo(clave, valor_decimal, valor_texto, descripcion, modificado_por, fecha_modificacion)` con `modificado_por` opcional (`null=True, blank=True`).
  - Helper `obtener_parametro_decimal(clave, default)` en `gastos/services.py` con fallback a $90.000,00 y 3,5% sin ejecutar `RunPython` en la migración SQL para no romper `muestra_entrega`.
  - Vista de edición protegida con capacidades existentes `gastos.decidir` o `gastos.registrar_pago`.
- **Criterio de cierre:** Pruebas unitarias de creación, fallback de parámetros sin filas en BD, baja lógica de centros de costo y denegación de edición a usuarios sin permisos.

### Issue #90 — Soporte de doble flujo y sincronización de Centro de Costo (`feat/90-doble-flujo-gastos`)

- **Objetivo:** Agregar `tipo_flujo` (`COMPRA_DIRECTA` / `REINTEGRO`) y `centro_costo` en `SolicitudGasto`.
- **Ajustes de auditoría:**
  - Al seleccionar un `CentroCosto` en el alta, el servidor asigna automáticamente `RevisionDatosTransferencia.centro_costo = centro_costo.nombre`.
  - En `REINTEGRO`, el servicio de pago exige `tipos_admitidos=("factura",)` sobre `FACTURA_PROVEEDOR` (rotulado en UI como *"Factura o Ticket-Factura de proveedor"*). No usar `TICKET_NO_FISCAL` para respetar el contrato de `documentos/c01.py`.
- **Criterio de cierre:** Pruebas de alta de solicitud con cada flujo, persistencia atómica, sincronización automática de nombre de centro de costo y rechazo de pago de reintegros con proformas/presupuestos.

### Issue #91 — Parametrización y cálculo de retención ATP (`feat/91-retencion-atp-pagos`)

- **Objetivo:** Extender `PagoExterno` con `monto_bruto`, `monto_retencion_atp`, `referencia_atp`, manteniendo `importe` como neto.
- **Ajustes de auditoría:**
  - CheckConstraint SQL con `models.F`: `importe = monto_bruto - monto_retencion_atp`.
  - No agregar ForeignKey directa a `Documento` para constancia de retención ATP; registrar `referencia_atp` de tipo texto e incorporar el archivo mediante el servicio documental estándar.
  - Firma retrocompatible en `registrar_pago_externo`: `monto_bruto: Any = None, monto_retencion_atp: Any = Decimal("0.00"), referencia_atp: Any = ""`. Si `monto_bruto is None`, asignar `monto_bruto = valid_importe` y `monto_retencion_atp = Decimal("0.00")`.
  - Actualizar guardas de inmutabilidad en el queryset de `PagoExterno`.
- **Criterio de cierre:** Pruebas de constraint en PostgreSQL, cálculo automático de retención sugerida en formulario, validación de discrepancia y compatibilidad con los tests previos de pago.

### Issue #92 — Panel compacto Master-Detail y Drawer lateral (`feat/92-panel-compacto-ui`)

- **Objetivo:** Rediseñar `solicitud_list.html` a una vista compacta de alta densidad con Drawer lateral de inspección rápida.
- **Ajustes de auditoría:**
  - En el Drawer, renderizar CBU/alias y botón de copiado rápido al portapapeles **únicamente si** `puede_consultar_datos_transferencia(actor, solicitud)` es `True` (`SPEC-013`).
  - Elevar el ancho del contenedor en la lista a `max-width: 1140px` (o contenedor fluido) para dar cabida a las 8 columnas.
  - Queryset optimizado con `select_related("centro_costo", "pago_externo")` y paginación a 25 registros para evitar N+1.
- **Criterio de cierre:** Pruebas de vistas verificando conteo de queries SQL, presencia/ausencia de datos bancarios según perfil, y funcionamiento del Drawer.

### Issue #93 — Alertas preventivas y control determinista de deuda (`feat/93-alertas-deuda-documental`)

- **Objetivo:** Implementar avisos visuales al solicitante por compras directas pagadas que adeuden factura definitiva.
- **Ajustes de auditoría:**
  - Parámetros en código: `DIAS_GRACIA_RENDICION_FACTURA = 15` y `MAX_TRAMITES_MORA_PERMITIDOS = 2`.
  - Inyección de `fecha_referencia: date | None = None` en el servicio evaluador para pruebas unitarias deterministas independientes del reloj del sistema.
  - Si un usuario supera el umbral de mora, `crear_solicitud_gasto` lanza `DeudaDocumentalBloqueoError` en el servidor.
- **Criterio de cierre:** Pruebas unitarias con fechas simuladas: solicitante con 1 trámite reciente (muestra banner, permite alta); solicitante con 3 trámites vencidos (muestra banner de advertencia grave y bloquea alta).

### Issue #94 — Reportería directiva cuatrimestral y por centro de costo (`feat/94-reporteria-cuatrimestral`)

- **Objetivo:** Crear vista de agregación directiva de montos solicitados y erogados.
- **Ajustes de auditoría:**
  - Agrupación por los 3 cuatrimestres del año calendario (C1: Ene–Abr, C2: May–Ago, C3: Sep–Dic).
  - Agrupación por `CentroCosto` con fila de respaldo para "Sin centro asignado / Histórico".
  - Desglose de erogaciones: Bruto, Retenciones ATP y Neto transferido.
  - Protección de acceso mediante `has_capability(actor, "gastos.consultar_todas")`.
- **Criterio de cierre:** Pruebas de consulta agregada con fixtures sintéticas de múltiples cuatrimestres y centros, verificando totales exactos y denegación a usuarios no autorizados.

### Issue #95 — Verificación integral, regresión y entrega (`chore/95-verificacion-entrega-i3`)

- **Objetivo:** Consolidar la entrega final con suite completa y actualización de evidencia.
- **Criterio de cierre:**
  - Ejecución de la suite completa de pruebas: `pytest` superando 650 pruebas en verde.
  - `python manage.py check` y `python manage.py makemigrations --check --dry-run` limpios.
  - `ruff check .` aprobado.
  - Ejecución exitosa de `python manage.py muestra_entrega crear` y `muestra_entrega verificar` sin fallos de hash.
  - Actualización de `docs/evidence/` y guía reproducible.

---

## 4. Cronograma de ramas y entregas (03/11 al 08/11/2026)

| Día | Ramas / Tareas | Hito alcanzado |
|---|---|---|
| **Lunes 03/11** | `feat/89-catalogos-parametros`<br/>`feat/90-doble-flujo-gastos` | Catálogos dinámicos, parámetros con fallback y tipificación de flujo en solicitudes. |
| **Martes 04/11** | `feat/91-retencion-atp-pagos` | Deducción de ATP en servidor, CheckConstraint SQL y firma retrocompatible. |
| **Miércoles 05/11** | `feat/92-panel-compacto-ui` | Listado compacto Master-Detail, Drawer lateral y copiado rápido de CBU seguro. |
| **Jueves 06/11** | `feat/93-alertas-deuda-documental`<br/>`feat/94-reporteria-cuatrimestral` | Alertas preventivas deterministas y dashboard de reporte cuatrimestral. |
| **Viernes 07/11** | `chore/95-verificacion-entrega-i3` | Suite de regresión completa (>650 tests), validación de `muestra_entrega` y merge a `main`. |
| **Sábado 08/11** | Congelamiento de código y entrega | Emisión de informe final para la carpeta académica de PPS. |
