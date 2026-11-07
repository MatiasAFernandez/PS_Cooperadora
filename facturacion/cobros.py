"""Cobros de una solicitud: alta atómica y verificación de ingreso separada del PDF."""

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from comunes.models import TramiteBase
from documentos.acceso import documentos_visibles
from documentos.models import Documento
from documentos.operaciones import operacion_documental
from documentos.revision import ConflictoRevision, revisar, ultima_revision, version_aceptada
from documentos.services import incorporar
from identidad.services import has_capability

from .forms_cobros import DATOS_COBRO, CobroForm, VerificacionCobroForm
from .models import CobroExterno, RectificacionCobro, SolicitudFacturacion, VerificacionCobro
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles
from .workflow import ConflictoConcurrenciaError


def puede_confirmar_al_registrar(actor):
    return all(
        has_capability(actor, c)
        for c in (
            "facturacion.registrar_cobro",
            "facturacion.verificar_cobro",
            "documentos.revisar",
            "documentos.consultar_metadatos",
        )
    )


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
        raise PermissionDenied(
            "No tenés permiso para confirmar el ingreso y el documento de respaldo."
        )
    if datos.get("moneda", "ARS") != "ARS":
        raise ValidationError("Registrá el cobro en pesos argentinos (ARS).")
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
                    raise ConflictoConcurrenciaError(
                        "El documento de respaldo cambió. Recargá el formulario."
                    )
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
                            "El documento de respaldo fue observado, rechazado o reemplazado. "
                            "Resolvé su revisión documental antes de confirmar en el alta."
                        )
                    try:
                        revisar(
                            actor=actor,
                            documento_id=documento.pk,
                            resultado="ACEPTADO",
                            motivo=(
                                "Conformidad del documento de respaldo al registrar el cobro; "
                                "mismo actor que informa y verifica el ingreso."
                            ),
                            revision_esperada=0,
                        )
                    except ConflictoRevision as exc:
                        raise ConflictoConcurrenciaError(str(exc)) from exc
                verificar_cobro(
                    actor=actor,
                    numero=numero,
                    cobro_id=cobro.pk,
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
                "La operación o el documento de respaldo ya está registrado."
            ) from exc
        raise


def verificar_cobro(*, actor, numero, cobro_id, datos):
    from .seguimiento import respaldo_actual

    solicitud = autorizar_cobro(actor, numero, verificar=True)
    if not solicitud.cobros.filter(pk=cobro_id).exists():
        raise ObjetoNoVisibleError
    form = VerificacionCobroForm(datos)
    if not form.is_valid():
        raise ValidationError({k: list(v) for k, v in form.errors.items()})
    with transaction.atomic():
        TramiteBase.objects.select_for_update().get(pk=solicitud.tramite_base_id)
        cobro = CobroExterno.objects.select_for_update().filter(
            pk=cobro_id, solicitud=solicitud
        ).first()
        if cobro is None:
            raise ConflictoConcurrenciaError("El cobro cambió. Recargá la solicitud.")
        autorizar_cobro(actor, numero, verificar=True)
        if VerificacionCobro.objects.filter(cobro=cobro).exists():
            raise ConflictoConcurrenciaError("Ese ingreso ya fue verificado. Recargá el detalle.")
        if form.cleaned_data["resultado"] == "CONFIRMADO" and not version_aceptada(
            respaldo_actual(cobro)
        ):
            raise ValidationError(
                "Para confirmar el ingreso, primero aceptá el documento de respaldo vigente."
            )
        return VerificacionCobro.objects.create(
            cobro=cobro, actor_id=actor.subject_id, **form.cleaned_data
        )


def cobro_rectificable(solicitud, cobro_id):
    cobro = (
        solicitud.cobros.select_related("verificacion__rectificacion").filter(pk=cobro_id).first()
    )
    if cobro is None:
        raise ObjetoNoVisibleError
    if cobro.resultado != "CONFIRMADO":
        raise ConflictoConcurrenciaError("El cobro ya no está confirmado. Recargá la solicitud.")
    return cobro


def rectificar_cobro(*, actor, numero, cobro_id, motivo):
    from .seguimiento import motivo_valido

    solicitud = autorizar_cobro(actor, numero, verificar=True)
    with transaction.atomic():
        TramiteBase.objects.select_for_update().get(pk=solicitud.tramite_base_id)
        solicitud = autorizar_cobro(actor, numero, verificar=True)
        cobro = cobro_rectificable(solicitud, cobro_id)
        return RectificacionCobro.objects.create(
            verificacion=cobro.verificacion,
            actor_id=actor.subject_id,
            motivo=motivo_valido(motivo),
        )


def resumen_cobros(solicitud):
    cobros = list(solicitud.cobros.select_related("verificacion__rectificacion", "documento"))
    resultados = ("PENDIENTE", "CONFIRMADO", "RECHAZADO")
    totales = dict.fromkeys(resultados, Decimal("0.00"))
    eventos = []
    for cobro in CobroExterno.todos.filter(solicitud=solicitud).select_related(
        "verificacion__rectificacion", "documento", "reemplaza"
    ):
        numero = cobro.numero_en_solicitud
        resultado = cobro.resultado
        if not cobro.sustituido and resultado in totales:
            totales[resultado] += cobro.importe
        eventos.append(cobro.como_historial(numero_cobro=numero))
        if resultado != "PENDIENTE":
            eventos.append(cobro.verificacion.como_historial(numero_cobro=numero))
        if resultado == "RECTIFICADO":
            eventos.append(
                cobro.verificacion.rectificacion.como_historial(cobro=cobro, numero_cobro=numero)
            )
    return cobros, totales, eventos


