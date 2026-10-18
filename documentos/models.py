"""Metadatos documentales; el contenido vive fuera de las rutas públicas."""

import uuid

from django.conf import settings
from django.db import IntegrityError, models


class Documento(models.Model):
    class Tipo(models.TextChoices):
        PRESUPUESTO_PROFORMA = "PRESUPUESTO_PROFORMA", "Presupuesto o proforma"
        FACTURA_PROVEEDOR = "FACTURA_PROVEEDOR", "Factura de proveedor"
        TICKET_NO_FISCAL = "TICKET_NO_FISCAL", "Ticket no fiscal"
        COMPROBANTE_PAGO = "COMPROBANTE_PAGO", "Comprobante de pago"
        CONSTANCIA_RETENCION_ATP = "CONSTANCIA_RETENCION_ATP", "Constancia ATP"
        FACTURA_EMITIDA_XUBIO = "FACTURA_EMITIDA_XUBIO", "Factura emitida en Xubio"
        NOTA_CREDITO_XUBIO = "NOTA_CREDITO_XUBIO", "Nota de crédito de Xubio"
        NOTA_DEBITO_XUBIO = "NOTA_DEBITO_XUBIO", "Nota de débito de Xubio"
        COMPROBANTE_COBRO = "COMPROBANTE_COBRO", "Comprobante de cobro"

    class Procedencia(models.TextChoices):
        SOLICITANTE = "SOLICITANTE", "Solicitante"
        EXTERNO_XUBIO = "EXTERNO_XUBIO", "Xubio"
        EXTERNO_BANCO = "EXTERNO_BANCO", "Banco"
        EXTERNO_ATP = "EXTERNO_ATP", "ATP"
        INTERNO_COOPERADORA = "INTERNO_COOPERADORA", "Cooperadora"

    # Puente documental protegido de gastos, conservado por compatibilidad.
    solicitud_gasto = models.ForeignKey(
        "gastos.SolicitudGasto",
        on_delete=models.PROTECT,
        related_name="documentos",
        null=True,
        blank=True,
    )
    tramite_base = models.ForeignKey(
        "comunes.TramiteBase",
        on_delete=models.PROTECT,
        related_name="documentos",
    )
    referencia_version = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    serie = models.UUIDField(default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1, editable=False)
    reemplaza = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sucesor",
    )
    tipo = models.CharField(max_length=64, choices=Tipo.choices)
    procedencia = models.CharField(max_length=64, choices=Procedencia.choices)
    archivo = models.CharField(max_length=255, unique=True)
    nombre_original = models.CharField(max_length=255)
    formato = models.CharField(max_length=32)
    tamano = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="documentos_incorporados",
    )
    fecha_incorporacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["solicitud_gasto", "id"])]
        constraints = [
            models.UniqueConstraint(fields=["serie", "version"], name="uq_documento_serie_version"),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="ck_documento_version"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("Cada versión documental es inmutable; crear un reemplazo.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("No se permite borrar una versión documental.")

    @property
    def referencia_tramite(self) -> str:
        return str(self.tramite_base.referencia)


class RevisionDocumento(models.Model):
    """Hecho inmutable de revisión de una versión; no cambia el documento ni el trámite."""

    class Resultado(models.TextChoices):
        ACEPTADO = "ACEPTADO", "Aceptado"
        OBSERVADO = "OBSERVADO", "Observado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    documento = models.ForeignKey(Documento, on_delete=models.PROTECT, related_name="revisiones")
    resultado = models.CharField(max_length=16, choices=Resultado.choices)
    motivo = models.TextField(blank=True, max_length=2000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(resultado__in=["ACEPTADO", "OBSERVADO", "RECHAZADO"]),
                name="ck_revision_resultado",
            ),
            models.CheckConstraint(
                condition=models.Q(resultado="ACEPTADO") | ~models.Q(motivo=""),
                name="ck_revision_motivo",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("La revisión documental es inmutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("La revisión documental es inmutable.")

    def como_historial(self):
        from comunes.contracts import EventoHistorialDTO

        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=self.documento.referencia_tramite,
            tipo_evento="revision_documental",
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha,
            estado_resultante=self.resultado,
            motivo_o_detalle=(
                f"{self.documento.get_tipo_display()} — versión {self.documento.version}: "
                f"{self.get_resultado_display()}. {self.motivo}"
            ).strip(),
        )
