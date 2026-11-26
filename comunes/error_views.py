"""Vistas HTTP de error compartidas (403, 404 y 500 autosuficiente)."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseServerError
from django.shortcuts import render
from django.template.loader import render_to_string

from identidad.services import resolve_actor


def _contexto_error_seguro(request: HttpRequest) -> dict[str, object]:
    """Resuelve contexto mínimo sin fallar si la sesión o la base no responden."""
    try:
        actor = resolve_actor(request)
    except Exception:  # noqa: BLE001
        actor = None
    return {
        "actor": actor,
        "acceso_local": bool(getattr(settings, "LOCAL_IDENTITY_ENABLED", False)),
    }


def error_403(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    respuesta = render(request, "403.html", _contexto_error_seguro(request), status=403)
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


def error_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    respuesta = render(request, "404.html", _contexto_error_seguro(request), status=404)
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


def error_500(request: HttpRequest) -> HttpResponse:
    html = render_to_string("500.html")
    respuesta = HttpResponseServerError(html, content_type="text/html; charset=utf-8")
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta
