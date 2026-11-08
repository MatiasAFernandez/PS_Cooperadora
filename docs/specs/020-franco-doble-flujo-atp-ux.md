# SPEC-020 — Doble flujo de gastos, retención ATP parametrizada, alertas preventivas y panel operativo compacto

- **Estado:** Implementada y verificada integralmente (Incremento I3 cerrado con 784 pruebas en verde, muestra determinista intacta y evidencia E2E aprobada).
- **Fecha:** 02/11/2026 (Diseño) — 03/11/2026 (Cierre y verificación de entrega).
- **Responsable principal:** Franco Damián Sánchez (Gastos y Pagos).
- **Rol del compañero:** Matías Alejandro Fernández (revisión cruzada de interfaces comunes y C01).
- **Validador:** Marcos Valussi (Director Cooperadora), Elvia (Cooperadora) y Nicolás Tortosa (Tutor Técnico / Sistemas).
- **Fuentes canónicas:** [Informe Consolidado Reunión 29/10/2026](/home/fran/repos/facultad/Práctica%20Profesional%20Supervisada/informes/INFORME_REUNION_COOPERADORA_2026-10-29.md), [Transcripción Unificada](/home/fran/repos/facultad/Práctica%20Profesional%20Supervisada/temp/TRANSCRIPCION_CONSOLIDADA_REUNION_2026-10-29.md) y [Dictamen de Auditoría Gemini Argon].
- **Seguimiento operativo:** GitHub Issues #89 a #95 (Incremento I3).

## Rediseño de la bandeja (06/11/2026)

La bandeja de la Issue #92 pasa a cuatro columnas y se apila en móvil. Conserva filtros y paginación. Los perfiles con capacidad de decidir o registrar pagos pueden abrir una vista rápida de solo lectura en escritorio desde el concepto. La acción lleva al detalle, donde se verifican los requisitos del próximo paso. Este diseño reemplaza los criterios iniciales de ocho columnas y copiado bancario en el panel. Los datos bancarios se consultan en las superficies autorizadas de SPEC-013.

---

## 1. Problema y valor

La demostración operativa del 29/10/2026 con la Asociación Cooperadora evidenció tres necesidades críticas para la viabilidad real del sistema:

1. **Doble modalidad operativa en gastos:** La oficina de Cooperadora maneja dos realidades distintas:
   - *Compra institucional directa al proveedor:* Se tramita con presupuesto previo; Cooperadora paga al comercio y el solicitante debe rendir posteriormente la factura fiscal definitiva (generando una deuda documental temporal).
   - *Reintegro de gastos menores o movilidad:* El docente/investigador solicita autorización previa estimada, gasta con fondos propios y rinde la factura/ticket a nombre de Cooperadora para que se le transfiera el reintegro.
2. **Retención impositiva de ATP provincial (Ingresos Brutos Chaco):** Cooperadora actúa como agente de retención en pagos que superan la base imponible legal (referencia actual: $90.000,00). El monto transferido por banco debe ser estrictamente el valor neto ($\text{Neto} = \text{Bruto} - \text{Retención ATP}$), debiendo vincularse la constancia de retención además del comprobante de transferencia bancaria. Hardcodear este valor en el código generaría obsolescencia inmediata ante cambios fiscales o inflación.
3. **Ergonomía visual y gestión masiva de solicitudes (UX/UI):** Cooperadora procesa semanalmente entre 20 y 30 solicitudes de transferencia y transferencias bancarias fijadas para lunes y jueves. Navegar pantallas completas con scroll vertical infinito para cada trámite genera fatiga visual y lentitud. Se requiere un panel compacto de alta densidad (Master-Detail) con previsualización rápida de comprobantes, botón de un clic para copiar CBU/alias y acciones contextuales.
4. **Política preventiva de rendición de comprobantes:** Evitar bloqueos intempestivos al personal cuando recién se efectuó una compra, reemplazándolos por advertencias visuales y margen de gracia, reservando la restricción estricta de nuevas solicitudes sólo para deudores con mora reiterada.
5. **Reportería directiva:** Marcos Valussi requiere métricas agregadas por cuatrimestre y por centro de costo.

