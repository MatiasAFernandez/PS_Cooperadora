# Verificación de #25 — comprobantes externos

Fecha: 20/10/2026. Base: `48c094a45416c468c2f4ed3fa03b0ea6ed4e700b`.
Rama: `codex/25-facturas-notas`. Implementación de Matías con asistencia de
Codex. El responsable confirmó una factura por solicitud, varias notas e
identidad global CUIT/tipo/letra/punto de venta/número. El perfil es provisional
de demo; no se atribuye validación institucional.

## Criterios y evidencia reproducible

Las pruebas de `tests/facturacion/test_comprobantes.py` usan PostgreSQL real,
archivos temporales y usuarios sintéticos:

| Criterio | Comprobación |
|---|---|
| Registro y consulta | Factura, dos créditos y débito conservan origen, actor, fecha, PDF e historial. Neto 90,20; solicitud PRESENTADA y versión intactas. |
| Cardinalidad e identidad | Una factura por solicitud; notas requieren factura propia. Duplicado global y numeración con ceros iniciales se rechazan. |
| Datos inválidos | CUIT, letra, rangos, fecha, tipo, importes cero, exceso de precisión, flotantes, NaN y desborde; PDF obligatorio y PNG rechazado. |
| Acceso | HTTP con CSRF; A consulta su trámite/PDF, B recibe 404, L no registra ni descarga; capacidades insuficientes se deniegan en servicio. |
| Atomicidad | Fallo después de insertar el registro revierte registro/PDF y compensa archivo; no cambia el historial previo. |
| Concurrencia | Dos conexiones y solicitudes distintas con la misma identidad dejan un único registro/PDF y compensan el archivo perdedor. |
| SQL e historia | UPDATE/DELETE, enlaces a PDF/factura ajenos y NaN se rechazan. Reversa con registros se bloquea sin quitar la guarda. |
| Evolución | Upgrade/reversa sin comprobantes preservan solicitud, historial y bytes del PDF existente. |

## Reproducción

Verificación local: Python 3.14.7, Django 5.2.17 y PostgreSQL 18.6 aislado.
La suite completa anterior a la última prueba de migración aprobó **528 pruebas
en 1248,65 s**. Las migraciones desde base vacía, `manage.py check`,
`makemigrations --check --dry-run` y Ruff aprobaron sin incidencias.
El conjunto focal final, incluida esa prueba adicional de migración, aprobó
**25 pruebas en 26,33 s** y Ruff volvió a aprobar. Los resultados no se suman
como una nueva suite completa; la CI de la PR verifica la versión final.

Con dependencias instaladas y PostgreSQL de pruebas configurado, ejecutar
`pytest`, `ruff check .`, `python manage.py check` y
`python manage.py makemigrations --check --dry-run`.
El [recorrido de facturación](../guides/recorrido-facturacion-i2.md) describe la
demo HTTP de factura, crédito y débito y sus permisos.

## Límites y revisión

El comprobante es su propio hecho auditable; se integra al historial sin crear
eventos de cobro ni cambiar el estado de la solicitud. La transacción reutiliza
la operación documental y sus garantías de compensación/recuperación, sin crear
otro mecanismo de almacenamiento. Los constraints y la guarda SQL protegen la
unicidad y los vínculos también frente a escrituras por otras vías.

No hay emisión fiscal, integración externa, conversión de monedas, cobro,
cierre/anulación automática ni edición/eliminación del registro. El PDF no
requiere aceptación documental previa. El perfil técnico exige mismo emisor y
letra para notas; queda sujeto a validación institucional junto al resto del perfil.

Las pantallas se renderizan en pruebas HTTP; no se declara inspección visual
interactiva. La revisión cruzada de Franco se registra en la PR; los checks
verdes por sí solos no la sustituyen.
