# Verificación de #24 — revisión documental

Fecha: 18/10/2026. Base: `190ab69ff852e7aa4c64eed122a7a1a7c8c70c49`.
Rama: `codex/24-revision-documental`. Implementación de Matías con asistencia de
Codex, por indicación de avanzar con #24. Matías eligió agregar RECHAZADO al
perfil de demo; no se atribuye validación institucional ni revisión de Franco.

## Criterios y pruebas

| Criterio | Evidencia |
|---|---|
| Capacidad independiente y acceso al documento/trámite | `test_permisos_objeto_inexistente_y_capacidades_independientes`: lectura/pago no permiten revisar; acceso ajeno/inexistente y falta de metadatos se deniegan. HTTP prueba revocación por petición y CSRF. |
| Resultado, actor y fecha consultables después de otro resultado o reemplazo | Prueba parametrizada en gastos/facturación conserva ACEPTADO → OBSERVADO, DTO y estados propios intactos. Reemplazo conserva revisión anterior y empieza sin revisión; versiones históricas ya no se revisan. |
| Carga/ausencia/rechazo/observación no acreditan conformidad | `version_aceptada` es falso hasta aceptación vigente y vuelve a falso tras observación o reemplazo. C01 omite/deniega OBSERVADO y RECHAZADO; mantiene la excepción técnica explícita sin revisión sin acreditar deuda. |
| Revisión fallida/repetida sin hechos parciales | Prueba de rollback inserta y falla dentro de la transacción: queda sólo la revisión anterior. Reenvíos y resultados idénticos se rechazan. Dos conexiones concurrentes dejan un único hecho. |
| Integridad y preservación | UPDATE/DELETE por ORM y SQL se rechazan. Upgrade/reversa vacía conserva documento y bytes; con historial la reversa se bloquea y conserva la guarda SQL. |
| Concurrencia con consumidores | Revisión/reemplazo serializados por la raíz. Verificación C01 bloquea la revisión hasta terminar su transacción. |

## Comprobaciones ejecutadas

Entorno: Python 3.14.7, Django 5.2.17, PostgreSQL 18.6 aislado en loopback,
base nueva y archivos sintéticos temporales. No se usaron datos reales ni bases
compartidas. No se cambiaron archivos del checkout original.

| Comprobación | Resultado |
|---|---|
| Suite completa de la implementación inicial | **479 passed in 78.42s**. Incluye regresión de gastos, facturación y proveedor real. |
| Pruebas focales finales de revisión y migración | **21 passed in 7.12s** tras agregar guardas de reversa y selección explícita del resultado. |
| Revisión/migraciones + proveedor real C01/C04 + facturación | **65 passed in 21.75s**; compatibilidad del delta final con ambos consumidores. |
| `ruff check .` | Aprobado. |
| `manage.py migrate --noinput` | Todas las migraciones aplicadas desde base vacía, incluidas 0007/0008. |
| `manage.py check` | Sin incidencias. |
| `manage.py makemigrations --check --dry-run` | Sin cambios. |

Las dos pruebas de migración se agregaron después de la suite de 479; los
resultados no se suman ni se presentan como otra suite completa. La CI de la PR
verifica el head final y su resultado se registra en la propia PR/issue.

## Reproducción y revisión pendiente

Con PostgreSQL aislado y dependencias instaladas, ejecutar `pytest`, Ruff y los
controles Django habituales. Para el recorrido local:

1. Habilitar el adaptador sintético y ejecutar
   `python manage.py preparar_identidad_demo --facturacion --revision-documental`.
   Asignar contraseñas locales con changepassword sin publicarlas.
2. A presenta una solicitud ficticia con respaldo. En su detalle abrir Revisión
   de respaldos. A consulta el historial; no recibe facultad de revisar.
3. O abre el respaldo, descarga si necesita y selecciona ACEPTADO, OBSERVADO o
   RECHAZADO. En los dos últimos completa motivo. Un reenvío da conflicto.
4. Reemplazar el respaldo desde una corrección conserva el historial anterior;
   la nueva versión aparece pendiente. Ninguna acción cierra el trámite.

La UI fue renderizada y recorrida mediante pruebas HTTP con CSRF real; no se
declara una inspección visual interactiva ni validación de Cooperadora.

Franco debe revisar el [contrato](../contracts/revision-documental-i2.md),
el ajuste C01 para resultados negativos, compatibilidad de bloqueos/migraciones
y los componentes comunes de historial. #24 permanece abierta hasta esa revisión
y la integración. #28 conserva la integración completa de gastos; #27 define
qué requisitos satisface cada tipo/etapa y #29 registra validación operativa.
