# Guía de interfaz de PS_Cooperadora

Esta es la referencia visual y de interacción vigente para diseñar, implementar y revisar pantallas de `PS_Cooperadora`. El objetivo es un producto administrativo y financiero moderno, limpio y sobrio —inspirado en la claridad de herramientas como Mercury y Notion— implementado con plantillas Django, HTML semántico, CSS y JavaScript nativo, sin cadena de compilación.

> **Estado vigente de convergencia:** el conjunto completo de vistas autenticadas (Gastos, Facturación, Documentos, Inicio, Avisos, Cuentas/Usuarios, Reportes Directivos y Configuración/Catálogos) ya implementa el sistema visual de esta guía sobre `tokens.css` y `base.css`. [muestrario.html](muestrario.html) se conserva exclusivamente como registro histórico de octubre 2026.

## Sistema visual base (`static/css/tokens.css`)

`static/css/tokens.css` es la **única fuente de verdad** de tokens visuales (no mantener copias duplicadas en `docs/`).

### Paleta: 90% neutros cálidos, 10% acento institucional

- **Superficies neutras cálidas:**
  - Lienzo de página: `--bg-canvas: #f7f7f5`
  - Sidebar: `--bg-sidebar: #fbfbfa`
  - Superficie principal (tablas, tarjetas, diálogos): `--bg-surface: #ffffff`
  - Superficie atenuada (cabeceras/pies de tabla, bloques resumen): `--bg-surface-muted: #fafaf8`
  - Contenedores sutiles / hover / pestañas: `--bg-subtle: #f2f2ef`, `--bg-hover: #f7f7f4`, `--bg-tabs: #ecece7`, `--bg-badge-muted: #e7e7e2`
- **Bordes delicados:** `--border-hairline: #ecece8` (filas y divisores internos), `--border-subtle: #e3e3de` (contenedores, sidebar, acciones secundarias sutiles), `--border-control: #d5d5ce` y `--border-control-hover: #b8b8af` (inputs y selects).
- **Tinta neutra para datos y títulos:**
  - `--ink-strong: #111827` para títulos `h1`/`h2`, conceptos principales, importes y títulos de diálogo (nunca usar azul saturado en importes ni en todos los encabezados).
  - `--ink-primary: #374151` para texto corrido, valores y acciones secundarias.
  - `--ink-muted: #6b7280` para metadatos, encabezados de columna y placeholders.
- **Acento marino institucional (uso acotado):**
  - `--brand-navy: #162f52` (marca y acentos oscuros), `--brand-primary: #1e4273` y `--brand-primary-hover: #153156` (CTA primario, acciones operativas pendientes e ítem activo de navegación), `--brand-soft: #eef3fa` (fondo activo en navegación), `--brand-avatar-bg: #e7edf6`, `--brand-badge-active: #dbe6f6`, `--brand-ring: #3b6fd8` (anillo de foco).
- **Estados semánticos:** pills suaves con punto de `6 px` + texto explícito (nunca depender sólo del color ni usar bordes duros chillones):
  - Información (`Presentada`): `#eff6ff` / `#1d4ed8` (punto `#3b82f6`)
  - Éxito (`Aceptada`, `Pagada`): `#ecfdf5` / `#047857` (punto `#10b981`)
  - Atención (`Observada`, pendientes): `#fffbeb` / `#b45309` (punto `#f59e0b`)
  - Error / rechazo / bloqueo: `#fef2f2` / `#b91c1c` (punto `#ef4444`)
  - Neutro (`Cerrada`, archivado): `#f3f4f6` / `#4b5563` (punto `#9ca3af`)

### Tipografía y pesos estándar

- Fuente principal: **`Inter`** con respaldo `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- Usar **exclusivamente pesos estándar (`400`, `500`, `600`, `700`)** —no usar pesos intermedios (`550`, `650`)— para garantizar renderizado idéntico con fuentes del sistema:
  - `700`: título principal `h1`, importes destacados en detalle/panel y sigla de marca.
  - `600`: conceptos de fila, importes en tabla, títulos de diálogo, ítem activo y etiquetas de sección.
  - `500`: botones, navegación inactiva, etiquetas de formulario y pills de estado.
  - `400`: texto de lectura, metadatos e inputs.
- Aplicar `font-variant-numeric: tabular-nums` en importes, números de trámite (`#55`), fechas y contadores.

