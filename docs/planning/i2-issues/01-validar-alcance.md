**Incremento:** I2  
**Specs:** [SPEC-004](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/004-matias-solicitudes-facturacion.md), [SPEC-009](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/009-matias-integracion-compartida.md); preguntas de SPEC-002/003/005/006/007.  
**Plan:** M-E01, M-E02, C01, C02.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez para interfaces; Cooperadora para reglas de operación.  
**Estado actual:** decisiones de facturación aceptadas por el director del
proyecto el 15/10/2026, según confirmación de Matías; acuerdo de contratos
compartidos A01–A05 confirmado por Franco en la propia Issue, sobre contratos
versionados anteriores. Detalles diferidos a Issues dependientes.

## Avance del relevamiento

El [inventario y recorrido respaldado por fuentes](01-relevamiento-fuentes.md)
separan situación actual, alcance del Plan de Trabajo y decisiones aún abiertas.
La [consulta priorizada a Cooperadora](01-consulta-cooperadora.md) recoge las
preguntas P01-P18 y los acuerdos internos A01-A05 con Franco. Las
[decisiones recibidas](01-decisiones-recibidas.md) registran qué reglas de
facturación aporta el documento presentado por Matías como validado por
Cooperadora, casos sintéticos y pendientes con responsables. Matías confirmó el
15/10/2026 el cargo de director del proyecto; no consta nombre ni minuta
separada. Franco confirmó
[A01–A05 en la Issue](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/20#issuecomment-6196767849),
con la precisión de que revisó contratos anteriores y no el nuevo registro
local. Éste identifica el contenido mínimo y los detalles diferidos.

P02 avanzó: la plantilla local marca 13 preguntas obligatorias en la primera
página, mientras fecha, número y archivo no llevan `*`. Para la nueva aplicación
se comunicó que esos tres datos son obligatorios si se declara un pago ya
presentado por banco o Mercado Pago, junto con validaciones de CUIT, correo e
importe. Sigue pendiente confirmar si se conservan las 13 exigencias originales.

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
