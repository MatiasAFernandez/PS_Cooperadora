"""Pruebas HTTP para el alta administrativa y aceptación de invitaciones (SPEC-027)."""

import re
import urllib.parse
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from identidad.cuentas import registrar_cuenta
from identidad.invitaciones import crear_cuenta_invitada
from identidad.models import CuentaLocal, InvitacionCuentaLocal
from identidad.services import Actor

pytestmark = pytest.mark.django_db

CLAVE_ADMIN = "Clave-admin-sintetica-987!"
CLAVE_INVITADO = "Clave-invitado-sintetica-654!"


@pytest.fixture(autouse=True)
def configuracion_local(settings):
    """Bandera local activa con URL base canónica y correo en memoria."""
    settings.LOCAL_IDENTITY_ENABLED = True
    settings.DEMO_IDENTITY_ENABLED = False
    settings.LOCAL_PUBLIC_BASE_URL = "https://cooperadora.example.invalid"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox.clear()


@pytest.fixture
def grupo_administracion(db):
    return Group.objects.create(name="local_administracion")


@pytest.fixture
def grupo_solicitante(db):
    return Group.objects.create(name="local_solicitante")


def _crear_cuenta(
    nombre: str,
    email: str,
    *,
    grupos=(),
    is_staff: bool = False,
    is_superuser: bool = False,
) -> CuentaLocal:
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password=CLAVE_ADMIN,
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
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=timezone.now(),
        decidida_en=timezone.now(),
    )


def _actor(cuenta: CuentaLocal) -> Actor:
    return Actor(
        subject_id=cuenta.user_id,
        capabilities=frozenset({"identidad.administrar_cuentas"}),
    )


def _extraer_token_de_correo(body: str) -> str:
    match = re.search(r"/cuentas/invitacion/\?token=([^\s]+)", body)
    assert match is not None, f"No se encontró enlace de invitación en el correo: {body}"
    return urllib.parse.unquote(match.group(1))


def _extraer_csrf(html: str) -> str:
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
    assert match is not None, "No se encontró token CSRF en el HTML."
    return match.group(1)


@pytest.fixture
def admin(grupo_administracion):
    return _crear_cuenta(
        "Admin Invitaciones",
        "admin.invit@example.invalid",
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
        "Solicitante Sin Cap",
        "solicitante.invit@example.invalid",
        grupos=(grupo_solicitante,),
    )


def test_permisos_y_flag_deshabilitada(settings, admin, solicitante):
    url_nueva = reverse("cuentas:usuario_nuevo")
    cuenta_inv = crear_cuenta_invitada(
        _actor(admin),
        nombre="Persona Invitada",
        email="permisos.invit@example.invalid",
    )
    url_reenviar = reverse("cuentas:usuario_reenviar_invitacion", args=[cuenta_inv.pk])
    url_aceptar = reverse("cuentas:aceptar_invitacion")

    # Anónimo redirige o deniega en rutas administrativas
    anon = Client()
    assert anon.get(url_nueva).status_code in (302, 403)
    assert anon.post(url_nueva, {"nombre": "X", "email": "x@example.invalid"}).status_code in (
        302,
        403,
    )
    assert anon.post(url_reenviar).status_code in (302, 403)

    # Solicitante sin capacidad -> 403
    cli_sol = Client()
    cli_sol.force_login(solicitante.user)
    assert cli_sol.get(url_nueva).status_code == 403
    assert cli_sol.post(url_nueva, {"nombre": "X", "email": "x@example.invalid"}).status_code == 403
    assert cli_sol.post(url_reenviar).status_code == 403

    # Staff/superusuario sin capacidad -> 403
    staff = _crear_cuenta(
        "Staff Sin Cap",
        "staff.sincap@example.invalid",
        is_staff=True,
        is_superuser=True,
    )
    cli_staff = Client()
    cli_staff.force_login(staff.user)
    assert cli_staff.get(url_nueva).status_code == 403
    assert cli_staff.post(url_reenviar).status_code == 403

    # GET en reenvío administrativo -> 405
    cli_admin = Client()
    cli_admin.force_login(admin.user)
    assert cli_admin.get(url_reenviar).status_code == 405

    # Flag apagada -> 404
    settings.LOCAL_IDENTITY_ENABLED = False
    assert cli_admin.get(url_nueva).status_code == 404
    assert cli_admin.post(url_reenviar).status_code == 404
    assert anon.get(url_aceptar).status_code == 404
    assert anon.get(reverse("cuentas:invitacion_completa")).status_code == 404


