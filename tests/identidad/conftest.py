"""Datos sintéticos aislados para las pruebas del adaptador."""

import secrets

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


@pytest.fixture
def demo_accounts(db, settings):
    settings.DEMO_IDENTITY_ENABLED = True
    user_model = get_user_model()
    password = secrets.token_urlsafe(24)
    groups = {
        name: Group.objects.create(name=name)
        for name in ("demo_solicitante", "demo_operadora", "demo_lectura")
    }
    accounts = {}
    for username, group_name in {
        "demo_a": "demo_solicitante",
        "demo_b": "demo_solicitante",
        "demo_o": "demo_operadora",
        "demo_l": "demo_lectura",
    }.items():
        user = user_model.objects.create_user(username=username, password=password)
        user.groups.add(groups[group_name])
        accounts[username] = user
    return accounts, groups, password
