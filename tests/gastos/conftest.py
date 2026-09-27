"""Fixtures y dobles de prueba para el módulo de gastos."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.middleware.csrf import _get_new_csrf_string, _mask_cipher_secret
from django.test import Client

User = get_user_model()


@dataclass(frozen=True)
class Actor:
    """Estructura de doble de prueba del actor según el contrato de demo v1."""

    subject_id: Any
    capabilities: frozenset[str]


def issue_csrf_credentials(client: Client) -> str:
    """Configura una cookie CSRF válida en el test client y retorna el token correspondiente."""
    secret = _get_new_csrf_string()
    client.cookies["csrftoken"] = secret
    return _mask_cipher_secret(secret)


@pytest.fixture
def create_actor() -> Callable[[str, list[str]], tuple[Any, Actor]]:
    """Crea un usuario y un actor asociado con las capacidades indicadas."""

    def _factory(username: str, capabilities: list[str]) -> tuple[Any, Actor]:
        user, _ = User.objects.get_or_create(username=username)
        actor = Actor(
            subject_id=user.pk,
            capabilities=frozenset(capabilities),
        )
        return user, actor

    return _factory


@pytest.fixture
def mock_identity_registry(monkeypatch: pytest.MonkeyPatch) -> dict[int, Actor]:
    """Registro en memoria y mocks para resolver actor y capacidades en pruebas desacopladas."""
    registry: dict[int, Actor] = {}

    def mock_resolve_actor(request: Any) -> Any:
        req_user = getattr(request, "user", None)
        if req_user and req_user.is_authenticated:
            return registry.get(req_user.pk)
        return None

    def mock_has_capability(actor: Any, code: str) -> bool:
        if actor is None or not hasattr(actor, "capabilities"):
            return False
        return code in getattr(actor, "capabilities", ())

    monkeypatch.setattr("gastos.auth.resolve_actor", mock_resolve_actor)
    monkeypatch.setattr("gastos.views.resolve_actor", mock_resolve_actor)
    monkeypatch.setattr("gastos.auth.has_capability", mock_has_capability)
    monkeypatch.setattr("gastos.views.has_capability", mock_has_capability)
    monkeypatch.setattr("gastos.queries.has_capability", mock_has_capability)

    return registry


@pytest.fixture
def auth_client(
    mock_identity_registry: dict[int, Actor],
) -> Callable[[Any, Actor], Client]:
    """Crea un test client estándar con el usuario logueado y el actor inyectado en el registro."""

    def _factory(user: Any, actor: Actor) -> Client:
        mock_identity_registry[user.pk] = actor
        client = Client()
        client.force_login(user)
        return client

    return _factory


@pytest.fixture
def csrf_auth_client(
    mock_identity_registry: dict[int, Actor],
) -> Callable[[Any, Actor], tuple[Client, str]]:
    """Crea un test client con enforce_csrf_checks=True, sesión iniciada y token CSRF válido."""

    def _factory(user: Any, actor: Actor) -> tuple[Client, str]:
        mock_identity_registry[user.pk] = actor
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        token = issue_csrf_credentials(client)
        return client, token

    return _factory
