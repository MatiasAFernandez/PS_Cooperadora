# I2 - paquete de Issues de Matías

Estado: Issues [#20 a #30](https://github.com/MatiasAFernandez/PS_Cooperadora/issues?q=is%3Aissue+is%3Aopen+%5BI2%5D)
publicadas el 09/10/2026 y asignadas a Matías. Los IDs `I2-01` a `I2-11` son
referencias locales; el número real figura en la tabla. La publicación no
acredita validación de Cooperadora ni inicio de implementación.

Se cotejó además con `main` y con el borrador I2 de Franco en
`origin/codex/i2-consulta-estados`. Ya se registra
[Issue #19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19) para el
primer tramo de SPEC-003 (DOC-R01–R03), y [#15](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/15)
y [#16](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/16) para I2 de
gastos. Este paquete no los recrea ni supone que estén terminados.

El Plan de Trabajo define una entrega incremental, pero no fija el contenido de
un incremento llamado I2. Este paquete propone I2 como el recorrido de
facturación y cobros de Matías, sus componentes comunes y la integración
necesaria. La prioridad MUST/SHOULD proviene del plan; el orden de Issues es una
propuesta técnica del equipo.

## Validación de las specs contra el plan

| Spec | Cobertura del plan | Resultado de la revisión |
|---|---|---|
| [002](../../specs/002-matias-identidad-permisos.md) | RF-001, RNF-001, M-E03, I02 | Alineada. El adaptador sintético de I1 ya existe en `identidad`; I2 debe ampliar capacidades y probar el consumidor facturación, sin rehacer T02 ni prometer autenticación institucional. |
| [003](../../specs/003-matias-documentos.md) | RF-004, RNF-001/004, M-E04, I03 | Alineada. En `origin/main`, el primer tramo DOC-R01–R03 ya está preparado para #19; I2-05 cubre DOC-R04 sin duplicarlo. Política de revisión y ubicación de prueba siguen sin validar. RF-005 sobre deuda tras un pago de gastos corresponde a Franco. |
| [004](../../specs/004-matias-solicitudes-facturacion.md) | RF-002, M-E01/02/05 | Alineada. El formulario y la entrevista ya están inventariados para #20; falta confirmar obligatoriedad, actores, observaciones y transiciones antes de fijar reglas de implementación. |
| [005](../../specs/005-matias-facturas-notas.md) | RF-002, M-E06, I01/03 | Alineada. Se registran operaciones externas; no se emiten comprobantes ni se integra Exubio por API. Falta validar campos, unicidad y efecto de notas. |
| [006](../../specs/006-matias-cobros.md) | RF-002, RNF-002/003, M-E07, I03 | Alineada. Faltan imputación, cobros parciales y moneda; las pruebas deben cubrir precisión y atomicidad. |
| [007](../../specs/007-matias-seguimiento-cierre.md) | RF-002/006, RNF-002, M-E08 | Alineada. El historial base se acuerda al modelar la solicitud; cancelación y cierre esperan las reglas de Cooperadora. |
| [008](../../specs/008-matias-consultas.md) | RF-007, RNF-003, M-E09 | Alineada para facturación; el plan pide consultas de ambos circuitos y Franco debe cubrir gastos. RF-007 es SHOULD: su implementación se confirma tras el recorrido MUST. |
| [009](../../specs/009-matias-integracion-compartida.md) | I01-I05 | Alineada. Sus contratos acompañan el desarrollo; I06-I08 y M-E10 a M-E12 se trazan aquí como tareas de verificación y entrega, no como reglas nuevas de la spec. |

El plan también exige M-E10 (pruebas y defectos), M-E11 (manual y contratos),
M-E12 (informe individual), I06 (revisión cruzada), I07 (demostración) e I08
(migraciones, datos y recuperación). Esas actividades figuran en I2-10. Las horas
del plan son estimaciones académicas por actividad: no se trasladan a las Issues
porque éstas reagrupan resultados y no hay horas ejecutadas acreditadas.

## Orden de desarrollo

| Orden | Issue y título | Spec principal | Depende de | Esfuerzo y prueba | Prioridad / situación inicial |
|---|---|---|---|---|---|
| 1 | [#20](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/20) ([I2-01](01-validar-alcance.md)) Validar el recorrido de facturación y los contratos compartidos | 004, 009 | Ninguna | Bajo en código; requiere validación humana | MUST; En Curso: [inventario](01-relevamiento-fuentes.md) y [preguntas](01-consulta-cooperadora.md); aún no aprobada |
| 2 | [#21](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/21) ([I2-02](02-identidad-facturacion.md)) Extender identidad y permisos a facturación | 002 | #20 (matriz mínima) y #4 de I1 | Bajo-medio; reutiliza componente probado | MUST; Backlog |
| 3 | [#22](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/22) ([I2-03](03-modelo-contratos.md)) Acordar e integrar el modelo y los contratos comunes | 009 | #20; revisión de Franco | Medio; migraciones e integridad cruzada | MUST; Backlog |
| 4 | [#23](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/23) ([I2-04](04-solicitudes.md)) Presentar, consultar, observar y corregir solicitudes de facturación | 004 | #21/#22 y reglas de #20 | Medio; flujo, permisos e historial inicial | MUST; Backlog |
| 5 | [#24](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/24) ([I2-05](05-documentos.md)) Registrar la revisión documental y su trazabilidad | 003 | #19, #21/#22 y regla de revisión de #20 | Medio; acciones y pruebas de autorización | MUST; Backlog |
| 6 | [#25](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/25) ([I2-06](06-facturas-notas.md)) Registrar facturas y notas externas vinculadas | 005 | #23, #19 y datos de #20 | Medio; vínculos y duplicados | MUST; Backlog |
| 7 | [#26](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/26) ([I2-07](07-cobros.md)) Registrar cobros externos y sus comprobantes | 006 | #25, #19 y reglas de #20 | Alto; importes, imputación y atomicidad | MUST; Backlog |
| 8 | [#27](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/27) ([I2-08](08-seguimiento-cierre.md)) Completar estados, historial, pendientes y cierre de facturación | 007 | #23 a #26, #19 y reglas de #20 | Alto; transiciones y concurrencia | MUST; Backlog |
| 9 | [#28](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/28) ([I2-09](09-integracion-circuitos.md)) Integrar permisos, documentos y navegación de ambos circuitos | 009 | #21 a #27, #19 y entregables de gastos I1/I2 | Alto; pruebas entre módulos | MUST; Backlog |
| 10 | [#29](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/29) ([I2-10](10-verificacion-entrega.md)) Verificar, documentar y demostrar el circuito integrado | 009 (apoyo) | #28; validación funcional separada | Medio-alto; regresión y reproducción | MUST; Backlog |
| 11 | [#30](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/30) ([I2-11](11-consultas.md)) Agregar filtros y resúmenes operativos de facturación | 008 | #25 a #27; priorización confirmada | Medio; permisos y totales decimales | SHOULD; Backlog opcional |

Los órdenes 2 y 3 pueden avanzar en paralelo tras I2-01. La Issue #19 puede
avanzar después del identificador y las capacidades documentales acordadas, sin
esperar la revisión DOC-R04. I2-04 puede entregar
primero el alta y consulta, pero la Issue se cierra sólo con observación,
corrección e historial de esos eventos. El contrato de I2-05 puede prepararse
junto a I2-04; su implementación espera el proveedor de #19. I2-06 no
presupone cobro; I2-07 no presupone cancelación. I2-08
completa esas reglas después de verificar los datos vinculados. I2-11 puede
desarrollarse antes de la demostración final si Cooperadora confirma su prioridad;
no bloquea el cierre del recorrido MUST.

## Seguimiento e integración

Cada archivo numerado conserva el cuerpo de su Issue. Las dependencias de los
cuerpos publicados usan números reales, registrados también en las specs y esta
tabla. Las Issues están asignadas a Matías; no se duplican #4 ni #19.
[WORKFLOW](../../WORKFLOW.md) propone un GitHub Project compartido. Para estas
Issues, usar únicamente los estados `Backlog`, `Ready`, `En Curso`, `Revisión` y
`Terminado`; el incremento `[I2]`, la spec y el responsable quedan identificados
en las Issues y sus enlaces, sin agregar campos al Project.

Una Issue pasa a `Ready` de implementación sólo con alcance y aceptación
verificables, responsable, dependencias resueltas y reglas operativas necesarias
confirmadas por quien corresponda. Registrar la causa y el responsable de cada
bloqueo. Las PR siguen [CONTRIBUTING](../../../CONTRIBUTING.md): rama corta desde
`main`, Issue enlazada, pruebas y revisión cruzada en cambios compartidos. Una
prueba técnica no sustituye la devolución funcional de Cooperadora.
