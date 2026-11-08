/**
 * static/gastos/js/documento_aporte.js
 *
 * Micro-interacción progresiva para carga y reemplazo de respaldo comercial.
 * Contrato de plantilla:
 *   - Wrapper: [data-aporte-upload]
 *   - Input nativo: input[type="file"]
 *   - Zona drag & drop: [data-aporte-drop]
 *   - Tarjeta de archivo seleccionado: [data-aporte-card] (inicia hidden)
 *   - Nombre del archivo: [data-aporte-nombre]
 *   - Tamaño formateado: [data-aporte-tamano]
 *   - Enlace de previsualización local: [data-aporte-abrir]
 *   - Botón cambiar archivo: [data-aporte-cambiar]
 *   - Botón quitar archivo: [data-aporte-quitar]
 *   - Estado y mensajes de error: [data-aporte-estado]
 *   - Botón cancelar inline: [data-aporte-cancelar] (dentro de form)
 */

(function () {
    'use strict';

    var EXTENSIONES_PERMITIDAS = ['pdf', 'jpg', 'jpeg', 'png'];
    var MIMES_PERMITIDOS = ['application/pdf', 'image/jpeg', 'image/pjpeg', 'image/png'];

    /**
     * Formatea el tamaño en bytes a representación legible (B, KB, MB).
     * @param {number} bytes
     * @returns {string}
     */
    function formatearTamano(bytes) {
        if (typeof bytes !== 'number' || isNaN(bytes) || bytes < 0) {
            return '';
        }
        if (bytes === 0) {
            return '0 B';
        }
        var k = 1024;
        var unidades = ['B', 'KB', 'MB', 'GB'];
        var i = Math.floor(Math.log(bytes) / Math.log(k));
        if (i >= unidades.length) {
            i = unidades.length - 1;
        }
        var valor = bytes / Math.pow(k, i);
        var texto = (i === 0) ? valor.toString() : valor.toFixed(1);
        if (texto.slice(-2) === '.0') {
            texto = texto.slice(0, -2);
        }
        return texto + ' ' + unidades[i];
    }

    /**
     * Valida que el archivo corresponda a formatos permitidos (PDF, JPG, PNG).
     * @param {File} archivo
     * @returns {boolean}
     */
    function esArchivoValido(archivo) {
        if (!archivo || !archivo.name) {
            return false;
        }
        var nombre = archivo.name;
        var punto = nombre.lastIndexOf('.');
        if (punto === -1 || punto === nombre.length - 1) {
            return false;
        }
        var extension = nombre.slice(punto + 1).toLowerCase();
        if (EXTENSIONES_PERMITIDAS.indexOf(extension) === -1) {
            return false;
        }
        if (archivo.type) {
            var tipo = archivo.type.toLowerCase();
            if (MIMES_PERMITIDOS.indexOf(tipo) === -1 && tipo !== 'application/octet-stream') {
                return false;
            }
        }
        return true;
    }

    /**
     * Inicializa el comportamiento de un wrapper de carga de respaldo.
     * @param {HTMLElement} wrapper
     */
    function inicializarWrapper(wrapper) {
        if (!wrapper || wrapper.dataset.aporteInicializado === 'true') {
            return;
        }
        wrapper.dataset.aporteInicializado = 'true';

        // Mejora progresiva: solo con JS activo ocultamos el input vía clase CSS
        wrapper.classList.add('is-aporte-enhanced');

        var inputArchivo = wrapper.querySelector('input[type="file"]');
        var dropzone = wrapper.querySelector('[data-aporte-drop]');
        var tarjeta = wrapper.querySelector('[data-aporte-card]');
        var nombreEl = wrapper.querySelector('[data-aporte-nombre]');
        var tamanoEl = wrapper.querySelector('[data-aporte-tamano]');
        var enlaceAbrir = wrapper.querySelector('[data-aporte-abrir]');
        var botonCambiar = wrapper.querySelector('[data-aporte-cambiar]');
        var botonQuitar = wrapper.querySelector('[data-aporte-quitar]');
        var estadoEl = wrapper.querySelector('[data-aporte-estado]');

        var archivoActual = null;
        var objectUrlActual = null;

        if (estadoEl) {
            if (!estadoEl.getAttribute('role')) {
                estadoEl.setAttribute('role', 'status');
            }
            if (!estadoEl.getAttribute('aria-live')) {
                estadoEl.setAttribute('aria-live', 'polite');
            }
        }

        function revocarUrl() {
            if (objectUrlActual) {
                try {
                    URL.revokeObjectURL(objectUrlActual);
                } catch (e) {
                    // Ignorar error al revocar
                }
                objectUrlActual = null;
            }
        }

        function mostrarError(mensaje) {
            if (estadoEl) {
                estadoEl.textContent = mensaje;
                estadoEl.classList.add('is-error');
            }
        }

        function limpiarError() {
            if (estadoEl) {
                estadoEl.textContent = '';
                estadoEl.classList.remove('is-error');
            }
        }

        function sincronizarInput() {
            if (!inputArchivo) {
                return;
            }
            if (archivoActual && window.DataTransfer) {
                try {
                    var dt = new DataTransfer();
                    dt.items.add(archivoActual);
                    inputArchivo.files = dt.files;
                    return;
                } catch (e) {
                    // DataTransfer no disponible o restringido
                }
            }
            if (!archivoActual) {
                try {
                    inputArchivo.value = '';
                } catch (e) {
                    // Ignorar error de asignación
                }
            }
        }

        function enfocarSelectorVisible() {
            if (!dropzone) {
                if (inputArchivo && typeof inputArchivo.focus === 'function') {
                    try {
                        inputArchivo.focus();
                    } catch (e) {}
                }
                return;
            }
            var elementoEnfocable = dropzone.querySelector('button, a[href], input, label, [tabindex="0"]');
            if (elementoEnfocable && typeof elementoEnfocable.focus === 'function') {
                try {
                    elementoEnfocable.focus();
                    return;
                } catch (e) {}
            }
            if (dropzone.getAttribute('tabindex') === null) {
                dropzone.setAttribute('tabindex', '-1');
            }
            try {
                dropzone.focus();
            } catch (e) {}
        }

        function presentarArchivo(archivo) {
            revocarUrl();
            archivoActual = archivo;

            if (window.URL && typeof window.URL.createObjectURL === 'function') {
                try {
                    objectUrlActual = URL.createObjectURL(archivo);
                } catch (e) {
                    objectUrlActual = null;
                }
            }

            if (nombreEl) {
                nombreEl.textContent = archivo.name || '';
            }

            if (tamanoEl) {
                tamanoEl.textContent = formatearTamano(archivo.size);
            }

            if (enlaceAbrir) {
                if (objectUrlActual) {
                    enlaceAbrir.setAttribute('href', objectUrlActual);
                    enlaceAbrir.setAttribute('target', '_blank');
                    enlaceAbrir.setAttribute('rel', 'noopener noreferrer');
                } else {
                    enlaceAbrir.removeAttribute('href');
                }
            }

            if (tarjeta) {
                tarjeta.hidden = false;
                tarjeta.removeAttribute('hidden');
                tarjeta.style.display = '';
            }

            if (dropzone) {
                dropzone.hidden = true;
                dropzone.setAttribute('hidden', '');
                dropzone.style.display = 'none';
            }

            limpiarError();
        }

        function procesarSeleccion(nuevoArchivo) {
            if (!nuevoArchivo) {
                // Cancelación del diálogo nativo: si ya había un archivo previo, conservarlo
                if (archivoActual) {
                    sincronizarInput();
                }
                return;
            }

            if (!esArchivoValido(nuevoArchivo)) {
                // Validación fallida: error claro sin perder la selección previa válida
                mostrarError('Formato no válido. Se admiten únicamente archivos PDF, JPG o PNG.');
                sincronizarInput();
                return;
            }

            // Si vino por drag-drop y el input no lo tiene sincronizado aún
            if (inputArchivo && inputArchivo.files && inputArchivo.files[0] !== nuevoArchivo && window.DataTransfer) {
                try {
                    var dt = new DataTransfer();
                    dt.items.add(nuevoArchivo);
                    inputArchivo.files = dt.files;
                } catch (e) {}
            }

            presentarArchivo(nuevoArchivo);
        }

        function quitarArchivo() {
            revocarUrl();
            archivoActual = null;

            if (inputArchivo) {
                try {
                    inputArchivo.value = '';
                } catch (e) {}
            }

            if (enlaceAbrir) {
                enlaceAbrir.removeAttribute('href');
            }

            if (nombreEl) {
                nombreEl.textContent = '';
            }

            if (tamanoEl) {
                tamanoEl.textContent = '';
            }

            if (tarjeta) {
                tarjeta.hidden = true;
                tarjeta.setAttribute('hidden', '');
                tarjeta.style.display = 'none';
            }

            if (dropzone) {
                dropzone.hidden = false;
                dropzone.removeAttribute('hidden');
                dropzone.style.display = '';
            }

            limpiarError();
            enfocarSelectorVisible();
        }

        // Eventos en input file
        if (inputArchivo) {
            inputArchivo.addEventListener('change', function () {
                var files = inputArchivo.files;
                if (files && files.length > 0) {
                    procesarSeleccion(files[0]);
                } else {
                    procesarSeleccion(null);
                }
            });
        }

        // Botón cambiar
        if (botonCambiar) {
            botonCambiar.addEventListener('click', function (e) {
                e.preventDefault();
                if (inputArchivo) {
                    inputArchivo.click();
                }
            });
        }

        // Botón quitar
        if (botonQuitar) {
            botonQuitar.addEventListener('click', function (e) {
                e.preventDefault();
                quitarArchivo();
            });
        }

        // Zona Drag and Drop
        if (dropzone) {
            var dragDepth = 0;

            dropzone.addEventListener('dragenter', function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragDepth += 1;
                dropzone.classList.add('is-dragover');
            });

            dropzone.addEventListener('dragover', function (e) {
                e.preventDefault();
                e.stopPropagation();
                if (e.dataTransfer) {
                    e.dataTransfer.dropEffect = 'copy';
                }
                dropzone.classList.add('is-dragover');
            });

            dropzone.addEventListener('dragleave', function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragDepth -= 1;
                if (dragDepth <= 0) {
                    dragDepth = 0;
                    dropzone.classList.remove('is-dragover');
                }
            });

            dropzone.addEventListener('drop', function (e) {
                e.preventDefault();
                e.stopPropagation();
                dragDepth = 0;
                dropzone.classList.remove('is-dragover');

                var files = e.dataTransfer ? e.dataTransfer.files : null;
                if (files && files.length > 0) {
                    procesarSeleccion(files[0]);
                }
            });

            // Clic directo sobre la zona (si no fue sobre botón o label existente)
            dropzone.addEventListener('click', function (e) {
                if (e.target.closest('label, button, a, input')) {
                    return;
                }
                if (inputArchivo) {
                    inputArchivo.click();
                }
            });

            // Accesibilidad de teclado sobre la zona
            dropzone.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    if (e.target.closest('button, a, input')) {
                        return;
                    }
                    e.preventDefault();
                    if (inputArchivo) {
                        inputArchivo.click();
                    }
                }
            });
        }

        // Estado inicial si el navegador preservó archivos seleccionados
        if (inputArchivo && inputArchivo.files && inputArchivo.files.length > 0) {
            procesarSeleccion(inputArchivo.files[0]);
        } else {
            if (tarjeta) {
                tarjeta.hidden = true;
                tarjeta.setAttribute('hidden', '');
                tarjeta.style.display = 'none';
            }
            if (dropzone) {
                dropzone.hidden = false;
                dropzone.removeAttribute('hidden');
                dropzone.style.display = '';
            }
        }

        // Limpieza de memoria ante descarga de la página
        window.addEventListener('pagehide', revocarUrl);
        window.addEventListener('beforeunload', revocarUrl);
    }

    /**
     * Vincula el comportamiento del botón cancelar inline:
     * Cierra el details#cargar-respaldo y enfoca el summary sin tocar valores del formulario.
     */
    function inicializarCancelarInline(raiz) {
        var contenedor = raiz || document;
        var botonesCancelar = contenedor.querySelectorAll('[data-aporte-cancelar]');
        for (var i = 0; i < botonesCancelar.length; i += 1) {
            (function (btn) {
                if (btn.dataset.cancelarInicializado === 'true') {
                    return;
                }
                btn.dataset.cancelarInicializado = 'true';

                btn.addEventListener('click', function (e) {
                    e.preventDefault();
                    var panel = document.getElementById('cargar-respaldo') || btn.closest('details');
                    if (!panel) {
                        return;
                    }
                    panel.open = false;
                    var summary = panel.querySelector('summary');
                    if (summary && typeof summary.focus === 'function') {
                        try {
                            summary.focus();
                        } catch (err) {}
                    }
                });
            }(botonesCancelar[i]));
        }
    }

    function init() {
        var wrappers = document.querySelectorAll('[data-aporte-upload]');
        for (var i = 0; i < wrappers.length; i += 1) {
            inicializarWrapper(wrappers[i]);
        }
        inicializarCancelarInline(document);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
