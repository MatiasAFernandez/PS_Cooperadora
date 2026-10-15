# I2 — seguimiento del gasto aceptado y pago externo

Fecha inicial: 06/10/2026. Estado actualizado: 15/10/2026. Responsable de gastos/pagos: Franco Damián Sánchez. **Plan compartido; C01 técnico y C03 avanzados para la demo, sin completar I2 ni aprobar reglas institucionales.**

## Fuentes y revisión del plan

Comportamiento y aceptación: [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md). Consulta de apoyo: [SPEC-010](../specs/010-franco-consulta-gastos.md). Formato de tareas: [I1](i1-tareas.md). Método: [ciclo SDD](../specs/README.md) y [CONTRIBUTING](../../CONTRIBUTING.md). No se sustituye el Plan de Trabajo académico ni se instala otra metodología.

La revisión del 06/10 cotejó RF/RNF y actividades con la copia revisada del 13/09 del plan individual de Franco, y el alcance con las specs vigentes en ese momento. El [Plan de Trabajo compartido](https://docs.google.com/document/d/1W435Jlo6K-54DpCbqokJBdcfWaFOydkMNHgNvem1Oz4/edit) conserva su función académica; este cotejo no certifica que aquella copia sea la última versión presentada o aprobada por la cátedra. No se publica la copia con datos personales ni se acreditan sus horas estimadas como ejecutadas.

**Estado al 15/10:** C01 A–D está acordado para esta demo como contrato técnico, y el costo de rehacer la persistencia fue aceptado explícitamente. C03 backend está implementado en PR #42; la pantalla de consulta S2 está en PR #43. Estas decisiones no son reglas institucionales ni acreditan integración documental, identidad real, cierre de I2 o validación de Cooperadora.

## Estado y orden de trabajo

- I1 T02–T05 están integrados. T06/[#8](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/8) conserva recorrido manual, reproducción independiente y acta; su guía está en [PR #14, Draft](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/14). T07/[#9](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/9) conserva devolución H1–H4. No se cierran por avanzar I2.
- S0: I2-T01/T02 (estado y concepto) están implementadas en [PR #44](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/44), abierta para revisión; son apoyo RF-007/F-E09, no el núcleo completo de I2.
- S1: C01 A–D fue acordado como contrato técnico de demo. La referencia compuesta por módulo e identificador distingue trámites; cada documento se vincula a un solo trámite con FK protegida, sin reasignación ni borrado del trámite mientras haya vínculos; las capacidades se separan por operación; el pago apunta al gasto y a una versión documental inmutable; la restricción de un pago positivo ARS por gasto aceptado y el tratamiento de reenvíos quedaron definidos. Q1–Q5 institucionales permanecen pendientes.
- S2: el detalle de gasto muestra resumen de pago y cronología en [PR #43](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/43), con datos sintéticos y en modo de solo lectura. No incluye alta de pago, selector documental, revisión ni proveedor real. La suite combinada registró 250 pruebas aprobadas; la evidencia manual quedó en el handoff privado.
- S3: persistencia C03 implementada en [PR #42](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/42), con migración, servicio, evento atómico e idempotencia. El puerto fija el contrato esperado del proveedor; no hay proveedor documental real ni integración ejecutable de las capacidades de identidad (#19/#21/#28).
- S4: convergencia técnica y devolución operativa, con evidencias separadas.

[Issue #15](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/15) sigue el incremento central; [#16](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/16), las consultas. [SPEC-003](../specs/003-matias-documentos.md) se integró como documentación mediante PR #18; [Issue #19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19), asignada a Matías, prepara DOC-R01–03. DOC-R04 e integración I03 no se dan por implementados. Trabajo privado de Matías desconocido.

Los IDs I2-C01…C06 siguientes son candidatos de planificación, no Issues creadas, compromisos del compañero ni tareas automáticamente Ready. Matías mantiene identidad/documentos; Franco, gastos/pagos. La revisión compartida se propone sin imponer disponibilidad o fechas.

## I2-C01 — ficha y contrato del consumidor (S1)

- Resultado: casos sintéticos de gasto/pago/documentos, capacidades por acción y objeto, ID de trámite, errores, repetición y fuentes de actor/fechas.
- Responsable/revisión: Franco prepara; Matías revisa las interfaces pertinentes por acuerdo.
- Requisitos/Plan: GP-01–06 como diseño; RF-003/004/005 parcial/006 y RF-001; F-E02, C01 e I01/I02/I03 en el alcance del consumidor.
- Dependencias: SPEC-002/003/009 y delimitación de #19; no exige proveedor terminado para preparar una propuesta.
- Cierre: reglas C01 A–D acordadas para esta demo; el contrato del puerto documenta entradas/garantías exigidas al proveedor. La integración de #19 aún debe validar la interfaz implementada; Q1–Q5 y cualquier política institucional siguen pendientes.
- Pruebas/evidencia: aceptación sin pago; documento ausente/ajeno/unknown; consulta sin capacidad de registro; actor falsificado; reenvío idéntico/distinto; fallo parcial; cronología. Revisión del contrato y registro de acuerdo, no tests del servidor inexistente.
- Estado: reglas técnicas A–D acordadas para la demo; proveedor documental e identidad ejecutables no integrados. Q1–Q5 siguen pendientes como validación institucional.

## I2-C02 — resumen de seguimiento (S2)

- Resultado: detalle de solo lectura que muestra decisión y pago persistido por C03 como dimensiones separadas; la situación documental pendiente se distingue sin simular una revisión real.
- Responsable/revisión: Franco; revisión técnica y de interfaces pertinentes, sin sustituir al proveedor de Matías.
- Requisitos/Plan: GP-01/05 y preparación GP-02/06; RF-003/004/005 parcial/006, F-E04/F-E08 parciales y F-E10.
- Dependencias: contrato C01 de demo; el proveedor real no se requiere para mostrar el resumen del pago, pero sí para acreditar respaldo, pertenencia y estado documental.
- Cierre: aceptación no equivale a pago/cierre; proforma mantiene pendiente; factura aportada con revisión unknown no implica conformidad; sin mutar EstadoSolicitud, identidad o revisión documental.
- Pruebas/evidencia: casos propios/ajenos, pago/no pago, aporte/revisión, denegación sin exposición, determinismo y ausencia de mutaciones/efectos. Datos ficticios y resultado marcado como demo.
- Estado: resumen y cronología de solo lectura implementados en [PR #43](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/43) y revisión manual sintética registrada. GP-01/06 son parciales; el detalle no prueba proveedor documental, revisión ni alta de pago.

## I2-C03 — persistencia del hecho externo (S3)

- Resultado: registro autorizado de un pago efectuado fuera del sistema, con actor/fecha de registro del servidor, fecha del hecho, importe/moneda y referencias; registro y evento atómicos.
- Responsable/revisión: Franco; revisión de esquema, autoridad, repetición e interfaces compartidas con Matías por acuerdo.
- Requisitos/Plan: GP-03/04; RF-003/006, RNF-002/003, F-E07 parcial, F-E10 e I05.
- Dependencias: C01 resuelto técnicamente y alcance/costo de rehacer aceptados para esta demo; Q1/Q2 para autoridad real, Q3 para cardinalidad/correcciones, Q4 para respaldo institucional. La demo persistida es aislada/sintética y no habilita uso real.
- Cierre: permiso por objeto, importes precisos, actor independiente del formulario, fallo sin parcial; identidad de operación y conflicto de payload tratados según contrato. Importe/fecha no son por sí solos identidad única.
- Pruebas/evidencia: PostgreSQL de prueba, acceso directo denegado, precisión, recarga, fallo provocado, repetición y concurrencia proporcional; diff y comandos reales.
- Estado: implementado y probado en PR #42 sobre PostgreSQL aislado; pendiente de integración con el proveedor documental real y capacidades ejecutables. La implementación técnica no determina reglas institucionales.

## I2-C04 — consumidor documental real (S3)

- Resultado: consultar respaldo propio y proyectar pendientes sin confundir aporte/revisión ni conceder permisos por consultar.
- Responsable/revisión: Franco escribe consumidor; Matías mantiene su componente. Contrato común revisado por ambos, sin reasignar #19.
- Requisitos/Plan: GP-02/05 y parte documental GP-06; RF-001/004/005 parcial/006, I02/I03 y F-E08 parcial.
- Dependencias: C01 y proveedor real #19 para asociación/recuperación; DOC-R04 y regla Q4 para demostrar revisión y satisfacción del pendiente, fuera del primer tramo #19.
- Cierre: documento ajeno no respalda ni expone metadatos/archivo; proforma y factura aportada sin revisión no conformidad. Sin DOC-R04, declarar consulta/aporte parcial, no C04 completo para GP-01–06.
- Pruebas/evidencia: dobles preparan; integración real comprueba URL/objeto/almacenamiento/identidad de demo, asociaciones cruzadas y revisión según contrato. Pruebas de Matías no prueban automáticamente el consumidor.
- Estado: candidato dependiente; no proveedor ni integración acreditados.

## I2-C05 — convergencia técnica (S4)

- Resultado: recorrido real GP-01–06, guía reproducible, evidencia criterio→versión→prueba y regresión S0.
- Responsable/revisión: Franco coordina; reproducción/revisión de Matías por acuerdo.
- Requisitos/Plan: RF-001/003/004/005 parcial/006/007 parcial, RNF aplicables; F-E04/07/08/09 parciales, F-E10/11/12 e I05/I06.
- Dependencias: C03/C04 reales, contratos y revisión documental cuando corresponda; versión S0 integrada o identificada explícitamente como rama de demo.
- Cierre: todos los GP con evidencia real, denegaciones, atomicidad/repetición y cronología; dobles/CI verde no completan I2. Cierre técnico separado de aceptación institucional.
- Pruebas/evidencia: recorrido aceptado→respaldo→hecho externo→consulta/revisión, accesos y regresiones pertinentes, reproducción registrada. No sumar ejecuciones solapadas como nuevos casos.
- Estado: candidato futuro, no demostrado por la demo C02.

## I2-C06 — devolución y cambios de hipótesis (S4)

- Resultado: Q1 etapas/datos, Q2 autoridad/correcciones, Q3 pagos/retenciones, Q4 documentos/revisión y Q5 regularización/cierre, vinculadas a supuestos/tareas.
- Responsable/revisión: Franco recoge gastos; Matías aporta interfaces por acuerdo; operadora/Marcos validan reglas.
- Requisitos/Plan: S-H1–5, RF-003/004/005/006, C02 y ajustes F-E02; no horas o validación acreditadas por una minuta propuesta.
- Dependencias: preguntas/casos se pueden enviar desde S1 sin reunión obligatoria; demo completa depende de C05. T07 de I1 puede aportar evidencia compartida, no aceptar I2 automáticamente.
- Cierre: cada respuesta confirmada/corregida/pendiente con fuente/fecha/ejemplo y ajuste trazado. Silencio no confirma; revisar con el propietario antes de cambiar interfaz.
- Pruebas/evidencia: minuta y cambios de spec; repetir únicamente pruebas afectadas si cambian reglas.
- Estado: candidato; respuestas institucionales pendientes.

## Cobertura parcial del Plan de Trabajo y próximo paso

F-E07 también exige comprobantes/retenciones, y F-E08 incluye cierre: este I2 recortado no los completa. F-E09 incluye resúmenes/totales además de filtros: S0 cubre sólo parte. I03 contempla integración documental real, no un doble. I06 contempla revisión mutua, no sólo revisión IA. I2-C01/C02 son IDs de tareas locales diferentes de C01/C02 académicos.

Próximo paso: revisar las PR #42 y #43, mantenerlas abiertas hasta decisión explícita y continuar únicamente con las integraciones documentales/de identidad de las Issues #19/#21/#28 cuando estén disponibles. No volver a solicitar el acuerdo técnico C01; Q1–Q5 siguen abiertos para validación institucional. T06/T07 y la convergencia GP-01–06 permanecen pendientes. No se agregan cambios automáticos en Issues/Project ni compromisos al compañero.
