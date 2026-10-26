"""Datos declarados de un comprobante externo; no emite ni valida fiscalmente."""

from decimal import Decimal

from django import forms

from .models import ComprobanteExterno
from .validation import validar_cuit


class ComprobanteExternoForm(forms.Form):
    tipo = forms.ChoiceField(choices=[("", "Seleccioná…"), *ComprobanteExterno.Tipo.choices])
    cuit_emisor = forms.CharField(
        label="CUIT de quien emite el comprobante",
        validators=[validar_cuit],
        max_length=11,
        help_text=(
            "Copialo del comprobante emitido. Si factura Cooperadora, corresponde su CUIT; "
            "el CUIT del receptor de la solicitud identifica a quien recibe la factura."
        ),
    )
    letra = forms.RegexField(
        regex=r"^[A-Z]$",
        label="Letra del comprobante (A, B, C…)",
        max_length=1,
        help_text=(
            "Copiala del comprobante emitido, en mayúscula. "
            "El campo Tipo distingue factura, nota de crédito o nota de débito."
        ),
    )
    punto_venta = forms.IntegerField(label="Punto de venta", min_value=1, max_value=99999)
    numero = forms.IntegerField(label="Número", min_value=1, max_value=99999999)
    fecha_emision = forms.DateField(
        label="Fecha de emisión",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    importe = forms.DecimalField(
        label="Importe del comprobante",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    archivo_pdf = forms.FileField(label="PDF del comprobante")

    procedencia = forms.ChoiceField(
        label="Origen",
        required=False,
        choices=[("EXTERNO_XUBIO", "Xubio"), ("EXTERNO_OTRO", "Otro")],
        initial="EXTERNO_XUBIO",
    )
    origen_aclaracion = forms.CharField(
        label="Aclaración del otro origen",
        required=False,
        max_length=200,
        help_text="Obligatoria si seleccionás Otro.",
    )

    def clean(self):
        datos = super().clean()
        origen = datos.get("procedencia") or "EXTERNO_XUBIO"
        datos["procedencia"] = origen
        if origen == "EXTERNO_OTRO" and not datos.get("origen_aclaracion"):
            self.add_error("origen_aclaracion", "Indicá el sistema o procedencia del comprobante.")
        if origen == "EXTERNO_XUBIO":
            datos["origen_aclaracion"] = ""
        return datos
