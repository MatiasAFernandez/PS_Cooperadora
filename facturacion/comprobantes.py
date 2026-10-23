"""Alta atómica de comprobante/PDF e historial, con autorización por solicitud."""

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError

from comunes.models import TramiteBase
from documentos.operaciones import operacion_documental
from documentos.policy import ArchivoInvalido, validar_archivo
from documentos.services import incorporar
from identidad.services import has_capability

from .forms_comprobantes import ComprobanteExternoForm
from .models import ComprobanteExterno, SolicitudFacturacion
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles
from .workflow import ConflictoConcurrenciaError

TIPOS_DOCUMENTALES = {
    "FACTURA": "FACTURA_EMITIDA_XUBIO",
    "NOTA_CREDITO": "NOTA_CREDITO_XUBIO",
    "NOTA_DEBITO": "NOTA_DEBITO_XUBIO",
}


def autorizar_registro(actor, numero):
    solicitud = filtrar_solicitudes_visibles(actor).filter(pk=numero).first()
    if solicitud is None:
        raise ObjetoNoVisibleError
    from .seguimiento import exigir_abierta
    exigir_abierta(solicitud)
    for capacidad in ("facturacion.registrar_factura_externa", "documentos.incorporar"):
        if not has_capability(actor, capacidad):
            raise PermissionDenied("No tenés permiso para registrar comprobantes.")
    return solicitud


def resumen_comprobantes(solicitud):
    registros = list(solicitud.comprobantes.select_related("documento", "factura_origen"))
    neto = sum(
        ((-c.importe if c.tipo == "NOTA_CREDITO" else c.importe) for c in registros),
        Decimal("0.00"),
    )
    return registros, neto


def registrar_comprobante(*, actor, numero_publico, datos, archivo_pdf):
    autorizar_registro(actor, numero_publico)
    if isinstance(datos.get("importe"), float | bool):
        raise ValidationError({"importe": "Usá un importe decimal exacto, sin flotantes."})
    form = ComprobanteExternoForm(datos, {"archivo_pdf": archivo_pdf} if archivo_pdf else None)
    if not form.is_valid():
        raise ValidationError({campo: list(errores) for campo, errores in form.errors.items()})
    limpio = form.cleaned_data
    archivo = validar_archivo(archivo_pdf)
    if archivo.formato != "application/pdf":
        raise ArchivoInvalido("El comprobante externo requiere un PDF.")
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
                procedencia="EXTERNO_XUBIO",
                _escrituras=escrituras,
            )
            return ComprobanteExterno.objects.create(
                solicitud=solicitud,
                documento=documento,
                factura_origen=factura,
                actor_id=actor.subject_id,
                fecha_emision=limpio["fecha_emision"],
                importe=limpio["importe"],
                **identidad,
            )
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
