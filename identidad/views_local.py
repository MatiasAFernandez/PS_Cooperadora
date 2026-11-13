"""Vistas para el flujo de acceso, registro y administración de cuentas locales."""

import logging
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
    redirect_to_login,
)
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.cache import add_never_cache_headers
from django.views.generic import FormView, TemplateView, View

from identidad.cuentas import (
    decidir_cuenta,
    enviar_verificacion,
    limitar,
    normalizar_correo,
    registrar_cuenta,
    verificar_correo,
)
from identidad.forms_local import (
    AccesoLocalForm,
    DecisionForm,
    RecuperacionLocalForm,
    ReenvioForm,
    RegistroForm,
    VerificacionForm,
)
from identidad.models import CuentaLocal
from identidad.services import has_capability, resolve_actor
from identidad.tokens_local import token_recuperacion_local

logger = logging.getLogger(__name__)


class LocalOnlyMixin:
    """Restringe el acceso exclusivamente cuando LOCAL_IDENTITY_ENABLED está activo."""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not getattr(settings, "LOCAL_IDENTITY_ENABLED", False):
            raise Http404("El acceso local no se encuentra habilitado.")
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


class RegistroView(LocalOnlyMixin, FormView):
    """Vista de registro público de cuentas locales."""

    template_name = "cuentas/formulario.html"
    form_class = RegistroForm
    success_url = reverse_lazy("cuentas:recibido")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Solicitar cuenta"
        context["submit_label"] = "Solicitar cuenta"
        context["acceso_local"] = True
        context["introduccion"] = (
            "Verificá tu correo y aguardá la aprobación para comenzar a operar."
        )
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        ip = request.META.get("REMOTE_ADDR") or "127.0.0.1"
        if not limitar(f"registro-ip:{ip}", maximo=10, segundos=300):
            form = self.get_form()
            form.add_error(None, "Se ha superado el límite de intentos. Intente más tarde.")
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: RegistroForm) -> HttpResponse:
        try:
            cuenta = registrar_cuenta(
                nombre=form.cleaned_data["nombre"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password1"],
                area_habitual=form.cleaned_data.get("area_habitual", ""),
                cuit_cuil=form.cleaned_data.get("cuit_cuil", ""),
                legajo=form.cleaned_data.get("legajo", ""),
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        if cuenta is not None:
            base_url = getattr(settings, "LOCAL_PUBLIC_BASE_URL", "")
            enviar_verificacion(cuenta, base_url=base_url)

        return redirect(self.get_success_url())

    def form_invalid(self, form: RegistroForm) -> HttpResponse:
        response = super().form_invalid(form)
        response.status_code = 400
        return response


class RecibidoView(LocalOnlyMixin, TemplateView):
    """Confirmación neutra tras completar el registro."""

    template_name = "cuentas/estado.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Solicitud recibida"
        context["modo"] = "recibido"
        context["mensaje"] = (
            "Si el pedido pudo registrarse, recibirás un enlace. "
            "Si no llega, podés intentar reenviarlo."
        )
        context["acceso_local"] = True
        return context


class VerificarView(LocalOnlyMixin, View):
    """Verificación de correo mediante enlace con token firmado."""

    def get(self, request: HttpRequest) -> HttpResponse:
        token = request.GET.get("token", "").strip()
        if not token:
            response = render(
                request,
                "cuentas/estado.html",
                {
                    "title": "Error de verificación",
                    "modo": "error",
                    "mensaje": "El enlace de verificación no contiene un token válido.",
                    "acceso_local": True,
                },
                status=400,
            )
            add_never_cache_headers(response)
            response["Referrer-Policy"] = "no-referrer"
            return response

        form = VerificacionForm(initial={"token": token})
        response = render(
            request,
            "cuentas/formulario.html",
            {
                "title": "Confirmar verificación de correo",
                "introduccion": "Presione el botón para confirmar la verificación de su correo.",
                "form": form,
                "submit_label": "Verificar mi correo",
                "acceso_local": True,
            },
        )
        add_never_cache_headers(response)
        # same-origin conserva el Referer interno que exige la validación CSRF
        # y evita enviar la URL con token a otros orígenes.
        response["Referrer-Policy"] = "same-origin"
        return response

    def post(self, request: HttpRequest) -> HttpResponse:
        form = VerificacionForm(request.POST)
        if not form.is_valid():
            response = render(
                request,
                "cuentas/estado.html",
                {
                    "title": "Error de verificación",
                    "modo": "error",
                    "mensaje": "Los datos del formulario de verificación son inválidos.",
                    "acceso_local": True,
                },
                status=400,
            )
            add_never_cache_headers(response)
            response["Referrer-Policy"] = "no-referrer"
            return response

        token = form.cleaned_data["token"]
        try:
            verificar_correo(token)
        except ValidationError as exc:
            msg = exc.messages[0] if hasattr(exc, "messages") and exc.messages else str(exc)
            response = render(
                request,
                "cuentas/estado.html",
                {
                    "title": "Error de verificación",
                    "modo": "error",
                    "mensaje": msg,
                    "acceso_local": True,
                },
                status=400,
            )
            add_never_cache_headers(response)
            response["Referrer-Policy"] = "no-referrer"
            return response

        return redirect(f"{reverse('cuentas:estado')}?modo=verificado")


class ReenviarView(LocalOnlyMixin, FormView):
    """Reenvío de correo de verificación para cuentas pendientes."""

    template_name = "cuentas/formulario.html"
    form_class = ReenvioForm
    success_url = reverse_lazy("cuentas:recibido")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Reenviar enlace de verificación"
        context["submit_label"] = "Reenviar correo"
        context["acceso_local"] = True
        context["introduccion"] = (
            "Ingrese su correo electrónico para recibir un nuevo enlace de verificación."
        )
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        ip = request.META.get("REMOTE_ADDR") or "127.0.0.1"
        if not limitar(f"reenvio-ip:{ip}", maximo=10, segundos=300):
            form = self.get_form()
            form.add_error(None, "Se ha superado el límite de intentos. Intente más tarde.")
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: ReenvioForm) -> HttpResponse:
        email_norm = normalizar_correo(form.cleaned_data["email"])
        cuenta = CuentaLocal.objects.filter(
            email__iexact=email_norm,
            estado=CuentaLocal.Estado.PENDIENTE,
            email_verificado_en__isnull=True,
            user__is_active=True,
        ).first()

        if cuenta is not None:
            base_url = getattr(settings, "LOCAL_PUBLIC_BASE_URL", "")
            enviar_verificacion(cuenta, base_url=base_url)

        return redirect(self.get_success_url())

    def form_invalid(self, form: ReenvioForm) -> HttpResponse:
        response = super().form_invalid(form)
        response.status_code = 400
        return response


class LocalLoginView(LocalOnlyMixin, LoginView):
    """Autenticación exclusiva para cuentas locales con control de tasa."""

    template_name = "cuentas/formulario.html"
    form_class = AccesoLocalForm

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Ingresar a Cooperadora"
        context["submit_label"] = "Iniciar sesión"
        context["acceso_local"] = True
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        ip = request.META.get("REMOTE_ADDR") or "127.0.0.1"
        user_raw = normalizar_correo(request.POST.get("username", ""))

        if not limitar(f"login-ip:{ip}", maximo=20, segundos=300) or (
            user_raw and not limitar(f"login-dest:{user_raw}", maximo=10, segundos=300)
        ):
            form = self.get_form()
            form.add_error(None, "Demasiados intentos de acceso fallidos. Intente más tarde.")
            response = self.form_invalid(form)
            response.status_code = 400
            return response

        return super().post(request, *args, **kwargs)

    def get_success_url(self) -> str:
        user = self.request.user
        cuenta = CuentaLocal.objects.filter(user_id=user.pk).first()

        if (
            cuenta is None
            or cuenta.email_verificado_en is None
            or cuenta.estado != CuentaLocal.Estado.APROBADA
        ):
            return reverse("cuentas:estado")

        redirect_to = self.get_redirect_url()
        return redirect_to if redirect_to else reverse("cuentas:inicio")


class LocalLogoutView(LocalOnlyMixin, LogoutView):
    """Cierre de sesión local por POST con token CSRF."""

    next_page = reverse_lazy("cuentas:login")


class InicioView(LocalOnlyMixin, View):
    """Panel de inicio local para usuarios operativos."""

    def get(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("cuentas:login"))

        cuenta = CuentaLocal.objects.filter(user_id=request.user.pk).first()
        if cuenta is None:
            raise PermissionDenied("No posee una cuenta local registrada.")

        actor = resolve_actor(request)
        if actor is None:
            return redirect("cuentas:estado")

        return render(
            request,
            "cuentas/inicio.html",
            {
                "actor": actor,
                "cuenta": cuenta,
                "acceso_local": True,
            },
        )


class EstadoView(LocalOnlyMixin, View):
    """Consulta de estado propia o visualización de confirmaciones públicas."""

    def get(self, request: HttpRequest) -> HttpResponse:
        modo = request.GET.get("modo", "estado")

        if request.user.is_authenticated:
            cuenta = CuentaLocal.objects.filter(user_id=request.user.pk).first()
            if cuenta is None:
                raise PermissionDenied("No posee una cuenta local registrada.")

            actor = resolve_actor(request)
            title = "Estado de cuenta"
            mensaje = "Información sobre el estado administrativo de su cuenta local."

            if modo == "verificado":
                title = "Correo verificado"
                mensaje = (
                    "Su correo electrónico ha sido verificado. "
                    "La cuenta se encuentra pendiente de aprobación administrativa."
                )

            return render(
                request,
                "cuentas/estado.html",
                {
                    "title": title,
                    "modo": modo,
                    "mensaje": mensaje,
                    "cuenta": cuenta,
                    "actor": actor,
                    "acceso_local": True,
                },
            )

        # Estados y confirmaciones públicas no autenticadas
        mensajes_modo = {
            "verificado": (
                "Correo verificado",
                (
                    "Su correo electrónico ha sido verificado. "
                    "La cuenta se encuentra pendiente de aprobación administrativa."
                ),
            ),
            "recibido": (
                "Solicitud recibida",
                (
                    "Si el pedido pudo registrarse, recibirás un enlace. "
                    "Si no llega, podés intentar reenviarlo."
                ),
            ),
            "recuperar_enviado": (
                "Revisá tu correo",
                (
                    "Si la cuenta puede recuperar el acceso, recibirás instrucciones. "
                    "Si no llegan, intentá nuevamente más tarde."
                ),
            ),
            "reset_completo": (
                "Contraseña restablecida",
                (
                    "Su contraseña ha sido restablecida correctamente. "
                    "Ya puede ingresar con su nueva clave."
                ),
            ),
            "clave_cambiada": (
                "Contraseña actualizada",
                "Su contraseña ha sido modificada con éxito.",
            ),
        }

        title, mensaje = mensajes_modo.get(
            modo,
            ("Estado de solicitud", "Información sobre el estado de su trámite de cuenta."),
        )

        return render(
            request,
            "cuentas/estado.html",
            {
                "title": title,
                "modo": modo,
                "mensaje": mensaje,
                "cuenta": None,
                "actor": None,
                "acceso_local": True,
            },
        )


class AltasView(LocalOnlyMixin, View):
    """Bandeja administrativa para evaluar altas pendientes."""

    def get(self, request: HttpRequest) -> HttpResponse:
        actor = resolve_actor(request)
        if not has_capability(actor, "identidad.administrar_cuentas"):
            raise PermissionDenied("No posee capacidad para administrar cuentas.")

        pendientes = CuentaLocal.objects.filter(estado=CuentaLocal.Estado.PENDIENTE).order_by(
            "creada_en"
        )
        paginator = Paginator(pendientes, 25)
        page = paginator.get_page(request.GET.get("page"))

        return render(
            request,
            "cuentas/altas.html",
            {
                "actor": actor,
                "cuentas": page,
                "acceso_local": True,
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        actor = resolve_actor(request)
        if not has_capability(actor, "identidad.administrar_cuentas"):
            raise PermissionDenied("No posee capacidad para administrar cuentas.")

        pendientes = CuentaLocal.objects.filter(estado=CuentaLocal.Estado.PENDIENTE).order_by(
            "creada_en"
        )
        paginator = Paginator(pendientes, 25)
        page = paginator.get_page(request.GET.get("page"))

        form = DecisionForm(request.POST)
        if form.is_valid():
            try:
                cuenta = decidir_cuenta(
                    actor=actor,
                    cuenta_id=form.cleaned_data["cuenta_id"],
                    aprobar=(form.cleaned_data["accion"] == "APROBAR"),
                    motivo=form.cleaned_data["motivo"],
                )
                resultado = (
                    "aprobada" if cuenta.estado == CuentaLocal.Estado.APROBADA else "rechazada"
                )
                messages.success(request, f"Solicitud de {cuenta.nombre_completo} {resultado}.")
                return redirect("cuentas:altas")
            except (ValidationError, PermissionDenied) as exc:
                msg = exc.messages[0] if hasattr(exc, "messages") and exc.messages else str(exc)
                return render(
                    request,
                    "cuentas/altas.html",
                    {
                        "actor": actor,
                        "cuentas": page,
                        "error": msg,
                        "form": form,
                        "acceso_local": True,
                    },
                    status=400,
                )

        error_msg = " ".join(str(error) for errores in form.errors.values() for error in errores)
        return render(
            request,
            "cuentas/altas.html",
            {
                "actor": actor,
                "cuentas": page,
                "error": error_msg,
                "form": form,
                "acceso_local": True,
            },
            status=400,
        )


class LocalPasswordResetView(LocalOnlyMixin, PasswordResetView):
    """Recuperación de contraseña con control de tasa y respuestas neutras."""

    template_name = "cuentas/formulario.html"
    form_class = RecuperacionLocalForm
    token_generator = token_recuperacion_local
    success_url = reverse_lazy("cuentas:recuperar_enviado")
    email_template_name = "cuentas/email_reset.txt"
    subject_template_name = "cuentas/asunto_reset.txt"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Recuperar contraseña"
        context["submit_label"] = "Enviar instrucciones"
        context["acceso_local"] = True
        context["introduccion"] = (
            "Ingrese su correo electrónico registrado para recibir las "
            "instrucciones de recuperación."
        )
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        ip = request.META.get("REMOTE_ADDR") or "127.0.0.1"
        dest_raw = normalizar_correo(request.POST.get("email", ""))

        if not limitar(f"reset-ip:{ip}", maximo=10, segundos=300) or (
            dest_raw and not limitar(f"reset-dest:{dest_raw}", maximo=10, segundos=300)
        ):
            form = self.get_form()
            form.add_error(None, "Se ha superado el límite de intentos. Intente más tarde.")
            response = self.form_invalid(form)
            response.status_code = 400
            return response

        return super().post(request, *args, **kwargs)

    def form_valid(self, form: Any) -> HttpResponse:
        try:
            return super().form_valid(form)
        except Exception as exc:
            logger.warning("Fallo al enviar correo de recuperación: %s", type(exc).__name__)
            return redirect(self.get_success_url())


class RecuperarEnviadoView(LocalOnlyMixin, TemplateView):
    """Confirmación neutra tras solicitar la recuperación de contraseña."""

    template_name = "cuentas/estado.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Revisá tu correo"
        context["modo"] = "recuperar_enviado"
        context["mensaje"] = (
            "Si la cuenta puede recuperar el acceso, recibirás instrucciones. "
            "Si no llegan, intentá nuevamente más tarde."
        )
        context["acceso_local"] = True
        return context


class LocalPasswordResetConfirmView(LocalOnlyMixin, PasswordResetConfirmView):
    """Establecimiento de nueva contraseña con validación de estado de cuenta local."""

    template_name = "cuentas/formulario.html"
    token_generator = token_recuperacion_local
    success_url = reverse_lazy("cuentas:reset_completo")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Restablecer contraseña"
        context["submit_label"] = "Guardar nueva contraseña"
        context["acceso_local"] = True
        return context

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        response = super().dispatch(request, *args, **kwargs)
        if 300 <= response.status_code < 400 or response.has_header("Location"):
            return response

        if not self.validlink:
            err_resp = render(
                request,
                "cuentas/estado.html",
                {
                    "title": "Enlace no válido",
                    "modo": "error",
                    "mensaje": (
                        "El enlace de recuperación es inválido o ha vencido. "
                        "Puede solicitar un nuevo enlace desde la sección de recuperación."
                    ),
                    "acceso_local": True,
                },
                status=400,
            )
            add_never_cache_headers(err_resp)
            err_resp["Referrer-Policy"] = "no-referrer"
            return err_resp
        return response

    def form_valid(self, form: Any) -> HttpResponse:
        if not (
            self.user
            and self.user.is_active
            and CuentaLocal.objects.filter(
                user_id=self.user.pk,
                email_verificado_en__isnull=False,
                estado=CuentaLocal.Estado.APROBADA,
            ).exists()
        ):
            form.add_error(None, "La cuenta no cumple las condiciones para restablecer contraseña.")
            response = self.form_invalid(form)
            response.status_code = 400
            return response

        return super().form_valid(form)


class ResetCompletoView(LocalOnlyMixin, TemplateView):
    """Confirmación de restablecimiento exitoso de contraseña."""

    template_name = "cuentas/estado.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Contraseña restablecida"
        context["modo"] = "reset_completo"
        context["mensaje"] = (
            "Su contraseña ha sido restablecida correctamente. "
            "Ya puede ingresar con su nueva clave."
        )
        context["acceso_local"] = True
        return context


class LocalPasswordChangeView(LocalOnlyMixin, PasswordChangeView):
    """Cambio voluntario de contraseña autenticado con invalidación de sesiones previas."""

    template_name = "cuentas/formulario.html"
    success_url = reverse_lazy("cuentas:clave_cambiada")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["old_password"].label = "Contraseña actual"
        return form

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Cambiar contraseña"
        context["submit_label"] = "Guardar nueva contraseña"
        context["acceso_local"] = True
        context["actor"] = resolve_actor(self.request)
        return context

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not getattr(settings, "LOCAL_IDENTITY_ENABLED", False):
            raise Http404("El acceso local no se encuentra habilitado.")
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("cuentas:login"))

        cuenta = CuentaLocal.objects.filter(user_id=request.user.pk).first()
        if cuenta is None or not request.user.is_active:
            raise PermissionDenied("Acceso restringido a cuentas locales activas.")

        return super().dispatch(request, *args, **kwargs)


class ClaveCambiadaView(LocalOnlyMixin, TemplateView):
    """Confirmación de contraseña actualizada."""

    template_name = "cuentas/estado.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Contraseña actualizada"
        context["modo"] = "clave_cambiada"
        context["mensaje"] = "Su contraseña ha sido modificada con éxito."
        context["acceso_local"] = True
        return context
