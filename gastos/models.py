"""Modelos para el circuito de gastos."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models
from django.db.models import Q
from django.utils.formats import date_format

from comunes.contracts import EventoHistorialDTO
from comunes.models import Circuito, TramiteBase


class EstadoSolicitud(models.TextChoices):
    PRESENTADA = "presentada", "Presentada"
    ACEPTADA = "aceptada", "Aceptada"
    POSTERGADA = "postergada", "Postergada"
    RECHAZADA = "rechazada", "Rechazada"


class TipoFlujoGasto(models.TextChoices):
    COMPRA_DIRECTA = "COMPRA_DIRECTA", "Compra directa a proveedor"
    REINTEGRO = "REINTEGRO", "Reintegro a solicitante"


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
    tipo_flujo = models.CharField(
        max_length=20,
        choices=TipoFlujoGasto.choices,
        default=TipoFlujoGasto.COMPRA_DIRECTA,
        db_index=True,
        help_text="Modalidad operativa del gasto (compra directa o reintegro).",
    )
    centro_costo = models.ForeignKey(
        "gastos.CentroCosto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitudes",
        help_text="Centro de costo institucional imputado opcionalmente.",
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


class RevisionDatosTransferenciaQuerySet(models.QuerySet):
    """QuerySet que impide modificar o borrar revisiones ya registradas."""

    def update(self, **kwargs: Any) -> int:
        raise IntegrityError(
            "No se permite modificar una Revisión de datos de transferencia existente."
        )

    def bulk_update(self, objs: Any, fields: Any, **kwargs: Any) -> int:
        raise IntegrityError(
            "No se permite modificar una Revisión de datos de transferencia existente."
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise IntegrityError(
            "No se permite borrar una Revisión de datos de transferencia existente."
        )


class RevisionDatosTransferencia(models.Model):
    """Datos operativos informados para preparar una transferencia del gasto.

    Cada corrección crea una fila nueva; las anteriores se conservan. El actor y
    la hora los fija el servidor. La ausencia de esta revisión no altera el
    estado del gasto ni el contrato documental del pago externo (C03).
    """

    solicitud = models.ForeignKey(
        SolicitudGasto,
        on_delete=models.PROTECT,
        related_name="revisiones_datos_transferencia",
        help_text="Gasto al que pertenece la revisión; el historial no se reasigna.",
    )
    numero_revision = models.PositiveIntegerField(
        help_text="Número secuencial de la revisión dentro del gasto (inicial: 1).",
    )
    titular_nombre = models.CharField(
        max_length=200,
        help_text="Titular o beneficiario de la cuenta, tal como fue informado.",
    )
    identificacion = models.CharField(
        max_length=100,
        help_text="Identificación informada del titular; no se valida contra un padrón.",
    )
    cbu_alias = models.CharField(
        max_length=128,
        help_text=(
            "CBU o alias informado como dato textual; no se valida contra un padrón bancario."
        ),
    )
    correo_comprobante = models.CharField(
        max_length=254,
        help_text="Correo informado para remitir el comprobante; no se envía automáticamente.",
    )
    centro_costo = models.CharField(
        max_length=100,
        help_text="Centro de costo informado; no se confunde con la unidad requirente.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revisiones_datos_transferencia_gasto",
        help_text="Actor del servidor que registró la revisión.",
    )
    fecha_hora = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora fijadas por el servidor al registrar la revisión.",
    )

    objects = RevisionDatosTransferenciaQuerySet.as_manager()

    class Meta:
        verbose_name = "Revisión de datos de transferencia"
        verbose_name_plural = "Revisiones de datos de transferencia"
        ordering = ["solicitud", "numero_revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["solicitud", "numero_revision"],
                name="uq_revision_datos_transferencia_numero",
            ),
            models.CheckConstraint(
                condition=Q(numero_revision__gt=0),
                name="revision_datos_transferencia_numero_positivo",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise IntegrityError(
                "Cada revisión de datos de transferencia es inmutable; registrá una nueva."
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise IntegrityError("No se permite borrar una Revisión de datos de transferencia.")

    def __str__(self) -> str:
        return (
            f"Revisión {self.numero_revision} de datos de transferencia "
            f"del gasto #{self.solicitud_id}"
        )


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
        restringidos = {
            "solicitud",
            "solicitud_id",
            "referencia_documental",
            "comprobante_bancario",
            "comprobante_bancario_id",
            "constancia_atp",
            "constancia_atp_id",
        }
        if restringidos.intersection(kwargs):
            raise IntegrityError(
                "No se permite reasignar solicitud, referencia_documental ni vínculos "
                "documentales del pago mediante update()."
            )
        return super().update(**kwargs)

    def bulk_update(self, objs: Any, fields: Any, **kwargs: Any) -> int:
        restringidos = {
            "solicitud",
            "solicitud_id",
            "referencia_documental",
            "comprobante_bancario",
            "comprobante_bancario_id",
            "constancia_atp",
            "constancia_atp_id",
        }
        if restringidos.intersection(fields):
            raise IntegrityError(
                "No se permite reasignar solicitud, referencia_documental ni vínculos "
                "documentales del pago mediante bulk_update()."
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
    monto_bruto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Monto bruto de la operación antes de retenciones impositivas.",
    )
    monto_retencion_atp = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto retenido según alícuota provincial ATP.",
    )
    referencia_atp = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Número o referencia del certificado de retención ATP.",
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
        blank=True,
        default="",
        help_text=(
            "Número de operación o referencia bancaria informada. Puede quedar vacío: "
            "no se inventa un número."
        ),
    )
    referencia_documental = models.CharField(
        max_length=255,
        help_text=(
            "Referencia opaca e inmutable a la versión documental bloqueada por el proveedor."
        ),
    )
    comprobante_bancario = models.ForeignKey(
        "documentos.Documento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos_como_comprobante_bancario",
        help_text=(
            "Documento PDF del comprobante bancario. Nulo sólo en registros históricos "
            "anteriores a la regla de PDF obligatorio."
        ),
    )
    constancia_atp = models.ForeignKey(
        "documentos.Documento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos_como_constancia_atp",
        help_text=(
            "Constancia ATP vigente del pago. Puede incorporarse después del registro; "
            "nunca se fabrica ni se infiere."
        ),
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Versión efectiva del pago. Cada rectificación o aporte posterior la incrementa.",
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
            models.CheckConstraint(
                condition=Q(importe=models.F("monto_bruto") - models.F("monto_retencion_atp"))
                & Q(monto_retencion_atp__gte=Decimal("0.00"))
                & Q(monto_bruto__gt=Decimal("0.00")),
                name="pago_externo_identidad_neto_atp",
            ),
            models.CheckConstraint(
                condition=Q(version__gt=0),
                name="pago_externo_version_positiva",
            ),
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if (
            (self.monto_bruto is None or self.monto_bruto == Decimal("0.00"))
            and self.importe
            and (self.monto_retencion_atp is None or self.monto_retencion_atp == Decimal("0.00"))
        ):
            self.monto_bruto = self.importe

    def clean(self) -> None:
        super().clean()
        if (
            self.monto_bruto is not None
            and self.monto_retencion_atp is not None
            and self.importe is not None
        ):
            if self.importe != (self.monto_bruto - self.monto_retencion_atp):
                raise ValidationError(
                    {
                        "importe": (
                            "El importe neto debe ser igual al monto bruto menos la retención ATP."
                        )
                    }
                )
        if (
            self.comprobante_bancario_id is not None
            and getattr(self.comprobante_bancario, "tipo", None)
            != "COMPROBANTE_PAGO"
        ):
            raise ValidationError(
                {"comprobante_bancario": "El comprobante bancario debe ser un PDF de pago."}
            )
        if (
            self.constancia_atp_id is not None
            and getattr(self.constancia_atp, "tipo", None)
            != "CONSTANCIA_RETENCION_ATP"
        ):
            raise ValidationError(
                {"constancia_atp": "La constancia ATP debe ser del tipo documental ATP."}
            )
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
        if (
            (self.monto_bruto is None or self.monto_bruto == Decimal("0.00"))
            and self.importe
            and (self.monto_retencion_atp is None or self.monto_retencion_atp == Decimal("0.00"))
        ):
            self.monto_bruto = self.importe

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

    @property
    def constancia_atp_pendiente(self) -> bool:
        """Pendiente derivado: retención positiva sin constancia vigente."""
        return self.monto_retencion_atp > Decimal("0.00") and self.constancia_atp_id is None

    @property
    def es_registro_legado(self) -> bool:
        """Un pago histórico sin comprobante no se presenta como documentado."""
        return self.comprobante_bancario_id is None

    def __str__(self) -> str:
        return f"Pago #{self.pk} de Solicitud #{self.solicitud_id} (${self.importe} {self.moneda})"


def formatear_importe_es_ar(valor) -> str:
    """Formato visible es-AR: miles con punto y dos decimales con coma."""
    cuantizado = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    texto = f"{abs(cuantizado):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{texto}" if cuantizado < 0 else texto


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
        """Adapta el hecho del pago sin exponer referencias o metadatos documentales.

        Si existe la representación original, el evento muestra los valores del
        alta y no los importes corregidos después. La fila efectiva se consulta
        por separado en la tarjeta del pago.
        """
        pago = self.pago
        original = PagoExternoOriginal.objects.filter(pago_id=pago.pk).first()
        importe = original.importe if original is not None else pago.importe
        fecha_pago = original.fecha_pago if original is not None else pago.fecha_pago
        referencia_externa = (
            original.referencia_externa if original is not None else pago.referencia_externa
        )
        monto_bruto = original.monto_bruto if original is not None else pago.monto_bruto
        monto_retencion_atp = (
            original.monto_retencion_atp
            if original is not None
            else pago.monto_retencion_atp
        )
        monto_bruto = Decimal(str(monto_bruto))
        monto_retencion_atp = Decimal(str(monto_retencion_atp))
        detalle = (
            f"Importe: {formatear_importe_es_ar(importe)} {pago.moneda}. "
            f"Fecha del hecho: {date_format(fecha_pago, 'd/m/Y')}."
        )
        if referencia_externa:
            detalle += f" Referencia externa: {referencia_externa}."
        if monto_retencion_atp > Decimal("0.00"):
            detalle += (
                f" Bruto: {formatear_importe_es_ar(monto_bruto)} {pago.moneda}. "
                f"Retención ATP: {formatear_importe_es_ar(monto_retencion_atp)} {pago.moneda}."
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


class PagoExternoOriginalQuerySet(models.QuerySet):
    """La representación original del alta es inmutable."""

    def delete(self) -> tuple[int, dict[str, int]]:
        raise IntegrityError("No se permite borrar la representación original del pago.")

    def update(self, **kwargs: Any) -> int:
        raise IntegrityError("No se permite modificar la representación original del pago.")

    def bulk_update(self, objs: Any, fields: Any, **kwargs: Any) -> int:
        raise IntegrityError("No se permite modificar la representación original del pago.")


class PagoExternoOriginal(models.Model):
    """Valores normalizados y documentos del alta original, separados del estado efectivo.

    Se crea una sola vez al registrar el pago. Las rectificaciones posteriores
    modifican ``PagoExterno`` y agregan filas a ``PagoExternoCambio``, pero esta
    representación conserva la identidad de los reenvíos de alta. Los registros
    históricos migrados se marcan con ``es_legado=True`` y no reciben un PDF
    inventado.
    """

    pago = models.OneToOneField(
        PagoExterno,
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="original",
        help_text="Pago cuyo alta original se conserva.",
    )
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    monto_bruto = models.DecimalField(max_digits=12, decimal_places=2)
    monto_retencion_atp = models.DecimalField(max_digits=12, decimal_places=2)
    moneda = models.CharField(max_length=3, default="ARS")
    fecha_pago = models.DateField()
    referencia_externa = models.CharField(max_length=128, blank=True, default="")
    referencia_documental = models.CharField(max_length=255)
    referencia_atp = models.CharField(max_length=128, blank=True, default="")
    comprobante_bancario = models.ForeignKey(
        "documentos.Documento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos_originales_como_comprobante",
    )
    constancia_atp = models.ForeignKey(
        "documentos.Documento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos_originales_como_constancia",
    )
    comprobante_sha256 = models.CharField(max_length=64, blank=True, default="")
    constancia_sha256 = models.CharField(max_length=64, blank=True, default="")
    es_legado = models.BooleanField(
        default=False,
        help_text="Alta anterior a la regla de comprobante PDF obligatorio.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = PagoExternoOriginalQuerySet.as_manager()

    class Meta:
        verbose_name = "Representación original del pago"
        verbose_name_plural = "Representaciones originales de pagos"
        constraints = [
            models.CheckConstraint(
                condition=Q(importe=models.F("monto_bruto") - models.F("monto_retencion_atp")),
                name="pago_original_identidad_neto_atp",
            ),
            models.CheckConstraint(
                condition=Q(moneda="ARS"),
                name="pago_original_moneda_ars",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise IntegrityError(
                "La representación original del pago es inmutable; use PagoExternoCambio."
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise IntegrityError("No se permite borrar la representación original del pago.")

    def __str__(self) -> str:
        return f"Alta original del Pago #{self.pago_id}"


class PagoExternoCambioQuerySet(models.QuerySet):
    """El historial de rectificaciones y aportes posteriores es append-only."""

    def delete(self) -> tuple[int, dict[str, int]]:
        raise IntegrityError("No se permite borrar un cambio de pago externo.")

    def update(self, **kwargs: Any) -> int:
        raise IntegrityError("No se permite modificar un cambio de pago externo.")

    def bulk_update(self, objs: Any, fields: Any, **kwargs: Any) -> int:
        raise IntegrityError("No se permite modificar un cambio de pago externo.")


class PagoExternoCambio(models.Model):
    """Hecho append-only de una rectificación o incorporación documental posterior.

    Guarda la versión resultante, el motivo obligatorio, el actor y la fecha del
    servidor, además de snapshots cerrados antes/después. No reemplaza al evento
    original del alta ni se usa como si fuera un pago adicional.
    """

    class Tipo(models.TextChoices):
        RECTIFICACION = "rectificacion", "Rectificación de datos"
        COMPROBANTE_REEMPLAZADO = "comprobante_reemplazado", "Comprobante bancario reemplazado"
        COMPROBANTE_INCORPORADO = "comprobante_incorporado", "Comprobante bancario incorporado"
        ATP_INCORPORADA = "atp_incorporada", "Constancia ATP incorporada"
        ATP_RETIRADA = "atp_retirada", "Constancia ATP desvinculada"

    pago = models.ForeignKey(
        PagoExterno,
        on_delete=models.PROTECT,
        related_name="cambios",
        help_text="Pago efectivo al que se aplicó el cambio.",
    )
    numero_version = models.PositiveIntegerField(
        help_text="Versión efectiva resultante después del cambio."
    )
    tipo = models.CharField(max_length=40, choices=Tipo.choices)
    motivo = models.TextField(max_length=500)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cambios_pago_externo",
    )
    fecha_hora = models.DateTimeField(auto_now_add=True)
    datos_antes = models.JSONField()
    datos_despues = models.JSONField()
    documento_anterior = models.ForeignKey(
        "documentos.Documento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cambios_pago_documento_anterior",
    )
    documento_nuevo = models.ForeignKey(
        "documentos.Documento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cambios_pago_documento_nuevo",
    )

    objects = PagoExternoCambioQuerySet.as_manager()

    class Meta:
        verbose_name = "Cambio de pago externo"
        verbose_name_plural = "Cambios de pagos externos"
        ordering = ["pago_id", "numero_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["pago", "numero_version"],
                name="uq_pago_externo_cambio_version",
            ),
            models.CheckConstraint(
                condition=Q(numero_version__gt=0),
                name="pago_externo_cambio_version_positiva",
            ),
            models.CheckConstraint(
                condition=~Q(motivo=""),
                name="pago_externo_cambio_motivo_obligatorio",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise IntegrityError("El historial de cambios del pago es append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise IntegrityError("El historial de cambios del pago es append-only.")

    def __str__(self) -> str:
        return f"Cambio v{self.numero_version} del Pago #{self.pago_id}: {self.get_tipo_display()}"


class CentroCosto(models.Model):
    """Catálogo de centros de costo o áreas para afectación de gastos.

    Permite al administrador agregar y desactivar centros de costo (baja lógica)
    sin romper la integridad referencial de los trámites históricos.
    """

    codigo = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Código identificador único del centro de costo (ej: lab-quimica).",
    )
    nombre = models.CharField(
        max_length=150,
        help_text="Nombre descriptivo del centro de costo.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Indica si el centro de costo está habilitado para nuevas solicitudes.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Centro de costo"
        verbose_name_plural = "Centros de costo"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.codigo})"


class ParametroOperativo(models.Model):
    """Parámetro operativo configurable de la Asociación Cooperadora.

    Permite al administrador editar valores como la base imponible y alícuota
    de retención ATP sin hardcodearlos en el código ni exigir migraciones.
    """

    clave = models.CharField(
        max_length=50,
        unique=True,
        help_text="Clave unívoca del parámetro operativo (ej: ATP_BASE_IMPONIBLE).",
    )
    valor_decimal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor numérico decimal si corresponde.",
    )
    valor_texto = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Valor en texto si corresponde.",
    )
    descripcion = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Descripción del propósito del parámetro.",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="parametros_operativos_modificados",
        help_text="Usuario que realizó la última modificación.",
    )
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parámetro operativo"
        verbose_name_plural = "Parámetros operativos"
        ordering = ["clave"]

    def __str__(self) -> str:
        valor = self.valor_decimal if self.valor_decimal is not None else self.valor_texto
        return f"{self.clave}: {valor}"

