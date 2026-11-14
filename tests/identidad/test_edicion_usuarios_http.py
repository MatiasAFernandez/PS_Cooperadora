"""Pruebas HTTP de edición administrativa de datos básicos locales (SPEC-024)."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from identidad.datos_usuarios import generar_referencia_edicion
from identidad.models import CambioDatosCuentaLocal, CuentaLocal

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
    cuit_cuil="",
    legajo="",
    grupos=(),
    is_staff=False,
    is_superuser=False,
):
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password=CLAVE,
        is_active=True,
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
        cuit_cuil=cuit_cuil,
        legajo=legajo,
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=timezone.now(),
        decidida_en=timezone.now(),
    )


def _extraer_referencia(html: str) -> str:
    match = re.search(r'name="referencia"\s+value="([^"]*)"', html)
    assert match is not None, "No se encontró el campo oculto referencia en el HTML."
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
        "admin.edicion@example.invalid",
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
        "solicitante.edicion@example.invalid",
        area="Compras",
        grupos=(grupo_solicitante,),
    )


@pytest.fixture
def usuario_objetivo():
    return _crear_cuenta(
        "Ana Pérez",
        "ana.perez@example.invalid",
        area="Compras",
        cuit_cuil="27-12345678-9",
        legajo="LEG-100",
    )


def test_get_y_post_admin_guarda_datos_y_muestra_historial(admin_client, admin, usuario_objetivo):
    url_editar = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    resp_get = admin_client.get(url_editar)
    assert resp_get.status_code == 200
    assert "no-store" in resp_get.headers.get("Cache-Control", "")
    html_get = resp_get.content.decode()
    assert "ana.perez@example.invalid" in html_get
    assert "Guardar cambios" in html_get
    assert "Cancelar" in html_get

    referencia = _extraer_referencia(html_get)
    resp_post = admin_client.post(
        url_editar,
        {
            "nombre_completo": "  Ana María Pérez  ",
            "area_habitual": "Tesorería",
            "cuit_cuil": "27-12345678-9",
            "legajo": "LEG-200",
            "referencia": referencia,
        },
        follow=True,
    )
    assert resp_post.status_code == 200
    assert resp_post.redirect_chain[0][0] == reverse(
        "cuentas:usuario_detalle", args=[usuario_objetivo.pk]
    )
    assert resp_post.redirect_chain[0][1] == 302

    usuario_objetivo.refresh_from_db()
    assert usuario_objetivo.nombre_completo == "Ana María Pérez"
    assert usuario_objetivo.area_habitual == "Tesorería"
    assert usuario_objetivo.legajo == "LEG-200"

    evento = CambioDatosCuentaLocal.objects.get(cuenta=usuario_objetivo)
    assert evento.autor_id == admin.user_id

    html_ficha = resp_post.content.decode()
    assert "Se guardaron los cambios en los datos de la cuenta." in html_ficha
    assert "Nombre completo:" in html_ficha
    assert "Área habitual:" in html_ficha
    assert "Legajo:" in html_ficha
    assert "Tesorería" in html_ficha


def test_autorizacion_rechaza_anonimo_solicitante_y_staff_superuser_sin_capacidad(
    solicitante, usuario_objetivo
):
    url = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])

    anon = Client()
    assert anon.get(url).status_code == 403
    assert anon.post(url, {}).status_code == 403

    cli_sol = Client()
    cli_sol.force_login(solicitante.user)
    assert cli_sol.get(url).status_code == 403
    assert cli_sol.post(url, {}).status_code == 403

    staff_super = _crear_cuenta(
        "Super Sin Cap",
        "super.sincap@example.invalid",
        is_staff=True,
        is_superuser=True,
    )
    cli_super = Client()
    cli_super.force_login(staff_super.user)
    assert cli_super.get(url).status_code == 403
    assert cli_super.post(url, {}).status_code == 403


def test_flag_local_apagada_responde_404(settings, admin_client, usuario_objetivo):
    settings.LOCAL_IDENTITY_ENABLED = False
    url = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    assert admin_client.get(url).status_code == 404
    assert admin_client.post(url, {}).status_code == 404


def test_cuenta_inexistente_responde_404(admin_client):
    url = reverse("cuentas:usuario_editar", args=[999999])
    assert admin_client.get(url).status_code == 404
    assert admin_client.post(url, {}).status_code == 404


def test_post_invalido_responde_400_y_conserva_datos(admin_client, usuario_objetivo):
    url = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    referencia = generar_referencia_edicion(usuario_objetivo)
    resp = admin_client.post(
        url,
        {
            "nombre_completo": "   ",
            "area_habitual": "Área Conservada",
            "cuit_cuil": "27-99999999-0",
            "legajo": "LEG-999",
            "referencia": referencia,
        },
    )
    assert resp.status_code == 400
    assert "no-store" in resp.headers.get("Cache-Control", "")
    html = resp.content.decode()
    assert "Área Conservada" in html
    assert "LEG-999" in html
    assert 'aria-invalid="true"' in html

    usuario_objetivo.refresh_from_db()
    assert usuario_objetivo.nombre_completo == "Ana Pérez"
    assert CambioDatosCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0


def test_post_noop_redirige_sin_crear_evento(admin_client, usuario_objetivo):
    url = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    referencia = generar_referencia_edicion(usuario_objetivo)
    resp = admin_client.post(
        url,
        {
            "nombre_completo": "Ana Pérez",
            "area_habitual": "Compras",
            "cuit_cuil": "27-12345678-9",
            "legajo": "LEG-100",
            "referencia": referencia,
        },
        follow=True,
    )
    assert resp.status_code == 200
    assert "Sin cambios." in resp.content.decode()
    assert CambioDatosCuentaLocal.objects.filter(cuenta=usuario_objetivo).count() == 0


def test_campos_protegidos_y_next_externo_ignorados(admin_client, usuario_objetivo):
    url = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    referencia = generar_referencia_edicion(usuario_objetivo)
    resp = admin_client.post(
        f"{url}?next=https://evil.example/phish",
        {
            "nombre_completo": "Ana Actualizada",
            "area_habitual": "Compras",
            "cuit_cuil": "27-12345678-9",
            "legajo": "LEG-100",
            "referencia": referencia,
            "email": "otro@example.invalid",
            "estado": CuentaLocal.Estado.RECHAZADA,
            "is_active": "false",
            "is_superuser": "true",
            "next": "https://evil.example/phish",
        },
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == reverse(
        "cuentas:usuario_detalle", args=[usuario_objetivo.pk]
    )

    usuario_objetivo.refresh_from_db()
    usuario_objetivo.user.refresh_from_db()
    assert usuario_objetivo.email == "ana.perez@example.invalid"
    assert usuario_objetivo.estado == CuentaLocal.Estado.APROBADA
    assert usuario_objetivo.user.is_active is True
    assert usuario_objetivo.user.is_superuser is False


def test_csrf_sin_token_responde_403(admin, usuario_objetivo):
    cli = Client(enforce_csrf_checks=True)
    cli.force_login(admin.user)
    url = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    referencia = generar_referencia_edicion(usuario_objetivo)
    resp = cli.post(
        url,
        {
            "nombre_completo": "Cambio Bloqueado",
            "area_habitual": "Compras",
            "cuit_cuil": "27-12345678-9",
            "legajo": "LEG-100",
            "referencia": referencia,
        },
    )
    assert resp.status_code == 403
    usuario_objetivo.refresh_from_db()
    assert usuario_objetivo.nombre_completo == "Ana Pérez"


def test_referencia_obsoleta_responde_409_no_escribe_y_conserva_referencia(
    admin_client, admin, usuario_objetivo
):
    url = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    referencia_vieja = _extraer_referencia(admin_client.get(url).content.decode())

    # Simular edición concurrente antes del POST
    CuentaLocal.objects.filter(pk=usuario_objetivo.pk).update(area_habitual="Modificada")

    resp = admin_client.post(
        url,
        {
            "nombre_completo": "Ana Intento",
            "area_habitual": "Compras",
            "cuit_cuil": "27-12345678-9",
            "legajo": "LEG-100",
            "referencia": referencia_vieja,
        },
    )
    assert resp.status_code == 409
    html = resp.content.decode()
    assert "cambiaron desde que abrió el formulario" in html
    assert "Recargar formulario" in html
    assert "Ana Intento" in html
    assert _extraer_referencia(html) == referencia_vieja

    usuario_objetivo.refresh_from_db()
    assert usuario_objetivo.nombre_completo == "Ana Pérez"
    assert usuario_objetivo.area_habitual == "Modificada"


def test_conserva_filtros_normalizados_en_retorno_y_paginacion_historial(
    admin_client, admin, usuario_objetivo
):
    # Crear 12 eventos para paginar de a 10
    for idx in range(1, 13):
        CambioDatosCuentaLocal.objects.create(
            cuenta=usuario_objetivo,
            autor=admin.user,
            cambios={
                "nombre_completo": {"anterior": f"Ana <{idx - 1}>", "nuevo": f"Ana <{idx}>"},
                "legajo": {"anterior": f"LEG-{idx - 1}", "nuevo": f"LEG-{idx}"},
            },
        )

    filtros = "q=compras&estado=APROBADA&page=2"
    base_editar = reverse("cuentas:usuario_editar", args=[usuario_objetivo.pk])
    url_editar = f"{base_editar}?{filtros}&ajeno=1"
    resp_get = admin_client.get(url_editar)
    assert resp_get.status_code == 200
    html_editar = resp_get.content.decode()
    detalle_url = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    assert f'href="{detalle_url}?q=compras&amp;estado=APROBADA&amp;page=2"' in html_editar
    assert "ajeno=1" not in html_editar

    resp_p1 = admin_client.get(f"{detalle_url}?{filtros}")
    assert resp_p1.status_code == 200
    html_p1 = resp_p1.content.decode()
    assert "Página 1 de 2" in html_p1
    assert "Ana &lt;12&gt;" in html_p1
    assert "LEG-12" in html_p1
    assert "historia_page=2" in html_p1
    assert "q=compras&amp;estado=APROBADA&amp;page=2&amp;historia_page=2" in html_p1

    resp_p2 = admin_client.get(f"{detalle_url}?{filtros}&historia_page=2")
    assert resp_p2.status_code == 200
    html_p2 = resp_p2.content.decode()
    assert "Página 2 de 2" in html_p2
    assert "LEG-2" in html_p2
    assert "LEG-1" in html_p2


def test_ficha_sin_cambios_muestra_estado_no_alarmista(admin_client, usuario_objetivo):
    url_detalle = reverse("cuentas:usuario_detalle", args=[usuario_objetivo.pk])
    resp = admin_client.get(url_detalle)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Editar datos" in html
    assert "Sin cambios registrados." in html
