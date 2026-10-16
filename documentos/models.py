"""Metadatos documentales; el contenido vive fuera de las rutas públicas."""

from django.conf import settings
from django.db import models


class Documento(models.Model):
    class Tipo(models.TextChoices):
        PRESUPUESTO = "PRESUPUESTO", "Presupuesto o proforma"
        FACTURA_PROVEEDOR = "FACTURA_PROVEEDOR", "Factura o ticket de proveedor"
        COMPROBANTE_PAGO = "COMPROBANTE_PAGO", "Comprobante de pago"
        CONSTANCIA_RETENCION_ATP = "CONSTANCIA_RETENCION_ATP", "Constancia ATP"
        FACTURA_EMITIDA = "FACTURA_EMITIDA", "Factura emitida"
        NOTA_CREDITO = "NOTA_CREDITO", "Nota de crédito"
        NOTA_DEBITO = "NOTA_DEBITO", "Nota de débito"
        COMPROBANTE_COBRO = "COMPROBANTE_COBRO", "Comprobante de cobro"

    class Procedencia(models.TextChoices):
        SOLICITANTE = "SOLICITANTE", "Solicitante"
        EXTERNO_XUBIO = "EXTERNO_XUBIO", "Xubio"
        EXTERNO_BANCO = "EXTERNO_BANCO", "Banco"
        EXTERNO_ATP = "EXTERNO_ATP", "ATP"
        INTERNO_COOPERADORA = "INTERNO_COOPERADORA", "Cooperadora"

    # La FK concreta protege el primer consumidor. Facturación añadirá su FK
    # cuando exista el modelo de trámite; no se usa una GenericForeignKey sin FK.
    solicitud_gasto = models.ForeignKey(
        "gastos.SolicitudGasto",
        on_delete=models.PROTECT,
        related_name="documentos",
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

    @property
    def referencia_tramite(self) -> str:
        return f"gastos:{self.solicitud_gasto_id}"
