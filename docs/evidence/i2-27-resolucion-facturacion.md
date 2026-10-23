# Verificación de #27 — resolución explícita de facturación

Fecha: 22/10/2026. Base: `887041d4ae0696ace2c8f154eb4478b32acd5a85`.
Rama: `codex/27-cierre-facturacion`. Implementación principal de Matías con
asistencia de Codex. Matías confirmó igualdad exacta para cierre, anulación
restringida, facultades explícitas, terminales sin reapertura y actualización
documental trazable. Es perfil provisional de demo; no validación institucional.

## Diseño y escenarios

| Decisión | Comportamiento y verificación |
|---|---|
| Cierre manual | Neto positivo, factura, cobros confirmados iguales al neto sin tolerancia, sin pendientes y respaldos vinculados vigentes aceptados. Faltante/exceso/PDF pendiente/observación bloquean sin evento parcial. |
| Anulación restringida | Sin factura ni ingresos pendientes/confirmados, o neto cero por notas aceptadas sin esos ingresos. Negativo, confirmado y pendiente bloquean; crédito no prueba devolución. |
| Declaración inicial | Una transferencia declarada no se ignora al resolver: debe tener registro de medio/operación y verificación explícita. No se infiere importe recibido. |
| Estado y seguimiento | PRESENTADA/OBSERVADA conservan el flujo de corrección. Etapa financiera intermedia derivada de hechos en lista/detalle, sin escrituras en GET ni eventos retroactivos. CERRADA/ANULADA persistidos con evento. |
| Capacidad y frescura | Grupo demo optativo de resolución, acción y objeto en servidor, motivo, CSRF y huella del diagnóstico. Cambio de revisión/operación invalida pantalla anterior. |
| Documento sucesor | Selección o carga/vínculo atómicos de sucesora del mismo trámite/tipo/serie, evento con anterior/nuevo, actor y motivo. FK original, importes y verificaciones intactos. Nueva versión requiere aceptación. |
| Terminal | Lectura/descarga autorizada conservadas. Nuevas operaciones, aportes, revisiones y cambios denegados en servicios y SQL. |
| Concurrencia | Cabecera antes de solicitud/raíz. Dos cierres dejan un evento; cierre frente a nota/cobro/revisión deja cierre+denegación o mutación+conflicto, sin inconsistencias. Gastos/C01 conservan su orden. |
| Fallos y evolución | Fallo al crear evento revierte resolución. Rollback de carga/vínculo compensa archivo. Reversa con resoluciones/actualizaciones se bloquea; vacía/upgrade preserva trámite y bytes previos. |

`tests/facturacion/test_cierre.py` comprueba estos casos con PostgreSQL real,
almacenamiento temporal y datos sintéticos. Incluye dos parciales con centavos,
rechazo SQL de cierre sin condiciones/evento, terminal inmutable, motivo sólo
whitespace, permisos, formulario con motivo conservado y versión obsoleta.

La corrección con archivo continúa la serie vigente cuando el respaldo inicial
compartido ya fue reemplazado por el operador; conserva el vínculo original del
cobro. La regresión evita que la nueva actualización documental deje ese recorrido
de corrección sin una salida válida.

Una regresión adicional comprueba que el lector sin metadatos no recibe motivos
de actualización ni resultados/identificadores del diagnóstico documental y que
la capacidad de resolución sola no amplía esa lectura.

## Proporcionalidad

Se reutilizan EventoFacturacion para resoluciones, DTO común, operación documental
y versiones inmutables. No hay otro motor de workflow ni subsistema de recovery.
ActualizacionRespaldo es un hecho append-only específico: evita permitir UPDATE
general de comprobantes/cobros. La huella de lectura evita multiplicar columnas de
versión entre todos los escritores y no reemplaza autorización.

Las guardas SQL de cierre repiten los invariantes financieros/documentales para
impedir que un UPDATE directo eluda condiciones materiales. Un trigger diferido
exige el evento terminal de la revisión y el índice impide duplicarlo. El contrato
documental explica el nuevo bloqueo de facturación; no cambia decisiones, pagos
ni política documental de gastos.

## Reproducción y límites

Entorno local: Python 3.14.7, Django 5.2.17 y PostgreSQL 18.6 aislado en loopback.

| Comprobación | Resultado |
|---|---|
| Suite completa antes del último ajuste de privacidad documental | 582 passed in 172.03s |
| Conjunto focal final de cierre, incluido el ajuste de privacidad | 31 passed in 26.43s |
| Ruff y diff --check | Aprobados |
| Django check | Sin incidencias |
| makemigrations --check --dry-run | Sin cambios |
| migrate sobre esquema anterior | 0010/0011 aplicadas sin errores |

Los conjuntos se solapan y no se suman. La CI de la PR verifica la versión final.
No se alteraron ramas de Franco ni el checkout original con cambios previos.

Con PostgreSQL aislado y dependencias, ejecutar pytest, Ruff y controles Django.
El [recorrido](../guides/recorrido-facturacion-i2.md) describe permisos, cierre,
anulación, bloqueos y actualización documental. Las pantallas se renderizan por
HTTP; no se declara inspección visual interactiva. Revisión cruzada de Franco en PR.

Regularización de diferencias, devoluciones, retenciones, comisiones y reapertura
no están implementadas. Los casos que las requieren permanecen bloqueados. No hay
movimiento de fondos, anulación fiscal ni cambio del módulo de gastos. #28 y la
validación institucional de #29 siguen separadas.
