/* Menú lateral: pliegue a riel (>=1440px) y superposición modal (<1440px). JS nativo, sin dependencias. */
(function () {
    "use strict";

    var root = document.documentElement;
    var nav = document.getElementById("app-nav");
    if (!nav) { return; }

    var menuBtn = document.getElementById("app-menu-btn");
    var toggle = document.getElementById("app-nav-toggle");
    var icon = document.getElementById("app-nav-toggle-icon");
    var scrim = document.getElementById("app-nav-scrim");
    var header = document.querySelector(".app-topbar");
    var content = document.querySelector(".app-content");
    var wide = window.matchMedia("(min-width: 1440px)");
    var ICONS = {
        close: "M18 6L6 18M6 6l12 12",
        fold: "M11 17l-5-5 5-5M18 17l-5-5 5-5",
        unfold: "M6 17l5-5-5-5M13 17l5-5-5-5"
    };
    var overlayOpen = false;
    var opener = null;

    function isRail() { return root.getAttribute("data-nav-rail") === "true"; }

    function drawerOpen() {
        // La vista rápida derecha de Gastos y el menú no se abren a la vez.
        return !!document.querySelector('dialog.bandeja-panel[open]');
    }

    function setToggleLabel(label, iconKey) {
        toggle.setAttribute("aria-label", label);
        toggle.setAttribute("title", label);
        icon.setAttribute("d", ICONS[iconKey]);
    }

    function syncToggle() {
        if (!wide.matches) {
            setToggleLabel("Cerrar menú", "close");
            toggle.removeAttribute("aria-expanded");
        } else if (isRail()) {
            setToggleLabel("Desplegar menú", "unfold");
            toggle.setAttribute("aria-expanded", "false");
        } else {
            setToggleLabel("Plegar menú", "fold");
            toggle.setAttribute("aria-expanded", "true");
        }
    }

    function setInert(on) {
        [header, content].forEach(function (el) { if (el) { el.inert = on; } });
    }

    function focusables() {
        return Array.prototype.slice.call(nav.querySelectorAll("a[href], button:not([disabled])"))
            .filter(function (el) { return el.offsetParent !== null || el === document.activeElement; });
    }

    function openOverlay() {
        if (overlayOpen || wide.matches || drawerOpen()) { return; }
        overlayOpen = true;
        opener = menuBtn;
        root.setAttribute("data-nav-open", "true");
        scrim.hidden = false;
        nav.setAttribute("role", "dialog");
        nav.setAttribute("aria-modal", "true");
        setInert(true);
        if (menuBtn) { menuBtn.setAttribute("aria-expanded", "true"); }
        var target = nav.querySelector('a[aria-current="page"]') || toggle;
        target.focus();
        document.addEventListener("keydown", onKeydown);
    }

    function closeOverlay(restoreFocus) {
        if (!overlayOpen) { return; }
        overlayOpen = false;
        root.removeAttribute("data-nav-open");
        scrim.hidden = true;
        nav.removeAttribute("role");
        nav.removeAttribute("aria-modal");
        setInert(false);
        if (menuBtn) { menuBtn.setAttribute("aria-expanded", "false"); }
        document.removeEventListener("keydown", onKeydown);
        if (restoreFocus && opener && document.body.contains(opener)) { opener.focus(); }
        opener = null;
    }

    function onKeydown(event) {
        if (event.key === "Escape") {
            event.preventDefault();
            closeOverlay(true);
            return;
        }
        if (event.key !== "Tab") { return; }
        var items = focusables();
        if (!items.length) { return; }
        var first = items[0];
        var last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function setRail(on) {
        if (on) { root.setAttribute("data-nav-rail", "true"); } else { root.removeAttribute("data-nav-rail"); }
        try { localStorage.setItem("navRail", on ? "1" : "0"); } catch (e) { /* almacenamiento no disponible */ }
        syncToggle();
    }

    if (menuBtn) {
        menuBtn.addEventListener("click", function () {
            if (overlayOpen) { closeOverlay(true); } else { openOverlay(); }
        });
    }
    toggle.addEventListener("click", function () {
        if (wide.matches) { setRail(!isRail()); } else { closeOverlay(true); }
    });
    scrim.addEventListener("click", function () { closeOverlay(true); });

    var onModeChange = function () {
        if (wide.matches) { closeOverlay(false); }
        syncToggle();
    };
    if (wide.addEventListener) { wide.addEventListener("change", onModeChange); } else { wide.addListener(onModeChange); }

    syncToggle();
})();
