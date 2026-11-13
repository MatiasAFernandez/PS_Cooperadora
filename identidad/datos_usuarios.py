"""Servicio de edición administrativa de datos básicos de cuentas locales (SPEC-024)."""

from collections.abc import Mapping
from typing import Any

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from identidad.models import CambioDatosCuentaLocal, CuentaLocal
from identidad.services import Actor, has_capability

CAPACIDAD_ADMINISTRAR = "identidad.administrar_cuentas"
SALT_REFERENCIA_EDICION = "identidad.datos_usuarios.referencia_edicion.v1"

CAMPOS_EDITABLES: tuple[str, ...] = (
    "nombre_completo",
    "area_habitual",
    "cuit_cuil",
    "legajo",
)

LONGITUDES_MAXIMAS: dict[str, int] = {
    "nombre_completo": 150,
    "area_habitual": 150,
    "cuit_cuil": 20,
    "legajo": 50,
}


def _snapshot_editable(cuenta: CuentaLocal) -> dict[str, str]:
    """Obtiene los valores actuales normalizados de los campos editables."""
    return {campo: getattr(cuenta, campo) or "" for campo in CAMPOS_EDITABLES}


def generar_referencia_edicion(cuenta: CuentaLocal) -> str:
    """Genera una referencia firmada con el PK y los valores actuales de la cuenta."""
    payload = {
        "pk": cuenta.pk,
        "valores": _snapshot_editable(cuenta),
    }
    return signing.dumps(payload, salt=SALT_REFERENCIA_EDICION)


def _verificar_referencia_edicion(cuenta: CuentaLocal, referencia: str) -> None:
    """Valida la firma de la referencia y contrasta contra el estado actual bajo bloqueo."""
    if not isinstance(referencia, str) or not referencia.strip():
        raise ValidationError(
            "Falta la referencia del formulario. Recargue la ficha e intente nuevamente."
        )

    try:
        payload = signing.loads(referencia, salt=SALT_REFERENCIA_EDICION)
    except signing.BadSignature as exc:
        raise ValidationError(
            "La referencia del formulario es inválida o fue alterada. "
            "Recargue la ficha e intente nuevamente."
        ) from exc

    if (
        not isinstance(payload, dict)
        or payload.get("pk") != cuenta.pk
        or not isinstance(payload.get("valores"), dict)
    ):
        raise ValidationError(
            "La referencia del formulario no corresponde a esta cuenta. "
            "Recargue la ficha e intente nuevamente."
        )

    valores_actuales = _snapshot_editable(cuenta)
    valores_referencia = payload["valores"]
    if any(valores_referencia.get(campo) != valores_actuales[campo] for campo in CAMPOS_EDITABLES):
        raise ValidationError(
            "Los datos de la cuenta cambiaron desde que abrió el formulario. "
            "Recargue la ficha para revisar los valores actuales antes de guardar."
        )


def _limpiar_y_validar_datos(datos: Mapping[str, Any]) -> dict[str, str]:
    """Limpia espacios exteriores y valida los campos editables permitidos."""
    if not isinstance(datos, Mapping):
        raise ValidationError("Los datos enviados no tienen un formato válido.")

    limpio: dict[str, str] = {}
    errores: dict[str, list[str]] = {}

    for campo in CAMPOS_EDITABLES:
        bruto = datos.get(campo, "")
        if bruto is None:
            bruto = ""
        if not isinstance(bruto, str):
            errores[campo] = ["Ingrese un texto válido."]
            continue

        valor = bruto.strip()
        max_len = LONGITUDES_MAXIMAS[campo]
        if len(valor) > max_len:
            errores[campo] = [f"Debe tener como máximo {max_len} caracteres."]
            continue

        limpio[campo] = valor

    if "nombre_completo" in limpio and not limpio["nombre_completo"]:
        errores["nombre_completo"] = ["El nombre completo es obligatorio."]

    if errores:
        raise ValidationError(errores)

    return limpio


def editar_datos_cuenta(
    actor: Actor | None,
    cuenta_id: int,
    datos: Mapping[str, Any],
    referencia: str,
) -> tuple[CuentaLocal, CambioDatosCuentaLocal | None]:
    """Edita los datos básicos de una CuentaLocal y registra el evento de cambio.

    Exige la capacidad ``identidad.administrar_cuentas`` antes de consultar la base.
    Verifica la referencia firmada bajo bloqueo de fila (``select_for_update``) y
    persiste cuenta y evento en una misma transacción. Si no hay cambios efectivos,
    no escribe ni genera evento.
    """
    if not has_capability(actor, CAPACIDAD_ADMINISTRAR) or actor is None:
        raise PermissionDenied("No posee capacidad para administrar cuentas.")

    with transaction.atomic():
        cuenta = CuentaLocal.objects.select_for_update().get(pk=cuenta_id)
        _verificar_referencia_edicion(cuenta, referencia)
        limpio = _limpiar_y_validar_datos(datos)

        cambios: dict[str, dict[str, str]] = {}
        for campo in CAMPOS_EDITABLES:
            anterior = getattr(cuenta, campo) or ""
            nuevo = limpio[campo]
            if anterior != nuevo:
                cambios[campo] = {"anterior": anterior, "nuevo": nuevo}

        if not cambios:
            return cuenta, None

        for campo, diff in cambios.items():
            setattr(cuenta, campo, diff["nuevo"])
        cuenta.save(update_fields=list(cambios.keys()))

        evento = CambioDatosCuentaLocal.objects.create(
            cuenta=cuenta,
            autor_id=actor.subject_id,
            cambios=cambios,
        )
        return cuenta, evento
