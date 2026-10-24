# Verificación y preparación de entrega I2 — #29

Base: `c1f491f` (#69 integrada, con #65/#66/#68). Aporte de Matías con asistencia
de Codex; revisión cruzada de Franco pendiente sobre la PR de este corte. El
estado operativo se conserva en #29/PR. Esta ficha organiza evidencia, no sustituye
el informe oficial, el registro de horas ni una devolución de Cooperadora.

## Criterios y evidencia

| Criterio #29 | Fuente / resultado | Límite |
|---|---|---|
| Permisos, archivos inválidos, estados, importes y errores | Suite de facturación/documentos/identidad/integración; #69 cerró técnicamente #28 con 598 pruebas y revisión sobre `47652bb`. | El resultado histórico no se atribuye al nuevo código del comando. La CI de esta PR verifica su SHA. |
| Revisiones cruzadas | PR #62/#64/#67/#68/#69 y #65/#66 integradas; #69 verifica el consumo común de los dos circuitos. | Franco debe revisar la nueva guía/comando/evidencia de #29. |
| Uso, contratos e instalación | Manuales de facturación y gastos, contratos de identidad/documentos, README y nueva [guía de entrega/recuperación](../guides/entrega-y-recuperacion-i2.md). | Demo local; sin despliegue, SSO o storage institucional. |
| Migración y recuperación | Migración desde base vacía; `pg_dump -Fc`, copia de storage y `pg_restore` en segunda base vacía; `migrate --check` y verificación de muestra correctos. | Ensayo lógico con escrituras detenidas, sin simular caída, pérdida de servidor ni RPO/RTO. |
| Demostración e informe | Guion de ambos circuitos preparado; índice individual de evidencia debajo. | Demostración aún no realizada; horas reales no registradas. |
| Aceptación funcional | Matías confirmó el 24/10/2026 que todavía no se realizó la demostración. | Validación abierta: sin aceptación, fecha de aprobación ni observaciones atribuibles a Cooperadora. |

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

## Índice para el informe individual de Matías

| Actividad / resultado | Evidencia a enlazar | Horas reales |
|---|---|---|
| Identidad/capacidades y documentos comunes | Specs 002/003, contratos, #21/#22/#24 y sus PR/evidencias. | No registradas. |
| Solicitudes y correcciones | Spec 004, #23 y evidencia del recorrido. | No registradas. |
| Factura/notas externas e ingresos verificados | Specs 005/006, #25/#26, PR #64/#67. | No registradas. |
| Diagnóstico y resolución explícita | Spec 007, #27, PR #68 y correcciones SQL revisadas. | No registradas. |
| Integración cruzada con gastos | Spec 009, #28, PR #69 y matriz con contribuciones de ambos responsables. | No registradas. |
| Instalación, recuperación y preparación de demo | #29, esta ficha, guía, comando y CI del corte. | No registradas. |

Las horas disponibles son las **propuestas en la planificación**, según confirmó
Matías el 24/10/2026. No se convierten en ejecutadas, no se calculan desde commits
o duración de tests y no se inventa una reconstrucción retrospectiva. Cualquier
registro posterior debe tener fuente y diferenciar actividad, fecha, duración
real y evidencia; las estimaciones mantienen su categoría y referencia al plan.

## Registro pendiente de demostración y devolución

- Estado: **no realizada**, confirmado por Matías el 24/10/2026.
- Fecha y participantes efectivos: pendientes; no hay acta ni aprobación.
- Versión a mostrar y entorno: anotar SHA y configuración del ensayo futuro.
- Casos observados: seguir el guion; para cada uno registrar resultado, evidencia
  y observación textual o resumen validado, con su fuente.
- Reglas por validar: conservar H1–H4 y las consultas abiertas del incremento;
  separar correcciones técnicas de decisiones institucionales.
- Devolución de Cooperadora: pendiente, con fuente/fecha por incorporar cuando
  exista; una revisión de Franco o un check verde no la sustituye.

La PR técnica puede revisarse mientras esta validación permanece abierta; el
cierre de #29 requiere revisar sus criterios y conservar explícitos los pendientes,
sin afirmar una demostración que todavía no ocurrió. #30 es SHOULD y no bloquea
esta preparación. #50 conserva la demostración del tramo de Franco.
