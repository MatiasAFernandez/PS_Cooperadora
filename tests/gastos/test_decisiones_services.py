"""Pruebas unitarias para los servicios de negocio de gastos (gastos/services.py).

Verifica:
- can_decide_expense: consulta pura, capacidades, visibilidad, H2 auto-decisión,
  matriz de transiciones.
- validate_decision_content: validación estricta de acciones, rechazo de booleanos y
  flotantes en versión, y obligatoriedad de motivo según acción.
- decide_expense (invocación directa):
  - T04-27: Rechazo de motivo vacío en postergar/rechazar (InvalidDecisionInputError).
  - T04-28: Rechazo de versión inválida (booleano / fracción / negativa) sin truncar
    (InvalidDecisionInputError).
  - T04-29: Precedencia de visibilidad (ExpenseNotFoundError) y permisos
    (ExpensePermissionDeniedError) sobre validación de contenido y concurrencia.
"""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model

from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto
from gastos.services import (
    ExpenseNotFoundError,
    ExpensePermissionDeniedError,
    InvalidDecisionInputError,
    can_decide_expense,
    decide_expense,
    validate_decision_content,
)
from identidad.services import Actor

User = get_user_model()


@pytest.mark.django_db
def test_can_decide_expense_actor_o_accion_invalida(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """can_decide_expense retorna False si el actor es None o la acción no es válida."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_a,
    )
    actor_o = Actor(
        subject_id=user_o.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas"}),
    )

    assert not can_decide_expense(None, solicitud, "aceptar")
    assert not can_decide_expense(actor_o, solicitud, "")
    assert not can_decide_expense(actor_o, solicitud, "aprobar")
    assert not can_decide_expense(actor_o, solicitud, "cancelar")


@pytest.mark.django_db
def test_can_decide_expense_sin_capacidad(demo_accounts: tuple[dict[str, Any], str]) -> None:
    """can_decide_expense retorna False si el actor carece de 'gastos.decidir'."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_l = accounts["demo_l"]

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_a,
    )
    actor_l = Actor(subject_id=user_l.pk, capabilities=frozenset({"gastos.consultar_todas"}))

    assert not can_decide_expense(actor_l, solicitud, "aceptar")
    assert not can_decide_expense(actor_l, solicitud, "postergar")
    assert not can_decide_expense(actor_l, solicitud, "rechazar")


@pytest.mark.django_db
def test_can_decide_expense_prohibicion_auto_decision_h2(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """can_decide_expense retorna False si el actor es el solicitante (prohibición H2)."""
    accounts, _ = demo_accounts
    user_o = accounts["demo_o"]

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos propios",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_o,
    )
    # Actor O con permisos de decidir, pero la solicitud es propia
    actor_o = Actor(
        subject_id=user_o.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas", "gastos.presentar"}),
    )

    assert not can_decide_expense(actor_o, solicitud, "aceptar")
    assert not can_decide_expense(actor_o, solicitud, "postergar")
    assert not can_decide_expense(actor_o, solicitud, "rechazar")


