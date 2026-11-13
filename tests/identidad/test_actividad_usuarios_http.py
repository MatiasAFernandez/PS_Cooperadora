"""Pruebas HTTP de desactivación y reactivación administrativa de cuentas locales (SPEC-025)."""

import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from identidad.models import (
    CambioActividadCuentaLocal,
    CambioDatosCuentaLocal,
    CuentaLocal,
)

pytestmark = pytest.mark.django_db

CLAVE = "Clave-sintetica-segura-123!"


@pytest.fixture(autouse=True)
def configuracion_local(settings):
    """Bandera local activa; las pruebas renderizan las plantillas reales."""
    settings.LOCAL_IDENTITY_ENABLED = True
    settings.DEMO_IDENTITY_ENABLED = False


def _crear_cuenta(
    nombre,
    email,
    *,
    area="",
    grupos=(),
    is_active=True,
    is_staff=False,
    is_superuser=False,
    estado=CuentaLocal.Estado.APROBADA,
    verificado=True,
):
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password=CLAVE,
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    if grupos:
        user.groups.add(*grupos)
    return CuentaLocal.objects.create(
        user=user,
        email=email,
        nombre_completo=nombre,
        area_habitual=area,
        estado=estado,
        email_verificado_en=timezone.now() if verificado else None,
        decidida_en=timezone.now() if estado != CuentaLocal.Estado.PENDIENTE else None,
    )


def _extraer_hidden(html: str, nombre: str) -> str:
    match = re.search(rf'name="{nombre}"\s+value="([^"]*)"', html)
    assert match is not None, f"No se encontró el campo oculto {nombre} en el HTML."
    return match.group(1)


@pytest.fixture
def grupo_administracion(db):
    return Group.objects.create(name="local_administracion")


@pytest.fixture
def grupo_solicitante(db):
    return Group.objects.create(name="local_solicitante")


@pytest.fixture
def admin(grupo_administracion):
    return _crear_cuenta(
        "Admin Local",
        "admin.actividad@example.invalid",
        area="Administración",
        grupos=(grupo_administracion,),
    )


@pytest.fixture
def admin_client(admin):
    cliente = Client()
    cliente.force_login(admin.user)
    return cliente


@pytest.fixture
def solicitante(grupo_solicitante):
    return _crear_cuenta(
        "Solicitante Local",
        "solicitante.actividad@example.invalid",
        area="Compras",
        grupos=(grupo_solicitante,),
    )


@pytest.fixture
def usuario_objetivo(grupo_solicitante):
    return _crear_cuenta(
        "Ana Pérez",
        "ana.actividad@example.invalid",
        area="Compras",
        grupos=(grupo_solicitante,),
        estado=CuentaLocal.Estado.PENDIENTE,
        verificado=False,
    )


def test_get_confirmacion_no_escribe_y_cancelar_conserva_filtros(
    admin_client, usuario_objetivo
):
    base_url = reverse("cuentas:usuario_actividad", args=[usuario_objetivo.pk])
    resp = admin_client.get(f"{base_url}?q=compras&estado=PENDIENTE&page=2&ajeno=1")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("Cache-Control", "")

    html = resp.content.decode()
    assert "Ana Pérez" in html
    assert "ana.actividad@example.invalid" in html
    assert "Desactivar cuenta" in html
    assert "cierra los accesos anteriores" in html
    assert "conserva los trámites" in html
    assert _extraer_hidden(html, "activar") == "false"
    assert _extraer_hidden(html, "actividad_esperada") == "true"

    detalle_url = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    assert f'href="{detalle_url}?q=compras&amp;estado=PENDIENTE&amp;page=2"' in html
    assert "ajeno=1" not in html

    usuario_objetivo.user.refresh_from_db()
    assert usuario_objetivo.user.is_active is True
    assert CambioActividadCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0


def test_autorizacion_rechaza_anonimo_solicitante_y_staff_sin_capacidad(
    solicitante, usuario_objetivo
):
    url = reverse("cuentas:usuario_actividad", args=[usuario_objetivo.pk])

    anon = Client()
    assert anon.get(url).status_code == 403
    assert anon.post(url, {}).status_code == 403

    cli_sol = Client()
    cli_sol.force_login(solicitante.user)
    assert cli_sol.get(url).status_code == 403
    assert cli_sol.post(url, {}).status_code == 403

    staff_super = _crear_cuenta(
        "Staff Sin Cap",
        "staff.sincap@example.invalid",
        is_staff=True,
        is_superuser=True,
    )
    cli_staff = Client()
    cli_staff.force_login(staff_super.user)
    assert cli_staff.get(url).status_code == 403
    assert cli_staff.post(url, {}).status_code == 403


