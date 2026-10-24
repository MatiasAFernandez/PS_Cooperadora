# I2-50 — evidencia focal de UI de gastos, 21/10/2026

**Corte de código:** `53d90f872aede1a15836dc87bb79e804129b50b7`, rama `feat/50-aporte-reemplazo-respaldo`, basada en el HEAD de PR #65 (`ffd0e9a618577133043eaed704ee9fa151150ad3`). Este corte local aún no está integrado.

Esta ficha consolida dos recorridos focales de UI normal con datos sintéticos. No es la matriz completa GP-01–06 ni declara completa #50, I2 o la integración de ambos circuitos.

## Validaciones previas reutilizadas

- Antes de los recorridos manuales, pasaron 25 pruebas focalizadas sobre PostgreSQL 17.11 y Ruff sobre el código del corte `53d90f8`.
- Validación focalizada repetida el 21/10/2026: `python -m pytest tests/gastos/test_models.py tests/gastos/test_respaldo_h4.py tests/integracion/test_49_proyeccion_revision_gastos.py tests/integracion/test_c04_pago_real_proyeccion.py tests/integracion/test_documentos_gasto_ui.py -q --tb=short` — **32 aprobadas en 11,73 s**, con PostgreSQL 17.11 temporal, sin volumen y enlazado a loopback. `ruff check --no-cache .` — aprobado (`All checks passed!`). No se ejecutó la suite completa ni la matriz manual GP.
- La revisión estática independiente inicial, anclada a `ffd0e9a`, señaló dos hallazgos materiales: la lista de versiones reemplazables incluía tipos no permitidos al actor, y los specs sobrestimaban el permiso necesario para reemplazar. El seguimiento de sólo lectura, realizado sobre el worktree corregido justo antes de crear `53d90f8`, confirmó las correcciones y no encontró nuevos hallazgos materiales. La respuesta del seguimiento no fijó un SHA de revisión; por eso no se presenta como dictamen anclado al commit. El revisor no ejecutó pruebas.

## RUN-50-20261021-02 — aporte, reemplazo y permisos

**Corte:** `53d90f8`; UI local, 21/10/2026. El gasto y las cuentas sintéticas se prepararon para el recorrido. Las acciones descritas abajo sí se observaron en la UI.

- Un archivo inválido devolvió `Tipo o extensión no permitidos.` y el formulario conservó tipo y procedencia.
- La solicitante aportó v1 y la operadora la revisó como `Aceptado`. Después, la solicitante reemplazó v1 con v2; el detalle mostró v1 como `Reemplazada` con su revisión conservada, y v2 como `Vigente`. La operadora revisó v2 por separado.
- La cuenta sin permiso de metadatos no vio nombres ni estados. La cuenta con permiso de incorporación pero sin metadatos sólo pudo iniciar un aporte nuevo y no recibió selector de versiones.

**Resultado:** evidencia parcial de GP-02 y evidencia técnica de GP-05. No se probó selección documental para el pago ni integración conjunta #28. `Aceptado` no acredita suficiencia ni conformidad institucional.

## RUN-50-20261021-03 — selección y registro de pago

**Corte y entorno:** `53d90f8`; PostgreSQL 17.11 temporal sin volúmenes, en loopback, y Django local. El proveedor real `documentos.c01.ProveedorDocumentalGastos` se configuró sólo en el entorno de los procesos locales.

- Se preparó un gasto sintético #1 en estado `Aceptada`, con estimado ARS 12.500. Una factura sintética vigente v1 se incorporó mediante el servicio documental sólo para preparar el fixture; esa incorporación no se atribuye a la UI.
- En la UI, la operadora registró para esa factura la revisión técnica `Aceptado`. El formulario de pago ofreció una única opción: la factura vigente asociada al gasto.
- En la UI se registró un pago ficticio de ARS 12.500, con fecha del hecho 21/10/2026 y referencia `PAGO-SINTETICO-C04-UI-20261021-001`.
- El detalle mostró el registro, el actor `Usuario #3`, la fecha del hecho y la fecha de registro. El gasto permaneció `Aceptada` y el estimado siguió en ARS 12.500. La factura se mantuvo `Vigente`, con su revisión separada y el vínculo documental visible en el historial.
- La pantalla aclaró que el registro es informativo: no cambia estado ni estimado y no confirma que el estimado esté saldado.

**Resultado:** observación focal de GP-01, GP-02 y GP-03 sobre un solo gasto. No se repitieron la carga ni el reemplazo, no se probó reenvío de GP-04, búsqueda/localización completa ni la integración conjunta #28. No hubo transferencia bancaria ni validación institucional/Q4.

## Evidencia histórica y límites vigentes

El recorrido del 20/10 (`RUN-50-20261020-01`) corresponde a otro corte, `ffd0e9a`. Sus resultados GP-01/03/05/06 observados, GP-02 parcial y GP-04 no ejecutado son históricos de ese SHA; no se atribuyen al corte `53d90f8`.

RUN02 y RUN03 añaden observaciones focales, no la matriz completa ni el cierre de #50. #28, Q1–Q5 y la aceptación operativa/institucional siguen pendientes. Las capturas de los detalles se mostraron durante la sesión, pero no se guardaron como archivos independientes.
