document.querySelectorAll('form[enctype="multipart/form-data"] input[type="file"]').forEach((campo) => {
    const zona = document.createElement('div');
    zona.className = 'file-drop';

    const ayuda = document.createElement('small');
    ayuda.id = `${campo.id || campo.name}-arrastre`;
    const instruccion = campo.multiple ? 'También podés arrastrar archivos aquí.' : 'También podés arrastrar un archivo aquí.';
    ayuda.textContent = instruccion;
    ayuda.setAttribute('aria-live', 'polite');
    campo.setAttribute('aria-describedby', [campo.getAttribute('aria-describedby'), ayuda.id].filter(Boolean).join(' '));
    campo.before(zona);
    zona.append(campo, ayuda);

    zona.addEventListener('dragover', (evento) => {
        if (!evento.dataTransfer.types.includes('Files')) return;
        evento.preventDefault();
        evento.dataTransfer.dropEffect = campo.disabled ? 'none' : 'copy';
        zona.classList.toggle('file-drop-active', !campo.disabled);
    });

    zona.addEventListener('dragleave', (evento) => {
        if (!zona.contains(evento.relatedTarget)) zona.classList.remove('file-drop-active');
    });

    campo.addEventListener('change', () => { ayuda.textContent = instruccion; });
    zona.addEventListener('drop', (evento) => {
        const archivos = evento.dataTransfer.files;
        zona.classList.remove('file-drop-active');
        if (!evento.dataTransfer.types.includes('Files')) return;
        evento.preventDefault();
        if (campo.disabled || !archivos.length) return;
        if (!campo.multiple && archivos.length > 1) {
            ayuda.textContent = 'Soltá un solo archivo en este campo.';
            return;
        }
        campo.files = archivos;
        campo.dispatchEvent(new Event('change', { bubbles: true }));
    });
});
