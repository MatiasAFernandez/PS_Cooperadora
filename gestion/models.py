from django.conf import settings
from django.db import IntegrityError, models


class ConfiguracionFormulario(models.Model):
    circuito = models.CharField(max_length=20, unique=True)
    revision = models.PositiveIntegerField(default=0)
    campos = models.JSONField(default=list)


class HechoInmutable(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("El registro histórico es inmutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("El registro histórico es inmutable.")


class VersionFormulario(HechoInmutable):
    configuracion = models.ForeignKey(ConfiguracionFormulario, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    campos = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["configuracion", "revision"], name="uq_version_formulario"
            )
        ]


class RespuestaFormulario(HechoInmutable):
    tramite = models.ForeignKey(
        "comunes.TramiteBase", on_delete=models.PROTECT, related_name="respuestas_formulario"
    )
    revision = models.PositiveIntegerField(default=0)
    campos = models.JSONField(default=list)
    datos = models.JSONField(default=dict)
