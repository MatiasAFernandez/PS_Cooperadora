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

from django.utils.formats import date_format

from gastos.auth import has_capability
from gastos.contracts import (
    DocumentVerificationError,
    DocumentVerificationPort,
    tipos_documento_admitidos_para_flujo,
)
from gastos.models import (
    EstadoSolicitud,
    EventoPagoExterno,
    PagoExterno,
    PagoExternoCambio,
    PagoExternoOriginal,
    formatear_importe_es_ar,
)
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


class PaymentVersionConflictError(PaymentConflictError):
    """La versión esperada del pago ya no es la vigente (HTTP 409)."""


class PaymentDocumentRequiredError(PaymentInvalidInputError):
    """Falta el comprobante bancario PDF o la decisión ATP exigida."""


@dataclass(frozen=True, slots=True)
class PagoExternoConsulta:
    """Información de presentación de un pago externo para un gasto visible.

    Garantía de privacidad y separación documental:
    NO incluye la referencia documental opaca ni metadatos del documento.
    Toma actor y fecha_hora del evento autoritativo asociado.
    Los identificadores/nombres documentales sólo se completan cuando el actor
    puede consultar metadatos; la presencia documental se informa como hecho.
    """

    id: int
    solicitud_id: int
    importe: Decimal
    moneda: str
    fecha_pago: date
    referencia_externa: str
    fecha_registro: datetime | None
    actor_id: int | None
    monto_bruto: Decimal = Decimal("0.00")
    monto_retencion_atp: Decimal = Decimal("0.00")
    referencia_atp: str = ""
    version: int = 1
    tiene_comprobante_bancario: bool = False
    comprobante_bancario_id: int | None = None
    comprobante_bancario_nombre: str = ""
    comprobante_bancario_tamano: int | None = None
    tiene_constancia_atp: bool = False
    constancia_atp_id: int | None = None
    constancia_atp_nombre: str = ""
    constancia_atp_tamano: int | None = None
    constancia_atp_pendiente: bool = False
    es_registro_legado: bool = False


@dataclass(frozen=True, slots=True)
class CambioPagoExternoConsulta:
    """Cambio legible del pago, con snapshots antes/después."""

    numero_version: int
    tipo: str
    tipo_mostrado: str
    motivo: str
    actor_id: int
    fecha_hora: datetime
    antes: str
    despues: str


def _validar_pdf(archivo: Any, *, etiqueta: str) -> Any:
    """Valida un archivo y exige específicamente PDF; no restringe otros circuitos."""
    from documentos.policy import ArchivoInvalido, validar_archivo

    try:
        validado = (
            archivo
            if hasattr(archivo, "sha256") and hasattr(archivo, "contenido")
            else validar_archivo(archivo)
        )
    except ArchivoInvalido as exc:
        raise PaymentInvalidInputError(f"{etiqueta}: {exc}") from exc
    if getattr(validado, "formato", None) != "application/pdf":
        raise PaymentInvalidInputError(f"{etiqueta} debe ser un archivo PDF.")
    return validado


def _validar_comprobante_bancario(
    archivo: Any, *, etiqueta: str = "El comprobante bancario"
) -> Any:
    """Valida comprobante bancario exigiendo PDF, JPG, JPEG o PNG con validación de contenido."""
    from documentos.policy import ArchivoInvalido, validar_archivo

    try:
        validado = (
            archivo
            if hasattr(archivo, "sha256") and hasattr(archivo, "contenido")
            else validar_archivo(archivo)
        )
    except ArchivoInvalido as exc:
        raise PaymentInvalidInputError(f"{etiqueta}: {exc}") from exc
    formatos_permitidos = {"application/pdf", "image/jpeg", "image/png"}
    if getattr(validado, "formato", None) not in formatos_permitidos:
        raise PaymentInvalidInputError(
            f"{etiqueta} debe ser un archivo PDF, JPG, JPEG o PNG."
        )
    return validado


