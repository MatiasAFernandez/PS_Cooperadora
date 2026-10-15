# SPEC-011 — I2: seguimiento del gasto aceptado y pago externo

- Estado al 15/10/2026: las decisiones técnicas A–D para la demo fueron acordadas; el backend C03 y el resumen/cronología están integrados mediante PR #42/#43. La PR #45 implementa el formulario consumidor y el selector contractual, con cierre seguro si faltan proveedor o permisos. La integración del proveedor documental y las capacidades reales de identidad siguen pendientes; I2 no está completo ni validado institucionalmente.
- Fecha inicial: 03/10/2026. Actualización de estado: 15/10/2026. Ubicación: `docs/specs/011-franco-seguimiento-pago-externo.md`.
- Responsable principal: Franco Damián Sánchez, gastos/pagos.
- Aporte de Matías Alejandro Fernández: identidad/capacidades y componente documental de SPEC-003; revisión de interfaces e integración. Esta propuesta no le asigna trabajo sin acuerdo.
- Validadores: Franco/Matías para diseño e integración; operadora/Marcos para reglas; coordinación para revisión del próximo tramo. Seguimiento en la Issue I2 de definición e integración; ver PR de publicación.
- Plan: RF-003/004/005/006, RNF-001/002/003/004; F-E02, F-E07, parte de F-E08, F-E10/11/12, C01/C02 e I01/I02/I03/I05/I06. SPEC-010 apoya RF-007/F-E09.

## Problema y valor

Después de aceptar una necesidad, solicitante y Cooperadora necesitan saber qué respaldo se aportó, qué pago externo se registró y qué documentación sigue pendiente. Una aceptación no acredita pago; un archivo aportado tampoco acredita revisión. I2 debe demostrar esa continuidad con un caso completo de gastos, manteniendo las responsabilidades de cada módulo.

Resultado previsto: desde un gasto aceptado, consultar su respaldo inicial, registrar de manera trazable un pago efectuado fuera del sistema y distinguir el pendiente de factura definitiva cuando el respaldo inicial fue proforma/presupuesto. Filtro y búsqueda ayudan a localizar ese trámite; por sí solos no completan I2.

## Fuentes, certeza y SDD

RF-003 exige registro de pagos externos; RF-004 documentos; RF-005 pendientes y cierre condicionado; RF-006 historial. F-E07 incluye además comprobantes y retenciones; F-E08 incluye cierre. El alcance recortado de I2 no completa esas tareas académicas.

Entrevista y relevamiento ampliado del 27/09 respaldan necesidad previa, decisión humana, respaldo inicial y posibilidad de factura definitiva posterior al pago. H1–H4 concretan una demo y continúan pendientes. SPEC-003 se integró como documentación mediante PR #18 y su primer tramo DOC-R01–03 está en la Issue #19 de Matías; SPEC-009 y el acuerdo de interfaces siguen pendientes. No existe evidencia de un proveedor documental implementado que gastos pueda dar por integrado.

Se aplica `docs/specs/README.md`: borrador → validación pertinente → plan → implementación autorizada → convergencia. `CONTRIBUTING.md` exige definir comportamiento antes de implementar y revisar interfaces compartidas. El [plan de tareas I2](../planning/i2-tareas.md) concreta resultado, responsabilidad, dependencia, criterio y pruebas. No se instala otra metodología. La directiva de Franco permite avanzar en demos con supuestos explícitos; no exige resolver todas las preguntas institucionales al inicio.

La validación se divide por costo: aprobar técnicamente un tramo sintético reversible puede preceder a la respuesta institucional. Antes de usar datos reales o fijar operaciones irreversibles deben revisarse los supuestos que afectan ese tramo. Aprobar este borrador no autoriza por sí solo una nueva implementación ni cierra I1.

## Alcance del incremento

Incluye un recorrido sintético: gasto aceptado → respaldo inicial vinculado y resultado de revisión distinguible → registro de pago externo → consulta de pago, actor/fecha y pendiente documental. Consumir documentos de Matías, preservar acceso por trámite y mantener trazabilidad. La primera demostración puede cubrir un pago completo en ARS y un único respaldo inicial, como ejemplos; no impone esa cardinalidad al negocio.

