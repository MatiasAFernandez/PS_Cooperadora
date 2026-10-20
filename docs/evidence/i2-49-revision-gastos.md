# I2-49 — proyección del historial documental en gastos

Fecha: 20/10/2026. Rama local: `feat/49-revision-documental-gastos`. Base de main: `48c094a45416c468c2f4ed3fa03b0ea6ed4e700b`, que ya incluye PR #62 (DOC-R04/#24).

## Alcance

El trabajo local agrega al detalle del gasto una proyección de las revisiones autorizadas para cada versión documental y sus eventos de aporte. El permiso de metadatos limita la consulta y la vista; el recorrido de pago y sus registros existentes no se reescriben. No define qué comprobante satisface un requisito institucional: Q1–Q5, incluida Q4, continúan pendientes.

## Validación ejecutada

- Docker Engine `29.6.1`; PostgreSQL temporal `postgres:17-alpine`, servidor `17.11`, enlazado sólo a `127.0.0.1:55439`. La instancia usó almacenamiento `tmpfs`, sin volúmenes ni datos preexistentes; el contenedor se eliminó al terminar. La configuración de base se pasó al proceso de pruebas; no se modificó `.env`.
- `python manage.py check`: aprobado, sin incidencias.
- `python manage.py makemigrations --check --dry-run`: aprobado, no detectó cambios pendientes.
- `python -m pytest -q tests/integracion/test_49_proyeccion_revision_gastos.py tests/integracion/test_c04_pago_real_proyeccion.py tests/integracion/test_bloqueo_documental.py tests/integracion/test_revision_documental.py tests/integracion/test_migracion_revision_documental.py tests/gastos/test_document_provider.py`: 52 pruebas aprobadas.
- La primera ejecución reveló que un test pasaba un `User` Django donde el contrato requiere `identidad.Actor`; se corrigió el argumento a `e.actor_staff` y la corrida focalizada completa volvió a pasar.
- Ruff sobre el test corregido y `git diff --check`: aprobados.

La rama todavía no está integrada. La corrida cubre #49, las regresiones documentales y C04 seleccionadas, pero no es la suite completa. El recorrido conjunto de #28 y la evidencia final de #50 permanecen pendientes.
