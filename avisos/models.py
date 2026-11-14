"""Modelos persistentes para avisos web internos."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse


class TipoAviso(models.TextChoices):
    """Tipos de aviso web soportados."""

    NUEVA_SOLICITUD_GASTO = "nueva_solicitud_gasto", "Nueva solicitud de gasto"
    DECISION_SOLICITUD_GASTO = "decision_solicitud_gasto", "Decisión sobre solicitud de gasto"
    PAGO_EXTERNO_REGISTRADO = "pago_externo_registrado", "Pago externo registrado"


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
    decision_id = models.PositiveBigIntegerField(null=True, blank=True)
    evento_pago_id = models.PositiveBigIntegerField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    leida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada_en", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["destinatario", "tipo", "solicitud_id"],
                condition=Q(decision_id__isnull=True, evento_pago_id__isnull=True),
                name="unique_aviso_destinatario_tipo_solicitud",
            ),
            models.UniqueConstraint(
                fields=["destinatario", "tipo", "decision_id"],
                condition=Q(decision_id__isnull=False),
                name="unique_aviso_destinatario_tipo_decision",
            ),
            models.UniqueConstraint(
                fields=["destinatario", "tipo", "evento_pago_id"],
                condition=Q(evento_pago_id__isnull=False),
                name="unique_aviso_destinatario_tipo_evento_pago",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
                        decision_id__isnull=True,
                        evento_pago_id__isnull=True,
                    )
                    | Q(
                        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
                        decision_id__isnull=False,
                        evento_pago_id__isnull=True,
                    )
                    | Q(
                        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
                        decision_id__isnull=True,
                        evento_pago_id__isnull=False,
                    )
                    | ~Q(
                        tipo__in=[
                            TipoAviso.NUEVA_SOLICITUD_GASTO,
                            TipoAviso.DECISION_SOLICITUD_GASTO,
                            TipoAviso.PAGO_EXTERNO_REGISTRADO,
                        ]
                    )
                ),
                name="check_aviso_tipo_fuente_coherente",
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
        if self.decision_id is not None:
            return (
                f"Aviso #{self.pk} ({self.tipo}) -> "
                f"solicitud #{self.solicitud_id} decisión #{self.decision_id}"
            )
        if self.evento_pago_id is not None:
            return (
                f"Aviso #{self.pk} ({self.tipo}) -> "
                f"solicitud #{self.solicitud_id} evento_pago #{self.evento_pago_id}"
            )
        return f"Aviso #{self.pk} ({self.tipo}) -> solicitud #{self.solicitud_id}"


class EstadoIntencionCorreo(models.TextChoices):
    """Estados operativos de una intención de envío de correo."""

    PENDIENTE = "pendiente", "Pendiente"
    EN_PROCESO = "en_proceso", "En proceso"
    ACEPTADO = "aceptado", "Aceptado por el servidor"
    FALLIDO = "fallido", "Fallido"
    OMITIDO = "omitido", "Omitido"
    INCIERTO = "incierto", "Incierto"


class IntencionCorreo(models.Model):
    """Intención de envío de correo electrónico vinculada uno a uno a un aviso web."""

    aviso = models.OneToOneField(
        Aviso,
        on_delete=models.CASCADE,
        related_name="intencion_correo",
    )
    estado = models.CharField(
        max_length=20,
        choices=EstadoIntencionCorreo.choices,
        default=EstadoIntencionCorreo.PENDIENTE,
    )
    intentos = models.PositiveIntegerField(default=0)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)
    ultimo_intento_en = models.DateTimeField(null=True, blank=True)
    aceptado_en = models.DateTimeField(null=True, blank=True)
    direccion_ultimo_intento = models.EmailField(max_length=254, blank=True, default="")
    codigo_resultado = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["pk"]
        indexes = [
            models.Index(
                fields=["estado"],
                name="idx_intencion_correo_estado",
            ),
        ]

    def __str__(self) -> str:
        return f"IntencionCorreo #{self.pk} (aviso #{self.aviso_id}, {self.estado})"