def _normalizar_importes(
    *,
    monto_bruto: Any,
    monto_retencion_atp: Any = Decimal("0.00"),
    importe: Any = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Deriva el neto en servidor: bruto - retención, sin confiar en el cliente."""
    from gastos.forms import normalizar_importe_monetario

    if monto_bruto is None and importe is not None:
        monto_bruto = importe
    if monto_bruto is None:
        raise PaymentInvalidInputError("El monto bruto es obligatorio.")
    if isinstance(monto_bruto, str):
        monto_bruto = normalizar_importe_monetario(monto_bruto, "monto_bruto")
    bruto = _validar_decimal_estricto(monto_bruto, "monto_bruto", permitir_cero=False)
    retencion_raw = (
        Decimal("0.00") if monto_retencion_atp in (None, "") else monto_retencion_atp
    )
    if isinstance(retencion_raw, str):
        retencion_raw = normalizar_importe_monetario(retencion_raw, "monto_retencion_atp")
    retencion = _validar_decimal_estricto(
        retencion_raw, "monto_retencion_atp", permitir_cero=True
    )
    if retencion >= bruto:
        raise PaymentInvalidInputError("La retención debe ser menor que el monto bruto.")
    neto = (bruto - retencion).quantize(Decimal("0.01"))
    if neto <= Decimal("0.00"):
        raise PaymentInvalidInputError("El neto transferido debe ser estrictamente positivo.")
    if importe is not None:
        if isinstance(importe, str):
            importe = normalizar_importe_monetario(importe, "importe")
        neto_informado = _validar_decimal_estricto(importe, "importe", permitir_cero=False)
        if neto_informado != neto:
            raise PaymentInvalidInputError(
                "El importe neto no coincide con monto bruto menos retención."
            )
    return bruto, retencion, neto


def _snapshot_pago(pago: PagoExterno) -> dict[str, Any]:
    """Snapshot JSON cerrado del estado efectivo para el historial."""
    comprobante = pago.comprobante_bancario if pago.comprobante_bancario_id else None
    constancia = pago.constancia_atp if pago.constancia_atp_id else None

    def _doc(doc: Any) -> dict[str, Any] | None:
        if doc is None:
            return None
        return {
            "documento_id": doc.pk,
            "sha256": doc.sha256,
            "nombre": doc.nombre_original,
            "tamano": doc.tamano,
            "tipo": doc.tipo,
            "version": doc.version,
        }

    return {
        "version": pago.version,
        "fecha_pago": pago.fecha_pago.isoformat(),
        "monto_bruto": f"{Decimal(str(pago.monto_bruto)):.2f}",
        "monto_retencion_atp": f"{Decimal(str(pago.monto_retencion_atp)):.2f}",
        "importe": f"{Decimal(str(pago.importe)):.2f}",
        "moneda": pago.moneda,
        "referencia_externa": pago.referencia_externa,
        "referencia_documental": pago.referencia_documental,
        "referencia_atp": pago.referencia_atp,
        "comprobante": _doc(comprobante),
        "constancia": _doc(constancia),
        "comprobante_sha256": comprobante.sha256 if comprobante else "",
        "constancia_sha256": constancia.sha256 if constancia else "",
        "es_legado": pago.comprobante_bancario_id is None,
    }


def _snapshot_original(pago: PagoExterno) -> dict[str, Any]:
    """Representación original del alta; si falta, se usa el estado legado actual."""
    original = PagoExternoOriginal.objects.filter(pago_id=pago.pk).first()
    if original is None:
        return _snapshot_pago(pago)
    return {
        "version": 1,
        "fecha_pago": original.fecha_pago.isoformat(),
        "monto_bruto": f"{original.monto_bruto:.2f}",
        "monto_retencion_atp": f"{original.monto_retencion_atp:.2f}",
        "importe": f"{original.importe:.2f}",
        "moneda": original.moneda,
        "referencia_externa": original.referencia_externa,
        "referencia_documental": original.referencia_documental,
        "referencia_atp": original.referencia_atp,
        "comprobante_sha256": original.comprobante_sha256,
        "constancia_sha256": original.constancia_sha256,
        "comprobante_documento_id": original.comprobante_bancario_id,
        "constancia_documento_id": original.constancia_atp_id,
        "es_legado": original.es_legado,
    }


def _coincide_alta_original(
    pago: PagoExterno,
    *,
    fecha_pago: date,
    monto_bruto: Decimal,
    monto_retencion_atp: Decimal,
    importe: Decimal,
    referencia_externa: str,
    referencia_documental: str,
    referencia_atp: str,
    comprobante_sha256: str | None,
    constancia_sha256: str | None,
) -> bool:
    """Compara el reenvío con el alta original, nunca con una rectificación."""
    original = _snapshot_original(pago)
    if original.get("fecha_pago") != fecha_pago.isoformat():
        return False
    if original.get("monto_bruto") != f"{monto_bruto:.2f}":
        return False
    if original.get("monto_retencion_atp") != f"{monto_retencion_atp:.2f}":
        return False
    if original.get("importe") != f"{importe:.2f}":
        return False
    if original.get("referencia_externa") != referencia_externa:
        return False
    if original.get("referencia_documental") != referencia_documental:
        return False
    if original.get("referencia_atp") != referencia_atp:
        return False
    if comprobante_sha256:
        if original.get("comprobante_sha256") and (
            original["comprobante_sha256"] != comprobante_sha256
        ):
            return False
    if constancia_sha256:
        if original.get("constancia_sha256") and (
            original["constancia_sha256"] != constancia_sha256
        ):
            return False
    return True


def _exigir_capacidades_documentales(actor: Any) -> None:
    """Reutiliza las capacidades vigentes del servicio documental, sin ampliarlas."""
    if not has_capability(actor, "documentos.incorporar"):
        raise PaymentPermissionDeniedError(
            "El actor no posee la capacidad 'documentos.incorporar'."
        )
    # La clasificación EXTERNO_BANCO/EXTERNO_ATP del servicio documental exige
    # consulta global del circuito de gasto. No se modifica ese contrato.
    if not has_capability(actor, "gastos.consultar_todas"):
        raise PaymentPermissionDeniedError(
            "La incorporación documental del pago exige visibilidad global de gastos."
        )


def _exigir_proveedor(proveedor: Any) -> None:
    if proveedor is None or not hasattr(proveedor, "verificar_y_bloquear_documento"):
        raise PaymentInvalidInputError("Se requiere un puerto proveedor documental obligatorio.")


def _crear_original_si_falta(pago: PagoExterno) -> None:
    """Conserva el estado legado antes de la primera rectificación, sin fabricar PDFs."""
    if PagoExternoOriginal.objects.filter(pago_id=pago.pk).exists():
        return
    PagoExternoOriginal.objects.create(
        pago=pago,
        importe=pago.importe,
        monto_bruto=pago.monto_bruto,
        monto_retencion_atp=pago.monto_retencion_atp,
        moneda=pago.moneda,
        fecha_pago=pago.fecha_pago,
        referencia_externa=pago.referencia_externa,
        referencia_documental=pago.referencia_documental,
        referencia_atp=pago.referencia_atp,
        comprobante_bancario_id=pago.comprobante_bancario_id,
        constancia_atp_id=pago.constancia_atp_id,
        comprobante_sha256=(
            pago.comprobante_bancario.sha256 if pago.comprobante_bancario_id else ""
        ),
        constancia_sha256=(pago.constancia_atp.sha256 if pago.constancia_atp_id else ""),
        es_legado=True,
    )


def _cambio_repetido(
    pago: PagoExterno,
    *,
    version_esperada: int,
    actor: Any,
    motivo: str,
    datos_despues: dict[str, Any],
    tipo: str,
) -> bool:
    """Reconoce la misma operación ya aplicada tras una respuesta perdida."""
    if version_esperada != pago.version - 1:
        return False
    ultimo = pago.cambios.order_by("-numero_version").first()
    if ultimo is None or ultimo.numero_version != pago.version:
        return False
    if ultimo.actor_id != actor.subject_id or ultimo.motivo != motivo:
        return False
    tipos_validos = {tipo}
    if tipo in {"comprobante_reemplazado", "comprobante_incorporado"}:
        tipos_validos = {"comprobante_reemplazado", "comprobante_incorporado"}
    if tipo in {"rectificacion", "atp_retirada"}:
        tipos_validos = {"rectificacion", "atp_retirada"}
    if ultimo.tipo not in tipos_validos:
        return False
    comparables = {
        clave: ultimo.datos_despues.get(clave)
        for clave in datos_despues
        if clave not in ("version", "comprobante", "constancia")
    }
    esperados = {
        clave: valor
        for clave, valor in datos_despues.items()
        if clave not in ("version", "comprobante", "constancia")
    }
    if comparables != esperados:
        return False
    for clave in ("comprobante", "constancia"):
        anterior = ultimo.datos_despues.get(clave) or {}
        nuevo = datos_despues.get(clave) or {}
        if (anterior.get("sha256"), anterior.get("nombre")) != (
            nuevo.get("sha256"),
            nuevo.get("nombre"),
        ):
            return False
    return True


def _resolver_version(
    pago: PagoExterno,
    *,
    version_esperada: int,
    actor: Any,
    motivo: str,
    datos_despues: dict[str, Any],
    tipo: str,
) -> bool:
    """Devuelve True si la operación ya estaba aplicada; False si debe aplicarse."""
    if version_esperada == pago.version:
        return False
    if _cambio_repetido(
        pago,
        version_esperada=version_esperada,
        actor=actor,
        motivo=motivo,
        datos_despues=datos_despues,
        tipo=tipo,
    ):
        return True
    raise PaymentVersionConflictError(
        "La versión esperada del pago no coincide con la versión efectiva."
    )


def _validar_motivo(motivo: Any) -> str:
    if not isinstance(motivo, str) or not motivo.strip():
        raise PaymentInvalidInputError("El motivo de la rectificación es obligatorio.")
    norm = motivo.strip()
    if len(norm) > 500:
        raise PaymentInvalidInputError("El motivo no puede superar los 500 caracteres.")
    return norm


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
      recorta espacios exteriores y puede quedar vacía; la referencia documental opaca se
      preserva exactamente y no puede quedar vacía. Ambas rechazan caracteres NUL y
      longitudes mayores a 128 o 255 caracteres.
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


def _validar_decimal_estricto(
    valor: Any,
    nombre_campo: str,
    *,
    permitir_cero: bool = False,
) -> Decimal:
    """Valida y normaliza un importe decimal conforme al estándar riguroso de GAST-R05."""
    if isinstance(valor, bool) or valor is None or isinstance(valor, (float, int)):
        raise PaymentInvalidInputError(
            f"El campo '{nombre_campo}' debe ser Decimal o string decimal ASCII "
            "(no se admiten bool, float ni int)."
        )

    if isinstance(valor, str):
        val_str = valor.strip()
        if not val_str:
            raise PaymentInvalidInputError(f"El campo '{nombre_campo}' no puede ser vacío.")
        if not _IMPORTE_DECIMAL_ESTRICTO.fullmatch(val_str):
            raise PaymentInvalidInputError(
                f"El campo '{nombre_campo}' debe ser un string decimal ASCII sin exponente "
                "(sólo dígitos, signo opcional y un punto decimal)."
            )
        try:
            dec = Decimal(val_str)
        except InvalidOperation:
            raise PaymentInvalidInputError(
                f"Formato numérico inválido para '{nombre_campo}'."
            ) from None
    elif isinstance(valor, Decimal):
        dec = valor
    else:
        raise PaymentInvalidInputError(f"Tipo de dato no admitido para '{nombre_campo}'.")

    if not dec.is_finite():
        raise PaymentInvalidInputError(f"El campo '{nombre_campo}' debe ser un número finito.")

    if permitir_cero:
        if dec < Decimal("0.00"):
            raise PaymentInvalidInputError(f"El campo '{nombre_campo}' no puede ser negativo.")
    else:
        if dec <= Decimal("0.00"):
            raise PaymentInvalidInputError(
                f"El campo '{nombre_campo}' debe ser estrictamente positivo."
            )

    exponent = dec.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise PaymentInvalidInputError(
            f"El campo '{nombre_campo}' no puede tener más de 2 cifras fraccionarias "
            "(sobreprecisión no admitida)."
        )

    if dec > Decimal("9999999999.99"):
        raise PaymentInvalidInputError(
            f"El campo '{nombre_campo}' excede el límite máximo permitido de 12 dígitos."
        )

    return dec.quantize(Decimal("0.01"))


def validate_retencion_atp_input(
    *,
    importe: Decimal,
    monto_bruto: Any = None,
    monto_retencion_atp: Any = Decimal("0.00"),
    referencia_atp: Any = "",
) -> tuple[Decimal, Decimal, str]:
    """Valida y normaliza la retención provincial ATP conforme a GAST-R04 y GAST-R05.

    Garantiza la identidad: Importe Neto == Monto Bruto - Monto Retención ATP.
    Si monto_bruto es None y retención es cero, asume monto_bruto = importe.
    """
    # 1. Normalizar referencia ATP
    if referencia_atp is None:
        norm_ref_atp = ""
    elif isinstance(referencia_atp, bool) or not isinstance(referencia_atp, str):
        raise PaymentInvalidInputError("La referencia ATP debe ser de tipo str.")
    elif "\x00" in referencia_atp:
        raise PaymentInvalidInputError("La referencia ATP no puede contener caracteres nulos.")
    else:
        norm_ref_atp = referencia_atp.strip()
        if len(norm_ref_atp) > 128:
            raise PaymentInvalidInputError(
                f"La referencia ATP excede el límite de 128 caracteres "
                f"(longitud: {len(norm_ref_atp)})."
            )

    # 2. Caso neutro retrocompatible: sin especificar monto_bruto y retención nula
    es_retencion_cero = (
        monto_retencion_atp is None
        or (
            not isinstance(monto_retencion_atp, (bool, float))
            and isinstance(monto_retencion_atp, (str, Decimal))
            and str(monto_retencion_atp).strip() in ("0", "0.0", "0.00", "0.000")
        )
        or (
            not isinstance(monto_retencion_atp, (bool, float))
            and monto_retencion_atp == Decimal("0.00")
        )
    )

    if monto_bruto is None and es_retencion_cero:
        return importe, Decimal("0.00"), norm_ref_atp

    # 3. Caso con valores informados: validación rigurosa
    if monto_bruto is None:
        raise PaymentInvalidInputError("Debe especificar monto_bruto si informa retención ATP.")

    valid_bruto = _validar_decimal_estricto(monto_bruto, "monto_bruto", permitir_cero=False)
    monto_ret_raw = Decimal("0.00") if monto_retencion_atp is None else monto_retencion_atp
    valid_retencion = _validar_decimal_estricto(
        monto_ret_raw, "monto_retencion_atp", permitir_cero=True
    )

    if importe != (valid_bruto - valid_retencion):
        raise PaymentInvalidInputError(
            f"Inconsistencia contable: el importe neto ({importe}) debe ser igual a "
            f"monto_bruto ({valid_bruto}) menos monto_retencion_atp ({valid_retencion})."
        )

    return valid_bruto, valid_retencion, norm_ref_atp


def calcular_huella_pago(
    *,
    solicitud_id: int,
    importe: Decimal,
    moneda: str,
    fecha_pago: date,
    referencia_externa: str,
    referencia_documental: str,
    monto_bruto: Decimal | None = None,
    monto_retencion_atp: Decimal | None = None,
    referencia_atp: str = "",
) -> str:
    """Calcula una huella SHA-256 canónica sin ambigüedad a partir de los valores normalizados."""
    payload_dict: dict[str, Any] = {
        "fecha_pago": fecha_pago.isoformat(),
        "importe": f"{importe.quantize(Decimal('0.01')):.2f}",
        "moneda": moneda,
        "referencia_documental": referencia_documental,
        "referencia_externa": referencia_externa,
        "solicitud_id": solicitud_id,
    }
    if monto_retencion_atp is not None and monto_retencion_atp > Decimal("0.00"):
        payload_dict["monto_retencion_atp"] = f"{monto_retencion_atp.quantize(Decimal('0.01')):.2f}"
    if monto_bruto is not None and monto_bruto != importe:
        payload_dict["monto_bruto"] = f"{monto_bruto.quantize(Decimal('0.01')):.2f}"
    if referencia_atp:
        payload_dict["referencia_atp"] = referencia_atp

    payload = json.dumps(
        payload_dict,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def registrar_pago_externo(
    *,
    actor: Any,
    solicitud_id: int,
    fecha_pago: Any,
    referencia_documental: Any,
    monto_bruto: Any = None,
    monto_retencion_atp: Any = Decimal("0.00"),
    referencia_externa: Any = "",
    referencia_atp: Any = "",
    comprobante_bancario: Any = None,
    constancia_atp: Any = None,
    incorporar_atp_despues: bool = False,
    importe: Any = None,
    document_provider: DocumentVerificationPort | None = None,
) -> PagoExterno:
    """Registra un pago externo documentado y compensa archivos si algo falla.

    Reglas del corte:
    - El neto se deriva en servidor de ``monto_bruto - monto_retencion_atp``.
    - El comprobante bancario PDF es obligatorio para un alta nueva. Un reenvío
      idéntico al alta original se resuelve sin PDF, sin C01 y sin proveedor.
    - La constancia ATP es un documento distinto: con retención positiva se
      adjunta ahora o se elige explícitamente incorporarla después.
    - ``operacion_documental`` es dueño de la transacción exterior; la carga de
      archivos se compensa si falla el segundo documento o la escritura SQL.
    - El reenvío se compara con ``PagoExternoOriginal``, nunca con importes
      corregidos ni con huellas históricas recalculadas.
    """
    if actor is None:
        raise PaymentPermissionDeniedError("Se requiere un actor autenticado.")

    solicitud_inicial = visible_expenses(actor).filter(pk=solicitud_id).first()
    if solicitud_inicial is None:
        raise PaymentExpenseNotFoundError(f"Solicitud #{solicitud_id} no visible o inexistente.")

    if not has_capability(actor, "gastos.registrar_pago"):
        raise PaymentPermissionDeniedError(
            "El actor no posee la capacidad 'gastos.registrar_pago'."
        )

    if solicitud_inicial.estado != EstadoSolicitud.ACEPTADA:
        raise PaymentInvalidExpenseStateError(
            f"La solicitud #{solicitud_id} se encuentra en estado "
            f"'{solicitud_inicial.estado}'; sólo se pueden registrar pagos sobre "
            "solicitudes aceptadas."
        )

    bruto, retencion, neto = _normalizar_importes(
        monto_bruto=monto_bruto,
        monto_retencion_atp=monto_retencion_atp,
        importe=importe,
    )
    _, valid_fecha, valid_ref_ext, valid_doc_ref = validate_payment_input(
        importe=neto,
        fecha_pago=fecha_pago,
        referencia_externa=referencia_externa,
        referencia_documental=referencia_documental,
    )
    valid_bruto, valid_retencion, valid_ref_atp = validate_retencion_atp_input(
        importe=neto,
        monto_bruto=bruto,
        monto_retencion_atp=retencion,
        referencia_atp=referencia_atp,
    )

    validado_banco = (
        _validar_comprobante_bancario(comprobante_bancario, etiqueta="El comprobante bancario")
        if comprobante_bancario is not None
        else None
    )
    validado_atp = (
        _validar_pdf(constancia_atp, etiqueta="La constancia ATP")
        if constancia_atp is not None
        else None
    )

    from documentos.models import Documento
    from documentos.operaciones import operacion_documental
    from documentos.services import incorporar

    with operacion_documental() as escrituras:
        solicitud = (
            visible_expenses(actor).select_for_update().filter(pk=solicitud_id).first()
        )
        if solicitud is None:
            raise PaymentExpenseNotFoundError(
                f"Solicitud #{solicitud_id} no visible o inexistente."
            )
        if not has_capability(actor, "gastos.registrar_pago"):
            raise PaymentPermissionDeniedError(
                "El actor no posee la capacidad 'gastos.registrar_pago'."
            )
        if solicitud.estado != EstadoSolicitud.ACEPTADA:
            raise PaymentInvalidExpenseStateError(
                f"La solicitud #{solicitud_id} se encuentra en estado "
                f"'{solicitud.estado}'; sólo se pueden registrar pagos sobre "
                "solicitudes aceptadas."
            )

        pago_existente = (
            PagoExterno.objects.select_for_update().filter(solicitud=solicitud).first()
        )
        if pago_existente is not None:
            if _coincide_alta_original(
                pago_existente,
                fecha_pago=valid_fecha,
                monto_bruto=valid_bruto,
                monto_retencion_atp=valid_retencion,
                importe=neto,
                referencia_externa=valid_ref_ext,
                referencia_documental=valid_doc_ref,
                referencia_atp=valid_ref_atp,
                comprobante_sha256=validado_banco.sha256 if validado_banco else None,
                constancia_sha256=validado_atp.sha256 if validado_atp else None,
            ):
                return pago_existente
            raise PaymentConflictError(
                f"Ya existe un pago registrado para la solicitud #{solicitud_id} "
                "con datos diferentes."
            )

        if validado_banco is None:
            raise PaymentDocumentRequiredError(
                "El comprobante bancario es obligatorio para registrar el pago."
            )
        if valid_retencion > Decimal("0.00"):
            if incorporar_atp_despues:
                if validado_atp is not None:
                    raise PaymentInvalidInputError(
                        "Al diferir la constancia ATP no se debe adjuntar un archivo."
                    )
                if valid_ref_atp:
                    raise PaymentInvalidInputError(
                        "Al diferir la constancia ATP no se debe informar una referencia."
                    )
            elif validado_atp is None:
                raise PaymentDocumentRequiredError(
                    "Elegí adjuntar la constancia ATP ahora o indicá explícitamente que "
                    "la incorporarás después."
                )
        else:
            if validado_atp is not None:
                raise PaymentInvalidInputError(
                    "Con retención cero no corresponde incorporar una constancia ATP."
                )
            if incorporar_atp_despues:
                raise PaymentInvalidInputError(
                    "Con retención cero no existe una constancia ATP pendiente."
                )
        _exigir_capacidades_documentales(actor)
        _exigir_proveedor(document_provider)

        tipos_admitidos = tipos_documento_admitidos_para_flujo(
            getattr(solicitud, "tipo_flujo", None)
        )
        doc_verificado = document_provider.verificar_y_bloquear_documento(
            actor=actor,
            gasto=solicitud,
            referencia_documental=valid_doc_ref,
            tipos_admitidos=tipos_admitidos,
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
            or getattr(doc_verificado, "tipo_documento", None) not in tipos_admitidos
        ):
            raise DocumentVerificationError(
                "La evidencia documental no corresponde al gasto bloqueado, a la "
                "referencia solicitada o posee un tipo no admitido para la modalidad."
            )

        doc_banco = incorporar(
            actor=actor,
            referencia=f"gastos:{solicitud.pk}",
            archivo=validado_banco,
            tipo=Documento.Tipo.COMPROBANTE_PAGO,
            procedencia=Documento.Procedencia.EXTERNO_BANCO,
            _escrituras=escrituras,
        )
        doc_atp = None
        if validado_atp is not None:
            doc_atp = incorporar(
                actor=actor,
                referencia=f"gastos:{solicitud.pk}",
                archivo=validado_atp,
                tipo=Documento.Tipo.CONSTANCIA_RETENCION_ATP,
                procedencia=Documento.Procedencia.EXTERNO_ATP,
                _escrituras=escrituras,
            )

        pago = PagoExterno.objects.create(
            solicitud=solicitud,
            importe=neto,
            monto_bruto=valid_bruto,
            monto_retencion_atp=valid_retencion,
            referencia_atp=valid_ref_atp,
            moneda="ARS",
            fecha_pago=valid_fecha,
            referencia_externa=valid_ref_ext,
            referencia_documental=doc_verificado.referencia_documental,
            comprobante_bancario=doc_banco,
            constancia_atp=doc_atp,
            version=1,
            huella_idempotencia=calcular_huella_pago(
                solicitud_id=solicitud.pk,
                importe=neto,
                moneda="ARS",
                fecha_pago=valid_fecha,
                referencia_externa=valid_ref_ext,
                referencia_documental=valid_doc_ref,
                monto_bruto=valid_bruto,
                monto_retencion_atp=valid_retencion,
                referencia_atp=valid_ref_atp,
            ),
        )
        EventoPagoExterno.objects.create(
            pago=pago,
            tipo_evento="pago_externo_registrado",
            actor_id=actor.subject_id,
        )
        PagoExternoOriginal.objects.create(
            pago=pago,
            importe=neto,
            monto_bruto=valid_bruto,
            monto_retencion_atp=valid_retencion,
            moneda="ARS",
            fecha_pago=valid_fecha,
            referencia_externa=valid_ref_ext,
            referencia_documental=valid_doc_ref,
            referencia_atp=valid_ref_atp,
            comprobante_bancario=doc_banco,
            constancia_atp=doc_atp,
            comprobante_sha256=doc_banco.sha256,
            constancia_sha256=doc_atp.sha256 if doc_atp else "",
            es_legado=False,
        )
        return pago


def rectificar_pago_externo(
    *,
    actor: Any,
    solicitud_id: int,
    version_esperada: Any,
    motivo: Any,
    fecha_pago: Any,
    referencia_documental: Any = None,
    monto_bruto: Any = None,
    monto_retencion_atp: Any = Decimal("0.00"),
    referencia_externa: Any = "",
    referencia_atp: Any = "",
    comprobante_bancario: Any = None,
) -> PagoExterno:
    """Rectifica datos efectivos y/o el comprobante bancario con historial append-only.

    No anula transferencias reales, no cambia beneficiario/cuenta y no reasigna
    el respaldo comercial C01. La versión esperada serializa la concurrencia y
    reconoce un reenvío exacto ya aplicado sin duplicar documentos ni eventos.
    """
    if actor is None:
        raise PaymentPermissionDeniedError("Se requiere un actor autenticado.")
    solicitud_inicial = visible_expenses(actor).filter(pk=solicitud_id).first()
    if solicitud_inicial is None:
        raise PaymentExpenseNotFoundError(f"Solicitud #{solicitud_id} no visible o inexistente.")
    if not has_capability(actor, "gastos.registrar_pago"):
        raise PaymentPermissionDeniedError(
            "El actor no posee la capacidad 'gastos.registrar_pago'."
        )
    pago_inicial = PagoExterno.objects.filter(solicitud_id=solicitud_id).first()
    if pago_inicial is None:
        raise PaymentInvalidExpenseStateError(
            "La solicitud no tiene un pago registrado para rectificar."
        )
    try:
        version = int(version_esperada)
    except (TypeError, ValueError):
        raise PaymentInvalidInputError("La versión esperada del pago es obligatoria.") from None
    if version <= 0:
        raise PaymentInvalidInputError("La versión esperada del pago debe ser positiva.")
    motivo_norm = _validar_motivo(motivo)
    bruto, retencion, neto = _normalizar_importes(
        monto_bruto=monto_bruto,
        monto_retencion_atp=monto_retencion_atp,
    )
    if referencia_documental is None:
        referencia_documental = pago_inicial.referencia_documental
    _, valid_fecha, valid_ref_ext, valid_doc_ref = validate_payment_input(
        importe=neto,
        fecha_pago=fecha_pago,
        referencia_externa=referencia_externa,
        referencia_documental=referencia_documental,
    )
    _, _, valid_ref_atp = validate_retencion_atp_input(
        importe=neto,
        monto_bruto=bruto,
        monto_retencion_atp=retencion,
        referencia_atp=referencia_atp,
    )
    validado_banco = (
        _validar_comprobante_bancario(comprobante_bancario, etiqueta="El comprobante bancario")
        if comprobante_bancario is not None
        else None
    )
    if validado_banco is not None:
        _exigir_capacidades_documentales(actor)

    from documentos.models import Documento
    from documentos.operaciones import operacion_documental
    from documentos.services import incorporar

    with operacion_documental() as escrituras:
        solicitud = (
            visible_expenses(actor).select_for_update().filter(pk=solicitud_id).first()
        )
        if solicitud is None:
            raise PaymentExpenseNotFoundError(
                f"Solicitud #{solicitud_id} no visible o inexistente."
            )
        if not has_capability(actor, "gastos.registrar_pago"):
            raise PaymentPermissionDeniedError(
                "El actor no posee la capacidad 'gastos.registrar_pago'."
            )
        # PostgreSQL rechaza FOR UPDATE sobre el lado anulable del join con
        # documentos: el lock cubre sólo la fila del pago. Las raíces
        # documentales se bloquean después, dentro de `incorporar`.
        pago = (
            PagoExterno.objects.select_for_update(of=("self",))
            .select_related("comprobante_bancario", "constancia_atp")
            .filter(solicitud_id=solicitud.pk)
            .first()
        )
        if pago is None:
            raise PaymentInvalidExpenseStateError(
                "La solicitud no tiene un pago registrado para rectificar."
            )
        if pago.referencia_documental != valid_doc_ref:
            raise PaymentConflictError(
                "La referencia documental del pago no coincide con la versión esperada."
            )

        retencion_cero = retencion == Decimal("0.00")
        constancia_retirada = retencion_cero and pago.constancia_atp_id is not None
        nuevo_documento = validado_banco is not None

        datos_antes = _snapshot_pago(pago)
        tipo = "rectificacion"
        if constancia_retirada:
            tipo = "atp_retirada"
        elif nuevo_documento:
            tipo = (
                "comprobante_reemplazado"
                if pago.comprobante_bancario_id
                else "comprobante_incorporado"
            )
        datos_despues_previstos = dict(datos_antes)
        datos_despues_previstos.update(
            {
                "fecha_pago": valid_fecha.isoformat(),
                "monto_bruto": f"{bruto:.2f}",
                "monto_retencion_atp": f"{retencion:.2f}",
                "importe": f"{neto:.2f}",
                "referencia_externa": valid_ref_ext,
                "referencia_atp": valid_ref_atp,
            }
        )
        if constancia_retirada:
            datos_despues_previstos["constancia"] = None
        if validado_banco is not None:
            datos_despues_previstos["comprobante"] = {
                "documento_id": 0,
                "sha256": validado_banco.sha256,
                "nombre": validado_banco.nombre,
                "tamano": len(validado_banco.contenido),
                "tipo": "COMPROBANTE_PAGO",
                "version": 0,
            }
            datos_despues_previstos["es_legado"] = False
        if _resolver_version(
            pago,
            version_esperada=version,
            actor=actor,
            motivo=motivo_norm,
            datos_despues=datos_despues_previstos,
            tipo=tipo,
        ):
            return pago

        if (
            not nuevo_documento
            and not constancia_retirada
            and pago.fecha_pago == valid_fecha
            and pago.monto_bruto == bruto
            and pago.monto_retencion_atp == retencion
            and pago.importe == neto
            and pago.referencia_externa == valid_ref_ext
            and pago.referencia_atp == valid_ref_atp
        ):
            raise PaymentInvalidInputError("No hay cambios para rectificar en el pago.")

        _crear_original_si_falta(pago)
        documento_anterior = None
        documento_nuevo = None
        if constancia_retirada:
            documento_anterior = pago.constancia_atp
            pago.constancia_atp = None
        if validado_banco is not None:
            documento_anterior = pago.comprobante_bancario
            documento_nuevo = incorporar(
                actor=actor,
                referencia=f"gastos:{solicitud.pk}",
                archivo=validado_banco,
                tipo=Documento.Tipo.COMPROBANTE_PAGO,
                procedencia=Documento.Procedencia.EXTERNO_BANCO,
                reemplaza_id=pago.comprobante_bancario_id,
                _escrituras=escrituras,
            )
            pago.comprobante_bancario = documento_nuevo

        pago.fecha_pago = valid_fecha
        pago.monto_bruto = bruto
        pago.monto_retencion_atp = retencion
        pago.importe = neto
        pago.referencia_externa = valid_ref_ext
        pago.referencia_atp = valid_ref_atp
        pago.version = pago.version + 1
        pago.save(
            update_fields=[
                "fecha_pago",
                "monto_bruto",
                "monto_retencion_atp",
                "importe",
                "referencia_externa",
                "referencia_atp",
                "comprobante_bancario",
                "constancia_atp",
                "version",
            ]
        )
        datos_despues = _snapshot_pago(pago)
        PagoExternoCambio.objects.create(
            pago=pago,
            numero_version=pago.version,
            tipo=tipo,
            motivo=motivo_norm,
            actor_id=actor.subject_id,
            datos_antes=datos_antes,
            datos_despues=datos_despues,
            documento_anterior=documento_anterior,
            documento_nuevo=documento_nuevo,
        )
        return pago


def incorporar_constancia_atp_posterior(
    *,
    actor: Any,
    solicitud_id: int,
    version_esperada: Any,
    motivo: Any,
    constancia_atp: Any,
) -> PagoExterno:
    """Incorpora la constancia ATP después del pago, con motivo y versión esperada."""
    if actor is None:
        raise PaymentPermissionDeniedError("Se requiere un actor autenticado.")
    solicitud_inicial = visible_expenses(actor).filter(pk=solicitud_id).first()
    if solicitud_inicial is None:
        raise PaymentExpenseNotFoundError(f"Solicitud #{solicitud_id} no visible o inexistente.")
    if not has_capability(actor, "gastos.registrar_pago"):
        raise PaymentPermissionDeniedError(
            "El actor no posee la capacidad 'gastos.registrar_pago'."
        )
    try:
        version = int(version_esperada)
    except (TypeError, ValueError):
        raise PaymentInvalidInputError("La versión esperada del pago es obligatoria.") from None
    if version <= 0:
        raise PaymentInvalidInputError("La versión esperada del pago debe ser positiva.")
    motivo_norm = _validar_motivo(motivo)
    if constancia_atp is None:
        raise PaymentDocumentRequiredError("Seleccioná el PDF de la constancia ATP.")
    validado_atp = _validar_pdf(constancia_atp, etiqueta="La constancia ATP")
    _exigir_capacidades_documentales(actor)

    from documentos.models import Documento
    from documentos.operaciones import operacion_documental
    from documentos.services import incorporar

    with operacion_documental() as escrituras:
        solicitud = (
            visible_expenses(actor).select_for_update().filter(pk=solicitud_id).first()
        )
        if solicitud is None:
            raise PaymentExpenseNotFoundError(
                f"Solicitud #{solicitud_id} no visible o inexistente."
            )
        if not has_capability(actor, "gastos.registrar_pago"):
            raise PaymentPermissionDeniedError(
                "El actor no posee la capacidad 'gastos.registrar_pago'."
            )
        # Mismo criterio que en rectificar: el join anulable no se bloquea.
        pago = (
            PagoExterno.objects.select_for_update(of=("self",))
            .select_related("constancia_atp")
            .filter(solicitud_id=solicitud.pk)
            .first()
        )
        if pago is None:
            raise PaymentInvalidExpenseStateError(
                "La solicitud no tiene un pago registrado."
            )
        if pago.monto_retencion_atp <= Decimal("0.00"):
            raise PaymentInvalidInputError(
                "Con retención cero no corresponde una constancia ATP."
            )
        if pago.version == version and pago.constancia_atp_id is not None:
            raise PaymentConflictError("El pago ya tiene una constancia ATP vinculada.")
        if pago.constancia_atp_id is not None:
            datos_antes = _snapshot_pago(pago)
            datos_despues = dict(datos_antes)
            if _resolver_version(
                pago,
                version_esperada=version,
                actor=actor,
                motivo=motivo_norm,
                datos_despues=datos_despues,
                tipo="atp_incorporada",
            ):
                return pago
            raise PaymentConflictError("El pago ya tiene una constancia ATP vinculada.")

        datos_antes = _snapshot_pago(pago)
        datos_despues_previstos = dict(datos_antes)
        datos_despues_previstos["constancia"] = {
            "documento_id": 0,
            "sha256": validado_atp.sha256,
            "nombre": validado_atp.nombre,
            "tamano": len(validado_atp.contenido),
            "tipo": "CONSTANCIA_RETENCION_ATP",
            "version": 1,
        }
        if _resolver_version(
            pago,
            version_esperada=version,
            actor=actor,
            motivo=motivo_norm,
            datos_despues=datos_despues_previstos,
            tipo="atp_incorporada",
        ):
            return pago

        _crear_original_si_falta(pago)
        documento = incorporar(
            actor=actor,
            referencia=f"gastos:{solicitud.pk}",
            archivo=validado_atp,
            tipo=Documento.Tipo.CONSTANCIA_RETENCION_ATP,
            procedencia=Documento.Procedencia.EXTERNO_ATP,
            _escrituras=escrituras,
        )
        pago.constancia_atp = documento
        pago.version = pago.version + 1
        pago.save(update_fields=["constancia_atp", "version"])
        PagoExternoCambio.objects.create(
            pago=pago,
            numero_version=pago.version,
            tipo="atp_incorporada",
            motivo=motivo_norm,
            actor_id=actor.subject_id,
            datos_antes=datos_antes,
            datos_despues=_snapshot_pago(pago),
            documento_anterior=None,
            documento_nuevo=documento,
        )
        return pago


def consultar_pago_externo(
    actor: Any,
    solicitud_id: int,
) -> PagoExternoConsulta | None:
    """Consulta pura del pago visible, con presencia documental y metadatos autorizados.

    Garantías:
    - No escribe ni filtra la referencia documental opaca.
    - La presencia del comprobante/constancia se informa como hecho.
    - El nombre, tamaño e identificador de cada documento sólo se completa con
      ``documentos.consultar_metadatos``; la descarga real se autoriza aparte.
    """
    if actor is None:
        return None

    solicitud = visible_expenses(actor).filter(pk=solicitud_id).first()
    if solicitud is None:
        return None

    pago = (
        PagoExterno.objects.filter(solicitud=solicitud)
        .select_related(
            "evento",
            "comprobante_bancario",
            "constancia_atp",
        )
        .first()
    )
    if pago is None:
        return None

    evento = getattr(pago, "evento", None)
    fecha_reg = evento.fecha_hora if evento else None
    actor_id = evento.actor_id if evento else None
    puede_metadatos = has_capability(actor, "documentos.consultar_metadatos")

    banco = pago.comprobante_bancario if pago.comprobante_bancario_id else None
    atp = pago.constancia_atp if pago.constancia_atp_id else None

    return PagoExternoConsulta(
        id=pago.pk,
        solicitud_id=pago.solicitud_id,
        importe=pago.importe,
        moneda=pago.moneda,
        fecha_pago=pago.fecha_pago,
        referencia_externa=pago.referencia_externa,
        fecha_registro=fecha_reg,
        actor_id=actor_id,
        monto_bruto=pago.monto_bruto,
        monto_retencion_atp=pago.monto_retencion_atp,
        referencia_atp=pago.referencia_atp,
        version=pago.version,
        tiene_comprobante_bancario=banco is not None,
        comprobante_bancario_id=banco.pk if banco and puede_metadatos else None,
        comprobante_bancario_nombre=(
            banco.nombre_original if banco and puede_metadatos else ""
        ),
        comprobante_bancario_tamano=(banco.tamano if banco and puede_metadatos else None),
        tiene_constancia_atp=atp is not None,
        constancia_atp_id=atp.pk if atp and puede_metadatos else None,
        constancia_atp_nombre=(atp.nombre_original if atp and puede_metadatos else ""),
        constancia_atp_tamano=(atp.tamano if atp and puede_metadatos else None),
        constancia_atp_pendiente=pago.constancia_atp_pendiente,
        es_registro_legado=pago.comprobante_bancario_id is None,
    )


def _formatear_snapshot(snapshot: dict[str, Any], *, puede_metadatos: bool) -> str:
    """Texto legible de un snapshot para el historial de rectificaciones."""

    def _importe(valor: Any) -> str:
        try:
            return f"$ {formatear_importe_es_ar(valor)}"
        except (InvalidOperation, TypeError, ValueError):
            return "sin dato"

    def _doc(valor: Any) -> str:
        if not valor:
            return "sin documento"
        if puede_metadatos and valor.get("nombre"):
            return f"{valor['nombre']} (v{valor.get('version', '?')})"
        return "documento incorporado"

    partes = [
        f"Fecha {date_format(date.fromisoformat(snapshot['fecha_pago']), 'd/m/Y')}",
        f"Bruto {_importe(snapshot.get('monto_bruto'))}",
        f"Retención {_importe(snapshot.get('monto_retencion_atp'))}",
        f"Neto {_importe(snapshot.get('importe'))}",
        f"Comprobante {_doc(snapshot.get('comprobante'))}",
        f"Constancia ATP {_doc(snapshot.get('constancia'))}",
    ]
    referencia = snapshot.get("referencia_externa") or "sin referencia informada"
    partes.append(f"Referencia {referencia}")
    return " · ".join(partes)


def consultar_cambios_pago(
    actor: Any, solicitud_id: int
) -> tuple[CambioPagoExternoConsulta, ...]:
    """Historial legible de rectificaciones y aportes posteriores del pago visible."""
    if actor is None:
        return ()
    solicitud = visible_expenses(actor).filter(pk=solicitud_id).first()
    if solicitud is None:
        return ()
    pago = PagoExterno.objects.filter(solicitud=solicitud).first()
    if pago is None:
        return ()
    puede_metadatos = has_capability(actor, "documentos.consultar_metadatos")
    cambios = pago.cambios.select_related("actor").order_by("numero_version")
    return tuple(
        CambioPagoExternoConsulta(
            numero_version=cambio.numero_version,
            tipo=cambio.tipo,
            tipo_mostrado=cambio.get_tipo_display(),
            motivo=cambio.motivo,
            actor_id=cambio.actor_id,
            fecha_hora=cambio.fecha_hora,
            antes=_formatear_snapshot(cambio.datos_antes, puede_metadatos=puede_metadatos),
            despues=_formatear_snapshot(cambio.datos_despues, puede_metadatos=puede_metadatos),
        )
        for cambio in cambios
    )


def derivar_categoria_respaldo(
    referencia_documental: str | None,
    opciones_documentales: Any,
) -> str | None:
    """Deriva categoría 'factura' o 'presupuesto' por igualdad exacta con opciones vigentes.

    Regla pura y desacoplada:
    - Compara por igualdad exacta la referencia documental opaca persistida en PagoExterno
      con OpcionDocumental.referencia_documental de las opciones vigentes ya validadas.
    - Si coincide con una opción cuyo tipo es 'factura', devuelve 'factura'.
    - Si coincide con una opción cuyo tipo es 'presupuesto' o 'proforma', devuelve 'presupuesto'.
    - Si no hay coincidencia exacta o el tipo no es admisible, devuelve None.
    - No recorta, normaliza ni expone la referencia.
    """
    if not isinstance(referencia_documental, str) or not referencia_documental:
        return None
    if not opciones_documentales:
        return None

    for opcion in opciones_documentales:
        op_ref = getattr(opcion, "referencia_documental", None)
        if op_ref == referencia_documental:
            tipo = getattr(opcion, "tipo_documento", None)
            if tipo == "factura":
                return "factura"
            if tipo in ("presupuesto", "proforma"):
                return "presupuesto"
            return None
    return None
