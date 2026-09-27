"""Acceso local de demostración mediante las vistas de Django."""

from django.conf import settings
from django.contrib.auth.views import LoginView, LogoutView, redirect_to_login
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from identidad.services import resolve_actor


class DemoOnlyMixin:
    def dispatch(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not settings.DEMO_IDENTITY_ENABLED:
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class DemoLoginView(DemoOnlyMixin, LoginView):
    template_name = "identidad/login.html"
    redirect_authenticated_user = True


class DemoLogoutView(LogoutView):
    # La salida permanece disponible si se apaga la demo con una sesión abierta.
    next_page = "identidad:login"

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        response = super().post(request, *args, **kwargs)
        if not settings.DEMO_IDENTITY_ENABLED:
            return HttpResponse("Sesión de demostración cerrada.")
        return response


class DemoHomeView(DemoOnlyMixin, View):
    def get(self, request: HttpRequest) -> HttpResponse:
        actor = resolve_actor(request)
        if actor is None:
            return redirect_to_login(request.get_full_path())
        return render(request, "identidad/inicio.html", {"actor": actor})
