"""Fixtures y configuración de pruebas para el módulo de gastos."""

import secrets
from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.middleware.csrf import _get_new_csrf_string, _mask_cipher_secret
from django.test import Client

from identidad.services import GROUP_CAPABILITIES, Actor

User = get_user_model()


@pytest.fixture(autouse=True)
def enable_demo_identity(settings: Any) -> None:
    """Habilita la identidad de demo por defecto para las pruebas de gastos."""
    settings.DEMO_IDENTITY_ENABLED = True


@pytest.fixture
def demo_groups(db: Any) -> dict[str, Group]:
    """Crea los grupos de identidad de demo."""
    return {
        name: Group.objects.get_or_create(name=name)[0]
        for name in ("demo_solicitante", "demo_operadora", "demo_lectura")
    }


@pytest.fixture
def demo_accounts(db: Any, demo_groups: dict[str, Group]) -> tuple[dict[str, Any], str]:
    """Crea las cuentas sintéticas A, B, O y L asociadas a sus respectivos grupos."""
    password = secrets.token_urlsafe(24)
    accounts = {}
    for username, group_name in {
        "demo_a": "demo_solicitante",
        "demo_b": "demo_solicitante",
        "demo_o": "demo_operadora",
        "demo_l": "demo_lectura",
    }.items():
        user = User.objects.create_user(username=username, password=password)
        user.groups.add(demo_groups[group_name])
        accounts[username] = user
    return accounts, password


def issue_csrf_credentials(client: Client) -> str:
    """Configura una cookie CSRF válida en el test client y retorna el token correspondiente."""
    secret = _get_new_csrf_string()
    client.cookies["csrftoken"] = secret
    return _mask_cipher_secret(secret)


@pytest.fixture
def create_actor(demo_groups: dict[str, Group]) -> Callable[[str, list[str]], tuple[Any, Actor]]:
    """Crea un usuario real asignado al grupo correspondiente según las capacidades requeridas."""

    def _factory(username: str, capabilities: list[str]) -> tuple[Any, Actor]:
        user, _ = User.objects.get_or_create(username=username)
        caps_set = frozenset(capabilities)
        if "gastos.presentar" in caps_set:
            user.groups.add(demo_groups["demo_solicitante"])
        elif "gastos.decidir" in caps_set:
            user.groups.add(demo_groups["demo_operadora"])
        elif "gastos.consultar_todas" in caps_set:
            user.groups.add(demo_groups["demo_lectura"])
        else:
            user.groups.clear()

        group_names = user.groups.values_list("name", flat=True)
        real_caps = frozenset().union(
            *(GROUP_CAPABILITIES[name] for name in group_names if name in GROUP_CAPABILITIES)
        )
        actor = Actor(subject_id=user.pk, capabilities=real_caps)
        return user, actor

    return _factory


@pytest.fixture
def auth_client() -> Callable[[Any, Any], Client]:
    """Crea un test client estándar con el usuario autenticado vía sesión real."""

    def _factory(user: Any, actor: Any = None) -> Client:
        client = Client()
        client.force_login(user)
        return client

    return _factory


@pytest.fixture
def csrf_auth_client() -> Callable[[Any, Any], tuple[Client, str]]:
    """Crea un test client con enforce_csrf_checks=True, sesión iniciada y token CSRF válido."""

    def _factory(user: Any, actor: Any = None) -> tuple[Client, str]:
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        token = issue_csrf_credentials(client)
        return client, token

    return _factory