def test_alta_administrativa_crea_cuenta_envia_correo_y_conserva_filtros(admin_client):
    url = f"{reverse('cuentas:usuario_nuevo')}?estado=PENDIENTE&verificado=no&page=2&ajeno=1"
    resp_get = admin_client.get(url)
    assert resp_get.status_code == 200
    assert "Crear y enviar invitación" in resp_get.content.decode("utf-8")

    resp_post = admin_client.post(
        url,
        {
            "nombre": "Lucía Gómez",
            "email": "Lucia.Gomez@Example.INVALID",
            "area_habitual": "Tesorería",
            "cuit_cuil": "27-30111222-3",
            "legajo": "LEG-404",
        },
    )
    assert resp_post.status_code == 302
    cuenta = CuentaLocal.objects.select_related("user", "invitacion_administrativa").get(
        email="lucia.gomez@example.invalid"
    )
    assert cuenta.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta.email_verificado_en is None
    assert cuenta.user.is_active is True
    assert not cuenta.user.has_usable_password()
    assert (
        cuenta.invitacion_administrativa.estado_envio == InvitacionCuentaLocal.EstadoEnvio.ENVIADA
    )

    destino_esperado = (
        f"{reverse('cuentas:usuario_detalle', args=[cuenta.pk])}"
        "?estado=PENDIENTE&verificado=no&page=2"
    )
    assert resp_post["Location"] == destino_esperado

    assert len(mail.outbox) == 1
    assert "https://cooperadora.example.invalid/cuentas/invitacion/?token=" in mail.outbox[0].body

    # Ficha muestra metadatos de invitación y botón de reenvío, nunca el token
    resp_ficha = admin_client.get(destino_esperado)
    html_ficha = resp_ficha.content.decode("utf-8")
    assert resp_ficha.status_code == 200
    assert "Alta administrativa por invitación" in html_ficha
    assert "Reenviar invitación" in html_ficha
    assert "?token=" not in html_ficha


def test_alta_duplicada_y_fallo_smtp_preserva_cuenta(monkeypatch, admin_client, solicitante):
    url = reverse("cuentas:usuario_nuevo")

    # Correo duplicado -> 400 conservando campos ingresados
    resp_dup = admin_client.post(
        url,
        {
            "nombre": "Nombre Conservado",
            "email": solicitante.email.upper(),
            "area_habitual": "Área Conservada",
            "cuit_cuil": "20-12345678-9",
            "legajo": "LEG-99",
        },
    )
    assert resp_dup.status_code == 400
    html_dup = resp_dup.content.decode("utf-8")
    assert "Nombre Conservado" in html_dup
    assert "Área Conservada" in html_dup
    assert "LEG-99" in html_dup
    assert len(mail.outbox) == 0

    # Fallo de SMTP -> cuenta persistida con estado ERROR y warning claro
    def _fallar_envio(*args, **kwargs):
        raise RuntimeError("SMTP caído")

    monkeypatch.setattr("identidad.invitaciones.send_mail", _fallar_envio)
    resp_smtp = admin_client.post(
        url,
        {
            "nombre": "Cuenta Sin SMTP",
            "email": "sin.smtp@example.invalid",
            "area_habitual": "Compras",
        },
        follow=True,
    )
    assert resp_smtp.status_code == 200
    cuenta = CuentaLocal.objects.select_related("invitacion_administrativa").get(
        email="sin.smtp@example.invalid"
    )
    assert cuenta.invitacion_administrativa.estado_envio == InvitacionCuentaLocal.EstadoEnvio.ERROR
    assert "pendiente para reenviar" in resp_smtp.content.decode("utf-8")


