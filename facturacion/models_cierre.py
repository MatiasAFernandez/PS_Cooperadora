"""Actualización documental explícita, sin reescribir comprobantes ni cobros."""

from django.conf import settings
from django.db import IntegrityError, models

from comunes.contracts import EventoHistorialDTO


class ActualizacionRespaldo(models.Model):
    comprobante = models.ForeignKey(
        "facturacion.ComprobanteExterno",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="actualizaciones_respaldo",
    )
    cobro = models.ForeignKey(
        "facturacion.CobroExterno",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="actualizaciones_respaldo",
    )
    anterior = models.ForeignKey("documentos.Documento", on_delete=models.PROTECT, related_name="+")
    nuevo = models.ForeignKey("documentos.Documento", on_delete=models.PROTECT, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    motivo = models.TextField(max_length=2000)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(comprobante__isnull=False, cobro__isnull=True)
                | models.Q(comprobante__isnull=True, cobro__isnull=False),
                name="ck_actualizacion_objeto",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("La actualización documental es inmutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("La actualización documental es inmutable.")

    def como_historial(self):
        objeto = self.comprobante if self.comprobante_id else self.cobro
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=f"facturacion:{objeto.solicitud_id}",
            tipo_evento="actualizacion_respaldo",
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha,
            estado_resultante="ACTUALIZADO",
            motivo_o_detalle=(
                f"{'Comprobante' if self.comprobante_id else 'Cobro'} #{objeto.pk}. "
                f"Respaldo #{self.anterior_id} → #{self.nuevo_id}. {self.motivo}"
            ),
        )
