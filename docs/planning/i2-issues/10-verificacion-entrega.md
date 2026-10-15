**Incremento:** I2  
**Spec de apoyo:** [SPEC-009](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/009-matias-integracion-compartida.md) y criterios de SPEC-002 a SPEC-007.  
**Plan:** M-E10, M-E11, M-E12, I06, I07, I08; RNF-005.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez; Cooperadora valida el recorrido operativo por separado.  
**Estado inicial:** Backlog.

## Resultado esperado

Dejar el circuito integrado verificable, instalable y defendible: corregir
defectos detectados, documentar uso y contratos, revisar cambios cruzados,
preparar datos y demostración, comprobar migración y recuperación de una muestra,
y organizar la evidencia del informe individual.

## Criterios de cierre

- Tests del módulo y de integración cubren permisos, archivos inválidos,
  consistencia de estados, importes, errores y operaciones no autorizadas;
  defectos que afectan criterios de aceptación se corrigen.
- Franco revisa facturación y Matías revisa los cambios de gastos y contratos
  compartidos; las incompatibilidades quedan resueltas.
- Manual de facturación, contratos de identidad/documentos y guía de instalación,
  migración y recuperación permiten repetir la verificación con datos sintéticos.
- La demostración reproduce ambos circuitos y registra observaciones; el informe
  individual enlaza resultados y horas reales, sin convertir estimaciones en
  horas ejecutadas.
- La aceptación funcional de Cooperadora consta con fuente y fecha; si sigue
  pendiente, se registra como validación abierta y no se afirma aprobación.

## Dependencias, pruebas y evidencia

Depende de #28. Evidencia: checks, resultados de pruebas, PRs y revisiones,
manual y guía, recuperación demostrada, acta de demo y registro de validación.
RF-007/ #30 no bloquea esta Issue mientras conserve prioridad SHOULD.
