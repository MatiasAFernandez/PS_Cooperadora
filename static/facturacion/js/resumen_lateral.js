const panel = document.getElementById('resumen-facturacion');
const titulo = document.getElementById('titulo-resumen-facturacion');
const contenido = panel.querySelector('[data-contenido-resumen]');
let activador;

if (typeof panel.showModal === 'function') {
    document.querySelectorAll('[data-resumen]').forEach((elemento) => {
        const resumen = document.getElementById(`resumen-solicitud-${elemento.dataset.resumen}`);
        if (!resumen) return;

        function abrir() {
            if (panel.open) return;
            activador = elemento;
            titulo.textContent = resumen.dataset.titulo;
            contenido.replaceChildren(resumen.content.cloneNode(true));
            panel.showModal();
            contenido.scrollTop = 0;
        }

        elemento.tabIndex = 0;
        elemento.setAttribute('aria-describedby', 'ayuda-abrir-resumen');
        elemento.addEventListener('click', (evento) => {
            if (!evento.target.closest('a, button')) abrir();
        });
        elemento.addEventListener('keydown', (evento) => {
            if (evento.target !== elemento || !['Enter', ' '].includes(evento.key)) return;
            evento.preventDefault();
            abrir();
        });
    });
}

function esFondo(evento) {
    const {left, right} = panel.getBoundingClientRect();
    return evento.target === panel && (evento.clientX < left || evento.clientX > right);
}

let empezoEnFondo = false;
panel.addEventListener('pointerdown', (evento) => { empezoEnFondo = esFondo(evento); });
panel.addEventListener('click', (evento) => {
    if (empezoEnFondo && esFondo(evento)) panel.close();
});

panel.addEventListener('close', () => {
    empezoEnFondo = false;
    if (!panel.open) activador?.focus({preventScroll: true});
});