---

## 2. Alcance

### Incluye

- **Catálogos dinámicos aislados (`gastos.CentroCosto`):** Modelo administrable por el operador para gestionar centros de costo (alta y baja lógica) sin sobreingeniería de motores de formularios ni tocar `comunes/models.py`.
- **Parámetros operativos configurables (`gastos.ParametroOperativo`):** Almacenamiento en base de datos de la base imponible de ATP ($90.000,00) y alícuota por defecto (3,5%), con lectura segura con fallback en Python para proteger `muestra_entrega.py`.
- **Tipificación de Solicitud (`tipo_flujo`):** `COMPRA_DIRECTA` vs. `REINTEGRO` en `SolicitudGasto`.
- **Evolución contable de `PagoExterno`:** Registro de `monto_bruto`, `monto_retencion_atp`, `referencia_atp`, manteniendo `importe` como el neto transferido con `CheckConstraint` SQL estricto.
- **Panel compacto Master-Detail:** Rediseño de `solicitud_list.html` con tabla densa de 8 columnas (ancho expandido a 1140px), Drawer lateral para inspección rápida, copiado seguro de CBU/alias según permisos de `SPEC-013` y acciones directas.
- **Alertas y control determinista de comprobantes pendientes:** Banners visuales de advertencia y restricción por mora reiterada con parámetros configurables en código (`DIAS_GRACIA_RENDICION_FACTURA = 15`, `MAX_TRAMITES_MORA_PERMITIDOS = 2`) y fecha de referencia inyectable para pruebas.
- **Reporte cuatrimestral:** Vista agregada de montos solicitados y erogados por cuatrimestres (C1, C2, C3) y por centro de costo, protegida por `gastos.consultar_todas`.

### No incluye

- Facturación electrónica externa o comunicación con AFIP/ATP por WebServices directos.
- Ejecución de transferencias bancarias automáticas mediante APIs de Home Banking.
- Modificación de los modelos compartidos de `comunes/` o del adaptador `identidad/` (mantiene compatibilidad con Matías).
- Modificación del contrato `documentos/c01.py` (se respetan sus tipos admitidos).

---

## 3. Requisitos verificables

Al presentar la solicitud, quien cuenta con permiso de aporte documental y visibilidad sobre el gasto puede adjuntar un respaldo inicial opcional acorde al flujo seleccionado: presupuesto o proforma en compra directa, y factura o ticket-factura en reintegro. Si no se elige archivo, la solicitud se presenta igualmente; si se seleccionó un archivo y su validación o carga falla, el error impide completar la presentación y permite corregir y reintentar en el mismo paso, manteniendo intactos los requisitos documentales del registro de pago y la autorización por documento.

- `GAST-R01 (Doble Flujo):` `SolicitudGasto` registra obligatoriamente su `tipo_flujo` (`COMPRA_DIRECTA` o `REINTEGRO`).
- `GAST-R02 (Sincronización de Centro de Costo):` Si el solicitante elige un `CentroCosto` en el alta, el campo textual `RevisionDatosTransferencia.centro_costo` se puebla automáticamente con `centro_costo.nombre` en el servidor, evitando duplicación en pantalla.
- `GAST-R03 (Contrato C01 en Reintegros):` En el flujo `REINTEGRO`, el registro de pago exige un documento verificado elegible de tipo `FACTURA_PROVEEDOR` (rotulado en UI como *"Factura o Ticket-Factura"*). No se admite pagar reintegros contra presupuestos ni proformas. En `COMPRA_DIRECTA` se admite pago contra `PRESUPUESTO_PROFORMA` o `FACTURA_PROVEEDOR`.
- `GAST-R04 (Cálculo ATP y CheckConstraint):` `PagoExterno` asegura en base de datos que `importe == monto_bruto - monto_retencion_atp`. Si no se especifica retención, `monto_retencion_atp = Decimal("0.00")` y `monto_bruto = importe`.
- `GAST-R05 (Firma Retrocompatible de Pago):` `registrar_pago_externo` mantiene compatibilidad con llamadas existentes (parámetros nuevos opcionales con defaults neutros).
- `GAST-R06 (Privacidad en Drawer):` Los datos bancarios (CBU/alias, titular, correo) y el botón de copiado rápido sólo se renderizan en el Drawer si `puede_consultar_datos_transferencia(actor, solicitud)` es verdadero.
- `GAST-R07 (Alertas y Control Determinista):` Un solicitante con compras directas pagadas que adeuden factura definitiva recibe un banner preventivo. Si acumula más de `MAX_TRAMITES_MORA_PERMITIDOS` con antigüedad mayor a `DIAS_GRACIA_RENDICION_FACTURA`, la creación de nuevas solicitudes es rechazada con `DeudaDocumentalBloqueoError`.
- `GAST-R08 (Reportería Cuatrimestral):` La vista de reporte agrupa montos por cuatrimestre del año y por centro de costo para usuarios con `gastos.consultar_todas`.

