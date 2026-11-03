# SPEC-019 — Doble flujo de gastos, retención ATP parametrizada, alertas preventivas y panel operativo compacto

- **Estado:** Listo para implementación (aprobado con ajustes de auditoría técnica).
- **Fecha:** 02/11/2026.
- **Responsable principal:** Franco Damián Sánchez (Gastos y Pagos).
- **Rol del compañero:** Matías Alejandro Fernández (revisión cruzada de interfaces comunes y C01).
- **Validador:** Marcos Valussi (Director Cooperadora), Elvia (Cooperadora) y Nicolás Tortosa (Tutor Técnico / Sistemas).
- **Fuentes canónicas:** [Informe Consolidado Reunión 29/10/2026](/home/fran/repos/facultad/Práctica%20Profesional%20Supervisada/informes/INFORME_REUNION_COOPERADORA_2026-10-29.md), [Transcripción Unificada](/home/fran/repos/facultad/Práctica%20Profesional%20Supervisada/temp/TRANSCRIPCION_CONSOLIDADA_REUNION_2026-10-29.md) y [Dictamen de Auditoría Gemini Argon].
- **Seguimiento operativo:** GitHub Issues #89 a #95 (Incremento I3).

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