### Ergonomía diferenciada: escritorio compacto vs. táctil `44 px`

- **Escritorio con puntero fino (`>= 960 px` y `pointer: fine`):** controles de **`36 px`** (`--ctrl-h: 36px`) en toolbars, filtros y botones principales; **`32 px`** (`--ctrl-h-sm: 32px`) en acciones de fila de tabla y controles densos; botones de sólo ícono de `34×34 px`.
- **Móvil y pantallas táctiles (`@media (max-width: 959px), (pointer: coarse)`):** todos los controles principales, inputs, selects, enlaces del menú y botones de cierre suben a **`44 px` mínimos** (`--ctrl-h: 44px`, `--ctrl-h-sm: 44px`, `.btn-icon: 44×44px`).
- **Móvil `390 px`:** cero desplazamiento horizontal de la página; textos largos y correos con `overflow-wrap: anywhere`; foco visible y contraste WCAG AA (`>= 4.5:1`) en ambos modos.

## Shell, navegación y controles comunes

- **Navegación lateral full-height (`>= 1280 px`):** sidebar fijo de `228 px` con marca institucional arriba, módulos agrupados al centro y cuenta + acción de cierre de sesión al pie (sin topbar burocrática con «Sesión activa» en escritorio). Plegable a riel de `64 px` conservando:
  - atributo `title` (y etiqueta visible al foco/hover) en cada enlace `.nav-link`;
  - el botón de cierre de sesión siempre accesible en el pie del riel.
- **Navegación en `< 1280 px` (tablets y móvil):** topbar móvil compacta (`56 px`) con botón menú de `44×44` y marca; al abrir el drawer lateral superpuesto, el cierre usa un botón limpio de **sólo ícono `×` de `44×44 px`** (`aria-label="Cerrar menú"`, sin texto visible «Cerrar»), con soporte de `Escape`, clic en el scrim, trampa de foco `Tab` y devolución de foco al botón que lo abrió.
- **Jerarquía de acciones (4 niveles):**
  1. **Primario (`.btn-primary`):** marino sólido, reservado al CTA dominante de la pantalla («Nueva solicitud») y a filas que exigen intervención operativa («Revisar solicitud», «Revisar pago», «Corregir solicitud»).
  2. **Secundario (`.btn-secondary`):** fondo blanco con `--border-control` y texto `--ink-strong`, para acciones útiles no dominantes (paginación, «Descargar», «Ver archivo»).
  3. **Sutil de fila / ghost (`.btn-ghost` / `.btn-row`):** para acciones pasivas repetitivas («Ver detalle» con borde `--border-subtle` y chevron sutil `›` en escritorio para que se lea como botón sin competir con el primario; «Limpiar» / «Cerrar» / cierres `×` sin borde en reposo).
  4. **Destructivo / rechazo (`.btn-danger` / `.btn-danger-solid`):** `.btn-danger` (superficie roja suave) para rechazos, anulaciones o revocaciones; `.btn-danger-solid` (fondo sólido rojo) únicamente en confirmaciones irreversibles. En móvil (`<= 640 px`), los botones `.button` / `.btn` permiten salto de línea controlado para evitar desbordes horizontales.
- **Primitivos compartidos de composición (`base.css` y `comunes`):**
  - `.page-back`: enlace discreto «← Volver a …» sobre el `h1` en detalles y formularios.
  - `.kv-list`: lista clave-valor (`<dl>`) en dos columnas en escritorio y apilada en `<= 640 px`.
  - `.ui-tabs-segmented` y `.ui-tabs-underline`: pestañas sobre enlaces reales `<a>` con `aria-current="page"`.
  - `templates/comunes/mensajes_flash.html`: contenedor `.flash-messages` que mapea etiquetas Django (`message-error` con `role="alert"`; `message-warning`, `message-success` e `info` con `role="status"`).
  - `{% load formato_ars %}` (`{{ valor|ars }}`): filtro compartido para importes ARS homogéneos en plantillas sin importar helpers entre módulos.
