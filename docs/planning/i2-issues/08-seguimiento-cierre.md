**Incremento:** I2  
**Spec:** [SPEC-007](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/007-matias-seguimiento-cierre.md).  
**Plan:** RF-002/006, RNF-002, M-E08. **Requisitos:** SEG-R01 a SEG-R05.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez para contrato de eventos.  
**Estado inicial:** Backlog.

## Resultado esperado

Completar el historial iniciado con la solicitud, los estados, pendientes,
cancelación y cierre de facturación según las reglas confirmadas por Cooperadora.
Derivar los pendientes desde facturas, notas, cobros y revisión documental, sin
aplicar a gastos una regla que pertenece a otro circuito.

## Criterios de cierre

- Estado e historial muestran cada acción relevante con tipo, actor y fecha y
  siguen consultables tras cerrar el trámite.
- Cancelación y pendientes se reconstruyen desde registros relacionados conforme
  a la regla validada; una factura o cobro no cierra por sí solo salvo decisión
  explícita de Cooperadora.
- Sólo una capacidad de cierre y la ausencia de pendientes exigibles permiten
  cerrar; una petición repetida, concurrente o desde estado obsoleto no duplica
  eventos ni deja cambios parciales.
- El acceso al historial respeta el permiso sobre la solicitud.

## Dependencias, pruebas y evidencia

Depende de #23, #24, #25, #26, #19 y decisiones de #20. Pruebas de transiciones,
pendientes, concurrencia en conexiones PostgreSQL independientes, rollback e
historial posterior al cierre. Evidencia: PR, caso completo y cierre denegado
por un pendiente ficticio.
