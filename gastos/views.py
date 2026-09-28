"""Vistas para el circuito de gastos."""

from typing import Any

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from gastos.auth import has_capability, resolve_actor
from gastos.forms import DecisionGastoForm, SolicitudGastoForm
from gastos.models import EstadoSolicitud
from gastos.queries import visible_expenses
from gastos.services import (
    ConcurrencyConflictError,
    ExpenseNotFoundError,
    ExpensePermissionDeniedError,
    InvalidDecisionInputError,
    InvalidTransitionError,
    can_decide_expense,
    decide_expense,
)


def _enforce_actor(request: HttpRequest) -> Any:
    """Verifica la presencia de un actor activo.

    Si no hay actor:
    - Con demo habilitada: redirige al acceso de demo.
    - Con demo deshabilitada: deniega con 403 Forbidden sin ofrecer login.
    """
    actor = resolve_actor(request)
    if actor is not None:
        return actor

    demo_enabled = getattr(settings, "DEMO_IDENTITY_ENABLED", False)
    if demo_enabled:
        return redirect_to_login(request.get_full_path())

    raise PermissionDenied("Identidad no configurada o demo deshabilitada.")


class SolicitudGastoCreateView(View):
    """Presentación de una nueva solicitud de gasto."""

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        if not has_capability(actor, "gastos.presentar"):
            raise PermissionDenied("No posee capacidad para presentar gastos.")

        form = SolicitudGastoForm()
        return render(
            request,
            "gastos/solicitud_form.html",
            {"form": form, "actor": actor},
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        if not has_capability(actor, "gastos.presentar"):
            raise PermissionDenied("No posee capacidad para presentar gastos.")

        form = SolicitudGastoForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "gastos/solicitud_form.html",
                {"form": form, "actor": actor},
                status=200,
            )

        solicitud = form.save(commit=False)
        # Valores estrictamente fijados por el servidor (CT-06)
        solicitud.solicitante_id = actor.subject_id
        solicitud.estado = EstadoSolicitud.PRESENTADA
        solicitud.version = 0
        solicitud.save()

        return redirect(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))


class SolicitudGastoListView(View):
    """Listado de solicitudes de gasto visibles para el actor."""

    def get(self, request: HttpRequest) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        solicitudes = visible_expenses(actor)
        return render(
            request,
            "gastos/solicitud_list.html",
            {"solicitudes": solicitudes, "actor": actor},
        )


class SolicitudGastoDetailView(View):
    """Detalle de una solicitud de gasto visible para el actor."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        # Aislamiento estricto: 404 para inexistentes o ajenas no visibles
        solicitud = get_object_or_404(visible_expenses(actor), pk=pk)
        decisiones = solicitud.decisiones.select_related("autor").all()
        can_decide = any(
            can_decide_expense(actor, solicitud, act)
            for act in ("aceptar", "postergar", "rechazar")
        )
        decision_form = (
            DecisionGastoForm(initial={"version": solicitud.version})
            if can_decide
            else None
        )

        return render(
            request,
            "gastos/solicitud_detail.html",
            {
                "solicitud": solicitud,
                "actor": actor,
                "decisiones": decisiones,
                "can_decide": can_decide,
                "decision_form": decision_form,
                "mensaje_respaldo": solicitud.mensaje_respaldo,
            },
        )


class SolicitudGastoDecidirView(View):
    """Registro de la decisión humana autorizada sobre una solicitud."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        result = _enforce_actor(request)
        if isinstance(result, HttpResponse):
            return result
        actor = result

        action = request.POST.get("action")
        version = request.POST.get("version")
        motivo = request.POST.get("motivo")

        try:
            decide_expense(
                actor=actor,
                solicitud_id=pk,
                action=action,
                expected_version=version,
                motivo=motivo,
            )
            return redirect(reverse("gastos:detalle", kwargs={"pk": pk}))
        except ExpenseNotFoundError as exc:
            raise Http404("Solicitud inexistente o no visible.") from exc
        except ExpensePermissionDeniedError as exc:
            raise PermissionDenied(str(exc)) from exc
        except InvalidDecisionInputError as exc:
            solicitud = visible_expenses(actor).filter(pk=pk).first()
            if solicitud:
                decisiones = solicitud.decisiones.select_related("autor").all()
                can_decide = any(
                    can_decide_expense(actor, solicitud, act)
                    for act in ("aceptar", "postergar", "rechazar")
                )
                form = DecisionGastoForm(data=request.POST)
                form.is_valid()
                form.add_error("motivo" if "motivo" in str(exc).lower() else None, str(exc))
                return render(
                    request,
                    "gastos/solicitud_detail.html",
                    {
                        "solicitud": solicitud,
                        "actor": actor,
                        "decisiones": decisiones,
                        "can_decide": can_decide,
                        "decision_form": form,
                        "error_decision": str(exc),
                        "mensaje_respaldo": solicitud.mensaje_respaldo,
                    },
                    status=400,
                )
            return HttpResponse(str(exc), status=400)
        except (ConcurrencyConflictError, InvalidTransitionError) as exc:
            return HttpResponse(str(exc), status=409)

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        return HttpResponseNotAllowed(["POST"])
