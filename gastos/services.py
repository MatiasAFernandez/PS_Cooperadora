"""Servicios de negocio para el módulo de gastos."""

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction

from comunes.models import Circuito, TramiteBase
from gastos.auth import has_capability
from gastos.datos_transferencia import validar_datos_transferencia
from gastos.models import (
    DecisionGasto,
    EstadoSolicitud,
    RevisionDatosTransferencia,
    SolicitudGasto,
)
from gastos.queries import visible_expenses


class ExpenseError(Exception):
    """Excepción base para errores de negocio del módulo de gastos."""


class ExpenseNotFoundError(ExpenseError):
    """Solicitud no encontrada o no visible para el actor (HTTP 404)."""


class ExpensePermissionDeniedError(ExpenseError):
    """Actor no autorizado para decidir sobre la solicitud (HTTP 403)."""


class InvalidDecisionInputError(ExpenseError):
    """Acción, versión o motivo inválidos validados dentro del servicio (HTTP 400)."""


class ConcurrencyConflictError(ExpenseError):
    """Versión desactualizada de la solicitud (HTTP 409)."""


class InvalidTransitionError(ExpenseError):
    """Transición no permitida desde el estado actual en base de datos (HTTP 409)."""


def can_decide_expense(actor: Any, expense: SolicitudGasto, action: str) -> bool:
    """Verifica si el actor puede ejecutar una acción de decisión sobre la solicitud.

    Garantías del contrato v1:
    - Consulta pura sin escrituras ni efectos secundarios en base de datos.
    - Actor ausente o acción desconocida retorna False.
    - Exige capacidad 'gastos.decidir'.
    - Exige que la solicitud sea visible para el actor según visible_expenses(actor).
    - Exige que el solicitante sea distinto del actor (prohibición de auto-decisión H2).
    - Exige que la transición solicitada sea válida desde el estado actual.
    """
    if actor is None or not action:
        return False

    if action not in {"aceptar", "postergar", "rechazar"}:
        return False

    if not has_capability(actor, "gastos.decidir"):
        return False

    # Prohibición provisional de auto-decisión de demo (H2)
    if expense.solicitante_id == actor.subject_id:
        return False

    # Comprobación de visibilidad efectiva
    if not visible_expenses(actor).filter(pk=expense.pk).exists():
        return False

    # Matriz de transiciones permitidas (SPEC-001)
    if expense.estado == EstadoSolicitud.PRESENTADA:
        return action in {"aceptar", "postergar", "rechazar"}

    if expense.estado == EstadoSolicitud.POSTERGADA:
        return action in {"aceptar", "rechazar"}

    # Estados ACEPTADA y RECHAZADA son terminales en I1
    return False


def validate_decision_content(
    *,
    action: Any,
    expected_version: Any,
    motivo: Any,
) -> tuple[str, int, str]:
    """Valida acción, versión y motivo dentro del servicio tras verificar acceso.

    Reglas estrictas de validación:
    - Acción: debe pertenecer exactamente a {'aceptar', 'postergar', 'rechazar'}.
    - Versión: debe ser estrictamente un entero no negativo. No trunca fracciones
      ni acepta booleanos mediante int() (en Python bool es subclase de int).
    - Motivo: obligatorio para 'postergar' y 'rechazar'; no puede ser vacío ni contener
      únicamente espacios en blanco. Opcional para 'aceptar'.
    """
    if action not in {"aceptar", "postergar", "rechazar"}:
        raise InvalidDecisionInputError(f"Acción de decisión desconocida: '{action}'.")

    # Validación rigurosa de versión entera no negativa
    if isinstance(expected_version, bool) or expected_version is None:
        raise InvalidDecisionInputError("La versión esperada debe ser un entero no negativo.")

    if isinstance(expected_version, str):
        val = expected_version.strip()
        # Rechaza dígitos no ASCII (ej: '²' U+00B2) y cadenas no numéricas
        if not (val.isascii() and val.isdigit()):
            raise InvalidDecisionInputError("La versión esperada debe ser un entero no negativo.")
        try:
            version_int = int(val)
        except ValueError:
            # Captura límites de conversión de Python (ej: >4300 dígitos)
            raise InvalidDecisionInputError(
                "La versión esperada debe ser un entero no negativo."
            ) from None
    elif isinstance(expected_version, int) and not isinstance(expected_version, bool):
        if expected_version < 0:
            raise InvalidDecisionInputError("La versión esperada debe ser un entero no negativo.")
        version_int = expected_version
    else:
        # Rechaza flotantes (no trunca fracciones), estructuras y objetos no enteros
        raise InvalidDecisionInputError("La versión esperada debe ser un entero no negativo.")

    motivo_raw = str(motivo) if motivo is not None else ""
    if "\x00" in motivo_raw:
        raise InvalidDecisionInputError("El motivo no puede contener caracteres nulos (NUL).")

    motivo_limpio = motivo_raw.strip()
    if action in {"postergar", "rechazar"} and not motivo_limpio:
        raise InvalidDecisionInputError(
            f"El motivo es obligatorio para la acción '{action}' y no puede contener sólo espacios."
        )

    return action, version_int, motivo_limpio


