# Guía de Diseño Visual y Sistema de Tokens Institucionales

- **Estado:** Especificación canónica de UI/UX (Calidad 2026).
- **Origen de diseño:** Ingeniería inversa visual de la Universidad Tecnológica Nacional - Facultad Regional Resistencia (UTN FRRe, relevamiento 17/10/2026).
- **Ámbito:** Todas las plantillas web (`templates/`) del proyecto `PS_Cooperadora`.
- **Archivos asociados:**
  - Tokens CSS para producción: [`static/css/tokens.css`](../../static/css/tokens.css).
  - Tokens CSS de referencia: [`docs/visual-guide/tokens.css`](tokens.css).
  - Catálogo vivo de componentes: [`docs/visual-guide/muestrario.html`](muestrario.html).

---

## 1. Principios del Sistema de Diseño

El sistema visual de `PS_Cooperadora` adopta un **estándar moderno de aplicación web de 2026** (inspirado en herramientas de alta productividad como Linear o Vercel Dashboard):

1. **Alta densidad y ergonomía:** Espaciado optimizado para que el personal administrativo y directivo visualice 20–30 registros sin fatiga ni scroll vertical excesivo.
2. **Accesibilidad sin excepciones (WCAG 2.1 AA):** Todos los pares de color de texto y fondos superan el ratio de contraste de **6:1**. Todas las zonas de interacción (botones, enlaces, filas seleccionables) respetan la cota mínima de toque de **44 px** (`--row-height-dense`).
3. **Simplicidad técnica sin cadenas de compilación complejas:** No se utilizan frameworks pesados SPA (React, Vue) ni ejecutables de Node.js/npm. Se aprovecha el potencial de **HTML5 semántico**, **CSS moderno** (`backdrop-filter`, `transform`, `CSS variables`, `grid`, `flexbox`) y **JavaScript nativo modular (ES6+)**.
4. **Ancho de grilla estandarizado:** El contenedor principal tiene un ancho máximo fijo de **1140 px** (`--content-width`), alineado con las páginas públicas utilitarias de la UTN FRRe.

---

## 2. Paleta de Colores y Tokens Oficiales

### Colores Institucionales

| Token CSS | Valor HEX | Uso y Evidencia UTN FRRe |
|---|---|---|
| `--ref-deep-blue` | `#090979` | Azul profundo institucional; cabeceras, pie de página y gradientes. |
| `--ref-blue` | `#084298` | Azul primario; botones principales, enlaces y encabezados destacados. |
| `--ref-bright-blue` | `#0d6efd` | Azul interactivo; foco visual (`:focus-visible`), bordes activos y acentos. |
| `--ref-text` | `#444444` | Gris carbón; texto de lectura principal con contraste certificado (>7:1 sobre blanco). |
| `--ref-heading` | `#37423b` | Títulos y etiquetas de formulario de alta jerarquía. |
| `--ref-bg-surface` | `#ffffff` | Fondo de tarjetas, tablas, modales y panel deslizante (drawer). |
| `--ref-bg-muted` | `#f8fafc` | Fondo base de la aplicación y alternancia de filas. |
| `--ref-border` | `#e2e8f0` | Bordes suaves de 1px (`border-slate-200`) para delimitar componentes sin saturar. |

### Tokens Semánticos de Estado

| Estado | Token Texto | Token Fondo | Token Borde | Contraste | Uso en Trámites |
|---|---|---|---|---|---|
| **Éxito / Pagado** | `#166534` | `#effaf2` | `#bbf7d0` | 6.8:1 | Solicitud aceptada, pago realizado, rendición conforme. |
| **Advertencia / Mora** | `#854d0e` | `#fffbeb` | `#fef08a` | 6.2:1 | Comprobantes en mora, retención ATP aplicable. |
| **Error / Bloqueo** | `#9f1239` | `#fff1f2` | `#fecdd3` | 7.1:1 | Solicitud rechazada, bloqueo por deuda documental, 403/500. |
| **Info / En Revisión** | `#075985` | `#eff8ff` | `#bae6fd` | 6.5:1 | Revisión documental, compra directa con proforma. |
| **Neutro / Cerrado** | `#475569` | `#f1f5f9` | `#cbd5e1` | 6.4:1 | Trámites finalizados, reintegros saldados. |

---

## 3. Escala Tipográfica y Geometría

La tipografía institucional es **Montserrat** (cargada con fuentes del sistema como fallback: `system-ui, -apple-system, sans-serif`).

