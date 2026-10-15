**Incremento:** I2  
**Spec:** [SPEC-003](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/003-matias-documentos.md).  
**Plan:** RF-004, RNF-001/002, M-E10; complementa M-E04/#19. I03 se verifica en #28. **Requisito principal:** DOC-R04.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez.  
**Estado inicial:** Backlog.

## Resultado esperado

Completar la revisión documental y su trazabilidad sobre el primer tramo de
SPEC-003 documentado como [Issue #19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19)
(DOC-R01–R03). Cooperadora define quién revisa, qué resultados existen y cuándo
un documento satisface un pendiente. El componente conserva esa decisión sin
convertir una carga en aprobación automática.

## Criterios de cierre

- Sólo la capacidad documental acordada permite revisar un archivo perteneciente
  a un trámite accesible; una petición directa sin permiso no modifica nada.
- La revisión conserva resultado, actor y fecha y es consultable en el historial
  autorizado aun después de un cambio posterior de estado.
- Un documento cargado, rechazado o pendiente de revisión no satisface un
  requisito documental salvo que la regla del circuito lo permita explícitamente.
- Una revisión fallida o repetida no deja evento o resultado parcial.

## Dependencias, pruebas y evidencia

Depende de #19, #21, #22 y regla de revisión de #20. Pruebas en PostgreSQL:
revisión permitida/denegada, documento ajeno o inexistente, resultado inválido,
repetición y rollback. Evidencia: PR, contrato de revisión y documentos
sintéticos. Carga, tipo/tamaño, metadatos y recuperación siguen en #19; la
integración real con gastos se cierra en #28.
