# SPEC-011 — I2: seguimiento del gasto aceptado y pago externo

- Estado: borrador SDD para revisión técnica; no implementado ni validado por Cooperadora.
- Fecha: 03/10/2026. Ubicación: `docs/specs/011-franco-seguimiento-pago-externo.md`.
- Responsable principal: Franco Damián Sánchez, gastos/pagos.
- Aporte de Matías Alejandro Fernández: identidad/capacidades y componente documental de SPEC-003; revisión de interfaces e integración. Esta propuesta no le asigna trabajo sin acuerdo.
- Validadores: Franco/Matías para diseño e integración; operadora/Marcos para reglas; coordinación para revisión del próximo tramo. Seguimiento en la Issue I2 de definición e integración; ver PR de publicación.
- Plan: RF-003/004/005/006, RNF-001/002/003/004; F-E02, F-E07, parte de F-E08, F-E10/11/12, C01/C02 e I01/I02/I03/I05/I06. SPEC-010 apoya RF-007/F-E09.

## Problema y valor

Después de aceptar una necesidad, solicitante y Cooperadora necesitan saber qué respaldo se aportó, qué pago externo se registró y qué documentación sigue pendiente. Una aceptación no acredita pago; un archivo aportado tampoco acredita revisión. I2 debe demostrar esa continuidad con un caso completo de gastos, manteniendo las responsabilidades de cada módulo.

Resultado previsto: desde un gasto aceptado, consultar su respaldo inicial, registrar de manera trazable un pago efectuado fuera del sistema y distinguir el pendiente de factura definitiva cuando el respaldo inicial fue proforma/presupuesto. Filtro y búsqueda ayudan a localizar ese trámite; por sí solos no completan I2.

## Fuentes, certeza y SDD

RF-003 exige registro de pagos externos; RF-004 documentos; RF-005 pendientes y cierre condicionado; RF-006 historial. F-E07 incluye además comprobantes y retenciones; F-E08 incluye cierre. El alcance recortado de I2 no completa esas tareas académicas.

Entrevista y relevamiento ampliado del 27/09 respaldan necesidad previa, decisión humana, respaldo inicial y posibilidad de factura definitiva posterior al pago. H1–H4 concretan una demo y continúan pendientes. SPEC-003 y SPEC-009 están en borrador; no existe aún un contrato documental implementado que gastos pueda dar por integrado.

Se aplica `docs/specs/README.md`: borrador → validación pertinente → plan → implementación autorizada → convergencia. `CONTRIBUTING.md` exige definir comportamiento antes de implementar; `AGENT_WORKFLOW.md` requiere revisar permisos, esquema relevante, contratos e integración antes de escribirlos. No se instala otra metodología. La directiva de Franco permite avanzar en demos con supuestos explícitos; no exige resolver todas las preguntas institucionales al inicio.

La validación se divide por costo: aprobar técnicamente un tramo sintético reversible puede preceder a la respuesta institucional. Antes de usar datos reales o fijar operaciones irreversibles deben revisarse los supuestos que afectan ese tramo. Aprobar este borrador no autoriza por sí solo una nueva implementación ni cierra I1.

## Alcance del incremento

Incluye un recorrido sintético: gasto aceptado → respaldo inicial vinculado y resultado de revisión distinguible → registro de pago externo → consulta de pago, actor/fecha y pendiente documental. Consumir documentos de Matías, preservar acceso por trámite y mantener trazabilidad. La primera demostración puede cubrir un pago completo en ARS y un único respaldo inicial, como ejemplos; no impone esa cardinalidad al negocio.

No incluye ejecutar transferencias, integrar bancos/Exubio/SSO, calcular retenciones, presupuestos disponibles, saldos contables, cierre automático ni bloqueo de nuevas solicitudes. El cierre se mantiene fuera de este incremento: no hay una acción de cerrar que eluda RF-005. Retenciones, pagos parciales/múltiples, correcciones/anulaciones y cierre forman tramos posteriores definidos por spec; no se declaran resueltos ni se admiten silenciosamente como si estuvieran soportados.

## Requisitos y aceptación prevista

Los casos siguientes son **criterios futuros, todavía no ejecutados**.

