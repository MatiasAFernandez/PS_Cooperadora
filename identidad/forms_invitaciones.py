"""Formularios para el alta administrativa mediante invitación (SPEC-027)."""

from typing import Any

from django import forms
from django.contrib.auth.forms import SetPasswordForm

from identidad.cuentas import normalizar_correo


class InvitacionAltaForm(forms.Form):
    """Formulario administrativo acotado para crear una cuenta local e invitarla."""

    nombre = forms.CharField(
        max_length=150,
        required=True,
        strip=True,
        label="Nombre completo",
        widget=forms.TextInput(attrs={"autocomplete": "name", "class": "form-control"}),
    )
    email = forms.EmailField(
        max_length=254,
        required=True,
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "class": "form-control"}),
    )
    area_habitual = forms.CharField(
        max_length=150,
        required=False,
        strip=True,
        label="Área habitual",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    cuit_cuil = forms.CharField(
        max_length=20,
        required=False,
        strip=True,
        label="CUIT / CUIL",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    legajo = forms.CharField(
        max_length=50,
        required=False,
        strip=True,
        label="Legajo",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def clean_email(self) -> str:
        """Normaliza el correo electrónico ingresado."""
        return normalizar_correo(self.cleaned_data.get("email") or "")


class AceptarInvitacionForm(SetPasswordForm):
    """Formulario público para que el titular defina su contraseña al aceptar invitación."""

    token = forms.CharField(widget=forms.HiddenInput(), required=True)

    def __init__(self, user: Any, *args: Any, **kwargs: Any) -> None:
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].widget.attrs.update(
            {"autocomplete": "new-password", "class": "form-control"}
        )
        self.fields["new_password2"].widget.attrs.update(
            {"autocomplete": "new-password", "class": "form-control"}
        )
