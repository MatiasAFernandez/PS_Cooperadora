from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from .envios import EnvioForm, confirmar_recepcion, declarar_envio
from .models import ComprobanteExterno
from .permissions import ObjetoNoVisibleError
from .views import FacturacionView


class DeclararEnvioView(FacturacionView):
    def post(self, request, numero, comprobante_id):
        solicitud = self.objeto(numero)
        comprobante = ComprobanteExterno.objects.filter(
            pk=comprobante_id, solicitud=solicitud
        ).first()
        if comprobante is None:
            raise ObjetoNoVisibleError
        try:
            declarar_envio(actor=self.actor, comprobante=comprobante,
                           datos={**request.POST.dict(), "enviado": True})
        except ValidationError as exc:
            return render(request, "facturacion/envio_error.html", {
                "solicitud": solicitud, "form": EnvioForm(request.POST), "error": exc,
                "comprobante": comprobante,
            }, status=400)
        return redirect("facturacion:detalle", numero=numero)


class ConfirmarRecepcionView(FacturacionView):
    def post(self, request, numero, envio_id):
        confirmar_recepcion(actor=self.actor, numero=numero, envio_id=envio_id)
        return redirect("facturacion:detalle", numero=numero)
