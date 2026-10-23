from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render

from documentos.acceso import documentos_visibles
from documentos.policy import ArchivoInvalido
from identidad.services import has_capability

from .seguimiento import (
    actualizar_respaldo,
    diagnostico,
    diagnostico_visible,
    exigir_abierta,
    resolver_tramite,
    respaldo_actual,
)
from .views import FacturacionView
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
        if not all(
            has_capability(self.actor, c)
            for c in ("facturacion.actualizar_respaldo", "documentos.consultar_metadatos")
        ):
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
        opciones = documentos_visibles(self.actor).filter(
            serie=anterior.serie,
            tipo=anterior.tipo,
            version__gt=anterior.version,
            sucesor__isnull=True,
        )
        return dict(
            actor=self.actor,
            solicitud=solicitud,
            anterior=anterior,
            opciones=opciones,
            diagnostico=diagnostico(solicitud),
        )

    def get(self, request, numero, clase, objeto_id):
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
            contexto.update(
                errores=exc.messages if isinstance(exc, ValidationError) else [str(exc)],
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
