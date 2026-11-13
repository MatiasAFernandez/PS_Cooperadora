"""Consulta y edición administrativa de cuentas locales (SPEC-023 / SPEC-024)."""

import urllib.parse
from typing import Any, cast

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.views.generic import View

from identidad.actividad_usuarios import cambiar_actividad_cuenta
from identidad.datos_usuarios import editar_datos_cuenta
from identidad.forms_usuarios import ActividadCuentaForm, EdicionDatosCuentaForm
from identidad.models import (
    CambioActividadCuentaLocal,
    CambioDatosCuentaLocal,
    CuentaLocal,
)
from identidad.services import Actor, has_capability, resolve_actor
from identidad.views_local import LocalOnlyMixin

CAPACIDAD_ADMINISTRAR = "identidad.administrar_cuentas"
TAMANIO_PAGINA = 25
TAMANIO_HISTORIAL = 10

ETIQUETAS_CAMPOS: dict[str, str] = {
    "nombre_completo": "Nombre completo",
    "area_habitual": "Área habitual",
    "cuit_cuil": "CUIT / CUIL",
    "legajo": "Legajo",
}


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


def _extraer_listado_query(request: HttpRequest) -> str:
    """Reusar los filtros y la página normalizados del listado para enlaces de retorno."""
    form = FiltrosUsuariosForm(request.GET)
    datos = form.cleaned_data if form.is_valid() else {}
    pagina_solicitada = request.GET.get("page", "")
    pagina = (
        int(pagina_solicitada)
        if pagina_solicitada.isdigit() and int(pagina_solicitada) > 0
        else None
    )
    return _query_normalizado(datos, pagina)


def _serializar_historial(eventos: Any) -> list[dict[str, Any]]:
    """Convertir eventos de cambio en filas simples con etiquetas humanas."""
    filas: list[dict[str, Any]] = []
    for evento in eventos:
        cambios_fila: list[dict[str, str]] = []
        if isinstance(evento.cambios, dict):
            for campo, etiqueta in ETIQUETAS_CAMPOS.items():
                detalle = evento.cambios.get(campo)
                if isinstance(detalle, dict):
                    cambios_fila.append(
                        {
                            "etiqueta": etiqueta,
                            "anterior": str(detalle.get("anterior") or ""),
                            "nuevo": str(detalle.get("nuevo") or ""),
                        }
                    )
        autor_nombre = ""
        if evento.autor:
            autor_nombre = evento.autor.get_full_name() or evento.autor.username
        filas.append(
            {
                "fecha": evento.fecha,
                "autor": autor_nombre or "Sin informar",
                "cambios": cambios_fila,
            }
        )
    return filas


