"""Modelos para la gestión de cuentas e identidades locales."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class CuentaLocal(models.Model):
    """Cuenta de usuario local para acceso sin proveedor externo."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cuenta_local",
    )
    email = models.EmailField(max_length=254)
    nombre_completo = models.CharField(max_length=150)
    area_habitual = models.CharField(max_length=150, blank=True)
    cuit_cuil = models.CharField(max_length=20, blank=True)
    legajo = models.CharField(max_length=50, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    email_verificado_en = models.DateTimeField(null=True, blank=True)
    nonce_verificacion = models.UUIDField(default=uuid.uuid4)
    ultimo_envio = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    decidida_en = models.DateTimeField(null=True, blank=True)
    decidida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="altas_decididas",
    )
    motivo = models.TextField(max_length=2000, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="unique_cuenta_local_lower_email",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_estado_display()})"


class LimiteAcceso(models.Model):
    """Registro para limitación de tasa de operaciones sin infraestructura externa."""

    clave = models.CharField(max_length=64, unique=True)
    inicio = models.DateTimeField()
    intentos = models.PositiveIntegerField(default=1)

    def __str__(self) -> str:
        return f"LimiteAcceso({self.clave[:8]}...: {self.intentos})"


class CambioDatosCuentaLocal(models.Model):
    """Registro de cambios administrativos sobre datos básicos de una cuenta local."""

    cuenta = models.ForeignKey(
        CuentaLocal,
        on_delete=models.PROTECT,
        related_name="cambios_datos",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cambios_datos_realizados",
    )
    fecha = models.DateTimeField(auto_now_add=True)
    cambios = models.JSONField()

    class Meta:
        ordering = ["-fecha", "-pk"]

    def __str__(self) -> str:
        return f"CambioDatosCuentaLocal(cuenta={self.cuenta_id}, fecha={self.fecha})"


class CambioActividadCuentaLocal(models.Model):
    """Registro de desactivaciones y reactivaciones administrativas de una cuenta local."""

    cuenta = models.ForeignKey(
        CuentaLocal,
        on_delete=models.PROTECT,
        related_name="cambios_actividad",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cambios_actividad_realizados",
    )
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField(max_length=2000)
    actividad_anterior = models.BooleanField()
    actividad_nueva = models.BooleanField()

    class Meta:
        ordering = ["-fecha", "-pk"]

    def __str__(self) -> str:
        return (
            f"CambioActividadCuentaLocal(cuenta={self.cuenta_id}, "
            f"{self.actividad_anterior}->{self.actividad_nueva}, fecha={self.fecha})"
        )


class CambioPerfilesCuentaLocal(models.Model):
    """Registro de cambios administrativos sobre perfiles gestionados de una cuenta local."""

    cuenta = models.ForeignKey(
        CuentaLocal,
        on_delete=models.PROTECT,
        related_name="cambios_perfiles",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cambios_perfiles_realizados",
    )
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField(max_length=2000)
    perfiles_anteriores = models.JSONField()
    perfiles_nuevos = models.JSONField()

    class Meta:
        ordering = ["-fecha", "-pk"]

    def __str__(self) -> str:
        return f"CambioPerfilesCuentaLocal(cuenta={self.cuenta_id}, fecha={self.fecha})"


class InvitacionCuentaLocal(models.Model):
    """Metadatos y estado de envío de invitación administrativa para una cuenta local."""

    class EstadoEnvio(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ENVIADA = "ENVIADA", "Enviada"
        ERROR = "ERROR", "Error"

    cuenta = models.OneToOneField(
        CuentaLocal,
        on_delete=models.PROTECT,
        related_name="invitacion_administrativa",
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invitaciones_cuentas_creadas",
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    aceptada_en = models.DateTimeField(null=True, blank=True)
    ultimo_intento_en = models.DateTimeField(null=True, blank=True)
    estado_envio = models.CharField(
        max_length=20,
        choices=EstadoEnvio.choices,
        default=EstadoEnvio.PENDIENTE,
    )

    def __str__(self) -> str:
        return f"InvitacionCuentaLocal(cuenta={self.cuenta_id}, estado={self.estado_envio})"
