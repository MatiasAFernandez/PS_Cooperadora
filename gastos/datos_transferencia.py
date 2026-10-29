"""Datos operativos de transferencia del gasto (SPEC-013).

Las revisiones son append-only y pertenecen al mismo gasto. La lectura se
limita al titular visible o a un actor de pago que ya puede ver el gasto; la
escritura se limita al titular con ``gastos.presentar`` antes del pago. Este
módulo no modifica identidad, documentos ni el contrato C03, y no ejecuta
operaciones bancarias.
"""

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from gastos.auth import has_capability
from gastos.models import (
    EstadoSolicitud,
    PagoExterno,
    RevisionDatosTransferencia,
    SolicitudGasto,
)
from gastos.queries import visible_expenses

CAMPOS_DATOS_TRANSFERENCIA: tuple[str, ...] = (
    "titular_nombre",
    "identificacion",
    "cbu_alias",
    "correo_comprobante",
    "centro_costo",
)

ETIQUETAS_DATOS_TRANSFERENCIA: dict[str, str] = {
    "titular_nombre": "Titular o beneficiario",
    "identificacion": "Identificación informada",
    "cbu_alias": "CBU o alias",
    "correo_comprobante": "Correo para el comprobante",
    "centro_costo": "Centro de costo informado",
}

LONGITUDES_DATOS_TRANSFERENCIA: dict[str, int] = {
    "titular_nombre": 200,
    "identificacion": 100,
    "cbu_alias": 128,
    "correo_comprobante": 254,
    "centro_costo": 100,
}

MENSAJE_CBU_ALIAS_FRECUENTE = (
    "«frecuente» no es un CBU ni un alias: ingresá el CBU o alias real informado."
)
MENSAJE_CORREO_COMPROBANTE_INVALIDO = (
    "Ingresá un correo de destino válido, por ejemplo nombre@dominio.test."
)


class DatosTransferenciaError(Exception):
    """Excepción base del circuito de datos de transferencia."""


class DatosTransferenciaNotFoundError(DatosTransferenciaError):
    """Gasto inexistente o no visible para el actor (HTTP 404)."""


class DatosTransferenciaPermissionDeniedError(DatosTransferenciaError):
    """El actor no puede leer o escribir estos datos (HTTP 403)."""


class DatosTransferenciaInvalidInputError(DatosTransferenciaError):
    """Bloque incompleto o con valores inválidos (HTTP 400)."""

    def __init__(self, mensaje: str, *, campos_faltantes: tuple[str, ...] = ()) -> None:
        super().__init__(mensaje)
        self.campos_faltantes = campos_faltantes


class DatosTransferenciaBloqueadaError(DatosTransferenciaError):
    """La solicitud rechazada o el pago ya registrado impiden una revisión (HTTP 409)."""


def es_cbu_alias_frecuente(valor: str) -> bool:
    """Detecta el literal «frecuente» sin distinguir mayúsculas ni espacios exteriores."""
    return valor.strip().casefold() == "frecuente"