def test_flag_local_apagada_y_cuenta_inexistente_responden_404(
    settings, admin_client, usuario_objetivo
):
    url = reverse("cuentas:usuario_actividad", args=[usuario_objetivo.pk])
    settings.LOCAL_IDENTITY_ENABLED = False
    assert admin_client.get(url).status_code == 404
    assert admin_client.post(url, {}).status_code == 404

    settings.LOCAL_IDENTITY_ENABLED = True
    url_inexistente = reverse("cuentas:usuario_actividad", args=[999999])
    assert admin_client.get(url_inexistente).status_code == 404
    assert admin_client.post(url_inexistente, {}).status_code == 404


def test_motivo_en_blanco_y_mayor_2000_responden_400_y_conservan_datos(
    admin_client, usuario_objetivo
):
    url = reverse("cuentas:usuario_actividad", args=[usuario_objetivo.pk])

    resp_blanco = admin_client.post(
        url,
        {
            "activar": "false",
            "actividad_esperada": "true",
            "motivo": "   ",
        },
    )
    assert resp_blanco.status_code == 400
    assert "no-store" in resp_blanco.headers.get("Cache-Control", "")
    assert 'aria-invalid="true"' in resp_blanco.content.decode()

    motivo_largo = "x" * 2001
    resp_largo = admin_client.post(
        url,
        {
            "activar": "false",
            "actividad_esperada": "true",
            "motivo": motivo_largo,
        },
    )
    assert resp_largo.status_code == 400
    html_largo = resp_largo.content.decode()
    assert motivo_largo in html_largo
    assert _extraer_hidden(html_largo, "activar") == "false"
    assert _extraer_hidden(html_largo, "actividad_esperada") == "true"

    usuario_objetivo.user.refresh_from_db()
    assert usuario_objetivo.user.is_active is True
    assert CambioActividadCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0


def test_csrf_sin_token_responde_403(admin, usuario_objetivo):
    cli = Client(enforce_csrf_checks=True)
    cli.force_login(admin.user)
    url = reverse("cuentas:usuario_actividad", args=[usuario_objetivo.pk])
    resp = cli.post(
        url,
        {
            "activar": "false",
            "actividad_esperada": "true",
            "motivo": "Bloqueado sin CSRF",
        },
    )
    assert resp.status_code == 403
    usuario_objetivo.user.refresh_from_db()
    assert usuario_objetivo.user.is_active is True
    assert CambioActividadCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0


def test_desactivar_y_reactivar_eventos_mensajes_filtros_y_estados_intactos(
    admin_client, admin, usuario_objetivo, grupo_solicitante
):
    url_act = reverse("cuentas:usuario_actividad", args=[usuario_objetivo.pk])
    url_det = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    filtros = "q=ana&page=2"

    resp_des = admin_client.post(
        f"{url_act}?{filtros}&next=https://evil.example/phish",
        {
            "activar": "false",
            "actividad_esperada": "true",
            "motivo": "Baja temporal <script>alert(1)</script>",
            "next": "https://evil.example/phish",
        },
        follow=True,
    )
    assert resp_des.status_code == 200
    assert resp_des.redirect_chain[0] == (f"{url_det}?{filtros}", 302)

    usuario_objetivo.refresh_from_db()
    usuario_objetivo.user.refresh_from_db()
    assert usuario_objetivo.user.is_active is False
    assert usuario_objetivo.estado == CuentaLocal.Estado.PENDIENTE
    assert usuario_objetivo.email_verificado_en is None
    assert list(usuario_objetivo.user.groups.values_list("name", flat=True)) == [
        grupo_solicitante.name
    ]

    html_des = resp_des.content.decode()
    assert "Desactivada" in html_des
    assert "Reactivar cuenta" in html_des
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_des
    assert "<script>alert(1)</script>" not in html_des

    resp_get_react = admin_client.get(f"{url_act}?{filtros}")
    assert resp_get_react.status_code == 200
    html_get_react = resp_get_react.content.decode()
    assert "Reactivar no cambia la aprobación ni la verificación de correo" in html_get_react
    assert _extraer_hidden(html_get_react, "activar") == "true"
    assert _extraer_hidden(html_get_react, "actividad_esperada") == "false"

    resp_react = admin_client.post(
        f"{url_act}?{filtros}",
        {
            "activar": "true",
            "actividad_esperada": "false",
            "motivo": "Reincorporación al área",
        },
        follow=True,
    )
    assert resp_react.status_code == 200
    assert resp_react.redirect_chain[0] == (f"{url_det}?{filtros}", 302)

    usuario_objetivo.refresh_from_db()
    usuario_objetivo.user.refresh_from_db()
    assert usuario_objetivo.user.is_active is True
    assert usuario_objetivo.estado == CuentaLocal.Estado.PENDIENTE
    assert usuario_objetivo.email_verificado_en is None
    assert list(usuario_objetivo.user.groups.values_list("name", flat=True)) == [
        grupo_solicitante.name
    ]

    html_react = resp_react.content.decode()
    assert "Activa" in html_react
    assert "Reincorporación al área" in html_react
    assert CambioActividadCuentaLocal.objects.filter(
        cuenta=usuario_objetivo, autor=admin.user
    ).count() == 2