@pytest.mark.django_db
def test_can_decide_expense_solicitud_no_visible(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """can_decide_expense retorna False si la solicitud no está en visible_expenses(actor)."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_b = accounts["demo_b"]

    solicitud_b = SolicitudGasto.objects.create(
        concepto="Insumos B",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_b,
    )
    # Actor A con capacidad de decidir pero sólo consulta_propias (solicitud de B no visible)
    actor_a = Actor(
        subject_id=user_a.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_propias"}),
    )

    assert not can_decide_expense(actor_a, solicitud_b, "aceptar")


@pytest.mark.django_db
def test_can_decide_expense_matriz_transiciones(demo_accounts: tuple[dict[str, Any], str]) -> None:
    """can_decide_expense respeta la matriz de transiciones según estado de la solicitud."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_o = Actor(
        subject_id=user_o.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas"}),
    )

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_a,
        estado=EstadoSolicitud.PRESENTADA,
    )
    # En PRESENTADA: aceptar, postergar, rechazar válidos
    assert can_decide_expense(actor_o, solicitud, "aceptar")
    assert can_decide_expense(actor_o, solicitud, "postergar")
    assert can_decide_expense(actor_o, solicitud, "rechazar")

    # En POSTERGADA: aceptar y rechazar válidos; postergar inválido
    solicitud.estado = EstadoSolicitud.POSTERGADA
    solicitud.save()
    assert can_decide_expense(actor_o, solicitud, "aceptar")
    assert can_decide_expense(actor_o, solicitud, "rechazar")
    assert not can_decide_expense(actor_o, solicitud, "postergar")

    # En ACEPTADA: terminal, ningún cambio permitido
    solicitud.estado = EstadoSolicitud.ACEPTADA
    solicitud.save()
    assert not can_decide_expense(actor_o, solicitud, "aceptar")
    assert not can_decide_expense(actor_o, solicitud, "postergar")
    assert not can_decide_expense(actor_o, solicitud, "rechazar")

    # En RECHAZADA: terminal, ningún cambio permitido
    solicitud.estado = EstadoSolicitud.RECHAZADA
    solicitud.save()
    assert not can_decide_expense(actor_o, solicitud, "aceptar")
    assert not can_decide_expense(actor_o, solicitud, "postergar")
    assert not can_decide_expense(actor_o, solicitud, "rechazar")


def test_validate_decision_content_accion_desconocida() -> None:
    """validate_decision_content rechaza acciones que no pertenezcan al conjunto permitido."""
    with pytest.raises(InvalidDecisionInputError, match="Acción de decisión desconocida"):
        validate_decision_content(action="aprobar", expected_version=0, motivo="")

    with pytest.raises(InvalidDecisionInputError, match="Acción de decisión desconocida"):
        validate_decision_content(action="", expected_version=0, motivo="")


def test_validate_decision_content_rechazo_booleano_y_flotante_version() -> None:
    """validate_decision_content rechaza booleanos, flotantes (sin truncar) y negativos."""
    # Rechazo estricto de booleanos (bool es subclase de int en Python)
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version=True, motivo="")

    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version=False, motivo="")

    # Rechazo de flotantes sin truncamiento
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version=1.5, motivo="")

    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version="1.5", motivo="")

    # Rechazo de enteros y cadenas negativas
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version=-1, motivo="")

    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version="-1", motivo="")

    # Rechazo de None o no numéricos
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version=None, motivo="")

    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version="abc", motivo="")

    # B3: Rechazo de dígitos no ASCII (ej: U+00B2 '²' que da True en isdigit())
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version="\u00b2", motivo="")

    # B3: Rechazo por desbordamiento de conversión entera (>4300 dígitos)
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        validate_decision_content(action="aceptar", expected_version="1" * 4301, motivo="")


def test_validate_decision_content_version_valida() -> None:
    """validate_decision_content acepta enteros y strings numéricas no negativas."""
    action, ver, mot = validate_decision_content(action="aceptar", expected_version=0, motivo="")
    assert ver == 0

    action, ver, mot = validate_decision_content(action="aceptar", expected_version="3", motivo="")
    assert ver == 3


