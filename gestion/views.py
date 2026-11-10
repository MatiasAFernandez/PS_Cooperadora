from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from facturacion.views import FacturacionView
from identidad.services import has_capability

from .formularios import CIRCUITOS, CampoEdicionForm, esquema_editor, guardar_campo
from .reportes import reporte_facturacion


class ConfiguracionView(FacturacionView):
    def comprobar(self, circuito):
        if not has_capability(self.actor, "gestion.configurar"):
            raise PermissionDenied
        if circuito not in dict(CIRCUITOS):
            raise Http404

    def get(self, request, circuito="GASTO"):
        self.comprobar(circuito)
        revision, campos = esquema_editor(circuito)
        extra = {}
        if circuito == "GASTO":
            from gastos.views import contexto_catalogos

            extra = contexto_catalogos(self.actor)
            extra.pop("actor")
        return render(
            request,
            "gestion/configuracion.html",
            dict(
                actor=self.actor,
                circuito=circuito,
                revision=revision,
                campos=campos,
                **extra,
            ),
        )


class CampoView(ConfiguracionView):
    def mostrar(self, request, circuito, clave, form, status=200):
        return render(
            request,
            "gestion/campo.html",
            dict(
                actor=self.actor,
                circuito=circuito,
                clave=clave,
                form=form,
            ),
            status=status,
        )

    def get(self, request, circuito, clave=None):
        self.comprobar(circuito)
        if clave and not any(c["clave"] == clave for c in esquema_editor(circuito)[1]):
            raise Http404
        return self.mostrar(
            request, circuito, clave, CampoEdicionForm(circuito=circuito, clave=clave)
        )

    def post(self, request, circuito, clave=None):
        self.comprobar(circuito)
        form = CampoEdicionForm(request.POST, circuito=circuito, clave=clave)
        try:
            guardar_campo(self.actor, circuito, clave, request.POST)
        except ValidationError as exc:
            form.is_valid()
            if hasattr(exc, "message_dict"):
                for campo, errores in exc.message_dict.items():
                    for error in errores:
                        form.add_error(campo if campo in form.fields else None, error)
            else:
                form.add_error(None, " ".join(exc.messages))
            return self.mostrar(request, circuito, clave, form, 400)
        return redirect("gestion:configuracion", circuito=circuito)


class ReporteFacturacionView(FacturacionView):
    def get(self, request):
        if not has_capability(self.actor, "facturacion.consultar_todas"):
            raise PermissionDenied
        try:
            orden = request.GET.get("orden", "cantidad")
            if orden not in {"cantidad", "solicitado", "neto"}:
                raise ValueError
            anio = int(request.GET.get("anio", timezone.localdate().year))
            if not 2000 <= anio <= 2100:
                raise ValueError
            cuatrimestre = (
                int(request.GET["cuatrimestre"]) if request.GET.get("cuatrimestre") else None
            )
            if cuatrimestre is not None and cuatrimestre not in {1, 2, 3}:
                raise ValueError
        except (ValueError, TypeError):
            return render(
                request,
                "gestion/reporte_facturacion.html",
                dict(
                    actor=self.actor,
                    error="Revisá el año (2000–2100) y el cuatrimestre.",
                ),
                status=400,
            )
        return render(
            request,
            "gestion/reporte_facturacion.html",
            dict(
                actor=self.actor,
                anio=anio,
                cuatrimestre=cuatrimestre,
                reporte=reporte_facturacion(anio, cuatrimestre, orden),
                orden=orden,
            ),
        )
