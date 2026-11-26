/* Botón «Copiar» compartido (.btn-copy[data-copy]) con fallback HTTP LAN y anuncio accesible. */
(function () {
    "use strict";

    if (document.documentElement.dataset.psCopyInit === "1") {
        return;
    }
    document.documentElement.dataset.psCopyInit = "1";

    function anunciar(texto) {
        var region = document.querySelector("[data-ps-copy-status]");
        if (!region) {
            region = document.createElement("span");
            region.setAttribute("data-ps-copy-status", "");
            region.setAttribute("role", "status");
            region.setAttribute("aria-live", "polite");
            region.style.cssText =
                "position:absolute;width:1px;height:1px;overflow:hidden;" +
                "clip:rect(0 0 0 0);white-space:nowrap;";
            document.body.appendChild(region);
        }
        region.textContent = "";
        window.setTimeout(function () {
            region.textContent = texto;
        }, 30);
    }

    function copiarFallback(valor) {
        var area = document.createElement("textarea");
        area.value = valor;
        area.setAttribute("readonly", "");
        area.style.cssText = "position:fixed;top:0;left:0;opacity:0;";
        document.body.appendChild(area);
        area.select();
        var ok = false;
        try {
            ok = document.execCommand("copy");
        } catch (e) {
            ok = false;
        }
        document.body.removeChild(area);
        return ok;
    }

    function copiarTexto(valor) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(valor).then(
                function () {
                    return true;
                },
                function () {
                    return copiarFallback(valor);
                }
            );
        }
        return Promise.resolve(copiarFallback(valor));
    }

    document.addEventListener("click", function (evento) {
        var boton = evento.target.closest
            ? evento.target.closest("[data-copy], [data-detail-copy]")
            : null;
        if (!boton) {
            return;
        }
        var valor =
            boton.getAttribute("data-copy") ||
            boton.getAttribute("data-detail-copy") ||
            "";
        if (!valor) {
            return;
        }
        copiarTexto(valor).then(function (ok) {
            if (!ok) {
                return;
            }
            boton.classList.add("copied");
            boton.setAttribute("data-copied", "true");
            var textoEl = boton.querySelector(".btn-copy-text");
            if (textoEl) {
                if (!boton.dataset.copyLabelOriginal) {
                    boton.dataset.copyLabelOriginal = textoEl.textContent || "Copiar";
                }
                textoEl.textContent = "Copiado";
            }
            anunciar("Copiado al portapapeles");
            window.clearTimeout(boton._copiadoTimer);
            boton._copiadoTimer = window.setTimeout(function () {
                boton.classList.remove("copied");
                boton.removeAttribute("data-copied");
                if (textoEl && boton.dataset.copyLabelOriginal) {
                    textoEl.textContent = boton.dataset.copyLabelOriginal;
                }
            }, 2000);
        });
    });
}());
