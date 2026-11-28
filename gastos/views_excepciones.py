"""Búsqueda, gestión e historial de excepciones por urgencia."""

from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q, Value
from django.db.models.functions import Concat
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from gastos.excepciones_deuda import (
    DIAS_VIGENCIA_SUGERIDA,
    MAX_CARACTERES_MOTIVO,
    excepcion_deuda_vigente,
    otorgar_excepcion_deuda,
    puede_gestionar_excepciones_deuda,
    puede_recibir_excepcion_deuda,
    revocar_excepcion_deuda,
)
from gastos.models import ExcepcionDeudaDocumental
from gastos.views import _enforce_actor
from identidad.services import usuarios_con_capacidad


class MotivoExcepcionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo",
        label_suffix="",
        max_length=MAX_CARACTERES_MOTIVO,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class OtorgarExcepcionForm(MotivoExcepcionForm):
    field_order = ("vence_en", "motivo")

    vence_en = forms.DateTimeField(
        label="Vence el",
        label_suffix="",
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        help_text=(
            f"La vigencia sugerida es de {DIAS_VIGENCIA_SUGERIDA} días. "
            "Usá la hora de Argentina."
        ),
    )

    def clean_vence_en(self):
        vence_en = self.cleaned_data["vence_en"]
        if vence_en <= timezone.now():
            raise ValidationError("Elegí una fecha y hora de vencimiento futuras.")
        return vence_en


class RevocarExcepcionForm(MotivoExcepcionForm):
    excepcion_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


def _titulares_excepciones():
    ids_capacidad = usuarios_con_capacidad("gastos.presentar").values("pk")
    tiene_historial = Exists(ExcepcionDeudaDocumental.objects.filter(titular_id=OuterRef("pk")))
    return (
        get_user_model()
        .objects.select_related("cuenta_local")
        .filter(Q(pk__in=ids_capacidad) | Q(tiene_historial))
    )


class GestionExcepcionesView(View):
    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        actor = _enforce_actor(request)
        if isinstance(actor, HttpResponse):
            return actor
        if not puede_gestionar_excepciones_deuda(actor):
            raise PermissionDenied("No tenés permiso para gestionar excepciones de Gastos.")
        self.actor = actor
        return super().dispatch(request, *args, **kwargs)


class TitularesExcepcionView(GestionExcepcionesView):
    def get(self, request: HttpRequest) -> HttpResponse:
        consulta = request.GET.get("q", "").strip()[:150]
        titulares = _titulares_excepciones().none()
        if consulta:
            titulares = (
                _titulares_excepciones()
                .alias(nombre=Concat("first_name", Value(" "), "last_name"))
                .filter(
                    Q(nombre__icontains=consulta)
                    | Q(username__icontains=consulta)
                    | Q(email__icontains=consulta)
                    | Q(cuenta_local__nombre_completo__icontains=consulta)
                    | Q(cuenta_local__email__icontains=consulta)
                )
                .order_by("last_name", "first_name", "username", "pk")
            )
        pagina = Paginator(titulares, 25).get_page(request.GET.get("page"))
        return render(
            request,
            "gastos/excepciones_urgencia.html",
            {"actor": self.actor, "consulta": consulta, "pagina": pagina},
        )


class ExcepcionTitularView(GestionExcepcionesView):
    def get(self, request: HttpRequest, titular_id: int) -> HttpResponse:
        titular = get_object_or_404(_titulares_excepciones(), pk=titular_id)
        return self._render(request, titular)

    def post(self, request: HttpRequest, titular_id: int) -> HttpResponse:
        titular = get_object_or_404(_titulares_excepciones(), pk=titular_id)
        accion = request.POST.get("accion")
        if accion == "otorgar":
            form = OtorgarExcepcionForm(request.POST)
            aplicar = otorgar_excepcion_deuda
            confirmacion = "Otorgaste la excepción por urgencia."
        elif accion == "revocar":
            form = RevocarExcepcionForm(request.POST)
            aplicar = revocar_excepcion_deuda
            confirmacion = "Revocaste la excepción por urgencia."
        else:
            return HttpResponseBadRequest("Seleccioná una acción válida.")

        if not form.is_valid():
            return self._render(request, titular, form=form, accion=accion, status=400)
        try:
            aplicar(actor=self.actor, titular_id=titular.pk, **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect(request.get_full_path())
        messages.success(request, confirmacion)
        parametros = request.GET.copy()
        parametros.pop("page", None)
        destino = reverse("gastos:excepcion_titular", args=[titular.pk], query=parametros)
        return redirect(destino)

    def _render(self, request, titular, *, form=None, accion=None, status=200):
        historial = ExcepcionDeudaDocumental.objects.filter(titular=titular).select_related(
            "otorgada_por", "revocada_por"
        )
        puede_recibir = puede_recibir_excepcion_deuda(titular)
        if not puede_recibir and not historial.exists():
            raise Http404
        ahora = timezone.now()
        vigente = excepcion_deuda_vigente(titular.pk, instante=ahora)
        formulario_visible = None
        if vigente is not None:
            formulario_visible = (
                form
                if accion == "revocar"
                else RevocarExcepcionForm(initial={"excepcion_id": vigente.pk})
            )
        elif puede_recibir:
            formulario_visible = (
                form
                if accion == "otorgar"
                else OtorgarExcepcionForm(
                    initial={"vence_en": ahora + timedelta(days=DIAS_VIGENCIA_SUGERIDA)}
                )
            )
        return render(
            request,
            "gastos/excepcion_titular.html",
            {
                "actor": self.actor,
                "titular": titular,
                "consulta": request.GET.get("q", "").strip()[:150],
                "vigente": vigente,
                "form": formulario_visible,
                "error_accion_no_disponible": form is not None and form is not formulario_visible,
                "historial": Paginator(historial, 10).get_page(request.GET.get("page")),
            },
            status=status,
        )