def test_noop_y_confirmacion_obsoleta(admin_client, usuario_objetivo):
    url = reverse("cuentas:usuario_actividad", args=[usuario_objetivo.pk])

    resp_noop = admin_client.post(
        url,
        {
            "activar": "true",
            "actividad_esperada": "true",
            "motivo": "Ya está activa",
        },
        follow=True,
    )
    assert resp_noop.status_code == 200
    assert "Sin cambios." in resp_noop.content.decode()
    assert CambioActividadCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0

    resp_obsoleta = admin_client.post(
        url,
        {
            "activar": "false",
            "actividad_esperada": "false",
            "motivo": "Confirmación desactualizada",
        },
    )
    assert resp_obsoleta.status_code == 409
    html_obs = resp_obsoleta.content.decode()
    assert "cambió desde que abrió la confirmación" in html_obs
    assert "Recargar confirmación" in html_obs
    assert "Confirmación desactualizada" in html_obs
    usuario_objetivo.user.refresh_from_db()
    assert usuario_objetivo.user.is_active is True


def test_self_post_no_escribe_y_ficha_propia_oculta_enlace_con_aviso(admin_client, admin):
    url_detalle = reverse("cuentas:usuario_detalle", args=[admin.pk])
    url_actividad = reverse("cuentas:usuario_actividad", args=[admin.pk])

    resp_ficha = admin_client.get(url_detalle)
    assert resp_ficha.status_code == 200
    html_ficha = resp_ficha.content.decode()
    assert url_actividad not in html_ficha
    assert "No podés desactivar tu propia cuenta." in html_ficha

    resp_post = admin_client.post(
        url_actividad,
        {
            "activar": "false",
            "actividad_esperada": "true",
            "motivo": "Intento de autodesactivación",
        },
    )
    assert resp_post.status_code == 400
    assert "No puede desactivar su propia cuenta." in resp_post.content.decode()
    admin.user.refresh_from_db()
    assert admin.user.is_active is True
    assert CambioActividadCuentaLocal.objects.filter(cuenta=admin).count() == 0


def test_historial_acceso_paginado_y_no_interfiere_con_historia_datos(
    admin_client, admin, usuario_objetivo
):
    for idx in range(1, 13):
        CambioActividadCuentaLocal.objects.create(
            cuenta=usuario_objetivo,
            autor=admin.user,
            motivo=f"Motivo actividad #{idx}",
            actividad_anterior=idx % 2 == 1,
            actividad_nueva=idx % 2 == 0,
        )
        CambioDatosCuentaLocal.objects.create(
            cuenta=usuario_objetivo,
            autor=admin.user,
            cambios={
                "legajo": {"anterior": f"LEG-{idx - 1}", "nuevo": f"LEG-{idx}"},
            },
        )

    url_det = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    resp = admin_client.get(f"{url_det}?q=ana&historia_page=2&actividad_page=2")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Motivo actividad #2" in html
    assert "Motivo actividad #1" in html
    assert "Motivo actividad #12" not in html
    assert "LEG-2" in html
    enlaces = [
        parse_qs(urlsplit(unescape(href)).query)
        for href in re.findall(r'href="([^"]+)"', html)
    ]
    assert {"q": ["ana"], "historia_page": ["2"], "actividad_page": ["1"]} in enlaces
    assert {"q": ["ana"], "historia_page": ["1"], "actividad_page": ["2"]} in enlaces
