"""Vistas HTTP administrativas y públicas para invitaciones de cuentas locales (SPEC-027)."""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import TemplateView, View

from identidad.forms_invitaciones import AceptarInvitacionForm, InvitacionAltaForm
from identidad.invitaciones import (
    _ERROR_ENLACE_GENERICO,
    aceptar_invitacion,
    crear_cuenta_invitada,
    enviar_invitacion,
    validar_invitacion,
)
from identidad.models import CuentaLocal, InvitacionCuentaLocal
from identidad.services import Actor
from identidad.views_local import LocalOnlyMixin
from identidad.views_usuarios import _autorizar, _extraer_listado_query


def _aplicar_cabeceras_sensibles(response: HttpResponse) -> HttpResponse:
    """Aplica cabeceras no-store y Referrer-Policy same-origin para flujos con token."""
    add_never_cache_headers(response)
    response["Referrer-Policy"] = "same-origin"
    return response


def _destino_ficha(pk: int, listado_query: str) -> str:
    """Construye la URL de retorno a la ficha conservando filtros normalizados."""
    destino = reverse("cuentas:usuario_detalle", args=[pk])
    if listado_query:
        return f"{destino}?{listado_query}"
    return destino


class UsuarioNuevoView(LocalOnlyMixin, View):
    """Alta administrativa de cuenta local mediante invitación por correo."""

    http_method_names = ["get", "post"]

    def _render_formulario(
        self,
        request: HttpRequest,
        *,
        actor: Actor,
        form: InvitacionAltaForm,
        listado_query: str,
        status: int = 200,
    ) -> HttpResponse:
        response = render(
            request,
            "cuentas/invitacion_alta.html",
            {
                "actor": actor,
                "acceso_local": True,
                "form": form,
                "listado_query": listado_query,
            },
            status=status,
        )
        add_never_cache_headers(response)
        return response

    def get(self, request: HttpRequest) -> HttpResponse:
        actor = _autorizar(request)
        listado_query = _extraer_listado_query(request)
        form = InvitacionAltaForm()
        return self._render_formulario(
            request,
            actor=actor,
            form=form,
            listado_query=listado_query,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        actor = _autorizar(request)
        listado_query = _extraer_listado_query(request)
        form = InvitacionAltaForm(request.POST)
        if not form.is_valid():
            return self._render_formulario(
                request,
                actor=actor,
                form=form,
                listado_query=listado_query,
                status=400,
            )

        try:
            cuenta = crear_cuenta_invitada(
                actor,
                nombre=form.cleaned_data["nombre"],
                email=form.cleaned_data["email"],
                area_habitual=form.cleaned_data.get("area_habitual", ""),
                cuit_cuil=form.cleaned_data.get("cuit_cuil", ""),
                legajo=form.cleaned_data.get("legajo", ""),
            )
        except ValidationError as exc:
            for mensaje in exc.messages:
                form.add_error(None, mensaje)
            return self._render_formulario(
                request,
                actor=actor,
                form=form,
                listado_query=listado_query,
                status=400,
            )

        envio_ok = False
        try:
            envio_ok = enviar_invitacion(cuenta)
        except ValidationError:
            envio_ok = False

        if envio_ok:
            messages.success(
                request,
                "Cuenta creada. La invitación fue aceptada por el servidor de correo "
                "para su envío.",
            )
        else:
            messages.warning(
                request,
                "Cuenta creada, pero no se pudo enviar la invitación ahora; "
                "quedó pendiente para reenviar desde la ficha.",
            )

        response = redirect(_destino_ficha(cuenta.pk, listado_query))
        add_never_cache_headers(response)
        return response


class UsuarioReenviarInvitacionView(LocalOnlyMixin, View):
    """Reenvío administrativo de invitación por POST con PRG hacia la ficha."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        _autorizar(request)
        listado_query = _extraer_listado_query(request)
        cuenta = get_object_or_404(
            CuentaLocal.objects.select_related("user", "invitacion_administrativa"),
            pk=pk,
        )
        invitacion = getattr(cuenta, "invitacion_administrativa", None)

        if invitacion is None:
            messages.error(request, "La cuenta no fue creada mediante invitación administrativa.")
        elif invitacion.aceptada_en is not None or cuenta.user.has_usable_password():
            messages.warning(
                request,
                "La invitación ya fue aceptada o la cuenta ya tiene una contraseña definida.",
            )
        elif not cuenta.user.is_active or cuenta.estado == CuentaLocal.Estado.RECHAZADA:
            messages.error(
                request, "La cuenta no se encuentra habilitada para recibir invitaciones."
            )
        else:
            from django.conf import settings

            min_interval = getattr(settings, "LOCAL_VERIFY_RESEND_MIN_INTERVAL", 60)
            ahora = timezone.now()
            if (
                min_interval > 0
                and cuenta.ultimo_envio is not None
                and (ahora - cuenta.ultimo_envio).total_seconds() < min_interval
            ):
                messages.warning(
                    request,
                    "Aguardá unos segundos antes de volver a reenviar la invitación.",
                )
            else:
                envio_ok = False
                try:
                    envio_ok = enviar_invitacion(cuenta)
                except ValidationError:
                    envio_ok = False

                if envio_ok:
                    messages.success(
                        request,
                        "Invitación reenviada al servidor de correo para su despacho.",
                    )
                else:
                    invitacion.refresh_from_db()
                    if invitacion.estado_envio == InvitacionCuentaLocal.EstadoEnvio.ERROR:
                        messages.error(
                            request,
                            "No se pudo enviar la invitación en este momento. "
                            "Intentá nuevamente más tarde.",
                        )
                    else:
                        messages.warning(
                            request,
                            "Se alcanzó el límite temporal de envíos. Intentá más tarde.",
                        )

        response = redirect(_destino_ficha(cuenta.pk, listado_query))
        add_never_cache_headers(response)
        return response


@method_decorator(
    sensitive_post_parameters("new_password1", "new_password2"),
    name="dispatch",
)
class AceptarInvitacionView(LocalOnlyMixin, View):
    """Vista pública para validar invitación y definir la contraseña del titular."""

    http_method_names = ["get", "post"]

    def _render_error_enlace(self, request: HttpRequest, mensaje: str) -> HttpResponse:
        response = render(
            request,
            "cuentas/estado.html",
            {
                "title": "Enlace no válido",
                "modo": "error",
                "mensaje": mensaje,
                "cuenta": None,
                "actor": None,
                "acceso_local": True,
            },
            status=400,
        )
        return _aplicar_cabeceras_sensibles(response)

    def _render_formulario(
        self,
        request: HttpRequest,
        *,
        form: AceptarInvitacionForm,
        cuenta: CuentaLocal,
        status: int = 200,
    ) -> HttpResponse:
        response = render(
            request,
            "cuentas/formulario.html",
            {
                "title": "Definir contraseña",
                "introduccion": (
                    f"Elegí una contraseña para {cuenta.email} para confirmar tu correo "
                    "y dejar la cuenta lista para aprobación."
                ),
                "form": form,
                "submit_label": "Confirmar contraseña",
                "acceso_local": True,
            },
            status=status,
        )
        return _aplicar_cabeceras_sensibles(response)

    def get(self, request: HttpRequest) -> HttpResponse:
        token = request.GET.get("token", "").strip()
        try:
            cuenta = validar_invitacion(token)
        except ValidationError:
            return self._render_error_enlace(request, _ERROR_ENLACE_GENERICO)

        form = AceptarInvitacionForm(user=cuenta.user, initial={"token": token})
        return self._render_formulario(request, form=form, cuenta=cuenta)

    def post(self, request: HttpRequest) -> HttpResponse:
        token = request.POST.get("token", "").strip()
        try:
            cuenta = validar_invitacion(token)
        except ValidationError:
            return self._render_error_enlace(request, _ERROR_ENLACE_GENERICO)

        form = AceptarInvitacionForm(user=cuenta.user, data=request.POST)
        if not form.is_valid():
            return self._render_formulario(request, form=form, cuenta=cuenta, status=400)

        try:
            aceptar_invitacion(
                form.cleaned_data["token"],
                form.cleaned_data["new_password1"],
            )
        except ValidationError as exc:
            if _ERROR_ENLACE_GENERICO in exc.messages:
                return self._render_error_enlace(request, _ERROR_ENLACE_GENERICO)
            for mensaje in exc.messages:
                form.add_error(None, mensaje)
            return self._render_formulario(request, form=form, cuenta=cuenta, status=400)

        response = redirect(reverse("cuentas:invitacion_completa"))
        return _aplicar_cabeceras_sensibles(response)


class InvitacionCompletaView(LocalOnlyMixin, TemplateView):
    """Confirmación pública neutra tras aceptar una invitación administrativa."""

    template_name = "cuentas/estado.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Contraseña definida"
        context["modo"] = "invitacion_completa"
        context["mensaje"] = (
            "Tu correo electrónico fue verificado y tu contraseña quedó definida. "
            "La cuenta se encuentra pendiente de aprobación administrativa para operar. "
            "Ya podés iniciar sesión para consultar su estado."
        )
        context["cuenta"] = None
        context["actor"] = None
        context["acceso_local"] = True
        return context

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        response = super().get(request, *args, **kwargs)
        return _aplicar_cabeceras_sensibles(response)
