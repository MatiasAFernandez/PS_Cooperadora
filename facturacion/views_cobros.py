from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render

from documentos.policy import ArchivoInvalido
from documentos.revision import version_aceptada
from identidad.services import has_capability

from .cobros import (
    autorizar_cobro,
    cobro_rectificable,
    corregir_cobro,
    puede_confirmar_al_registrar,
    puede_corregir_cobro,
    rectificar_cobro,
    registrar_cobro,
    respaldos_cobro,
    verificar_cobro,
)
from .forms_cobros import DATOS_COBRO, CobroForm, ModificarCobroForm, VerificacionCobroForm
from .permissions import ObjetoNoVisibleError
from .seguimiento import (
    actualizar_respaldo,
    diagnostico,
    exigir_abierta,
    importes_cobro,
    puede_actualizar_respaldo,
    respaldo_actual,
    sucesores_respaldo_cobro,
)
from .views import FacturacionView, _errores
from .workflow import ConflictoConcurrenciaError


class RegistrarCobroView(FacturacionView):
    def mostrar(self, request, solicitud, form, status=200):
        return render(
            request,
            "facturacion/cobro_form.html",
            {
                "actor": self.actor,
                "solicitud": solicitud,
                "form": form,
            },
            status=status,
        )

    def get(self, request, numero):
        solicitud = autorizar_cobro(self.actor, numero)
        return self.mostrar(
            request,
            solicitud,
            CobroForm(
                documentos=respaldos_cobro(self.actor, solicitud),
                puede_confirmar=puede_confirmar_al_registrar(self.actor),
            ),
        )

    def post(self, request, numero):
        solicitud = autorizar_cobro(self.actor, numero)
        form = CobroForm(
            request.POST,
            request.FILES,
            documentos=respaldos_cobro(self.actor, solicitud),
            puede_confirmar=puede_confirmar_al_registrar(self.actor),
        )
        try:
            registrar_cobro(
                actor=self.actor,
                numero=numero,
                datos=request.POST,
                archivo=request.FILES.get("archivo"),
            )
        except (ValidationError, ArchivoInvalido, ConflictoConcurrenciaError) as exc:
            form.is_valid()
            if isinstance(exc, ConflictoConcurrenciaError):
                form.add_error(None, str(exc))
            else:
                _errores(form, exc, campo_archivo="archivo")
            return self.mostrar(
                request,
                solicitud,
                form,
                409 if isinstance(exc, ConflictoConcurrenciaError) else 400,
            )
        return redirect("facturacion:detalle", numero=numero)


class ModificarCobroView(FacturacionView):
    def contexto(self, request, numero, cobro_id):
        solicitud = self.objeto(numero)
        exigir_abierta(solicitud)
        cobro = solicitud.cobros.filter(pk=cobro_id).first()
        if cobro is None:
            raise ObjetoNoVisibleError
        puede_corregir = puede_corregir_cobro(self.actor, cobro)
        puede_vincular = puede_actualizar_respaldo(self.actor)
        puede_solo_documento = puede_vincular and cobro.resultado != "RECTIFICADO"
        if not (puede_corregir or puede_solo_documento):
            raise PermissionDenied
        anterior = respaldo_actual(cobro)
        datos = (request.POST, request.FILES) if request.method == "POST" else ()
        return dict(
            actor=self.actor,
            solicitud=solicitud,
            cobro=cobro,
            form=ModificarCobroForm(
                *datos,
                cobro=cobro,
                revision=diagnostico(solicitud)["revision"],
                puede_corregir=puede_corregir,
                puede_adjuntar=has_capability(self.actor, "documentos.incorporar"),
                opciones=sucesores_respaldo_cobro(self.actor, anterior) if puede_vincular else None,
            ),
            puede_corregir=puede_corregir,
            puede_solo_documento=puede_solo_documento,
            documento_actual=(
                anterior if has_capability(self.actor, "documentos.consultar_metadatos") else None
            ),
        )

    def get(self, request, numero, cobro_id):
        return render(
            request, "facturacion/corregir_cobro.html", self.contexto(request, numero, cobro_id)
        )

    def post(self, request, numero, cobro_id):
        contexto = self.contexto(request, numero, cobro_id)
        form = contexto["form"]
        if "nuevo_id" not in form.fields and request.POST.get("nuevo_id"):
            raise PermissionDenied
        if "archivo" not in form.fields and request.FILES.get("archivo"):
            raise PermissionDenied
        if not contexto["puede_corregir"] and any(campo in request.POST for campo in DATOS_COBRO):
            raise PermissionDenied
        status = 400
        try:
            if form.is_valid():
                self.guardar(numero, contexto)
                return redirect("facturacion:detalle", numero=numero)
        except (ValidationError, ArchivoInvalido, ConflictoConcurrenciaError) as exc:
            _errores(form, exc, campo_archivo="archivo")
            if isinstance(exc, ConflictoConcurrenciaError):
                status = 409
        return render(request, "facturacion/corregir_cobro.html", contexto, status=status)

    def guardar(self, numero, contexto):
        form = contexto["form"]
        d = form.cleaned_data
        cobro = contexto["cobro"]
        if d["revision"] != form.initial["revision"] or d["resultado_esperado"] != cobro.resultado:
            raise ConflictoConcurrenciaError("El trámite cambió. Recargá el formulario.")
        nuevo = d.get("nuevo_id")
        archivo = d.get("archivo")
        cambios = any(d[campo] != getattr(cobro, campo) for campo in DATOS_COBRO)
        reemplaza_documento = bool(archivo or nuevo)
        puede_reenviar = contexto["puede_corregir"] and (
            cobro.resultado == "RECHAZADO"
            or (cobro.resultado == "PENDIENTE" and not contexto["puede_solo_documento"])
        )
        if cambios or (reemplaza_documento and puede_reenviar):
            corregir_cobro(
                actor=self.actor,
                numero=numero,
                cobro_id=cobro.pk,
                datos=d,
                archivo=archivo,
                nuevo_id=nuevo.pk if nuevo else None,
                resultado_esperado=d["resultado_esperado"],
                revision_esperada=d["revision"],
            )
        elif reemplaza_documento:
            if cobro.resultado == "RECTIFICADO":
                raise ValidationError("Corregí algún dato para volver a presentar este cobro.")
            if not contexto["puede_solo_documento"]:
                raise PermissionDenied("No tenés permiso para modificar sólo el documento.")
            actualizar_respaldo(
                actor=self.actor,
                numero=numero,
                clase="cobro",
                objeto_id=cobro.pk,
                archivo=archivo,
                nuevo_id=nuevo.pk if nuevo else None,
                motivo=d["motivo"],
                revision_esperada=d["revision"],
            )
        else:
            raise ValidationError("Modificá algún dato o elegí un documento de respaldo.")


