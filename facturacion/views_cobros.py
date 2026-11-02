from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render

from documentos.policy import ArchivoInvalido

from .cobros import (
    autorizar_cobro,
    corregir_cobro,
    puede_confirmar_al_registrar,
    puede_corregir_cobro,
    registrar_cobro,
    respaldos_cobro,
    verificar_cobro,
)
from .forms_cobros import CobroForm, CorreccionCobroForm, VerificacionCobroForm
from .permissions import ObjetoNoVisibleError
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
                _errores(form, exc)
            return self.mostrar(
                request,
                solicitud,
                form,
                409 if isinstance(exc, ConflictoConcurrenciaError) else 400,
            )
        return redirect("facturacion:detalle", numero=numero)


class CorregirCobroView(FacturacionView):
    def objeto_cobro(self, numero, cobro_id):
        solicitud = autorizar_cobro(self.actor, numero)
        cobro = solicitud.cobros.filter(pk=cobro_id).first()
        if cobro is None:
            raise ObjetoNoVisibleError
        if not puede_corregir_cobro(self.actor, cobro):
            raise PermissionDenied
        return solicitud, cobro

    def mostrar(self, request, solicitud, cobro, form, status=200):
        return render(
            request,
            "facturacion/corregir_cobro.html",
            {
                "actor": self.actor,
                "solicitud": solicitud,
                "cobro": cobro,
                "form": form,
            },
            status=status,
        )

    def get(self, request, numero, cobro_id):
        solicitud, cobro = self.objeto_cobro(numero, cobro_id)
        form = CorreccionCobroForm(
            initial={
                campo: getattr(cobro, campo)
                for campo in ("medio", "numero_operacion", "fecha_operacion", "importe")
            }
        )
        return self.mostrar(request, solicitud, cobro, form)

    def post(self, request, numero, cobro_id):
        solicitud, cobro = self.objeto_cobro(numero, cobro_id)
        form = CorreccionCobroForm(request.POST, request.FILES)
        try:
            corregir_cobro(
                actor=self.actor,
                numero=numero,
                cobro_id=cobro_id,
                datos=request.POST,
                archivo=request.FILES.get("archivo"),
            )
        except (ValidationError, ArchivoInvalido, ConflictoConcurrenciaError) as exc:
            form.is_valid()
            _errores(form, exc)
            return self.mostrar(
                request,
                solicitud,
                cobro,
                form,
                409 if isinstance(exc, ConflictoConcurrenciaError) else 400,
            )
        return redirect("facturacion:detalle", numero=numero)


class VerificarCobroView(FacturacionView):
    def resolver(self, numero, cobro_id):
        solicitud = autorizar_cobro(self.actor, numero, verificar=True)
        cobro = solicitud.cobros.select_related("verificacion").filter(pk=cobro_id).first()
        if cobro is None:
            raise ObjetoNoVisibleError
        return solicitud, cobro

    def mostrar(self, request, numero, cobro_id, form, status=200):
        solicitud, cobro = self.resolver(numero, cobro_id)
        return render(
            request,
            "facturacion/verificar_cobro.html",
            {
                "actor": self.actor,
                "solicitud": solicitud,
                "cobro": cobro,
                "form": form,
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
