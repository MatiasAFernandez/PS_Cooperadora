# I2 — seguimiento del gasto aceptado y pago externo

Fecha: 06/10/2026. Responsable de gastos/pagos: Franco Damián Sánchez. Preparación y revisión documental asistidas por Codex, con insumos de Gemini. **Plan compartido para revisión; no I2 completo ni aprobación de contratos reales.**

## Fuentes y revisión del plan

Comportamiento y aceptación: [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md). Consulta de apoyo: [SPEC-010](../specs/010-franco-consulta-gastos.md). Formato de tareas: [I1](i1-tareas.md). Método: [ciclo SDD](../specs/README.md) y [CONTRIBUTING](../../CONTRIBUTING.md). No se sustituye el Plan de Trabajo académico ni se instala otra metodología.

La revisión del 06/10 cotejó RF/RNF y actividades con la copia revisada del 13/09 del plan individual de Franco, y el alcance con las specs actuales. El [Plan de Trabajo compartido](https://docs.google.com/document/d/1W435Jlo6K-54DpCbqokJBdcfWaFOydkMNHgNvem1Oz4/edit) conserva su función académica; este cotejo no certifica que aquella copia sea la última versión presentada o aprobada por la cátedra. No se publica la copia con datos personales ni se acreditan sus horas estimadas como ejecutadas.

**Veredicto documental:** coherente para revisar y preparar los tramos S1/S2 con hipótesis visibles. S3 conserva decisiones materiales antes de esquema, permisos y registro persistente. La aprobación técnica de una demo no acredita acuerdo de Matías, reglas de Cooperadora, implementación integrada ni cierre institucional.

## Estado y orden de trabajo

- I1 T02–T05 están integrados. T06/[#8](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/8) conserva recorrido manual, reproducción independiente y acta; su guía está en [PR #14, Draft](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/14). T07/[#9](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/9) conserva devolución H1–H4. No se cierran por avanzar I2.
- S0: I2-T01/T02 (estado y concepto) están implementadas en [PR #17, Draft](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/17), para revisión e integración; son apoyo RF-007/F-E09, no el núcleo completo de I2.
- S1: preparar casos y contrato consumidor; revisión de ID/capacidades/documentos/repetición con Matías por acuerdo. No asumir que el contrato está acordado.
- S2: existe una demo sintética local de proyección, fuera de la aplicación y de este PR: siete pruebas y tres invariantes focales aprobados por Codex. No implementa pago, permisos de servidor o integración documental.
- S3: persistencia del hecho externo e integración del proveedor real. Requiere decisiones técnicas y supuestos pertinentes; no migrar por intuición.
- S4: convergencia técnica y devolución operativa, con evidencias separadas.

[Issue #15](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/15) sigue el incremento central; [#16](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/16), las consultas. [SPEC-003](../specs/003-matias-documentos.md) se integró como documentación mediante PR #18; [Issue #19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19), asignada a Matías, prepara DOC-R01–03. DOC-R04 e integración I03 no se dan por implementados. Trabajo privado de Matías desconocido.

Los IDs I2-C01…C06 siguientes son candidatos de planificación, no Issues creadas, compromisos del compañero ni tareas automáticamente Ready. Matías mantiene identidad/documentos; Franco, gastos/pagos. La revisión compartida se propone sin imponer disponibilidad o fechas.

## I2-C01 — ficha y contrato del consumidor (S1)

- Resultado: casos sintéticos de gasto/pago/documentos, capacidades por acción y objeto, ID de trámite, errores, repetición y fuentes de actor/fechas.
- Responsable/revisión: Franco prepara; Matías revisa las interfaces pertinentes por acuerdo.
- Requisitos/Plan: GP-01–06 como diseño; RF-003/004/005 parcial/006 y RF-001; F-E02, C01 e I01/I02/I03 en el alcance del consumidor.
- Dependencias: SPEC-002/003/009 y delimitación de #19; no exige proveedor terminado para preparar una propuesta.
- Cierre: ambas partes de cada interfaz acuerdan entradas/salidas/errores y casos permitidos/denegados; S-H1–5 confirmados o diferidos con punto/coste. No fijar cardinalidad, transporte o política institucional por defecto.
- Pruebas/evidencia: aceptación sin pago; documento ausente/ajeno/unknown; consulta sin capacidad de registro; actor falsificado; reenvío idéntico/distinto; fallo parcial; cronología. Revisión del contrato y registro de acuerdo, no tests del servidor inexistente.
- Estado: candidato parcial; preparación disponible, acuerdo no acreditado.

## I2-C02 — proyección sintética de seguimiento (S2)

- Resultado: detalle/política pura que distinga aceptación, hecho de pago, aporte documental y revisión, sin persistencia nueva.
- Responsable/revisión: Franco; revisión técnica y de interfaces pertinentes, sin sustituir al proveedor de Matías.
- Requisitos/Plan: GP-01/05 y preparación GP-02/06; RF-003/004/005 parcial/006, F-E04/F-E08 parciales y F-E10.
- Dependencias: casos C01 suficientes para esta demo, supuestos S-H visibles y plan técnico revisado antes de implementar; proveedor real no requerido para prototipo aislado.
- Cierre: aceptación no equivale a pago/cierre; proforma mantiene pendiente; factura aportada con revisión unknown no implica conformidad; sin mutar EstadoSolicitud, identidad o revisión documental.
- Pruebas/evidencia: casos propios/ajenos, pago/no pago, aporte/revisión, denegación sin exposición, determinismo y ausencia de mutaciones/efectos. Datos ficticios y resultado marcado como demo.
- Estado: demo local producida; aplicación real e interfaces siguen pendientes. No GP integrados ni Ready inferidos.

## I2-C03 — persistencia del hecho externo (S3)

- Resultado: registro autorizado de un pago efectuado fuera del sistema, con actor/fecha de registro del servidor, fecha del hecho, importe/moneda y referencias; registro y evento atómicos.
- Responsable/revisión: Franco; revisión de esquema, autoridad, repetición e interfaces compartidas con Matías por acuerdo.
- Requisitos/Plan: GP-03/04; RF-003/006, RNF-002/003, F-E07 parcial, F-E10 e I05.
- Dependencias: C01 resuelto técnicamente, alcance S-H1–4 elegido y plan de datos revisado; Q1/Q2 para autoridad, Q3 para cardinalidad/correcciones, Q4 para respaldo. Demo persistida aislada sólo con alcance y coste de rehacer explícitamente aceptados, sin uso real.
- Cierre: permiso por objeto, importes precisos, actor independiente del formulario, fallo sin parcial; identidad de operación y conflicto de payload tratados según contrato. Importe/fecha no son por sí solos identidad única.
- Pruebas/evidencia: PostgreSQL de prueba, acceso directo denegado, precisión, recarga, fallo provocado, repetición y concurrencia proporcional; diff y comandos reales.
- Estado: candidato; sin migración, registro real ni implementación aprobada por este documento.

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

Próximo paso compartido: revisar C01 con Matías para ID, capacidades, documentos y repetición; conservar demo C02 como evidencia de presentación con supuestos. Puede avanzarse en preparación reversible mientras T06/T07 siguen abiertos. No iniciar C03/C04 ni cerrar contratos por la publicación de este plan; cada tramo necesita alcance suficiente y autorización vigente. No cambios automáticos en Issues/Project ni compromisos asignados al compañero.
