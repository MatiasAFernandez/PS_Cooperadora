**Incremento:** I2  
**Spec:** [SPEC-005](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/005-matias-facturas-notas.md).  
**Plan:** RF-002, M-E06, I01/I03. **Requisitos:** COM-R01 a COM-R04.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez para vínculos compartidos.  
**Estado inicial:** Backlog.

## Resultado esperado

Registrar y consultar facturas y notas emitidas fuera del sistema, con referencia
externa, procedencia, solicitud y respaldo protegido. Los datos, unicidad y
efectos de notas deben estar definidos en #20 antes de programarlos.

## Criterios de cierre

- Un operador autorizado vincula un comprobante externo válido a una solicitud
  existente y lo encuentra en el detalle con actor y fecha de registro.
- Un dato duplicado o vínculo inválido según las reglas acordadas se rechaza sin
  crear comprobante huérfano ni estado parcial.
- Un lector sin acceso a la solicitud no ve el registro ni descarga su respaldo
  por URL directa.
- Registrar una factura o nota no crea un cobro ni ejecuta operaciones en Exubio.

## Dependencias, pruebas y evidencia

Depende de #23, del componente documental de #19 y decisiones de #20; no
requiere completar DOC-R04 para registrar un respaldo. Pruebas de validación, asociación,
integridad, lectura autorizada/denegada y atomicidad en PostgreSQL. Evidencia:
PR y solicitud ficticia con factura y nota de procedencia identificable.
