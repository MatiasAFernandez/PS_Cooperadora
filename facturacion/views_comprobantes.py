"""Formulario de registro externo, integrado al detalle y al layout de facturación."""

from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from documentos.policy import ArchivoInvalido

from .comprobantes import autorizar_registro, registrar_comprobante
from .forms_comprobantes import ComprobanteExternoForm
from .views import FacturacionView, _errores


class RegistrarComprobanteView(FacturacionView):
    def mostrar(self, request, solicitud, form, status=200):
        return render(
            request,
            "facturacion/comprobante_form.html",
            {
                "actor": self.actor,
                "solicitud": solicitud,
                "form": form,
                "factura": solicitud.comprobantes.filter(tipo="FACTURA").first(),
            },
            status=status,
        )

    def get(self, request, numero):
        solicitud = autorizar_registro(self.actor, numero)
        return self.mostrar(request, solicitud, ComprobanteExternoForm())

    def post(self, request, numero):
        solicitud = autorizar_registro(self.actor, numero)
        form = ComprobanteExternoForm(request.POST, request.FILES)
        try:
            registrar_comprobante(
                actor=self.actor,
                numero_publico=numero,
                datos=request.POST,
                archivo_pdf=request.FILES.get("archivo_pdf"),
            )
        except (ValidationError, ArchivoInvalido) as exc:
            form.is_valid()
            _errores(form, exc)
            return self.mostrar(request, solicitud, form, 400)
        return redirect("facturacion:detalle", numero=numero)
