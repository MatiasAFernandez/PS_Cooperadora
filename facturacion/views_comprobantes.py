"""Formulario de registro externo, integrado al detalle y al layout de facturación."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone

from documentos.policy import ArchivoInvalido
from identidad.services import has_capability

from .comprobantes import (
    autorizar_registro,
    corregir_comprobante,
    puede_aceptar_al_registrar,
    puede_registrar_comprobante,
    registrar_comprobante,
)
from .forms_comprobantes import DATOS_COMPROBANTE, ComprobanteExternoForm, ModificarComprobanteForm
from .permissions import ObjetoNoVisibleError
from .seguimiento import (
    actualizar_respaldo,
    diagnostico,
    exigir_abierta,
    puede_actualizar_respaldo,
    respaldo_actual,
    sucesores_respaldo_comprobante,
)
from .views import FacturacionView, _errores
from .workflow import ConflictoConcurrenciaError


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
        form = ComprobanteExternoForm(
            initial={"importe": solicitud.importe_factura,
                     "destinatario": solicitud.email_envio_factura,
                     "fecha_envio": timezone.localdate()},
            puede_aceptar=puede_aceptar_al_registrar(self.actor),
        )
        return self.mostrar(request, solicitud, form)

    def post(self, request, numero):
        solicitud = autorizar_registro(self.actor, numero)
        form = ComprobanteExternoForm(
            request.POST, request.FILES, puede_aceptar=puede_aceptar_al_registrar(self.actor)
        )
        try:
            registrar_comprobante(
                actor=self.actor,
                numero_publico=numero,
                datos=request.POST,
                archivo_pdf=request.FILES.get("archivo_pdf"),
            )
        except ConflictoConcurrenciaError as exc:
            form.is_valid()
            form.add_error(None, str(exc))
            return self.mostrar(request, solicitud, form, 409)
        except (ValidationError, ArchivoInvalido) as exc:
            form.is_valid()
            _errores(form, exc, campo_archivo="archivo_pdf")
            return self.mostrar(request, solicitud, form, 400)
        return redirect("facturacion:detalle", numero=numero)


class ModificarComprobanteView(FacturacionView):
    def contexto(self, request, numero, comprobante_id):
        solicitud = self.objeto(numero)
        exigir_abierta(solicitud)
        comprobante = solicitud.comprobantes.filter(pk=comprobante_id).first()
        if comprobante is None:
            raise ObjetoNoVisibleError
        puede_corregir = puede_registrar_comprobante(self.actor)
        puede_vincular = puede_actualizar_respaldo(self.actor)
        if not (puede_corregir or puede_vincular):
            raise PermissionDenied
        anterior = respaldo_actual(comprobante)
        opciones = None
        if puede_vincular and anterior:
            opciones = sucesores_respaldo_comprobante(self.actor, anterior)
            if not puede_corregir:
                opciones = opciones.filter(procedencia=comprobante.procedencia)
        datos = (request.POST, request.FILES) if request.method == "POST" else ()
        return dict(
            actor=self.actor,
            solicitud=solicitud,
            comprobante=comprobante,
            documento_actual=(
                anterior if has_capability(self.actor, "documentos.consultar_metadatos") else None
            ),
            puede_corregir=puede_corregir,
            form=ModificarComprobanteForm(
                *datos,
                comprobante=comprobante,
                revision=diagnostico(solicitud)["revision"],
                puede_corregir=puede_corregir,
                puede_adjuntar=has_capability(self.actor, "documentos.incorporar"),
                opciones=opciones,
            ),
        )

    def get(self, request, numero, comprobante_id):
        return render(
            request,
            "facturacion/comprobante_form.html",
            self.contexto(request, numero, comprobante_id),
        )

    def post(self, request, numero, comprobante_id):
        contexto = self.contexto(request, numero, comprobante_id)
        form = contexto["form"]
        if "nuevo" not in form.fields and request.POST.get("nuevo"):
            raise PermissionDenied
        if "archivo_pdf" not in form.fields and request.FILES.get("archivo_pdf"):
            raise PermissionDenied
        if not contexto["puede_corregir"] and any(
            campo in request.POST for campo in DATOS_COMPROBANTE
        ):
            raise PermissionDenied
        status = 400
        try:
            if form.is_valid():
                self.guardar(numero, contexto)
                return redirect("facturacion:detalle", numero=numero)
        except (ValidationError, ArchivoInvalido, ConflictoConcurrenciaError) as exc:
            _errores(form, exc, campo_archivo="archivo_pdf")
            if isinstance(exc, ConflictoConcurrenciaError):
                status = 409
        return render(request, "facturacion/comprobante_form.html", contexto, status=status)

    def guardar(self, numero, contexto):
        form = contexto["form"]
        datos = form.cleaned_data
        comprobante = contexto["comprobante"]
        if datos["revision"] != form.initial["revision"]:
            raise ConflictoConcurrenciaError("El trámite cambió. Recargá el formulario.")
        nuevo = datos.get("nuevo")
        archivo = datos.get("archivo_pdf")
        if (archivo and not comprobante.documento_id) or any(
            datos[campo] != getattr(comprobante, campo) for campo in DATOS_COMPROBANTE
        ):
            corregir_comprobante(
                actor=self.actor,
                numero=numero,
                comprobante_id=comprobante.pk,
                datos=form.data,
                archivo_pdf=archivo,
            )
        elif nuevo or archivo:
            actualizar_respaldo(
                actor=self.actor,
                numero=numero,
                clase="comprobante",
                objeto_id=comprobante.pk,
                nuevo_id=nuevo.pk if nuevo else None,
                archivo=archivo,
                motivo=datos["motivo"],
                revision_esperada=datos["revision"],
            )
        else:
            raise ValidationError("Modificá algún dato o elegí un PDF.")
