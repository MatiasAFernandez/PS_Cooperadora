# PAQUETE DE AUDITORÍA TÉCNICA — ISSUE #92 (INCREMENTO I3)

**Destinatario:** Gemini Argon (Auditor Técnico y Arquitecto de Software)  
**Proyecto:** Sistema de Gestión — Asociación Cooperadora UTN FRRe (`PS_Cooperadora`)  
**Incremento:** I3 — Cierre técnico de Gastos: Doble Flujo, ATP, Catálogos y UX Compacta  
**Especificación canónica:** [SPEC-020](docs/specs/020-franco-doble-flujo-atp-ux.md) (`GAST-R06` / `SPEC-013`)  
**Issue auditada:** [Issue #92 en GitHub](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/92) — `feat(gastos/ui): panel compacto Master-Detail con Drawer lateral, ancho expandido y privacidad bancaria`  
**Rama:** `feat/92-panel-compacto-ui`  
**Autor:** Franco Damián Sánchez (Gastos y Pagos)  
**Fecha de corte:** 03/11/2026 14:50  

---

## 1. Instrucción para el Auditor (Prompt para Gemini Argon)

> Actúa como **Auditor Técnico Senior y Arquitecto de Software y UI/UX** del sistema de la Asociación Cooperadora.  
> Tu objetivo es realizar una **revisión exhaustiva de código (Code Review)** de la implementación de la **Issue #92** desarrollada por Franco Sánchez conforme a los requisitos de la demo y SPEC-020.
> 
> Evalúa la solución contra:
> 1. **Privacidad Estricta en SSR (GAST-R06 / SPEC-013):** En `SolicitudGastoListView` y `solicitud_list.html`, la exclusión de datos bancarios para perfiles sin capacidad de registrar pago (ej. `demo_lectura` o usuarios ajenos) debe ocurrir en el servidor mediante Django Templates (`{% if s.puede_ver_transferencia %}`). Comprobar que CBU/alias, titular y correo **no se emiten** ni en el cuerpo del Drawer ni en atributos `data-*` del DOM.
> 2. **Panel Compacto Master-Detail de Alta Densidad (Calidad 2026):** Rediseño ergonómico de `solicitud_list.html` con tabla de 8 columnas (`ID`, `Modalidad`, `Centro de Costo`, `Concepto`, `Monto Estimado`, `Estado`, `Fecha`, `Acciones`), aprovechando el ancho estándar de 1140px, altura de fila densa de 44px (`var(--row-height-dense)`), números tabulares (`.font-tabular`), y badges semánticos con contraste verificado WCAG >6:1.
> 3. **Micro-interacciones y Drawer Lateral en Vanilla JS:** Código nativo en `static/gastos/js/drawer.js` (~150 líneas) sin frameworks pesados ni dependencias externas: apertura con animación slide-in (`translateX`), cierre mediante backdrop, botón de escape (tecla `ESC`) o botón cerrar, foco accesible y botón de copiado rápido de CBU/alias.
> 4. **Fallback de Copiado CBU para Red Local HTTP (LAN):** Mecanismo híbrido en `copiarAlPortapapeles`: usa `navigator.clipboard.writeText` en contextos seguros (`localhost` o `HTTPS`) y recurre automáticamente a `<textarea>` temporal off-screen con `document.execCommand("copy")` en IPs de intranet (`http://192.168.x.x:8000`), garantizando feedback visual ("✓ Copiado") por 2 segundos.
> 5. **Optimización de Consultas SQL contra N+1:** Queryset en `SolicitudGastoListView` optimizado mediante `select_related("centro_costo", "pago_externo")` y `prefetch_related("revisiones_datos_transferencia")`, con paginación a 25 registros (`Paginator`), asegurando un conteo fijo y acotado de queries (6 queries) independiente del número de filas.
> 6. **Cero Regresiones:** Compatibilidad con las 750 pruebas existentes, elevando la suite a 757 tests en verde.
>
> **Estructura del Dictamen Requerida:**
> - **1. Veredicto:** `[APROBADO]`, `[APROBADO CON OBSERVACIONES MENORES]` o `[RECHAZADO CON CAMBIOS REQUERIDOS]`.
> - **2. Evaluación de Criterios Clave:**
>   - Privacidad estricta en SSR y seguridad de datos bancarios.
>   - Ergonomía visual, alta densidad y tokens institucionales.
>   - Robustez de JS nativo y fallback de copiado LAN.
>   - Rendimiento ORM y prevención de N+1.
>   - Cobertura de pruebas unitarias en `test_panel_compacto_drawer.py`.
> - **3. Observaciones y Sugerencias de Optimización (si aplican).**
> - **4. Dictamen de Continuidad:** Autorización para avanzar con la **Issue #93** (`I3-05`: `feat(gastos): política de advertencias visuales y control determinista por comprobantes adeudados`).

---

## 2. Estado de Verificación Automatizada

- **Nuevas pruebas del Panel y Drawer (`test_panel_compacto_drawer.py`):** `7 passed in 1.92s` (100% verde).
- **Suite completa del módulo Gastos (`tests/gastos/`):** `420 passed in 27.27s` (100% verde).
- **Muestra de Entrega e Invariantes (`test_muestra_entrega.py`):** `3 passed in 1.66s`.
- **Suite Completa del Proyecto (`pytest -q`):** `757 passed in 69.09s` (0 regresiones).
- **Linter y Formato (`ruff check .`):** `All checks passed!`
- **Django system check (`python manage.py check`):** `System check identified no issues (0 silenced).`
- **Integridad de migraciones (`makemigrations --check`):** `No changes detected.`

---

## 3. Código Fuente Modificado e Invariantes Implementados

### 3.1. Vista y Optimización de Queryset (`gastos/views.py`)

```python
class SolicitudGastoListView(View):
    """Listado de solicitudes de gasto visibles para el actor (panel compacto Master-Detail)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        solicitudes = (
            visible_expenses(actor)
            .select_related("centro_costo", "pago_externo")
            .prefetch_related("revisiones_datos_transferencia")
        )
        filtro_form = FiltroEstadoGastoForm(request.GET)
        if filtro_form.is_valid():
            solicitudes = filtro_form.filtrar_fecha(solicitudes, "fecha_creacion")
            estado = filtro_form.cleaned_data["estado"]
            if estado:
                solicitudes = solicitudes.filter(estado=estado)
            concepto = filtro_form.cleaned_data["q"]
            if concepto:
                solicitudes = solicitudes.filter(concepto__icontains=concepto)
        else:
            solicitudes = solicitudes.none()

        paginator = Paginator(solicitudes, 25)
        page_number = request.GET.get("page") or request.GET.get("pagina")
        page_obj = paginator.get_page(page_number)

        # Enriquecimiento SSR con evaluación de privacidad sin consultas redundantes (GAST-R06 / SPEC-013)
        puede_ver_todas_transferencias = has_capability(actor, "gastos.registrar_pago")
        for s in page_obj:
            s.puede_ver_transferencia = (
                puede_ver_todas_transferencias or s.solicitante_id == actor.subject_id
            )
            if s.puede_ver_transferencia:
                revs = list(s.revisiones_datos_transferencia.all())
                s.datos_transferencia_actual = revs[-1] if revs else None
            else:
                s.datos_transferencia_actual = None

        parametros = request.GET.copy()
        parametros.pop("page", None)
        parametros.pop("pagina", None)

        return render(
            request,
            "gastos/solicitud_list.html",
            {
                "solicitudes": page_obj,
                "page_obj": page_obj,
                "is_paginated": page_obj.has_other_pages(),
                "filtros_query": parametros.urlencode(),
                "actor": actor,
                "filtro_form": filtro_form,
            },
        )
```

### 3.2. JavaScript Nativo y Fallback LAN (`static/gastos/js/drawer.js`)

```javascript
/**
 * Copia texto (CBU o alias) al portapapeles con fallback para entornos LAN HTTP.
 */
function copiarAlPortapapeles(texto, boton) {
  if (!texto) return;

  function mostrarFeedback() {
    if (!boton) return;
    const textoOriginal = boton.innerHTML;
    boton.classList.add("copied");
    boton.innerHTML = "✓ Copiado";
    setTimeout(() => {
      boton.classList.remove("copied");
      boton.innerHTML = textoOriginal;
    }, 2000);
  }

  // 1. Contexto seguro moderno (HTTPS o localhost)
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard
      .writeText(texto)
      .then(mostrarFeedback)
      .catch((err) => {
        console.warn("navigator.clipboard falló, aplicando fallback execCommand:", err);
        fallbackCopiarTexto(texto, mostrarFeedback);
      });
  } else {
    // 2. Fallback para red local HTTP (IPs 192.168.x.x en demos presenciales)
    fallbackCopiarTexto(texto, mostrarFeedback);
  }
}

function fallbackCopiarTexto(texto, callbackExito) {
  const textarea = document.createElement("textarea");
  textarea.value = texto;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  try {
    const copiado = document.execCommand("copy");
    if (copiado && typeof callbackExito === "function") {
      callbackExito();
    }
  } catch (error) {
    console.error("Fallback de copiado al portapapeles falló:", error);
  } finally {
    document.body.removeChild(textarea);
  }
}
```

### 3.3. Plantilla Master-Detail y Privacidad en SSR (`templates/gastos/solicitud_list.html`)

- **Tabla Densa de 8 Columnas:**
  `ID`, `Modalidad` (chips `Compra Directa` en azul y `Reintegro` en violeta), `Centro de Costo` imputado, `Concepto` (con tooltip y truncamiento ergonómico), `Monto Estimado` (`.font-tabular`), `Estado` (chips de color semántico), `Fecha` y `Acciones` (`Inspeccionar` + `Ver Detalle`).
- **Privacidad Estricta de Datos Bancarios en SSR:**
  ```html
  {% if s.puede_ver_transferencia %}
      {% if s.datos_transferencia_actual %}
          <!-- Renderizado del CBU con botón de 1-click y formato monoespaciado -->
          <span class="font-mono">{{ s.datos_transferencia_actual.cbu_alias }}</span>
          <button type="button" class="btn-copy" onclick="copiarAlPortapapeles('{{ s.datos_transferencia_actual.cbu_alias|escapejs }}', this)">
              Copiar CBU
          </button>
      {% endif %}
  {% else %}
      <!-- Privacidad estricta SSR: Ni CBU ni titular se emiten al DOM -->
      <div class="message message-info">
          <strong>Privacidad Institucional:</strong>
          <p>Los datos de transferencia bancaria están restringidos exclusivamente al titular del gasto y al personal autorizado de tesorería (GAST-R06 / SPEC-013).</p>
      </div>
  {% endif %}
  ```
- **Integración con Retención ATP Chaco:**
  En gastos con pago confirmado, el Drawer exhibe automáticamente el desglose: Monto Bruto, Retención ATP Chaco con constancia y Neto Transferido.
- **Acceso Directo a Pago:**
  En solicitudes con estado `ACEPTADA`, si el usuario posee la capacidad `gastos.registrar_pago`, el Drawer despliega el botón directo `Registrar Pago`.

---

## 4. Matriz de Pruebas Implementadas (`tests/gastos/test_panel_compacto_drawer.py`)

| # | Test | Componente | Invariante Verificado |
|---|---|---|---|
| 1 | `test_solicitud_list_renderiza_8_columnas_y_badges` | UI / Tabla Densa | Cabeceras de 8 columnas, badges de modalidad y llamada a `drawer.js`. |
| 2 | `test_solicitud_list_drawer_privacidad_ssr_sin_datos_bancarios` | Seguridad / SSR | `demo_lectura` no recibe CBU/alias ni titular en ninguna parte del HTML (cero fuga de datos). |
| 3 | `test_solicitud_list_drawer_con_datos_bancarios_para_tesoreria` | Permisos / Tesorería | Personal con `gastos.registrar_pago` recibe CBU, titular y botón de copiado `.btn-copy`. |
| 4 | `test_solicitud_list_drawer_con_datos_bancarios_para_titular` | Permisos / Titular | El solicitante accede a sus propios datos bancarios en el Drawer. |
| 5 | `test_solicitud_list_drawer_muestra_desglose_atp` | Dominio / ATP | Exposición en Drawer de bruto, retención ATP con constancia y neto transferido. |
| 6 | `test_solicitud_list_queries_optimizadas_sin_n_mas_1` | Rendimiento ORM | 10 solicitudes con relaciones complejas se resuelven en 6 consultas fijas (sin N+1). |
| 7 | `test_solicitud_list_paginacion_a_25_registros` | Paginador Django | 30 registros generan 25 en página 1 y 5 en página 2, con enlaces Anterior/Siguiente. |

---

## 5. Dictamen Esperado de Gemini Argon

Solicitamos a **Gemini Argon** emitir el informe formal de auditoría técnica con:
1. Dictamen general (`[APROBADO]`).
2. Evaluación sobre la privacidad en SSR (`GAST-R06`), el fallback de copiado LAN y la optimización contra N+1.
3. Autorización para avanzar con la **Issue #93 (`I3-05`)**: `feat(gastos): política de advertencias visuales y control determinista por comprobantes adeudados`.
