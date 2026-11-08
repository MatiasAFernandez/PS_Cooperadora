"""Hechos inmutables de ingreso declarado y verificación independiente."""

from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, models
from django.utils.functional import cached_property

from comunes.contracts import EventoHistorialDTO


class CobroVigenteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(sustituido=False)


class CobroExterno(models.Model):
    sustituido = models.BooleanField(default=False, editable=False)
    reemplaza = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="correccion"
    )
    motivo_correccion = models.TextField(blank=True)
    objects = CobroVigenteManager()
    todos = models.Manager()
    solicitud = models.ForeignKey(
        "facturacion.SolicitudFacturacion", on_delete=models.PROTECT, related_name="cobros"
    )
    medio = models.CharField(max_length=30)
    numero_operacion = models.CharField(max_length=100)
    fecha_operacion = models.DateField()
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    moneda = models.CharField(max_length=3, default="ARS", editable=False)
    procedencia = models.CharField(max_length=30, editable=False)
    documento = models.OneToOneField("documentos.Documento", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_registro", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["medio", "numero_operacion"],
                name="uq_cobro_operacion_global",
                condition=models.Q(sustituido=False),
            ),
            models.CheckConstraint(
                condition=models.Q(
                    importe__gte=Decimal("0.01"), importe__lte=Decimal("9999999999.99")
                ),
                name="ck_cobro_importe",
            ),
            models.CheckConstraint(condition=models.Q(moneda="ARS"), name="ck_cobro_moneda"),
            models.CheckConstraint(
                condition=models.Q(medio__in=["MERCADO_PAGO", "BNA_COMUN", "BNA_UVT", "NBCH"]),
                name="ck_cobro_medio",
            ),
            models.CheckConstraint(
                condition=models.Q(procedencia__in=["SOLICITANTE", "INTERNO_COOPERADORA"]),
                name="ck_cobro_procedencia",
            ),
        ]

    @property
    def resultado(self):
        try:
            verificacion = self.verificacion
        except VerificacionCobro.DoesNotExist:
            return "PENDIENTE"
        if hasattr(verificacion, "rectificacion"):
            return "RECTIFICADO"
        return verificacion.resultado

    @cached_property
    def cobro_original(self):
        original = self
        while original.reemplaza_id:
            original = original.reemplaza
        return original

    @cached_property
    def numero_en_solicitud(self):
        """Ordinal visible; la identidad global se conserva para URLs y relaciones."""
        original = self.cobro_original
        return (
            type(self)
            .todos.filter(solicitud_id=self.solicitud_id, reemplaza__isnull=True)
            .filter(
                models.Q(fecha_registro__lt=original.fecha_registro)
                | models.Q(fecha_registro=original.fecha_registro, pk__lte=original.pk)
            )
            .count()
        )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("El cobro registrado es inmutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("El cobro registrado es inmutable.")

    def como_historial(self, *, numero_cobro=None):
        if numero_cobro is None:
            numero_cobro = self.numero_en_solicitud
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=f"facturacion:{self.solicitud_id}",
            tipo_evento="cobro_corregido" if self.reemplaza_id else "cobro_informado",
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha_registro,
            estado_resultante="PENDIENTE",
            motivo_o_detalle=(
                f"Cobro #{numero_cobro}. {self.importe:.2f} ARS. "
                f"{self.medio}: {self.numero_operacion}. {self.motivo_correccion}"
            ),
        )


class VerificacionCobro(models.Model):
    class Resultado(models.TextChoices):
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    cobro = models.OneToOneField(
        CobroExterno, on_delete=models.PROTECT, related_name="verificacion"
    )
    resultado = models.CharField(max_length=12, choices=Resultado.choices)
    motivo = models.TextField(blank=True, max_length=2000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(resultado__in=["CONFIRMADO", "RECHAZADO"]),
                name="ck_verificacion_cobro_resultado",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("La verificación de ingreso es inmutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("La verificación de ingreso es inmutable.")

    def como_historial(self, *, numero_cobro=None):
        if numero_cobro is None:
            numero_cobro = self.cobro.numero_en_solicitud
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=f"facturacion:{self.cobro.solicitud_id}",
            tipo_evento="cobro_verificado",
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha,
            estado_resultante=self.resultado,
            motivo_o_detalle=f"Cobro #{numero_cobro}. {self.motivo}",
        )


class RectificacionCobro(models.Model):
    verificacion = models.OneToOneField(
        VerificacionCobro, on_delete=models.PROTECT, related_name="rectificacion"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField(max_length=2000)

    def como_historial(self, *, cobro, numero_cobro):
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=f"facturacion:{cobro.solicitud_id}",
            tipo_evento="cobro_rectificado",
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha,
            estado_resultante="RECTIFICADO",
            motivo_o_detalle=f"Cobro #{numero_cobro}. {self.motivo}",
        )
