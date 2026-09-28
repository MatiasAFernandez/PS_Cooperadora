"""Configuración global de la suite de pruebas."""

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _fast_password_hashers(settings: Any) -> None:
    """Configura MD5PasswordHasher para acelerar la suite de pruebas."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
