# Acta tecnica I1-T06: verificacion en curso

- Issue: [#8](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/8).
- Fecha del registro asistido: 2026-10-12.
- Base: `0a9939b59e03f84d5d1c6df9839af76793df0d63` (`main`). Verificacion
  local de los ajustes en `codex/8-demo-evidence`, [PR #37](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/37).
- Guia de reproduccion: [recorrido tecnico I1](../guides/recorrido-tecnico-i1.md).
- Estado: **reproduccion independiente de Matias completada**; no apta para
  cierre hasta el recorrido de Franco y la conformidad de ambos con el acta.

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
acta. No se adjuntaron capturas y queda pendiente acordar la evidencia final.

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

- [ ] Franco ejecuta y registra el recorrido de formularios, decisiones,
  historial y mensajes H4 con las cuatro cuentas sinteticas.
- [x] Matias preparo las cuentas sinteticas y reprodujo el recorrido de forma
  independiente, comprobando el contrato de identidad en gastos y las
  denegaciones por objeto.
- [ ] Adjuntar capturas sin datos reales ni secretos que cada integrante acuerde
  como evidencia de su reproduccion.
- [ ] Anotar defectos encontrados, su correccion y nueva prueba, o mantener la
  Issue abierta si afectan criterios de aceptacion.
- [ ] Ambos revisan y acuerdan este acta, consignando limitaciones y preguntas
  para Cooperadora. La validacion operativa se realiza en #9.

| Integrante | Entorno y commit | Fecha | Resultado y evidencia | Conformidad |
|---|---|---|---|---|
| Franco | Pendiente | Pendiente | Pendiente | Pendiente |
| Matias | Windows; Python 3.14.7, PostgreSQL 18.6; PR #37 (`2196c6f`) | 2026-10-12 | 107 pruebas aprobadas; recorrido A/O/B/L, historial, H4 y denegaciones; confirmo que constituye su reproduccion independiente. Sin capturas adjuntas. | Pendiente de acuerdo final del acta |
