// Cada selección conserva los demás filtros mediante el formulario GET.
document.querySelectorAll('[data-filtros-reporte]').forEach((form) => {
  form.addEventListener('change', (event) => {
    if (event.target.matches('select, input:not([type="hidden"])')) {
      form.requestSubmit();
    }
  });
});
