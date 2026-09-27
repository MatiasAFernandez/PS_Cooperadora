"""Modelos para el circuito de gastos."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class EstadoSolicitud(models.TextChoices):
    PRESENTADA = "presentada", "Presentada"
    ACEPTADA = "aceptada", "Aceptada"
    POSTERGADA = "postergada", "Postergada"
    RECHAZADA = "rechazada", "Rechazada"


class SolicitudGasto(models.Model):
    """Solicitud de gasto presentada ante Cooperadora."""

    concepto = models.CharField(
        max_length=255,
        help_text="Descripción o concepto de la necesidad de gasto.",
    )
    monto_estimado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Importe estimado único en ARS.",
    )
    unidad_requirente = models.CharField(
        max_length=100,
        help_text="Unidad sintética requirente de prueba.",
    )
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="solicitudes_gasto",
        help_text="Usuario solicitante asignado por el servidor.",
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora de presentación fijadas por el servidor.",
    )
    estado = models.CharField(
        max_length=20,
        choices=EstadoSolicitud.choices,
        default=EstadoSolicitud.PRESENTADA,
        help_text="Estado del trámite (inicial: presentada).",
    )
    version = models.PositiveIntegerField(
        default=0,
        help_text="Versión para control de concurrencia e historial (inicial: 0).",
    )

    class Meta:
        verbose_name = "Solicitud de gasto"
        verbose_name_plural = "Solicitudes de gasto"
        ordering = ["-fecha_creacion", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(monto_estimado__gt=0),
                name="solicitud_monto_estimado_positivo",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=0),
                name="solicitud_version_no_negativa",
            ),
        ]

    def __str__(self) -> str:
        return f"Solicitud #{self.pk} - {self.concepto} (${self.monto_estimado})"
