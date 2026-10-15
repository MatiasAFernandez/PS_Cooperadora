**Incremento:** I2  
**Spec:** [SPEC-009](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/009-matias-integracion-compartida.md).  
**Plan:** I01, C01; soporte de M-E02 y M-E05. **Requisitos:** INT-R03/04.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez.  
**Estado inicial:** Backlog.

## Resultado esperado

Acordar con ejemplos de ambos circuitos los identificadores, relaciones e
integridad compartida; definir la forma mínima de eventos (tipo, actor, fecha)
que necesita la solicitud desde su primera presentación. Implementar las
migraciones y contratos internos necesarios para #23 y los documentos, sin
imponer un único mapa de estados a gastos y facturación.

## Criterios de cierre

- La matriz de responsabilidades asigna propietario y revisor a cada dato e
  interfaz común; Franco aprueba ejemplos de gastos y Matías los de facturación.
- Relaciones válidas persisten y referencias inexistentes o cruzadas se rechazan
  sin cambios parciales en PostgreSQL.
- El contrato de evento admite presentación, observación y corrección sin borrar
  acciones previas; cada módulo conserva sus transiciones.
- Migraciones y pruebas son reproducibles desde la base documentada.

## Dependencias, pruebas y evidencia

Depende de #20 y revisión cruzada. Pruebas de integridad, migración y registro
atómico de evento con casos sintéticos de los dos módulos. Evidencia: contrato
versionado, PR revisada y resultados de pruebas. El cierre funcional de
facturación queda en #27.
