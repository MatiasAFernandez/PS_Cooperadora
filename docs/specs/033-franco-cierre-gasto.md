# SPEC-033 — Seguimiento documental y cierre explícito de gasto

Fecha: 16/11/2026. Responsable principal: Franco Damián Sánchez (Gastos).
Estado: implementada en rama de tarea (`feat/136-cierre-gasto`); seguimiento en [#136](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/136).
Base: `RF-005`, `F-E08`, [SPEC-011](011-franco-seguimiento-pago-externo.md) y [SPEC-020](020-franco-doble-flujo-atp-ux.md).
**Condición de integración compartida:** incluye extensión mínima revisable en `documentos/acceso.py` y `documentos/views.py` para aplicar la guarda terminal a `Circuito.GASTO`; requiere revisión y acuerdo de interfaz con Matías antes de mergear a `main`.

## Problema, valor y límites

Una solicitud de gasto aceptada y pagada podía quedar con documentación pendiente (por ejemplo, compra directa pagada con presupuesto proforma) o sin revisión aceptada de todos sus respaldos, sin un hito explícito que verifique las condiciones documentales y registre el cierre administrativo.

Este corte incorpora el seguimiento de precondiciones documentales y el registro inmutable `CierreGasto` separado de `EstadoSolicitud` y `DecisionGasto`. No incluye reapertura de trámites cerrados, ejecución bancaria ni reglas institucionales no confirmadas.

## Reglas de negocio y precondiciones

1. **Modelo separado e inmutable (`CierreGasto`):**
   - `OneToOneField` protegido (`PROTECT`) hacia `SolicitudGasto`, con `CierreGastoQuerySet` (`update`, `bulk_update` y `delete` lanzan `IntegrityError`), `actor`, `fecha_cierre`, `observacion` opcional, `pago_version` y referencias exactas a `Documento` y `RevisionDocumento` (`ACEPTADO`) usados al cerrar (`documento_fiscal`, `revision_fiscal`, `documento_comprobante_pago`, `revision_comprobante_pago` y, si corresponde, `documento_constancia_atp`, `revision_constancia_atp`).
2. **Precondiciones obligatorias (`evaluar_requisitos_cierre`):**
   - Solicitud en estado `aceptada` con `PagoExterno` registrado y sin `CierreGasto` previo.
   - `FACTURA_PROVEEDOR` vigente (`sucesor__isnull=True`, excluyendo adjuntos de pago) con última `RevisionDocumento` en `ACEPTADO` tanto en compra directa como en reintegro; un `PRESUPUESTO_PROFORMA` o `TICKET_NO_FISCAL` nunca habilita el cierre (sin alterar la admisión de presupuesto para el pago inicial).
   - `comprobante_bancario` del pago vigente y con última revisión `ACEPTADO`.
   - Si `monto_retencion_atp > 0`: `constancia_atp` del pago vigente y con última revisión `ACEPTADO`.
3. **Permisos y visibilidad (`identidad`, `gastos`):**
   - Capacidad granular `gastos.cerrar` (grupo `demo_gastos_cierre`, habilitable opcionalmente en `preparar_identidad_demo` con `--cierre-gastos` sobre `demo_o`), combinada con visibilidad (`visible_expenses`) y permiso de lectura documental (`documentos.consultar_metadatos` o `documentos.ver_metadatos`).
   - El evento `cierre_gasto` («Cierre del trámite») y el resumen para actores sin permiso documental no exponen nombres de archivo ni IDs documentales.
4. **Serialización y snapshot de confirmación (`cerrar_solicitud_gasto`):**
   - Orden canónico de locks bajo `@transaction.atomic`: `SolicitudGasto` → `PagoExterno` → raíces de series documentales (`bloquear_serie`) ordenadas por `serie`.
   - Reevaluación bajo locks, validación de `expected_version` y `huella_cierre` (obligatorios en `POST` HTTP mediante `CerrarSolicitudGastoForm`, con `400`/`409` visible y conservando la `observacion` ingresada ante omisión o cambios concurrentes entre `GET` y `POST`) e incremento `version + 1`.
5. **Efectos posteriores y coherencia:**
   - Excluye trámites cerrados de `verificar_deuda_documental_solicitante` y `obtener_pendientes_actuales_gastos`, y muestra el chip administrativo `Cerrada` junto a `Pagada` en el detalle, la bandeja y el panel de vista rápida.
   - Bloquea con `409` rectificaciones de pago, aportes ATP posteriores y aportes documentales en `SolicitudGastoDocumentosView`, y deshabilita controles de reemplazo/revisión en el detalle.
   - Propuesta revisable con Matías: extensión de `bloquear_facturacion_abierta` (`documentos/acceso.py`) y `documento_revision` (`documentos/views.py`) a `Circuito.GASTO` con `CierreGasto`.
