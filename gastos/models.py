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


MENSAJE_RESPALDO_ACEPTADA = "Respaldo del gasto (presupuesto o factura): por aportar"
MENSAJE_RESPALDO_OTRAS = "No se solicita documentación en esta etapa de la demostración"


def get_mensaje_respaldo(estado: str) -> str:
    """Retorna el mensaje de documentación de respaldo para un estado según la hipótesis H4."""
    if estado == EstadoSolicitud.ACEPTADA:
        return MENSAJE_RESPALDO_ACEPTADA
    return MENSAJE_RESPALDO_OTRAS


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

    @property
    def mensaje_respaldo(self) -> str:
        """Mensaje de documentación de respaldo según hipótesis de demo H4."""
        return get_mensaje_respaldo(self.estado)


class DecisionGasto(models.Model):
    """Registro de un evento de decisión sobre una solicitud de gasto."""

    solicitud = models.ForeignKey(
        SolicitudGasto,
        on_delete=models.CASCADE,
        related_name="decisiones",
        help_text="Solicitud sobre la cual recae la decisión.",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="decisiones_gasto",
        help_text="Usuario de prueba asignado en servidor al momento de la decisión.",
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora exactas fijadas por el servidor al momento de la decisión.",
    )
    motivo = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Justificación de la decisión "
            "(obligatoria en postergación y rechazo; opcional en aceptación)."
        ),
    )
    estado_anterior = models.CharField(
        max_length=20,
        choices=EstadoSolicitud.choices,
        help_text="Estado en que se encontraba la solicitud inmediatamente antes de esta decisión.",
    )
    estado_resultante = models.CharField(
        max_length=20,
        choices=EstadoSolicitud.choices,
        help_text="Nuevo estado resultante de la solicitud tras aplicar la decisión.",
    )

    class Meta:
        verbose_name = "Decisión de gasto"
        verbose_name_plural = "Decisiones de gasto"
        ordering = ["fecha", "id"]
        indexes = [
            models.Index(fields=["solicitud", "fecha"]),
        ]

    def __str__(self) -> str:
        return f"Decisión #{self.pk} sobre Solicitud #{self.solicitud_id}: {self.estado_resultante}"
