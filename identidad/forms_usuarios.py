"""Formulario de edición administrativa de datos básicos locales (SPEC-024)."""

from typing import Any

from django import forms

from identidad.datos_usuarios import CAMPOS_EDITABLES, generar_referencia_edicion
from identidad.models import CuentaLocal


class EdicionDatosCuentaForm(forms.ModelForm):
    """Formulario acotado a los datos básicos editables de CuentaLocal."""

    referencia = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
    )

    class Meta:
        model = CuentaLocal
        fields = ["nombre_completo", "area_habitual", "cuit_cuil", "legajo"]
        labels = {
            "nombre_completo": "Nombre completo",
            "area_habitual": "Área habitual",
            "cuit_cuil": "CUIT / CUIL",
            "legajo": "Legajo",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for campo in CAMPOS_EDITABLES:
            field = self.fields[campo]
            if isinstance(field, forms.CharField):
                field.strip = True
        self.fields["nombre_completo"].required = True
        self.fields["area_habitual"].required = False
        self.fields["cuit_cuil"].required = False
        self.fields["legajo"].required = False

        # Sólo inicializa la referencia en formularios sin datos POST;
        # en POST se conserva la referencia enviada originalmente.
        if not self.is_bound and self.instance and self.instance.pk:
            self.fields["referencia"].initial = generar_referencia_edicion(self.instance)


OPCIONES_BOOLEANAS = (("true", "true"), ("false", "false"))


def _coerce_bool(valor: str) -> bool:
    """Convierte valores explícitos 'true'/'false' en booleanos."""
    if valor == "true":
        return True
    if valor == "false":
        return False
    raise forms.ValidationError("Valor booleano inválido.")


class ActividadCuentaForm(forms.Form):
    """Formulario de confirmación para desactivar o reactivar una cuenta local (SPEC-025)."""

    activar = forms.TypedChoiceField(
        choices=OPCIONES_BOOLEANAS,
        coerce=_coerce_bool,
        empty_value=None,
        required=True,
        widget=forms.HiddenInput(),
    )
    actividad_esperada = forms.TypedChoiceField(
        choices=OPCIONES_BOOLEANAS,
        coerce=_coerce_bool,
        empty_value=None,
        required=True,
        widget=forms.HiddenInput(),
    )
    motivo = forms.CharField(
        label="Motivo",
        required=True,
        strip=True,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
    )
