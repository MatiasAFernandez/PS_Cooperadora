/**
 * Panel Compacto Master-Detail y Drawer Lateral — PS_Cooperadora
 * Micro-interacciones en JavaScript nativo (ES6+) sin frameworks externos.
 * Cumple con GAST-R06, directrices de accesibilidad (a11y) y fallback de copiado LAN.
 */

let drawerActivo = null;

/**
 * Abre el Drawer lateral correspondiente al ID de la solicitud.
 * @param {string|number} id - Identificador de la solicitud.
 */
function abrirDrawer(id) {
  const panelId = `drawer-solicitud-${id}`;
  const panel = document.getElementById(panelId);
  const backdrop = document.getElementById("drawer-backdrop");

  if (!panel || !backdrop) {
    return;
  }

  // Cerrar cualquier drawer previamente abierto
  if (drawerActivo && drawerActivo !== panel) {
    cerrarDrawer();
  }

  drawerActivo = panel;
  panel.style.display = "flex";
  // Pequeño retardo para permitir la transición CSS de slide-in
  requestAnimationFrame(() => {
    backdrop.classList.add("active", "is-open");
    panel.classList.add("open", "is-open");
  });

  // Foco en el botón de cerrar para accesibilidad (WCAG)
  const botonCerrar = panel.querySelector(".btn-close, .drawer-close");
  if (botonCerrar) {
    botonCerrar.focus();
  }

  document.addEventListener("keydown", manejarTecladoDrawer);
}

/**
 * Cierra el Drawer lateral actualmente activo.
 */
function cerrarDrawer() {
  if (!drawerActivo) {
    return;
  }

  const panel = drawerActivo;
  const backdrop = document.getElementById("drawer-backdrop");

  if (backdrop) {
    backdrop.classList.remove("active", "is-open");
  }
  panel.classList.remove("open", "is-open");

  // Ocultar tras finalizar la animación de 250ms
  setTimeout(() => {
    panel.style.display = "none";
    if (drawerActivo === panel) {
      drawerActivo = null;
    }
  }, 250);

  document.removeEventListener("keydown", manejarTecladoDrawer);
}

/**
 * Maneja eventos de teclado cuando el drawer está abierto (ESC para cerrar).
 * @param {KeyboardEvent} evento
 */
function manejarTecladoDrawer(evento) {
  if (evento.key === "Escape") {
    cerrarDrawer();
  }
}

/**
 * Copia texto (CBU o alias) al portapapeles con fallback para entornos LAN HTTP.
 * @param {string} texto - Cadena a copiar.
 * @param {HTMLElement} boton - Elemento botón para feedback visual.
 */
function copiarAlPortapapeles(texto, boton) {
  if (!texto) {
    return;
  }

  // Idempotencia visual: prevenir doble clic rápido
  if (boton && boton.classList.contains("copied")) {
    return;
  }

  function mostrarFeedback() {
    if (!boton) {
      return;
    }
    if (!boton.dataset.originalText) {
      boton.dataset.originalText = boton.innerHTML;
    }
    const textoOriginal = boton.dataset.originalText;
    boton.classList.add("copied");
    boton.innerHTML = "✓ Copiado";
    setTimeout(() => {
      boton.classList.remove("copied");
      boton.innerHTML = textoOriginal;
      delete boton.dataset.originalText;
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

/**
 * Fallback de copiado usando textarea temporal fuera de pantalla y execCommand.
 * @param {string} texto
 * @param {Function} callbackExito
 */
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

// Inicialización de eventos al cargar el DOM
document.addEventListener("DOMContentLoaded", () => {
  const backdrop = document.getElementById("drawer-backdrop");
  if (backdrop) {
    backdrop.addEventListener("click", cerrarDrawer);
  }
});
