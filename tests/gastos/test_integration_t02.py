"""Pruebas de integración del consumidor de gastos con el contrato de identidad T02."""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse

from gastos.auth import has_capability, resolve_actor
from gastos.models import SolicitudGasto
from gastos.queries import visible_expenses
from tests.gastos.conftest import Actor

User = get_user_model()


def test_sin_t02_resolve_actor_retorna_none_incluso_con_actor_en_request() -> None:
    """Sin T02 disponible, resolve_actor retorna None y no recurre a request.actor."""
    factory = RequestFactory()
    request = factory.get("/")
    # Inyectamos un actor sintético en el objeto request
    request.actor = Actor(subject_id=42, capabilities=frozenset(["gastos.presentar"]))

    # resolve_actor de producto NO debe usar request.actor como fallback
    assert resolve_actor(request) is None


def test_sin_t02_has_capability_retorna_false_incluso_con_capacidades_en_actor() -> None:
    """Sin T02, has_capability retorna False de forma segura sin evaluar atributos locales."""
    actor = Actor(
        subject_id=1,
        capabilities=frozenset(["gastos.presentar", "gastos.consultar_propias"]),
    )

    # has_capability de producto NO debe evaluar localmente actor.capabilities
    assert has_capability(actor, "gastos.presentar") is False
    assert has_capability(actor, "gastos.consultar_propias") is False
    assert has_capability(actor, "gastos.consultar_todas") is False
    assert has_capability(None, "gastos.presentar") is False


def test_error_interno_en_identidad_no_se_oculta_como_ausencia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si identidad.services tiene un fallo interno (ej. dependencia), no se silencia."""

    def fake_import_module(name: str) -> Any:
        if name == "identidad.services":
            raise ModuleNotFoundError(
                "No module named 'dep_interna_rotura'", name="dep_interna_rotura"
            )
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: object() if name == "identidad.services" else None,
    )
    monkeypatch.setattr("importlib.import_module", fake_import_module)

    factory = RequestFactory()
    request = factory.get("/")

    # resolve_actor no debe capturar el ModuleNotFoundError interno
    with pytest.raises(ModuleNotFoundError) as exc_info:
        resolve_actor(request)
    assert exc_info.value.name == "dep_interna_rotura"

    # has_capability tampoco debe capturar el ModuleNotFoundError interno
    actor = Actor(subject_id=1, capabilities=frozenset(["gastos.presentar"]))
    with pytest.raises(ModuleNotFoundError) as exc_info_cap:
        has_capability(actor, "gastos.presentar")
    assert exc_info_cap.value.name == "dep_interna_rotura"


@pytest.mark.django_db
def test_visible_expenses_comportamiento_estricto_contrato(
    mock_identity_registry: dict[int, Any],
) -> None:
    """visible_expenses devuelve todas, propias o ninguna según capacidades de actor."""
    user1 = User.objects.create_user("user1")
    user2 = User.objects.create_user("user2")

    s1 = SolicitudGasto.objects.create(
        concepto="S1", monto_estimado=Decimal("100"), unidad_requirente="U1", solicitante=user1
    )
    s2 = SolicitudGasto.objects.create(
        concepto="S2", monto_estimado=Decimal("200"), unidad_requirente="U2", solicitante=user2
    )

    actor_todas = Actor(subject_id=99, capabilities=frozenset(["gastos.consultar_todas"]))
    actor_propias_1 = Actor(
        subject_id=user1.pk, capabilities=frozenset(["gastos.consultar_propias"])
    )
    actor_sin_cap = Actor(subject_id=user1.pk, capabilities=frozenset([]))

    # Todas
    assert set(visible_expenses(actor_todas)) == {s1, s2}
    # Propias
    assert set(visible_expenses(actor_propias_1)) == {s1}
    # Ninguna
    assert list(visible_expenses(actor_sin_cap)) == []
    # Sin actor
    assert list(visible_expenses(None)) == []


@pytest.mark.django_db
def test_demo_deshabilitada_con_sesion_previa_produce_ausencia_actor(settings: Any) -> None:
    """Al desactivar la demo, resolve_actor produce ausencia de actor aun con sesión previa."""
    settings.DEMO_IDENTITY_ENABLED = False

    user = User.objects.create_user("user_demo")
    client = Client()
    client.force_login(user)

    # Intento de acceso a lista de gastos
    response = client.get(reverse("gastos:lista"))
    # Con demo deshabilitada debe denegar con 403 Forbidden y sin ofrecer login de demo
    assert response.status_code == 403
