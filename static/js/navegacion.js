/* Menú lateral: pliegue a riel (>=1280px), superposición modal (<1280px),
   tooltips modernos sin doble title nativo y cierre progresivo del popover de cuenta. */
(function () {
    "use strict";

    var root = document.documentElement;
    var nav = document.getElementById("app-nav");
    if (!nav) { return; }

    var brandLink = document.getElementById("app-brand-link");
    var menuBtn = document.getElementById("app-menu-btn");
    var toggle = document.getElementById("app-nav-toggle");
    var toggleSvg = document.getElementById("app-nav-toggle-svg");
    var toggleTip = document.getElementById("app-nav-toggle-tip");
    var scrim = document.getElementById("app-nav-scrim");
    var accountMenu = document.getElementById("app-account-menu");
    var header = document.querySelector(".app-topbar");
    var content = document.querySelector(".app-content");
    var wide = window.matchMedia("(min-width: 1280px)");
    var ICON_MARKUP = {
        close: '<path d="M18 6 6 18M6 6l12 12"/>',
        fold: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>',
        unfold: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>'
    };
    var overlayOpen = false;
    var opener = null;

    // Suprimir tooltips nativos del navegador cuando los tooltips CSS modernos están activos.
    nav.querySelectorAll(".app-nav-body a[title]").forEach(function (link) {
        link.setAttribute("data-tooltip", link.getAttribute("title"));
        link.removeAttribute("title");
    });

    function isRail() { return root.getAttribute("data-nav-rail") === "true"; }

    function drawerOpen() {
        // La vista rápida derecha de Gastos y el menú no se abren a la vez.
        return !!document.querySelector('dialog.bandeja-panel[open]');
    }

    function setToggleLabel(label, iconKey) {
        toggle.setAttribute("aria-label", label);
        if (toggleTip) { toggleTip.textContent = label; }
        if (toggleSvg) { toggleSvg.innerHTML = ICON_MARKUP[iconKey]; }
    }

    function syncToggle() {
        var inRail = wide.matches && isRail();
        if (!wide.matches) {
            setToggleLabel("Cerrar menú", "close");
            toggle.removeAttribute("aria-expanded");
        } else if (inRail) {
            setToggleLabel("Desplegar menú", "unfold");
            toggle.setAttribute("aria-expanded", "false");
        } else {
            setToggleLabel("Plegar menú", "fold");
            toggle.setAttribute("aria-expanded", "true");
        }

        // En riel colapsado el único objetivo interactivo de la cabecera es el botón expandir.
        if (brandLink) {
            if (inRail) {
                brandLink.setAttribute("tabindex", "-1");
                brandLink.setAttribute("aria-hidden", "true");
            } else {
                brandLink.removeAttribute("tabindex");
                brandLink.removeAttribute("aria-hidden");
            }
        }
    }

    function setInert(on) {
        [header, content].forEach(function (el) { if (el) { el.inert = on; } });
    }

    function focusables() {
        return Array.prototype.slice.call(nav.querySelectorAll("a[href], button:not([disabled]), summary"))
            .filter(function (el) { return el.offsetParent !== null || el === document.activeElement; });
    }

    function closeAccountMenu(restoreFocus) {
        if (!accountMenu || !accountMenu.open) { return; }
        accountMenu.open = false;
        if (restoreFocus) {
            var summary = accountMenu.querySelector("summary");
            if (summary) { summary.focus(); }
        }
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
        document.addEventListener("keydown", onOverlayKeydown);
    }

    function closeOverlay(restoreFocus) {
        if (!overlayOpen) { return; }
        closeAccountMenu(false);
        overlayOpen = false;
        root.removeAttribute("data-nav-open");
        scrim.hidden = true;
        nav.removeAttribute("role");
        nav.removeAttribute("aria-modal");
        setInert(false);
        if (menuBtn) { menuBtn.setAttribute("aria-expanded", "false"); }
        document.removeEventListener("keydown", onOverlayKeydown);
        if (restoreFocus && opener && document.body.contains(opener)) { opener.focus(); }
        opener = null;
    }

    function onOverlayKeydown(event) {
        if (event.key === "Escape") {
            event.preventDefault();
            if (accountMenu && accountMenu.open) {
                closeAccountMenu(true);
                return;
            }
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
        closeAccountMenu(false);
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

    // Mejora progresiva para <details> de cuenta: click fuera y Escape en escritorio.
    if (accountMenu) {
        document.addEventListener("click", function (event) {
            if (accountMenu.open && !accountMenu.contains(event.target)) {
                accountMenu.open = false;
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && accountMenu.open && !overlayOpen) {
                event.preventDefault();
                closeAccountMenu(true);
            }
        });
    }

    // Selector de tema (Claro / Oscuro / Sistema) persistido en localStorage.
    var themeBtns = nav.querySelectorAll("[data-theme-choice]");
    function readThemePref() {
        try {
            var saved = localStorage.getItem("theme");
            if (saved === "light" || saved === "dark" || saved === "system") { return saved; }
        } catch (e) { /* almacenamiento no disponible */ }
        return "system";
    }
    function applyTheme(pref) {
        if (pref === "light" || pref === "dark") {
            root.setAttribute("data-theme", pref);
        } else {
            root.removeAttribute("data-theme");
            pref = "system";
        }
        try { localStorage.setItem("theme", pref); } catch (e) { /* almacenamiento no disponible */ }
        themeBtns.forEach(function (btn) {
            btn.setAttribute("aria-pressed", btn.getAttribute("data-theme-choice") === pref ? "true" : "false");
        });
    }
    if (themeBtns.length) {
        applyTheme(readThemePref());
        themeBtns.forEach(function (btn) {
            btn.addEventListener("click", function () {
                applyTheme(btn.getAttribute("data-theme-choice") || "system");
            });
        });
    }

    var onModeChange = function () {
        if (wide.matches) { closeOverlay(false); }
        syncToggle();
    };
    if (wide.addEventListener) { wide.addEventListener("change", onModeChange); } else { wide.addListener(onModeChange); }

    syncToggle();
})();
