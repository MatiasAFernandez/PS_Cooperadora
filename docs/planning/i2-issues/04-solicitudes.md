**Incremento:** I2  
**Spec:** [SPEC-004](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/004-matias-solicitudes-facturacion.md).  
**Plan:** RF-002, M-E05. **Requisitos:** FAC-R01 a FAC-R04.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez para acceso, navegación e historial común.  
**Estado inicial:** Backlog.

## Resultado esperado

Recorrido en vistas y formularios Django para presentar y consultar solicitudes,
registrar observaciones de Cooperadora y correcciones del solicitante, con
persistencia y eventos. Usar los campos y transiciones validados en #20.

## Criterios de cierre

- Un formulario válido crea una solicitud con presentador y fecha fijados por el
  servidor; uno inválido no crea trámite ni evento.
- Lista y detalle muestran únicamente solicitudes autorizadas, incluso al pedir
  identificadores ajenos directamente.
- Sólo quien tenga la capacidad acordada observa o corrige; la corrección
  conserva la versión previa, la observación, los actores y las fechas.
- Una petición repetida, incompatible con el estado actual o sin CSRF válido
  no cambia el trámite ni duplica eventos.

## Dependencias, pruebas y evidencia

Depende de #21, #22 y reglas de #20. Pruebas de formulario, propiedad,
observación, corrección, persistencia y rechazo atómico en PostgreSQL.
Evidencia: PR y recorrido sintético solicitante - Cooperadora - solicitante.
Archivos, facturas y cobros se entregan en las Issues siguientes.
