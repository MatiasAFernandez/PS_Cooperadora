# SPEC-032 — Observación y subsanación de solicitudes de gasto

Fecha: 15/11/2026. Responsable principal: Franco Damián Sánchez (Gastos).
Estado: integrada en `main` mediante PR #135; seguimiento en [#134](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/134).
Base: `RF-003`, `F-E06`, [SPEC-020](020-franco-doble-flujo-atp-ux.md) y [SPEC-030](030-franco-avisos-decision-gastos.md).
No modifica Facturación, pagos externos, cierre de trámite (`F-E08`) ni reglas institucionales pendientes (`Q1`–`Q5`).

## Problema, valor y límites
La evaluación de gastos admitía aceptar, postergar o rechazar una solicitud, pero carecía de una instancia explícita de **observación** que permitiera al titular subsanar datos básicos de la solicitud y reenviarla a evaluación con trazabilidad completa.

Este tramo incorpora la acción `observar` (separada de `postergar`) y la subsanación controlada por el titular, conservando inmutables la modalidad (`tipo_flujo`), la identidad del trámite, el titular, la unidad requirente y los registros históricos. No habilita pagos, cierre administrativo ni reapertura de trámites aceptados o rechazados.

## Transiciones y reglas de negocio
1. `EstadoSolicitud` incorpora `OBSERVADA = "observada", "Observada"`.
2. **Evaluación (`can_decide_expense`, `validate_decision_content`, `decide_expense`, capacidad `gastos.decidir`):**
   - Desde `presentada`: admite `aceptar`, `observar`, `postergar` y `rechazar`.
   - Desde `postergada`: admite `aceptar`, `observar` y `rechazar`.
   - `observar` exige `motivo` no vacío y sin `NUL`, registra `DecisionGasto` y programa el aviso de decisión al titular (`Observada`).
   - En estado `observada` no se permiten decisiones de operador hasta el reenvío del titular.
3. **Subsanación (`puede_corregir_solicitud`, `corregir_solicitud_gasto`, capacidad `gastos.presentar` + titularidad):**
   - Orden de guardas: visibilidad (`404`) → titularidad y `gastos.presentar` (`403`) → estado `observada`, ausencia de `PagoExterno` y última `DecisionGasto` en `observada` sin subsanación (`409` en `POST`; redirección informativa en `GET`) → validación de entrada (`400`) → `expected_version` (`409`).
   - Campos editables mínimos: `concepto`, `monto_estimado` (`> 0`) y `centro_costo` activo opcional o el ya asignado (sincronizando `TramiteBase.centro_costo_codigo` en la misma transacción, sin fabricar revisiones artificiales de transferencia).
   - Registra un hecho inmutable `SubsanacionGasto` (con `SubsanacionGastoQuerySet` bloqueando `update`/`bulk_update`/`delete`, `OneToOneField` `PROTECT` a `DecisionGasto` y `CheckConstraint`s SQL) integrado en la cronología común (`como_historial()`, `tipo_evento="subsanacion_gasto"`).

## Avisos, interfaz y verificación
- Los avisos web y por correo de decisión existentes representan el estado `Observada` mediante `get_estado_resultante_display()`.
- La subsanación reintegra la solicitud al filtro `Pendiente de decisión`; no emite `nueva_solicitud_gasto` ni agrega un tipo de aviso nuevo en este corte.
- El detalle (`solicitud_detail.html`) y la bandeja (`_bandeja_fila.html`) incorporan chip/motivo/pendiente `Observada`, el botón `Observar` para operadores, la acción **Corregir solicitud** para el titular habilitado (o aviso explícito si carece de `gastos.presentar`) y la priorización del `centro_costo` vigente en `pago_form.html` e inline de transferencia.
- La vista `<int:pk>/corregir/` (`solicitud_corregir_form.html`) reutiliza la guía visual vigente (escritorio y móvil, sin SPA), conservando valores ante `400` y `409`.
