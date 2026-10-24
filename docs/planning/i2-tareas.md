# I2 — seguimiento del gasto aceptado y pago externo

Fecha inicial: 06/10/2026. Estado actualizado: 21/10/2026. Responsable de gastos/pagos: Franco Damián Sánchez. **Plan compartido; C01–C03 integrados, C04 con proveedor real y proyección parcial (#55), identidad de trámite (#56), eventos/navegación comunes (#59) y DOC-R04 (#24, PR #62) integrados en main 48c094a45416c468c2f4ed3fa03b0ea6ed4e700b; PR #60/#61 cerraron #22/#23. #28, #49 y #50 siguen abiertas. La proyección del historial por versión en gastos está implementada localmente en #49 y cuenta con pruebas focalizadas aprobadas en PostgreSQL (véase la evidencia); la rama aún no está integrada. RUN02/RUN03 aportan observaciones focales de UI para #50; la matriz completa sigue pendiente. I2 no está completo ni hay reglas institucionales aprobadas.**

## Fuentes y revisión del plan

Comportamiento y aceptación: [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md). Consulta de apoyo: [SPEC-010](../specs/010-franco-consulta-gastos.md). Formato de tareas: [I1](i1-tareas.md). Método: [ciclo SDD](../specs/README.md) y [CONTRIBUTING](../../CONTRIBUTING.md). No se sustituye el Plan de Trabajo académico ni se instala otra metodología.

La revisión del 06/10 cotejó RF/RNF y actividades con la copia revisada del 13/09 del plan individual de Franco, y el alcance con las specs vigentes en ese momento. El [Plan de Trabajo compartido](https://docs.google.com/document/d/1W435Jlo6K-54DpCbqokJBdcfWaFOydkMNHgNvem1Oz4/edit) conserva su función académica; este cotejo no certifica que aquella copia sea la última versión presentada o aprobada por la cátedra. No se publica la copia con datos personales ni se acreditan sus horas estimadas como ejecutadas.

**Estado al 21/10:** C01 A–D está acordado para esta demo como contrato técnico. Backend, resumen, consultas y formulario están integrados mediante PR #42/#43/#44/#45. PR #55 integró el consumidor C04 con el proveedor documental real y proyección parcial; PR #56 integró la cabecera protegida SolicitudGasto.tramite_base (#53 cerrada). PR #59 integró eventos/navegación comunes de #54; PR #60/#61 cerraron #22/#23. PR #62 integró DOC-R04 (#24) en main, base 48c094a45416c468c2f4ed3fa03b0ea6ed4e700b. #28, #49 y #50 siguen abiertas. La proyección del historial documental por versión en el detalle del gasto está implementada localmente en #49; su validación focalizada aprobó 52 pruebas en PostgreSQL aislado (véase la evidencia), pero la rama aún no está integrada. RUN02/RUN03 aportan evidencia de UI focal para #50; la matriz completa, la búsqueda/localización y el cierre de C05 siguen pendientes. Estos avances no completan I2 ni acreditan reglas institucionales.

## Estado y orden de trabajo

- I1 T02–T06 están completados técnicamente; #8 está cerrada y la guía/acta vigentes se integraron en #37/#39. #14 quedó reemplazada. T07/[#9](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/9) conserva la devolución H1–H4 reprogramada, sin bloquear la demo I2 bajo supuestos explícitos.
- S0: I2-T01/T02 (estado y concepto) están integradas mediante [PR #44](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/44); #16 está cerrada. Son apoyo RF-007/F-E09, no el núcleo completo de I2.
- S1: C01 A–D fue acordado como contrato técnico de demo. La referencia compuesta por módulo e identificador distingue trámites; cada documento se vincula a un solo trámite con FK protegida; las capacidades se separan por operación; el pago apunta al gasto y a una versión documental inmutable; la restricción de un pago positivo ARS por gasto aceptado y el tratamiento de reenvíos quedaron definidos. Contrato común de trámites integrado en #51. Q1–Q5 institucionales permanecen pendientes.
- S2: el detalle de gasto muestra resumen de pago y cronología en [PR #43](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/43), y el formulario consumidor con selector en [PR #45](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/45), con datos sintéticos. GP-01/GP-04 están verificados en este tramo. La suite de CI en main aprobó.
- S3: persistencia C03 integrada mediante [PR #42](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/42), con migración, servicio, evento atómico e idempotencia (#40 cerrada). Integración del consumidor C04 con el proveedor documental real y proyección documental parcial en [PR #55](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/55); vínculo protegido `SolicitudGasto.tramite_base` integrado en [PR #56](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/56) (#53 cerrada); DOC-R04 en [PR #62](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/62) (#24). La proyección de revisiones en gastos está implementada localmente en #49 y tiene validación focalizada aprobada en PostgreSQL; la rama aún espera revisión e integración.
- S4: convergencia técnica y devolución operativa, con evidencias separadas. #54 está integrada en main mediante PR #59; #22/#23 cerraron mediante PR #60/#61. RUN02/RUN03 aportan observaciones focales de UI para #50; siguen pendientes la matriz GP-01–06, la búsqueda/localización completa y el recorrido integrado. #28 conserva la integración conjunta de ambos circuitos.

[Issue #15](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/15) sigue el incremento central; [#16](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/16) quedó cerrada. [SPEC-003](../specs/003-matias-documentos.md) se integró como documentación mediante PR #18; la Issue #19 quedó cerrada tras PR #47/#48. PR #51 integró el contrato común de trámites; PR #55 integró el consumidor C04 con el proveedor documental real y PR #56 la cabecera de trámite. PR #59 integró la entrega #54; PR #60/#61 cerraron #22/#23; PR #62 integró DOC-R04 (#24). La proyección del historial por versión en el detalle de gastos está implementada localmente en #49 y cuenta con validación focalizada aprobada en PostgreSQL; la rama aún espera revisión e integración. #28 conserva la integración conjunta, y #50 el recorrido/evidencia final.

Los IDs I2-C01…C06 siguientes son candidatos de planificación, no Issues creadas, compromisos del compañero ni tareas automáticamente Ready. Matías mantiene identidad/documentos; Franco, gastos/pagos. La revisión compartida se propone sin imponer disponibilidad o fechas.

## I2-C01 — ficha y contrato del consumidor (S1)

- Resultado: casos sintéticos de gasto/pago/documentos, capacidades por acción y objeto, ID de trámite, errores, repetición y fuentes de actor/fechas.
- Responsable/revisión: Franco prepara; Matías revisa las interfaces pertinentes por acuerdo.
- Requisitos/Plan: GP-01–06 como diseño; RF-003/004/005 parcial/006 y RF-001; F-E02, C01 e I01/I02/I03 en el alcance del consumidor.
- Dependencias: SPEC-002/003/009 y delimitación de #19; no exige proveedor terminado para preparar una propuesta.
- Cierre: reglas C01 A–D acordadas para esta demo; el contrato del puerto documenta entradas/garantías exigidas al proveedor. El proveedor real fue integrado en #51/#55 y la cabecera en #56; Q1–Q5 y cualquier política institucional siguen pendientes.
- Pruebas/evidencia: aceptación sin pago; documento ausente/ajeno/unknown; consulta sin capacidad de registro; actor falsificado; reenvío idéntico/distinto; fallo parcial; cronología. El acuerdo C01 conserva la evidencia de diseño; la integración ejecutable del consumidor se verifica en PR #55 y no se atribuye a la fase de diseño.
- Estado: reglas técnicas A–D acordadas para la demo; contrato de proveedor integrado en #51 y consumido en #55; cabecera integrada en #56. Q1–Q5 siguen pendientes como validación institucional.

## I2-C02 — resumen de seguimiento (S2)

- Resultado: detalle de solo lectura que muestra decisión y pago persistido por C03 como dimensiones separadas; la situación documental pendiente se distingue sin simular una revisión real.
- Responsable/revisión: Franco; revisión técnica y de interfaces pertinentes, sin sustituir al proveedor de Matías.
- Requisitos/Plan: GP-01/05 y preparación GP-02/06; RF-003/004/005 parcial/006, F-E04/F-E08 parciales y F-E10.
- Dependencias: contrato C01 de demo; el proveedor real no se requiere para mostrar el resumen del pago, pero sí para acreditar respaldo, pertenencia y estado documental.
- Cierre: aceptación no equivale a pago/cierre; proforma mantiene pendiente; factura aportada con revisión unknown no implica conformidad; sin mutar EstadoSolicitud, identidad o revisión documental.
- Pruebas/evidencia: casos propios/ajenos, pago/no pago, aporte/revisión, denegación sin exposición, determinismo y ausencia de mutaciones/efectos. Datos ficticios y resultado marcado como demo.
- Estado: resumen y cronología de solo lectura implementados en [PR #43](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/43) y formulario/selector en [PR #45](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/45). GP-01 y GP-04 verificados; proveedor real y vínculo del trámite disponibles en PR #55/#56. Los eventos y la navegación comunes se integraron mediante PR #59 (#54), y DOC-R04 mediante PR #62 (#24). La proyección contextual de revisiones por versión está implementada localmente en #49 y cuenta con pruebas focalizadas aprobadas en PostgreSQL; la integración conjunta permanece en #28 y la matriz/evidencia final se consolida en #50.

## I2-C03 — persistencia del hecho externo (S3)

- Resultado: registro autorizado de un pago efectuado fuera del sistema, con actor/fecha de registro del servidor, fecha del hecho, importe/moneda y referencias; registro y evento atómicos.
- Responsable/revisión: Franco; revisión de esquema, autoridad, repetición e interfaces compartidas con Matías por acuerdo.
- Requisitos/Plan: GP-03/04; RF-003/006, RNF-002/003, F-E07 parcial, F-E10 e I05.
- Dependencias: C01 resuelto técnicamente y alcance/costo de rehacer aceptados para esta demo; Q1/Q2 para autoridad real, Q3 para cardinalidad/correcciones, Q4 para respaldo institucional. La demo persistida es aislada/sintética y no habilita uso real.
- Cierre: permiso por objeto, importes precisos, actor independiente del formulario, fallo sin parcial; identidad de operación y conflicto de payload tratados según contrato. Importe/fecha no son por sí solos identidad única.
- Pruebas/evidencia: PostgreSQL de prueba, acceso directo denegado, precisión, recarga, fallo provocado, repetición y concurrencia proporcional; diff y comandos reales.
- Estado: implementado y probado en [PR #42](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/42) sobre PostgreSQL aislado, y en el recorrido UI/HTTP mediante [PR #45](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/45) (#40 cerrada). La implementación técnica no determina reglas institucionales.

## I2-C04 — consumidor documental real (S3)

- Resultado: consultar respaldo propio y proyectar pendientes sin confundir aporte/revisión ni conceder permisos por consultar.
- Responsable/revisión: Franco escribe consumidor; Matías mantiene documentos e identidad. Contrato común revisado por ambos; proveedor C01 integrado en #51.
- Requisitos/Plan: GP-02/05 y parte documental GP-06; RF-001/004/005 parcial/006, I02/I03 y F-E08 parcial.
- Dependencias: proveedor real C01 (#51) consumido en #55; vínculo de trámite en #56; DOC-R04 implementado en PR #62 (#24). Q4 sigue pendiente como regla institucional.
- Cierre: documento ajeno no respalda ni expone metadatos/archivo; proforma y factura aportada sin revisión no implican conformidad. La vista debe proyectar las revisiones existentes por versión sin cambiar el comportamiento de pago; mantener cobertura parcial hasta completar el recorrido de #50 y cerrar la evidencia GP-01–06.
- Pruebas/evidencia: integración real comprueba URL/objeto/almacenamiento/identidad de demo, asociaciones cruzadas y proyección de categorías según contrato. Pruebas focales y regresión en PR #55.
- Estado: consumidor integrado con el proveedor documental real y proyección parcial mediante [PR #55](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/55) en main; cabecera e integridad de trámite integradas en [PR #56](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/56) (#53 cerrada); DOC-R04 integrado mediante [PR #62](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/62) (#24). Issue #49 sigue abierta; la proyección del historial de cada versión está implementada localmente y su validación focalizada en PostgreSQL aprobó 52 pruebas (véase la evidencia). La rama aún no está integrada.

## I2-C05 — convergencia técnica (S4)

- Resultado: recorrido real GP-01–06, guía reproducible, evidencia criterio→versión→prueba y regresión S0.
- Responsable/revisión: Franco coordina; reproducción/revisión de Matías por acuerdo.
- Requisitos/Plan: RF-001/003/004/005 parcial/006/007 parcial, RNF aplicables; F-E04/07/08/09 parciales, F-E10/11/12 e I05/I06.
- Dependencias: C03/C04 reales integrados (#42/#55/#56) y DOC-R04 (#24); integración conjunta en #28. Las comprobaciones focales de GP-02 y GP-03 sobre un gasto pueden verificarse sin esperar #28.
- Cierre: todos los GP con evidencia real, denegaciones, atomicidad/repetición y cronología; dobles/CI verde no completan I2. Cierre técnico separado de aceptación institucional.
- Pruebas/evidencia: recorrido aceptado→respaldo→hecho externo→consulta/revisión, accesos y regresiones pertinentes, reproducción registrada. No sumar ejecuciones solapadas como nuevos casos.
- Estado: Issue #50 abierta. RUN02/RUN03 en el corte `53d90f8` aportan evidencia focal de UI para incorporación/reemplazo, permisos y registro de un pago; véase [`docs/evidence/i2-50-recorrido-gastos-ui.md`](../evidence/i2-50-recorrido-gastos-ui.md). La matriz completa GP-01–06, búsqueda/localización y el cierre de C05 siguen pendientes. El proveedor real y el vínculo están disponibles (#55/#56), DOC-R04 quedó integrado en PR #62 (#24), y navegación/eventos comunes en PR #59 (#54). La integración conjunta de ambos circuitos depende de #28. No sustituye #29.

## I2-C06 — devolución y cambios de hipótesis (S4)

- Resultado: Q1 etapas/datos, Q2 autoridad/correcciones, Q3 pagos/retenciones, Q4 documentos/revisión y Q5 regularización/cierre, vinculadas a supuestos/tareas.
- Responsable/revisión: Franco recoge gastos; Matías aporta interfaces por acuerdo; operadora/Marcos validan reglas.
- Requisitos/Plan: S-H1–5, RF-003/004/005/006, C02 y ajustes F-E02; no horas o validación acreditadas por una minuta propuesta.
- Dependencias: preguntas/casos se pueden enviar desde S1 sin reunión obligatoria; demo completa depende de C05. T07 de I1 puede aportar evidencia compartida, no aceptar I2 automáticamente.
- Cierre: cada respuesta confirmada/corregida/pendiente con fuente/fecha/ejemplo y ajuste trazado. Registrar cada respuesta y mantener explícitas las cuestiones pendientes; revisar con el propietario antes de cambiar interfaz.
- Pruebas/evidencia: minuta y cambios de spec; repetir únicamente pruebas afectadas si cambian reglas.
- Estado: candidato; respuestas institucionales Q1–Q5 pendientes.

## Cobertura parcial del Plan de Trabajo y próximo paso

F-E07 también exige comprobantes/retenciones, y F-E08 incluye cierre: este I2 recortado no los completa. F-E09 incluye resúmenes/totales además de filtros: S0 cubre sólo parte. I03 contempla integración documental real, no un doble. I06 contempla revisión mutua, no sólo revisión IA. I2-C01/C02 son IDs de tareas locales diferentes de C01/C02 académicos.

La entrega #54 se integró mediante PR #59; PR #60/#61 cerraron #22/#23 y PR #62 integró DOC-R04 (#24). #28, #49 y #50 permanecen abiertas. RUN02/RUN03 aportan observaciones focales de UI en `53d90f8`, pero la matriz y el recorrido completo de gastos para #50 siguen pendientes; pueden ejecutarse sin esperar #28. La comprobación conjunta de gastos y facturación sí depende de #28. Q1–Q5 y T07 siguen abiertos para validación institucional; T06 ya está cerrada. Mantener separados estado técnico y validación institucional.
