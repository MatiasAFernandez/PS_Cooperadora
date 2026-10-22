"""Datos declarados de un comprobante externo; no emite ni valida fiscalmente."""

from decimal import Decimal

from django import forms

from .models import ComprobanteExterno
from .validation import validar_cuit


class ComprobanteExternoForm(forms.Form):
    tipo = forms.ChoiceField(choices=[("", "Seleccioná…"), *ComprobanteExterno.Tipo.choices])
    cuit_emisor = forms.CharField(label="CUIT del emisor", validators=[validar_cuit], max_length=11)
    letra = forms.RegexField(
        regex=r"^[A-Z]$",
        label="Letra",
        max_length=1,
        help_text="Copiala del comprobante emitido, en mayúscula.",
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
