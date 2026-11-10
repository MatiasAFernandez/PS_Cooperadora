"""Declaración externa de envío y acuse voluntario, sin ejecutar correo."""

from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from comunes.models import TramiteBase

from .models import ComprobanteExterno, ConfirmacionRecepcion, EnvioComprobante
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles


class EnvioForm(forms.Form):
    enviado = forms.BooleanField(label="Ya envié este comprobante por correo", required=False)
    destinatario = forms.EmailField(label="Destinatario del envío", required=False)
    fecha_envio = forms.DateField(
        label="Fecha de envío", required=False,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    def clean(self):
        datos = super().clean()
        if datos.get("enviado"):
            for campo in ("destinatario", "fecha_envio"):
                if not datos.get(campo):
                    self.add_error(campo, "Completá este dato para informar el envío.")
            if datos.get("fecha_envio") and datos["fecha_envio"] > timezone.localdate():
                self.add_error("fecha_envio", "El envío no puede tener una fecha futura.")
        return datos


def declarar_envio(*, actor, comprobante, datos):
    from .comprobantes import autorizar_registro

    form = EnvioForm(datos)
    if not form.is_valid():
        raise ValidationError(dict(form.errors))
    if not form.cleaned_data["enviado"]:
        return None
    with transaction.atomic():
        TramiteBase.objects.select_for_update().get(pk=comprobante.solicitud.tramite_base_id)
        autorizar_registro(actor, comprobante.solicitud_id)
        actual = ComprobanteExterno.objects.filter(pk=comprobante.pk).first()
        if actual is None:
            raise ValidationError("El comprobante cambió. Recargá la solicitud.")
        fecha = form.cleaned_data["fecha_envio"]
        if fecha < actual.fecha_emision:
            raise ValidationError({"fecha_envio": "El envío no puede preceder a la emisión."})
        ultimo = actual.envios.order_by("-pk").first()
        destinatario = form.cleaned_data["destinatario"]
        if ultimo and (ultimo.fecha_envio, ultimo.destinatario) == (fecha, destinatario):
            return ultimo
        return EnvioComprobante.objects.create(
            comprobante=actual, destinatario=destinatario, fecha_envio=fecha,
            actor_id=actor.subject_id,
        )


def confirmar_recepcion(*, actor, numero, envio_id):
    with transaction.atomic():
        solicitud = filtrar_solicitudes_visibles(actor).filter(pk=numero).first()
        if solicitud is None:
            raise ObjetoNoVisibleError
        if solicitud.tramite_base.solicitante_actor_id != str(actor.subject_id):
            raise PermissionDenied(
                "Sólo el solicitante puede confirmar que recibió el comprobante."
            )
        TramiteBase.objects.select_for_update().get(pk=solicitud.tramite_base_id)
        envio = EnvioComprobante.objects.filter(
            pk=envio_id, comprobante__solicitud=solicitud
        ).first()
        if envio is None:
            raise ObjetoNoVisibleError
        return ConfirmacionRecepcion.objects.get_or_create(
            envio=envio, defaults={"actor_id": actor.subject_id}
        )[0]
