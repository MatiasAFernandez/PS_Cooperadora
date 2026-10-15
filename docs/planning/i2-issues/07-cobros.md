**Incremento:** I2  
**Spec:** [SPEC-006](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/006-matias-cobros.md).  
**Plan:** RF-002, RNF-002/003, M-E07, I03. **Requisitos:** COB-R01 a COB-R04.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez.  
**Estado inicial:** Backlog.

## Resultado esperado

Registrar cobros realizados externamente, sus importes decimales, facturas
asociadas y comprobantes de ingreso protegidos. Aplicar sólo las reglas de
imputación, moneda y parcialidad confirmadas en #20.

## Criterios de cierre

- Un cobro válido conserva referencia, procedencia, fecha, registrante, importe,
  vínculos y comprobante; el detalle permite reconstruir sus asociaciones.
- Un importe o vínculo no permitido se rechaza sin cobro, asociación o cambio
  parcial; importes con centavos conservan precisión decimal.
- Un usuario ajeno no consulta el cobro ni recupera el comprobante mediante
  identificador directo.
- Registrar el ingreso no mueve dinero ni presume cancelación del trámite.

## Dependencias, pruebas y evidencia

Depende de #25, del componente documental de #19 y reglas de #20. Pruebas de importes, vínculos múltiples
si fueron aprobados, atomicidad, permiso y descarga; PostgreSQL y documentos
ficticios. Evidencia: PR, cobro asociado y caso fallido sin cambios parciales.