- **Selectores `<select>`:** estilizar siempre con `appearance: none`, `select::picker-icon { display: none; }` (evita flecha doble en Chromium moderno), `line-height: 20px`, `padding-block` exacto (`7px` en `36px`, `11px` en `44px`) y chevron SVG único a la derecha.
- **Iconografía:** usar exclusivamente la familia **Lucide** como SVG inline (`viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="1.75"`, `stroke-linecap="round"`, `stroke-linejoin="round"`, `aria-hidden="true"`).
- **Diálogos, paneles rápidos y visor compartido (`<dialog>`):** superficie opaca blanca, backdrop oscurecido con leve blur y bloqueo de scroll del documento (`body:has(...[open])`). El cierre usa botón único `×` accesible (`.btn-icon`, `aria-label` claro y sin duplicar botones «Cerrar» en el pie), tecla `Escape` y clic en el backdrop protegido con guarda `pointerdown` (evita cerrar si el arrastre empezó adentro), devolviendo el foco al disparador con `focus({ preventScroll: true })`. Respetar `@media (prefers-reduced-motion: reduce)`. En vistas convergentes con múltiples filas, usar un único `<dialog>` poblado desde `<template>` cuando corresponda en nuevas implementaciones. El visor compartido (`visor_documento_dialogo.html` + `visor_documentos.css`) sigue el mismo estándar cálido sin azules saturados heredados.
- **Adjunto de archivos (`adjuntar_archivos.js`):** los formularios que implementen una zona de carga propia (`.rp-dropzone`, `.sd-dropzone`, `[data-file-drop-custom]`, etc.) deben excluir el inicializador genérico para evitar dropzones duplicados sobre un mismo `<input type="file">`.

### Convenciones editoriales, importes y formularios (`D-2`)

- **Voseo argentino y sentence case:** redactar mensajes y ayudas en voseo claro («Completá», «Seleccioná», «Revisá»; evitar fórmulas como «para su cuenta»). Usar sentence case en navegación, títulos, pestañas y botones («Solicitud de gasto», «Solicitud de facturación», «Ver detalle ›»).
- **Formato ARS único:** mostrar todo importe en pesos como `$ 195.000,00` (punto de miles, coma decimal, dos dígitos) con `tabular-nums`, prefijo `-$ ` en negativos y `—` si falta, reutilizando `{{ valor|ars }}`.
- **Retorno único arriba a la izquierda:** las pantallas secundarias y formularios incluyen un solo enlace `.page-back` («← Volver a …») arriba a la izquierda; no duplicarlo con otro «Volver» al final del formulario.
- **Campos opcionales:** indicar `(Opcional)` en la etiqueta de los campos no requeridos; prohibido usar asteriscos `*` o leyendas globales «Los campos con * son obligatorios».

## Mejora progresiva y arquitectura CSS

- **Stack:** plantillas Django, HTML semántico, CSS nativo y JS modular sin Node.js, npm, Tailwind ni SPA.
- **Orden estricto de cascada en `templates/base.html`:** `tokens.css` → `base.css` → `navegacion.css` → hojas locales del módulo (`{% block extra_css %}` / `{% block extra_head %}`). No colocar bloques `<style>` inline después de `extra_css`.
- **Contrato sin JavaScript:**
  - Las pestañas/segmentos de vista rápida (por ejemplo, `Todas` | `Requieren atención` en `/gastos/`) deben renderizarse como **enlaces `<a>` reales con query params** (`?atencion=1` / listado base), nunca como botones que dependan sólo de JS.
  - Las barras de filtro con búsqueda dinámica en vivo deben conservar un botón `Filtrar` operativo para navegación GET sin JS (visible en `html:not(.js)` / `<noscript>` o cuando el usuario seleccione un filtro de fecha que requiera envío).
  - La descarga de documentos y el enlace al detalle desde el concepto deben seguir funcionando sin JS.

## Anti-patrones prohibidos para agentes

Al diseñar, implementar o revisar vistas, **rechazar** los siguientes patrones:

