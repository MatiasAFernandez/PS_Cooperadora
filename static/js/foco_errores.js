/* Enfoque progresivo en resumen superior de errores tras fallo de POST. */
(function () {
    "use strict";

    function enfocarError() {
        var resumen = document.querySelector("[data-auto-focus-error]");
        if (!resumen) {
            return;
        }
        try {
            resumen.focus({ preventScroll: true });
        } catch (e) {
            if (typeof resumen.focus === "function") {
                resumen.focus();
            }
        }
        var reducido = !!(
            typeof window.matchMedia === "function" &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches
        );
        try {
            resumen.scrollIntoView({
                block: "center",
                inline: "nearest",
                behavior: reducido ? "auto" : "smooth",
            });
        } catch (e) {
            if (typeof resumen.scrollIntoView === "function") {
                resumen.scrollIntoView();
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", enfocarError);
    } else {
        enfocarError();
    }
}());