def test_validate_decision_content_motivo_obligatorio() -> None:
    """validate_decision_content exige motivo no vacío para postergar y rechazar, y lo limpia."""
    # Postergar exige motivo
    with pytest.raises(InvalidDecisionInputError, match="El motivo es obligatorio"):
        validate_decision_content(action="postergar", expected_version=0, motivo="")

    with pytest.raises(InvalidDecisionInputError, match="El motivo es obligatorio"):
        validate_decision_content(action="postergar", expected_version=0, motivo="   ")

    with pytest.raises(InvalidDecisionInputError, match="El motivo es obligatorio"):
        validate_decision_content(action="postergar", expected_version=0, motivo=None)

    # Rechazar exige motivo
    with pytest.raises(InvalidDecisionInputError, match="El motivo es obligatorio"):
        validate_decision_content(action="rechazar", expected_version=0, motivo="")

    with pytest.raises(InvalidDecisionInputError, match="El motivo es obligatorio"):
        validate_decision_content(action="rechazar", expected_version=0, motivo="   ")

    # Aceptar permite motivo vacío y lo convierte a string limpio
    action, ver, mot = validate_decision_content(action="aceptar", expected_version=0, motivo="")
    assert mot == ""

    action, ver, mot = validate_decision_content(action="aceptar", expected_version=0, motivo=None)
    assert mot == ""

    action, ver, mot = validate_decision_content(
        action="postergar", expected_version=0, motivo="  Falta presupuesto  "
    )
    assert mot == "Falta presupuesto"


def test_validate_decision_content_rechazo_caracter_nul_en_motivo() -> None:
    """B4: validate_decision_content rechaza caracteres NUL (0x00) en el motivo."""
    for action in ("aceptar", "postergar", "rechazar"):
        with pytest.raises(InvalidDecisionInputError, match="caracteres nulos"):
            validate_decision_content(
                action=action,
                expected_version=0,
                motivo="Motivo con nulo\x00en el texto",
            )