---

## 4. Reglas de negocio y estados

### Matriz de Flujos de Gasto

| Característica | Flujo A: Compra Institucional Directa (`COMPRA_DIRECTA`) | Flujo B: Reintegro de Gastos Menores (`REINTEGRO`) |
|---|---|---|
| **Respaldo inicial** | Presupuesto o Factura Proforma comercial. | Estimación previa; comprobante rendido tras el gasto. |
| **Destinatario del pago** | Cuenta bancaria del proveedor / comercio. | Cuenta bancaria del solicitante / docente. |
| **Documento para habilitar pago (C01)** | `PRESUPUESTO_PROFORMA` o `FACTURA_PROVEEDOR`. | Exclusivamente `FACTURA_PROVEEDOR` verificada. |
| **Estado post-pago** | *Pendiente de Factura Definitiva* (deuda documental). | *Saldado / Finalizado* (sin deuda documental). |
| **Acción posterior requerida** | Solicitante rinde factura fiscal oficial definitiva; Cooperadora revisa y cierra. | Ninguna; el gasto queda completamente rendido. |

### Factura definitiva y restricción por mora (GAST-R07)

Para calcular la restricción de nuevas solicitudes, una compra directa pagada deja de contar como adeudada en cuanto se guarda una factura definitiva vigente asociada al gasto. Así el solicitante puede regularizar el trámite sin depender del tiempo de revisión de Cooperadora.

| Última revisión de la versión vigente | Efecto sobre la restricción |
|---|---|
| Pendiente de revisión | La compra queda fuera del cómputo de mora mientras Cooperadora revisa la factura. |
| Aceptada | La compra sigue fuera del cómputo. |
| Observada o rechazada | La compra vuelve a contar como adeudada. La antigüedad se calcula desde la fecha del pago original. |

Al guardar una nueva versión de la factura, se evalúa esa versión desde su estado pendiente de revisión. El dictamen anterior queda en el historial de su versión. Si hay otras compras vencidas, la restricción se levanta sólo cuando el total queda dentro del límite. Este cálculo afecta la presentación de nuevas solicitudes y es independiente de la revisión documental y del estado de la cuenta.

Los 15 días y el máximo de dos compras vencidas son parámetros de demo pendientes de validación institucional.

### Regla Impositiva de Retención ATP

```
Si Monto Bruto >= Base Imponible ATP (obtenida de ParametroOperativo con fallback a $90.000,00):
   1. La interfaz resalta la advertencia de retención y sugiere:
      Retención Sugerida = Monto Bruto * (Alícuota Defecto / 100)
   2. El operador puede ajustar el monto exacto según el aplicativo de ATP.
   3. Se valida estrictamente:
      Importe Neto = Monto Bruto - Monto Retención ATP
   4. Se almacena la referencia del aplicativo ATP en referencia_atp.
Sino:
   Monto Retención ATP = 0.00
   Importe Neto = Monto Bruto
```

