# Verificación técnica del recorrido #21/#23

Fecha: 16/10/2026. Rama de trabajo: codex/21-23-facturacion.
Base: main d65beda83e2bc056800c87778224c7fe23d06287.
Resultado: implementación local preparada para revisión; no acredita aprobación
de Franco ni aceptación de Cooperadora. No se cerraron issues ni se publicó una PR.

## Cambios comprobados

- Actor compatible con correo opcional, preparación optativa de demo y
  autorización por objeto en lista, detalle, observación y corrección.
- Presentación, observación y corrección con eventos inmutables, datos
  anteriores/posteriores y metadatos asignados por servidor.
- D01 condicional; cuenta corriente y respaldos opcionales no reciben
  restricciones nuevas. La carga no verifica el ingreso ni registra cobro formal.
- Idempotencia de alta, conflictos de versión y bloqueo en PostgreSQL.
- Asociación de respaldos por trámite/tipo, reemplazos con versiones y retirada
  explícita del vínculo conservando historia.
- Compensación de archivos, manifiesto privado y reconciliación tras resultado
  incierto del commit.
- Migración desde #22 con varias solicitudes técnicas: UUID individuales,
  cabeceras/PK/eventos conservados, sin inventar datos fiscales.

## Resultados ejecutados

Entorno: Python 3.14.7 del entorno local existente, Django 5.2.17,
PostgreSQL 18 temporal aislado en localhost y almacenamiento temporal.
No se modificaron credenciales ni datos de la instancia PostgreSQL habitual.

| Verificación | Resultado |
|---|---|
| ruff check . | Aprobado, sin errores. |
| python manage.py check | Sin incidencias. |
| python manage.py makemigrations --check --dry-run | No changes detected. |
| pytest -q --tb=short --maxfail=1 | 402 passed in 54.25s. |
| git diff --check | Sin errores en el diff rastreado. |

La suite contiene 33 casos nuevos (incluida parametrización) y conserva los
restantes de identidad, documentos, contratos y gastos. La prueba previa de
rollback de #22 se adaptó para modificar versión en lugar de insertar un estado
ficticio que el catálogo de #23 ya no admite; sigue comprobando rollback conjunto.
No se modificaron los modelos ni servicios de gastos.

Las carreras de dos conexiones comprobaron una sola alta/observación/corrección
exitosa y conflicto en la restante. Los fallos de evento revirtieron estado,
centro, versión y documentos nuevos. La prueba de commit incierto confirmó en
base, simuló pérdida de respuesta y comprobó que el archivo referenciado no se
elimina durante reconciliación. Los fallos de borrado conservaron la excepción
principal y el manifiesto para reintentar.

## Límites y siguiente revisión

Las pruebas HTTP renderizan formularios/detalle, recorren solicitudes y verifican
CSRF real, accesos ajenos y errores. No se ejecutó una inspección visual interactiva
en navegador ni una validación de usuarios de Cooperadora. La guía incluye ese
recorrido y sus comprobaciones de etiquetas/teclado/mensajes.

Se mantienen explícitas las hipótesis de obligatoriedad y catálogos de demo.
Revisión documental, facturas/notas, cobros, cierre/anulación e integración completa
de ambos consumidores permanecen en #24–#28 según sus responsabilidades.
Franco debe revisar los cambios de contrato comunes y su compatibilidad desde
gastos; Matías presenta este recorrido para validación funcional.

Consultar la guía docs/guides/recorrido-facturacion-i2.md para preparar cuentas
sin contraseñas publicadas y recuperar archivos con aplicación detenida.