1. **Boxitis:** encerrar en cajas con borde de `1px` elementos que se agrupan mejor por espaciado (topbar con botones encerrados, barra de filtros metida en tarjeta pesada cuando es toolbar plana, botones `Ver detalle` gigantes de ancho completo en tabla de escritorio).
2. **Controles de `44 px` fijos en escritorio:** no forzar altura táctil móvil sobre toolbars, filtros y filas de tabla en pantallas de escritorio (`pointer: fine`).
3. **Duplicación de avisos y controles:** no mostrar un banner superior de atención cuando ya existe una pestaña o filtro de «Requieren atención» visible a pocos píxeles con la misma acción.
4. **Texto redundante junto a íconos universales de cierre:** no renderizar botones `× Cerrar` en el drawer de navegación ni botones `Cerrar` de ancho completo en paneles laterales; usar `×` con `aria-label` claro.
5. **Azul saturado en datos y títulos:** no usar `#090979`, `#084298` ni `#0d6efd` hardcodeados ni teñir todos los importes y `h1` de azul brillante.
6. **Controles `<select>` nativos sin pulir o con doble flecha:** no omitir `select::picker-icon { display: none; }` ni dejar el texto descentrado verticalmente.
7. **SVGs improvisados a mano o mezcla de librerías de íconos:** usar trazos coherentes de Lucide.
8. **Peleas de especificidad con `!important`:** resolver conflictos corrigiendo la cascada en `base.css` / `tokens.css` y selectores con prefijo de componente; nunca agregar `!important` para tapar estilos globales (excepción válida: `[hidden] { display: none !important; }`).
9. **Colisiones globales y redeclaración de `:root` en `extra_css`:** prohibido redeclarar tokens en `:root` o sobrescribir clases compartidas sin prefijo (`.btn`, `.card`, `.app-ic`, `.btn-danger`, `.badge`) en hojas locales cargadas por `{% block extra_css %}`. Toda hoja de módulo o vista específica debe prefijar sus selectores (`.fac-*`, `.bandeja-*`, `.gestion-*`).

## Encargo corto y verificación

Cada encargo visual debe indicar: vista y rol, archivos permitidos, estados a comprobar (con datos, vacío, filtrado, error, permisos y sin JS) y verificación en escritorio (`1280×800`) y móvil (`390×844`, indicando si fue simulación o teléfono real).

- **Checklist de verificación cruzada (si el cambio toca `tokens.css`, `base.css`, `navegacion.*`, `visor_documentos.*` o `adjuntar_archivos.js`):**
  1. `/facturacion/` y `/facturacion/<id>/`: tooltips `(i)` operativos por teclado (`Tab`) y sin JS, y todos los botones `.btn` sin recorte ni overflow horizontal en `390×844`.
  2. `/documentos/<id>/revision/`: cierre de visor y layout legibles tras cambios compartidos.
  3. `/gastos/<id>/pagar/` y `/facturacion/<id>/cobros/nuevo/`: componente compartido `selector_comprobante` sin doble dropzone, con vista previa local y respaldo `<input type="file">` nativo sin JS; `/gastos/presentar/` sin doble caja de carga.
  4. `/gastos/<id>/#pago-externo`: visor compartido con `×` accesible (`34×34 px` escritorio / `44×44 px` móvil), sin texto «Cerrar» y cierre con `Escape`.
  5. Navegación lateral: contador `.app-nav-badge` en `Avisos` visible expandido y oculto al replegar al riel de `64 px`, más etiquetas `title` en todos los enlaces.
  6. Vistas con hojas locales (`/gastos/administracion/catalogos/`, `/gestion/reportes/gastos/`, `/gestion/reportes/facturacion/`, `/gestion/configuracion/<circuito>/`): tokens cálidos intactos sin redeclaraciones de `:root` ni `!important` globales, y `@media print` A4 operativo en reportes.
  7. Registrar evidencia antes/después para revisión compartida antes de integrar a `main`.

> **Decisiones de convergencia integradas (`D-2`–`D-5`):** las convenciones `D-2` (voseo argentino, sentence case, formato ARS `{{ valor|ars }}`, retorno único `.page-back` y marca `(Opcional)`), `D-3` (bandeja `/facturacion/` con pestañas `Todas | Requieren atención (N)`, 25 filas completas, tarjetas `< 960 px`, distinción solicitante/correo y verbo «Verificar ingreso»), `D-4` (`<details>` para re-revisión documental cuando existe resultado vigente y pestaña `Requieren atención` para Solicitantes en `/gastos/`) y `D-5` (guarda y confirmación explícita en «Cerrar trámite» sin exigir motivo, placeholder `"Seleccioná…"` en `/facturacion/nueva/`, nombres visibles internos vs `Titular`/`Cooperadora` para solicitantes en historial común y copy sin promesas de notificación inexistente) quedaron implementadas y revisadas con Matías en la convergencia `Inc 5–9B` sin alterar permisos ni contratos de dominio.
