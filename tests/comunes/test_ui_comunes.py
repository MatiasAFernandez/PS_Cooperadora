from decimal import Decimal

from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from comunes.templatetags.formato_ars import ars


class _MensajeSintetico:
    def __init__(self, texto: str, tags: str = ""):
        self._texto = texto
        self.tags = tags

    def __str__(self) -> str:
        return self._texto


class FormatoArsTests(SimpleTestCase):
    def test_positivos_y_decimales(self):
        self.assertEqual(ars(195000), "$ 195.000,00")
        self.assertEqual(ars(Decimal("1234.5")), "$ 1.234,50")
        self.assertEqual(ars(1234.5), "$ 1.234,50")

    def test_redondeo_half_up(self):
        self.assertEqual(ars(Decimal("10.005")), "$ 10,01")
        self.assertEqual(ars(Decimal("10.004")), "$ 10,00")

    def test_cero_y_negativo_cero_normalizado(self):
        self.assertEqual(ars(0), "$ 0,00")
        self.assertEqual(ars(Decimal("-0.00")), "$ 0,00")
        self.assertEqual(ars(Decimal("-0.001")), "$ 0,00")

    def test_negativos(self):
        self.assertEqual(ars(Decimal("-1234.50")), "-$ 1.234,50")
        self.assertEqual(ars(-500), "-$ 500,00")

    def test_cadenas_estandar_y_argentinas(self):
        self.assertEqual(ars("195000.5"), "$ 195.000,50")
        self.assertEqual(ars("195000,5"), "$ 195.000,50")
        self.assertEqual(ars("195.000,50"), "$ 195.000,50")

    def test_valores_invalidos_o_no_finitos_devuelven_raya(self):
        for invalido in (
            None,
            "",
            "   ",
            "abc",
            True,
            False,
            float("nan"),
            float("inf"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
            Decimal("NaN"),
        ):
            with self.subTest(invalido=invalido):
                self.assertEqual(ars(invalido), "—")

    def test_render_en_plantilla_django(self):
        tpl = Template("{% load formato_ars %}{{ valor|ars }}")
        salida = tpl.render(Context({"valor": Decimal("195000")}))
        self.assertEqual(salida, "$ 195.000,00")


class MensajesFlashTests(SimpleTestCase):
    def test_sin_mensajes_devuelve_vacio(self):
        salida = render_to_string("comunes/mensajes_flash.html", {"messages": []})
        self.assertEqual(salida.strip(), "")

    def test_mapea_tags_a_clases_y_roles_accesibles(self):
        mensajes = [
            _MensajeSintetico("Error de validación", tags="error"),
            _MensajeSintetico("Advertencia de revisión", tags="warning"),
            _MensajeSintetico("Cambios guardados", tags="success"),
            _MensajeSintetico("Dato informativo", tags="info"),
            _MensajeSintetico("Mensaje sin etiqueta", tags=""),
        ]
        salida = render_to_string("comunes/mensajes_flash.html", {"messages": mensajes})

        self.assertIn('<div class="flash-messages">', salida)
        self.assertIn(
            '<div class="message message-error" role="alert">Error de validación</div>',
            salida,
        )
        self.assertIn(
            '<div class="message message-warning" role="status">Advertencia de revisión</div>',
            salida,
        )
        self.assertIn(
            '<div class="message message-success" role="status">Cambios guardados</div>',
            salida,
        )
        self.assertIn(
            '<div class="message message-info" role="status">Dato informativo</div>',
            salida,
        )
        self.assertIn(
            '<div class="message message-info" role="status">Mensaje sin etiqueta</div>',
            salida,
        )
