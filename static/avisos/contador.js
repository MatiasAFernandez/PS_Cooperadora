(function () {
    const link = document.querySelector("[data-avisos-contador-url]");
    if (!link) return;

    const url = link.getAttribute("data-avisos-contador-url");
    const badge = link.querySelector("[data-avisos-contador]");
    if (!url || !badge || typeof window.fetch !== "function") return;

    function ocultar() {
        badge.hidden = true;
        badge.textContent = "";
        badge.removeAttribute("aria-label");
        badge.className = "";
    }

    fetch(url, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
    })
        .then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            const n = data && data.no_leidos;
            if (!Number.isInteger(n) || n <= 0) {
                ocultar();
                return;
            }
            badge.className = "badge badge-info";
            badge.textContent = String(n);
            badge.setAttribute(
                "aria-label",
                n === 1 ? "1 aviso sin leer" : n + " avisos sin leer"
            );
            badge.hidden = false;
        })
        .catch(function () {
            ocultar();
        });
})();
