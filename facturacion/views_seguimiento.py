from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render

from documentos.policy import ArchivoInvalido

from .seguimiento import (
    actualizar_respaldo,
    diagnostico,
    diagnostico_visible,
    exigir_abierta,
    puede_actualizar_respaldo,
    resolver_tramite,
    respaldo_actual,
    sucesores_respaldo,
)
from .views import FacturacionView, _mensaje_archivo
from .workflow import ConflictoConcurrenciaError


class ResolverTramiteView(FacturacionView):
    def post(self, request, numero):
        solicitud = self.objeto(numero)
        try:
            resolver_tramite(
                actor=self.actor,
                numero=numero,
                accion=request.POST.get("accion"),
                motivo=request.POST.get("motivo"),
                revision_esperada=request.POST.get("revision"),
            )
        except (ValidationError, ConflictoConcurrenciaError) as exc:
            return render(
                request,
                "facturacion/resolver_error.html",
                {
                    "actor": self.actor,
                    "solicitud": solicitud,
                    "diagnostico": diagnostico_visible(self.actor, solicitud),
                    "errores": exc.messages if isinstance(exc, ValidationError) else [str(exc)],
                    "motivo": request.POST.get("motivo", ""),
                    "accion": request.POST.get("accion", ""),
                },
                status=409 if isinstance(exc, ConflictoConcurrenciaError) else 400,
            )
        return redirect("facturacion:detalle", numero=numero)


class ActualizarRespaldoView(FacturacionView):
    def contexto(self, request, numero, clase, objeto_id):
        solicitud = self.objeto(numero)
        exigir_abierta(solicitud)
        if not puede_actualizar_respaldo(self.actor):
            raise PermissionDenied
        if clase not in {"comprobante", "cobro"}:
            from django.http import Http404

            raise Http404
        from django.http import Http404

        objeto = (
            (solicitud.comprobantes if clase == "comprobante" else solicitud.cobros)
            .filter(pk=objeto_id)
            .first()
        )
        if objeto is None:
            raise Http404
        anterior = respaldo_actual(objeto)
        if anterior is None:
            raise Http404
        opciones = sucesores_respaldo(self.actor, anterior)
        return dict(
            actor=self.actor,
            solicitud=solicitud,
            anterior=anterior,
            opciones=opciones,
            diagnostico=diagnostico(solicitud),
        )

    def get(self, request, numero, clase, objeto_id):
        if clase == "cobro":
            return redirect("facturacion:corregir_cobro", numero=numero, cobro_id=objeto_id)
        return render(
            request,
            "facturacion/actualizar_respaldo.html",
            self.contexto(request, numero, clase, objeto_id),
        )

    def post(self, request, numero, clase, objeto_id):
        contexto = self.contexto(request, numero, clase, objeto_id)
        try:
            nuevo_id = request.POST.get("nuevo_id")
            if nuevo_id and not nuevo_id.isdecimal():
                raise ValidationError("Seleccioná la versión sucesora vigente.")
            actualizar_respaldo(
                actor=self.actor,
                numero=numero,
                clase=clase,
                objeto_id=objeto_id,
                nuevo_id=int(nuevo_id) if nuevo_id else None,
                archivo=request.FILES.get("archivo"),
                motivo=request.POST.get("motivo"),
                revision_esperada=request.POST.get("revision"),
            )
        except (ValidationError, ArchivoInvalido, ConflictoConcurrenciaError) as exc:
            if isinstance(exc, ArchivoInvalido):
                contexto["error_archivo"] = _mensaje_archivo(exc, solo_pdf=clase == "comprobante")
            else:
                contexto["errores"] = (
                    exc.messages if isinstance(exc, ValidationError) else [str(exc)]
                )
            contexto.update(
                motivo=request.POST.get("motivo", ""),
                nuevo_id=request.POST.get("nuevo_id"),
            )
            return render(
                request,
                "facturacion/actualizar_respaldo.html",
                contexto,
                status=409 if isinstance(exc, ConflictoConcurrenciaError) else 400,
            )
        return redirect("facturacion:detalle", numero=numero)