@transaction.atomic
def decide_expense(
    *,
    actor: Any,
    solicitud_id: int,
    action: Any,
    expected_version: Any,
    motivo: Any,
) -> SolicitudGasto:
    """Ejecuta la decisión de gasto de forma atómica bajo la secuencia definitiva:

    1. Inicio de transacción y bloqueo de la solicitud visible (404 si es ajena o inexistente).
    2. Comprobación de capacidad y prohibición de decisión propia (403).
    3. Validación de acción, versión y motivo dentro del servicio (400).
    4. Comprobación de versión vigente y transición sobre la fila bloqueada (409).
    5. Escritura conjunta de estado, versión y evento.
    """
    if actor is None:
        raise ExpensePermissionDeniedError("Se requiere un actor autenticado.")

    # 1. Obtener y bloquear exclusivamente sobre visible_expenses(actor)
    solicitud = (
        visible_expenses(actor)
        .select_for_update()
        .filter(pk=solicitud_id)
        .first()
    )
    if solicitud is None:
        # Objeto ajeno o inexistente: 404 estricto (precede a validación de contenido)
        raise ExpenseNotFoundError(f"Solicitud #{solicitud_id} no visible o inexistente.")

    # 2. Comprobar capacidad gastos.decidir y solicitante != actor
    if not has_capability(actor, "gastos.decidir"):
        # Visible sin permiso: 403 (precede a validación de contenido)
        raise ExpensePermissionDeniedError("El actor no posee la capacidad 'gastos.decidir'.")

    if solicitud.solicitante_id == actor.subject_id:
        # Intento de decisión sobre gasto propio: 403 (precede a validación de contenido)
        raise ExpensePermissionDeniedError(
            "No está permitido decidir sobre una solicitud propia (H2)."
        )

    # 3. Validación de acción, versión y motivo dentro del servicio tras accesos
    valid_action, valid_version, valid_motivo = validate_decision_content(
        action=action,
        expected_version=expected_version,
        motivo=motivo,
    )

    # 4. Comprobación de versión vigente sobre la fila bloqueada
    if solicitud.version != valid_version:
        raise ConcurrencyConflictError(
            f"Conflicto de concurrencia: versión esperada {valid_version}, "
            f"actual en BD {solicitud.version}."
        )

    # 5. Comprobación de transición permitida sobre el estado actual bloqueado
    mapa_estados = {
        "aceptar": EstadoSolicitud.ACEPTADA,
        "postergar": EstadoSolicitud.POSTERGADA,
        "rechazar": EstadoSolicitud.RECHAZADA,
    }
    transiciones_validas = {
        EstadoSolicitud.PRESENTADA: {"aceptar", "postergar", "rechazar"},
        EstadoSolicitud.POSTERGADA: {"aceptar", "rechazar"},
    }
    acciones_permitidas = transiciones_validas.get(solicitud.estado, set())
    if valid_action not in acciones_permitidas:
        raise InvalidTransitionError(
            f"Transición '{valid_action}' no permitida desde estado actual '{solicitud.estado}'."
        )

    # 6. Escritura conjunta atómica de estado, versión y evento
    nuevo_estado = mapa_estados[valid_action]
    estado_anterior = solicitud.estado

    solicitud.estado = nuevo_estado
    solicitud.version += 1
    solicitud.save(update_fields=["estado", "version"])

    DecisionGasto.objects.create(
        solicitud=solicitud,
        autor_id=actor.subject_id,
        motivo=valid_motivo,
        estado_anterior=estado_anterior,
        estado_resultante=nuevo_estado,
    )

    return solicitud


def _reservar_numero_solicitud_gasto() -> int:
    """Reserva un número libre y avanza la secuencia propia de gastos.

    PostgreSQL entrega valores únicos por transacción concurrente. Si la
    secuencia quedó detrás de números históricos cargados explícitamente, se
    descarta el valor ocupado y se solicita el siguiente; nunca se reutiliza una
    cabecera huérfana.
    """
    with connection.cursor() as cursor:
        while True:
            cursor.execute(
                "SELECT nextval(pg_get_serial_sequence('gastos_solicitudgasto', 'id'))"
            )
            numero = cursor.fetchone()[0]
            ocupado = SolicitudGasto.objects.filter(pk=numero).exists() or (
                TramiteBase.objects.filter(
                    circuito=Circuito.GASTO, numero_publico=numero
                ).exists()
            )
            if not ocupado:
                return numero


@transaction.atomic
def crear_solicitud_gasto(
    *,
    actor: Any,
    concepto: str,
    monto_estimado: Any,
    unidad_requirente: str,
    datos_transferencia: Mapping[str, Any] | None = None,
) -> SolicitudGasto:
    """Crea cabecera y solicitud juntas con valores fijados por el servidor.

    La capacidad se revalida dentro del servicio, el número público se reserva
    con la secuencia de PostgreSQL y el centro de costo institucional queda NULL:
    la unidad requirente no acredita un centro de costo. Si se informa un bloque
    completo de datos de transferencia, se crea su primera revisión en la misma
    transacción; un bloque parcial se rechaza antes de reservar el número.
    """
    if not has_capability(actor, "gastos.presentar"):
        raise PermissionDenied("El actor no posee la capacidad 'gastos.presentar'.")

    datos_validos = validar_datos_transferencia(datos_transferencia)

    numero = _reservar_numero_solicitud_gasto()
    base = TramiteBase.objects.create(
        circuito=Circuito.GASTO,
        numero_publico=numero,
        solicitante_actor_id=str(actor.subject_id),
        centro_costo_codigo=None,
    )
    solicitud = SolicitudGasto.objects.create(
        pk=numero,
        tramite_base=base,
        concepto=concepto,
        monto_estimado=monto_estimado,
        unidad_requirente=unidad_requirente,
        solicitante_id=actor.subject_id,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )
    if datos_validos is not None:
        RevisionDatosTransferencia.objects.create(
            solicitud=solicitud,
            numero_revision=1,
            actor_id=actor.subject_id,
            **datos_validos,
        )
    return solicitud