| ID / plan | Comportamiento | Aceptación verificable | Prueba y evidencia previstas |
|---|---|---|---|
| GP-01 — RF-003/006; F-E07/08 | Mantener separadas decisión, pago y situación documental | Dado un gasto aceptado sin pago registrado, el detalle conserva la decisión y no afirma que está pagado o cerrado. | Prueba de consulta y captura del escenario sin pago. |
| GP-02 — RF-001/004; I02/I03 | Vincular respaldo inicial al trámite con acceso autorizado | Dado un documento sintético del gasto, A/O autorizados consultan su referencia; B no obtiene archivo ni metadatos por URL. Aportar no equivale a revisar. | Contrato documental con doble del consumidor, luego integración real con componente de Matías. Sólo la segunda acredita integración. |
| GP-03 — RF-003/006; F-E07 | Registrar un hecho externo con trazabilidad | Actor autorizado registra fecha del hecho, importe/moneda, referencia y vínculo a comprobante; servidor fija actor y fecha de registro. Se conserva en recarga. No se envía orden bancaria. | Servicio y vista con PostgreSQL; evento y datos persistidos; ejemplo de pago ficticio. Campos mínimos sujetos a revisión de S1. |
| GP-04 — RNF-002/003; F-E10/I05 | Evitar modificación parcial o repetida | Un fallo de validación/persistencia no deja pago/evento parcial; reenvío del mismo registro no duplica el hecho. | Pruebas de transacción, precisión decimal y repetición contra contrato de identidad del registro aprobado en S1. No usar sólo importe/fecha como identificador único. |
| GP-05 — RF-004/005 parcial; F-E08/I03 | Distinguir respaldo inicial de factura definitiva | Con proforma inicial y pago registrado, se muestra factura definitiva pendiente; con factura aportada aún sin revisar, no se afirma conformidad. La revisión correspondiente permite indicar que ese pendiente fue satisfecho según la hipótesis aplicable. | Tabla de casos proforma/factura, ausente/aportada/revisada y pago/no pago; prueba de regla y consumo documental. |
| GP-06 — RF-006/007; F-E04/09 | Consultar cronología y localizar el trámite | Consulta autorizada muestra decisión, registro externo y revisión documental con origen, actor y fecha; buscar por concepto/estado sigue respetando visibilidad. | Integración del detalle/historial y regresión SPEC-010; ejemplos separados de fecha del hecho y fecha del registro. |

Un documento del otro trámite no puede completar un pendiente ni justificar un pago. Una persona con consulta global no recibe por ello capacidad de registrar pagos o revisar documentos. Los nombres concretos de capacidades nuevos deben acordarse con Matías, no inferirse de `gastos.decidir`.

## Supuestos explícitos y puntos de revisión

| ID | Supuesto de trabajo para demo | Avance reversible permitido | Punto de revisión y costo si cambia |
|---|---|---|---|
| S-H1 | El ejemplo parte de una necesidad aceptada, con importe sintético ARS. | Prototipo de detalle y escenarios del consumidor usando datos en memoria. | Revisar etapas y excepciones con Q1 antes de persistir su precondición. Bajo en prototipo; alto si el estado ya condiciona pagos históricos. |
| S-H2 | Un perfil sintético puede registrar el pago; A consulta y B queda aislado. | Tabla de capacidades y pruebas del consumidor con actores explícitos, como propuesta. | Acuerdo técnico con Matías antes de cambiar resolución; Q2 antes de asignar permisos reales. Alto: una autorización equivocada expone o modifica datos. |
| S-H3 | Primer escenario: un pago completo ARS, sin retenciones ni anulaciones. | Formulario/prototipo sintético y validadores de formato sin escribir registros reales. | Q3 antes de consolidar modelo de pagos. Alto: cardinalidad, importes neto/bruto y correcciones afectan migración, historial y sumas. No crear una restricción uno-a-uno por ese ejemplo. |
| S-H4 | Proforma permite ilustrar pendiente de factura definitiva; aportado y revisado son distintos. | Casos de aceptación y política de presentación pura, aislada y etiquetada como demo. | Q4 y contrato con Matías antes de persistir vínculos/revisiones. Alto: cambiar dueño, tipo o vínculo documental puede romper acceso y evidencia. |
| S-H5 | I2 consulta pendientes, sin cerrar ni bloquear futuras solicitudes. | Proyección del pendiente sin mutar `EstadoSolicitud` ni grabar un booleano definitivo de conformidad. | Q5 antes del tramo de cierre. Alto: cerrar/bloquear afecta derechos y procesos; requiere historial y criterio validado. |

Los IDs S-H son supuestos nuevos de diseño, no reemplazos ni confirmaciones de H1–H4. Una respuesta que los contradiga se registra con fuente/fecha y se transforma en cambio de spec antes de adaptar código dependiente. El silencio o el visto de WhatsApp no confirman una regla.

## Arquitectura propuesta y límites de costo

- Conservar monolito modular Django/PostgreSQL. Gastos es dueño del registro de pago externo y sus reglas; identidad y documentos siguen perteneciendo a Matías.
- Mantener `SolicitudGasto.estado` como decisión I1 durante este tramo. Presentar pago y documentación como dimensiones separadas; no extender el enum a una cadena definitiva «aceptada → pagada → cerrada» sin resolver correcciones, pagos parciales y pendientes. Una proyección puede cambiar sin reescribir todas las filas históricas.
- El importe estimado existente no se renombra ni reutiliza como importe pagado. El registro externo requiere su propia evidencia y fecha. Cambiar ese significado luego contaminaría consultas e informe.
- Proponer un registro relacionado con solicitud y eventos trazables, pero no fijar aún migración, cardinalidad total ni unicidad bancaria. Una tabla separada facilita evolución; no evita decidir correcciones y agrupaciones antes de persistir. No implementar un libro contable genérico.
- No reutilizar `DecisionGasto` para pagos: sus estados anterior/resultante describen decisiones. Proponer una lectura de cronología que combine orígenes conservando su significado; el contrato de eventos se revisa con SPEC-009 antes de compartirlo.
- Centralizar la regla de pendientes en una operación de consulta sin efectos, alimentada por hechos y revisión documental. No mantener simultáneamente banderas independientes de conformidad y datos documentales que puedan divergir.

