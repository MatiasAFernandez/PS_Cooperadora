"""Solicitud mínima y eventos propios, sin implementar transiciones de #23–#27."""

from django.conf import settings
from django.db import IntegrityError, models

from comunes.contracts import EventoHistorialDTO


class SolicitudFacturacion(models.Model):
    tramite_base = models.OneToOneField(
        "comunes.TramiteBase", on_delete=models.PROTECT, related_name="solicitud_facturacion"
    )
    estado = models.CharField(max_length=40, default="BORRADOR_TECNICO")

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            previo = type(self).objects.filter(pk=self.pk).values_list("tramite_base_id", flat=True)
            if previo.exists() and previo.get() != self.tramite_base_id:
                raise IntegrityError("La cabecera de la solicitud es inmutable.")
        super().save(*args, **kwargs)


class EventoFacturacion(models.Model):
    """Registro append-only; los servicios de #23 validarán las transiciones."""

    solicitud = models.ForeignKey(
        SolicitudFacturacion, on_delete=models.PROTECT, related_name="eventos"
    )
    tipo_evento = models.CharField(max_length=40)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    estado_resultante = models.CharField(max_length=40)
    motivo_o_detalle = models.TextField(blank=True)

    class Meta:
        ordering = ["fecha_hora", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("No se permite modificar un evento de facturación.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("No se permite borrar un evento de facturación.")

    def como_historial(self) -> EventoHistorialDTO:
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=str(self.solicitud.tramite_base.referencia),
            tipo_evento=self.tipo_evento,
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha_hora,
            estado_resultante=self.estado_resultante,
            motivo_o_detalle=self.motivo_o_detalle,
        )
