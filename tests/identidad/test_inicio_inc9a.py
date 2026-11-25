"""Pruebas de regresión de Inicio (Incremento 9A): saludo seguro y tarjetas por rol."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from identidad.models import CuentaLocal

pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()


def _crear_cuenta_aprobada(username: str, nombre: str, grupos: list[str]) -> CuentaLocal:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.invalid",
        password="PasswordSintetica9A!",
        is_active=True,
    )
    for nombre_grupo in grupos:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)
    from django.utils import timezone

    return CuentaLocal.objects.create(
        user=user,
        email=user.email,
        nombre_completo=nombre,
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=timezone.now(),
    )


def test_inicio_corrige_hola_vacio_y_adapta_tarjetas_para_operadora(settings):
    settings.LOCAL_IDENTITY_ENABLED = True
    cuenta = _crear_cuenta_aprobada(
        "op_inicio_9a",
        "",
        ["demo_operadora", "demo_facturacion_operadora"],
    )
    cliente = Client()
    cliente.force_login(cuenta.user)

    resp = cliente.get(reverse("cuentas:inicio"))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Hola, ." not in html
    assert "Hola, op_inicio_9a." in html
    assert "Solicitudes de gasto" in html
    assert "Solicitudes de facturación" in html
    assert "Mis solicitudes de gasto" not in html
    assert "Mis solicitudes de facturación" not in html
    assert "Reportes" in html
    assert "Configuración" in html
    assert "Avisos" in html
    assert "Mi cuenta" in html
    assert "inicio-grid--few" not in html


def test_inicio_solicitante_y_perfil_pocas_tarjetas(settings):
    settings.LOCAL_IDENTITY_ENABLED = True
    solicitante = _crear_cuenta_aprobada(
        "sol_inicio_9a",
        "Ing. Ana Pérez",
        ["local_solicitante"],
    )
    solo_config = _crear_cuenta_aprobada(
        "config_9a",
        "Lic. Carlos Ruiz",
        ["demo_administracion"],
    )
    sin_circuitos = _crear_cuenta_aprobada(
        "sin_circ_9a",
        "Téc. Sofía Paz",
        [],
    )

    c_sol = Client()
    c_sol.force_login(solicitante.user)
    html_sol = c_sol.get(reverse("cuentas:inicio")).content.decode()
    assert "Hola, Ing. Ana Pérez." in html_sol
    assert "Mis solicitudes de gasto" in html_sol
    assert "Mis solicitudes de facturación" in html_sol

    c_pocas = Client()
    c_pocas.force_login(solo_config.user)
    html_pocas = c_pocas.get(reverse("cuentas:inicio")).content.decode()
    assert "inicio-grid--few" in html_pocas
    assert "Configuración" in html_pocas
    assert "Mi cuenta" in html_pocas

    c_una = Client()
    c_una.force_login(sin_circuitos.user)
    html_una = c_una.get(reverse("cuentas:inicio")).content.decode()
    assert "inicio-grid--few" in html_una
    assert "Mi cuenta" in html_una
    assert "todavía no tiene circuitos operativos asignados" in html_una
