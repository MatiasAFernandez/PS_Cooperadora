**Incremento:** I2  
**Specs:** [SPEC-004](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/004-matias-solicitudes-facturacion.md), [SPEC-009](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/009-matias-integracion-compartida.md); preguntas de SPEC-002/003/005/006/007.  
**Plan:** M-E01, M-E02, C01, C02.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez para interfaces; Cooperadora para reglas de operación.  
**Estado actual:** En Curso; relevamiento de fuentes registrado, pendiente de
validación de Cooperadora y acuerdo técnico con Franco.

## Avance del relevamiento

El [inventario y recorrido respaldado por fuentes](01-relevamiento-fuentes.md)
separan situación actual, alcance del Plan de Trabajo y decisiones aún abiertas.
La [consulta priorizada a Cooperadora](01-consulta-cooperadora.md) recoge las
preguntas P01-P18 y los acuerdos internos A01-A05 con Franco. No hay todavía
minuta de confirmación posterior ni contratos compartidos aprobados; esta Issue
permanece abierta.

P02 está parcialmente respondida: la plantilla local de solicitud de factura
marca 16 preguntas obligatorias. Faltan la lógica condicional de la sección de
comprobante y las validaciones que regirán en la nueva aplicación.

## Resultado esperado

Inventario de formularios, ejemplos anonimizados, actores y documentos; recorrido
de facturación con campos, observación/corrección, factura, nota, cobro,
cancelación y cierre; matriz de permisos y responsabilidades; contratos de
identidad, documento, identificadores y evento acordados con Franco. Registrar
fuente, fecha y decisión, o dejar un bloqueo explícito cuando Cooperadora no
responda. Actualizar las specs afectadas en vez de asumir reglas faltantes.

## Criterios de cierre

- Los casos de aceptación describen un recorrido válido y casos de rechazo con
  datos sintéticos; se puede señalar qué regla soporta cada caso.
- Franco y Matías revisan propiedad de modelos, entradas/salidas, estados,
  errores y responsable de integración de los contratos compartidos.
- Cooperadora confirma o corrige campos, actores, documentos, imputación,
  observación, cancelación y cierre. Cada pendiente no resuelto tiene responsable
  y bloquea sólo las Issues que lo requieren.
- No se presenta una hipótesis de demo o una decisión técnica como aprobación
  institucional.

## Dependencias, pruebas y evidencia

Sin dependencia técnica. Revisar los ejemplos contra RF-001/002/004/006 y
RNF-001/002/003/004 del Plan de Trabajo. Evidencia: inventario, matriz,
contratos, casos de aceptación, revisión cruzada y minuta de Cooperadora.
