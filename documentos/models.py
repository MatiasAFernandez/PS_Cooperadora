"""Metadatos documentales; el contenido vive fuera de las rutas públicas."""

from django.conf import settings
from django.db import models


class Documento(models.Model):
    # La FK concreta protege el primer consumidor. Facturación añadirá su FK
    # cuando exista el modelo de trámite; no se usa una GenericForeignKey sin FK.
    solicitud_gasto = models.ForeignKey(
        "gastos.SolicitudGasto",
        on_delete=models.PROTECT,
        related_name="documentos",
    )
    tipo = models.CharField(max_length=64)
    procedencia = models.CharField(max_length=64)
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