> **Ajuste UX/UI (05/11/2026):**
> - El aviso preventivo lee el umbral desde el dataset utilizando un parser monetario insensible a la localización (`parseMoney`), evitando errores de cálculo `NaN` cuando el valor se renderiza con formato `es-AR` (ej. `90.000,00`).
> - Al diferir la constancia ATP (`incorporar_atp_despues`), los campos de constancia y referencia se ocultan y se excluyen del payload saliente, con validación de servidor que previene combinaciones incoherentes por POST directo.
> - Cuando la retención informada iguala o supera al monto bruto, se presenta un mensaje de error inline accesible (`#rp-retencion-inline-error`) y el importe neto muestra un guion (`—`), complementando la validación del servidor.

---

## 5. Criterios de aceptación

1. **Dado** un usuario que presenta una solicitud de tipo `COMPRA_DIRECTA`, **cuando** selecciona un centro de costo del catálogo y completa datos bancarios, **entonces** la solicitud se crea con `tipo_flujo="compra_directa"` y la revisión de transferencia adopta automáticamente el nombre del centro de costo.
2. **Dado** un gasto aprobado de tipo `REINTEGRO` que sólo cuenta con un presupuesto cargado, **cuando** la operadora intenta registrar el pago externo, **entonces** el sistema no ofrece el presupuesto y deniega el pago hasta que exista una `FACTURA_PROVEEDOR` verificada.
3. **Dado** un pago de \$120.000 con retención de ATP de \$4.200, **cuando** se registra, **entonces** `monto_bruto` se persiste en 120000.00, `monto_retencion_atp` en 4200.00, e `importe` en 115800.00.
4. **Dado** un intento de forzar en base de datos un pago donde $\text{importe} \ne \text{monto\_bruto} - \text{monto\_retencion\_atp}$, **entonces** la base de datos PostgreSQL rechaza la transacción con violación de `pago_externo_identidad_neto_atp`.
5. **Dado** un usuario lector global sin permisos de pago (`demo_lectura`), **cuando** visualiza el panel de solicitudes e inspecciona el Drawer lateral, **entonces** no se renderizan el CBU, alias ni los datos bancarios del solicitante.
6. **Dado** un solicitante con 1 compra directa pagada hace 20 días sin factura definitiva, **cuando** ingresa al panel, **entonces** observa un banner preventivo amarillo pero puede seguir creando solicitudes.
7. **Dado** un solicitante con 3 compras directas pagadas hace más de 15 días sin factura definitiva, **cuando** intenta enviar una nueva solicitud, **entonces** el servidor rechaza la creación y le indica regularizar los comprobantes pendientes.
8. **Dado** un comando `python manage.py muestra_entrega crear` ejecutado sobre base vacía, **cuando** se ejecuta, **entonces** finaliza exitosamente con código 0 y conserva idénticas las huellas de verificación determinista.

---

## 6. Datos, permisos y sensibilidad

- **Aislamiento de permisos:**
  - Administración de `CentroCosto` y `ParametroOperativo`: Requiere capacidad `gastos.decidir` o `gastos.registrar_pago`. No se crean nuevas capacidades en `identidad/` para evitar alterar el adaptador de demo.
  - Reportería directiva: Requiere `gastos.consultar_todas`.
  - Acceso a datos de transferencia en el Drawer: Exige estrictamente `puede_consultar_datos_transferencia(actor, solicitud)` conforme a `SPEC-013`.
- **Sensibilidad y datos sintéticos:** Todos los centros de costo de prueba (`Laboratorio de Química`, `Grupo Cátedra ISI`, `Capacitación Externa`) y datos bancarios de fixtures son enteramente sintéticos.

---

## 7. Módulos e interfaces

- **Módulo Propietario:** `gastos/` (Franco Damián Sánchez).
- **Modelos:**
  - `gastos.models.CentroCosto`
  - `gastos.models.ParametroOperativo`
  - `gastos.models.SolicitudGasto` (evolución: `tipo_flujo`, `centro_costo`)
  - `gastos.models.PagoExterno` (evolución: `monto_bruto`, `monto_retencion_atp`, `referencia_atp`)