@pytest.mark.django_db
def test_t04_27_servicio_motivo_vacio_rechazado(demo_accounts: tuple[dict[str, Any], str]) -> None:
    """T04-27: Invocación directa al servicio con motivo obligatorio vacío.

    Lanza InvalidDecisionInputError (HTTP 400). Transacción revertida y 0 escrituras en BD.
    """
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_o = Actor(
        subject_id=user_o.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas"}),
    )

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_a,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    with pytest.raises(InvalidDecisionInputError, match="El motivo es obligatorio"):
        decide_expense(
            actor=actor_o,
            solicitud_id=solicitud.pk,
            action="postergar",
            expected_version=0,
            motivo="   ",
        )

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_28_servicio_version_invalida_rechazada(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-28: Invocación directa al servicio con versión inválida (booleano / fracción / negativa).

    Lanza InvalidDecisionInputError (HTTP 400) sin truncar fracciones ni admitir booleanos.
    Transacción revertida y 0 escrituras en BD.
    """
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_o = Actor(
        subject_id=user_o.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas"}),
    )

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_a,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    # Versión booleana
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        decide_expense(
            actor=actor_o,
            solicitud_id=solicitud.pk,
            action="aceptar",
            expected_version=True,
            motivo="",
        )

    # Versión flotante
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        decide_expense(
            actor=actor_o,
            solicitud_id=solicitud.pk,
            action="aceptar",
            expected_version=1.5,
            motivo="",
        )

    # Versión negativa
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        decide_expense(
            actor=actor_o,
            solicitud_id=solicitud.pk,
            action="aceptar",
            expected_version=-1,
            motivo="",
        )

    # B3: Versión con dígito no ASCII (U+00B2 '²')
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        decide_expense(
            actor=actor_o,
            solicitud_id=solicitud.pk,
            action="aceptar",
            expected_version="\u00b2",
            motivo="",
        )

    # B3: Versión que supera el límite de conversión de enteros (>4300 dígitos)
    with pytest.raises(InvalidDecisionInputError, match="entero no negativo"):
        decide_expense(
            actor=actor_o,
            solicitud_id=solicitud.pk,
            action="aceptar",
            expected_version="1" * 4301,
            motivo="",
        )

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_servicio_motivo_con_caracter_nul_rechazado(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """B4: decide_expense rechaza motivo con NUL en aceptar, postergar y rechazar.

    Lanza InvalidDecisionInputError (HTTP 400). Transacción revertida y 0 escrituras en BD.
    """
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_o = Actor(
        subject_id=user_o.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas"}),
    )

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos con NUL",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Laboratorio",
        solicitante=user_a,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    for act in ("aceptar", "postergar", "rechazar"):
        with pytest.raises(InvalidDecisionInputError, match="caracteres nulos"):
            decide_expense(
                actor=actor_o,
                solicitud_id=solicitud.pk,
                action=act,
                expected_version=0,
                motivo="Texto con byte\x00nulo no permitido",
            )

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_29_servicio_precedencia_visibilidad_y_permisos_sobre_contenido(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-29: Invocación directa: precedencia de visibilidad y permisos sobre contenido.

    - Llamada directa sobre solicitud ajena con versión/acción inválida lanza
      ExpenseNotFoundError (404).
    - Llamada sobre solicitud visible sin permiso con versión/acción inválida lanza
      ExpensePermissionDeniedError (403).
    0 escrituras en BD.
    """
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_b = accounts["demo_b"]
    user_l = accounts["demo_l"]

    solicitud_b = SolicitudGasto.objects.create(
        concepto="Insumos de B",
        monto_estimado=Decimal("7000.00"),
        unidad_requirente="Biblioteca",
        solicitante=user_b,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    actor_a = Actor(
        subject_id=user_a.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    # Objeto ajeno (no visible para A): lanza ExpenseNotFoundError (404) antes de evaluar contenido
    with pytest.raises(ExpenseNotFoundError, match="no visible o inexistente"):
        decide_expense(
            actor=actor_a,
            solicitud_id=solicitud_b.pk,
            action="accion_invalida",
            expected_version=True,
            motivo="",
        )

    # Objeto ajeno con B3 o B4 sigue lanzando 404 (precedencia de visibilidad)
    with pytest.raises(ExpenseNotFoundError, match="no visible o inexistente"):
        decide_expense(
            actor=actor_a,
            solicitud_id=solicitud_b.pk,
            action="aceptar",
            expected_version="\u00b2",
            motivo="Texto con byte\x00nulo",
        )

    # Objeto visible pero sin permiso (L ve todo pero no tiene gastos.decidir)
    actor_l = Actor(subject_id=user_l.pk, capabilities=frozenset({"gastos.consultar_todas"}))
    with pytest.raises(ExpensePermissionDeniedError, match="gastos.decidir"):
        decide_expense(
            actor=actor_l,
            solicitud_id=solicitud_b.pk,
            action="accion_invalida",
            expected_version="1.5",
            motivo="",
        )

    # Objeto visible sin permiso con B3 o B4 lanza 403 (precedencia de permisos)
    with pytest.raises(ExpensePermissionDeniedError, match="gastos.decidir"):
        decide_expense(
            actor=actor_l,
            solicitud_id=solicitud_b.pk,
            action="aceptar",
            expected_version="1" * 4301,
            motivo="Texto con byte\x00nulo",
        )

    # Solicitud propia con permiso general (H2 auto-decisión denegada antes de evaluar contenido)
    actor_b_con_decidir = Actor(
        subject_id=user_b.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas"}),
    )
    with pytest.raises(ExpensePermissionDeniedError, match="solicitud propia"):
        decide_expense(
            actor=actor_b_con_decidir,
            solicitud_id=solicitud_b.pk,
            action="accion_invalida",
            expected_version="version_corrupta",
            motivo="",
        )

    # Solicitud propia con B3 o B4 lanza 403 (precedencia de permisos)
    with pytest.raises(ExpensePermissionDeniedError, match="solicitud propia"):
        decide_expense(
            actor=actor_b_con_decidir,
            solicitud_id=solicitud_b.pk,
            action="aceptar",
            expected_version="\u00b2",
            motivo="Texto con byte\x00nulo",
        )

    solicitud_b.refresh_from_db()
    assert solicitud_b.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_b.version == 0
    assert not DecisionGasto.objects.exists()
