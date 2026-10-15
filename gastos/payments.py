"""Servicios y consultas para el circuito de pagos externos en gastos.

Mantiene persistencia, validación y consultas de pagos externos desacoplados
de decisiones y documentos según SPEC-011.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from gastos.auth import has_capability
from gastos.contracts import (
    TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
    DocumentVerificationError,
    DocumentVerificationPort,
)
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno
from gastos.queries import visible_expenses

# Formato decimal ASCII estricto admitido para importes: sin exponente, sin
# separadores de miles, sin guiones bajos y sin dígitos no ASCII.
_IMPORTE_DECIMAL_ESTRICTO = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
# Formato ISO calendario estricto YYYY-MM-DD (rechaza semana ISO, formato básico, etc.).
_FECHA_ISO_ESTRICTA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class PaymentError(Exception):
    """Excepción base para errores del circuito de pago externo."""


class PaymentExpenseNotFoundError(PaymentError):
    """Solicitud no encontrada o no visible para el actor (HTTP 404)."""


class PaymentPermissionDeniedError(PaymentError):
    """Actor no autorizado para registrar pago (HTTP 403)."""


class PaymentInvalidInputError(PaymentError):
    """Datos de entrada inválidos para el registro de pago (HTTP 400)."""


class PaymentInvalidExpenseStateError(PaymentError):
    """Estado de solicitud no permite registrar pago (HTTP 409)."""


class PaymentConflictError(PaymentError):
    """Conflicto con un pago existente que posee datos distintos (HTTP 409)."""


@dataclass(frozen=True, slots=True)
class PagoExternoConsulta:
    """Información de presentación de un pago externo para un gasto visible.

    Garantía de privacidad y separación documental:
    NO incluye la referencia documental opaca ni metadatos del documento.
    Toma actor y fecha_hora del evento autoritativo asociado.
    """

    id: int
    solicitud_id: int
    importe: Decimal
    moneda: str
    fecha_pago: date
    referencia_externa: str
    fecha_registro: datetime | None
    actor_id: int | None


def validate_payment_input(
    *,
    importe: Any,
    fecha_pago: Any,
    referencia_externa: Any,
    referencia_documental: Any,
) -> tuple[Decimal, date, str, str]:
    """Valida y normaliza rigurosamente los datos de entrada para un pago externo.

    Reglas estrictas:
    - Importe: sólo Decimal o string decimal ASCII sin exponente (rechaza bool, float, int).
      Rechaza no finitos (NaN, Inf), negativos y cero. Máximo 2 cifras fraccionarias sin redondeo
      silencioso. Máximo 12 dígitos en total (Decimal(12, 2)).
    - Fecha: sólo date o ISO YYYY-MM-DD (rechaza datetime). No inventa regla de fecha futura.
    - Referencias: estrictamente de tipo str (sin coerción con str()). La referencia externa
      recorta espacios exteriores; la referencia documental opaca se preserva exactamente.
      Ambas rechazan caracteres NUL, valores vacíos y longitudes mayores a 128 o 255 caracteres.
    """
    # 1. Validación estricta de Importe
    if (
        isinstance(importe, bool)
        or importe is None
        or isinstance(importe, (float, int))
    ):
        raise PaymentInvalidInputError(
            "El importe debe ser Decimal o string decimal ASCII (no se admiten bool, float ni int)."
        )

    if isinstance(importe, str):
        val_str = importe.strip()
        if not val_str:
            raise PaymentInvalidInputError("El importe no puede ser vacío.")
        if not _IMPORTE_DECIMAL_ESTRICTO.fullmatch(val_str):
            raise PaymentInvalidInputError(
                "El importe debe ser un string decimal ASCII sin exponente "
                "(sólo dígitos, signo opcional y un punto decimal)."
            )
        try:
            dec = Decimal(val_str)
        except InvalidOperation:
            raise PaymentInvalidInputError(
                "Formato numérico inválido para importe."
            ) from None
    elif isinstance(importe, Decimal):
        dec = importe
    else:
        raise PaymentInvalidInputError("Tipo de dato no admitido para el importe.")

    if not dec.is_finite():
        raise PaymentInvalidInputError("El importe debe ser un número finito.")

    if dec <= Decimal("0.00"):
        raise PaymentInvalidInputError("El importe debe ser estrictamente positivo.")

    # Verificación de sobreprecisión (máximo 2 cifras fraccionarias sin redondeo silencioso)
    exponent = dec.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise PaymentInvalidInputError(
            "El importe no puede tener más de 2 cifras fraccionarias (sobreprecisión no admitida)."
        )

    # Verificación de desbordamiento de dígitos (Decimal(12, 2) -> max 10 dígitos enteros)
    if dec > Decimal("9999999999.99"):
        raise PaymentInvalidInputError(
            "El importe excede el límite máximo permitido de 12 dígitos."
        )

    norm_importe = dec.quantize(Decimal("0.01"))

    # 2. Validación estricta de Fecha de Pago
    if isinstance(fecha_pago, datetime):
        raise PaymentInvalidInputError(
            "No se admite datetime en la fecha de pago; use date o cadena ISO YYYY-MM-DD."
        )

    if isinstance(fecha_pago, bool) or fecha_pago is None:
        raise PaymentInvalidInputError("La fecha de pago es obligatoria.")

    if isinstance(fecha_pago, date):
        norm_fecha = fecha_pago
    elif isinstance(fecha_pago, str):
        str_fecha = fecha_pago.strip()
        if not _FECHA_ISO_ESTRICTA.fullmatch(str_fecha):
            raise PaymentInvalidInputError(
                "Formato de fecha de pago inválido. Se requiere fecha ISO calendario YYYY-MM-DD."
            )
        try:
            norm_fecha = date.fromisoformat(str_fecha)
        except ValueError:
            raise PaymentInvalidInputError(
                f"Fecha de pago inexistente en el calendario: '{fecha_pago}'."
            ) from None
    else:
        raise PaymentInvalidInputError(
            "Tipo de dato no admitido para la fecha de pago (sólo date o cadena ISO YYYY-MM-DD)."
        )

    # 3. Validación estricta de Referencia Externa (str sin coerción)
    if not isinstance(referencia_externa, str) or isinstance(referencia_externa, bool):
        raise PaymentInvalidInputError("La referencia externa debe ser de tipo str.")

    if "\x00" in referencia_externa:
        raise PaymentInvalidInputError("La referencia externa no puede contener caracteres nulos.")

    norm_ref = referencia_externa.strip()
    if not norm_ref:
        raise PaymentInvalidInputError(
            "La referencia externa no puede ser vacía ni contener sólo espacios."
        )

    if len(norm_ref) > 128:
        raise PaymentInvalidInputError(
            f"La referencia externa excede el límite de 128 caracteres (longitud: {len(norm_ref)})."
        )

    # 4. Validación estricta de Referencia Documental (str sin coerción)
    if not isinstance(referencia_documental, str) or isinstance(referencia_documental, bool):
        raise PaymentInvalidInputError("La referencia documental debe ser de tipo str.")

    if "\x00" in referencia_documental:
        raise PaymentInvalidInputError(
            "La referencia documental no puede contener caracteres nulos."
        )

    referencia_doc = referencia_documental
    if not referencia_doc.strip():
        raise PaymentInvalidInputError(
            "La referencia documental no puede ser vacía ni contener sólo espacios."
        )

    if len(referencia_doc) > 255:
        raise PaymentInvalidInputError(
            f"La referencia documental excede el límite de 255 caracteres "
            f"(longitud: {len(referencia_doc)})."
        )

    return norm_importe, norm_fecha, norm_ref, referencia_doc


def calcular_huella_pago(
    *,
    solicitud_id: int,
    importe: Decimal,
    moneda: str,
    fecha_pago: date,
    referencia_externa: str,
    referencia_documental: str,
) -> str:
    """Calcula una huella SHA-256 canónica sin ambigüedad a partir de los valores normalizados."""
    payload = json.dumps(
        {
            "fecha_pago": fecha_pago.isoformat(),
            "importe": f"{importe.quantize(Decimal('0.01')):.2f}",
            "moneda": moneda,
            "referencia_documental": referencia_documental,
            "referencia_externa": referencia_externa,
            "solicitud_id": solicitud_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@transaction.atomic
def registrar_pago_externo(
    *,
    actor: Any,
    solicitud_id: int,
    importe: Any,
    fecha_pago: Any,
    referencia_externa: Any,
    referencia_documental: Any,
    document_provider: DocumentVerificationPort | None = None,
) -> PagoExterno:
    """Registra de forma atómica un pago externo sobre una solicitud de gasto visible y aceptada.

    Secuencia de ejecución y garantías:
    1. Bloqueo pesimista sobre la fila visible del gasto con select_for_update.
       Precedencia: si la solicitud es ajena o inexistente, lanza 404 antes de comprobar permisos.
    2. Comprobación de capacidad 'gastos.registrar_pago' (403). gastos.decidir NO concede pago.
    3. Exigencia de estado ACEPTADA (409).
    4. Validación y normalización estricta de importes, fecha y referencias (400).
    5. Comprobación de idempotencia sobre la fila de pago asociada:
       - Si ya existe un pago idéntico (compara huella Y todos los campos normalizados), retorna el
         pago previo sin invocar ni requerir document_provider y sin duplicar eventos.
       - Si existe un pago previo pero con datos distintos, emite PaymentConflictError (409).
    6. Sólo al crear un nuevo registro se valida la dependencia de document_provider y se invoca
       dentro de esta transacción. Orden de lock: gasto primero, versión documental después.
       Valida que la evidencia (proof) devuelta coincida exactamente en solicitud_id,
       referencia documental y tipo admitido.
    7. Escritura conjunta atómica de PagoExterno y EventoPagoExterno (con actor y timestamp
       autoritativos). Rollback total ante cualquier falla en el guardado del pago o del evento.
    """
    if actor is None:
        raise PaymentPermissionDeniedError("Se requiere un actor autenticado.")

    # 1. Obtener y bloquear exclusivamente sobre visible_expenses(actor)
    # Precedencia estricta: objeto ajeno o inexistente genera 404 antes de comprobar permisos (403)
    solicitud = (
        visible_expenses(actor)
        .select_for_update()
        .filter(pk=solicitud_id)
        .first()
    )
    if solicitud is None:
        raise PaymentExpenseNotFoundError(f"Solicitud #{solicitud_id} no visible o inexistente.")

    # 2. Comprobar capacidad específica de registro de pago
    if not has_capability(actor, "gastos.registrar_pago"):
        raise PaymentPermissionDeniedError(
            "El actor no posee la capacidad 'gastos.registrar_pago'."
        )

    # 3. Exigir estado ACEPTADA
    if solicitud.estado != EstadoSolicitud.ACEPTADA:
        raise PaymentInvalidExpenseStateError(
            f"La solicitud #{solicitud_id} se encuentra en estado '{solicitud.estado}'; "
            "sólo se pueden registrar pagos sobre solicitudes aceptadas."
        )

    # 4. Validar y normalizar parámetros
    valid_importe, valid_fecha, valid_ref_ext, valid_doc_ref = validate_payment_input(
        importe=importe,
        fecha_pago=fecha_pago,
        referencia_externa=referencia_externa,
        referencia_documental=referencia_documental,
    )
    huella = calcular_huella_pago(
        solicitud_id=solicitud.pk,
        importe=valid_importe,
        moneda="ARS",
        fecha_pago=valid_fecha,
        referencia_externa=valid_ref_ext,
        referencia_documental=valid_doc_ref,
    )

    # 5. Comprobar reenvíos previos sobre la fila bloqueada
    pago_existente = PagoExterno.objects.filter(solicitud=solicitud).first()
    if pago_existente is not None:
        es_identico = (
            pago_existente.huella_idempotencia == huella
            and pago_existente.importe == valid_importe
            and pago_existente.moneda == "ARS"
            and pago_existente.fecha_pago == valid_fecha
            and pago_existente.referencia_externa == valid_ref_ext
            and pago_existente.referencia_documental == valid_doc_ref
        )
        if es_identico:
            # Reenvío idéntico: reautorizado con éxito, retorna sin requerir provider
            return pago_existente
        # Conflicto con datos distintos
        raise PaymentConflictError(
            f"Ya existe un pago registrado para la solicitud #{solicitud_id} con datos diferentes."
        )

    # 6. Sólo para nuevo registro: validar proveedor documental y verificar evidencia exacta
    if document_provider is None or not hasattr(
        document_provider, "verificar_y_bloquear_documento"
    ):
        raise PaymentInvalidInputError("Se requiere un puerto proveedor documental obligatorio.")

    doc_verificado = document_provider.verificar_y_bloquear_documento(
        actor=actor,
        gasto=solicitud,
        referencia_documental=valid_doc_ref,
        tipos_admitidos=TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
    )
    if doc_verificado is None:
        raise DocumentVerificationError(
            "El proveedor no devolvió evidencia documental verificada."
        )

    evidencia_solicitud_id = getattr(doc_verificado, "solicitud_id", None)
    if evidencia_solicitud_id is None:
        evidencia_solicitud_id = getattr(doc_verificado, "gasto_id", None)

    if (
        evidencia_solicitud_id != solicitud.pk
        or getattr(doc_verificado, "referencia_documental", None) != valid_doc_ref
        or getattr(doc_verificado, "tipo_documento", None)
        not in TIPOS_DOCUMENTO_ADMITIDOS_PAGO
    ):
        raise DocumentVerificationError(
            "La evidencia documental no corresponde al gasto bloqueado, a la referencia "
            "solicitada o posee un tipo no admitido."
        )

    # 7. Escritura conjunta atómica de pago y evento autoritativo
    pago = PagoExterno.objects.create(
        solicitud=solicitud,
        importe=valid_importe,
        moneda="ARS",
        fecha_pago=valid_fecha,
        referencia_externa=valid_ref_ext,
        referencia_documental=doc_verificado.referencia_documental,
        huella_idempotencia=huella,
    )

    EventoPagoExterno.objects.create(
        pago=pago,
        tipo_evento="pago_externo_registrado",
        actor_id=actor.subject_id,
    )

    return pago


def consultar_pago_externo(
    actor: Any,
    solicitud_id: int,
) -> PagoExternoConsulta | None:
    """Consulta pura para leer el pago externo asociado a una solicitud visible.

    Garantías:
    - Consulta pura sin efectos secundarios ni escrituras en base de datos.
    - Exige que la solicitud sea visible para el actor según visible_expenses(actor).
    - Si la solicitud no es visible o no existe para el actor: retorna None sin filtrar
      existencia a terceros.
    - Si la solicitud no tiene pago registrado: retorna None.
    - Si la solicitud tiene pago registrado: retorna PagoExternoConsulta, OMITIENDO
      la referencia documental para evitar su exposición genérica.
    """
    if actor is None:
        return None

    solicitud = visible_expenses(actor).filter(pk=solicitud_id).first()
    if solicitud is None:
        return None

    pago = (
        PagoExterno.objects.filter(solicitud=solicitud)
        .select_related("evento")
        .first()
    )
    if pago is None:
        return None

    evento = getattr(pago, "evento", None)
    fecha_reg = evento.fecha_hora if evento else None
    actor_id = evento.actor_id if evento else None

    return PagoExternoConsulta(
        id=pago.pk,
        solicitud_id=pago.solicitud_id,
        importe=pago.importe,
        moneda=pago.moneda,
        fecha_pago=pago.fecha_pago,
        referencia_externa=pago.referencia_externa,
        fecha_registro=fecha_reg,
        actor_id=actor_id,
    )
