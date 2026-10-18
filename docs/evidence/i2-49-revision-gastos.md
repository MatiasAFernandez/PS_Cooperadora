# I2-49 — proyección del historial documental en gastos

Fecha: 18/10/2026. Rama local: `feat/49-revision-documental-gastos`. Base de main: `48c094a45416c468c2f4ed3fa03b0ea6ed4e700b`, que ya incluye PR #62 (DOC-R04/#24).

## Alcance

El trabajo local agrega al detalle del gasto una proyección de las revisiones autorizadas para cada versión documental y sus eventos de aporte. El permiso de metadatos limita la consulta y la vista; el recorrido de pago y sus registros existentes no se reescriben. No define qué comprobante satisface un requisito institucional: Q1–Q5, incluida Q4, continúan pendientes.

## Validación ejecutada

- Ruff sobre los módulos Python modificados: aprobado.
- `python manage.py check`: aprobado, sin incidencias.
- `git diff --check`: aprobado.
- `python -m pytest --collect-only -q tests/integracion/test_49_proyeccion_revision_gastos.py tests/integracion/test_c04_pago_real_proyeccion.py`: 4 casos colectados, sin ejecutar.
- Pruebas de integración nuevas y focales: no ejecutadas. Docker Desktop no tenía un daemon disponible y no había PostgreSQL local escuchando en el puerto configurado. No se inició ni modificó una instancia persistente.
- `python manage.py makemigrations --check --dry-run`: intento interrumpido al quedar sin respuesta con PostgreSQL no disponible; no se considera una validación aprobada.

Los resultados son estáticos y locales. La rama todavía no está integrada; GP-05/GP-06 y la regresión de pago requieren la ejecución de las pruebas en PostgreSQL aislado. El recorrido conjunto de #28 y la evidencia final de #50 permanecen pendientes.
