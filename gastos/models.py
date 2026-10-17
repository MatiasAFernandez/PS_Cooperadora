"""Modelos para el circuito de gastos."""

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models
from django.db.models import Q

from comunes.contracts import EventoHistorialDTO
from comunes.models import Circuito, TramiteBase


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


_SOLICITUD_GASTO_CAMPOS_INMUTABLES = {
    "id",
    "pk",
    "tramite_base",
    "tramite_base_id",
    "solicitante",
    "solicitante_id",
}


class SolicitudGastoQuerySet(models.QuerySet):
    """QuerySet que impide reasignar la identidad de una solicitud existente."""

    def update(self, **kwargs: Any) -> int:
        if _SOLICITUD_GASTO_CAMPOS_INMUTABLES.intersection(kwargs):
            raise IntegrityError(
                "No se permite reasignar id, tramite_base ni solicitante "
                "en una SolicitudGasto existente."
            )
        return super().update(**kwargs)

    def bulk_update(self, objs: Any, fields: Any, **kwargs: Any) -> int:
        if _SOLICITUD_GASTO_CAMPOS_INMUTABLES.intersection(fields):
            raise IntegrityError(
                "No se permite reasignar id, tramite_base ni solicitante "
                "en una SolicitudGasto existente."
            )
        return super().bulk_update(objs, fields, **kwargs)


class SolicitudGasto(models.Model):
    """Solicitud de gasto presentada ante Cooperadora."""

    tramite_base = models.OneToOneField(
        "comunes.TramiteBase",
        on_delete=models.PROTECT,
        related_name="solicitud_gasto",
        editable=False,
        help_text="Cabecera común protegida; número y titular coinciden con la solicitud.",
    )
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

    objects = SolicitudGastoQuerySet.as_manager()

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

    @classmethod
    def from_db(cls, db: str, field_names: Any, values: Any) -> "SolicitudGasto":
        """Conserva la identidad leída sin forzar campos diferidos."""
        instancia = super().from_db(db, field_names, values)
        cargados = dict(zip(field_names, values, strict=False))
        if {"id", "tramite_base_id", "solicitante_id"} <= cargados.keys():
            instancia._identidad_original = (
                cargados["id"],
                cargados["tramite_base_id"],
                cargados["solicitante_id"],
            )
        else:
            instancia._identidad_original = None
        return instancia

    def _validar_tramite_base(self) -> None:
        """Comprueba en ORM la relación protegida antes de escribir."""
        if self.tramite_base_id is None:
            raise IntegrityError(
                "La solicitud de gasto requiere una cabecera de trámite."
            )
        base = (
            TramiteBase.objects.filter(pk=self.tramite_base_id)
            .values("circuito", "numero_publico", "solicitante_actor_id")
            .first()
        )
        if base is None:
            raise IntegrityError("La cabecera de trámite no existe.")
        if (
            base["circuito"] != Circuito.GASTO
            or base["numero_publico"] != self.pk
            or base["solicitante_actor_id"] != str(self.solicitante_id)
        ):
            raise IntegrityError(
                "La cabecera debe pertenecer al circuito GASTO, compartir el número "
                "público y acreditar al solicitante de la solicitud."
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        identidad = (self.pk, self.tramite_base_id, self.solicitante_id)
        if self._state.adding:
            if self.pk is None:
                raise IntegrityError(
                    "El número público de la solicitud debe reservarse antes del alta."
                )
            self._validar_tramite_base()
        else:
            original = getattr(self, "_identidad_original", None)
            if original is None:
                original = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values_list("id", "tramite_base_id", "solicitante_id")
                    .first()
                )
            if original is None:
                raise IntegrityError("La solicitud de gasto no existe.")
            if identidad != original:
                raise IntegrityError(
                    "No se permite reasignar id, tramite_base ni solicitante "
                    "en una SolicitudGasto existente."
                )
            self._validar_tramite_base()
        super().save(*args, **kwargs)
        self._identidad_original = identidad

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

    def como_historial(self) -> EventoHistorialDTO:
        """Adapta la decisión al contrato de lectura común sin incluir otros datos."""
        estado_anterior = self.get_estado_anterior_display()
        estado_resultante = self.get_estado_resultante_display()
        detalle = (
            f"Estado anterior: {estado_anterior}. "
            f"Estado resultante: {estado_resultante}."
        )
        if self.motivo:
            detalle += f" Motivo: {self.motivo}"
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=f"gastos:{self.solicitud_id}",
            tipo_evento="decision_gasto",
            actor_id=str(self.autor_id),
            fecha_hora=self.fecha,
            estado_resultante=self.estado_resultante,
            motivo_o_detalle=detalle,
        )


