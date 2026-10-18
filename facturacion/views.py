"""Pantallas Django del recorrido de facturación, con autorización también en servicios."""

import logging

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from documentos.policy import ArchivoInvalido
from documentos.services import documentos_visibles
from identidad.services import has_capability, resolve_actor

from .forms import SolicitudFacturacionForm
from .models import EstadoSolicitudFacturacion as Estado
from .permissions import (
    ObjetoNoVisibleError,
    filtrar_solicitudes_visibles,
    verificar_accion,
)
from .workflow import (
    ConflictoConcurrenciaError,
    corregir_solicitud_facturacion,
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)

logger = logging.getLogger(__name__)


class FacturacionView(View):
    def dispatch(self, request, *args, **kwargs):
        self.actor = resolve_actor(request)
        if self.actor is None:
            if settings.DEMO_IDENTITY_ENABLED:
                return redirect_to_login(request.get_full_path())
            raise PermissionDenied
        try:
            return super().dispatch(request, *args, **kwargs)
        except ObjetoNoVisibleError as exc:
            raise Http404 from exc
        except ConflictoConcurrenciaError as exc:
            return render(
                request,
                "facturacion/error.html",
                {
                    "actor": self.actor,
                    "error": str(exc),
                },
                status=409,
            )
        except (DatabaseError, OSError):
            logger.exception("Fallo de persistencia en facturación; revisar registro privado.")
            return render(
                request,
                "facturacion/error.html",
                {
                    "actor": self.actor,
                    "error": (
                        "No pudimos confirmar la operación. "
                        "Consultá el trámite antes de reintentar."
                    ),
                },
                status=503,
            )

    def objeto(self, numero):
        solicitud = filtrar_solicitudes_visibles(self.actor).filter(pk=numero).first()
        if solicitud is None:
            raise Http404
        return solicitud


def _version_post(request):
    try:
        version = int(request.POST.get("version_esperada", ""))
        if version < 1:
            raise ValueError
        return version
    except ValueError as exc:
        raise ValidationError("Falta una versión válida. Recargá el formulario.") from exc


def _errores(form, exc):
    """Combina errores del servicio sin repetir los que ya produjo el formulario."""
    if hasattr(exc, "message_dict"):
        errores = exc.message_dict
    else:
        errores = {
            NON_FIELD_ERRORS: exc.messages if isinstance(exc, ValidationError) else [str(exc)]
        }
    for field, messages in errores.items():
        destino = field if field in form.fields else None
        for mensaje in messages:
            if mensaje not in form.errors.get(destino or NON_FIELD_ERRORS, []):
                form.add_error(destino, mensaje)


def _version_visible(datos):
    """Etiquetas del formulario; el esquema JSON no forma parte de la interfaz."""
    if not datos:
        return []
    filas = []
    for campo, field in SolicitudFacturacionForm.base_fields.items():
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo == "presento_comprobante_pago":
            valor = "Sí" if valor else "No"
        elif hasattr(field, "choices"):
            valor = dict(field.choices).get(valor, valor)
        filas.append((field.label, valor))
    return filas


class ListaSolicitudesView(FacturacionView):
    def get(self, request):
        if not any(
            has_capability(self.actor, c)
            for c in (
                "facturacion.consultar_todas",
                "facturacion.consultar_propias",
            )
        ):
            raise PermissionDenied
        pagina = Paginator(
            filtrar_solicitudes_visibles(self.actor).order_by("-fecha_presentacion", "-pk"),
            25,
        ).get_page(request.GET.get("pagina"))
        return render(request, "facturacion/lista.html", {"actor": self.actor, "pagina": pagina})


class PresentarSolicitudView(FacturacionView):
    def _capacidad(self):
        if not has_capability(self.actor, "facturacion.presentar"):
            raise PermissionDenied

    def get(self, request):
        self._capacidad()
        return self.mostrar(request, SolicitudFacturacionForm(), emitir_token(self.actor))

    def mostrar(self, request, form, token, status=200):
        return render(
            request,
            "facturacion/formulario.html",
            {
                "actor": self.actor,
                "form": form,
                "token": token,
                "titulo": "Presentar solicitud",
            },
            status=status,
        )

    def post(self, request):
        self._capacidad()
        token = request.POST.get("token_presentacion", "")
        form = SolicitudFacturacionForm(request.POST, request.FILES)
        # El servicio mantiene precedencia de token antes de datos, aun si el form falla.
        try:
            solicitud = presentar_solicitud_facturacion(
                actor=self.actor,
                datos=request.POST,
                token_presentacion=token,
                archivo_comprobante=request.FILES.get("archivo_comprobante"),
            )
        except (ValidationError, ArchivoInvalido) as exc:
            form.is_valid()
            _errores(form, exc)
            return self.mostrar(request, form, token, 400)
        return redirect("facturacion:detalle", numero=solicitud.pk)


