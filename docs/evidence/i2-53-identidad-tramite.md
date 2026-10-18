# Verificación técnica #53 — identidad directa del trámite de gastos

Fecha: 17/10/2026. Rama: `feat/53-identidad-tramite-gastos`.
Base: `main` en `7ba783cb42fc6c20fc11c54eacb04baa0236fe93`.
Resultado de la verificación previa a la publicación: implementación local
preparada para revisión; ese corte no acreditaba revisión humana, integración
con C04/#55, aceptación de Cooperadora ni cierre de issues. Entonces no se había
publicado ninguna rama remota ni Pull Request.

> [!NOTE]
> **Resultado posterior e integración en main**:
> La Pull Request #56 (head `37c28a9523a16742dcc7534896f90e38db7cbf55`), correspondiente a esta entrega, fue revisada, aprobada e integrada en `main` en el commit `2d8686004d0b440664e8f652c892b2bfe506b62f`, cerrando la Issue #53. Las comprobaciones y resultados que figuran a continuación se conservan intactos como registro histórico de la verificación previa a la publicación.

## Cambios comprobados

- `SolicitudGasto.tramite_base` es un `OneToOneField` protegido, no editable y
  obligatorio, con `related_name="solicitud_gasto"`; el número público sigue
  siendo la PK y debe coincidir con `TramiteBase.numero_publico`.
- Migración en tres etapas: columna anulable, backfill transaccional y
  `NOT NULL` más trigger PostgreSQL. El backfill reutiliza una cabecera exacta
  existente o crea la faltante, y aborta antes de escribir si cambia el
  circuito, número, titular o una referencia documental.
- El trigger `gastos_validar_tramite_base` rechaza altas y reasignaciones
  directas incompatibles en PostgreSQL, incluso por SQL que no pasa por el ORM.
- `crear_solicitud_gasto` revalida `gastos.presentar`, reserva la secuencia de
  gastos, crea cabecera y solicitud en una transacción y deja
  `centro_costo_codigo` en `NULL`. La vista de alta delega en el servicio; los
  GET no escriben.
- Las guardas de modelo mantienen errores comprensibles y el borrado de gasto
  conserva sus decisiones en cascada; la cabecera vinculada queda protegida.
- Las pruebas compartidas que crean gastos directos usan un helper que crea
  cabecera y solicitud válidas. El puente temporal de `comunes`/`documentos` no
  se modificó y sigue encontrando la cabecera existente.

## Migraciones y preservación

| Etapa | Archivo | Efecto |
|---|---|---|
| 1 | `gastos/0004_solicitudgasto_tramite_base.py` | Agrega la relación anulable. |
| 2 | `gastos/0005_backfill_solicitudgasto_tramite_base.py` | Valida, reutiliza o crea cabeceras y vincula cada gasto. |
| 3 | `gastos/0006_integridad_solicitudgasto_tramite_base.py` | Hace la relación obligatoria e instala el trigger. |

Las pruebas de migración cubren reutilización de cabecera, alta faltante,
rollback ante titular incompatible, preservación de documentos y bytes,
coincidencia `gastos:N`/`facturacion:N`, reversa exitosa y reversa bloqueada por
una inconsistencia controlada. La reversa conserva cabeceras y documentos; no
borra filas comunes ni archivos.

## Verificación ejecutada

Entorno: Python 3.11.9, Django 5.2.17, PostgreSQL 17.10 aislado en
`127.0.0.1:55433`, base/usuario sintéticos de la tarea. No se instalaron
dependencias ni se usaron datos reales.

| Comando | Resultado |
|---|---|
| `pytest -q` | 423 passed in 78.73s. |
| `ruff check .` | Sin errores. |
| `python manage.py check` | Sin incidencias. |
| `python manage.py makemigrations --check --dry-run` | `No changes detected`. |
| `python manage.py migrate --noinput` | Aplicó todas las migraciones, incluidas 0004–0006. |
| `python manage.py migrate gastos 0003 --noinput` y `python manage.py migrate gastos --noinput` | Reversa y reaplicación correctas sobre la base aislada. |
| `git diff --check` | Sin errores de espacio en el diff. |

## Límites y dependencias

- El puente temporal de lectura de `comunes`/`documentos` permanece. Retirarlo y
  migrar las lecturas al vínculo directo requiere un cambio compartido posterior
  con revisión de Matías; no forma parte de este corte.
- No se asume integrada la rama C04/PR #55. La compatibilidad verificada es la
  del árbol base `7ba783c`, sus pruebas y el puente actual.
- La migración de datos usa bloqueos de tabla y fila y está pensada para una
  ventana de mantenimiento. Datos históricos incoherentes bloquean la migración
  y requieren corrección manual; no se reparan ni se transfieren titulares
  automáticamente.
- No se ejecutó una revisión humana, una prueba de carga con volumen de
  producción ni una validación institucional de reglas de negocio.
