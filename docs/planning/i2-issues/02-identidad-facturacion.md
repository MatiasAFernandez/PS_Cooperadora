**Incremento:** I2  
**Spec:** [SPEC-002](https://github.com/MatiasAFernandez/PS_Cooperadora/blob/main/docs/specs/002-matias-identidad-permisos.md).  
**Plan:** RF-001, RNF-001, M-E03, I02. **Requisitos:** ID-R01 a ID-R04.  
**Responsable principal:** Matías Alejandro Fernández. **Revisor:** Franco Damián Sánchez.  
**Estado inicial:** Backlog.

## Resultado esperado

Extender el componente `identidad` ya implementado para I1 con capacidades
explícitas de facturación acordadas en #20. El módulo de facturación consume
`resolve_actor` y `has_capability` y aplica propiedad y permisos por objeto en
listas, detalle y acciones. Conservar el adaptador sintético sólo para prueba,
sin convertirlo en autenticación institucional ni duplicar T02 de I1.

## Criterios de cierre

- Sin identidad válida se deniega operar; una identidad sin capacidad no puede
  presentar, revisar, registrar ni cerrar según la matriz validada.
- Un solicitante no obtiene ni modifica trámites ajenos por lista, URL directa o
  petición de acción. Una capacidad global de lectura no implica capacidad de
  modificación.
- Cambiar o revocar una capacidad se refleja según el contrato acordado;
  `is_staff` y `is_superuser` no otorgan autoridad de negocio.
- Franco comprueba que ambos circuitos reciben la misma estructura de actor y
  que las reglas de propiedad quedan en cada módulo.

## Dependencias, pruebas y evidencia

Depende de #20 y del componente I1 existente. Pruebas de sesiones válidas,
ausentes e inactivas, acceso propio/ajeno, rutas directas, acciones denegadas y
revocación. Evidencia: PR, matriz de capacidades y pruebas de integración
contra los dos consumidores cuando esté disponible #28.
