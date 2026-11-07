"""Alta atómica de comprobante/PDF e historial, con autorización por solicitud."""

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from comunes.models import TramiteBase
from documentos.models import Documento
from documentos.operaciones import operacion_documental
from documentos.policy import TipoArchivoNoSoportado, validar_archivo
from documentos.revision import ConflictoRevision, revisar
from documentos.services import almacenamiento, incorporar
from identidad.services import has_capability

from .forms_comprobantes import DATOS_COMPROBANTE, ComprobanteExternoForm, ModificarComprobanteForm
from .models import ComprobanteExterno, SolicitudFacturacion
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles
from .workflow import ConflictoConcurrenciaError

TIPOS_DOCUMENTALES = {
    "FACTURA": "FACTURA_EMITIDA_XUBIO",
    "NOTA_CREDITO": "NOTA_CREDITO_XUBIO",
    "NOTA_DEBITO": "NOTA_DEBITO_XUBIO",
}


def puede_registrar_comprobante(actor):
    return has_capability(actor, "facturacion.registrar_factura_externa") and has_capability(
        actor, "documentos.incorporar"
    )


def autorizar_registro(actor, numero):
    solicitud = filtrar_solicitudes_visibles(actor).filter(pk=numero).first()
    if solicitud is None:
        raise ObjetoNoVisibleError
    from .seguimiento import exigir_abierta
    exigir_abierta(solicitud)
    if not puede_registrar_comprobante(actor):
        raise PermissionDenied("No tenés permiso para registrar comprobantes.")
    return solicitud


def resumen_comprobantes(solicitud):
    registros = list(solicitud.comprobantes.select_related("documento"))
    registros.sort(key=lambda comprobante: comprobante.tipo != "FACTURA")
    neto = sum(
        ((-c.importe if c.tipo == "NOTA_CREDITO" else c.importe) for c in registros),
        Decimal("0.00"),
    )
    return registros, neto


def puede_aceptar_al_registrar(actor):
    return has_capability(actor, "documentos.revisar") and has_capability(
        actor, "documentos.consultar_metadatos"
    )


def pdf_comprobante(archivo):
    validado = validar_archivo(archivo)
    if validado.formato != "application/pdf":
        raise TipoArchivoNoSoportado("El comprobante externo requiere un PDF.")
    return validado


def registrar_comprobante(*, actor, numero_publico, datos, archivo_pdf):
    autorizar_registro(actor, numero_publico)
    puede_aceptar = puede_aceptar_al_registrar(actor)
    aceptar = ComprobanteExternoForm.base_fields["aceptar_respaldo"].clean(
        datos.get("aceptar_respaldo")
    )
    if aceptar and not puede_aceptar:
        raise PermissionDenied(
            "No tenés permiso para aceptar el documento de respaldo al registrar."
        )
    if isinstance(datos.get("importe"), float | bool):
        raise ValidationError({"importe": "Usá un importe decimal exacto, sin flotantes."})
    form = ComprobanteExternoForm(
        datos, {"archivo_pdf": archivo_pdf} if archivo_pdf else None, puede_aceptar=puede_aceptar
    )
    if not form.is_valid():
        raise ValidationError({campo: list(errores) for campo, errores in form.errors.items()})
    limpio = form.cleaned_data
    archivo = pdf_comprobante(archivo_pdf)
    try:
        with operacion_documental() as escrituras:
            # Mismo orden que el recorrido de solicitud: cabecera -> solicitud -> documento.
            base = TramiteBase.objects.select_for_update().get(
                circuito="FACTURACION", numero_publico=numero_publico
            )
            solicitud = SolicitudFacturacion.objects.select_for_update().get(tramite_base=base)
            autorizar_registro(actor, numero_publico)
            factura = solicitud.comprobantes.filter(tipo="FACTURA").first()
            if limpio["tipo"] == "FACTURA":
                if factura:
                    raise ConflictoConcurrenciaError("Esta solicitud ya tiene una factura.")
                factura = None
            else:
                if factura is None:
                    raise ValidationError("Registrá primero la factura de esta solicitud.")
                if (limpio["cuit_emisor"], limpio["letra"]) != (factura.cuit_emisor, factura.letra):
                    raise ValidationError("La nota debe conservar emisor y letra de su factura.")
            identidad = {
                k: limpio[k]
                for k in (
                    "cuit_emisor",
                    "tipo",
                    "letra",
                    "punto_venta",
                    "numero",
                )
            }
            if ComprobanteExterno.objects.filter(**identidad).exists():
                raise ConflictoConcurrenciaError("Ese comprobante externo ya está registrado.")
            documento = incorporar(
                actor=actor,
                referencia=str(base.referencia),
                archivo=archivo,
                tipo=TIPOS_DOCUMENTALES[limpio["tipo"]],
                procedencia=limpio["procedencia"],
                _escrituras=escrituras,
            )
            comprobante = ComprobanteExterno.objects.create(
                solicitud=solicitud,
                documento=documento,
                factura_origen=factura,
                actor_id=actor.subject_id,
                procedencia=limpio["procedencia"],
                origen_aclaracion=limpio["origen_aclaracion"],
                fecha_emision=limpio["fecha_emision"],
                importe=limpio["importe"],
                **identidad,
            )
            if aceptar:
                revisar(
                    actor=actor,
                    documento_id=documento.pk,
                    resultado="ACEPTADO",
                    motivo="Conformidad del documento de respaldo al registrar el comprobante.",
                    revision_esperada=0,
                )
            return comprobante
    except ConflictoRevision as exc:
        raise ConflictoConcurrenciaError(str(exc)) from exc
    except IntegrityError as exc:
        causa = exc.__cause__
        if getattr(getattr(causa, "diag", None), "constraint_name", None) in {
            "uq_comprobante_identidad_externa",
            "uq_una_factura_por_solicitud",
        }:
            raise ConflictoConcurrenciaError(
                "El comprobante ya fue registrado. Recargá el detalle."
            ) from exc
        raise


