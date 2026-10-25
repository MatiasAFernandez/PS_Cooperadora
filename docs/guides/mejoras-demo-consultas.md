# Consulta, presentación y exportación tras el ensayo

Corte del 25/10/2026: rama `codex/mejoras-vistas-demo`, base `97e76de`.
La versión publicada y su revisión se identifican en la PR asociada. Alcance aprobado por Matías en
[SPEC-012](../specs/012-mejoras-demo-consultas.md). La revisión cruzada y la
validación institucional permanecen separadas. No declara cierre de #29 ni #30.

## Actualizar y ejecutar

Con Django detenido y PostgreSQL disponible, instalar las dependencias del
proyecto (`python -m pip install -r requirements/dev.txt`). La exportación agrega
ReportLab 4.4.9 como dependencia de ejecución. Respaldar base y almacenamiento
como conjunto, conservar la versión y aplicar `python manage.py migrate`.

Este corte incorpora documentos 0010 (etiquetas/origen) y facturación 0013
(aclaración, validación y funciones SQL). Conserva los comprobantes anteriores
como Xubio sin modificar sus hechos ni versiones documentales. No revertir si
existen comprobantes de Otro origen; la reversa se rechaza para conservarlos.

Iniciar el servidor según README, con identidad de demo habilitada y proveedor
documental de gastos configurado si se ensaya ese circuito. Las cuentas y claves
existentes no necesitan regenerarse. No se incorpora configuración personal al
producto ni se habilitan datos reales.

## Recorrido de comprobación

1. Entrar por Inicio de demo y recorrer gastos/facturación: ambos usan la misma
   base visual. Inicio de demo y Salir aparecen en la navegación autorizada.
   La salida es un POST protegido por CSRF; no hay salida por GET.
2. Buscar gastos por concepto y facturación por número, solicitante, receptor,
   CUIT o detalle. Combinar estado/seguimiento y período de presentación.
   Elegir Día exacto, Mes con año o Año; sólo se habilitan sus campos. Sin JS,
   la validación y selección de campos activos permanecen en servidor.
3. Verificar que filtros inválidos muestran errores y no amplían el acceso.
   La paginación de facturación conserva filtros. La fecha usa la zona horaria
   configurada, incluyendo límites de medianoche.
4. Incorporar factura/nota y cobro sintéticos. Revisiones por atender reúne sus
   versiones vigentes sin revisión o con resultado Observado/Rechazado; una
   aceptación las retira de esa lista y las mantiene en Respaldos conservados.
   Se conserva el historial de todas las versiones. Sin metadatos no se revelan
   nombres ni resultados documentales.
5. En Pendientes y resolución, comparar neto e ingresos confirmados. Se muestra
   diferencia con signo, importe por cubrir, exceso o sin diferencia. Pendientes
   no se computan como confirmados. Los impedimentos identifican comprobante u
   operación, archivo y versión. No cambian las condiciones de cierre/anulación.
6. Registrar cada tipo de comprobante con Xubio predeterminado y con Otro más
   aclaración. Omitir la aclaración debe fallar sin registro ni PDF residual.
   Actualizar un respaldo conserva la procedencia del comprobante. Los registros
   existentes siguen inmutables y la identidad externa mantiene su unicidad.
7. Exportar solicitud a PDF como titular, operadora y lector global. Comprobar
   identificación, versión, fechas, datos de formulario y rótulo no fiscal.
   No incluye archivos adjuntos ni historial financiero; no se importa en Xubio.
   Un solicitante ajeno recibe 404. También funciona tras cierre/anulación.

## Evidencia local del corte

- Suite completa en PostgreSQL 18.6 aislado, Python 3.14.7: **620 passed in
  223.47s**. Incluye 19 casos nuevos, permisos A/B/O/L, fechas, búsqueda, origen,
  revisiones y PDF. No se suman las ejecuciones focales que se solapan.
- Ruff, `manage.py check`, `makemigrations --check --dry-run` y diff sin errores.
- Upgrade y reversa a 0012/upgrade en copia restaurada de la base sintética del
  ensayo. Las pruebas históricas restauran el esquema actual en `finally` cuando
  una reversa multipaso se rechaza; no usan modelos actuales contra esquemas viejos.
- Migración aplicada después a la base del ensayo con dump privado y copia de
  storage previos. Comparación de 16 tablas y 7 archivos sin cambios en valores
  anteriores; el campo nuevo queda vacío para Xubio. Incluye claves hash y grupos
  existentes, sin publicarlos. La comparación precede al smoke HTTP: éste crea
  sesiones y puede actualizar último acceso, sin modificar hechos del negocio.
- Smoke HTTP en la base actualizada: inicio/listados con A/B/O/L, PDF autorizado
  para B/O/L y 404 para A sobre el trámite de B.
- Inspección de navegador en copia aislada: listado, filtro mensual, navegación,
  detalle/exportación y formulario con Xubio predeterminado y Otro.
- PDF normal de una página y texto largo de cinco páginas renderizados e
  inspeccionados, con acentos y caracteres escapados. Artefactos y logs privados
  en `.local/`, sin versionar datos, contraseñas ni respaldos.

La prueba automática de contenido binario no sustituye la inspección visual.
No se ensayó aquí despliegue institucional, integración Xubio, operación real,
rendimiento masivo ni validación funcional con Cooperadora.
