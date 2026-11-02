# Atención y recorrido de facturación — #80/#78

Solicitud de Matías del 02/11/2026. Implementación de Matías con asistencia de
Codex; revisión cruzada de Franco pendiente en PR. El SHA y los checks finales
se registran en esa PR, que conserva el seguimiento operativo.

## Resultado

- Solicitante con consulta y presentación usa un enlace por circuito:
  Solicitud de Gasto y Solicitud de Facturación. El alta permanece en los listados.
  Cuentas con presentación sin consulta conservan un acceso autorizado al alta.
- Campos de pago condicionales, columnas y acceso Ver Detalle; cuatro filas
  visibles con scroll de teclado y cabecera fija. La paginación sigue en 25.
- Paneles de atención por actor y acciones al principio del detalle. Excluyen
  terminales, lector sin escritura y espera de acciones ajenas; no modifican
  estados, saldos, autorizaciones ni verificaciones.
- Opción 35 retirada del formulario; datos históricos conservados.
- Corrección de cobros propios pendientes/rechazados (#87/SPEC-019), confirmada
  expresamente por Matías: datos y respaldo, nueva versión pendiente de revisión,
  ordinal estable e historia completa. Sólo el cobro vigente cuenta en saldos.

Reglas de proximidad mensual, orden y permanencia del operador y conservación
de campos ocultos confirmadas por Matías en esta sesión. La corrección de cobro
tiene endpoint propio con autorización por autor, titular, capacidad y estado.
Los confirmados y trámites terminales permanecen protegidos.

## Comprobaciones

- Corte final: 708 pruebas aprobadas en 344,07 s, PostgreSQL 18 local con base
  sintética separada. Incluye permisos, CSRF, ciclo de atención, dos correcciones
  concurrentes, rollback, migración con datos previos, rechazo de reversa con
  historia y guardas SQL. No se modifica la base de la demo.
- Ruff, manage.py check y makemigrations --check --dry-run aprobados; enlaces
  Markdown locales correctos. El control de diff incluye archivos nuevos.
- Edge headless con páginas Django y datos sintéticos: siete filas generan scroll
  y exactamente cuatro visibles en ventanas ancha y angosta; campos ocultos inicialmente y al seleccionar No,
  visibles al seleccionar Sí, no enviados con No y valor conservado al alternar.
- Inspección de captura del listado: columnas, botón, cuatro filas y navegación.
  HTML y capturas de QA permanecen privados en .local/qa80.

## Límites

No se envían correos (#78 sigue parcial), no hay editor administrativo (#77 sigue
parcial), ni cambios a referencias de Xubio o regularización de confirmados. Las tarjetas
reutilizan las operaciones que cada perfil puede realizar; no representan deuda
institucional ni automatizan el cierre. El manual de marca definitivo sigue
pendiente. Las consultas recorren candidatos abiertos hasta reunir dos/tres
acciones; se cargan relaciones de facturas/cobros por lotes de 25. La inspección
visual corresponde a páginas sintéticas renderizadas; las sesiones, permisos y
persistencia se comprueban en pruebas HTTP/servicios.

La migración 0015 conserva datos monetarios de versiones anteriores, permite
únicamente su marca de sustitución y exige sucesor al commit; protege las
confirmaciones y adapta el cierre SQL a los cobros vigentes. No se aplicó a la
base de demo. Las pruebas usan base separada y archivos temporales.