No incluye ejecutar transferencias, integrar bancos/Exubio/SSO, calcular retenciones, presupuestos disponibles, saldos contables, cierre automático ni bloqueo de nuevas solicitudes. El cierre se mantiene fuera de este incremento: no hay una acción de cerrar que eluda RF-005. Retenciones, pagos parciales/múltiples, correcciones/anulaciones y cierre forman tramos posteriores definidos por spec; no se declaran resueltos ni se admiten silenciosamente como si estuvieran soportados.

## Requisitos y aceptación prevista

Los casos siguientes son criterios de aceptación y su estado técnico al 15/10/2026. Una implementación parcial o una prueba con dobles no acredita la integración con documentos ni la validación institucional.

| ID / plan | Comportamiento | Aceptación verificable | Prueba y evidencia previstas | Estado al 15/10/2026 |
|---|---|---|---|---|
| GP-01 — RF-003/006; F-E07/08 | Mantener separadas decisión, pago y situación documental | Dado un gasto aceptado sin pago registrado, el detalle conserva la decisión y no afirma que está pagado o cerrado. | Consulta del detalle con y sin pago; captura de ambos escenarios. | Parcial: PR #43 muestra por separado decisión y pago en el detalle con pago; falta evidencia del escenario sin pago y del pendiente documental integrado. |
| GP-02 — RF-001/004; I02/I03 | Vincular respaldo inicial al trámite con acceso autorizado | El documento pertenece a un trámite concreto; cada operación de metadatos/descarga aplica autorización propia. Aportar no equivale a revisar. | Contrato del proveedor y pruebas de pertenencia/visibilidad; luego integración con el proveedor real. | Pendiente: PR #42 define el puerto y sus garantías, pero el proveedor documental real y su vínculo FK aún no están integrados (#19). |
| GP-03 — RF-003/006; F-E07 | Registrar un hecho externo con trazabilidad | Actor autorizado registra fecha del hecho, importe/moneda, referencia y versión documental; servidor fija actor y fecha de registro. No se envía orden bancaria. | Servicio PostgreSQL, registro persistente, evento y ejemplo ficticio; integración HTTP/formulario se verifica por separado. | Parcial implementado en PR #42: servicio y persistencia transaccional con puerto documental; no hay formulario/ruta de registro ni proveedor real, y la capacidad real de identidad sigue pendiente (#21/#28). |
| GP-04 — RNF-002/003; F-E10/I05 | Evitar modificación parcial o repetida | Un fallo no deja pago/evento parcial; el reenvío idéntico devuelve el registro sin evento duplicado y un payload distinto produce conflicto. | Pruebas de transacción, precisión decimal, reenvío, conflicto y concurrencia proporcional. | Implementado y verificado en C03/PR #42: pago y evento atómicos; restricción única por gasto; huella canónica incluye datos normalizados y referencia documental. |
| GP-05 — RF-004/005 parcial; F-E08/I03 | Distinguir respaldo inicial de factura definitiva | Una proforma/presupuesto no satisface por sí sola la factura definitiva; una revisión desconocida no equivale a aprobación. | Tabla de casos de tipo/revisión y consumo del proveedor real; validar la regla institucional por separado. | Pendiente de integración: el contrato admite factura o presupuesto/proforma y documenta revisión desconocida como tolerancia técnica; no se demuestra revisión ni cumplimiento del pendiente. |
| GP-06 — RF-006/007; F-E04/09 | Consultar cronología y localizar el trámite | Consulta autorizada muestra decisión y registro externo con origen, actor y fechas; búsqueda conserva visibilidad. | Detalle/historial, regresión SPEC-010 y revisión documental cuando exista proveedor. | Parcial: PR #43 muestra decisión y registro externo en orden y conserva la búsqueda/listado de SPEC-010; revisión y actor/fecha documental dependen de #19. Revisión manual sintética realizada en `127.0.0.1:8012/gastos/1/`. |

Un documento del otro trámite no puede completar un pendiente ni justificar un pago. Una persona con consulta global no recibe por ello capacidad de registrar pagos o revisar documentos. Las capacidades listadas son las acordadas para esta demo; el catálogo y la aplicación en identidad siguen pendientes y no se infieren de `gastos.decidir`.

## Supuestos explícitos y puntos de revisión

