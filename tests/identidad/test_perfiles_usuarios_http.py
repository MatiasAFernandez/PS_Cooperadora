"""Pruebas HTTP de asignación administrativa de perfiles locales (SPEC-026)."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from identidad.models import (
    CambioActividadCuentaLocal,
    CambioDatosCuentaLocal,
    CambioPerfilesCuentaLocal,
    CuentaLocal,
)
from identidad.perfiles_usuarios import PERFILES_CATALOGO

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
    for nombre_grupo in grupos:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)
    return CuentaLocal.objects.create(
        user=user,
        email=email,
        nombre_completo=nombre,
        area_habitual=area,
        estado=estado,
        email_verificado_en=timezone.now() if verificado else None,
        decidida_en=timezone.now() if estado != CuentaLocal.Estado.PENDIENTE else None,
    )


def _extraer_referencia(html: str) -> str:
    match = re.search(r'name="referencia"\s+value="([^"]*)"', html)
    assert match is not None, "No se encontró el campo oculto referencia en el HTML."
    return match.group(1)


@pytest.fixture
def admin():
    return _crear_cuenta(
        "Admin Local",
        "admin.perfiles@example.invalid",
        area="Administración",
        grupos=("local_administracion",),
    )


@pytest.fixture
def admin_client(admin):
    cliente = Client()
    cliente.force_login(admin.user)
    return cliente


@pytest.fixture
def solicitante():
    return _crear_cuenta(
        "Solicitante Local",
        "solicitante.perfiles@example.invalid",
        area="Compras",
        grupos=("local_solicitante",),
    )


@pytest.fixture
def usuario_objetivo():
    return _crear_cuenta(
        "Ana Pérez",
        "ana.perfiles@example.invalid",
        area="Compras",
        grupos=("local_solicitante",),
        estado=CuentaLocal.Estado.PENDIENTE,
        verificado=False,
    )


def test_get_admin_muestra_catalogo_humano_y_cancelar_conserva_filtros(
    admin_client, usuario_objetivo
):
    base_url = reverse("cuentas:usuario_perfiles", args=[usuario_objetivo.pk])
    resp = admin_client.get(f"{base_url}?q=compras&estado=PENDIENTE&page=2&ajeno=1")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("Cache-Control", "")

    html = resp.content.decode()
    assert "Ana Pérez" in html
    assert "ana.perfiles@example.invalid" in html
    assert "no aprueba, verifica ni activa la cuenta" in html
    assert _extraer_referencia(html)
    assert "demo_" not in html
    assert "identidad.administrar_cuentas" not in html
    assert "gestion.configurar" not in html

    for perfil in PERFILES_CATALOGO:
        assert perfil.nombre in html
        assert perfil.descripcion in html

    detalle_url = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    assert f'href="{detalle_url}?q=compras&amp;estado=PENDIENTE&amp;page=2"' in html
    assert "ajeno=1" not in html
    assert CambioPerfilesCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0


def test_autorizacion_rechaza_anonimo_solicitante_staff_y_superuser_sin_capacidad(
    solicitante, usuario_objetivo
):
    url = reverse("cuentas:usuario_perfiles", args=[usuario_objetivo.pk])

    anonimo = Client()
    assert anonimo.get(url).status_code == 403
    assert anonimo.post(url, {"motivo": "Prueba", "referencia": "x"}).status_code == 403

    sol_client = Client()
    sol_client.force_login(solicitante.user)
    assert sol_client.get(url).status_code == 403
    assert sol_client.post(url, {"motivo": "Prueba", "referencia": "x"}).status_code == 403

    staff = _crear_cuenta(
        "Staff Sin Grupo",
        "staff.perfiles@example.invalid",
        is_staff=True,
        is_superuser=True,
    )
    staff_client = Client()
    staff_client.force_login(staff.user)
    assert staff_client.get(url).status_code == 403
    assert staff_client.post(url, {"motivo": "Prueba", "referencia": "x"}).status_code == 403


def test_flag_local_identity_desactivada_devuelve_404(settings, admin_client, usuario_objetivo):
    settings.LOCAL_IDENTITY_ENABLED = False
    url = reverse("cuentas:usuario_perfiles", args=[usuario_objetivo.pk])
    assert admin_client.get(url).status_code == 404
    assert admin_client.post(url, {"motivo": "Prueba", "referencia": "x"}).status_code == 404


def test_post_actualiza_perfiles_registra_historia_y_conserva_estados_y_filtros(
    admin_client, usuario_objetivo
):
    base_url = reverse("cuentas:usuario_perfiles", args=[usuario_objetivo.pk])
    get_resp = admin_client.get(f"{base_url}?q=compras&page=2")
    referencia = _extraer_referencia(get_resp.content.decode())

    post_resp = admin_client.post(
        f"{base_url}?q=compras&page=2",
        {
            "perfiles": ["operacion_gastos", "lectura_facturacion"],
            "motivo": "Asignación operativa para pruebas.",
            "referencia": referencia,
        },
    )
    assert post_resp.status_code == 302
    assert "no-store" in post_resp.headers.get("Cache-Control", "")
    expected_detalle = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    assert post_resp["Location"] == f"{expected_detalle}?q=compras&page=2"

    ficha_resp = admin_client.get(post_resp["Location"])
    assert ficha_resp.status_code == 200
    ficha_html = ficha_resp.content.decode()
    assert "Se guardaron los cambios en los perfiles de la cuenta." in ficha_html
    assert "Operación de gastos" in ficha_html
    assert "Lectura global de facturación" in ficha_html
    assert "Asignación operativa para pruebas." in ficha_html

    usuario_objetivo.refresh_from_db()
    usuario_objetivo.user.refresh_from_db()
    grupos = set(usuario_objetivo.user.groups.values_list("name", flat=True))
    assert grupos == {"demo_operadora", "demo_facturacion_lectura"}
    assert "local_administracion" not in grupos
    assert usuario_objetivo.estado == CuentaLocal.Estado.PENDIENTE
    assert usuario_objetivo.email_verificado_en is None
    assert usuario_objetivo.user.is_active is True
    assert usuario_objetivo.user.check_password(CLAVE) is True

    eventos = list(CambioPerfilesCuentaLocal.objects.filter(cuenta=usuario_objetivo))
    assert len(eventos) == 1
    assert eventos[0].perfiles_anteriores == ["solicitante"]
    assert eventos[0].perfiles_nuevos == ["lectura_facturacion", "operacion_gastos"]


def test_guardar_vacio_preserva_grupos_ajenos_sin_exponer_internos(admin_client, usuario_objetivo):
    grupo_ajeno, _ = Group.objects.get_or_create(name="demo_solicitante")
    usuario_objetivo.user.groups.add(grupo_ajeno)

    url = reverse("cuentas:usuario_perfiles", args=[usuario_objetivo.pk])
    get_resp = admin_client.get(url)
    get_html = get_resp.content.decode()
    assert "Se conservan otros permisos que esta pantalla no modifica." in get_html
    assert "demo_solicitante" not in get_html

    referencia = _extraer_referencia(get_html)
    post_resp = admin_client.post(
        url,
        {
            "motivo": "Retiro de perfiles del catálogo.",
            "referencia": referencia,
        },
        follow=True,
    )
    assert post_resp.status_code == 200
    ficha_html = post_resp.content.decode()
    assert "Sin perfiles del catálogo asignados." in ficha_html
    assert "Se conservan otros permisos que esta pantalla no modifica." in ficha_html
    assert "demo_solicitante" not in ficha_html
    assert "sin acceso" not in ficha_html.lower()

    grupos = set(usuario_objetivo.user.groups.values_list("name", flat=True))
    assert grupos == {"demo_solicitante"}


def test_post_invalido_conserva_entradas_y_rechaza_csrf_sin_token(
    admin, admin_client, usuario_objetivo
):
    url = reverse("cuentas:usuario_perfiles", args=[usuario_objetivo.pk])
    referencia = _extraer_referencia(admin_client.get(url).content.decode())

    resp_choice = admin_client.post(
        url,
        {
            "perfiles": ["inexistente"],
            "motivo": "Motivo conservado",
            "referencia": referencia,
        },
    )
    assert resp_choice.status_code == 400
    html_choice = resp_choice.content.decode()
    assert "Motivo conservado" in html_choice
    assert _extraer_referencia(html_choice) == referencia

    resp_motivo = admin_client.post(
        url,
        {
            "perfiles": ["operacion_gastos"],
            "motivo": "   ",
            "referencia": referencia,
        },
    )
    assert resp_motivo.status_code == 400
    html_motivo = resp_motivo.content.decode()
    assert _extraer_referencia(html_motivo) == referencia
    assert 'value="operacion_gastos"' in html_motivo
    assert CambioPerfilesCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(admin.user)
    resp_csrf = csrf_client.post(
        url,
        {"perfiles": ["operacion_gastos"], "motivo": "Sin CSRF", "referencia": referencia},
    )
    assert resp_csrf.status_code == 403
    assert CambioPerfilesCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0


def test_noop_y_referencia_obsoleta_409_sin_escrituras(admin_client, usuario_objetivo):
    url = reverse("cuentas:usuario_perfiles", args=[usuario_objetivo.pk])
    ref_inicial = _extraer_referencia(admin_client.get(url).content.decode())

    resp_noop = admin_client.post(
        url,
        {
            "perfiles": ["solicitante"],
            "motivo": "Sin cambios reales.",
            "referencia": ref_inicial,
        },
        follow=True,
    )
    assert resp_noop.status_code == 200
    assert "Sin cambios." in resp_noop.content.decode()
    assert CambioPerfilesCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0

    # Otro cambio actualiza los perfiles y vuelve obsoleta ref_inicial
    resp_ok = admin_client.post(
        url,
        {
            "perfiles": ["operacion_gastos"],
            "motivo": "Cambio previo.",
            "referencia": ref_inicial,
        },
    )
    assert resp_ok.status_code == 302

    resp_409 = admin_client.post(
        url,
        {
            "perfiles": ["registro_pagos"],
            "motivo": "Intento obsoleto.",
            "referencia": ref_inicial,
        },
    )
    assert resp_409.status_code == 409
    html_409 = resp_409.content.decode()
    assert "Recargar formulario" in html_409
    assert "Intento obsoleto." in html_409
    assert set(usuario_objetivo.user.groups.values_list("name", flat=True)) == {"demo_operadora"}
    assert CambioPerfilesCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 1


def test_cuenta_propia_ficha_get_y_post_forzado_sin_mutacion(admin, admin_client):
    ficha_url = reverse("cuentas:usuario_detalle", args=[admin.pk])
    ficha_html = admin_client.get(ficha_url).content.decode()
    perfiles_url = reverse("cuentas:usuario_perfiles", args=[admin.pk])
    assert perfiles_url not in ficha_html
    assert "Otro administrador debe cambiar tus perfiles." in ficha_html

    get_resp = admin_client.get(perfiles_url)
    assert get_resp.status_code == 200
    get_html = get_resp.content.decode()
    assert "Otro administrador debe cambiar tus perfiles." in get_html
    assert 'name="perfiles"' not in get_html
    assert 'name="referencia"' not in get_html
    assert "Guardar perfiles" not in get_html
    assert "Guardar perfiles" not in get_html

    from identidad.perfiles_usuarios import generar_referencia_perfiles

    ref_propia = generar_referencia_perfiles(admin)
    post_resp = admin_client.post(
        perfiles_url,
        {
            "perfiles": ["solicitante"],
            "motivo": "Intento propio.",
            "referencia": ref_propia,
        },
    )
    assert post_resp.status_code == 400
    assert "No puede modificar sus propios perfiles." in post_resp.content.decode()
    assert set(admin.user.groups.values_list("name", flat=True)) == {"local_administracion"}
    assert CambioPerfilesCuentaLocal.objects.filter(cuenta=admin).count() == 0


def test_efecto_permisos_en_siguiente_peticion_con_client_target(admin_client):
    objetivo = _crear_cuenta(
        "Lucía Gómez",
        "lucia.perfiles@example.invalid",
        grupos=("local_solicitante",),
    )
    target_client = Client()
    target_client.force_login(objetivo.user)

    listado_url = reverse("cuentas:usuarios")
    assert target_client.get(listado_url).status_code == 403

    perfiles_url = reverse("cuentas:usuario_perfiles", args=[objetivo.pk])
    ref_alta = _extraer_referencia(admin_client.get(perfiles_url).content.decode())
    assert (
        admin_client.post(
            perfiles_url,
            {
                "perfiles": ["solicitante", "administracion_cuentas"],
                "motivo": "Habilita administración.",
                "referencia": ref_alta,
            },
        ).status_code
        == 302
    )
    assert target_client.get(listado_url).status_code == 200

    ref_baja = _extraer_referencia(admin_client.get(perfiles_url).content.decode())
    assert (
        admin_client.post(
            perfiles_url,
            {
                "perfiles": ["solicitante"],
                "motivo": "Retira administración.",
                "referencia": ref_baja,
            },
        ).status_code
        == 302
    )
    assert target_client.get(listado_url).status_code == 403


def test_ficha_paginacion_independiente_y_escape_en_historial_perfiles(
    admin, admin_client, usuario_objetivo
):
    for indice in range(12):
        CambioDatosCuentaLocal.objects.create(
            cuenta=usuario_objetivo,
            autor=admin.user,
            cambios={"area_habitual": {"anterior": f"A{indice}", "nuevo": f"B{indice}"}},
        )
        CambioActividadCuentaLocal.objects.create(
            cuenta=usuario_objetivo,
            autor=admin.user,
            actividad_anterior=True,
            actividad_nueva=False,
            motivo=f"Actividad {indice}",
        )
        CambioPerfilesCuentaLocal.objects.create(
            cuenta=usuario_objetivo,
            autor=admin.user,
            motivo="<script>alert(1)</script>" if indice == 0 else f"Perfil {indice}",
            perfiles_anteriores=["solicitante"],
            perfiles_nuevos=["operacion_gastos"],
        )

    ficha_url = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    resp = admin_client.get(f"{ficha_url}?q=ana&historia_page=2&actividad_page=2&perfiles_page=2")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "Operación de gastos" in html
    assert "Solicitante" in html
    assert "q=ana&amp;historia_page=2&amp;actividad_page=2&amp;perfiles_page=1" in html
