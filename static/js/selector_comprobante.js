(function () {
    "use strict";

    function formatearTamano(bytes) {
        if (!Number.isFinite(bytes) || bytes <= 0) {
            return "tamaño no informado";
        }
        if (bytes >= 1024 * 1024) {
            return (bytes / (1024 * 1024)).toFixed(1) + " MiB";
        }
        return Math.max(1, Math.ceil(bytes / 1024)) + " KB";
    }

    function mismoArchivo(a, b) {
        if (!a || !b) {
            return false;
        }
        return (
            a === b ||
            (a.name === b.name && a.size === b.size && a.lastModified === b.lastModified)
        );
    }

    async function validarArchivo(file, formatos, maxBytes) {
        if (!file) {
            return formatos === "pdf"
                ? "Seleccioná un archivo PDF."
                : "Seleccioná un comprobante (PDF o imagen).";
        }
        if (file.size === 0) {
            return "El archivo está vacío.";
        }
        if (file.size > maxBytes) {
            const maxMib = Math.max(1, Math.round(maxBytes / (1024 * 1024)));
            return "El archivo supera el máximo de " + maxMib + " MiB.";
        }

        const nombre = (file.name || "").toLowerCase();
        const esPdf = nombre.endsWith(".pdf");
        const esJpg = nombre.endsWith(".jpg") || nombre.endsWith(".jpeg");
        const esPng = nombre.endsWith(".png");

        if (formatos === "pdf") {
            if (!esPdf) {
                return "El archivo debe tener extensión .pdf.";
            }
        } else if (!esPdf && !esJpg && !esPng) {
            return "El comprobante debe ser un archivo PDF, JPG o PNG.";
        }

        try {
            const buffer = await file.slice(0, 8).arrayBuffer();
            const bytes = new Uint8Array(buffer);
            if (esPdf) {
                if (bytes.length < 5 || String.fromCharCode.apply(null, bytes.slice(0, 5)) !== "%PDF-") {
                    return "El contenido no corresponde a un PDF válido.";
                }
            } else if (esJpg) {
                if (bytes.length < 3 || bytes[0] !== 0xff || bytes[1] !== 0xd8 || bytes[2] !== 0xff) {
                    return "El contenido no corresponde a una imagen JPEG válida.";
                }
            } else if (esPng) {
                const firmaPng = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
                if (bytes.length < 8) {
                    return "El contenido no corresponde a una imagen PNG válida.";
                }
                for (let i = 0; i < firmaPng.length; i += 1) {
                    if (bytes[i] !== firmaPng[i]) {
                        return "El contenido no corresponde a una imagen PNG válida.";
                    }
                }
            }
        } catch (err) {
            return "No se pudo leer el archivo elegido.";
        }

        return null;
    }

    function asignarArchivoAlInput(input, file) {
        if (!input || typeof window.DataTransfer !== "function") {
            return false;
        }
        try {
            const dt = new window.DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            return Boolean(input.files && input.files.length === 1 && mismoArchivo(input.files[0], file));
        } catch (err) {
            return false;
        }
    }

    function iniciarSelector(root) {
        if (!root || root.dataset.scInit === "1") {
            return;
        }
        root.dataset.scInit = "1";

        const dropEl = root.querySelector("[data-sc-drop]");
        const input = dropEl ? dropEl.querySelector('input[type="file"]') : null;
        const triggerEl = root.querySelector("[data-sc-trigger]");
        const cardEl = root.querySelector("[data-sc-card]");
        const nombreEl = root.querySelector("[data-sc-nombre]");
        const metaEl = root.querySelector("[data-sc-meta]");
        const btnVer = root.querySelector("[data-sc-ver]");
        const linkDescargar = root.querySelector("[data-sc-descargar]");
        const btnCambiar = root.querySelector("[data-sc-cambiar]");
        const btnQuitar = root.querySelector("[data-sc-quitar]");
        const statusEl = root.querySelector("[data-sc-status]");
        const avisoPerdidaEl = root.querySelector("[data-sc-aviso-perdida]");

        if (!dropEl || !input || !cardEl) {
            return;
        }

        const maxBytes = Number(root.dataset.maxBytes || 10 * 1024 * 1024);
        const formatos = (root.dataset.formatos || "pdf-imagen").trim().toLowerCase();
        const tituloVisor = root.dataset.tituloVisor || "Comprobante";

        const estado = {
            file: null,
            objectUrl: "",
        };
        let opSeq = 0;

        function revocarUrl() {
            if (estado.objectUrl) {
                window.URL.revokeObjectURL(estado.objectUrl);
                estado.objectUrl = "";
            }
        }

        function setError(texto) {
            if (!statusEl) {
                return;
            }
            if (!texto) {
                clearError();
                return;
            }
            statusEl.hidden = false;
            statusEl.textContent = texto;
            statusEl.setAttribute("role", "alert");
            statusEl.classList.add("sc-error", "rp-error");
        }

        function clearError() {
            if (!statusEl) {
                return;
            }
            statusEl.hidden = true;
            statusEl.textContent = "";
            statusEl.setAttribute("role", "status");
            statusEl.classList.remove("sc-error", "rp-error");
        }

        function focusControl() {
            const destino = estado.file && btnCambiar && !cardEl.hidden ? btnCambiar : triggerEl;
            if (!destino || typeof destino.focus !== "function") {
                return;
            }
            try {
                destino.focus({ preventScroll: true });
            } catch (err) {
                destino.focus();
            }
        }

        function despacharCambio(valid, error) {
            root.dispatchEvent(
                new CustomEvent("selector-comprobante:change", {
                    bubbles: true,
                    detail: {
                        file: estado.file,
                        valid: Boolean(valid),
                        error: error || "",
                    },
                })
            );
        }

        function renderEstado() {
            if (estado.file) {
                dropEl.hidden = true;
                cardEl.hidden = false;
                if (nombreEl) {
                    nombreEl.textContent = estado.file.name;
                }
                if (metaEl) {
                    metaEl.textContent = formatearTamano(estado.file.size);
                }
                if (linkDescargar) {
                    linkDescargar.href = estado.objectUrl || "#";
                    linkDescargar.download = estado.file.name;
                    linkDescargar.hidden = !estado.objectUrl;
                }
                if (btnVer) {
                    btnVer.hidden = false;
                }
                if (avisoPerdidaEl) {
                    avisoPerdidaEl.hidden = true;
                }
            } else {
                dropEl.hidden = false;
                cardEl.hidden = true;
                if (nombreEl) {
                    nombreEl.textContent = "";
                }
                if (metaEl) {
                    metaEl.textContent = "";
                }
                if (linkDescargar) {
                    linkDescargar.href = "#";
                    linkDescargar.setAttribute("download", "");
                }
            }
        }

        async function manejarArchivo(file, opciones) {
            const opts = opciones || {};
            const actualOp = ++opSeq;
            const prevFile = estado.file;
            const problema = await validarArchivo(file, formatos, maxBytes);
            if (actualOp !== opSeq) {
                return;
            }

            if (problema) {
                let conservado = false;
                if (prevFile) {
                    if (opts.desdeDrop && input.files && input.files.length === 1 && mismoArchivo(input.files[0], prevFile)) {
                        conservado = true;
                    } else {
                        conservado = asignarArchivoAlInput(input, prevFile);
                    }
                }
                if (conservado) {
                    estado.file = prevFile;
                } else {
                    revocarUrl();
                    estado.file = null;
                    input.value = "";
                }
                renderEstado();
                setError(problema);
                focusControl();
                despacharCambio(Boolean(estado.file), problema);
                return;
            }

            if (opts.desdeDrop) {
                const asignado = asignarArchivoAlInput(input, file);
                if (!asignado) {
                    revocarUrl();
                    estado.file = null;
                    input.value = "";
                    renderEstado();
                    const msg = "Usá el botón «Seleccionar archivo» para adjuntar el comprobante.";
                    setError(msg);
                    focusControl();
                    despacharCambio(false, msg);
                    return;
                }
            }

            revocarUrl();
            estado.file = file;
            estado.objectUrl = window.URL.createObjectURL(file);
            clearError();
            renderEstado();
            despacharCambio(true, "");
        }

        function quitarSeleccion() {
            opSeq += 1;
            revocarUrl();
            estado.file = null;
            input.value = "";
            clearError();
            renderEstado();
            focusControl();
            despacharCambio(false, "");
        }

        input.addEventListener("change", (evento) => {
            const file = evento.target.files && evento.target.files[0];
            if (!file) {
                if (estado.file) {
                    const conservado = asignarArchivoAlInput(input, estado.file);
                    if (!conservado) {
                        quitarSeleccion();
                    }
                }
                return;
            }
            manejarArchivo(file, { desdeDrop: false });
        });

        ["dragenter", "dragover"].forEach((tipo) => {
            dropEl.addEventListener(tipo, (evento) => {
                if (!evento.dataTransfer || !evento.dataTransfer.types || !Array.from(evento.dataTransfer.types).includes("Files")) {
                    return;
                }
                evento.preventDefault();
                dropEl.classList.add("is-over");
            });
        });

        ["dragleave", "dragend"].forEach((tipo) => {
            dropEl.addEventListener(tipo, (evento) => {
                if (!dropEl.contains(evento.relatedTarget)) {
                    dropEl.classList.remove("is-over");
                }
            });
        });

        dropEl.addEventListener("drop", (evento) => {
            evento.preventDefault();
            dropEl.classList.remove("is-over");
            const files = evento.dataTransfer && evento.dataTransfer.files;
            if (!files || files.length !== 1) {
                const msg = "Elegí un único archivo.";
                setError(msg);
                focusControl();
                despacharCambio(Boolean(estado.file), msg);
                return;
            }
            manejarArchivo(files[0], { desdeDrop: true });
        });

        dropEl.addEventListener("click", (evento) => {
            if (evento.target.closest("label, button, a, input")) {
                return;
            }
            input.click();
        });

        if (triggerEl) {
            triggerEl.addEventListener("keydown", (evento) => {
                if (evento.key === "Enter" || evento.key === " ") {
                    evento.preventDefault();
                    input.click();
                }
            });
        }

        if (btnCambiar) {
            btnCambiar.addEventListener("click", () => {
                input.click();
            });
        }

        if (btnQuitar) {
            btnQuitar.addEventListener("click", () => {
                quitarSeleccion();
            });
        }

        if (btnVer) {
            btnVer.addEventListener("click", () => {
                if (!estado.file) {
                    return;
                }
                if (
                    window.PSVisorDocumentos &&
                    typeof window.PSVisorDocumentos.abrirArchivoLocal === "function"
                ) {
                    window.PSVisorDocumentos.abrirArchivoLocal({
                        file: estado.file,
                        titulo: tituloVisor,
                        nombre: estado.file.name,
                        formatos: formatos,
                        descargarLabel: "Descargar " + estado.file.name,
                        disparador: btnVer,
                    });
                    return;
                }
                if (estado.objectUrl) {
                    window.open(estado.objectUrl, "_blank", "noopener");
                }
            });
        }

        root._selectorComprobante = {
            getFile: () => estado.file,
            setError,
            clearError,
            focusControl,
        };

        window.addEventListener("pagehide", () => {
            revocarUrl();
        });

        renderEstado();
    }

    function iniciarTodos() {
        document.querySelectorAll("[data-selector-comprobante]").forEach(iniciarSelector);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciarTodos);
    } else {
        iniciarTodos();
    }
})();