### Contrato del consumidor documental a acordar en S1

Propuesta conceptual, sin firmas definitivas ni código de Matías:

| Interacción | Entrada/salida necesarias | Garantía y responsable |
|---|---|---|
| Consultar respaldos del gasto | Actor resuelto + referencia de trámite → referencias, tipos y resultado/autor/fecha de revisión autorizados. | Matías provee componente; Franco aporta vínculo/visibilidad y casos. Sin ruta pública de almacenamiento. |
| Validar respaldo de un registro externo | Referencia de documento + gasto accesible → vínculo válido o rechazo sin escritura. | Ambos acuerdan identidad del trámite, misma pertenencia y vigencia. No confiar en el ID enviado por formulario. |
| Registrar hecho externo | Actor + gasto + datos del hecho + referencias válidas + identidad de reenvío → registro/evento o error atómico. | Franco; visibilidad y capacidad se verifican en servidor. La revisión técnica define transacción y duplicación, no la operadora. |
| Proyectar situación documental | Hechos del gasto y documentos/revisiones visibles → pendiente y explicación de la regla aplicada. | Regla de gastos: Franco. No habilita descarga ni modifica una revisión documental. |

Tipos permitidos, tamaño, reemplazos/versiones y errores se acuerdan con SPEC-003. No copiar el máximo observado de un formulario a una política definitiva. Mientras el componente falte, usar dobles de prueba sólo en el consumidor; no crear otra implementación documental.

## Secuencia elegida y condición para comenzar cada tramo

| Tramo | Resultado / archivos previstos | Puede avanzar ahora / puerta de salida |
|---|---|---|
| S0 — conservar consulta de apoyo | SPEC-010: estado y búsqueda, ya implementados. | Coordinar revisión de I2-T02; no agregar otros SHOULD para reemplazar núcleo. Su entrega no completa I2. |
| S1 — acordar una ficha de pago y el consumo documental | Ejemplos sintéticos y contrato candidato de gastos/documentos, matriz permiso/escenario y reglas de repetición. Docs de spec/contrato, sin migraciones. | Es la **siguiente tarea prioritaria**: la arquitectura y los casos pueden prepararse ya. Franco/Matías revisan interfaz; Q1–Q5 pueden responderse asincrónicamente. Registrar los supuestos que se difieran. |
| S2 — demostrar seguimiento posterior a aceptación | Prototipo de detalle/política pura de pendientes en gastos, tests con dobles; archivos previstos de presentación/consulta y pruebas, no modelos nuevos. | Implementable antes de devolución institucional con S-H identificados y plan técnico revisado. Esta ronda sólo lo planifica. No se presenta el doble como documento realmente recibido ni esta demo como GP-02 integrado. |
| S3 — persistir registro externo e integrar respaldo | Modelo/migración de registro, servicio/vista de gastos, contrato documental real, pruebas transaccionales y por objeto. | Requiere S1 resuelto técnicamente y elegir explícitamente alcance de S-H3/S-H4. Si la devolución institucional demora, una demo aislada sintética puede avanzar tras aceptar el costo de rehacer la migración; no se habilita uso real ni se declara regla institucional. |
| S4 — converger y documentar el recorrido | Escenario GP-01–06 real integrado, guía, resultados, límites y devolución. | Revisar contra spec, documentar casos no cubiertos y actualizar evidencia F-E10/11/12. Sólo entonces evaluar cierre técnico de I2; aceptación funcional se acredita aparte. |

No hay un veto genérico de desarrollo hasta reunión: prototipo, política de presentación, fixtures y contrato consumidor son baratos de revisar. Tampoco hay permiso para migrar por intuición: estados definitivos, autoridad real, vínculos documentales, multiplicidad y cierre concentran el costo. Si S1 no logra acuerdo documental, S2 sigue siendo un prototipo útil y S3 se limita; no se sustituye a Matías ni se sigue agregando filtros.

## Documentación, evidencia y condición de cierre

Cada tramo conserva la cadena RF/tarea → criterio GP → commit/diff → comando/resultado → guía/captura/minuta. El paquete de evidencia para informe distingue lo ejecutado de estos criterios futuros. No adjudica horas del plan como realizadas ni autoría humana del código generado sin revisión del alumno.

I2 **no está completo**. Su cierre técnico propuesto exige GP-01–06 sobre componentes reales acordados, revisión de cambios sustantivos, pruebas pertinentes y guía reproducible. S2 con dobles no cumple esa condición. Una demo por video puede aportar devolución institucional explícita; no requiere presencia física por los documentos consultados. La reproducción independiente de T06 y su acta siguen siendo otra evidencia pendiente.

Preguntas Q1–Q5: etapas/datos; autoridad/correcciones; pagos/retenciones; documentos por momento; regularización/cierre. La Issue del incremento conserva esas consultas. La evidencia del informe y el guion de devolución asincrónica se mantienen en coordinación privada; no son dependencias del producto ni sustituyen la plantilla oficial.