def corregir_comprobante(*, actor, numero, comprobante_id, datos, archivo_pdf=None):
    from .seguimiento import (
        diagnostico,
        puede_actualizar_respaldo,
        respaldo_actual,
        sucesores_respaldo_comprobante,
    )

    solicitud = autorizar_registro(actor, numero)
    try:
        with operacion_documental() as escrituras:
            TramiteBase.objects.select_for_update().get(pk=solicitud.tramite_base_id)
            solicitud = autorizar_registro(actor, numero)
            previo = solicitud.comprobantes.select_for_update().filter(pk=comprobante_id).first()
            if previo is None or datos.get("revision") != diagnostico(solicitud)["revision"]:
                raise ConflictoConcurrenciaError("El trámite cambió. Recargá el formulario.")
            anterior = respaldo_actual(previo)
            puede_vincular = puede_actualizar_respaldo(actor)
            if datos.get("nuevo") and not puede_vincular:
                raise PermissionDenied("No tenés permiso para vincular una versión existente.")
            form = ModificarComprobanteForm(
                datos,
                {"archivo_pdf": archivo_pdf} if archivo_pdf else None,
                comprobante=previo,
                revision=datos["revision"],
                puede_corregir=True,
                puede_adjuntar=True,
                opciones=(
                    sucesores_respaldo_comprobante(actor, anterior) if puede_vincular else None
                ),
            )
            if not form.is_valid():
                raise ValidationError(
                    {campo: list(errores) for campo, errores in form.errors.items()}
                )
            limpio = form.cleaned_data
            campos = {campo: limpio[campo] for campo in DATOS_COMPROBANTE}
            if all(valor == getattr(previo, campo) for campo, valor in campos.items()):
                raise ValidationError("Modificá al menos un dato del comprobante.")
            factura = solicitud.comprobantes.filter(tipo="FACTURA").get()
            emisor = (limpio["cuit_emisor"], limpio["letra"])
            if previo.tipo == "FACTURA":
                if solicitud.comprobantes.exclude(tipo="FACTURA").exclude(
                    cuit_emisor=emisor[0], letra=emisor[1]
                ).exists():
                    raise ValidationError(
                        "El emisor y la letra deben coincidir con las notas registradas."
                    )
            elif emisor != (factura.cuit_emisor, factura.letra):
                raise ValidationError("La nota debe conservar emisor y letra de su factura.")

            identidad = {
                campo: limpio[campo] for campo in ("cuit_emisor", "letra", "punto_venta", "numero")
            }
            if ComprobanteExterno.objects.filter(tipo=previo.tipo, **identidad).exclude(
                pk=previo.pk
            ).exists():
                raise ValidationError("Ese comprobante externo ya está registrado.")

            fuente = limpio.get("nuevo") or anterior
            archivo = limpio["archivo_pdf"]
            if archivo is None:
                with almacenamiento().open(fuente.archivo, "rb") as origen:
                    archivo = SimpleUploadedFile(
                        fuente.nombre_original, origen.read(), fuente.formato
                    )
            ultima_version = Documento.objects.filter(serie=anterior.serie).latest("version")
            documento = incorporar(
                actor=actor,
                referencia=f"facturacion:{numero}",
                archivo=pdf_comprobante(archivo),
                tipo=anterior.tipo,
                procedencia=limpio["procedencia"],
                reemplaza_id=ultima_version.pk,
                _escrituras=escrituras,
            )
            ComprobanteExterno.objects.filter(pk=previo.pk).update(sustituido=True)
            return ComprobanteExterno.objects.create(
                solicitud=solicitud,
                tipo=previo.tipo,
                factura_origen=None if previo.tipo == "FACTURA" else factura,
                documento=documento,
                actor_id=actor.subject_id,
                reemplaza=previo,
                motivo_correccion=limpio["motivo"],
                **campos,
            )
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) in {
            "uq_comprobante_identidad_externa", "uq_una_factura_por_solicitud",
            "facturacion_comprobanteexterno_reemplaza_id_key",
        }:
            raise ConflictoConcurrenciaError("El comprobante cambió. Recargá el detalle.") from exc
        raise
