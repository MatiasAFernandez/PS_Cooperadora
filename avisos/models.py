"""Modelos persistentes para avisos web internos."""

from django.conf import settings
from django.db import models
from django.urls import reverse


class TipoAviso(models.TextChoices):
    """Tipos de aviso web soportados."""

    NUEVA_SOLICITUD_GASTO = "nueva_solicitud_gasto", "Nueva solicitud de gasto"


class Aviso(models.Model):
    """Aviso web persistente por destinatario para un evento de negocio."""

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="avisos",
    )
    tipo = models.CharField(
        max_length=50,
        choices=TipoAviso.choices,
        default=TipoAviso.NUEVA_SOLICITUD_GASTO,
    )
    solicitud_id = models.PositiveBigIntegerField()
    creada_en = models.DateTimeField(auto_now_add=True)
    leida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada_en", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["destinatario", "tipo", "solicitud_id"],
                name="unique_aviso_destinatario_tipo_solicitud",
            ),
        ]
        indexes = [
            models.Index(
                fields=["destinatario", "leida_en", "creada_en"],
                name="idx_aviso_dest_leida_creada",
            ),
        ]

    def get_absolute_url(self) -> str:
        """Devuelve la ruta de servidor protegida para la solicitud asociada."""
        return reverse("gastos:detalle", kwargs={"pk": self.solicitud_id})

    def __str__(self) -> str:
        return f"Aviso #{self.pk} ({self.tipo}) -> solicitud #{self.solicitud_id}"