def test_reenvio_administrativo_respeta_cooldown(settings, admin, admin_client, monkeypatch):
    settings.LOCAL_VERIFY_RESEND_MIN_INTERVAL = 60
    admin_client.post(
        reverse("cuentas:usuario_nuevo"),
        {"nombre": "Usuario Cooldown", "email": "cooldown@example.invalid"},
    )
    cuenta = CuentaLocal.objects.get(email="cooldown@example.invalid")
    assert len(mail.outbox) == 1
    token_viejo = _extraer_token_de_correo(mail.outbox[0].body)

    url_reenviar = reverse("cuentas:usuario_reenviar_invitacion", args=[cuenta.pk])
    resp_cooldown = admin_client.post(url_reenviar, follow=True)
    assert resp_cooldown.status_code == 200
    assert len(mail.outbox) == 1
    assert "Aguardá unos segundos" in resp_cooldown.content.decode("utf-8")

    # Avanzar el reloj de la prueba también vence el límite persistido en base.
    ahora_avanzado = timezone.now() + timedelta(seconds=120)
    monkeypatch.setattr(timezone, "now", lambda: ahora_avanzado)

    resp_ok = admin_client.post(url_reenviar, follow=True)
    assert resp_ok.status_code == 200
    assert len(mail.outbox) == 2

    # El enlace anterior quedó invalidado
    anon = Client()
    assert (
        anon.get(f"{reverse('cuentas:aceptar_invitacion')}?token={token_viejo}").status_code == 400
    )


def test_aceptar_invitacion_get_no_consume_post_setpassword_csrf_y_replay(
    settings, admin_client, solicitante
):
    admin_client.post(
        reverse("cuentas:usuario_nuevo"),
        {"nombre": "Titular Invitado", "email": "titular.ok@example.invalid"},
    )
    token = _extraer_token_de_correo(mail.outbox[0].body)
    url_aceptar = reverse("cuentas:aceptar_invitacion")

    # GET no consume y aplica no-store + Referrer-Policy same-origin
    cli_csrf = Client(enforce_csrf_checks=True)
    resp_get = cli_csrf.get(f"{url_aceptar}?token={urllib.parse.quote(token)}")
    assert resp_get.status_code == 200
    assert "no-store" in resp_get["Cache-Control"]
    assert resp_get["Referrer-Policy"] == "same-origin"

    cuenta = CuentaLocal.objects.select_related("user", "invitacion_administrativa").get(
        email="titular.ok@example.invalid"
    )
    assert cuenta.email_verificado_en is None
    assert cuenta.invitacion_administrativa.aceptada_en is None
    assert not cuenta.user.has_usable_password()

    # POST con error de contraseña -> 400 sin repoblar clave
    csrf_token = _extraer_csrf(resp_get.content.decode("utf-8"))
    clave_mala = "clave-no-coincide-123"
    resp_err = cli_csrf.post(
        url_aceptar,
        {
            "csrfmiddlewaretoken": csrf_token,
            "token": token,
            "new_password1": clave_mala,
            "new_password2": "otra-clave-456",
        },
        HTTP_REFERER="http://testserver/cuentas/invitacion/",
    )
    assert resp_err.status_code == 400
    assert "no-store" in resp_err["Cache-Control"]
    assert resp_err["Referrer-Policy"] == "same-origin"
    assert clave_mala not in resp_err.content.decode("utf-8")

    # POST sin CSRF -> 403
    resp_nocsrf = cli_csrf.post(
        url_aceptar,
        {
            "token": token,
            "new_password1": CLAVE_INVITADO,
            "new_password2": CLAVE_INVITADO,
        },
        HTTP_REFERER="http://testserver/cuentas/invitacion/",
    )
    assert resp_nocsrf.status_code == 403

    # POST válido con CSRF y same-origin -> PRG a invitacion_completa, sin autologin
    csrf_token = _extraer_csrf(resp_err.content.decode("utf-8"))
    resp_ok = cli_csrf.post(
        url_aceptar,
        {
            "csrfmiddlewaretoken": csrf_token,
            "token": token,
            "new_password1": CLAVE_INVITADO,
            "new_password2": CLAVE_INVITADO,
        },
        HTTP_REFERER="http://testserver/cuentas/invitacion/",
    )
    assert resp_ok.status_code == 302
    assert resp_ok["Location"] == reverse("cuentas:invitacion_completa")
    assert "no-store" in resp_ok["Cache-Control"]
    assert resp_ok["Referrer-Policy"] == "same-origin"

    cuenta.refresh_from_db()
    cuenta.user.refresh_from_db()
    cuenta.invitacion_administrativa.refresh_from_db()
    assert cuenta.email_verificado_en is not None
    assert cuenta.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta.invitacion_administrativa.aceptada_en is not None
    assert cuenta.user.has_usable_password()
    assert cuenta.user.check_password(CLAVE_INVITADO)

    # Sin autologin: la sesión sigue anónima y la confirmación explica aprobación pendiente
    resp_comp = cli_csrf.get(reverse("cuentas:invitacion_completa"))
    assert resp_comp.status_code == 200
    assert "_auth_user_id" not in cli_csrf.session
    assert "pendiente de aprobación" in resp_comp.content.decode("utf-8")

    # Replay del token ya consumido -> 400
    assert cli_csrf.get(f"{url_aceptar}?token={urllib.parse.quote(token)}").status_code == 400
    assert (
        cli_csrf.post(
            url_aceptar,
            {
                "csrfmiddlewaretoken": csrf_token,
                "token": token,
                "new_password1": CLAVE_INVITADO,
                "new_password2": CLAVE_INVITADO,
            },
            HTTP_REFERER="http://testserver/cuentas/invitacion/",
        ).status_code
        == 400
    )


