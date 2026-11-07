const formularioCobro = document.querySelector("[data-modificar-cobro]");
const avisoRectificacion = formularioCobro?.querySelector("[data-aviso-rectificacion]");

if (avisoRectificacion) {
    const campos = [...formularioCobro.querySelectorAll("[data-valor-original]")];
    const boton = formularioCobro.querySelector('button[type="submit"]');

    function actualizarAviso() {
        const cambios = campos.some((campo) => {
            const original = campo.dataset.valorOriginal;
            if (campo.type === "number" && campo.value !== "") {
                return campo.valueAsNumber !== Number(original);
            }
            return campo.value.trim() !== original;
        });
        avisoRectificacion.hidden = !cambios;
        boton.textContent = cambios ? "Rectificar y guardar corrección" : "Guardar cambios";
    }

    formularioCobro.addEventListener("input", actualizarAviso);
    formularioCobro.addEventListener("change", actualizarAviso);
    actualizarAviso();
}
