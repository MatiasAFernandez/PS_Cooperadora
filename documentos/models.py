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

    # Puente protegido de gastos hasta que Franco incorpore su OneToOne.
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
