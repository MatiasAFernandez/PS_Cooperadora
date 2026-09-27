"""CT-01 a CT-03: sesión y capacidades resueltas en servidor."""

from dataclasses import FrozenInstanceError

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, RequestFactory

from identidad.services import Actor, has_capability, resolve_actor


def _request_with_session(client: Client):
    response = client.get("/demo/")
    return response.wsgi_request


@pytest.mark.django_db
def test_ct01_solo_sesion_valida_y_cuenta_activa_producen_actor(demo_accounts) -> None:
    accounts, _, password = demo_accounts
    client = Client()

    assert resolve_actor(_request_with_session(client)) is None
    assert not client.login(username="demo_a", password="incorrecta")
    assert resolve_actor(_request_with_session(client)) is None

    assert client.login(username="demo_a", password=password)
    actor = resolve_actor(_request_with_session(client))
    assert actor == Actor(
        subject_id=accounts["demo_a"].pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )
    with pytest.raises(FrozenInstanceError):
        actor.subject_id = 999
    with pytest.raises(AttributeError):
        actor.capabilities.add("gastos.decidir")

    client.logout()
    assert resolve_actor(_request_with_session(client)) is None

    accounts["demo_a"].is_active = False
    accounts["demo_a"].save(update_fields=["is_active"])
    assert not client.login(username="demo_a", password=password)
    assert resolve_actor(_request_with_session(client)) is None


@pytest.mark.django_db
def test_ct02_demo_apagada_anula_una_sesion_previa(demo_accounts, settings) -> None:
    _, _, password = demo_accounts
    client = Client()
    assert client.login(username="demo_a", password=password)
    assert resolve_actor(_request_with_session(client)) is not None

    settings.DEMO_IDENTITY_ENABLED = False
    assert resolve_actor(_request_with_session(client)) is None
    assert client.get("/demo/acceso/").status_code == 404
    assert client.get("/demo/").status_code == 404


@pytest.mark.django_db
def test_ct02_datos_del_cliente_y_grupos_desconocidos_no_conceden_capacidades(
    demo_accounts,
) -> None:
    accounts, _, password = demo_accounts
    client = Client()
    assert client.login(username="demo_a", password=password)
    response = client.get(
        "/demo/?subject_id=999&capabilities=gastos.decidir",
        HTTP_X_USER="demo_o",
        HTTP_X_GROUPS="demo_operadora",
    )
    actor = resolve_actor(response.wsgi_request)
    assert actor.subject_id == accounts["demo_a"].pk
    assert not has_capability(actor, "gastos.decidir")
    assert has_capability(actor, "gastos.presentar") is True
    assert has_capability(actor, "gastos.no_existe") is False
    assert has_capability(None, "gastos.presentar") is False

    form_request = RequestFactory().post(
        "/demo/", {"subject_id": "999", "capabilities": "gastos.decidir"}
    )
    form_request.session = client.session
    assert resolve_actor(form_request) == actor

    accounts["demo_a"].groups.add(Group.objects.create(name="grupo_desconocido"))
    assert resolve_actor(_request_with_session(client)).capabilities == actor.capabilities

    # Ni un atributo request.actor ni un usuario inventado reemplazan la sesión.
    request = RequestFactory().get("/demo/?subject_id=999")
    request.actor = Actor(subject_id=999, capabilities=frozenset({"gastos.decidir"}))
    request.user = accounts["demo_o"]
    assert resolve_actor(request) is None


@pytest.mark.django_db
def test_perfiles_sinteticos_tienen_solo_las_capacidades_de_su_grupo(demo_accounts) -> None:
    _, _, password = demo_accounts
    expected = {
        "demo_a": {"gastos.presentar", "gastos.consultar_propias"},
        "demo_b": {"gastos.presentar", "gastos.consultar_propias"},
        "demo_o": {"gastos.consultar_todas", "gastos.decidir"},
        "demo_l": {"gastos.consultar_todas"},
    }
    for username, capabilities in expected.items():
        client = Client()
        assert client.login(username=username, password=password)
        actor = resolve_actor(_request_with_session(client))
        assert actor.capabilities == frozenset(capabilities)


@pytest.mark.django_db
def test_ct03_staff_superusuario_y_cuenta_sin_grupo_no_tienen_permiso(settings) -> None:
    settings.DEMO_IDENTITY_ENABLED = True
    user_model = get_user_model()
    password = "solo-prueba-local"
    users = [
        user_model.objects.create_user("sin_grupo", password=password),
        user_model.objects.create_user("staff", password=password, is_staff=True),
        user_model.objects.create_superuser("superusuario", password=password),
    ]
    for user in users:
        client = Client()
        assert client.login(username=user.username, password=password)
        actor = resolve_actor(_request_with_session(client))
        assert actor is not None
        assert actor.capabilities == frozenset()
        assert has_capability(actor, "gastos.decidir") is False


@pytest.mark.django_db
def test_ct03_altas_y_revocaciones_se_reflejan_en_la_siguiente_peticion(demo_accounts) -> None:
    _, groups, password = demo_accounts
    client = Client()
    assert client.login(username="demo_a", password=password)
    before = resolve_actor(_request_with_session(client))
    assert before.capabilities == frozenset({"gastos.presentar", "gastos.consultar_propias"})

    user = get_user_model().objects.get(username="demo_a")
    user.groups.add(groups["demo_operadora"])
    combined = resolve_actor(_request_with_session(client))
    assert has_capability(combined, "gastos.decidir")
    assert has_capability(combined, "gastos.consultar_todas")

    user.groups.clear()
    after = resolve_actor(_request_with_session(client))
    assert after.capabilities == frozenset()
    assert before.capabilities == frozenset({"gastos.presentar", "gastos.consultar_propias"})
