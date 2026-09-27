"""Acceso HTTP de demo y preparación local reproducible."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse

from identidad.management.commands.preparar_identidad_demo import DEMO_USERS


@pytest.mark.django_db
def test_login_logout_y_cuenta_inactiva(demo_accounts) -> None:
    accounts, _, password = demo_accounts
    client = Client(enforce_csrf_checks=True)
    login_url = reverse("identidad:login")
    home_url = reverse("identidad:inicio")
    logout_url = reverse("identidad:logout")

    response = client.get(login_url)
    assert response.status_code == 200
    csrf = client.cookies["csrftoken"].value
    no_csrf = client.post(login_url, {"username": "demo_a", "password": "incorrecta"})
    assert no_csrf.status_code == 403
    response = client.post(
        login_url,
        {"username": "demo_a", "password": "incorrecta", "csrfmiddlewaretoken": csrf},
    )
    assert response.status_code == 200
    response = client.post(
        login_url,
        {"username": "demo_a", "password": password, "csrfmiddlewaretoken": csrf},
    )
    assert response.status_code == 302
    assert response.url == home_url
    assert str(accounts["demo_a"].pk) in client.get(home_url).content.decode()

    assert client.get(logout_url).status_code == 405
    csrf = client.cookies["csrftoken"].value
    response = client.post(logout_url, {"csrfmiddlewaretoken": csrf})
    assert response.status_code == 302
    assert client.get(home_url).status_code == 302

    accounts["demo_a"].is_active = False
    accounts["demo_a"].save(update_fields=["is_active"])
    client.get(login_url)
    csrf = client.cookies["csrftoken"].value
    response = client.post(
        login_url,
        {"username": "demo_a", "password": password, "csrfmiddlewaretoken": csrf},
    )
    assert response.status_code == 200
    assert client.get(home_url).status_code == 302


@pytest.mark.django_db
def test_login_descarta_next_externo(demo_accounts) -> None:
    _, _, password = demo_accounts
    client = Client()
    response = client.post(
        reverse("identidad:login"),
        {"username": "demo_a", "password": password, "next": "https://externo.invalid/"},
    )
    assert response.status_code == 302
    assert response.url == reverse("identidad:inicio")


@pytest.mark.django_db
def test_salida_sigue_disponible_tras_apagar_la_demo(demo_accounts, settings) -> None:
    _, _, password = demo_accounts
    client = Client()
    assert client.login(username="demo_a", password=password)
    settings.DEMO_IDENTITY_ENABLED = False
    response = client.post(reverse("identidad:logout"))
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_preparar_cuentas_sin_claves_fijas_y_repetir_sin_perderlas(settings) -> None:
    settings.DEMO_IDENTITY_ENABLED = True
    call_command("preparar_identidad_demo", verbosity=0)
    user_model = get_user_model()
    for username, group_name in DEMO_USERS.items():
        user = user_model.objects.get(username=username)
        assert not user.has_usable_password()
        assert set(user.groups.values_list("name", flat=True)) == {group_name}

    user = user_model.objects.get(username="demo_a")
    user.set_password("contraseña-local-de-prueba")
    user.save(update_fields=["password"])
    previous_hash = user.password
    call_command("preparar_identidad_demo", verbosity=0)
    user.refresh_from_db()
    assert user.password == previous_hash
    assert user_model.objects.filter(username__in=DEMO_USERS).count() == 4


@pytest.mark.django_db
def test_preparacion_rechaza_flag_apagado_y_colision(settings) -> None:
    settings.DEMO_IDENTITY_ENABLED = False
    with pytest.raises(CommandError):
        call_command("preparar_identidad_demo", verbosity=0)
    assert not get_user_model().objects.filter(username__in=DEMO_USERS).exists()

    settings.DEMO_IDENTITY_ENABLED = True
    user = get_user_model().objects.create_user("demo_a", is_staff=True)
    with pytest.raises(CommandError):
        call_command("preparar_identidad_demo", verbosity=0)
    assert user.groups.count() == 0
    assert not get_user_model().objects.filter(username="demo_b").exists()