| ID | Supuesto de trabajo para demo | Avance reversible permitido | Punto de revisión y costo si cambia |
|---|---|---|---|
| S-H1 | El ejemplo parte de un gasto aceptado. | La demo sólo admite registrar pago sobre gasto aceptado; aceptación no equivale a pago/cierre. | Acordado como regla técnica C01 para esta demo. Q1 institucional sigue pendiente; revisar antes de uso real. |
| S-H2 | Las capacidades se comprueban separadamente sobre el gasto concreto. | Consulta usa `gastos.consultar_propias`/`gastos.consultar_todas`; incorporar/ver metadatos/descargar/registrar pago requieren capacidades explícitas. `gastos.decidir` no concede registrar pago. | Acordado como regla técnica C01. Catálogo/adaptador de identidad e integración ejecutable siguen pendientes (#21/#28); Q2 institucional sigue pendiente. |
| S-H3 | Un registro por gasto aceptado, importe positivo en ARS, fecha del hecho y referencia externa. | Unicidad por gasto; pago y evento se persisten atómicamente; huella normalizada incluye la versión documental; reenvío idéntico es idempotente y otro contenido produce conflicto. | Acordado e implementado en C03/PR #42. Pagos parciales, retenciones, anulaciones y agrupaciones quedan fuera y Q3 sigue pendiente. |
| S-H4 | El pago referencia una versión documental inmutable vinculada a ese gasto; reemplazar genera otra versión. Cada documento apunta a un solo trámite concreto con FK protegida; el vínculo no se reasigna y no se borra un trámite con documentos o pagos asociados. | El proveedor debe validar en servidor pertenencia, tipo admitido y vigencia, bloqueando la versión durante la transacción. Para la demo se admite factura o presupuesto/proforma ficticios; revisión desconocida permite el recorrido técnico, pero no equivale a aprobación ni satisface la factura definitiva. | Acordado como contrato técnico C01; la implementación real del proveedor, integridad FK, selector y revisión siguen pendientes (#19). Q4 institucional sigue pendiente. |
| S-H5 | Registrar un pago no cierra el gasto ni declara saldado el importe estimado. | Pago y decisión siguen siendo dimensiones distintas; no se habilita cierre ni bloqueo automático. | Acordado como límite de la demo. Q5 institucional y un eventual flujo de cierre siguen pendientes. |

Los IDs S-H son supuestos nuevos de diseño, no reemplazos ni confirmaciones de H1–H4. Una respuesta que los contradiga se registra con fuente/fecha y se transforma en cambio de spec antes de adaptar código dependiente. El silencio o el visto de WhatsApp no confirman una regla.

## Arquitectura propuesta y límites de costo

- Conservar monolito modular Django/PostgreSQL. Gastos es dueño del registro de pago externo y sus reglas; identidad y documentos siguen perteneciendo a Matías.
- Mantener `SolicitudGasto.estado` como decisión I1 durante este tramo. Presentar pago y documentación como dimensiones separadas; no extender el enum a una cadena definitiva «aceptada → pagada → cerrada» sin resolver correcciones, pagos parciales y pendientes. Una proyección puede cambiar sin reescribir todas las filas históricas.
- El importe estimado existente no se renombra ni reutiliza como importe pagado. El registro externo requiere su propia evidencia y fecha. Cambiar ese significado luego contaminaría consultas e informe.
- C03 persiste un registro `PagoExterno` por gasto aceptado mediante relación uno-a-uno protegida y un `EventoPagoExterno` inmutable. La unicidad es una restricción técnica de la demo, no una regla institucional definitiva. No se implementa libro contable genérico ni se cubren correcciones, agrupaciones o pagos parciales.
- No reutilizar `DecisionGasto` para pagos: sus estados anterior/resultante describen decisiones. PR #43 combina decisión y registro de pago en una cronología de lectura, conservando su significado. El contrato general de eventos se revisa con SPEC-009 antes de compartirlo.
- Centralizar la regla de pendientes en una operación de consulta sin efectos, alimentada por hechos y revisión documental. No mantener simultáneamente banderas independientes de conformidad y datos documentales que puedan divergir.

### Contrato del consumidor documental

Contrato técnico de la demo aceptado en C01 y reflejado en PR #42; no implica que el proveedor real de documentos esté implementado:

| Interacción | Entrada/salida necesarias | Garantía y responsable |
|---|---|---|
| Consultar respaldos del gasto | Actor resuelto + referencia de trámite → referencias, tipos y resultado/autor/fecha de revisión autorizados. | Matías provee componente; Franco aporta vínculo/visibilidad y casos. Sin ruta pública de almacenamiento. |
| Validar respaldo de un registro externo | Referencia de documento + gasto accesible → vínculo válido o rechazo sin escritura. | Ambos acuerdan identidad del trámite, misma pertenencia y vigencia. No confiar en el ID enviado por formulario. |
| Registrar hecho externo | Actor + gasto + datos del hecho + referencias válidas + identidad de reenvío → registro/evento o error atómico. | Franco; visibilidad y capacidad se verifican en servidor. La revisión técnica define transacción y duplicación, no la operadora. |
| Proyectar situación documental | Hechos del gasto y documentos/revisiones visibles → pendiente y explicación de la regla aplicada. | Regla de gastos: Franco. No habilita descarga ni modifica una revisión documental. |

Para esta demo se admiten factura, presupuesto o proforma ficticios. La versión debe quedar asociada por FK protegida a un único trámite concreto; el proveedor real debe impedir reasignaciones y borrados mientras existan vínculos, conservar versiones anteriores y bloquear la vigente al validar el pago. Los permisos de metadatos/descarga y el selector corresponden a la integración de #19. Los dobles permanecen en pruebas; no sustituyen el proveedor.

## Secuencia elegida y condición para comenzar cada tramo

| Tramo | Resultado / archivos previstos | Puede avanzar ahora / puerta de salida |
|---|---|---|
| S0 — conservar consulta de apoyo | SPEC-010: estado y búsqueda, ya implementados. | Coordinar revisión de I2-T02; no agregar otros SHOULD para reemplazar núcleo. Su entrega no completa I2. |
| S1 — acordar ficha técnica de demo e interfaces | Decisiones C01 A–D aceptadas para demo; contrato del consumidor y separación de capacidades documentados. | Decisiones técnicas C01 cerradas para este corte. Q1–Q5 y la integración real con los módulos propietarios permanecen pendientes. |
| S2 — demostrar seguimiento posterior a aceptación | Detalle de solo lectura con resumen de pago y cronología; pruebas focales y evidencia visual. | Implementado en PR #43 y marcado completo en #15. No incluye formulario, registro desde UI ni integración documental; GP-02/05 no se completan. |
| S3 — persistir registro externo | Modelo/migración, servicio de gastos, controles de objeto, bloqueo/puerto documental y pruebas transaccionales. | Persistencia C03 implementada en PR #42 sobre PostgreSQL aislado y verificada. El proveedor documental y las capacidades ejecutables de identidad siguen pendientes; no habilita uso real. |
| S4 — converger y documentar el recorrido | Escenario GP-01–06 real integrado, guía, resultados, límites y devolución. | Revisar contra spec, documentar casos no cubiertos y actualizar evidencia F-E10/11/12. Sólo entonces evaluar cierre técnico de I2; aceptación funcional se acredita aparte. |

El acuerdo técnico de C01 y la aceptación explícita del costo de rehacer permitieron implementar la persistencia sintética de C03. El alcance no habilita datos ni operación reales. La integración se limita hasta contar con el proveedor documental y el catálogo de identidad correspondientes; no se sustituye a sus responsables ni se amplía el alcance a cierre, pagos parciales, retenciones o transferencias.

## Documentación, evidencia y condición de cierre

Cada tramo conserva la cadena RF/tarea → criterio GP → commit/diff → comando/resultado → guía/captura/minuta. El paquete de evidencia para informe distingue lo ejecutado de estos criterios futuros. No adjudica horas del plan como realizadas ni autoría humana del código generado sin revisión del alumno.

I2 **no está completo**. C03 y la consulta de pago están en PR abiertas #42 y #43; el proveedor documental y la identidad real no están integrados, y GP-01/03/05/06 permanecen parciales según la tabla. El cierre técnico exige GP-01–06 sobre componentes reales acordados, revisión de cambios sustantivos, pruebas pertinentes y guía reproducible. Una demo sintética no equivale a validación institucional. La reproducción independiente de T06 y su acta siguen siendo otra evidencia pendiente.

Preguntas Q1–Q5: etapas/datos; autoridad/correcciones; pagos/retenciones; documentos por momento; regularización/cierre. La Issue del incremento conserva esas consultas. La evidencia del informe y el guion de devolución asincrónica se mantienen en coordinación privada; no son dependencias del producto ni sustituyen la plantilla oficial.