def validar_datos_transferencia(
    datos: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    """Valida un bloque completo o vacío y devuelve sus valores normalizados.

    ``None`` y un bloque con todos los campos vacíos se consideran ausencia de
    datos. Un bloque parcial o con valores no textuales/nulos se rechaza. El
    correo de destino debe tener sintaxis válida y el CBU/alias no puede ser el
    literal «frecuente». Los valores se conservan recortados, sin copiarlos del
    correo de la sesión.
    """
    if datos is None:
        return None
    if not isinstance(datos, Mapping):
        raise DatosTransferenciaInvalidInputError(
            "Los datos de transferencia deben informarse como un conjunto de campos."
        )

    valores: dict[str, str] = {}
    for campo in CAMPOS_DATOS_TRANSFERENCIA:
        valor = datos.get(campo, "")
        if valor is None:
            valor = ""
        if not isinstance(valor, str):
            raise DatosTransferenciaInvalidInputError(
                f"El campo «{ETIQUETAS_DATOS_TRANSFERENCIA[campo]}» debe ser texto."
            )
        if "\x00" in valor:
            raise DatosTransferenciaInvalidInputError(
                "Los datos de transferencia no pueden contener caracteres nulos."
            )
        valor = valor.strip()
        limite = LONGITUDES_DATOS_TRANSFERENCIA[campo]
        if len(valor) > limite:
            raise DatosTransferenciaInvalidInputError(
                f"El campo «{ETIQUETAS_DATOS_TRANSFERENCIA[campo]}» supera "
                f"el máximo de {limite} caracteres."
            )
        valores[campo] = valor

    if not any(valores.values()):
        return None

    if es_cbu_alias_frecuente(valores["cbu_alias"]):
        raise DatosTransferenciaInvalidInputError(MENSAJE_CBU_ALIAS_FRECUENTE)

    if valores["correo_comprobante"]:
        try:
            validate_email(valores["correo_comprobante"])
        except ValidationError as exc:
            raise DatosTransferenciaInvalidInputError(
                MENSAJE_CORREO_COMPROBANTE_INVALIDO
            ) from exc

    faltantes = tuple(campo for campo in CAMPOS_DATOS_TRANSFERENCIA if not valores[campo])
    if faltantes:
        detalle = ", ".join(ETIQUETAS_DATOS_TRANSFERENCIA[campo] for campo in faltantes)
        raise DatosTransferenciaInvalidInputError(
            "Si completás el bloque de transferencia, todos sus datos son obligatorios. "
            f"Falta: {detalle}.",
            campos_faltantes=faltantes,
        )

    return valores


def datos_de_revision(revision: RevisionDatosTransferencia) -> dict[str, str]:
    """Devuelve sólo los campos operativos de una revisión para un formulario."""
    return {campo: getattr(revision, campo) for campo in CAMPOS_DATOS_TRANSFERENCIA}


def puede_consultar_datos_transferencia(actor: Any, gasto: SolicitudGasto) -> bool:
    """Autoriza lectura sensible: titular visible o actor de pago con visibilidad.

    ``gastos.consultar_todas`` por sí sola no concede acceso a estos datos.
    """
    if actor is None or gasto is None:
        return False
    if not visible_expenses(actor).filter(pk=gasto.pk).exists():
        return False
    return gasto.solicitante_id == actor.subject_id or has_capability(
        actor, "gastos.registrar_pago"
    )


def consultar_revisiones_datos_transferencia(
    actor: Any, solicitud_id: int
) -> tuple[RevisionDatosTransferencia, ...] | None:
    """Lee las revisiones autorizadas o devuelve ``None`` sin revelar datos.

    Un titular visible recibe su historial, incluso vacío. Un actor con
    ``gastos.registrar_pago`` sólo recibe datos si el gasto ya es visible por
    los controles existentes. Cualquier otro caso devuelve ``None``.
    """
    if actor is None:
        return None

    gasto = visible_expenses(actor).filter(pk=solicitud_id).first()
    if gasto is None:
        return None
    if gasto.solicitante_id != actor.subject_id and not has_capability(
        actor, "gastos.registrar_pago"
    ):
        return None

    return tuple(
        RevisionDatosTransferencia.objects.filter(solicitud_id=gasto.pk).order_by(
            "numero_revision"
        )
    )


def puede_editar_datos_transferencia(
    actor: Any,
    gasto: SolicitudGasto,
    *,
    pago_registrado: bool,
) -> bool:
    """Indica si el titular puede agregar o corregir datos en este momento."""
    if actor is None or gasto is None:
        return False
    if gasto.solicitante_id != actor.subject_id:
        return False
    if not has_capability(actor, "gastos.presentar"):
        return False
    if gasto.estado == EstadoSolicitud.RECHAZADA or pago_registrado:
        return False
    return visible_expenses(actor).filter(pk=gasto.pk).exists()


@transaction.atomic
def registrar_revision_datos_transferencia(
    *,
    actor: Any,
    solicitud_id: int,
    datos: Mapping[str, Any] | None,
) -> RevisionDatosTransferencia:
    """Registra una revisión nueva del titular, serializada con el pago.

    Pasos:
    1. Bloquea la fila del gasto visible (404 si es ajeno o inexistente).
    2. Exige que el actor sea el titular y tenga ``gastos.presentar`` (403).
    3. Rechaza una revisión si la solicitud fue rechazada o ya tiene pago (409).
    4. Valida el bloque completo (400) y crea la revisión con actor/hora de servidor.

    El bloqueo sobre ``SolicitudGasto`` es el mismo que usa
    ``registrar_pago_externo``; si el pago confirmó primero, no se escribe una
    revisión nueva.
    """
    if actor is None:
        raise DatosTransferenciaPermissionDeniedError("Se requiere un actor autenticado.")

    solicitud = (
        visible_expenses(actor).select_for_update().filter(pk=solicitud_id).first()
    )
    if solicitud is None:
        raise DatosTransferenciaNotFoundError(
            f"Solicitud #{solicitud_id} no visible o inexistente."
        )

    if solicitud.solicitante_id != actor.subject_id:
        raise DatosTransferenciaPermissionDeniedError(
            "Sólo el titular del gasto puede informar o corregir estos datos."
        )
    if not has_capability(actor, "gastos.presentar"):
        raise DatosTransferenciaPermissionDeniedError(
            "El actor no posee la capacidad 'gastos.presentar'."
        )

    if solicitud.estado == EstadoSolicitud.RECHAZADA:
        raise DatosTransferenciaBloqueadaError(
            "La solicitud fue rechazada y no admite nuevos datos de transferencia."
        )
    if PagoExterno.objects.filter(solicitud_id=solicitud.pk).exists():
        raise DatosTransferenciaBloqueadaError(
            "La solicitud ya tiene un pago registrado; no se corrigen datos "
            "posteriores en esta demo."
        )

    valores = validar_datos_transferencia(datos)
    if valores is None:
        raise DatosTransferenciaInvalidInputError(
            "Ingresá los datos completos de transferencia para guardar una revisión."
        )

    ultimo_numero = (
        RevisionDatosTransferencia.objects.filter(solicitud_id=solicitud.pk)
        .order_by("-numero_revision")
        .values_list("numero_revision", flat=True)
        .first()
        or 0
    )
    return RevisionDatosTransferencia.objects.create(
        solicitud=solicitud,
        numero_revision=ultimo_numero + 1,
        actor_id=actor.subject_id,
        **valores,
    )
