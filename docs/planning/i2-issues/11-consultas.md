**Incremento:** I2; prioridad SHOULD, su ejecución requiere confirmación.  
**Spec:** [SPEC-008](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/008-matias-consultas.md).  
**Plan:** RF-007, RNF-003, M-E09. **Requisitos:** CON-R01 a CON-R04.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez para alcance y presentación comunes.  
**Estado inicial:** Backlog opcional.

## Resultado esperado

Búsqueda, filtros y resúmenes operativos de facturación y cobros con alcance
autorizado y totales reconstruibles. Cooperadora define antes los filtros y el
tratamiento de notas, cobros parciales y cancelaciones. Franco decide por su
parte las consultas del circuito de gastos exigidas por RF-007.

## Criterios de cierre

- Cada filtro devuelve sólo trámites autorizados, también ante parámetros
  manipulados y combinaciones de filtros.
- Cada total declara su conjunto y se reconstruye desde registros visibles o
  autorizados; conserva centavos y las reglas acordadas para notas y cobros.
- La consulta no sustituye la contabilidad externa ni añade gráficos o
  exportaciones sin alcance aprobado.
- Se confirma con Cooperadora que RF-007 sigue dentro de la entrega y qué
  criterios aplican a gastos y a facturación.

## Dependencias, pruebas y evidencia

Depende de #25, #26, #27 y priorización confirmada. Pruebas de autorización,
filtros combinados y totales decimales en PostgreSQL. Evidencia: PR, dataset
sintético, cálculo manual contrastado y definición aprobada de cada resumen.
