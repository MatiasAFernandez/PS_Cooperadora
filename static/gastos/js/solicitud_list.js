const pantallaAncha = window.matchMedia("(min-width: 960px)");
const RESPALDO_CIERRE_MS = 80;

function duracionSalida(panel) {
    const estilo = window.getComputedStyle(panel);
    if (estilo.animationName === "none") return 0;
    const duracion = estilo.animationDuration.split(",")[0].trim();
    const valor = Number.parseFloat(duracion);
    if (!Number.isFinite(valor)) return 0;
    return duracion.endsWith("ms") ? valor : valor * 1000;
}

function clicFueraDelPanel(evento, panel) {
    const rect = panel.getBoundingClientRect();
    return (
        evento.clientX < rect.left ||
        evento.clientX > rect.right ||
        evento.clientY < rect.top ||
        evento.clientY > rect.bottom
    );
}

function cerrarPanel(panel) {
    if (!panel.open || panel.classList.contains("is-closing")) return;

    let cerrado = false;
    let respaldo = null;

    const finalizar = () => {
        if (cerrado) return;
        cerrado = true;
        if (respaldo !== null) window.clearTimeout(respaldo);
        panel.removeEventListener("animationend", alTerminar);
        panel.classList.remove("is-closing");
        if (panel.open) panel.close();
    };

    const alTerminar = (evento) => {
        if (evento.target === panel && evento.animationName === "bandeja-panel-sale") {
            finalizar();
        }
    };

    panel.classList.add("is-closing");
    const duracion = duracionSalida(panel);
    if (!duracion) {
        finalizar();
        return;
    }
    panel.addEventListener("animationend", alTerminar);
    respaldo = window.setTimeout(finalizar, duracion + RESPALDO_CIERRE_MS);
}

document.querySelectorAll("[data-vista-rapida]").forEach((enlace) => {
    const panel = document.getElementById(enlace.dataset.vistaRapida);
    if (!panel || typeof panel.showModal !== "function") return;

    enlace.addEventListener("click", (evento) => {
        if (
            !pantallaAncha.matches ||
            evento.ctrlKey ||
            evento.metaKey ||
            evento.shiftKey ||
            evento.altKey
        ) return;
        evento.preventDefault();
        if (panel.open) return;
        panel.classList.remove("is-closing");
        panel.showModal();
    });

    panel.addEventListener("click", (evento) => {
        // "Cerrar" usa un form method="dialog"; interceptarlo conserva la salida suave.
        const objetivo = evento.target;
        if (objetivo instanceof Element) {
            const botonCerrar = objetivo.closest('form[method="dialog"] button');
            if (botonCerrar && panel.contains(botonCerrar)) {
                if (!panel.classList.contains("is-closing")) {
                    evento.preventDefault();
                    cerrarPanel(panel);
                }
                return;
            }
        }
        // El backdrop tiene como target al propio <dialog>; el rectángulo evita
        // cerrar cuando el clic cae en el padding interior del cuadro.
        if (objetivo !== panel || !clicFueraDelPanel(evento, panel)) return;
        cerrarPanel(panel);
    });

    panel.addEventListener("cancel", (evento) => {
        if (!panel.open || panel.classList.contains("is-closing")) return;
        evento.preventDefault();
        cerrarPanel(panel);
    });

    panel.addEventListener("close", () => {
        panel.classList.remove("is-closing");
        enlace.focus();
    });

    pantallaAncha.addEventListener("change", () => {
        if (!pantallaAncha.matches && panel.open) cerrarPanel(panel);
    });
});
