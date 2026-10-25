"""Solicitudes y eventos inmutables del recorrido de presentación y corrección."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models

from comunes.contracts import EventoHistorialDTO

from .choices import MEDIOS_PAGO_EFECTIVOS, CondicionIVA, ModalidadCobro, ProductoServicio
from .models_cierre import ActualizacionRespaldo  # noqa: F401
from .models_cobros import CobroExterno, VerificacionCobro  # noqa: F401
from .validation import validar_cuit


class EstadoSolicitudFacturacion(models.TextChoices):
    BORRADOR_TECNICO = "BORRADOR_TECNICO", "Borrador técnico"
    PRESENTADA = "PRESENTADA", "Presentada"
    OBSERVADA = "OBSERVADA", "Observada"
    CERRADA = "CERRADA", "Cerrada"
    ANULADA = "ANULADA", "Anulada"


class SolicitudQuerySet(models.QuerySet):
    def operativas(self):
        return self.exclude(estado=EstadoSolicitudFacturacion.BORRADOR_TECNICO)


class SolicitudFacturacion(models.Model):
    tramite_base = models.OneToOneField(
        "comunes.TramiteBase", on_delete=models.PROTECT, related_name="solicitud_facturacion"
    )
    estado = models.CharField(
        max_length=40, choices=EstadoSolicitudFacturacion.choices, default="BORRADOR_TECNICO"
    )
    version_concurrencia = models.PositiveIntegerField(default=1)
    clave_idempotencia = models.UUIDField(default=uuid.uuid4, editable=False)
    correo_solicitante = models.EmailField(blank=True, editable=False)
    fecha_presentacion = models.DateTimeField(null=True, blank=True, editable=False)
    presento_comprobante_pago = models.BooleanField(null=True, blank=True)
    nombre_solicitante = models.CharField(max_length=200, blank=True)
    cuit_receptor = models.CharField(max_length=11, blank=True, validators=[validar_cuit])
    nombre_receptor = models.CharField(max_length=255, blank=True)
    condicion_iva = models.CharField(max_length=30, choices=CondicionIVA.choices, blank=True)
    email_envio_factura = models.EmailField(blank=True)
    detalle_factura = models.TextField(blank=True)
    importe_factura = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    producto_servicio = models.CharField(
        max_length=60, choices=ProductoServicio.choices, blank=True
    )
    modalidad_cobro = models.CharField(max_length=30, choices=ModalidadCobro.choices, blank=True)
    observaciones = models.TextField(blank=True)
    fecha_operacion_declarada = models.DateField(null=True, blank=True)
    numero_operacion_declarado = models.CharField(max_length=100, blank=True)
    documento_comprobante_inicial = models.ForeignKey(
        "documentos.Documento", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    observacion_vigente = models.TextField(blank=True)

    objects = SolicitudQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estado="BORRADOR_TECNICO")
                | (
                    models.Q(fecha_presentacion__isnull=False)
                    & models.Q(presento_comprobante_pago__isnull=False)
                    & models.Q(importe_factura__isnull=False, importe_factura__gte=Decimal("0.01"))
                    & ~models.Q(correo_solicitante="")
                    & ~models.Q(nombre_solicitante="")
                    & ~models.Q(cuit_receptor="")
                    & ~models.Q(nombre_receptor="")
                    & ~models.Q(condicion_iva="")
                    & ~models.Q(email_envio_factura="")
                    & ~models.Q(detalle_factura="")
                    & ~models.Q(producto_servicio="")
                    & ~models.Q(modalidad_cobro="")
                    & ~models.Q(observaciones="")
                ),
                name="ck_fac_datos_operativos",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(estado="BORRADOR_TECNICO")
                    | ~models.Q(
                        presento_comprobante_pago=True,
                        modalidad_cobro__in=(
                            "MERCADO_PAGO",
                            "BNA_COMUN",
                            "BNA_UVT",
                            "NBCH",
                        ),
                    )
                    | (
                        models.Q(fecha_operacion_declarada__isnull=False)
                        & ~models.Q(numero_operacion_declarado="")
                        & models.Q(documento_comprobante_inicial__isnull=False)
                    )
                ),
                name="ck_fac_respaldo_d01",
            ),
            models.UniqueConstraint(
                fields=["clave_idempotencia"], name="uq_facturacion_clave_idempotencia"
            ),
            models.CheckConstraint(
                condition=models.Q(version_concurrencia__gt=0), name="ck_fac_version_positiva"
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=EstadoSolicitudFacturacion.values),
                name="ck_fac_estado_conocido",
            ),
        ]

    @property
    def centro_costo(self):
        return self.tramite_base.centro_costo_codigo

    @property
    def estado_seguimiento(self):
        from .seguimiento import estado_visible

        return estado_visible(self)

    def clean(self):
        if self.estado == EstadoSolicitudFacturacion.BORRADOR_TECNICO:
            return
        errors = {}
        for field in (
            "correo_solicitante",
            "fecha_presentacion",
            "nombre_solicitante",
            "cuit_receptor",
            "nombre_receptor",
            "condicion_iva",
            "email_envio_factura",
            "detalle_factura",
            "producto_servicio",
            "modalidad_cobro",
            "observaciones",
        ):
            value = getattr(self, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors[field] = "Este campo es obligatorio."
        if type(self.presento_comprobante_pago) is not bool:
            errors["presento_comprobante_pago"] = "Seleccioná Sí o No."
        if self.presento_comprobante_pago and self.modalidad_cobro in MEDIOS_PAGO_EFECTIVOS:
            for field in (
                "fecha_operacion_declarada",
                "numero_operacion_declarado",
                "documento_comprobante_inicial",
            ):
                if not getattr(self, field):
                    errors[field] = "Obligatorio al declarar pago por banco o Mercado Pago."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            previo = type(self).objects.filter(pk=self.pk).values_list("tramite_base_id", flat=True)
            if previo.exists() and previo.get() != self.tramite_base_id:
                raise IntegrityError("La cabecera de la solicitud es inmutable.")
        super().save(*args, **kwargs)


class EventoFacturacion(models.Model):
    """Registro append-only; los servicios funcionales validan las transiciones."""

    solicitud = models.ForeignKey(
        SolicitudFacturacion, on_delete=models.PROTECT, related_name="eventos"
    )
    tipo_evento = models.CharField(max_length=40)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    estado_resultante = models.CharField(max_length=40)
    motivo_o_detalle = models.TextField(blank=True)
    snapshot_datos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["fecha_hora", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("No se permite modificar un evento de facturación.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("No se permite borrar un evento de facturación.")

    def como_historial(self) -> EventoHistorialDTO:
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=str(self.solicitud.tramite_base.referencia),
            tipo_evento=self.tipo_evento,
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha_hora,
            estado_resultante=self.estado_resultante,
            motivo_o_detalle=self.motivo_o_detalle,
        )


class ComprobanteExterno(models.Model):
    """Registro inmutable de un comprobante ya emitido; es su propio hecho auditable."""

    class Tipo(models.TextChoices):
        FACTURA = "FACTURA", "Factura"
        CREDITO = "NOTA_CREDITO", "Nota de crédito"
        DEBITO = "NOTA_DEBITO", "Nota de débito"

    solicitud = models.ForeignKey(
        SolicitudFacturacion, on_delete=models.PROTECT, related_name="comprobantes"
    )
    tipo = models.CharField(max_length=16, choices=Tipo.choices)
    cuit_emisor = models.CharField(max_length=11, validators=[validar_cuit])
    letra = models.CharField(max_length=1)
    punto_venta = models.PositiveIntegerField()
    numero = models.PositiveIntegerField()
    fecha_emision = models.DateField()
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    procedencia = models.CharField(
        max_length=30,
        default="EXTERNO_XUBIO",
        choices=[("EXTERNO_XUBIO", "Xubio"), ("EXTERNO_OTRO", "Otro")],
    )
    origen_aclaracion = models.CharField(max_length=200, blank=True, default="", db_default="")
    factura_origen = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="notas"
    )
    documento = models.OneToOneField("documentos.Documento", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_registro", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(procedencia="EXTERNO_XUBIO", origen_aclaracion="")
                | models.Q(procedencia="EXTERNO_OTRO", origen_aclaracion__regex=r"\S"),
                name="ck_comprobante_procedencia",
            ),
            models.UniqueConstraint(
                fields=["cuit_emisor", "tipo", "letra", "punto_venta", "numero"],
                name="uq_comprobante_identidad_externa",
            ),
            models.UniqueConstraint(
                fields=["solicitud"],
                condition=models.Q(tipo="FACTURA"),
                name="uq_una_factura_por_solicitud",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    importe__gte=Decimal("0.01"), importe__lte=Decimal("9999999999.99")
                ),
                name="ck_comprobante_importe",
            ),
            models.CheckConstraint(
                condition=models.Q(punto_venta__gte=1, punto_venta__lte=99999),
                name="ck_comprobante_punto_venta",
            ),
            models.CheckConstraint(
                condition=models.Q(numero__gte=1, numero__lte=99999999),
                name="ck_comprobante_numero",
            ),
            models.CheckConstraint(
                condition=models.Q(tipo="FACTURA", factura_origen__isnull=True)
                | models.Q(tipo__in=["NOTA_CREDITO", "NOTA_DEBITO"], factura_origen__isnull=False),
                name="ck_comprobante_origen",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("El comprobante registrado es inmutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("El comprobante registrado es inmutable.")

    @property
    def identificacion(self):
        return f"{self.get_tipo_display()} {self.letra} {self.punto_venta:05d}-{self.numero:08d}"

    @property
    def origen_mostrado(self):
        return "Xubio" if self.procedencia == "EXTERNO_XUBIO" else f"Otro: {self.origen_aclaracion}"

    def como_historial(self):
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=f"facturacion:{self.solicitud_id}",
            tipo_evento="comprobante_externo_registrado",
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha_registro,
            estado_resultante="REGISTRADO",
            motivo_o_detalle=(
                f"{self.identificacion}. Emisor: {self.cuit_emisor}. "
                f"Origen: {self.origen_mostrado}."
            ),
        )
