# Informe de Verificación E2E y Evidencia Visual — Issue #90

- **Módulo:** Gastos y Pagos (`gastos/`)
- **Incremento verificado:** Soporte de doble flujo (Compra Directa vs Reintegro) y sincronización de Centro de Costo (Issue #90)
- **Fecha:** 03 de noviembre de 2026
- **Responsable:** Franco Damián Sánchez (Rol: Lead QA Engineer & Browser Automation Specialist)
- **Entorno:** Local (Django 5.2.17, PostgreSQL 16, Google Chrome via CDP / Playwright)
- **Estado de verificación:** **Aprobado sin observaciones materiales**

---

## 1. Resumen Ejecutivo de la Verificación

Se realizó la verificación funcional y visual de punta a punta (E2E) interactiva y automatizada sobre el navegador Google Chrome. Las pruebas recorrieron el ciclo de vida completo de las solicitudes de gasto bajo las modalidades **Reintegro** y **Compra Directa**, validando los controles de acceso por capacidades, las reglas contractuales y la persistencia en base de datos.

### Matriz de Resultados

| ID | Criterio / Requerimiento | Descripción | Resultado | Evidencia |
|---|---|---|:---:|---|
| **E2E-90-01** | `GAST-R01` | Selector de modalidad (`COMPRA_DIRECTA` / `REINTEGRO`) visible y funcional en `/gastos/presentar/`. | **PASS** | [`e2e-90-01-alta-reintegro-form.png`](./e2e-90-01-alta-reintegro-form.png) |
| **E2E-90-02** | Catálogo Dinámico | Filtrado estricto de centros de costo activos en el selector (los centros inactivos no se ofrecen). | **PASS** | [`e2e-90-01-alta-reintegro-form.png`](./e2e-90-01-alta-reintegro-form.png) |
| **E2E-90-03** | `GAST-R02` | Auto-sincronización en servidor del `CentroCosto` institucional hacia `RevisionDatosTransferencia.centro_costo` cuando el solicitante lo omite. | **PASS** | [`e2e-90-02-detalle-reintegro-sincronizado.png`](./e2e-90-02-detalle-reintegro-sincronizado.png) |
| **E2E-90-04** | Valor Explícito | Si el solicitante ingresa manualmente un centro de costo en datos de transferencia, se preserva su texto literal sin sobreescribirlo. | **PASS** | [`e2e-90-04-detalle-compra-directa.png`](./e2e-90-04-detalle-compra-directa.png) |
| **E2E-90-05** | Decisión Directiva | Transición de estado a "Aceptada" por operadora con registro de motivo auditable y versión de concurrencia. | **PASS** | [`e2e-90-05-decision-operadora.png`](./e2e-90-05-decision-operadora.png) |
| **E2E-90-06** | `GAST-R03` | En flujo **Reintegro**, el registro de pago exige exclusivamente `FACTURA_PROVEEDOR`, excluyendo presupuestos y proformas. | **PASS** | [`e2e-90-06-pago-reintegro-factura-exigida.png`](./e2e-90-06-pago-reintegro-factura-exigida.png) |
| **E2E-90-07** | Flujo Compra Directa | En flujo **Compra Directa**, el registro de pago admite tanto facturas como presupuestos o proformas vigentes. | **PASS** | [`e2e-90-07-pago-compra-directa-ambas-opciones.png`](./e2e-90-07-pago-compra-directa-ambas-opciones.png) |
| **E2E-90-08** | Responsividad Mobile | Adaptabilidad en viewport móvil (375x812, iPhone 13) sin desbordes horizontales ni solapamientos. | **PASS** | [`e2e-90-08-responsivo-alta-mobile.png`](./e2e-90-08-responsivo-alta-mobile.png) |
| **E2E-90-09** | Responsividad Tablet | Vista estructurada en tablet (768x1024, iPad) con paneles y cronología legibles. | **PASS** | [`e2e-90-09-responsivo-detalle-tablet.png`](./e2e-90-09-responsivo-detalle-tablet.png) |
| **E2E-90-10** | Calidad de Consola | Cero excepciones de JavaScript y cero errores no controlados durante todo el ciclo de navegación. | **PASS** | Consola limpia en ejecución E2E |

---

## 2. Detalle de los Recorridos de Prueba

### Escenario 1: Alta de Reintegro y Sincronización Automática (`GAST-R01`, `GAST-R02`)
1. **Actor:** `demo_a` (Solicitante estándar con capacidades `gastos.presentar`, `gastos.consultar_propias`).
2. **Acción:** Navega a `/gastos/presentar/`.
3. **Comprobación de Catálogos:**
   - Selector "Modalidad de Gasto": ofrece "Compra directa a proveedor" y "Reintegro a solicitante".
   - Selector "Centro de Costo": expone centros activos (`Laboratorio de Inteligencia Artificial`, `Laboratorio de Química`) y excluye `Proyecto Cerrado 2024`.
4. **Carga:** Se selecciona modalidad `REINTEGRO` y centro `Laboratorio de Inteligencia Artificial (lab-ia)`. En el bloque opcional de datos de transferencia se completan titular, CBU, correo e identificación, dejando el campo de texto "Centro de costo informado" **vacío deliberadamente**.
5. **Verificación en Detalle (`/gastos/<id>/`):**
   - La cabecera muestra el badge "Reintegro a solicitante".
   - El panel de transferencia expone `Centro de costo informado: Laboratorio de Inteligencia Artificial`, confirmando la auto-sincronización en servidor (`GAST-R02`).

### Escenario 2: Alta de Compra Directa y Preservación de Valor Explícito
1. **Actor:** `demo_a` (Solicitante).
2. **Acción:** Presenta solicitud con modalidad `COMPRA_DIRECTA`.
3. **Carga:** Se selecciona centro institucional `Laboratorio de Inteligencia Artificial` y se ingresa en transferencia el valor explícito `Subdirección de Infraestructura Tecnológica`.
4. **Verificación en Detalle:**
   - La modalidad se renderiza como "Compra directa a proveedor".
   - El centro de costo informado en transferencia conserva exactamente `Subdirección de Infraestructura Tecnológica`, demostrando que los valores manuales no son sobreescritos.

### Escenario 3: Restricción Contractual C01 en Pagos (`GAST-R03`)
1. **Actor:** `demo_o` (Operadora con capacidades `gastos.decidir`, `gastos.registrar_pago`, `documentos.ver_metadatos`).
2. **Aprobación:** Accede al detalle de ambas solicitudes y registra la decisión de aceptación con motivo justificado.
3. **Aporte Documental:** Se incorporan sintéticamente a cada solicitud una factura de proveedor (`FACTURA_PROVEEDOR`) y un presupuesto (`PRESUPUESTO_PROFORMA`).
4. **Verificación en Pago de Reintegro (`/gastos/<id_reintegro>/pagar/`):**
   - El selector `referencia_documental` **únicamente** ofrece la opción `Factura de proveedor` (rotulada bajo el contrato C01).
   - El presupuesto es estrictamente filtrado y no aparece como opción seleccionable (`GAST-R03`).
5. **Verificación en Pago de Compra Directa (`/gastos/<id_directa>/pagar/`):**
   - El selector ofrece tanto `Factura de proveedor` como `Presupuesto o proforma`, permitiendo la prosecución del pago con cualquiera de ambos comprobantes comerciales.

### Escenario 4: Auditoría Visual y Consola
- **Mobile (375x812):** Formulario de presentación adaptable con espaciados táctiles accesibles.
- **Tablet (768x1024):** Paneles de detalle y tablas de historial alineadas.
- **Consola:** Cero excepciones runtime no controladas.

---

## 3. Registro de Hallazgo Técnico y Corrección Implementada

Durante la ejecución inicial con navegador real se detectó un caso de desambiguación en el formulario de presentación `/gastos/presentar/`:
- **Causa:** Tanto el formulario de la solicitud (`SolicitudGastoForm`) como el subformulario opcional (`DatosTransferenciaForm`) definen un campo denominado `centro_costo`. Al ser renderizados en el mismo formulario HTML, el navegador enviaba dos parámetros con la misma clave en `request.POST`.
- **Efecto:** En peticiones enviadas por navegador real, `request.POST.get("centro_costo")` tomaba el último valor (el campo de texto de transferencia, que podía ser una cadena vacía o texto libre), ignorando el identificador numérico seleccionado en el `<select>`.
- **Solución implementada en `gastos/views.py` (`SolicitudGastoCreateView`):** Se incorporó la desambiguación mediante `request.POST.getlist("centro_costo")`, asignando el primer elemento al modelo de solicitud (`centro_costo_id`) y el segundo elemento al formulario de transferencia (`texto_transferencia`).
- **Validación:** Se ejecutó la suite de pruebas unitarias (`tests/gastos/test_doble_flujo.py` y `tests/gastos/test_catalogos_parametros.py`), verificando que los **31 tests unitarios pasan exitosamente (100%)** y que la prueba E2E de navegador real concluye con resultado positivo.

---

## 4. Archivos de Evidencia Gráfica Generados

1. `e2e-90-01-alta-reintegro-form.png` — Formulario de presentación con modalidad Reintegro y centros activos.
2. `e2e-90-02-detalle-reintegro-sincronizado.png` — Vista de detalle con badge Reintegro y centro auto-sincronizado.
3. `e2e-90-03-alta-compra-directa-form.png` — Formulario de Compra Directa con centro explícito.
4. `e2e-90-04-detalle-compra-directa.png` — Vista de detalle de Compra Directa con preservación de texto explícito.
5. `e2e-90-05-decision-operadora.png` — Formulario de decisión directiva de operadora `demo_o`.
6. `e2e-90-06-pago-reintegro-factura-exigida.png` — Formulario de pago en Reintegro mostrando exclusión estricta de presupuestos (solo factura).
7. `e2e-90-07-pago-compra-directa-ambas-opciones.png` — Formulario de pago en Compra Directa con admisión de factura y presupuesto.
8. `e2e-90-08-responsivo-alta-mobile.png` — Formulario responsivo en viewport 375x812 (Mobile).
9. `e2e-90-09-responsivo-detalle-tablet.png` — Detalle responsivo en viewport 768x1024 (Tablet).