- **Servicios:**
  - `gastos.services.crear_solicitud_gasto`: soporte de `tipo_flujo`, `centro_costo` y control de deuda documental.
  - `gastos.services.obtener_parametro_decimal`: lectura con fallback en código.
  - `gastos.services.verificar_deuda_documental_solicitante`: evaluación determinista con fecha inyectable.
  - `gastos.payments.registrar_pago_externo`: firma compatible y validación de neto ATP.
- **Vistas y Templates:**
  - `gastos.views.SolicitudGastoListView` + `templates/gastos/solicitud_list.html`: tabla compacta (1140px), badges de flujo, drawer lateral y atajos.
  - `gastos.views.ReporteCuatrimestralGastosView` + `templates/gastos/reporte_cuatrimestral.html`: resumen directivo agregado.
  - `gastos.views.AdministracionCatalogosView` + `templates/gastos/administracion_catalogos.html`: edición de centros de costo y base ATP.

---

## 8. Estrategia de prueba y evidencia

- **Pruebas unitarias:** Modelos, check constraints de SQL, validaciones de formularios y funciones de cálculo con `pytest`.
- **Pruebas de regresión:** Ejecución completa de la suite de `gastos/` y suite de integración (`test_c04_pago_real_proyeccion.py`, `test_muestra_entrega.py`).
- **Verificación de muestra:** `python manage.py muestra_entrega crear` y `muestra_entrega verificar`.
- **Auditoría de estilo:** `ruff check .` sin observaciones.

---

## 9. Estado de Cierre y Verificación (03/11/2026)

- **Issues atómicas implementadas:**
  - Issue #89: Catálogos dinámicos (`CentroCosto`) y parámetros con fallback (`ParametroOperativo`).
  - Issue #90: Doble flujo (`COMPRA_DIRECTA` / `REINTEGRO`), sincronización con `RevisionDatosTransferencia` y contrato C01.
  - Issue #91: Cálculo de retención ATP, `CheckConstraint` SQL y firma compatible.
  - Issue #92: Panel compacto Master-Detail (1140px, Montserrat), Drawer lateral y privacidad bancaria SSR (`SPEC-013`).
  - Issue #93: Política preventiva de comprobantes adeudados (15 días de gracia) y bloqueo por mora (> 2 trámites).
  - Issue #94: Reportería directiva cuatrimestral agregada (C1, C2, C3) y por centro de costo sin producto cartesiano.
  - Issue #95: Verificación integral de regresión, determinismo de muestra de entrega y captura E2E consolidada.
- **Resultado de la Suite:** **784 pruebas en verde (0 regresiones)** en 132.77s.
- **Informe de evidencia:** [`docs/evidence/i3-95-verificacion-entrega-consolidada.md`](../evidence/i3-95-verificacion-entrega-consolidada.md).
- **Muestra sintética:** `test_muestra_entrega.py` aprobada con hashes SHA-256 inalterados.

## 10. Actualización local 04/11/2026 — registro de pago documentado

La pantalla de registro de pago se ajusta al feedback de Franco sin cambiar los
parámetros ATP configurados ni la catalogación general:

- Se retira del formulario la sugerencia automática de alícuota. La retención se
  informa en pesos; un desplegable opcional permite calcular una sugerencia
  aritmética con base y porcentaje explícitos, sin alícuota predeterminada ni
  persistencia. El importe efectivo sigue siendo el que se registra.
- El aviso de umbral se calcula sobre el bruto real, no sobre el estimado, y no
  determina por sí solo una obligación fiscal. La frontera exacta `>`/`>=` y su
  validación institucional no se modifican en este corte.
- La retención cero oculta la tarjeta ATP y muestra «No aplica» según el dato
  registrado; un valor inválido muestra «Por definir»; un valor positivo permite
  adjuntar ahora (por defecto) o incorporar después con pendiente visible.
- El comprobante bancario PDF es obligatorio en el alta. La constancia ATP es un
  documento distinto y su incorporación posterior tiene ruta y permiso propios.

Este ajuste es local y no acredita por sí solo el cierre de la Issue ni una nueva
validación con la operadora.