def _puede_corregir_como_operador(actor, cobro):
    return has_capability(actor, "facturacion.registrar_cobro") and (
        cobro.resultado != "CONFIRMADO" or has_capability(actor, "facturacion.verificar_cobro")
    )


def puede_corregir_cobro(actor, cobro):
    if (
        cobro.sustituido
        or cobro.solicitud.estado in {"CERRADA", "ANULADA"}
        or not has_capability(actor, "documentos.incorporar")
    ):
        return False

    if _puede_corregir_como_operador(actor, cobro):
        return True

    return (
        has_capability(actor, "facturacion.informar_cobro")
        and cobro.solicitud.tramite_base.solicitante_actor_id == str(actor.subject_id)
        and cobro.cobro_original.actor_id == actor.subject_id
        and cobro.cobro_original.procedencia == "SOLICITANTE"
    )


def corregir_cobro(
    *,
    actor,
    numero,
    cobro_id,
    datos,
    archivo=None,
    nuevo_id=None,
    resultado_esperado=None,
    revision_esperada=None,
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from documentos.services import almacenamiento

    from .forms_cobros import CorreccionCobroForm
    from .seguimiento import (
        diagnostico,
        puede_actualizar_respaldo,
        respaldo_actual,
        sucesores_respaldo_cobro,
    )

    solicitud = autorizar_cobro(actor, numero)
    if isinstance(datos.get("importe"), float | bool):
        raise ValidationError({"importe": "Usá un importe decimal exacto."})
    if nuevo_id and archivo:
        raise ValidationError("Elegí una versión existente o adjuntá un archivo nuevo.")
    form = CorreccionCobroForm(datos, {"archivo": archivo} if archivo else None)
    if not form.is_valid():
        raise ValidationError({k: list(v) for k, v in form.errors.items()})
    d = form.cleaned_data
    try:
        with operacion_documental() as escrituras:
            TramiteBase.objects.select_for_update().get(pk=solicitud.tramite_base_id)
            solicitud = autorizar_cobro(actor, numero)
            previo = (
                CobroExterno.objects.select_for_update()
                .filter(pk=cobro_id, solicitud_id=numero)
                .first()
            )
            if previo is None:
                raise ConflictoConcurrenciaError("El cobro cambió. Recargá la solicitud.")
            if not puede_corregir_cobro(actor, previo):
                raise PermissionDenied("No tenés permiso para corregir este cobro.")
            if resultado_esperado is not None and resultado_esperado != previo.resultado:
                raise ConflictoConcurrenciaError(
                    "El estado del ingreso cambió. Recargá el formulario."
                )
            if (
                revision_esperada is not None
                and revision_esperada != diagnostico(solicitud)["revision"]
            ):
                raise ConflictoConcurrenciaError("El trámite cambió. Recargá el formulario.")
            campos = {campo: d[campo] for campo in DATOS_COBRO}
            if previo.resultado == "CONFIRMADO" and all(
                valor == getattr(previo, campo) for campo, valor in campos.items()
            ):
                raise ValidationError(
                    "Modificá al menos un dato del ingreso confirmado para corregirlo."
                )
            if (
                CobroExterno.objects.exclude(pk=previo.pk)
                .filter(medio=d["medio"], numero_operacion=d["numero_operacion"])
                .exists()
            ):
                raise ValidationError("Esa operación ya está registrada en otro cobro.")
            anterior = respaldo_actual(previo)
            ultima_version = Documento.objects.filter(serie=anterior.serie).latest("version")
            fuente = anterior
            if nuevo_id:
                if not puede_actualizar_respaldo(actor):
                    raise PermissionDenied("No tenés permiso para vincular una versión existente.")
                fuente = sucesores_respaldo_cobro(actor, anterior).filter(pk=nuevo_id).first()
                if fuente is None:
                    raise ValidationError("Seleccioná una versión sucesora vigente y disponible.")
            if archivo is None:
                with almacenamiento().open(fuente.archivo, "rb") as origen:
                    archivo = SimpleUploadedFile(
                        fuente.nombre_original, origen.read(), fuente.formato
                    )
            interno = _puede_corregir_como_operador(actor, previo)
            if previo.resultado == "CONFIRMADO":
                RectificacionCobro.objects.create(
                    verificacion=previo.verificacion,
                    actor_id=actor.subject_id,
                    motivo=d["motivo"],
                )
            CobroExterno.objects.filter(pk=previo.pk).update(sustituido=True)
            documento = incorporar(
                actor=actor,
                referencia=f"facturacion:{numero}",
                archivo=archivo,
                tipo="COMPROBANTE_COBRO",
                procedencia="EXTERNO_BANCO" if interno else "SOLICITANTE",
                reemplaza_id=ultima_version.pk,
                _escrituras=escrituras,
            )
            return CobroExterno.objects.create(
                solicitud=solicitud,
                **campos,
                documento=documento,
                actor_id=actor.subject_id,
                procedencia="INTERNO_COOPERADORA" if interno else "SOLICITANTE",
                reemplaza=previo,
                motivo_correccion=d["motivo"],
            )
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) in {
            "uq_cobro_operacion_global",
            "facturacion_cobroexterno_reemplaza_id_key",
        }:
            raise ConflictoConcurrenciaError("El cobro o la operación cambió. Recargá.") from exc
        raise
