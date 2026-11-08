# Guía de interfaz de PS_Cooperadora

Esta es la referencia vigente para diseñar, implementar y revisar pantallas. La exploración visual del sitio de UTN FRRe explica el origen de parte de la identidad gráfica. El resultado de esa exploración se conserva como [muestrario histórico](muestrario.html). Para decidir la composición y el comportamiento de una pantalla, partir de los recorridos y componentes actuales.

## Referencias para reutilizar

| Si necesitás | Partí de |
|---|---|
| Navegación lateral, encabezado y adaptación móvil | [Layout base](../../templates/base.html), [navegación](../../templates/comunes/navegacion_tramites.html) y [sus estilos](../../static/css/navegacion.css) |
| Jerarquía de un trámite, estados, documentos y acciones por rol | [Detalle de la solicitud](../../templates/gastos/solicitud_detail.html) |
| Formularios operativos, importes, validación y acciones al pie | [Registrar pago](../../templates/gastos/pago_form.html) |
| Bandeja compacta y detalle progresivo | [Listado de Gastos](../../templates/gastos/solicitud_list.html) y [su interacción](../../static/gastos/js/solicitud_list.js) |
| Indicadores, filtros simples y avanzados, y tabla adaptable | [Reporte Directivo de Gastos](../../templates/gastos/reporte_cuatrimestral.html) |
| Búsqueda, edición y confirmación de baja lógica | [Catálogos y parámetros](../../templates/gastos/gestion_catalogos.html) |

Elegí las referencias que correspondan a la tarea. Cuando exista un mockup aprobado, el encargo debe identificarlo y especificar qué HTML, CSS y patrones de interacción se reutilizan. Adaptá esa base al layout, los permisos y los datos reales del circuito. Si dos referencias difieren, resolvé la diferencia con el patrón más coherente para el recorrido y anotá el ajuste pendiente si queda fuera del alcance.

## Decisiones de interfaz

- **Empezá por la tarea y el rol.** Definí qué necesita ver la persona para decidir, cuál es su acción principal y qué debe ocurrir si faltan datos o permisos. Mostrá primero la información que cambia la decisión. Dejá el resto para filtros avanzados, secciones desplegables o un detalle a demanda.
- **Mantené el vocabulario y la jerarquía.** El mismo dato conserva su nombre entre pantallas. La misma acción conserva su estilo, posición y rótulo en contextos equivalentes. Usá verbos concretos como «Guardar cambios» o «Registrar pago». Para ir desde otra sección, «Ir al listado de gastos». Para regresar desde el detalle, «Volver al listado», conservando filtros si el recorrido ya los transmite. Ofrecé un acceso filtrado solo cuando aplique los criterios que anuncia.
- **Usá iconos reconocibles con una función.** Reutilizá la familia SVG del producto para búsqueda, volver, cerrar, expandir y acciones similares. Acompañá con texto las acciones cuyo significado pueda ser ambiguo. Un control de solo icono necesita nombre accesible. Los iconos decorativos se ocultan a tecnologías de asistencia.
- **Mostrá el estado y el siguiente paso.** Usá texto en chips, avisos y resultados. Priorizá el error cerca del dato que la persona debe corregir y conservá lo ingresado. Si falta un requisito para actuar, indicá cuál y cómo resolverlo. Una confirmación sensible debe decir qué cambia y sobre qué registro.
- **Aplicá interactividad cuando reduce pasos o carga visual.** Buscadores de catálogo, paneles de vistazo, controles desplegables y feedback de copiado tienen un propósito concreto. Si un panel bloquea el fondo, contemplá cierre explícito, Escape, clic fuera cuando corresponda y devolución de foco. Usá transiciones cortas y respetá la preferencia de movimiento reducido.
- **Diseñá móvil desde el comienzo.** Priorizá campos y acciones esenciales antes de compactar. Una bandeja de trabajo frecuente debe permitir actuar sin desplazamiento horizontal de toda la página. Validá etiquetas, foco visible, teclado, contraste y zonas táctiles de 44 px para los controles principales. Un estado importante se entiende por su texto además del color.

## Base técnica y revisión

Usá plantillas Django, HTML semántico, CSS y JavaScript nativo. Los [tokens cargados por el producto](../../static/css/tokens.css) son la fuente de Montserrat, paleta institucional, bordes, radios, espaciado y ancho de contenido. Reutilizá los componentes y clases que ya resuelvan la interacción. Las vistas nuevas no requieren Tailwind, HTMX, un framework SPA ni una cadena de compilación. Cualquier dependencia nueva se justifica en el cambio que la necesita.

Django conserva la validación, la autorización y la persistencia. Usá JavaScript como mejora progresiva donde sea viable. Verificá en la demo el recorrido principal, un error representativo, el estado vacío cuando aplique y el acceso por rol si cambia. Compará escritorio y móvil con la referencia elegida. Registrá las diferencias visuales concretas que se difieran, con pantalla y motivo, para la próxima pasada.

### Encargo corto para un agente

Indicá la vista y el rol, la acción principal, una o dos referencias reales, el mockup aprobado si existe, los archivos permitidos y qué se debe conservar. Incluí los estados y tamaños a comprobar. Pedí una revisión visual del resultado en la demo junto con las pruebas focalizadas que correspondan al riesgo del cambio.
