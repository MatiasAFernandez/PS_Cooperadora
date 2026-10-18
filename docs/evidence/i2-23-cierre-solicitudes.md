# Verificación de #23 — solicitudes de facturación

Fecha: 18/10/2026. Base de comprobación:
`a708526a859e92de257c88bc0ba854565f7ec98b`, con #52 y #59 integradas y #22
cerrada. Trabajo realizado con asistencia de Codex por indicación de Matías.
Se conserva la implementación funcional; este delta agrega aceptación HTTP y
concilia la documentación de cierre.

## Criterios y evidencia

| Criterio | Verificación |
|---|---|
| FAC-R01: alta válida con identidad/fecha del servidor; inválida sin trámite/evento | `test_aceptacion_issue_23.py`: formulario inválido sin cabecera/solicitud/evento; alta válida rechaza identidad/estado inyectados. `test_recorrido.py`: importes, CUIT, catálogos y D01. |
| FAC-R02: lista/detalle sólo autorizados | A accede a su trámite; B recibe lista vacía/404; L consulta sin observar. `test_autorizacion_objeto_y_servicio_directo` y pruebas de sesiones/revocación complementan acceso directo e identidad. |
| FAC-R03: observación/corrección autorizadas con versión previa, observación, actores y fechas | Ciclo HTTP A → O → A con CSRF válido; tres eventos, actores y horas del servidor, estado final PRESENTADA v3 y snapshots antes/después/observación atendida visibles. |
| FAC-R04: repetición, estado/versión incompatible y CSRF no alteran ni duplican | Reenvío del alta y de observación/corrección responde 409; corregir PRESENTADA u observar OBSERVADA con versión vigente también responde 409. POST sin CSRF responde 403. Se conserva una solicitud/cabecera y tres eventos. |
| Atomicidad, concurrencia y respaldos | `test_atomicidad.py`: conexiones independientes compiten por alta/observación/corrección, rollback ante fallo de evento y almacenamiento, recuperación de borrado y commit incierto. `test_migracion.py` conserva cabeceras/eventos. |

Los casos de la tabla son datos sintéticos. La nueva prueba completa el ciclo
de pantallas mediante Django Client con `enforce_csrf_checks=True`; no se
presenta como inspección visual en navegador. Las pruebas existentes ya cubrían
las operaciones por servicio y rechazos HTTP por separado.

## Resultados ejecutados

Entorno: Python 3.14.7, Django 5.2.17, PostgreSQL 18.6 en instancia aislada con
base de prueba nueva y almacenamiento temporal. No se usan datos de Cooperadora.

| Comando | Resultado |
|---|---|
| `python -m pytest -q tests/facturacion tests/identidad/test_navegacion_comun.py --tb=short` | **62 passed in 17.67s**; incluye la nueva aceptación, migraciones, carreras, rollback y navegación común. |
| `python -m ruff check .` | Aprobado. |
| `python manage.py check` | Sin incidencias. |
| `python manage.py migrate --noinput` | Todas las migraciones aplicadas desde base vacía. |
| `python manage.py makemigrations --check --dry-run` | Sin cambios pendientes y con historia consistente. |
| `git diff --check` y enlaces relativos de cuatro documentos | Correctos. |

La suite completa de la base funcional se comprobó al cerrar #22: 459 pruebas
aprobadas y CI #90 correcta. Ese resultado es antecedente, no una nueva ejecución
de la suite completa con la prueba de #23. La PR de cierre registra el SHA y la
CI de este delta; los controles finales se detallan al cerrar la issue.

## Revisión e integración existentes

[PR #52](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/52), integrada
en `7ba783cb42fc6c20fc11c54eacb04baa0236fe93`, aprobada por Franco sobre
`0a8b9899d43933c8c94ba60d016b91356c6e8e17` el 16/10/2026 en horario argentino
(17/10 UTC). Su revisión verificó Actor, permisos por petición, API documental,
DTO, migraciones y compatibilidad con C04 sin defectos bloqueantes; registró
72 pruebas focales y controles/CI correctos, con los límites de su comprobación.
La navegación y el historial comunes de #59 fueron revisados e integrados al
cerrar #22. Esta entrega no atribuye a Franco revisión de la nueva prueba HTTP.

La [guía local](../guides/recorrido-facturacion-i2.md) permite preparar identidades
y repetir el ciclo. El [registro histórico](i2-21-23-verificacion-tecnica.md)
conserva los resultados iniciales y el recorrido interactivo anterior.

## Alcance y seguimiento operativo

Se verifica el perfil técnico de demo: PRESENTADA → OBSERVADA → PRESENTADA,
motivo no vacío y corrección por el titular con versión vigente. El ingreso
declarado permanece sin verificar. D01 exige fecha, operación y archivo sólo
con pago declarado por banco/Mercado Pago; no agrega restricciones para cuenta
corriente o respaldos opcionales.

Según #20, Matías recoge en #29 la validación de Cooperadora después de presentar
la demo: obligatoriedad de campos, catálogos, actores/visibilidad, excepciones y
rondas o transiciones adicionales. El cierre de #23 no acredita esa aceptación
ni define rechazo definitivo, SSO, revisión documental (#24), facturas/notas
(#25), cobros (#26), cierre/anulación (#27) o integración completa (#28).

No se incorporan los cambios previos del checkout original ni el trabajo de #57.
