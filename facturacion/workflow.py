"""Operaciones funcionales de #23: autorización, bloqueo, snapshots y archivos.

La fábrica técnica de services.py permanece separada para contratos de #22.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.utils import timezone

from comunes.models import TramiteBase
from documentos import services as documentos
from documentos.operaciones import operacion_documental
from documentos.policy import validar_archivo
from identidad.services import Actor, has_capability

from .forms import SolicitudFacturacionForm
from .models import EstadoSolicitudFacturacion as Estado
from .models import EventoFacturacion, SolicitudFacturacion
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles, verificar_accion
from .services import crear_solicitud_tecnica

SALT = "facturacion.presentar.v1"
DATOS_MODELO = (
    "presento_comprobante_pago",
    "nombre_solicitante",
    "cuit_receptor",
    "nombre_receptor",
    "condicion_iva",
    "email_envio_factura",
    "detalle_factura",
    "importe_factura",
    "producto_servicio",
    "modalidad_cobro",
    "observaciones",
    "fecha_operacion_declarada",
    "numero_operacion_declarado",
)


class ConflictoConcurrenciaError(Exception):
    pass


class PresentacionDuplicadaError(ConflictoConcurrenciaError):
    pass


def emitir_token(actor):
    import uuid

    return signing.Signer(salt=SALT).sign(f"{actor.subject_id}:{uuid.uuid4()}")


def verificar_token(actor, token):
    try:
        sujeto, clave = signing.Signer(salt=SALT).unsign(token).split(":")
        if sujeto != str(actor.subject_id):
            raise ValueError
        return UUID(clave)
    except (signing.BadSignature, ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("El formulario no es válido. Abrí uno nuevo.") from exc


def _version(value):
    if type(value) is not int or value < 1:
        raise ValidationError("La versión esperada debe ser un entero positivo.")


def _datos(datos, archivo, documento_actual=False):
    # Form valida tipos/longitudes/catálogos también al invocar el servicio en Python.
    form = SolicitudFacturacionForm(
        datos,
        {"archivo_comprobante": archivo} if archivo is not None else None,
        documento_actual=documento_actual,
    )
    if not form.is_valid():
        raise ValidationError({k: list(v) for k, v in form.errors.items()})
    limpio = form.cleaned_data
    validado = validar_archivo(archivo) if archivo is not None else None
    return limpio, validado


def _asignar(solicitud, limpio):
    for campo in DATOS_MODELO:
        setattr(solicitud, campo, limpio[campo])
    solicitud.tramite_base.centro_costo_codigo = limpio["centro_costo"]


def _serializar(solicitud):
    datos = {campo: getattr(solicitud, campo) for campo in DATOS_MODELO}
    datos.update(
        centro_costo=solicitud.centro_costo,
        estado=solicitud.estado,
        version_concurrencia=solicitud.version_concurrencia,
        correo_solicitante=solicitud.correo_solicitante,
        fecha_presentacion=solicitud.fecha_presentacion,
    )
    doc = solicitud.documento_comprobante_inicial
    datos["documento_comprobante_inicial"] = (
        None
        if doc is None
        else {
            "id": doc.pk,
            "tipo": doc.tipo,
            "serie": str(doc.serie),
            "version": doc.version,
            "referencia_version": str(doc.referencia_version),
        }
    )
    datos["observacion_vigente"] = solicitud.observacion_vigente
    for campo, value in datos.items():
        if isinstance(value, Decimal):
            datos[campo] = format(value, ".2f")
        elif isinstance(value, datetime | date):
            datos[campo] = value.isoformat()
    return datos


def _evento(solicitud, actor, tipo, antes=None, observacion=None, nota=None):
    return EventoFacturacion.objects.create(
        solicitud=solicitud,
        actor_id=actor.subject_id,
        tipo_evento=tipo,
        estado_resultante=solicitud.estado,
        motivo_o_detalle=solicitud.observacion_vigente if tipo == "OBSERVACION" else nota or "",
        snapshot_datos={
            "esquema_version": 1,
            "tipo_evento": tipo,
            "version_anterior": antes["version_concurrencia"] if antes else None,
            "version_resultante": solicitud.version_concurrencia,
            "antes": antes,
            "despues": _serializar(solicitud),
            "observacion_atendida": observacion,
            "nota_correccion": nota,
        },
    )


def _validar_modelo(solicitud):
    # La clave se comprueba con constraint SQL nombrada, incluso en carreras.
    solicitud.full_clean(exclude=["clave_idempotencia"])


def _adjuntar(solicitud, actor, limpio, archivo, escrituras):
    actual = solicitud.documento_comprobante_inicial
    if archivo is not None:
        if actual is not None:
            # El registro de cobro puede haber reemplazado su versión compartida.
            # La carga explícita continúa la serie vigente sin reescribir la declaración anterior.
            documentos.bloquear_serie(actual)
            actual = actual.__class__.objects.get(serie=actual.serie, sucesor__isnull=True)
        procedencia = (
            "EXTERNO_BANCO"
            if has_capability(actor, "facturacion.consultar_todas")
            else "SOLICITANTE"
        )
        solicitud.documento_comprobante_inicial = documentos.incorporar(
            actor=actor,
            referencia=str(solicitud.tramite_base.referencia),
            archivo=archivo,
            tipo="COMPROBANTE_COBRO",
            procedencia=procedencia,
            reemplaza_id=actual.pk if actual else None,
            _escrituras=escrituras,
        )
    elif limpio["retirar_comprobante"]:
        solicitud.documento_comprobante_inicial = None
    elif actual is not None:
        documentos.bloquear_serie(actual)
        if actual.tramite_base_id != solicitud.tramite_base_id:
            raise ValidationError("El respaldo no pertenece a la solicitud.")
        if (
            actual.tipo != "COMPROBANTE_COBRO"
            or actual.__class__.objects.filter(reemplaza=actual).exists()
        ):
            raise ValidationError("El respaldo fue reemplazado. Actualizá la solicitud.")


def presentar_solicitud_facturacion(*, actor, datos, token_presentacion, archivo_comprobante=None):
    if not has_capability(actor, "facturacion.presentar"):
        raise PermissionDenied("No tenés permiso para presentar.")
    clave = verificar_token(actor, token_presentacion)
    if SolicitudFacturacion.objects.filter(clave_idempotencia=clave).exists():
        raise PresentacionDuplicadaError("Esta presentación ya fue registrada.")
    if not actor.email_registrado:
        raise ValidationError("La cuenta necesita un correo de presentación configurado.")
    validate_email(actor.email_registrado)
    limpio, archivo = _datos(datos, archivo_comprobante)
    try:
        with operacion_documental() as escrituras:
            solicitud = crear_solicitud_tecnica(actor=actor)
            solicitud.clave_idempotencia = clave
            solicitud.save(update_fields=["clave_idempotencia"])
            _asignar(solicitud, limpio)
            solicitud.tramite_base.save(update_fields=["centro_costo_codigo"])
            _adjuntar(solicitud, actor, limpio, archivo, escrituras)
            solicitud.correo_solicitante = actor.email_registrado
            solicitud.fecha_presentacion = timezone.now()
            solicitud.estado = Estado.PRESENTADA
            _validar_modelo(solicitud)
            solicitud.save()
            _evento(solicitud, actor, "PRESENTACION")
    except IntegrityError as exc:
        causa = exc.__cause__
        if (
            getattr(causa, "sqlstate", None) == "23505"
            and getattr(getattr(causa, "diag", None), "constraint_name", None)
            == "uq_facturacion_clave_idempotencia"
        ):
            raise PresentacionDuplicadaError("Esta presentación ya fue registrada.") from exc
        raise
    return solicitud


def _bloquear(actor, numero, accion, version):
    # Un actor ajeno no toma bloqueos sobre trámites que no puede consultar.
    if not filtrar_solicitudes_visibles(actor).filter(pk=numero).exists():
        raise ObjetoNoVisibleError
    # Orden explícito común: cabecera -> solicitud -> raíz documental -> versión.
    base = (
        TramiteBase.objects.select_for_update()
        .filter(
            circuito="FACTURACION",
            numero_publico=numero,
        )
        .first()
    )
    if base is None:
        raise ObjetoNoVisibleError
    solicitud = (
        SolicitudFacturacion.objects.operativas()
        .select_for_update()
        .filter(tramite_base=base)
        .first()
    )
    if solicitud is None:
        raise ObjetoNoVisibleError
    solicitud.tramite_base = base
    verificar_accion(actor, solicitud, accion)
    _version(version)
    esperado = Estado.PRESENTADA if accion == "observar" else Estado.OBSERVADA
    if solicitud.estado != esperado or solicitud.version_concurrencia != version:
        raise ConflictoConcurrenciaError("La solicitud cambió. Recargá el detalle.")
    return solicitud


def observar_solicitud_facturacion(*, actor, numero_publico, motivo, version_esperada):
    from django.db import transaction

    if not isinstance(actor, Actor):
        raise PermissionDenied
    with transaction.atomic():
        solicitud = _bloquear(actor, numero_publico, "observar", version_esperada)
        if not isinstance(motivo, str) or not motivo.strip():
            raise ValidationError("El motivo de observación es obligatorio.")
        antes = _serializar(solicitud)
        solicitud.estado = Estado.OBSERVADA
        solicitud.observacion_vigente = motivo.strip()
        solicitud.version_concurrencia += 1
        solicitud.save(update_fields=["estado", "observacion_vigente", "version_concurrencia"])
        _evento(solicitud, actor, "OBSERVACION", antes)
    return solicitud


def corregir_solicitud_facturacion(
    *,
    actor,
    numero_publico,
    datos,
    version_esperada,
    nota_correccion="",
    archivo_comprobante=None,
):
    if not isinstance(actor, Actor):
        raise PermissionDenied
    with operacion_documental() as escrituras:
        solicitud = _bloquear(actor, numero_publico, "corregir", version_esperada)
        limpio, archivo = _datos(
            datos, archivo_comprobante, bool(solicitud.documento_comprobante_inicial_id)
        )
        if not isinstance(nota_correccion, str):
            raise ValidationError("La nota de corrección debe ser texto.")
        antes = _serializar(solicitud)
        observacion = solicitud.observacion_vigente
        _asignar(solicitud, limpio)
        _adjuntar(solicitud, actor, limpio, archivo, escrituras)
        solicitud.tramite_base.save(update_fields=["centro_costo_codigo"])
        solicitud.estado = Estado.PRESENTADA
        solicitud.observacion_vigente = ""
        solicitud.version_concurrencia += 1
        _validar_modelo(solicitud)
        solicitud.save()
        _evento(solicitud, actor, "CORRECCION", antes, observacion, nota_correccion.strip())
    return solicitud
