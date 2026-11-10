from dataclasses import replace
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from tests.facturacion.conftest import datos, escenario  # noqa: F401


@pytest.fixture
def administrador(request):
    contexto = request.getfixturevalue("escenario")
    user = get_user_model().objects.create_user(
        username="administrador_sintetico", email="admin@example.invalid"
    )
    user.groups.set(contexto.usuarios["o"].groups.all())
    user.groups.add(Group.objects.get_or_create(name="demo_administracion")[0])
    actor = replace(
        contexto.actores["o"],
        subject_id=user.pk,
        capabilities=contexto.actores["o"].capabilities | {"gestion.configurar"},
    )
    return SimpleNamespace(user=user, actor=actor)
