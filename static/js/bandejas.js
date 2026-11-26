export function enlaceResumenDeFila(evento, selectorEnlace) {
    const objetivo = evento.target;
    if (!(objetivo instanceof Element) ||
        evento.defaultPrevented || evento.button !== 0 ||
        evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return null;

    const fila = objetivo.closest("tr[data-resumen]");
    if (!fila || objetivo.closest("dialog")) return null;

    const control = objetivo.closest("a, button, input, select, textarea");
    if (control) return control.matches(selectorEnlace) ? control : null;

    const seleccion = window.getSelection();
    if (seleccion && !seleccion.isCollapsed &&
        (fila.contains(seleccion.anchorNode) || fila.contains(seleccion.focusNode))) return null;

    return fila.querySelector(selectorEnlace);
}

export function iniciarDesplazamiento(resultados) {
    const contenedor = resultados.querySelector(".bandeja-desplazamiento");
    const tabla = contenedor?.querySelector("table");
    const filas = tabla?.tBodies[0].rows;
    const cantidadVisible = 5;
    if (!filas || filas.length <= cantidadVisible) return;

    const ultimaVisible = filas[cantidadVisible - 1];
    function ajustarAltura() {
        const altura = ultimaVisible.getBoundingClientRect().bottom -
            tabla.getBoundingClientRect().top;
        contenedor.style.setProperty("--bandeja-alto-visible", `${altura}px`);
    }

    contenedor.classList.add("bandeja-desplazamiento--activo");
    contenedor.tabIndex = 0;
    contenedor.setAttribute("role", "region");
    contenedor.setAttribute("aria-label", "Listado desplazable de solicitudes");
    ajustarAltura();

    const observador = new ResizeObserver(ajustarAltura);
    observador.observe(tabla.tHead);
    for (const fila of Array.from(filas).slice(0, cantidadVisible)) {
        observador.observe(fila);
    }
    return observador;
}

export function sincronizarPestanas(bandeja, pagina) {
    const actuales = bandeja.querySelector("[data-bandeja-tabs]");
    const nuevas = pagina.querySelector("[data-bandeja-tabs]");
    if (!actuales || !nuevas) return;

    nuevas.querySelectorAll("[data-bandeja-tab]").forEach((origen) => {
        const destino = actuales.querySelector(`[data-bandeja-tab="${origen.dataset.bandejaTab}"]`);
        if (!destino) return;
        destino.setAttribute("href", origen.getAttribute("href"));
        destino.className = origen.className;
        destino.replaceChildren(...origen.childNodes);
    });
}
