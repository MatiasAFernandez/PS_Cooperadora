/**
 * static/gastos/js/solicitud_respaldo.js
 *
 * Sincroniza el texto de tipo de respaldo según la modalidad de gasto en el alta
 * y, si cambia la modalidad con un archivo seleccionado, lo quita mediante el
 * control existente de documento_aporte.js y anuncia la reselección requerida.
 */

(function () {
    'use strict';

    var TEXTOS_MODALIDAD = {
        COMPRA_DIRECTA: 'Presupuesto o proforma',
        REINTEGRO: 'Factura o ticket factura'
    };

    function textoPorModalidad(valor) {
        return valor === 'REINTEGRO' ? TEXTOS_MODALIDAD.REINTEGRO : TEXTOS_MODALIDAD.COMPRA_DIRECTA;
    }

    function tieneArchivoSeleccionado(wrapper) {
        if (!wrapper) {
            return false;
        }
        var inputArchivo = wrapper.querySelector('input[type="file"]');
        if (inputArchivo) {
            if (inputArchivo.files && inputArchivo.files.length > 0) {
                return true;
            }
            if (inputArchivo.value) {
                return true;
            }
        }
        var tarjeta = wrapper.querySelector('[data-aporte-card]');
        return Boolean(tarjeta && !tarjeta.hidden);
    }

    function init() {
        var panel = document.querySelector('[data-respaldo-details]');
        var selectModalidad = document.querySelector('#id_tipo_flujo, select[name="tipo_flujo"]');
        if (!panel || !selectModalidad) {
            return;
        }

        var noJsEls = panel.querySelectorAll('[data-respaldo-nojs]');
        for (var i = 0; i < noJsEls.length; i += 1) {
            noJsEls[i].hidden = true;
            noJsEls[i].setAttribute('hidden', '');
        }

        var tipoEls = panel.querySelectorAll('[data-respaldo-tipo], [data-respaldo-texto]');
        var wrapper = panel.querySelector('[data-aporte-upload]');
        var botonQuitar = wrapper ? wrapper.querySelector('[data-aporte-quitar]') : null;
        var estadoEl = wrapper ? wrapper.querySelector('[data-aporte-estado]') : null;
        var inputArchivo = wrapper ? wrapper.querySelector('input[type="file"]') : null;

        function actualizarTexto(modalidad) {
            var texto = textoPorModalidad(modalidad);
            for (var j = 0; j < tipoEls.length; j += 1) {
                tipoEls[j].textContent = texto;
            }
            return texto;
        }

        function sincronizarVisibilidadEstado() {
            if (!estadoEl) {
                return;
            }
            if (estadoEl.textContent && estadoEl.textContent.trim() !== '') {
                estadoEl.hidden = false;
                estadoEl.removeAttribute('hidden');
            } else {
                estadoEl.hidden = true;
                estadoEl.setAttribute('hidden', '');
            }
        }

        var modalidadActual = selectModalidad.value || 'COMPRA_DIRECTA';
        actualizarTexto(modalidadActual);

        selectModalidad.addEventListener('change', function () {
            var nuevaModalidad = selectModalidad.value || 'COMPRA_DIRECTA';
            var cambioModalidad = nuevaModalidad !== modalidadActual;
            modalidadActual = nuevaModalidad;
            var textoRequerido = actualizarTexto(nuevaModalidad);

            if (cambioModalidad && tieneArchivoSeleccionado(wrapper)) {
                if (botonQuitar) {
                    botonQuitar.click();
                }
                panel.open = true;
                if (estadoEl) {
                    estadoEl.textContent = 'Cambiaste la modalidad. Seleccioná un archivo acorde (' + textoRequerido + ').';
                    estadoEl.classList.add('is-error');
                    estadoEl.hidden = false;
                    estadoEl.removeAttribute('hidden');
                }
            }
        });

        if (inputArchivo) {
            inputArchivo.addEventListener('change', sincronizarVisibilidadEstado);
        }
        if (wrapper) {
            wrapper.addEventListener('drop', sincronizarVisibilidadEstado);
        }
        if (botonQuitar) {
            botonQuitar.addEventListener('click', sincronizarVisibilidadEstado);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