class VerificarCobroView(FacturacionView):
    def resolver(self, numero, cobro_id):
        solicitud = autorizar_cobro(self.actor, numero, verificar=True)
        cobro = (
            solicitud.cobros.select_related("verificacion__rectificacion")
            .filter(pk=cobro_id)
            .first()
        )
        if cobro is None:
            raise ObjetoNoVisibleError
        return solicitud, cobro

    def mostrar(self, request, numero, cobro_id, form, status=200):
        solicitud, cobro = self.resolver(numero, cobro_id)
        importes = importes_cobro(solicitud.comprobantes.all(), solicitud.cobros.all())
        respaldo = respaldo_actual(cobro)
        respaldo_aceptado = version_aceptada(respaldo)
        if not respaldo_aceptado:
            resultado = form.fields["resultado"]
            resultado.choices = [
                opcion for opcion in resultado.choices if opcion[0] != "CONFIRMADO"
            ]
        return render(
            request,
            "facturacion/verificar_cobro.html",
            {
                "actor": self.actor,
                "solicitud": solicitud,
                "cobro": cobro,
                "form": form,
                "respaldo_aceptado": respaldo_aceptado,
                "respaldo": respaldo
                if has_capability(self.actor, "documentos.consultar_metadatos")
                else None,
                "supera_importe_solicitado": cobro.importe > solicitud.importe_factura,
                "supera_neto": importes["hay_factura"]
                and importes["confirmado"] + cobro.importe > importes["neto"],
            },
            status=status,
        )

    def get(self, request, numero, cobro_id):
        return self.mostrar(request, numero, cobro_id, VerificacionCobroForm())

    def post(self, request, numero, cobro_id):
        self.resolver(numero, cobro_id)
        form = VerificacionCobroForm(request.POST)
        try:
            verificar_cobro(actor=self.actor, numero=numero, cobro_id=cobro_id, datos=request.POST)
        except (ValidationError, ConflictoConcurrenciaError) as exc:
            form.is_valid()
            if isinstance(exc, ValidationError):
                _errores(form, exc)
            else:
                form.add_error(None, str(exc))
            return self.mostrar(
                request,
                numero,
                cobro_id,
                form,
                409 if isinstance(exc, ConflictoConcurrenciaError) else 400,
            )
        return redirect("facturacion:detalle", numero=numero)


class RectificarCobroView(FacturacionView):
    def mostrar(self, request, numero, cobro_id, errores=()):
        solicitud = autorizar_cobro(self.actor, numero, verificar=True)
        cobro = cobro_rectificable(solicitud, cobro_id)
        return render(
            request,
            "facturacion/rectificar_cobro.html",
            {"actor": self.actor, "solicitud": solicitud, "cobro": cobro, "errores": errores},
            status=400 if errores else 200,
        )

    def get(self, request, numero, cobro_id):
        return self.mostrar(request, numero, cobro_id)

    def post(self, request, numero, cobro_id):
        try:
            rectificar_cobro(
                actor=self.actor,
                numero=numero,
                cobro_id=cobro_id,
                motivo=request.POST.get("motivo"),
            )
        except ValidationError as exc:
            return self.mostrar(request, numero, cobro_id, exc.messages)
        return redirect("facturacion:detalle", numero=numero)
