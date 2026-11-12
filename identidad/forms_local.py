"""Formularios para el flujo de acceso, registro y administración de cuentas locales."""

import logging
import urllib.parse
from collections.abc import Generator
from typing import Any

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ImproperlyConfigured, ValidationError

from identidad.cuentas import normalizar_correo
from identidad.models import CuentaLocal
from identidad.tokens_local import token_recuperacion_local

logger = logging.getLogger(__name__)


class RegistroForm(forms.Form):
    """Formulario de registro público para nuevas cuentas locales."""

    nombre = forms.CharField(
        max_length=150,
        label="Nombre completo",
        widget=forms.TextInput(attrs={"autocomplete": "name", "class": "form-control"}),
    )
    email = forms.EmailField(
        max_length=254,
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "class": "form-control"}),
    )
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )
    password2 = forms.CharField(
        label="Repetir contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )
    area_habitual = forms.CharField(
        max_length=150,
        required=False,
        label="Área habitual",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    cuit_cuil = forms.CharField(
        max_length=20,
        required=False,
        label="CUIT / CUIL",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    legajo = forms.CharField(
        max_length=50,
        required=False,
        label="Legajo",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas ingresadas no coinciden.")

        if p1 and p2 and p1 == p2:
            user_model = get_user_model()
            email = normalizar_correo(cleaned_data.get("email") or "")
            nombre = (cleaned_data.get("nombre") or "").strip()
            temp_user = user_model(
                username="local_temp_validation",
                email=email,
                first_name=nombre[:150],
            )
            try:
                validate_password(p1, user=temp_user)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data


class AccesoLocalForm(AuthenticationForm):
    """Formulario de autenticación exclusivo para identidades locales por correo."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Ingresá un correo electrónico y una contraseña válidos.",
    }

    username = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "class": "form-control", "autofocus": True}
        ),
    )

    def __init__(self, request: Any = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(request, *args, **kwargs)
        self.fields["password"].widget.attrs.update(
            {"autocomplete": "current-password", "class": "form-control"}
        )

    def clean(self) -> dict[str, Any]:
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            email_norm = normalizar_correo(username)
            user_model = get_user_model()
            cuenta = (
                CuentaLocal.objects.select_related("user").filter(email__iexact=email_norm).first()
            )
            if cuenta is None:
                # Calcular hash dummy para mitigar enumeración y análisis de tiempos
                dummy = user_model()
                dummy.set_password(password)
                raise self.get_invalid_login_error()

            self.user_cache = authenticate(
                self.request,
                username=cuenta.user.get_username(),
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()

            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class ReenvioForm(forms.Form):
    """Formulario para solicitar un nuevo enlace de verificación de correo."""

    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "class": "form-control", "autofocus": True}
        ),
    )


class VerificacionForm(forms.Form):
    """Formulario interno para confirmar la verificación mediante token firmado."""

    token = forms.CharField(widget=forms.HiddenInput())


class DecisionForm(forms.Form):
    """Formulario administrativo para resolver altas de cuentas pendientes."""

    cuenta_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput())
    accion = forms.ChoiceField(
        choices=[("APROBAR", "Aprobar"), ("RECHAZAR", "Rechazar")],
        widget=forms.RadioSelect(),
    )
    motivo = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        accion = cleaned.get("accion")
        motivo = (cleaned.get("motivo") or "").strip()
        if accion == "RECHAZAR" and not motivo:
            self.add_error("motivo", "El motivo es obligatorio al rechazar una solicitud.")
        return cleaned


class RecuperacionLocalForm(PasswordResetForm):
    """Formulario de recuperación de clave restringido a cuentas locales aprobadas."""

    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "class": "form-control", "autofocus": True}
        ),
    )

    def get_users(self, email: str) -> Generator[AbstractBaseUser, None, None]:
        email_norm = normalizar_correo(email)
        cuentas = CuentaLocal.objects.select_related("user").filter(
            email__iexact=email_norm,
            email_verificado_en__isnull=False,
            estado=CuentaLocal.Estado.APROBADA,
            user__is_active=True,
        )
        for cuenta in cuentas:
            if normalizar_correo(cuenta.user.email) != normalizar_correo(cuenta.email):
                continue
            if cuenta.user.has_usable_password():
                yield cuenta.user

    def save(
        self,
        domain_override: str | None = None,
        subject_template_name: str = "cuentas/asunto_reset.txt",
        email_template_name: str = "cuentas/email_reset.txt",
        use_https: bool = False,
        token_generator: Any = token_recuperacion_local,
        from_email: str | None = None,
        request: Any = None,
        html_email_template_name: str | None = None,
        extra_email_context: dict[str, Any] | None = None,
    ) -> None:
        base_url = getattr(settings, "LOCAL_PUBLIC_BASE_URL", "")
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            logger.error("LOCAL_PUBLIC_BASE_URL no está configurada o es inválida.")
            raise ImproperlyConfigured("LOCAL_PUBLIC_BASE_URL no está configurada correctamente.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            logger.error("LOCAL_PUBLIC_BASE_URL contiene elementos no permitidos.")
            raise ImproperlyConfigured("LOCAL_PUBLIC_BASE_URL contiene elementos no permitidos.")
        if parsed.path not in ("", "/"):
            logger.error("LOCAL_PUBLIC_BASE_URL debe apuntar a la raíz del servidor.")
            raise ImproperlyConfigured("LOCAL_PUBLIC_BASE_URL contiene una ruta no permitida.")

        domain_override = parsed.netloc
        use_https = parsed.scheme == "https"

        ctx: dict[str, Any] = {
            "acceso_local": True,
            "reset_url_name": "cuentas:reset_confirm",
        }
        if extra_email_context:
            ctx.update(extra_email_context)

        from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)

        super().save(
            domain_override=domain_override,
            subject_template_name=subject_template_name,
            email_template_name=email_template_name,
            use_https=use_https,
            token_generator=token_generator,
            from_email=from_email,
            request=request,
            html_email_template_name=html_email_template_name,
            extra_email_context=ctx,
        )
