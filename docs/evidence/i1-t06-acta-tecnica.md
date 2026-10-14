# Acta tecnica I1-T06: verificacion en curso

- Issue: [#8](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/8).
- Fecha del registro de Matias: 2026-10-12; ampliacion de Franco: 2026-10-14.
- Base: `0a9939b59e03f84d5d1c6df9839af76793df0d63` (`main`). Verificacion
  local de los ajustes en `codex/8-demo-evidence`, [PR #37](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/37).
- Guia de reproduccion: [recorrido tecnico I1](../guides/recorrido-tecnico-i1.md).
- Estado: **recorridos independientes de Matias y Franco registrados**. La
  conformidad final de ambos con el acta y la seleccion de evidencia sigue pendiente.

## Evidencia comprobada

| Control | Resultado | Evidencia o limite |
|---|---|---|
| `ruff check .` local | Aprobado | `All checks passed!` en este checkout. |
| `python manage.py check` local | Aprobado | `System check identified no issues (0 silenced)`. |
| Migraciones en PostgreSQL 18.6 | Aprobadas | `migrate --noinput` aplico todas las migraciones. `makemigrations --check --dry-run`: `No changes detected`. |
| `pytest -q` local | Aprobado | 107 pruebas aprobadas con Python 3.14.7 y PostgreSQL 18.6, incluidas concurrencia, CSRF y CT-01 a CT-08. Un aviso no funcional de escritura de `.pytest_cache` en Windows. |
| CI de `main` con PostgreSQL 17 | Aprobada | [Ejecucion 37983344296](https://github.com/MatiasAFernandez/PS_Cooperadora/actions/runs/37983344296): lint, checks Django y 107 pruebas aprobadas (`107 passed in 4.09s`). Incluye pruebas de concurrencia en PostgreSQL y CT-01 a CT-08. |
| CI de la PR #37 | Aprobada | [Ejecucion 38294033563](https://github.com/MatiasAFernandez/PS_Cooperadora/actions/runs/38294033563) para `2196c6f`. |
| Integracion de identidad en gastos | Revisada en codigo | `gastos/auth.py` importa `resolve_actor` y `has_capability` de `identidad.services`; las vistas y servicios de gastos consumen esa interfaz. No implica validacion institucional. |
| Recorrido en navegador | Aprobado en prueba asistida | A presento solicitudes sinteticas #1 y #2; O postergo #1 con motivo y luego la acepto, y rechazo #2 con motivo. A consulto los historiales y mensajes H4 tras recargar. B tuvo lista vacia y 404 por URL directa. L consulto ambas sin controles de decision. Los logs de este recorrido no contienen 500. |
| Navegacion por capacidad | Corregida y verificada | O y L veian enlaces de presentacion que conducian a 403. La PR oculta esos enlaces sin cambiar la denegacion en el servidor; pruebas enfocadas y suite completa aprobadas. |

Matias confirmo que la prueba local asistida descrita arriba constituye su
reproduccion independiente. Se realizo en su entorno con apoyo de Codex; no es
una reproduccion atribuible a Franco ni supone la conformidad de ambos con el
acta. No se adjuntaron capturas de ese recorrido y queda pendiente acordar la evidencia final.

## Entorno y limites de la prueba

El servicio nativo PostgreSQL 18.6 existente escucha en `127.0.0.1:5432` y
requiere una clave no configurada en el proyecto. No se modifico ese servicio
ni ninguna de sus bases. Para la prueba se creo un cluster temporal separado
en la carpeta temporal de Windows y se escucho solo en `127.0.0.1:55432`.
Se uso autenticacion `trust` solo en este cluster de datos sinteticos, nunca
en la instancia existente ni en un entorno real. La configuracion de Django
se paso por variables del proceso; no se creo `.env` ni se guardaron claves en
Git. Las contrasenas efimeras de A, B, O y L se invalidaron al terminar.
El servidor de desarrollo y el cluster temporal quedaron detenidos.

Podman continua bloqueado por WSL2 (`HCS_E_SERVICE_NOT_AVAILABLE`), pero ya no
impide la prueba porque PostgreSQL funciona nativamente. Los resultados locales
en Python 3.14/PostgreSQL 18 complementan, no reemplazan, la CI de Python 3.11/
PostgreSQL 17. La consulta SQL final registro `#1 aceptada` version 2,
`#2 rechazada` version 1 y tres eventos de decision en el orden esperado.

## Pendientes para el cierre

- [x] Franco ejecuta y registra el recorrido de formularios, decisiones,
  historial y mensajes H4 con las cuatro cuentas sinteticas.
- [x] Matias preparo las cuentas sinteticas y reprodujo el recorrido de forma
  independiente, comprobando el contrato de identidad en gastos y las
  denegaciones por objeto.
- [x] Adjuntar y organizar capturas sinteticas aportadas por Franco, con indice.
- [ ] Ambos acuerdan la seleccion final de evidencia de sus reproducciones.
- [ ] Anotar defectos encontrados, su correccion y nueva prueba, o mantener la
  Issue abierta si afectan criterios de aceptacion.
- [ ] Ambos revisan y acuerdan este acta, consignando limitaciones y preguntas
  para Cooperadora. La validacion operativa se realiza en #9.

| Integrante | Entorno y commit | Fecha | Resultado y evidencia | Conformidad |
|---|---|---|---|---|
| Franco | Windows; Python 3.11.9, Django 5.2.17, PostgreSQL 17.11; ensayo combinado `60f21f1` (#37 + #17) | 2026-10-14 | Recorrido manual A/O/B/L, recargas, historial, H4, filtros y lectura de solicitud abierta #3; [indice de capturas y limites](i1-t06-franco/README.md). 151 pruebas combinadas aprobadas y controles tecnicos complementarios registrados por separado. | Pendiente de acuerdo final del acta |
| Matias | Windows; Python 3.14.7, PostgreSQL 18.6; PR #37 (`2196c6f`) | 2026-10-12 | 107 pruebas aprobadas; recorrido A/O/B/L, historial, H4 y denegaciones; confirmo que constituye su reproduccion independiente. Sin capturas adjuntas. | Pendiente de acuerdo final del acta |

## Reproduccion de Franco, 14/10/2026

Franco realizo el recorrido manual en su entorno y confirmo los resultados paso
a paso. La version recorrida combina el head `35be7cc` de #37 con el head
`85dbd54` de #17 sobre main `0a9939b`, congelada en
[`60f21f156c2d30ce7240cb10ce0308071f80daa1`](https://github.com/MatiasAFernandez/PS_Cooperadora/tree/60f21f156c2d30ce7240cb10ce0308071f80daa1).
Por tanto, las pruebas de filtros y sus capturas tambien incluyen #17; no se
atribuyen a #37 aislada.

- A presento #1 (ARS 45000, laboratorio de prueba); O la postergo y luego acepto.
  A verifico al recargar estado aceptada, version 2, dos eventos y mensaje H4 de
  presupuesto/factura por aportar.
- A presento #2 (ARS 85000, administracion de prueba); O la rechazo con motivo.
  A verifico al recargar rechazada/version 1 y el evento con motivo.
- B comprobo listado sin las solicitudes de A y Not Found por las URLs directas
  de #1 y #2. L consulto ambos detalles e historiales.
- Para no confundir restriccion por estado terminal con restriccion por permiso,
  Franco creo #3 como A y verifico que L puede consultar una solicitud presentada
  sin controles de decision. Tambien exploro filtros y motivos obligatorios.

Los controles tecnicos complementarios se distinguen del recorrido manual:
151 pruebas aprobadas en 15,47 s sobre PostgreSQL 17.11 (las 44 de filtros estan
incluidas); Ruff, check Django y migraciones sin cambios pendientes. Una peticion
HTTP real como L a #3, con sesion y CSRF validos, recibio 403; las solicitudes,
versiones y eventos no cambiaron. CT-05 (auto-decision y decidir sin visibilidad)
queda cubierto por la suite, no por una nueva accion manual atribuida a Franco.
Los logs inspeccionados del recorrido no mostraron respuestas 500.

### Interrupcion y limites de la evidencia

Durante el primer tramo se interrumpio el entorno y se reinicio PostgreSQL.
La base temporal estaba en memoria y perdio sus datos. No fue un fallo de la
operacion de gastos: antes de la interrupcion el log registra la aceptacion con
redireccion correcta. Se preservo ese registro, se preparo una base sintetica con
volumen persistente y Franco repitio el tramo; no se reconstruyeron filas para
simular recuperacion. No se cuentan ambas corridas como casos nuevos distintos.

El conjunto de capturas puede contener momentos anteriores y posteriores a esa
repeticion. El indice conserva sus fuentes y no las presenta como una secuencia
temporal unica. No contiene claves, cookies, datos reales ni rutas personales.
Una imagen respalda lo que muestra; el actor y la recarga se acreditan con el
relato directo de Franco y las comprobaciones correspondientes, no se infieren
solo por ausencia de botones.

Se registro un mensaje de validacion duplicado y la oferta de Postergar cuando
ese estado no admite otra postergacion segun el recorte actual. Son observaciones
de interfaz que no produjeron cambios indebidos ni alteran el resultado de las
garantias verificadas. La nueva accion de observacion/pedido de informacion fue
aceptada conceptualmente por Franco y Matias segun el reporte de Franco; requiere
criterios propios antes de implementarse. Rectificar una decision por error es
otra necesidad registrada, todavia por definir. Ninguna se incorpora ni se declara
resuelta por estas capturas.

La guia/acta anterior de #14 conserva evidencia historica y detalles de escenarios;
no se elimina ni se integra automaticamente junto con #37. Este aporte completa
el acta de #37 para revision conjunta. No cierra #8 ni acredita la devolucion
institucional de H1-H4, que sigue en #9.
