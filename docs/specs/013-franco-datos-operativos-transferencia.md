# SPEC-013 — Datos operativos y continuidad de transferencia en gastos

- Estado: borrador técnico para la entrega local de #74; no validado como regla institucional.
- Fecha: 27/10/2026.
- Responsable: Franco Damián Sánchez (gastos/pagos).
- Referencia: [Issue #74](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/74), relacionada con #15 y apoyada en SPEC-011 y el contrato `i2-pago-externo.md`.
- Revisión: avanzar con supuestos reversibles y preguntas explícitas para la demostración del 29/10.

## Problema y resultado

El gasto conserva concepto, importe estimado, unidad requirente, decisiones, documentos y pago externo, pero no los datos de destino necesarios para preparar una transferencia. El solicitante, el titular/beneficiario de la cuenta y el destinatario del comprobante pueden ser personas distintas. La vista tampoco debe hacer parecer que aceptar una solicitud equivale a pagarla, que un archivo equivale a una revisión o que registrar un pago cierra el trámite.

La entrega permite guardar y corregir los datos operativos como revisiones del mismo gasto, con actor y fecha fijados por el servidor; muestra esa información sólo a perfiles con autorización pertinente; y separa visualmente la solicitud, los datos de transferencia, el pago y los documentos. La factura posterior a una proforma se incorpora y revisa como documento nuevo, sin cambiar el pago ni cerrar el gasto.

## Alcance

- Datos de destino: nombre del titular/beneficiario, identificación informada, CBU o alias real, correo para remitir el comprobante y centro de costo informado.
- En la presentación inicial, el bloque de transferencia es opcional; si se completa, se guardan todos sus campos en la misma transacción. Si se omite, el titular puede completarlo más tarde sobre el mismo trámite.
- Una corrección crea una nueva revisión. Se conserva la anterior, junto con el actor y la hora del servidor; la pantalla autorizada distingue la revisión actual del historial.
- Supuesto técnico provisional de permisos: el titular que ya puede consultar sus propios gastos puede verlos; sólo el titular con `gastos.presentar` puede completar/corregir mientras la solicitud no esté rechazada ni tenga un PagoExterno. Un actor con `gastos.registrar_pago` sólo los consulta si además puede acceder al gasto por los controles de visibilidad existentes. `gastos.consultar_todas` por sí sola no revela datos bancarios. No se agrega una capacidad ni se modifica el adaptador de identidad en este incremento.
- Los datos se capturan como fueron informados. No se copian del email de sesión ni se presume que el titular es quien solicita. CBU/alias se guarda como un dato textual con límites de longitud; no se escribe “frecuente” como si fuera una cuenta. Identificación y centro de costo no se validan contra un padrón todavía inexistente; centro de costo no se confunde con unidad requirente.
- La falta de datos de transferencia no crea una solicitud distinta ni modifica el contrato C03. No se cambia el requisito documental vigente para registrar un PagoExterno ni se ejecuta una operación bancaria.
- La carga, consulta y descarga de comprobante bancario y constancia ATP reutiliza el proveedor documental y sus permisos actuales. Se explicita su diferencia respecto de factura/proforma del proveedor.
- Después de registrar el pago asociado a una proforma, el detalle indica si hay una factura vigente incorporada y su revisión propia. Un archivo incorporado no se presenta como aprobado, suficiente ni cierre.

## Fuera de alcance

No incluye datos reales, verificación bancaria, ejecución de transferencias, maestro de proveedores, valores “frecuentes”, catálogo/editor de centros de costo, envío de emails, retenciones, pagos múltiples, cambios al módulo de Matías, permisos institucionales o cierre contable. La corrección después del registro de pago queda bloqueada en esta demo para evitar cambiar retrospectivamente los datos operativos asociados al caso; Cooperadora debe confirmar si hace falta una regularización posterior distinta.

## Criterios de aceptación

1. Una presentación sin datos de transferencia sigue siendo válida. Una presentación con el bloque completo crea una única solicitud y una primera revisión; un bloque parcialmente completado explica qué falta y no deja una solicitud o revisión parcial.
2. El titular puede agregar o corregir datos en el mismo gasto mientras la solicitud no esté rechazada y todavía no tenga pago. Cada escritura crea una revisión con actor/fecha del servidor y conserva los valores anteriores.
3. Un titular ajeno, un lector global sin `gastos.registrar_pago`, un actor sin visibilidad o una sesión sin permiso no puede leer ni modificar estos datos. La denegación no revela datos ni deja escrituras.
4. La corrección y el registro del pago se serializan sobre el gasto. Si el PagoExterno se confirma primero, no se permite una revisión nueva; si la corrección termina primero, queda como revisión actual antes de registrar el pago.
5. El detalle mantiene independientes el estado de la solicitud, los datos de transferencia, el PagoExterno y el estado/revisión de documentos. No se habilita cierre ni se bloquea C03 por ausencia de datos de destino.
6. Sin factura/proforma habilitada, el registro de pago sigue deshabilitado y la pantalla explica el respaldo exigido, cómo aportarlo si el perfil tiene permiso y a quién acudir si no. C03 conserva sus verificaciones autoritativas.
7. Caso sintético factura→pago y caso proforma→pago→factura: la factura posterior es una versión real del proveedor documental, conserva su revisión independiente y no sustituye el respaldo que quedó referenciado por el pago.

## Datos, permisos y sensibilidad

CBU/alias, identificación, correo y titular son datos personales/financieros. Sólo se exponen en el detalle y formulario específico después de autorizar acceso al gasto y verificar el permiso sensible descrito arriba. No se agregan a listados, búsquedas, cronologías comunes, exportaciones ni logs. Actor, revisión y fecha se fijan en servidor. Las pruebas usan cuentas y valores sintéticos.

## Módulos e interfaces

- Propietario: `gastos` (modelo de revisiones, servicio transaccional, formulario y vistas/templates Django).
- Integraciones reutilizadas: `visible_expenses`, capacidades actuales, `PagoExterno`/C03, carga documental y proyección de revisiones ya disponibles.
- Migración aditiva sin backfill de datos inventados. Los gastos históricos permanecen sin revisión de transferencia hasta que el titular aporte datos.
- No se modifica `identidad`, `documentos`, el contrato C03 ni la interfaz de facturación.

## Prueba y evidencia

Pruebas focales de validación, alta/corrección e historial, acceso por titular y actor de pago, denegaciones por objeto/capacidad, transacción/concurrencia entre corrección y pago, y persistencia en PostgreSQL. Recorrido visual con dos escenarios y un intento bloqueado sin respaldo. Revisar migración/diff, `manage.py check`, `makemigrations --check`, Ruff y suite pertinente según el workflow. La prueba de navegador describe sólo la versión ejecutada.

## Preguntas para Cooperadora

- ¿Quién carga, consulta, verifica y corrige los datos, y puede alguien de Cooperadora corregir por el titular? ¿Cómo se regulariza un error detectado después del pago?
- ¿Qué significa exactamente “frecuente”, de qué fuente confiable proviene y quién mantiene ese valor? Hasta acordarlo, ingresar el CBU o alias real.
- ¿Quién selecciona y valida el centro de costo, y qué catálogo aplica? La demo lo guarda como texto informado, separado de la unidad requirente.
- ¿Se puede registrar el pago sin completar los datos del destino? Se preserva el contrato vigente y la decisión queda abierta.
- ¿Quién remite el comprobante, a qué correo y cómo se confirma la entrega? El campo de correo no envía mensajes.
- ¿Qué condición documental permite considerar atendida la factura posterior a proforma, y quién la confirma? Cargar o revisar un archivo no equivale por sí solo a cierre.

## Decisiones del corte técnico

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 27/10/2026 | Issue #74, SPEC-011 y contrato C03 | Agregar una revisión por gasto y corregir antes de registrar el pago; capture inicial opcional y corrección posterior sobre el mismo gasto. | No backfill ni política institucional; datos sintéticos y trazabilidad por revisión. |
| 27/10/2026 | Perfiles actuales de demo | Reutilizar permisos/visibilidad actuales; `consultar_todas` no concede lectura bancaria. | Sin cambios a la interfaz de identidad propiedad de Matías. |
| 27/10/2026 | Contrato C03 | Mantener inalterado el requisito documental del pago y dejar independiente el registro de cuenta destino. | La ausencia de datos de cuenta no altera autorización ni persistencia de PagoExterno. |