| Nivel | Tamaño | Peso | Interlínea | Aplicación |
|---|---|---|---|---|
| `--text-xs` | `0.75rem` (12px) | 600 | 1.2 | Badges de estado, píldoras, metadatos y tooltips. |
| `--text-sm` | `0.875rem` (14px) | 500/600 | 1.3 | Celdas de tablas densas, inputs, botones secundarios. |
| `--text-base` | `1.00rem` (16px) | 400 | 1.5 | Texto de lectura, descripciones y ayudas. |
| `--text-lg` | `1.125rem` (18px) | 600 | 1.3 | Títulos de tarjetas y resúmenes. |
| `--text-xl` | `1.25rem` (20px) | 700 | 1.2 | Títulos de panel y subtítulos de módulo. |
| `--text-2xl` | `1.50rem` (24px) | 700 | 1.2 | Título principal de página (`h1`/`h2`). |

### Geometría y Elevaciones

- **Ancho del contenedor principal:** `1140px` (`max-width: var(--content-width)`).
- **Radio de esquinas:**
  - Pequeño (`--radius-sm: 0.25rem;` / 4px): Inputs y badges.
  - Mediano (`--radius-md: 0.375rem;` / 6px): Botones, tarjetas y selects.
  - Grande (`--radius-lg: 0.5rem;` / 8px): Contenedor de tablas, modales y drawer.
- **Bordes:** Líneas delgadas `1px solid var(--ref-border)`.
- **Efecto de desenfoque:** `backdrop-filter: blur(3px);` con capa semi-transparente `rgba(15, 23, 42, 0.4)` para overlays y modales.

---

## 4. Estándar Arquitectónico para Próximas Tareas (Issue #92)

Para la implementación del **Panel Compacto Master-Detail y Drawer Lateral (Issue #92)**, la solución técnica debe cumplir con las siguientes especificaciones:

```
+-------------------------------------------------------------------------------+
|  BARRA DE NAVEGACIÓN INSTITUCIONAL (1140px)                                   |
+-------------------------------------------------------------------------------+
|  FILTROS COMPACTOS Y ACCIONES DIRECTAS                                         |
+-------------------------------------------------------------+-----------------+
|  TABLA MASTER (8 columnas)                                  | DRAWER LATERAL  |
|  - Filas de 44px de altura ergonómica                       | - Slide-in 250ms|
|  - Sticky header con borde sutil                            | - Ancho 520px   |
|  - Hover interactivo (#f8fafc) y selección (#eff6ff)        | - CBU/Alias con |
|  - Badges atenuados de estado y modalidad                   |   botón copiado |
|  - Click en fila abre el Drawer de detalle                  | - Cierre con Esc|
+-------------------------------------------------------------+-----------------+
```

### 1. Tabla Master de 8 Columnas
- Columnas: ID, Concepto/Justificación, Modalidad, Centro de Costo, Monto Estimado (ARS), Estado, Fecha, Acciones.
- Altura de fila: 44 px exactos para ergonomía táctil y de cursor.
- Cabecera fija (`position: sticky; top: 0; background: #f8fafc; z-index: 2`).

### 2. Drawer Lateral (Detail)
- Panel deslizante lateral derecho de ancho fijo `520px` (`--drawer-width`).
- Animación de entrada suave: `transform: translateX(0)` en 250ms (`cubic-bezier(0.4, 0, 0.2, 1)`).
- Backdrop oscuro con desenfoque: `background: rgba(15, 23, 42, 0.4); backdrop-filter: blur(3px)`.
- Cierre intuitivo: al presionar la tecla `Escape`, hacer clic en el botón de cerrar (`✕`) o hacer clic fuera del panel.

### 3. Copiado Rápido de CBU / Alias
- Botón accesible `.btn-copy` que interactúa con la API nativa `navigator.clipboard.writeText`.
- Feedback visual instantáneo: transición de ícono a check verde (`✓ Copiado`) y retorno automático a los 2 segundos.
- Control de privacidad: sólo se renderizan los datos bancarios y el botón de copiado si el actor posee la capacidad `gastos.registrar_pago` o es el titular de la solicitud (`SPEC-013`).

### 4. JavaScript Nativo Modular
- Ubicación: `static/gastos/js/gastos_master_detail.js`.
- Tamaño: Entre 50 y 80 líneas de JavaScript puro (ES6+).
- Estilo: Código documentado con JSDoc, sin frameworks externos, con gestión defensiva de eventos y eliminación de listeners al desmontar.

---

## 5. Muestrario de Componentes

Para inspeccionar interactivamente todos los componentes en funcionamiento local sin necesidad de levantar el servidor de base de datos, abrir directamente en cualquier navegador web:

```bash
# Abrir el muestrario estático local
xdg-open docs/visual-guide/muestrario.html
```
