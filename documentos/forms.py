"""Entrada del formulario de revisión; el servicio revalida permisos y datos."""

from django import forms

from .models import RevisionDocumento


class RevisionDocumentoForm(forms.Form):
    resultado = forms.ChoiceField(
        label="Resultado",
        choices=[("", "Seleccioná un resultado"), *RevisionDocumento.Resultado.choices],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    motivo = forms.CharField(
        label="Motivo",
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Describí el motivo si observás o rechazás el documento.",
            }
        ),
        help_text="Obligatorio para observar o rechazar. Opcional para aceptar.",
    )
    revision_esperada = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
