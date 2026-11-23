(function () {
    'use strict';

    var IMAGENES_PERMITIDAS = {
        'image/jpeg': 'image/jpeg',
        'image/jpg': 'image/jpeg',
        'image/png': 'image/png'
    };

    function mimePermitido(formatos, contentType) {
        if (!contentType) {
            return '';
        }
        var base = contentType.split(';')[0].trim().toLowerCase();
        if (base === 'application/pdf') {
            return 'application/pdf';
        }
        if (formatos === 'pdf-imagen' && Object.prototype.hasOwnProperty.call(IMAGENES_PERMITIDAS, base)) {
            return IMAGENES_PERMITIDAS[base];
        }
        return '';
    }

    function urlMismoOrigen(rawUrl) {
        if (!rawUrl) {
            return '';
        }
        try {
            var parsed = new URL(rawUrl, window.location.href);
            if (parsed.origin !== window.location.origin) {
                return '';
            }
            return parsed.href;
        } catch (e) {
            return '';
        }
    }

    function init() {
        var dialog = document.querySelector('[data-visor-doc-dialog]');
        if (!dialog || typeof dialog.showModal !== 'function' || typeof window.fetch !== 'function' || !window.URL || typeof window.URL.createObjectURL !== 'function') {
            return;
        }

        var disparadores = document.querySelectorAll('[data-visor-doc-trigger]');
        if (!disparadores.length) {
            return;
        }

        var elTitulo = dialog.querySelector('[data-visor-titulo]');
        var elNombre = dialog.querySelector('[data-visor-nombre]');
        var elBody = dialog.querySelector('[data-visor-body]');
        var elCargando = dialog.querySelector('[data-visor-cargando]');
        var elImagenWrap = dialog.querySelector('[data-visor-imagen-wrap]');
        var elImagen = dialog.querySelector('[data-visor-imagen]');
        var elPdf = dialog.querySelector('[data-visor-pdf]');
        var elPdfLink = dialog.querySelector('[data-visor-pdf-link]');
        var elError = dialog.querySelector('[data-visor-error]');
        var elErrorTexto = dialog.querySelector('[data-visor-error-texto]');
        var btnCerrar = dialog.querySelector('[data-visor-cerrar]');
        var btnReintentar = dialog.querySelector('[data-visor-reintentar]');
        var linkDescargar = dialog.querySelector('[data-visor-descargar]');

        var solicitudId = 0;
        var abortController = null;
        var objectUrl = '';
        var disparadorActual = null;
        var archivoActual = null;

        function revocarUrl() {
            if (objectUrl) {
                window.URL.revokeObjectURL(objectUrl);
                objectUrl = '';
            }
            elImagen.onload = null;
            elImagen.onerror = null;
            elImagen.removeAttribute('src');
            elImagen.alt = '';
            elPdfLink.setAttribute('href', '#');
        }

        function cancelarCarga() {
            solicitudId += 1;
            if (abortController) {
                abortController.abort();
                abortController = null;
            }
        }

        function ocultarEstados() {
            elCargando.hidden = true;
            elImagenWrap.hidden = true;
            elPdf.hidden = true;
            elError.hidden = true;
            elErrorTexto.textContent = '';
            btnReintentar.hidden = true;
        }

        function limpiarContenido() {
            revocarUrl();
            ocultarEstados();
            if (elBody) {
                elBody.scrollTop = 0;
            }
        }

        function mostrarError(mensaje, recuperable) {
            revocarUrl();
            ocultarEstados();
            elErrorTexto.textContent = mensaje;
            elError.hidden = false;
            btnReintentar.hidden = !recuperable;
        }

        function cargarArchivo() {
            if (!archivoActual) {
                return;
            }
            cancelarCarga();
            limpiarContenido();
            elCargando.hidden = false;

            var idActual = solicitudId;
            var urlSegura = urlMismoOrigen(archivoActual.url);
            if (!urlSegura) {
                mostrarError('El archivo no está disponible en este momento.', false);
                return;
            }

            var signal;
            if (typeof window.AbortController === 'function') {
                abortController = new window.AbortController();
                signal = abortController.signal;
            }

            window.fetch(urlSegura, {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store',
                redirect: 'manual',
                signal: signal
            }).then(function (response) {
                if (idActual !== solicitudId || !dialog.open) {
                    return null;
                }
                if (response.type === 'opaqueredirect' || response.redirected || (response.status >= 300 && response.status < 400)) {
                    mostrarError('El archivo no está disponible en este momento.', false);
                    return null;
                }
                if (response.status === 403 || response.status === 404) {
                    mostrarError('El archivo no está disponible en este momento.', false);
                    return null;
                }
                if (!response.ok) {
                    mostrarError('No se pudo cargar el archivo en este momento. Podés reintentar o usar «Descargar».', true);
                    return null;
                }

                var mime = mimePermitido(archivoActual.formatos, response.headers.get('content-type'));
                if (!mime) {
                    mostrarError('Este archivo no se puede mostrar en vista previa. Podés acceder usando «Descargar».', false);
                    return null;
                }

                return response.blob().then(function (blob) {
                    if (idActual !== solicitudId || !dialog.open) {
                        return;
                    }
                    var blobTipado = blob.type === mime ? blob : new Blob([blob], { type: mime });
                    objectUrl = window.URL.createObjectURL(blobTipado);

                    if (mime === 'application/pdf') {
                        ocultarEstados();
                        elPdfLink.setAttribute('href', objectUrl);
                        elPdf.hidden = false;
                        return;
                    }

                    elImagen.onload = function () {
                        if (idActual !== solicitudId || !dialog.open) {
                            return;
                        }
                        ocultarEstados();
                        elImagenWrap.hidden = false;
                    };
                    elImagen.onerror = function () {
                        if (idActual !== solicitudId || !dialog.open) {
                            return;
                        }
                        mostrarError('No se pudo mostrar la imagen. Podés acceder al archivo usando «Descargar».', false);
                    };
                    elImagen.alt = archivoActual.nombre ? (archivoActual.titulo + ': ' + archivoActual.nombre) : archivoActual.titulo;
                    elImagen.src = objectUrl;
                });
            }).catch(function (err) {
                if (idActual !== solicitudId || !dialog.open || (err && err.name === 'AbortError')) {
                    return;
                }
                mostrarError('No se pudo cargar el archivo por un problema de conexión. Podés reintentar o usar «Descargar».', true);
            }).finally(function () {
                if (idActual === solicitudId) {
                    abortController = null;
                }
            });
        }

        function abrirDesde(disparador) {
            cancelarCarga();
            limpiarContenido();

            var url = urlMismoOrigen(disparador.getAttribute('data-visor-url') || '');
            var formatos = (disparador.getAttribute('data-visor-formatos') || 'pdf').trim().toLowerCase();
            var titulo = disparador.getAttribute('data-visor-titulo') || 'Archivo';
            var nombre = disparador.getAttribute('data-visor-nombre') || '';
            var descargarLabel = disparador.getAttribute('data-visor-descargar-label') || ('Descargar ' + titulo);

            disparadorActual = disparador;
            archivoActual = { url: url, formatos: formatos, titulo: titulo, nombre: nombre };

            elTitulo.textContent = titulo;
            if (nombre) {
                elNombre.textContent = nombre;
                elNombre.hidden = false;
            } else {
                elNombre.textContent = '';
                elNombre.hidden = true;
            }

            linkDescargar.setAttribute('href', url || '#');
            linkDescargar.setAttribute('aria-label', descargarLabel);

            if (!dialog.open) {
                dialog.showModal();
            }
            btnCerrar.focus();
            cargarArchivo();
        }

        for (var i = 0; i < disparadores.length; i += 1) {
            disparadores[i].hidden = false;
        }

        document.addEventListener('click', function (evento) {
            var trigger = evento.target.closest ? evento.target.closest('[data-visor-doc-trigger]') : null;
            if (!trigger) {
                return;
            }
            abrirDesde(trigger);
        });

        btnCerrar.addEventListener('click', function () {
            if (dialog.open) {
                dialog.close();
            }
        });

        btnReintentar.addEventListener('click', function () {
            btnCerrar.focus();
            cargarArchivo();
        });

        dialog.addEventListener('click', function (evento) {
            if (evento.target === dialog && dialog.open) {
                dialog.close();
            }
        });

        dialog.addEventListener('close', function () {
            cancelarCarga();
            limpiarContenido();
            var destino = disparadorActual;
            disparadorActual = null;
            archivoActual = null;
            if (destino && destino.isConnected && typeof destino.focus === 'function') {
                destino.focus();
            }
        });

        window.addEventListener('pagehide', function () {
            cancelarCarga();
            revocarUrl();
            if (dialog.open) {
                dialog.close();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
