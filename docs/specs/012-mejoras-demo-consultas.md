# SPEC-012 — Ajustes de consulta y presentación tras ensayo local

Alcance aprobado por Matías el 25/10/2026 durante el ensayo guiado con datos
sintéticos. Implementación en rama de tarea para revisión; no equivale a validación de
Cooperadora, revisión cruzada ni integración. Relacionado con #30 (consultas),
SPEC-005, SPEC-007 y SPEC-010. Matías mantiene facturación/documentos; los cambios
compartidos y de gastos requieren revisión de Franco según el flujo existente.

## Comportamiento aprobado

- Una base visual común toma los estilos de gastos para facturación y revisión
  documental. La navegación autorizada incorpora Inicio de demo y salida por POST
  con CSRF. Consultar un listado no registra operaciones del negocio.
- Ambos listados filtran por fecha de presentación en la zona horaria configurada:
  día exacto, mes/año o año. Se usa el período seleccionado; campos de otros
  períodos no afectan el filtro. Parámetros inválidos muestran errores y no
  resultados parciales. Fecha, estado y texto se combinan sobre trámites visibles.
- Gastos conserva búsqueda por concepto y sus cuatro estados. Facturación busca
  por número de solicitud exacto o texto en solicitante, receptor, CUIT y detalle;
  filtra por estado/seguimiento. Presentada sin factura, facturada pendiente de
  cobro y cobrada en revisión se distinguen sin alterar estados almacenados.
  Observada y resoluciones terminales conservan prioridad; los filtros financieros
  usan el mismo criterio de cobertura que la consulta existente, sin autorizar cierre.
- Revisión de respaldos incluye todas las versiones vigentes del trámite cuyo
  último resultado no sea Aceptado: sin revisión, Observado o Rechazado, también
  facturas/notas. Respaldos conservados incluye todos los tipos y versiones.
  Se respetan las capacidades documentales existentes.
- Diferencia = neto de comprobantes menos ingresos confirmados, con signo e
  indicación de importe por cubrir, exceso o sin diferencia. Los pendientes no
  se cuentan como confirmados. No constituye una nueva regla de regularización.
- Los impedimentos documentales identifican factura/nota por su identificación,
  o cobro por medio y operación, más archivo y versión. Sin metadatos se mantiene
  el mensaje neutral existente, sin revelar nombres.
- Facturas, notas de crédito y de débito admiten origen Xubio (predeterminado) u
  Otro con aclaración obligatoria. Los registros anteriores conservan Xubio.
  El origen no integra ni debilita la unicidad fiscal existente. Registros y
  versiones siguen inmutables; reemplazos no modifican el origen del comprobante.
- Los códigos documentales históricos terminados en `_XUBIO` se conservan para
  preservar contratos/cadenas; sus etiquetas visibles pasan a ser neutrales. La
  procedencia diferencia Xubio/Otro. No se reescriben versiones anteriores.
- Exportación PDF por solicitud autorizada al titular, operadora y lector global,
  bajo el mismo acceso al objeto. Incluye datos del formulario salvo archivos y
  control de retirada, correo del solicitante, identificador, versión, estado,
  presentación y fecha de exportación. No incorpora bytes, rutas, revisiones ni
  historial de cobros; no requiere permisos documentales para datos ya visibles.
  Se rotula «Solicitud para preparar facturación — no es comprobante fiscal».
  Disponible también después de cerrar o anular; no emite ni importa en Xubio.

## Verificación y límites

Probar combinaciones y límites locales de fechas, visibilidad A/B/O/L, seguimiento
financiero, errores, origen alternativo para los tres tipos, falta de aclaración,
integridad SQL, inmutabilidad, preservación de datos y autorización PDF. Revisar
visualmente listados/formularios y PDF, incluyendo detalle largo. Migrar una copia
antes de aplicar al entorno del ensayo, conservando respaldo privado de base y
almacenamiento. La evidencia del corte vive en la guía de verificación asociada.

No agrega resúmenes globales, SSO, emisión externa, retenciones, devolución,
destinatarios de pagos ni reglas sobre factura anterior a aprobación de gastos.
Las hipótesis H1–H4 conservan su estado. No acredita cierre completo de #30 ni
demostración/aceptación institucional de #29.
