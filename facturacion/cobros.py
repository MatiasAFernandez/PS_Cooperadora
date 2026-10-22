"""Cobros de una solicitud: alta atómica y verificación de ingreso separada del PDF."""

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from comunes.models import TramiteBase
from documentos.acceso import documentos_visibles
from documentos.operaciones import operacion_documental
from documentos.services import incorporar
from identidad.services import has_capability

from .forms_cobros import CobroForm, VerificacionCobroForm
from .models import CobroExterno, SolicitudFacturacion, VerificacionCobro
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles
from .workflow import ConflictoConcurrenciaError


def autorizar_cobro(actor, numero, *, verificar=False):
    solicitud = filtrar_solicitudes_visibles(actor).filter(pk=numero).first()
    if solicitud is None:
        raise ObjetoNoVisibleError
    capacidades = (
        ("facturacion.verificar_cobro",)
        if verificar
        else ("facturacion.registrar_cobro", "facturacion.informar_cobro")
    )
    if not any(has_capability(actor, c) for c in capacidades):
        raise PermissionDenied("No tenés permiso para esta acción de cobro.")
    return solicitud


def respaldos_cobro(actor, solicitud):
    if not has_capability(actor, "documentos.consultar_metadatos"):
        from documentos.models import Documento

        return Documento.objects.none()
    return (
        documentos_visibles(actor)
        .filter(
            tramite_base=solicitud.tramite_base,
            tipo="COMPROBANTE_COBRO",
            cobroexterno__isnull=True,
        )
        .order_by("fecha_incorporacion", "pk")
    )


def registrar_cobro(*, actor, numero, datos, archivo=None):
    solicitud = autorizar_cobro(actor, numero)
    if datos.get("moneda", "ARS") != "ARS":
        raise ValidationError("El perfil de demo admite únicamente ARS.")
    if isinstance(datos.get("importe"), float | bool):
        raise ValidationError({"importe": "Usá un importe decimal exacto."})
    form = CobroForm(
        datos,
        {"archivo": archivo} if archivo else None,
        documentos=respaldos_cobro(actor, solicitud),
    )
    if not form.is_valid():
        raise ValidationError({k: list(v) for k, v in form.errors.items()})
    d = form.cleaned_data
    try:
        with operacion_documental() as escrituras:
            TramiteBase.objects.select_for_update().get(pk=solicitud.tramite_base_id)
            solicitud = SolicitudFacturacion.objects.select_for_update().get(pk=numero)
            autorizar_cobro(actor, numero)
            if CobroExterno.objects.filter(
                medio=d["medio"], numero_operacion=d["numero_operacion"]
            ).exists():
                raise ConflictoConcurrenciaError("Esa operación de cobro ya está registrada.")
            documento = d["documento"]
            if documento:
                if not respaldos_cobro(actor, solicitud).filter(pk=documento.pk).exists():
                    raise ConflictoConcurrenciaError("El respaldo cambió. Recargá el formulario.")
            else:
                documento = incorporar(
                    actor=actor,
                    referencia=f"facturacion:{numero}",
                    archivo=d["archivo"],
                    tipo="COMPROBANTE_COBRO",
                    procedencia="EXTERNO_BANCO"
                    if has_capability(actor, "facturacion.consultar_todas")
                    else "SOLICITANTE",
                    _escrituras=escrituras,
                )
            return CobroExterno.objects.create(
                solicitud=solicitud,
                medio=d["medio"],
                numero_operacion=d["numero_operacion"],
                fecha_operacion=d["fecha_operacion"],
                importe=d["importe"],
                documento=documento,
                actor_id=actor.subject_id,
                procedencia="INTERNO_COOPERADORA"
                if has_capability(actor, "facturacion.registrar_cobro")
                else "SOLICITANTE",
            )
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) in {
            "uq_cobro_operacion_global",
            "facturacion_cobroexterno_documento_id_key",
        }:
            raise ConflictoConcurrenciaError(
                "La operación o su respaldo ya está registrado."
            ) from exc
        raise


def verificar_cobro(*, actor, numero, cobro_id, datos):
    solicitud = autorizar_cobro(actor, numero, verificar=True)
    if not solicitud.cobros.filter(pk=cobro_id).exists():
        raise ObjetoNoVisibleError
    form = VerificacionCobroForm(datos)
    if not form.is_valid():
        raise ValidationError({k: list(v) for k, v in form.errors.items()})
    with transaction.atomic():
        TramiteBase.objects.select_for_update().get(pk=solicitud.tramite_base_id)
        cobro = CobroExterno.objects.select_for_update().get(pk=cobro_id, solicitud=solicitud)
        autorizar_cobro(actor, numero, verificar=True)
        if VerificacionCobro.objects.filter(cobro=cobro).exists():
            raise ConflictoConcurrenciaError("Ese ingreso ya fue verificado. Recargá el detalle.")
        return VerificacionCobro.objects.create(
            cobro=cobro, actor_id=actor.subject_id, **form.cleaned_data
        )


def resumen_cobros(solicitud):
    cobros = list(solicitud.cobros.select_related("verificacion", "documento"))
    totales = {r: Decimal("0.00") for r in ("PENDIENTE", "CONFIRMADO", "RECHAZADO")}
    eventos = []
    for cobro in cobros:
        totales[cobro.resultado] += cobro.importe
        eventos.append(cobro.como_historial())
        if cobro.resultado != "PENDIENTE":
            eventos.append(cobro.verificacion.como_historial())
    return cobros, totales, eventos
