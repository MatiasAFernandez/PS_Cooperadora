"""Consulta administrativa de cuentas locales (SPEC-023)."""

import urllib.parse
from typing import Any, cast

from django import forms
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.cache import add_never_cache_headers
from django.views.generic import View

from identidad.models import CuentaLocal
from identidad.services import Actor, has_capability, resolve_actor
from identidad.views_local import LocalOnlyMixin

CAPACIDAD_ADMINISTRAR = "identidad.administrar_cuentas"
TAMANIO_PAGINA = 25


class FiltrosUsuariosForm(forms.Form):
    """Filtros GET del listado administrativo de cuentas locales."""

    q = forms.CharField(required=False, max_length=150, strip=True, label="Buscar")
    estado = forms.ChoiceField(
        required=False,
        choices=[("", "Todas"), *CuentaLocal.Estado.choices],
        label="Aprobación",
    )
    verificado = forms.ChoiceField(
        required=False,
        choices=[("", "Todos"), ("si", "Sí"), ("no", "No")],
        label="Correo verificado",
    )
    actividad = forms.ChoiceField(
        required=False,
        choices=[("", "Todas"), ("activa", "Activa"), ("inactiva", "Inactiva")],
        label="Actividad",
    )


def _autorizar(request: HttpRequest) -> Actor:
    """Resolver el actor y exigir la capacidad administrativa antes de consultar."""
    actor = resolve_actor(request)
    if not has_capability(actor, CAPACIDAD_ADMINISTRAR):
        raise PermissionDenied("No posee capacidad para administrar cuentas.")
    return cast(Actor, actor)


def _cuentas_base() -> QuerySet[CuentaLocal]:
    """Cuentas con las relaciones que usan el listado y la ficha."""
    return CuentaLocal.objects.select_related("user", "decidida_por")


def _filtrar(cuentas: QuerySet[CuentaLocal], datos: dict[str, Any]) -> QuerySet[CuentaLocal]:
    """Aplicar cada filtro de forma independiente y ordenar de manera estable."""
    busqueda = datos.get("q") or ""
    if busqueda:
        cuentas = cuentas.filter(
            Q(nombre_completo__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(area_habitual__icontains=busqueda)
        )

    estado = datos.get("estado") or ""
    if estado:
        cuentas = cuentas.filter(estado=estado)

    verificado = datos.get("verificado") or ""
    if verificado == "si":
        cuentas = cuentas.filter(email_verificado_en__isnull=False)
    elif verificado == "no":
        cuentas = cuentas.filter(email_verificado_en__isnull=True)

    actividad = datos.get("actividad") or ""
    if actividad == "activa":
        cuentas = cuentas.filter(user__is_active=True)
    elif actividad == "inactiva":
        cuentas = cuentas.filter(user__is_active=False)

    return cuentas.order_by("nombre_completo", "pk")


def _query_normalizado(datos: dict[str, Any], pagina: int | None = None) -> str:
    """Serializar sólo filtros válidos y una página numérica, sin parámetros ajenos."""
    pares: list[tuple[str, str]] = []
    for nombre in ("q", "estado", "verificado", "actividad"):
        valor = (datos.get(nombre) or "").strip()
        if valor:
            pares.append((nombre, valor))
    if pagina is not None and pagina > 1:
        pares.append(("page", str(pagina)))
    return urllib.parse.urlencode(pares)


def _pagina(request: HttpRequest, cuentas: QuerySet[CuentaLocal]) -> Any:
    """Paginar en bloques de 25 con tolerancia a números de página inválidos."""
    return Paginator(cuentas, TAMANIO_PAGINA).get_page(request.GET.get("page"))


class UsuariosView(LocalOnlyMixin, View):
    """Listado filtrable y paginado de cuentas locales."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest) -> HttpResponse:
        actor = _autorizar(request)
        form = FiltrosUsuariosForm(request.GET)

        if not form.is_valid():
            sin_resultados = Paginator(_cuentas_base().none(), TAMANIO_PAGINA).get_page(1)
            response = render(
                request,
                "cuentas/usuarios.html",
                {
                    "actor": actor,
                    "acceso_local": True,
                    "form": form,
                    "cuentas": sin_resultados,
                    "filtros_query": "",
                    "listado_query": "",
                    "total": 0,
                },
                status=400,
            )
            add_never_cache_headers(response)
            return response

        datos = form.cleaned_data
        pagina = _pagina(request, _filtrar(_cuentas_base(), datos))
        response = render(
            request,
            "cuentas/usuarios.html",
            {
                "actor": actor,
                "acceso_local": True,
                "form": form,
                "cuentas": pagina,
                "filtros_query": _query_normalizado(datos),
                "listado_query": _query_normalizado(datos, pagina.number),
                "total": pagina.paginator.count,
            },
        )
        add_never_cache_headers(response)
        return response


class UsuarioDetalleView(LocalOnlyMixin, View):
    """Ficha de consulta de una cuenta local, sin admitir destinos externos."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor = _autorizar(request)

        form = FiltrosUsuariosForm(request.GET)
        datos = form.cleaned_data if form.is_valid() else {}
        pagina_solicitada = request.GET.get("page", "")
        pagina = (
            int(pagina_solicitada)
            if pagina_solicitada.isdigit() and int(pagina_solicitada) > 0
            else None
        )
        listado_query = _query_normalizado(datos, pagina)

        cuenta = get_object_or_404(_cuentas_base(), pk=pk)
        response = render(
            request,
            "cuentas/usuario_detalle.html",
            {
                "actor": actor,
                "acceso_local": True,
                "cuenta": cuenta,
                "listado_query": listado_query,
            },
        )
        add_never_cache_headers(response)
        return response
