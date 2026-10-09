**Incremento:** I2  
**Spec:** [SPEC-009](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/009-matias-integracion-compartida.md).  
**Plan:** I02 (permisos), I03 (documentos), I04 (navegación), I05 (escenarios). **Requisitos:** INT-R01 a INT-R05.  
**Responsable principal:** Matías Alejandro Fernández para componentes comunes y facturación. **Revisor e integrador del recorrido de gastos:** Franco Damián Sánchez.  
**Estado inicial:** Backlog.

## Resultado esperado

Integrar facturación con la identidad, documentos, relaciones, eventos y
navegación de la aplicación compartida. Verificar ambos recorridos juntos,
manteniendo la propiedad funcional de cada alumno y registrando los cambios de
contrato con revisión cruzada.

## Criterios de cierre

- Identidades ficticias con capacidades distintas obtienen accesos permitidos y
  denegados coherentes en gastos y facturación.
- Un documento de cada circuito se asocia al trámite correcto; la descarga
  directa ajena se deniega y las relaciones inválidas no dejan cambios parciales.
- Facturación se recorre desde la navegación común sin romper el recorrido de
  gastos; cada historial expone tipo, actor y fecha con reglas de estado propias.
- Franco revisa los contratos y los ejemplos de gastos; Matías revisa el uso de
  componentes compartidos desde facturación.

## Dependencias, pruebas y evidencia

Depende de #21 a #27, #19 y de los recorridos de gastos I1/I2 necesarios
para comprobar el consumidor documental real. Pruebas
cruzadas en PostgreSQL, acceso permitido/denegado, documentos y consistencia.
Evidencia: PRs revisadas, matriz de responsabilidades, resultados de pruebas y
dos recorridos sintéticos. Si gastos aún no está integrado, registrar bloqueo
con Franco como coordinador de ese tramo, sin declarar completa la Issue.
