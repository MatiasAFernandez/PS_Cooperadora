from django import forms
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class _ArchivoDummyForm(forms.Form):
    comprobante = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"accept": "application/pdf,.pdf,image/png,.png"}),
    )


class SelectorComprobanteTemplateTests(SimpleTestCase):
    def test_render_completo_con_acciones_y_sin_doble_dropzone(self):
        form = _ArchivoDummyForm()
        html = render_to_string(
            "comunes/selector_comprobante.html",
            {
                "field": form["comprobante"],
                "component_id": "prueba-comp",
                "titulo_visor": "Comprobante de prueba",
                "max_mib": 10,
                "max_bytes": 10485760,
                "formatos": "pdf-imagen",
            },
        )
        self.assertIn('id="prueba-comp-selector"', html)
        self.assertIn("data-selector-comprobante", html)
        self.assertIn("data-file-drop-custom", html)
        self.assertIn("Seleccionar archivo", html)
        self.assertIn("Ver archivo", html)
        self.assertIn("Descargar", html)
        self.assertIn("Cambiar", html)
        self.assertIn("Quitar", html)
        self.assertIn('id="prueba-comp-status"', html)
        self.assertNotIn("data-sc-aviso-perdida", html)

    def test_render_muestra_aviso_perdida_si_se_informa(self):
        form = _ArchivoDummyForm()
        html = render_to_string(
            "comunes/selector_comprobante.html",
            {
                "field": form["comprobante"],
                "component_id": "prueba-comp",
                "aviso_perdida": "Volvé a elegir el comprobante.",
            },
        )
        self.assertIn("data-sc-aviso-perdida", html)
        self.assertIn("Volvé a elegir el comprobante.", html)
