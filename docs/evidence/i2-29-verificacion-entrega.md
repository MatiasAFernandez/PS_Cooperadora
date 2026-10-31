# Verificación y preparación de entrega I2 — #29

Estado al 31/10/2026: demo realizada el 29/10/2026 sobre
`09095a6d472bfcceeab21a4b371c7880f35e98c4`, según confirmación de Matías.
Ver [evidencia y devolución](demo-2026-10-29.md). Se recibieron pedidos de ajuste;
no se declara aceptación integral ni producción. Los apartados del 24/10 son
históricos. Las ampliaciones se siguen por separado en #30 y #76–#85.

Base de la preparación técnica: `c1f491f` (#69 integrada, con #65/#66/#68).
La PR #70 incorporó muestra, recuperación y guía tras la revisión de Franco.
La demostración posterior corresponde a `09095a6`; la actualización documental
conserva ambas versiones y sus resultados. Aporte de Matías con asistencia de
Codex; Franco mantiene gastos/pagos y la revisión de contratos comunes.
El estado operativo se conserva en #29/PR.

## Criterios y evidencia

| Criterio #29 | Fuente / resultado | Límite |
|---|---|---|
| Permisos, archivos inválidos, estados, importes y errores | #69 cerró técnicamente #28 con 598 pruebas; #70 verificó el comando de muestra y su CI aprobó 601 pruebas. | Son resultados de sus respectivos SHA; la actualización documental no los presenta como pruebas nuevas de aplicación. |
| Revisiones cruzadas | PR #62/#64/#67/#68/#69/#70 y #65/#66 integradas; #69 verifica el consumo común de los dos circuitos. | Las nuevas interfaces se revisan en sus propias issues. |
| Uso, contratos e instalación | Manuales de facturación y gastos, contratos de identidad/documentos, README y nueva [guía de entrega/recuperación](../guides/entrega-y-recuperacion-i2.md). | Demo local; sin despliegue, SSO o storage institucional. |
| Migración y recuperación | Migración desde base vacía; `pg_dump -Fc`, copia de storage y `pg_restore` en segunda base vacía; `migrate --check` y verificación de muestra correctos. | Ensayo lógico con escrituras detenidas, sin simular caída, pérdida de servidor ni RPO/RTO. |
| Demostración e informe | Recorridos completos de gastos y facturación mostrados el 29/10; [devolución registrada](demo-2026-10-29.md) e índice del plan individual debajo. | Los escenarios técnicos no recorridos conservan su evidencia anterior. |
| Aceptación funcional | Cooperadora aportó observaciones sobre el flujo completo y necesidades de evolución, con fuentes y tiempos en la ficha de demo. | Devolución funcional registrada y validación abierta de reglas específicas; sin aprobación integral ni habilitación productiva. |

## Ensayo técnico de recuperación — 24/10/2026

PostgreSQL 18.6 en loopback, Python 3.14.7 y Django 5.2.17. Bases nuevas
`entrega29_origen` y `entrega29_restaurada`; almacenamiento privado distinto para
cada una. Sin servidor web activo ni escrituras concurrentes. Datos y PDFs
enteramente sintéticos. Los dumps, manifiestos y bytes permanecen en `.local/`.

1. `migrate --noinput` aplicó todas las migraciones desde cero, incluidas las
   guardas terminales 0012; `muestra_entrega crear` preparó dos trámites y cuatro
   versiones documentales con sus hechos mediante los servicios reales.
2. `pg_dump -Fc --no-owner` generó el respaldo; se copió todo el directorio de
   archivos y se restauró en la segunda base mediante `pg_restore --exit-on-error
   --no-owner`, sin limpiar ni sobrescribir una base existente.
3. `migrate --check` no encontró migraciones pendientes. `muestra_entrega verificar`
   comparó las huellas de filas de comunes/gastos/facturación/documentos, grupos
   de cuentas y bytes: resultado correcto.
4. Las cuatro descargas del titular devolvieron los bytes correspondientes;
   las cuatro peticiones ajenas devolvieron 404, como se esperaba. El comando
   no toma un 404 ajeno como fallo de recuperación.
5. Tres pruebas automatizadas verifican muestra, detección de bytes alterados,
   rechazo de repetición sobre base poblada, demo deshabilitada y usuarios previos:
   **3 passed in 6.00s**. No sustituyen el ensayo real de dump/restore.

La recuperación conserva versiones, vínculos de pago, revisiones, importes,
historial y estado terminal; las huellas no incluyen passwords ni sesiones.
No se declara demostración visual: el ensayo usa servicios y cliente HTTP Django.

Validación conjunta del corte: `pytest tests/integracion
tests/identidad/test_navegacion_comun.py -q` terminó con **111 passed in 34.32s**.
Ruff, formato del comando/tests, `manage.py check`, `makemigrations --check
--dry-run` y `git diff --check` aprobados. Los conjuntos se solapan y no se suman;
la CI de la PR verifica la suite completa de su SHA.

## Actividades del plan individual de Matías

Fuente: Plan de Trabajo de Matías, tabla de actividades. Corte: 31/10/2026.

| Tarea | Resultado y evidencia | Estado | Horas del plan |
|---|---|---|---:|
| M-E01 | Relevamiento de formularios y documentos; [inventario](../planning/i2-issues/01-relevamiento-fuentes.md). | Completada | 8 |
| M-E02 | Reglas, modelo y casos de aceptación en [specs 002–009](../specs/README.md). | Completada para el corte demostrado | 10 |
| C01 | Responsabilidades y [contratos comunes](../contracts/i2-tramites-provider-matias.md); #20/#22. | Completada | 4 |
| C02 | Ejemplos, decisiones y [devolución de Cooperadora](demo-2026-10-29.md); #20/#29. | Realizada; ampliaciones en seguimiento | 6 |
| M-E03 | Identidad y capacidades; [verificación #21/#23](i2-21-23-verificacion-tecnica.md), SPEC-002. | Completada | 16 |
| M-E04 | Almacenamiento, metadatos y autorización; SPEC-003, #19/#24. | Completada | 20 |
| M-E05 | Solicitud, consulta, observación y corrección; [#23](i2-23-cierre-solicitudes.md), PR #52. | Completada | 12 |
| M-E06 | Facturas y notas externas; [#25](i2-25-comprobantes-externos.md), PR #64. | Completada | 8 |
| M-E07 | Cobros y respaldos de ingreso; [#26](i2-26-cobros-externos.md), PR #67. | Completada | 18 |
| M-E08 | Estados, historial, pendientes y cierre; [#27](i2-27-resolucion-facturacion.md), PR #68. | Completada | 10 |
| M-E09 | Filtros integrados en #71/#73; [resúmenes en #30](../specs/008-matias-consultas.md). | Parcial: faltan resúmenes | 8 |
| M-E10 | Pruebas funcionales, permisos, errores e integridad; evidencias #23–#28 y CI #70. | Completada para el corte demostrado | 14 |
| M-E11 | [Manual de facturación](../guides/recorrido-facturacion-i2.md) y contratos de identidad/documentos. | Completada | 6 |
| M-E12 | Organización de resultados en esta ficha e índice de fuentes para el informe. | Informe individual en preparación | 6 |
| I01 | Modelo común, relaciones y restricciones; [#22](i2-22-cierre-contratos.md). | Completada | 10 |
| I02 | Accesos permitidos y denegados en ambos circuitos; [#28](i2-28-integracion-circuitos.md). | Completada | 6 |
| I03 | Documentos, facturas, cobros y consumidor real C01; #51/#55/#65/#66/#69. | Completada | 8 |
| I04 | Navegación y presentación común; #59/#69/#71/#73. | Completada | 4 |
| I05 | Escenarios cruzados y consistencia; [#28](i2-28-integracion-circuitos.md), PR #69. | Completada | 8 |
| I06 | Revisión de cambios de gastos/contratos y revisión de facturación por Franco; #65/#66/#68/#69/#70. | Completada para el corte demostrado | 6 |
| I07 | Datos, demostración de ambos recorridos y [observaciones del 29/10](demo-2026-10-29.md). | Completada | 6 |
| I08 | Migraciones, datos sintéticos y [guía de instalación/recuperación](../guides/entrega-y-recuperacion-i2.md); ensayo de PR #70. | Completada | 6 |
| Total | Plan individual de Matías | | 200 |

## Alcance de aceptación y continuidad

La demo recorrió ambos circuitos desde la solicitud hasta la actuación de
Cooperadora, con validación, respaldos y decisión operativa según cada módulo.
La [ficha de demo](demo-2026-10-29.md) distingue lo mostrado, las necesidades
confirmadas y las definiciones abiertas. La devolución respalda el recorrido y
requiere ajustes; no constituye aceptación de toda excepción ni uso productivo.

Los cambios nuevos se gestionan en #30 y #76–#85, con sus dependencias y
responsables. #30 mantiene prioridad SHOULD. #50 conserva la evidencia y
demostración del tramo de Franco. La integración de esta documentación no
declara implementadas las propuestas SPEC-014–018 ni modifica los contratos
operativos vigentes por sí sola.
