# Verificación de #22 — modelo y contratos comunes

Fecha: 18/10/2026. Revisión realizada con asistencia de Codex por indicación de
Matías. Se comprobó el head de #59 `1331eb49c38049e944dd32aa51321a6adbe95762`
sobre `2d8686004d0b440664e8f652c892b2bfe506b62f`. #59 fue aprobada en la
revisión `5563028470` e integrada por squash en
`aa6e3ce1364a320d255e9d6eaaedb5b66dc3bc59`. Los árboles del head probado y
ese commit integrado son idénticos (`git diff <head> <merge> --stat` vacío).

## Matriz de criterios de cierre

| Criterio de #22 | Evidencia comprobada |
|---|---|
| Propietario y revisor por dato/interfaz; ejemplos de ambos circuitos | Matriz del [contrato común](../contracts/i2-tramites-provider-matias.md). Franco revisó #51/#52; Matías revisó #55/#56/#59. La adaptación conjunta prueba referencias de igual número y distinto circuito. |
| Relaciones válidas e inválidas sin efectos parciales en PostgreSQL | `tests/integracion/test_issue_22_contratos_y_modelo.py`, `tests/gastos/test_tramite_base.py`: cabeceras, referencias ajenas/inexistentes/cruzadas, guardas ORM y SQL, documentos y rollback de creación. |
| Eventos de presentación/observación/corrección sin borrar acciones, con estados propios | `tests/facturacion/test_recorrido.py::test_recorrido_conserva_identidad_versiones_y_observacion`; eventos append-only y DTO cronológico en pruebas de #22; decisiones/pagos de gastos se adaptan sin equipararlos a revisión documental. |
| Migraciones y pruebas reproducibles | `tests/integracion/test_migracion_issue_22.py`, `tests/gastos/test_migracion_issue_53.py`, `tests/facturacion/test_migracion.py`; upgrade conserva referencias, metadatos y bytes, reversa/reaplicación y rechazo atómico de inconsistencias. Migración desde base vacía ejecutada. |
| Atomicidad de evento y operación en ambos circuitos | `tests/gastos/test_concurrency.py::test_t04_22_reversion_atomica_ante_fallo_guardar_evento`, `tests/gastos/test_pago_externo_services.py::test_rollback_completo_si_falla_la_creacion_del_evento`, `tests/facturacion/test_atomicidad.py` y prueba de rollback común de #22. |

## Verificación independiente ejecutada

Entorno: Python 3.14.7, Django 5.2.17, PostgreSQL 18.6 aislado en loopback,
cluster nuevo con datos sintéticos y almacenamiento temporal de las pruebas.
No se usaron bases compartidas ni documentos reales.

| Comprobación | Resultado |
|---|---|
| `python -m pytest -q --tb=short` | **459 passed in 85.35s**. Incluye integridad, migraciones, concurrencia, autorizaciones HTTP, documentos, facturación y navegación común. |
| `python -m ruff check .` | Aprobado. |
| `python manage.py check` | Sin incidencias. |
| `python manage.py migrate --noinput` | Todas las migraciones aplicadas desde base vacía. |
| `python manage.py makemigrations --check --dry-run` | Sin cambios; repetido con la base creada y migrada para comprobar historia consistente. |
| `git diff --check origin/main...HEAD` sobre el head de #59 | Sin errores. |
| [CI #88](https://github.com/MatiasAFernandez/PS_Cooperadora/actions/runs/39090962013) del head de #59 | `quality` success: lint, controles Django y suite sobre Python 3.11/PostgreSQL 17. |

La revisión inspeccionó los 14 archivos del diff, su acceso por actor/objeto,
campos del DTO, escape del detalle y exclusión de referencia documental, huella
de idempotencia y snapshots privados. No se encontraron defectos materiales;
no se modificó la implementación de Franco durante la revisión.

La conciliación posterior cambia únicamente este registro, SPEC-009 y el
contrato: referencias relativas y diff se comprueban antes de publicar. Las
459 pruebas corresponden al código de #59 y al árbol integrado idéntico; no se
presentan como otra ejecución sobre el commit documental.

## Reproducción

Desde un checkout limpio con dependencias de `requirements/dev.txt`, configurar
POSTGRES_HOST/PORT/USER/PASSWORD/DB hacia una instancia PostgreSQL aislada,
con permiso para crear la base de pruebas. Ejecutar los comandos de la tabla.
La suite realiza sus pruebas de migración sobre su propia base y restaura el
esquema final. No ejecutar contra una base compartida.

## Alcance y continuidad

El cierre de #22 acredita modelo y contratos INT-R03/04. #28 conserva integración
funcional completa; #29/#50, demostración y evidencia de recorridos. #24 conserva
revisión documental y #25–#27 factura/cobro/cierre. El puente documental permanece
por compatibilidad, con relación directa de gastos ya protegida; retirarlo
requiere revisión compartida posterior. La validación institucional sigue aparte.

La actualización se limita a los documentos comunes de #22; no incorpora ni
descarta el trabajo local de #57 ni cambia los documentos propios de gastos.
