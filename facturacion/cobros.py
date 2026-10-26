"""Cobros de una solicitud: alta atómica y verificación de ingreso separada del PDF."""

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from comunes.models import TramiteBase
from documentos.acceso import documentos_visibles
from documentos.operaciones import operacion_documental
from documentos.revision import ConflictoRevision, revisar, ultima_revision, version_aceptada
from documentos.services import incorporar
from identidad.services import has_capability

from .forms_cobros import CobroForm, VerificacionCobroForm
from .models import CobroExterno, SolicitudFacturacion, VerificacionCobro
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles
from .workflow import ConflictoConcurrenciaError


def puede_confirmar_al_registrar(actor):
    return all(has_capability(actor, c) for c in (
        "facturacion.registrar_cobro", "facturacion.verificar_cobro",
        "documentos.revisar", "documentos.consultar_metadatos",
    ))


def autorizar_cobro(actor, numero, *, verificar=False):
    solicitud = filtrar_solicitudes_visibles(actor).filter(pk=numero).first()
    if solicitud is None:
        raise ObjetoNoVisibleError
    from .seguimiento import exigir_abierta
    exigir_abierta(solicitud)
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
    puede_confirmar = puede_confirmar_al_registrar(actor)
    confirmar = CobroForm.base_fields["confirmar_al_registrar"].clean(
        datos.get("confirmar_al_registrar")
    )
    if confirmar and not puede_confirmar:
        raise PermissionDenied("No tenés permiso para confirmar ingreso y respaldo al registrar.")
    if datos.get("moneda", "ARS") != "ARS":
        raise ValidationError("El perfil de demo admite únicamente ARS.")
    if isinstance(datos.get("importe"), float | bool):
        raise ValidationError({"importe": "Usá un importe decimal exacto."})
    form = CobroForm(
        datos,
        {"archivo": archivo} if archivo else None,
        documentos=respaldos_cobro(actor, solicitud),
        puede_confirmar=puede_confirmar,
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
            cobro = CobroExterno.objects.create(
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
            if d.get("confirmar_al_registrar"):
                # Conformidad explícita del mismo actor, no una revisión independiente.
                if not version_aceptada(documento):
                    if ultima_revision(documento) is not None:
                        raise ValidationError(
                            "El respaldo tiene una revisión desfavorable o fue reemplazado. "
                            "Resolvé su revisión documental antes de confirmar en el alta."
                        )
                    try:
                        revisar(
                            actor=actor, documento_id=documento.pk, resultado="ACEPTADO",
                            motivo=(
                                "Conformidad del respaldo declarada al registrar el cobro; "
                                "mismo actor que informa y verifica el ingreso."
                            ),
                            revision_esperada=0,
                        )
                    except ConflictoRevision as exc:
                        raise ConflictoConcurrenciaError(str(exc)) from exc
                verificar_cobro(
                    actor=actor, numero=numero, cobro_id=cobro.pk,
                    datos={
                        "resultado": "CONFIRMADO",
                        "motivo": "Ingreso externo cotejado y confirmado al registrar el cobro.",
                    },
                )
            return cobro
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
    for numero, cobro in enumerate(cobros, start=1):
        cobro.numero_en_solicitud = numero
        totales[cobro.resultado] += cobro.importe
        eventos.append(cobro.como_historial())
        if cobro.resultado != "PENDIENTE":
            eventos.append(cobro.verificacion.como_historial(numero_cobro=numero))
    return cobros, totales, eventos
