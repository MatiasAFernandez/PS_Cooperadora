"""Vistas HTTP para la bandeja de avisos web internos de Gastos."""

from __future__ import annotations

from typing import cast
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from avisos.models import Aviso, TipoAviso
from avisos.permisos import (
    TIPO_EVENTO_PAGO_REGISTRADO,
    avisos_autorizados_queryset,
    puede_acceder_bandeja_avisos,
)
from gastos.models import DecisionGasto, EventoPagoExterno
from identidad.services import Actor, resolve_actor

ESTADOS_VALIDOS = ("todos", "no_leidos")
POR_PAGINA = 25


def _autorizar(request: HttpRequest) -> Actor:
    """Resolver el actor actual y exigir al menos una capacidad de consulta de Gastos."""
    actor = resolve_actor(request)
    if not puede_acceder_bandeja_avisos(actor):
        raise PermissionDenied("No posee permisos para consultar avisos de gastos.")
    return cast(Actor, actor)


def _avisos_del_actor(actor: Actor) -> QuerySet[Aviso]:
    """Devolver avisos del actor autenticado según la matriz compartida por tipo."""
    return avisos_autorizados_queryset(actor)


def _parse_page_number(raw: str | None) -> int | None:
    """Validar un número de página positivo; devuelve None si no es válido."""
    valor = (raw or "").strip()
    if len(valor) > 10 or not valor.isascii() or not valor.isdigit():
        return None
    numero = int(valor)
    return numero if numero >= 1 else None


@never_cache
@require_GET
def lista(request: HttpRequest) -> HttpResponse:
    """Bandeja personal de avisos con filtro Todos / No leídos y paginación."""
    actor = _autorizar(request)

    if "estado" in request.GET:
        estado = request.GET["estado"]
        if estado not in ESTADOS_VALIDOS:
            return render(
                request,
                "avisos/lista.html",
                {
                    "actor": actor,
                    "estado": "todos",
                    "estado_invalido": True,
                    "avisos": None,
                    "page_obj": None,
                    "total": 0,
                },
                status=400,
            )
    else:
        estado = "todos"

    qs = _avisos_del_actor(actor)
    if estado == "no_leidos":
        qs = qs.filter(leida_en__isnull=True)

    paginator = Paginator(qs, POR_PAGINA)
    page_obj = paginator.get_page(request.GET.get("page"))

    decision_ids = [
        aviso.decision_id
        for aviso in page_obj.object_list
        if aviso.tipo == TipoAviso.DECISION_SOLICITUD_GASTO and aviso.decision_id is not None
    ]
    decisiones_por_id = (
        DecisionGasto.objects.only("id", "solicitud_id", "estado_resultante", "fecha").in_bulk(
            decision_ids
        )
        if decision_ids
        else {}
    )
    evento_pago_ids = [
        aviso.evento_pago_id
        for aviso in page_obj.object_list
        if aviso.tipo == TipoAviso.PAGO_EXTERNO_REGISTRADO
        and aviso.evento_pago_id is not None
    ]
    eventos_pago_por_id = (
        {
            evento["pk"]: evento
            for evento in EventoPagoExterno.objects.filter(pk__in=evento_pago_ids).values(
                "pk", "pago__solicitud_id", "fecha_hora", "tipo_evento"
            )
        }
        if evento_pago_ids
        else {}
    )

    items_pagina: list[dict[str, object]] = []
    for aviso in page_obj.object_list:
        es_decision = aviso.tipo == TipoAviso.DECISION_SOLICITUD_GASTO
        es_pago = aviso.tipo == TipoAviso.PAGO_EXTERNO_REGISTRADO
        resultado_evento = ""
        fecha_evento = None
        if es_decision and aviso.decision_id is not None:
            decision = decisiones_por_id.get(aviso.decision_id)
            if decision is not None and decision.solicitud_id == aviso.solicitud_id:
                resultado_evento = decision.get_estado_resultante_display()
                fecha_evento = decision.fecha
        elif es_pago and aviso.evento_pago_id is not None:
            evento_pago = eventos_pago_por_id.get(aviso.evento_pago_id)
            if (
                evento_pago is not None
                and evento_pago["tipo_evento"] == TIPO_EVENTO_PAGO_REGISTRADO
                and evento_pago["pago__solicitud_id"] == aviso.solicitud_id
            ):
                fecha_evento = evento_pago["fecha_hora"]
        items_pagina.append(
            {
                "aviso": aviso,
                "es_decision": es_decision,
                "es_pago": es_pago,
                "resultado_evento": resultado_evento,
                "fecha_evento": fecha_evento,
            }
        )

    return render(
        request,
        "avisos/lista.html",
        {
            "actor": actor,
            "estado": estado,
            "estado_invalido": False,
            "avisos": items_pagina,
            "page_obj": page_obj,
            "total": paginator.count,
        },
    )


@never_cache
@require_GET
def contador(request: HttpRequest) -> JsonResponse:
    """Devolver la cantidad de avisos no leídos del actor en formato JSON."""
    actor = _autorizar(request)
    no_leidos = _avisos_del_actor(actor).filter(leida_en__isnull=True).count()
    return JsonResponse({"no_leidos": no_leidos})


@never_cache
@require_POST
def leer(request: HttpRequest, pk: int) -> HttpResponse:
    """Marcar un aviso propio como leído de forma idempotente y redirigir."""
    actor = _autorizar(request)
    aviso = get_object_or_404(_avisos_del_actor(actor), pk=pk)

    ahora = timezone.now()
    actualizados = (
        _avisos_del_actor(actor)
        .filter(pk=aviso.pk, leida_en__isnull=True)
        .update(leida_en=ahora)
    )

    if actualizados:
        messages.success(
            request,
            f"Aviso de la solicitud #{aviso.solicitud_id} marcado como leído.",
        )
    else:
        messages.info(
            request,
            f"El aviso de la solicitud #{aviso.solicitud_id} ya estaba marcado como leído.",
        )

    estado = request.POST.get("estado", "todos")
    if estado not in ESTADOS_VALIDOS:
        estado = "todos"
    page_num = _parse_page_number(request.POST.get("page"))

    params: list[tuple[str, str]] = [("estado", estado)]
    if page_num is not None and page_num > 1:
        params.append(("page", str(page_num)))

    destino = f"{reverse('avisos:lista')}?{urlencode(params)}"
    return redirect(destino)
