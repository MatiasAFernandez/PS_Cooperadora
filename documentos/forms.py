"""Entrada del formulario de revisión; el servicio revalida permisos y datos."""

from django import forms

from .models import RevisionDocumento


class RevisionDocumentoForm(forms.Form):
    resultado = forms.ChoiceField(
        choices=[("", "Seleccioná un resultado"), *RevisionDocumento.Resultado.choices]
    )
    motivo = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea,
        help_text="Obligatorio para observar o rechazar.",
    )
    revision_esperada = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