class DetalleSolicitudView(FacturacionView):
    def get(self, request, numero):
        solicitud = self.objeto(numero)
        eventos = list(solicitud.eventos.all())
        return render(
            request,
            "facturacion/detalle.html",
            {
                "actor": self.actor,
                "solicitud": solicitud,
                "historial": [e.como_historial() for e in eventos],
                "versiones": [
                    {
                        "tipo": e.tipo_evento,
                        "fecha": e.fecha_hora,
                        "antes": _version_visible(e.snapshot_datos.get("antes")),
                        "despues": _version_visible(e.snapshot_datos.get("despues")),
                    }
                    for e in eventos
                ],
                "respaldos": documentos_visibles(self.actor)
                .filter(
                    tramite_base=solicitud.tramite_base,
                    tipo="COMPROBANTE_COBRO",
                )
                .order_by("fecha_incorporacion", "pk")
                if has_capability(self.actor, "documentos.consultar_metadatos")
                else [],
                "puede_observar": has_capability(self.actor, "facturacion.observar")
                and solicitud.estado == Estado.PRESENTADA,
                "puede_corregir": has_capability(self.actor, "facturacion.corregir")
                and solicitud.tramite_base.solicitante_actor_id == str(self.actor.subject_id)
                and solicitud.estado == Estado.OBSERVADA,
                "puede_descargar": has_capability(self.actor, "documentos.recuperar_contenido"),
                "puede_ver_revision": has_capability(self.actor, "documentos.consultar_metadatos"),
            },
        )


class ObservarSolicitudView(FacturacionView):
    def post(self, request, numero):
        solicitud = self.objeto(numero)
        verificar_accion(self.actor, solicitud, "observar")
        try:
            observar_solicitud_facturacion(
                actor=self.actor,
                numero_publico=numero,
                motivo=request.POST.get("motivo", ""),
                version_esperada=_version_post(request),
            )
        except ValidationError as exc:
            return render(
                request,
                "facturacion/error.html",
                {
                    "actor": self.actor,
                    "error": " ".join(exc.messages),
                },
                status=400,
            )
        return redirect("facturacion:detalle", numero=numero)


class CorregirSolicitudView(FacturacionView):
    def _solicitud(self, numero):
        solicitud = self.objeto(numero)
        verificar_accion(self.actor, solicitud, "corregir")
        return solicitud

    def mostrar(self, request, solicitud, form, status=200):
        return render(
            request,
            "facturacion/formulario.html",
            {
                "actor": self.actor,
                "form": form,
                "titulo": "Corregir solicitud",
                "solicitud": solicitud,
            },
            status=status,
        )

    def get(self, request, numero):
        solicitud = self._solicitud(numero)
        if solicitud.estado != Estado.OBSERVADA:
            raise ConflictoConcurrenciaError("La solicitud no está observada.")
        initial = {
            name: getattr(solicitud, name)
            for name in SolicitudFacturacionForm.base_fields
            if hasattr(solicitud, name)
        }
        return self.mostrar(
            request,
            solicitud,
            SolicitudFacturacionForm(
                initial=initial,
                documento_actual=bool(solicitud.documento_comprobante_inicial_id),
            ),
        )

    def post(self, request, numero):
        solicitud = self._solicitud(numero)
        form = SolicitudFacturacionForm(
            request.POST,
            request.FILES,
            documento_actual=bool(solicitud.documento_comprobante_inicial_id),
        )
        try:
            corregir_solicitud_facturacion(
                actor=self.actor,
                numero_publico=numero,
                datos=request.POST,
                version_esperada=_version_post(request),
                nota_correccion=request.POST.get("nota_correccion", ""),
                archivo_comprobante=request.FILES.get("archivo_comprobante"),
            )
        except (ValidationError, ArchivoInvalido) as exc:
            form.is_valid()
            _errores(form, exc)
            return self.mostrar(request, solicitud, form, 400)
        return redirect("facturacion:detalle", numero=numero)
