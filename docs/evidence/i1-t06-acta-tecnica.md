# Acta tecnica I1-T06: verificacion en curso

- Issue: [#8](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/8).
- Fecha del registro asistido: 2026-10-12.
- Revision verificada: `0a9939b59e03f84d5d1c6df9839af76793df0d63` (`main`).
- Guia de reproduccion: [recorrido tecnico I1](../guides/recorrido-tecnico-i1.md).
- Estado: **no apta para cierre** hasta completar los recorridos independientes
  y la conformidad de Franco y Matias.

## Evidencia comprobada

| Control | Resultado | Evidencia o limite |
|---|---|---|
| `ruff check .` local | Aprobado | `All checks passed!` en este checkout. |
| `python manage.py check` local | Aprobado | `System check identified no issues (0 silenced)`. |
| Recoleccion de `pytest` local | Aprobada | 107 tests recogidos; no equivale a ejecutarlos. |
| Pruebas de configuracion sin base | Aprobadas | 4 aprobadas; se excluyo `test_database_connection`. |
| CI de `main` con PostgreSQL 17 | Aprobada | [Ejecucion 37983344296](https://github.com/MatiasAFernandez/PS_Cooperadora/actions/runs/37983344296): lint, checks Django y 107 pruebas aprobadas (`107 passed in 4.09s`). Incluye pruebas de concurrencia en PostgreSQL y CT-01 a CT-08. |
| Integracion de identidad en gastos | Revisada en codigo | `gastos/auth.py` importa `resolve_actor` y `has_capability` de `identidad.services`; las vistas y servicios de gastos consumen esa interfaz. No implica validacion institucional. |

## Impedimento local

Podman 6.1.2 esta instalado, pero `podman-machine-default` no habia iniciado.
`podman machine start podman-machine-default` fallo al crear la VM WSL con
`HCS_E_SERVICE_NOT_AVAILABLE` (caracteristica requerida no instalada o no
disponible). `wsl --status` informa que WSL2 no es compatible con la
configuracion actual y pide habilitar "Plataforma de maquina virtual" y
virtualizacion en BIOS/UEFI. No se detecto PostgreSQL en los puertos 5432 o
55432. Por ello no se ejecutaron localmente `migrate`, `preparar_identidad_demo`,
`makemigrations --check --dry-run`, la suite completa ni la demo en navegador.
La comprobacion de migraciones se interrumpio al esperar la conexion a la base;
no produjo un resultado aprobatorio. No se borraron volumenes ni datos.
El entorno virtual disponible usa Python 3.14.7; la version de referencia del
proyecto y de la CI es Python 3.11. Django 5.2.17 y Psycopg 3.3.5 admiten
Python 3.14, por lo que esto no bloquea la repeticion local. Registrar la
version usada para compararla con CI.

## Pendientes para el cierre

- [ ] Restaurar WSL2/virtualizacion para Podman o instalar PostgreSQL 17 nativo
  para pruebas; repetir migraciones, controles y suite completa en el entorno local.
- [ ] Franco ejecuta y registra el recorrido de formularios, decisiones,
  historial y mensajes H4 con las cuatro cuentas sinteticas.
- [ ] Matias prepara sus cuentas y reproduce el recorrido de forma independiente,
  comprobando el contrato de identidad y las denegaciones por objeto.
- [ ] Registrar capturas sin datos reales ni secretos y verificar ausencia de
  errores 500 en las acciones y denegaciones.
- [ ] Anotar defectos encontrados, su correccion y nueva prueba, o mantener la
  Issue abierta si afectan criterios de aceptacion.
- [ ] Ambos revisan y acuerdan este acta, consignando limitaciones y preguntas
  para Cooperadora. La validacion operativa se realiza en #9.

| Integrante | Entorno y commit | Fecha | Resultado y evidencia | Conformidad |
|---|---|---|---|---|
| Franco | Pendiente | Pendiente | Pendiente | Pendiente |
| Matias | Pendiente | Pendiente | Pendiente | Pendiente |
