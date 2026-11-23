(() => {
    "use strict";

    const pantallaAncha = window.matchMedia("(min-width: 960px)");
    const RESPALDO_CIERRE_MS = 80;
    const DEBOUNCE_BUSQUEDA_MS = 300;

    // -------------------------------------------------------------------------
    // Panel de vista rápida (escritorio >= 960 px)
    // -------------------------------------------------------------------------

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

    function inicializarVistasRapidas(raiz) {
        if (!raiz) return;
        raiz.querySelectorAll("[data-vista-rapida]").forEach((enlace) => {
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

            let empezoEnFondo = false;
            panel.addEventListener("pointerdown", (evento) => {
                empezoEnFondo = evento.target === panel && clicFueraDelPanel(evento, panel);
            });

            panel.addEventListener("click", (evento) => {
                // El cierre de la cabecera usa form method="dialog"; interceptarlo conserva la salida suave.
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
                // cerrar cuando el clic cae en el padding interior y la guarda impide cierres al seleccionar texto.
                if (!empezoEnFondo || objetivo !== panel || !clicFueraDelPanel(evento, panel)) return;
                cerrarPanel(panel);
            });

            panel.addEventListener("cancel", (evento) => {
                if (!panel.open || panel.classList.contains("is-closing")) return;
                evento.preventDefault();
                cerrarPanel(panel);
            });

            panel.addEventListener("close", () => {
                empezoEnFondo = false;
                panel.classList.remove("is-closing");
                if (enlace.isConnected) enlace.focus({ preventScroll: true });
            });
        });
    }

    function urlBusqueda(formulario) {
        const url = new URL(formulario.action);
        const datos = new FormData(formulario);
        for (const [nombre, valor] of datos) {
            if (valor && nombre !== "page" && nombre !== "pagina") {
                url.searchParams.append(nombre, valor);
            }
        }
        if (formulario.dataset.soloAtencion === "1") {
            url.searchParams.set("atencion", "1");
        }
        return url;
    }

    function sincronizarErrores(formulario, origen) {
        formulario.querySelectorAll(".errorlist").forEach((lista) => {
            const campo = lista.closest(".form-group")?.querySelector("[name]");
            if (campo) {
                campo.removeAttribute("aria-invalid");
                const descripciones = (campo.getAttribute("aria-describedby") || "")
                    .split(/\s+/)
                    .filter((id) => id && id !== lista.id);
                if (descripciones.length) {
                    campo.setAttribute("aria-describedby", descripciones.join(" "));
                } else {
                    campo.removeAttribute("aria-describedby");
                }
            }
            lista.remove();
        });

        origen.querySelectorAll(":scope > .errorlist, .form-group .errorlist").forEach((lista) => {
            const copia = lista.cloneNode(true);
            const campoOrigen = lista.closest(".form-group")?.querySelector("[name]");
            if (!campoOrigen) {
                formulario.prepend(copia);
                return;
            }
            const campo = formulario.elements.namedItem(campoOrigen.name);
            const grupo = campo?.closest(".form-group");
            if (!grupo) return;

            copia.id ||= `${campo.id}_error`;
            grupo.append(copia);
            campo.setAttribute("aria-invalid", "true");
            const descripciones = campo.getAttribute("aria-describedby") || "";
            campo.setAttribute("aria-describedby", `${descripciones} ${copia.id}`.trim());
        });
    }

    function iniciarBusqueda(formulario, resultados, estado) {
        const buscador = formulario.elements.namedItem("q");
        const avisoError = "No se pudo actualizar la búsqueda. Se muestran los resultados anteriores. Podés reintentar con «Filtrar».";
        let temporizador;
        let consulta;
        let componiendo = false;

        function informar(texto, modo = "sr") {
            estado.className = `bandeja-estado-busqueda bandeja-estado-busqueda--${modo}`;
            estado.textContent = texto;
        }

        function cargando(activo) {
            if (activo) resultados.setAttribute("aria-busy", "true");
            else resultados.removeAttribute("aria-busy");
            resultados.classList.toggle("is-loading", activo);
        }

        function cancelarBusqueda() {
            window.clearTimeout(temporizador);
            consulta?.abort();
            consulta = null;
            cargando(false);
            if (estado.classList.contains("bandeja-estado-busqueda--cargando")) informar("");
        }

        async function buscar() {
            const url = urlBusqueda(formulario);
            if (url.origin !== window.location.origin) return;

            const peticion = new AbortController();
            consulta = peticion;
            cargando(true);
            informar("Buscando solicitudes…", "cargando");

            try {
                const respuesta = await window.fetch(url, { signal: peticion.signal });
                if (peticion.signal.aborted) return;
                if (!respuesta.ok || respuesta.redirected) {
                    informar(avisoError, "error");
                    return;
                }

                const html = await respuesta.text();
                if (peticion.signal.aborted) return;
                const pagina = new DOMParser().parseFromString(html, "text/html");
                const formOrigen = pagina.querySelector("[data-bandeja-filtros]");
                const resultadosOrigen = pagina.querySelector("[data-bandeja-resultados]");
                if (!formOrigen || !resultadosOrigen) {
                    informar(avisoError, "error");
                    return;
                }

                sincronizarErrores(formulario, formOrigen);
                if (resultadosOrigen.dataset.tieneErrores === "1") {
                    informar("Hay errores en los filtros. La consulta nueva no se aplicó. Se muestran los resultados anteriores.", "error");
                    return;
                }

                window.history.replaceState(window.history.state, "", url);
                resultados.replaceChildren(...resultadosOrigen.childNodes);
                inicializarVistasRapidas(resultados);

                const limpiarActual = formulario.querySelector("[data-bandeja-limpiar]");
                const limpiarOrigen = pagina.querySelector("[data-bandeja-limpiar]");
                if (limpiarActual && limpiarOrigen) {
                    limpiarActual.hidden = limpiarOrigen.hidden;
                    const hrefLimpio = limpiarOrigen.getAttribute("href");
                    if (hrefLimpio) limpiarActual.setAttribute("href", hrefLimpio);
                }

                const tabsActuales = formulario.closest(".bandeja")?.querySelector("[data-bandeja-tabs]");
                const tabsOrigen = pagina.querySelector("[data-bandeja-tabs]");
                if (tabsActuales && tabsOrigen) {
                    tabsOrigen.querySelectorAll("[data-bandeja-tab]").forEach((origen) => {
                        const destino = tabsActuales.querySelector(
                            `[data-bandeja-tab="${origen.dataset.bandejaTab}"]`
                        );
                        const href = origen.getAttribute("href");
                        if (destino && href) destino.setAttribute("href", href);
                    });
                }

                const total = Number(resultadosOrigen.dataset.totalResultados);
                informar(total ? `${total} solicitud${total === 1 ? "" : "es"}` : "No se encontraron solicitudes.");
            } catch {
                if (!peticion.signal.aborted) informar(avisoError, "error");
            } finally {
                if (consulta === peticion) {
                    consulta = null;
                    cargando(false);
                }
            }
        }

        function programarBusqueda() {
            cancelarBusqueda();
            temporizador = window.setTimeout(buscar, DEBOUNCE_BUSQUEDA_MS);
        }

        buscador.addEventListener("compositionstart", () => {
            componiendo = true;
            cancelarBusqueda();
        });
        buscador.addEventListener("compositionend", () => {
            componiendo = false;
            programarBusqueda();
        });
        formulario.addEventListener("input", (evento) => {
            if (evento.target !== buscador) cancelarBusqueda();
            else if (!componiendo && !evento.isComposing) programarBusqueda();
        });
        formulario.addEventListener("change", (evento) => {
            if (evento.target !== buscador) cancelarBusqueda();
        });
        formulario.addEventListener("submit", cancelarBusqueda);

        // La respuesta pendiente no debe reemplazar una fila que el usuario acaba de abrir.
        // Si cambia de pestaña durante el debounce de búsqueda, conserva el término vigente.
        formulario.closest(".bandeja").addEventListener("click", (evento) => {
            const enlace = evento.target.closest?.("a[href]");
            if (enlace && !evento.ctrlKey && !evento.metaKey && !evento.shiftKey && !evento.altKey) {
                if (enlace.matches("[data-bandeja-tab]")) {
                    const destinoUrl = new URL(enlace.href, window.location.origin);
                    if (buscador.value.trim()) destinoUrl.searchParams.set("q", buscador.value);
                    else destinoUrl.searchParams.delete("q");
                    destinoUrl.searchParams.delete("page");
                    destinoUrl.searchParams.delete("pagina");
                    enlace.setAttribute("href", `${destinoUrl.pathname}${destinoUrl.search}`);
                }
                cancelarBusqueda();
            }
        });
        window.addEventListener("pagehide", cancelarBusqueda);
    }

    const resultados = document.querySelector("[data-bandeja-resultados]");
    const formulario = document.querySelector("[data-bandeja-filtros]");
    const estado = document.querySelector("[data-bandeja-estado]");

    if (resultados) {
        inicializarVistasRapidas(resultados);
        pantallaAncha.addEventListener("change", () => {
            if (!pantallaAncha.matches) {
                resultados.querySelectorAll(".bandeja-panel[open]").forEach(cerrarPanel);
            }
        });
    }
    if (formulario && resultados && estado) iniciarBusqueda(formulario, resultados, estado);
})();
