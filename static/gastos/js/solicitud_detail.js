(function () {
    'use strict';

    var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

    function esVisible(el) {
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }

    function abrirDetailsAncestros(el) {
        var details = el.closest('details');
        while (details) {
            if (!details.open) {
                details.open = true;
            }
            details = details.parentElement ? details.parentElement.closest('details') : null;
        }
    }

    function objetivoEnfocable(el) {
        if (el.matches(FOCUSABLE)) {
            return el;
        }
        var interno = el.querySelector(FOCUSABLE);
        if (interno && esVisible(interno)) {
            return interno;
        }
        var aviso = el.querySelector('[tabindex="-1"]');
        if (aviso && esVisible(aviso)) {
            return aviso;
        }
        if (el.matches('[tabindex="-1"]')) {
            return el;
        }
        el.setAttribute('tabindex', '-1');
        return el;
    }

    function enfocarYDesplazar(el) {
        if (!el) {
            return;
        }
        var foco = objetivoEnfocable(el);
        try {
            foco.focus({ preventScroll: true });
        } catch (e) {
            if (typeof foco.focus === 'function') {
                foco.focus();
            }
        }
        var reducido = !!(typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        try {
            foco.scrollIntoView({
                block: 'center',
                inline: 'nearest',
                behavior: reducido ? 'auto' : 'smooth'
            });
        } catch (e) {
            if (typeof foco.scrollIntoView === 'function') {
                foco.scrollIntoView();
            }
        }
    }

    function esModificado(evento, link) {
        if (evento.defaultPrevented) {
            return true;
        }
        if (evento.button !== undefined && evento.button !== 0) {
            return true;
        }
        if (evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey) {
            return true;
        }
        if (link && link.target && link.target.toLowerCase() !== '_self') {
            return true;
        }
        return false;
    }

    function abrirPanelRespaldo(raiz, actualizarUrlHash) {
        var panel = raiz.querySelector('details#cargar-respaldo, #cargar-respaldo');
        if (!panel) {
            return;
        }
        abrirDetailsAncestros(panel);
        if (panel.tagName && panel.tagName.toLowerCase() === 'details') {
            panel.open = true;
        } else if (panel.open !== undefined) {
            panel.open = true;
        }

        if (actualizarUrlHash && window.location.hash !== '#cargar-respaldo') {
            if (window.history && window.history.pushState) {
                window.history.pushState(null, '', '#cargar-respaldo');
            } else {
                window.location.hash = '#cargar-respaldo';
            }
        }

        var summary = (panel.querySelector && panel.querySelector('summary[data-respaldo-focus], [data-respaldo-focus]')) ||
                      raiz.querySelector('summary[data-respaldo-focus], [data-respaldo-focus]') ||
                      (panel.querySelector && panel.querySelector('summary')) ||
                      panel;

        enfocarYDesplazar(summary);
    }

    function iniciarInteraccionRespaldo(raiz) {
        raiz.addEventListener('click', function (evento) {
            var link = evento.target.closest ? evento.target.closest('[data-abrir-respaldo]') : null;
            if (!link || !raiz.contains(link)) {
                return;
            }
            var href = link.getAttribute('href') || '';
            if (href !== '#cargar-respaldo' && link.hash !== '#cargar-respaldo') {
                return;
            }
            if (esModificado(evento, link)) {
                return;
            }
            evento.preventDefault();
            abrirPanelRespaldo(raiz, true);
        });

        window.addEventListener('hashchange', function () {
            if (window.location.hash === '#cargar-respaldo') {
                abrirPanelRespaldo(raiz, false);
            }
        });
    }

    function init() {
        var raiz = document.querySelector('.solicitud-detalle');
        if (!raiz) {
            return;
        }
        iniciarInteraccionRespaldo(raiz);
        var cancelarTransferencia = raiz.querySelector('[data-transferencia-cancelar]');
        if (cancelarTransferencia) {
            cancelarTransferencia.addEventListener('click', function () {
                var panel = cancelarTransferencia.closest('details');
                if (!panel) {
                    return;
                }
                panel.open = false;
                var summary = panel.querySelector('summary');
                if (summary) {
                    summary.focus();
                }
            });
        }

        var marcados = raiz.querySelectorAll('[data-detail-decision-error]');
        var destinoDecision = null;
        for (var i = 0; i < marcados.length; i += 1) {
            abrirDetailsAncestros(marcados[i]);
            if (esVisible(marcados[i])) {
                destinoDecision = marcados[i];
                break;
            }
        }

        var erroresRespaldo = raiz.querySelectorAll('[data-respaldo-error]');
        var destinoError = null;
        if (erroresRespaldo.length > 0) {
            var panelRespaldo = raiz.querySelector('details#cargar-respaldo, #cargar-respaldo');
            if (panelRespaldo) {
                abrirDetailsAncestros(panelRespaldo);
                if (panelRespaldo.tagName && panelRespaldo.tagName.toLowerCase() === 'details') {
                    panelRespaldo.open = true;
                } else if (panelRespaldo.open !== undefined) {
                    panelRespaldo.open = true;
                }
            }
            for (var j = 0; j < erroresRespaldo.length; j += 1) {
                abrirDetailsAncestros(erroresRespaldo[j]);
                if (esVisible(erroresRespaldo[j])) {
                    destinoError = erroresRespaldo[j];
                    break;
                }
            }
        }

        var errorTransferencia = raiz.querySelector('[data-transferencia-error]');
        if (errorTransferencia) {
            abrirDetailsAncestros(errorTransferencia);
        }

        if (destinoDecision) {
            enfocarYDesplazar(destinoDecision);
            return;
        }

        if (destinoError) {
            enfocarYDesplazar(destinoError);
            return;
        }

        if (errorTransferencia && esVisible(errorTransferencia)) {
            enfocarYDesplazar(errorTransferencia);
            return;
        }

        if (window.location.hash === '#cargar-respaldo') {
            abrirPanelRespaldo(raiz, false);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