def test_token_vencido_y_sesion_ajena_preservada(settings, admin_client, solicitante):
    admin_client.post(
        reverse("cuentas:usuario_nuevo"),
        {"nombre": "Invitado Vencido", "email": "vencido@example.invalid"},
    )
    token = _extraer_token_de_correo(mail.outbox[0].body)
    url_aceptar = reverse("cuentas:aceptar_invitacion")

    # Enlace vencido con otra sesión: 400 neutro, sin mostrar la cuenta ni cambiar sesión.
    cli_otro = Client()
    cli_otro.force_login(solicitante.user)
    settings.LOCAL_VERIFICATION_TIMEOUT = -1
    resp_vencido = cli_otro.get(f"{url_aceptar}?token={urllib.parse.quote(token)}")
    assert resp_vencido.status_code == 400
    assert solicitante.email not in resp_vencido.content.decode("utf-8")
    assert int(cli_otro.session["_auth_user_id"]) == solicitante.user_id


def test_reenvio_publico_selecciona_enlace_correcto_sin_enumerar_y_sin_regresion(
    admin_client, monkeypatch
):
    # 1. Cuenta invitada pendiente sin clave -> ReenviarView envía enlace de invitación
    admin_client.post(
        reverse("cuentas:usuario_nuevo"),
        {"nombre": "Invitada Pública", "email": "publica.invit@example.invalid"},
    )
    mail.outbox.clear()
    ahora_avanzado = timezone.now() + timedelta(seconds=120)
    monkeypatch.setattr(timezone, "now", lambda: ahora_avanzado)

    anon = Client()
    resp_inv = anon.post(
        reverse("cuentas:reenviar"),
        {"email": "publica.invit@example.invalid"},
    )
    assert resp_inv.status_code == 302
    assert resp_inv["Location"] == reverse("cuentas:recibido")
    assert len(mail.outbox) == 1
    assert "/cuentas/invitacion/?token=" in mail.outbox[0].body

    # 2. Cuenta auto-registrada normal -> ReenviarView envía enlace de verificación normal
    mail.outbox.clear()
    cuenta_reg = registrar_cuenta(
        nombre="Registro Normal",
        email="registro.normal@example.invalid",
        password=CLAVE_INVITADO,
    )
    assert cuenta_reg is not None
    resp_reg = anon.post(
        reverse("cuentas:reenviar"),
        {"email": "registro.normal@example.invalid"},
    )
    assert resp_reg.status_code == 302
    assert resp_reg["Location"] == reverse("cuentas:recibido")
    assert len(mail.outbox) == 1
    assert "/cuentas/verificar/?token=" in mail.outbox[0].body

    # 3. Correo inexistente -> misma respuesta neutra sin enumerar ni 500
    mail.outbox.clear()
    resp_inex = anon.post(
        reverse("cuentas:reenviar"),
        {"email": "no.existe@example.invalid"},
    )
    assert resp_inex.status_code == 302
    assert resp_inex["Location"] == reverse("cuentas:recibido")
    assert len(mail.outbox) == 0

    # 4. Recuperación normal sigue accesible sin regresión
    resp_rec = anon.get(reverse("cuentas:recuperar"))
    assert resp_rec.status_code == 200