class UsuarioDetalleView(LocalOnlyMixin, View):
    """Ficha de consulta de una cuenta local, sin admitir destinos externos."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor = _autorizar(request)
        listado_query = _extraer_listado_query(request)

        cuenta = get_object_or_404(_cuentas_base(), pk=pk)
        eventos_qs = (
            CambioDatosCuentaLocal.objects.filter(cuenta=cuenta)
            .select_related("autor")
            .order_by("-fecha", "-pk")
        )
        historial_page = Paginator(eventos_qs, TAMANIO_HISTORIAL).get_page(
            request.GET.get("historia_page")
        )
        actividad_qs = (
            CambioActividadCuentaLocal.objects.filter(cuenta=cuenta)
            .select_related("autor")
            .order_by("-fecha", "-pk")
        )
        actividad_page = Paginator(actividad_qs, TAMANIO_HISTORIAL).get_page(
            request.GET.get("actividad_page")
        )
        response = render(
            request,
            "cuentas/usuario_detalle.html",
            {
                "actor": actor,
                "acceso_local": True,
                "cuenta": cuenta,
                "listado_query": listado_query,
                "es_cuenta_propia": cuenta.user_id == actor.subject_id,
                "historial_page": historial_page,
                "historial_items": _serializar_historial(historial_page),
                "actividad_page": actividad_page,
            },
        )
        add_never_cache_headers(response)
        return response


class UsuarioEditarView(LocalOnlyMixin, View):
    """Edición administrativa de datos básicos de una cuenta local (SPEC-024)."""

    http_method_names = ["get", "post"]

    def _render_formulario(
        self,
        request: HttpRequest,
        *,
        actor: Actor,
        cuenta: CuentaLocal,
        form: EdicionDatosCuentaForm,
        listado_query: str,
        status: int = 200,
        mostrar_recarga: bool = False,
    ) -> HttpResponse:
        response = render(
            request,
            "cuentas/usuario_editar.html",
            {
                "actor": actor,
                "acceso_local": True,
                "cuenta": cuenta,
                "form": form,
                "listado_query": listado_query,
                "mostrar_recarga": mostrar_recarga,
            },
            status=status,
        )
        add_never_cache_headers(response)
        return response

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor = _autorizar(request)
        cuenta = get_object_or_404(_cuentas_base(), pk=pk)
        listado_query = _extraer_listado_query(request)
        form = EdicionDatosCuentaForm(instance=cuenta)
        return self._render_formulario(
            request,
            actor=actor,
            cuenta=cuenta,
            form=form,
            listado_query=listado_query,
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor = _autorizar(request)
        cuenta = get_object_or_404(_cuentas_base(), pk=pk)
        listado_query = _extraer_listado_query(request)
        form = EdicionDatosCuentaForm(request.POST, instance=cuenta)

        if not form.is_valid():
            return self._render_formulario(
                request,
                actor=actor,
                cuenta=cuenta,
                form=form,
                listado_query=listado_query,
                status=400,
            )

        try:
            cuenta_actualizada, evento = editar_datos_cuenta(
                actor,
                cuenta.pk,
                form.cleaned_data,
                form.cleaned_data["referencia"],
            )
        except ValidationError as exc:
            for mensaje in exc.messages:
                form.add_error(None, mensaje)
            es_conflicto = any(
                "cambiaron desde que abrió el formulario" in mensaje
                for mensaje in exc.messages
            )
            return self._render_formulario(
                request,
                actor=actor,
                cuenta=cuenta,
                form=form,
                listado_query=listado_query,
                status=409 if es_conflicto else 400,
                mostrar_recarga=True,
            )

        if evento is not None:
            messages.success(request, "Se guardaron los cambios en los datos de la cuenta.")
        else:
            messages.info(request, "Sin cambios.")

        destino = reverse("cuentas:usuario_detalle", args=[cuenta_actualizada.pk])
        if listado_query:
            destino = f"{destino}?{listado_query}"
        response = redirect(destino)
        add_never_cache_headers(response)
        return response


class UsuarioActividadView(LocalOnlyMixin, View):
    """Confirmación y ejecución de desactivación o reactivación local (SPEC-025)."""

    http_method_names = ["get", "post"]

    def _accion_activar(self, form: ActividadCuentaForm, cuenta: CuentaLocal) -> bool:
        valor = form["activar"].value()
        if valor == "true":
            return True
        if valor == "false":
            return False
        return not bool(cuenta.user.is_active)

    def _render_formulario(
        self,
        request: HttpRequest,
        *,
        actor: Actor,
        cuenta: CuentaLocal,
        form: ActividadCuentaForm,
        listado_query: str,
        status: int = 200,
        mostrar_recarga: bool = False,
    ) -> HttpResponse:
        response = render(
            request,
            "cuentas/usuario_actividad.html",
            {
                "actor": actor,
                "acceso_local": True,
                "cuenta": cuenta,
                "form": form,
                "listado_query": listado_query,
                "accion_activar": self._accion_activar(form, cuenta),
                "es_cuenta_propia": cuenta.user_id == actor.subject_id,
                "mostrar_recarga": mostrar_recarga,
            },
            status=status,
        )
        add_never_cache_headers(response)
        return response

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor = _autorizar(request)
        cuenta = get_object_or_404(_cuentas_base(), pk=pk)
        listado_query = _extraer_listado_query(request)
        actividad_actual = bool(cuenta.user.is_active)
        form = ActividadCuentaForm(
            initial={
                "activar": "false" if actividad_actual else "true",
                "actividad_esperada": "true" if actividad_actual else "false",
            }
        )
        return self._render_formulario(
            request,
            actor=actor,
            cuenta=cuenta,
            form=form,
            listado_query=listado_query,
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        actor = _autorizar(request)
        cuenta = get_object_or_404(_cuentas_base(), pk=pk)
        listado_query = _extraer_listado_query(request)
        form = ActividadCuentaForm(request.POST)

        if not form.is_valid():
            return self._render_formulario(
                request,
                actor=actor,
                cuenta=cuenta,
                form=form,
                listado_query=listado_query,
                status=400,
            )

        try:
            cuenta_actualizada, evento = cambiar_actividad_cuenta(
                actor,
                cuenta.pk,
                form.cleaned_data["activar"],
                form.cleaned_data["motivo"],
                form.cleaned_data["actividad_esperada"],
            )
        except ValidationError as exc:
            for mensaje in exc.messages:
                form.add_error(None, mensaje)
            es_conflicto = any(
                "cambió desde que abrió la confirmación" in mensaje
                for mensaje in exc.messages
            )
            return self._render_formulario(
                request,
                actor=actor,
                cuenta=cuenta,
                form=form,
                listado_query=listado_query,
                status=409 if es_conflicto else 400,
                mostrar_recarga=es_conflicto,
            )

        if evento is not None:
            if evento.actividad_nueva:
                messages.success(request, "Cuenta marcada como Activa.")
            else:
                messages.success(request, "Cuenta marcada como Desactivada.")
        else:
            messages.info(request, "Sin cambios.")

        destino = reverse("cuentas:usuario_detalle", args=[cuenta_actualizada.pk])
        if listado_query:
            destino = f"{destino}?{listado_query}"
        response = redirect(destino)
        add_never_cache_headers(response)
        return response