class PagoExternoQuerySet(models.QuerySet):
    """QuerySet para PagoExterno que impide la reasignación de vínculos por update()."""

    def update(self, **kwargs: Any) -> int:
        restringidos = {"solicitud", "solicitud_id", "referencia_documental"}
        if restringidos.intersection(kwargs):
            raise IntegrityError(
                "No se permite reasignar solicitud ni referencia_documental "
                "en PagoExterno existente."
            )
        return super().update(**kwargs)

    def bulk_update(self, objs: Any, fields: Any, **kwargs: Any) -> int:
        restringidos = {"solicitud", "solicitud_id", "referencia_documental"}
        if restringidos.intersection(fields):
            raise IntegrityError(
                "No se permite reasignar solicitud ni referencia_documental "
                "en PagoExterno existente."
            )
        return super().bulk_update(objs, fields, **kwargs)


_EVENTO_PAGO_EXTERNO_CAMPOS_INMUTABLES = {
    "pago",
    "pago_id",
    "tipo_evento",
    "actor",
    "actor_id",
    "fecha_hora",
    "id",
    "pk",
}
_EVENTO_PAGO_EXTERNO_ATRIBUTOS_AUDITABLES = {
    "pago": "pago_id",
    "tipo_evento": "tipo_evento",
    "actor": "actor_id",
    "fecha_hora": "fecha_hora",
}


class EventoPagoExternoQuerySet(models.QuerySet):
    """QuerySet que impide modificar o borrar el evento auditable."""

    def delete(self) -> tuple[int, dict[str, int]]:
        raise IntegrityError("No se permite borrar un EventoPagoExterno existente.")

    def update(self, **kwargs: Any) -> int:
        if _EVENTO_PAGO_EXTERNO_CAMPOS_INMUTABLES.intersection(kwargs):
            raise IntegrityError(
                "No se permite modificar un EventoPagoExterno existente."
            )
        return super().update(**kwargs)

    def bulk_update(self, objs: Any, fields: Any, **kwargs: Any) -> int:
        if _EVENTO_PAGO_EXTERNO_CAMPOS_INMUTABLES.intersection(fields):
            raise IntegrityError(
                "No se permite modificar un EventoPagoExterno existente."
            )
        return super().bulk_update(objs, fields, **kwargs)


class PagoExterno(models.Model):
    """Registro de pago propio de gastos asociado a una solicitud aceptada.

    Límite acordado para esta demo técnica:
    - Relación OneToOne protegida hacia SolicitudGasto (a lo sumo un pago por gasto).
      Esto refleja el límite acordado para la demostración, no una regla institucional definitiva.
    - on_delete=PROTECT en solicitud para retener historial ante borrados accidentales.
    - Moneda fija en ARS e importe estrictamente positivo con restricciones en base de datos.
    - Referencia documental inmutable y opaca provista por el proveedor documental.
    - Inmutabilidad estricta de vínculos: solicitud y referencia_documental quedan congeladas
      tras la creación y no pueden reasignarse.
    """

    solicitud = models.OneToOneField(
        SolicitudGasto,
        on_delete=models.PROTECT,
        related_name="pago_externo",
        help_text="Solicitud de gasto a la que aplica el pago (límite demo: 1 pago por gasto).",
    )
    importe = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Importe efectivamente pagado en ARS.",
    )
    moneda = models.CharField(
        max_length=3,
        default="ARS",
        help_text="Moneda del pago (fijo en ARS para esta demo).",
    )
    fecha_pago = models.DateField(
        help_text="Fecha en que se produjo el hecho del pago.",
    )
    referencia_externa = models.CharField(
        max_length=128,
        help_text="Referencia externa del comprobante o transacción bancaria/comercial.",
    )
    referencia_documental = models.CharField(
        max_length=255,
        help_text=(
            "Referencia opaca e inmutable a la versión documental bloqueada por el proveedor."
        ),
    )
    huella_idempotencia = models.CharField(
        max_length=64,
        help_text=(
            "Huella SHA-256 de valores normalizados para detección de "
            "reenvíos idénticos o conflictos."
        ),
    )

    objects = PagoExternoQuerySet.as_manager()

    class Meta:
        verbose_name = "Pago externo"
        verbose_name_plural = "Pagos externos"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(importe__gt=0),
                name="pago_externo_importe_positivo",
            ),
            models.CheckConstraint(
                condition=Q(moneda="ARS"),
                name="pago_externo_moneda_ars",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.pk is not None and not self._state.adding:
            original = (
                PagoExterno.objects.filter(pk=self.pk)
                .values("solicitud_id", "referencia_documental")
                .first()
            )
            if original is not None:
                if self.solicitud_id != original["solicitud_id"]:
                    raise ValidationError(
                        {
                            "solicitud": (
                                "No se permite reasignar la solicitud de un pago externo existente."
                            )
                        }
                    )
                if self.referencia_documental != original["referencia_documental"]:
                    raise ValidationError(
                        {
                            "referencia_documental": (
                                "No se permite reasignar la referencia documental "
                                "de un pago externo existente."
                            )
                        }
                    )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and not self._state.adding:
            original = (
                PagoExterno.objects.filter(pk=self.pk)
                .values("solicitud_id", "referencia_documental")
                .first()
            )
            if original is not None:
                if self.solicitud_id != original["solicitud_id"]:
                    raise IntegrityError(
                        "No se permite reasignar la solicitud de un pago externo existente."
                    )
                if self.referencia_documental != original["referencia_documental"]:
                    raise IntegrityError(
                        "No se permite reasignar la referencia documental "
                        "de un pago externo existente."
                    )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Pago #{self.pk} de Solicitud #{self.solicitud_id} (${self.importe} {self.moneda})"


class EventoPagoExterno(models.Model):
    """Evento auditable e inmutable del registro de un pago externo.

    Garantiza atomicidad separada de auditoría sin JSON/historial genérico
    ni campos duplicados innecesarios. No utiliza DecisionGasto.
    Evento de auditoría inmutable: vínculo, actor, tipo y hora quedan fijados al crear.
    """

    pago = models.OneToOneField(
        PagoExterno,
        on_delete=models.PROTECT,
        related_name="evento",
        help_text="Pago externo asociado. Límite de demo: exactamente un evento por pago.",
    )
    tipo_evento = models.CharField(
        max_length=50,
        default="pago_externo_registrado",
        help_text="Tipo de evento registrado (por defecto: pago_externo_registrado).",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="eventos_pago_externo",
        help_text="Actor del servidor que ejecutó el registro.",
    )
    fecha_hora = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora exactas fijadas por el servidor al momento del registro.",
    )

    objects = EventoPagoExternoQuerySet.as_manager()

    class Meta:
        verbose_name = "Evento de pago externo"
        verbose_name_plural = "Eventos de pago externo"
        ordering = ["-fecha_hora", "-id"]

    def clean(self) -> None:
        super().clean()
        if self.pk is not None and not self._state.adding:
            original = (
                EventoPagoExterno.objects.filter(pk=self.pk)
                .values(*_EVENTO_PAGO_EXTERNO_ATRIBUTOS_AUDITABLES.values())
                .first()
            )
            if original is not None:
                cambios = {
                    campo: "No se permite modificar un evento de pago externo existente."
                    for campo, atributo in _EVENTO_PAGO_EXTERNO_ATRIBUTOS_AUDITABLES.items()
                    if getattr(self, atributo) != original[atributo]
                }
                if cambios:
                    raise ValidationError(cambios)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and not self._state.adding:
            original = (
                EventoPagoExterno.objects.filter(pk=self.pk)
                .values(*_EVENTO_PAGO_EXTERNO_ATRIBUTOS_AUDITABLES.values())
                .first()
            )
            if original is not None:
                cambios = [
                    campo
                    for campo, atributo in _EVENTO_PAGO_EXTERNO_ATRIBUTOS_AUDITABLES.items()
                    if getattr(self, atributo) != original[atributo]
                ]
                if cambios:
                    raise IntegrityError(
                        "No se permite modificar un EventoPagoExterno existente: "
                        + ", ".join(cambios)
                    )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise IntegrityError("No se permite borrar un EventoPagoExterno existente.")

    def __str__(self) -> str:
        return f"Evento #{self.pk} - {self.tipo_evento} sobre Pago #{self.pago_id}"

    def como_historial(self) -> EventoHistorialDTO:
        """Adapta el hecho del pago sin exponer referencias o metadatos documentales."""
        pago = self.pago
        detalle = (
            f"Importe: {pago.importe} {pago.moneda}. "
            f"Fecha del hecho: {pago.fecha_pago.isoformat()}. "
            f"Referencia externa: {pago.referencia_externa}."
        )
        return EventoHistorialDTO(
            evento_id=self.pk,
            tramite_ref=f"gastos:{pago.solicitud_id}",
            tipo_evento=self.tipo_evento,
            actor_id=str(self.actor_id),
            fecha_hora=self.fecha_hora,
            estado_resultante=pago.solicitud.estado,
            motivo_o_detalle=detalle,
        )
