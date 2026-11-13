"""Pruebas funcionales HTTP completas para el adaptador de acceso local (SPEC-022)."""

import re
import urllib.parse
from io import StringIO
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.mail.message import EmailMultiAlternatives
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from identidad.cuentas import (
    decidir_cuenta,
    enviar_verificacion,
    limitar,
    registrar_cuenta,
    token_verificacion,
    verificar_correo,
)
from identidad.models import CuentaLocal
from identidad.services import Actor, has_capability, resolve_actor


@pytest.fixture(autouse=True)
def configuracion_local(settings: Any) -> None:
    """Configuración predeterminada para pruebas de acceso local."""
    settings.LOCAL_IDENTITY_ENABLED = True
    settings.DEMO_IDENTITY_ENABLED = False
    settings.LOGIN_URL = "cuentas:login"
    settings.LOGIN_REDIRECT_URL = "cuentas:inicio"
    settings.LOCAL_PUBLIC_BASE_URL = "http://testserver"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def usuario_admin(db: Any) -> Any:
    """Usuario administrador de cuentas locales legítimo."""
    user_model = get_user_model()
    admin_user = user_model.objects.create_user(
        username="admin_http_runner",
        email="admin.http@example.invalid",
        password="Clave-segura-sintetica-admin-123!",
    )
    grupo, _ = Group.objects.get_or_create(name="local_administracion")
    admin_user.groups.add(grupo)

    now = timezone.now()
    CuentaLocal.objects.create(
        user=admin_user,
        email="admin.http@example.invalid",
        nombre_completo="Admin Local",
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=now,
        decidida_en=now,
        motivo="Bootstrap admin test",
    )
    return admin_user


@pytest.fixture
def admin_client(usuario_admin: Any) -> Client:
    """Cliente HTTP con sesión forzada del administrador."""
    c = Client()
    c.force_login(usuario_admin)
    return c


@pytest.fixture
def actor_admin(admin_client: Client) -> Actor:
    """Actor administrador resuelto legítimamente desde una sesión HTTP."""
    resp = admin_client.get(reverse("cuentas:altas"))
    actor = resolve_actor(resp.wsgi_request)
    assert actor is not None
    return actor


@pytest.fixture
def cuenta_solicitante(db: Any) -> CuentaLocal:
    """Cuenta local registrada y verificada lista para evaluación."""
    cuenta = registrar_cuenta(
        nombre="Solicitante HTTP",
        email="solicitante.http@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
        area_habitual="Compras",
        cuit_cuil="20-33445566-9",
        legajo="LEG-9988",
    )
    assert cuenta is not None
    token = token_verificacion(cuenta)
    return verificar_correo(token)


@pytest.mark.django_db
def test_1_registro_http_exitoso_y_duplicados_neutros(client: Client) -> None:
    """El registro crea la cuenta pendiente, envía email y no realiza auto-login."""
    mail.outbox.clear()
    resp = client.post(
        reverse("cuentas:registro"),
        {
            "nombre": "Nuevo Solicitante",
            "email": "nuevo.solicitante@example.invalid",
            "password1": "Clave-segura-sintetica-valida-123!",
            "password2": "Clave-segura-sintetica-valida-123!",
            "area_habitual": "",
            "cuit_cuil": "",
            "legajo": "",
        },
    )
    assert resp.status_code == 302
    assert resp.url == reverse("cuentas:recibido")

    # Sin auto-login
    assert "_auth_user_id" not in client.session

    # Cuenta creada en pendiente y email enviado
    cuenta = CuentaLocal.objects.get(email="nuevo.solicitante@example.invalid")
    assert cuenta.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta.user.groups.count() == 0
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["nuevo.solicitante@example.invalid"]

    # Duplicado local: misma respuesta sin crear usuarios extra
    user_count_before = get_user_model().objects.count()
    resp_dup = client.post(
        reverse("cuentas:registro"),
        {
            "nombre": "Intento Duplicado",
            "email": "nuevo.solicitante@example.invalid",
            "password1": "Clave-segura-sintetica-valida-123!",
            "password2": "Clave-segura-sintetica-valida-123!",
        },
    )
    assert resp_dup.status_code == 302
    assert resp_dup.url == reverse("cuentas:recibido")
    assert get_user_model().objects.count() == user_count_before

    # Contraseñas dispares conservan datos no sensibles y arrojan 400
    resp_bad = client.post(
        reverse("cuentas:registro"),
        {
            "nombre": "Nombre Mantenido",
            "email": "mantenido@example.invalid",
            "password1": "Clave-segura-sintetica-valida-123!",
            "password2": "Clave-Diferente-No-Coincide-999!",
        },
    )
    assert resp_bad.status_code == 400
    assert "Nombre Mantenido" in resp_bad.content.decode()


@pytest.mark.django_db
def test_2_verificar_correo_flujo_tokens_y_seguridad() -> None:
    """GET no consume token; POST verifica casilla sin aprobar y rechaza replays."""
    cuenta = registrar_cuenta(
        nombre="Verif User",
        email="verif.test@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    assert cuenta is not None
    mail.outbox.clear()
    enviar_verificacion(cuenta, base_url="http://testserver")
    assert len(mail.outbox) == 1

    # Extraer enlace y token del correo sin imprimirlo
    match = re.search(r"(http://[^\s\n]+)", mail.outbox[0].body)
    assert match is not None
    enlace = match.group(1)
    parsed = urllib.parse.urlsplit(enlace)
    params = urllib.parse.parse_qs(parsed.query)
    assert "token" in params
    token = params["token"][0]

    csrf_client = Client(enforce_csrf_checks=True)

    # GET prepara formulario sin consumir token. La política same-origin
    # conserva el referente interno para CSRF sin filtrarlo a otros orígenes.
    resp_get = csrf_client.get(reverse("cuentas:verificar"), {"token": token})
    assert resp_get.status_code == 200
    assert resp_get.headers["Referrer-Policy"] == "same-origin"
    assert "no-store" in resp_get.headers["Cache-Control"]
    contenido_form = resp_get.content.decode()
    # No exponer token visible como texto plano en el cuerpo
    assert f">{token}<" not in contenido_form

    match_csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', contenido_form)
    assert match_csrf is not None
    csrf_form_token = match_csrf.group(1)

    cuenta.refresh_from_db()
    assert cuenta.email_verificado_en is None

    # POST cross-origin con CSRF válido: 403 y token de verificación intacto
    resp_cross = csrf_client.post(
        reverse("cuentas:verificar"),
        {"token": token, "csrfmiddlewaretoken": csrf_form_token},
        HTTP_ORIGIN="https://origen.example.invalid",
    )
    assert resp_cross.status_code == 403
    cuenta.refresh_from_db()
    assert cuenta.email_verificado_en is None

    # POST sin token CSRF: 403 y token de verificación intacto
    resp_sin_csrf = csrf_client.post(
        reverse("cuentas:verificar"),
        {"token": token},
        HTTP_ORIGIN="http://testserver",
    )
    assert resp_sin_csrf.status_code == 403
    cuenta.refresh_from_db()
    assert cuenta.email_verificado_en is None

    # POST same-origin con CSRF válido consume el token y verifica sin aprobar
    resp_post = csrf_client.post(
        reverse("cuentas:verificar"),
        {"token": token, "csrfmiddlewaretoken": csrf_form_token},
        HTTP_ORIGIN="http://testserver",
    )
    assert resp_post.status_code == 302
    assert resp_post.url == f"{reverse('cuentas:estado')}?modo=verificado"

    cuenta.refresh_from_db()
    assert cuenta.email_verificado_en is not None
    assert cuenta.estado == CuentaLocal.Estado.PENDIENTE

    # Replay genera 400 aun con CSRF válido
    resp_replay = csrf_client.post(
        reverse("cuentas:verificar"),
        {"token": token, "csrfmiddlewaretoken": csrf_form_token},
        HTTP_ORIGIN="http://testserver",
    )
    assert resp_replay.status_code == 400

    # Token inválido genera 400
    resp_inv = csrf_client.post(
        reverse("cuentas:verificar"),
        {"token": "firma-corrupta", "csrfmiddlewaretoken": csrf_form_token},
        HTTP_ORIGIN="http://testserver",
    )
    assert resp_inv.status_code == 400


@pytest.mark.django_db
def test_3_login_pendiente_aprobacion_admin_y_aislamiento_capacidades(
    admin_client: Client, cuenta_solicitante: CuentaLocal
) -> None:
    """Login pendiente redirige a estado; aprobación por admin otorga perfil de solicitante."""
    solicitante_client = Client()
    login_resp = solicitante_client.post(
        reverse("cuentas:login"),
        {
            "username": cuenta_solicitante.email,
            "password": "Clave-segura-sintetica-valida-123!",
        },
    )
    # Pendiente va forzosamente a estado
    assert login_resp.status_code == 302
    assert login_resp.url == reverse("cuentas:estado")

    # Sesión no operativa frente a resolver_actor
    req_simulado = MagicMock()
    req_simulado.session = solicitante_client.session
    req_simulado.user = cuenta_solicitante.user
    assert resolve_actor(req_simulado) is None

    # Solicitante no puede acceder a bandeja de altas (403)
    resp_altas_denegada = solicitante_client.get(reverse("cuentas:altas"))
    assert resp_altas_denegada.status_code == 403

    # Admin aprueba desde POST altas
    resp_aprobar = admin_client.post(
        reverse("cuentas:altas"),
        {
            "cuenta_id": cuenta_solicitante.pk,
            "accion": "APROBAR",
            "motivo": "",
        },
    )
    assert resp_aprobar.status_code == 302
    assert resp_aprobar.url == reverse("cuentas:altas")

    cuenta_solicitante.refresh_from_db()
    assert cuenta_solicitante.estado == CuentaLocal.Estado.APROBADA

    # Misma sesión ahora resuelve Actor operativo
    actor = resolve_actor(req_simulado)
    assert actor is not None
    assert actor.subject_id == cuenta_solicitante.user.pk
    assert has_capability(actor, "gastos.presentar") is True
    assert has_capability(actor, "facturacion.presentar") is True

    # No tiene permisos de pagos ni configuración general
    assert has_capability(actor, "gastos.registrar_pago") is False
    assert has_capability(actor, "gestion.configurar") is False
    assert has_capability(actor, "identidad.administrar_cuentas") is False

    # Doble decisión genera conflicto (400)
    resp_conflicto = admin_client.post(
        reverse("cuentas:altas"),
        {
            "cuenta_id": cuenta_solicitante.pk,
            "accion": "APROBAR",
            "motivo": "",
        },
    )
    assert resp_conflicto.status_code == 400


@pytest.mark.django_db
def test_4_csrf_y_gating_cuando_local_identity_disabled(settings: Any) -> None:
    """CSRF rechaza POST sin token y flag desactivado devuelve 404 en rutas locales."""
    csrf_client = Client(enforce_csrf_checks=True)

    # POST sin token es rechazado
    assert csrf_client.post(reverse("cuentas:registro"), {}).status_code == 403
    assert csrf_client.post(reverse("cuentas:altas"), {}).status_code == 403
    assert csrf_client.post(reverse("cuentas:logout"), {}).status_code == 403

    # Flag desactivado
    settings.LOCAL_IDENTITY_ENABLED = False
    normal_client = Client()
    assert normal_client.get(reverse("cuentas:login")).status_code == 404
    assert normal_client.get(reverse("cuentas:registro")).status_code == 404
    assert normal_client.get(reverse("cuentas:cambiar_clave")).status_code == 404


@pytest.mark.django_db
def test_5_login_errores_neutros_y_prevencion_open_redirect(
    client: Client, cuenta_solicitante: CuentaLocal, actor_admin: Actor
) -> None:
    """Credenciales incorrectas dan error neutro y next externo es saneado."""
    # Desconocido
    resp_desc = client.post(
        reverse("cuentas:login"),
        {"username": "inexistente@example.invalid", "password": "password-fake-123"},
    )
    assert resp_desc.status_code == 200
    assert "_auth_user_id" not in client.session

    # Inactiva
    cuenta_solicitante.user.is_active = False
    cuenta_solicitante.user.save()
    resp_inac = client.post(
        reverse("cuentas:login"),
        {
            "username": cuenta_solicitante.email,
            "password": "Clave-segura-sintetica-valida-123!",
        },
    )
    assert resp_inac.status_code == 200
    assert "_auth_user_id" not in client.session

    # Reactivar usuario antes de aprobar para cumplir validación del núcleo
    cuenta_solicitante.user.is_active = True
    cuenta_solicitante.user.save()

    # Open redirect en usuario aprobado es neutralizado
    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_solicitante.pk, aprobar=True)

    resp_redirect = client.post(
        f"{reverse('cuentas:login')}?next=https://malicious.example.invalid/steal",
        {
            "username": cuenta_solicitante.email,
            "password": "Clave-segura-sintetica-valida-123!",
        },
    )
    assert resp_redirect.status_code == 302
    # No redirige al dominio externo
    assert not resp_redirect.url.startswith("https://malicious.example.invalid")
    assert resp_redirect.url == reverse("cuentas:inicio")


@pytest.mark.django_db
def test_6_recuperacion_contrasena_flujo_completo(
    client: Client, cuenta_solicitante: CuentaLocal, actor_admin: Actor, settings: Any
) -> None:
    """Recuperación genera enlace seguro con host configurado y cambia clave sin auto-login."""
    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_solicitante.pk, aprobar=True)
    mail.outbox.clear()

    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["otro-host-desconocido.com"]
    # POST recuperar
    resp_rec = client.post(
        reverse("cuentas:recuperar"),
        {"email": cuenta_solicitante.email},
        HTTP_HOST="otro-host-desconocido.com",
    )
    assert resp_rec.status_code == 302
    assert resp_rec.url == reverse("cuentas:recuperar_enviado")
    assert len(mail.outbox) == 1

    cuerpo = mail.outbox[0].body
    # Host proviene de LOCAL_PUBLIC_BASE_URL (testserver) y no de cabecera request
    assert "http://testserver/cuentas/recuperar/" in cuerpo

    match = re.search(r"/cuentas/recuperar/([A-Za-z0-9_\-]+)/([A-Za-z0-9_\-]+)/", cuerpo)
    assert match is not None
    uidb64, token = match.group(1), match.group(2)

    # GET link genera 302 estándar de Django hacia set-password
    resp_link = client.get(
        reverse("cuentas:reset_confirm", kwargs={"uidb64": uidb64, "token": token})
    )
    assert resp_link.status_code == 302

    # Seguir hacia set-password da 200
    resp_form = client.get(resp_link.url)
    assert resp_form.status_code == 200

    # POST nueva contraseña
    resp_change = client.post(
        resp_link.url,
        {
            "new_password1": "Nueva-clave-sintetica-valida-789!",
            "new_password2": "Nueva-clave-sintetica-valida-789!",
        },
    )
    assert resp_change.status_code == 302
    assert resp_change.url == reverse("cuentas:reset_completo")

    # Sin auto-login y contraseña efectivamente cambiada
    assert "_auth_user_id" not in client.session
    cuenta_solicitante.user.refresh_from_db()
    assert cuenta_solicitante.user.check_password("Nueva-clave-sintetica-valida-789!")

    # Cuentas pendientes no reciben email de recuperación
    mail.outbox.clear()
    cuenta_pend = registrar_cuenta(
        nombre="Pendiente Rec",
        email="pend.rec@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    assert cuenta_pend is not None
    client.post(reverse("cuentas:recuperar"), {"email": cuenta_pend.email})
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_7_fallo_smtp_recuperacion_no_da_500(
    client: Client, cuenta_solicitante: CuentaLocal, actor_admin: Actor, monkeypatch: Any
) -> None:
    """Fallo en envío de correo de recuperación responde confirmación condicional sin 500."""
    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_solicitante.pk, aprobar=True)

    monkeypatch.setattr(
        EmailMultiAlternatives,
        "send",
        MagicMock(side_effect=OSError("Fallo de socket SMTP")),
    )
    resp = client.post(
        reverse("cuentas:recuperar"),
        {"email": cuenta_solicitante.email},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("cuentas:recuperar_enviado")

    # Confirmación condicional visible
    resp_conf = client.get(resp.url)
    assert resp_conf.status_code == 200
    assert "Revisá tu correo" in resp_conf.content.decode()


@pytest.mark.django_db
def test_8_cambio_de_clave_autenticado_mantiene_sesion_actual(
    cuenta_solicitante: CuentaLocal, actor_admin: Actor
) -> None:
    """El cambio voluntario exige contraseña actual, actualiza hash y mantiene sesión activa."""
    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_solicitante.pk, aprobar=True)
    c = Client()
    c.force_login(cuenta_solicitante.user)

    # Error con clave actual incorrecta
    resp_err = c.post(
        reverse("cuentas:cambiar_clave"),
        {
            "old_password": "clave-vieja-incorrecta",
            "new_password1": "Nueva-clave-sintetica-valida-888!",
            "new_password2": "Nueva-clave-sintetica-valida-888!",
        },
    )
    assert resp_err.status_code == 200

    # Cambio exitoso
    resp_ok = c.post(
        reverse("cuentas:cambiar_clave"),
        {
            "old_password": "Clave-segura-sintetica-valida-123!",
            "new_password1": "Nueva-clave-sintetica-valida-888!",
            "new_password2": "Nueva-clave-sintetica-valida-888!",
        },
    )
    assert resp_ok.status_code == 302
    assert resp_ok.url == reverse("cuentas:clave_cambiada")

    # La sesión actual se preserva mediante update_session_auth_hash
    assert c.get(reverse("cuentas:inicio")).status_code == 200


@pytest.mark.django_db
def test_9_rate_limiting_en_vistas_bloquea_excesos(client: Client) -> None:
    """Agotar la tasa permitida en el modelo LimiteAcceso rechaza intentos posteriores."""
    ip = "127.0.0.1"
    # Agotar intencionalmente los 10 intentos de registro para la IP
    for _ in range(10):
        limitar(f"registro-ip:{ip}", maximo=10, segundos=300)

    resp = client.post(
        reverse("cuentas:registro"),
        {
            "nombre": "Rate Limited",
            "email": "ratelimit@example.invalid",
            "password1": "Clave-segura-sintetica-valida-123!",
            "password2": "Clave-segura-sintetica-valida-123!",
        },
    )
    assert resp.status_code == 400
    assert not CuentaLocal.objects.filter(email="ratelimit@example.invalid").exists()


@pytest.mark.django_db
def test_10_comando_preparar_cuenta_local_garantias_y_rechazos() -> None:
    """preparar_cuenta_local exige comprobación, es idempotente y no salta el circuito."""
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="operador_tecnico",
        email="operador.tecnico@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )

    out = StringIO()

    # Falta flag obligatorio
    with pytest.raises(CommandError, match="--correo-verificado"):
        call_command("preparar_cuenta_local", username="operador_tecnico", stdout=out)

    # Ejecución correcta con flag
    call_command(
        "preparar_cuenta_local",
        username="operador_tecnico",
        correo_verificado=True,
        administrador=True,
        stdout=out,
    )
    assert "preparada exitosamente" in out.getvalue()

    cuenta = CuentaLocal.objects.get(user=user)
    assert cuenta.estado == CuentaLocal.Estado.APROBADA
    assert cuenta.email_verificado_en is not None
    assert user.groups.filter(name="local_solicitante").exists()
    assert user.groups.filter(name="local_administracion").exists()

    # Idempotencia: segunda ejecución preserva estado
    call_command(
        "preparar_cuenta_local",
        username="operador_tecnico",
        correo_verificado=True,
        stdout=out,
    )
    assert cuenta.estado == CuentaLocal.Estado.APROBADA

    # Cuenta existente pendiente genera CommandError (no bypass de circuito)
    user_pend = user_model.objects.create_user(
        username="usuario_pendiente_previo",
        email="pendiente.previo@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    CuentaLocal.objects.create(
        user=user_pend,
        email="pendiente.previo@example.invalid",
        nombre_completo="Pendiente Previo",
        estado=CuentaLocal.Estado.PENDIENTE,
    )
    with pytest.raises(CommandError, match="bandeja administrativa"):
        call_command(
            "preparar_cuenta_local",
            username="usuario_pendiente_previo",
            correo_verificado=True,
            stdout=out,
        )


@pytest.mark.django_db
def test_11_revocacion_tokens_tras_suspension_y_reactivacion(
    client: Client, cuenta_solicitante: CuentaLocal, actor_admin: Actor
) -> None:
    """La suspensión y reactivación del usuario revoca tokens de recuperación y verificación."""
    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_solicitante.pk, aprobar=True)
    cuenta_solicitante.refresh_from_db()
    user = cuenta_solicitante.user
    nonce_original = cuenta_solicitante.nonce_verificacion

    # 1. Guardar sin cambiar is_active: el nonce NO debe rotar
    user.save(update_fields=["is_active"])
    cuenta_solicitante.refresh_from_db()
    assert cuenta_solicitante.nonce_verificacion == nonce_original

    # 2. Solicitar recuperación de contraseña para la cuenta aprobada
    mail.outbox.clear()
    resp_rec = client.post(reverse("cuentas:recuperar"), {"email": cuenta_solicitante.email})
    assert resp_rec.status_code == 302
    assert len(mail.outbox) == 1

    cuerpo = mail.outbox[0].body
    match = re.search(r"/cuentas/recuperar/([A-Za-z0-9_\-]+)/([A-Za-z0-9_\-]+)/", cuerpo)
    assert match is not None
    uidb64, token_viejo = match.group(1), match.group(2)

    # 3. Suspender y reactivar el usuario modificando is_active
    user.is_active = False
    user.save(update_fields=["is_active"])
    cuenta_solicitante.refresh_from_db()
    assert cuenta_solicitante.nonce_verificacion != nonce_original
    nonce_intermedio = cuenta_solicitante.nonce_verificacion

    user.is_active = True
    user.save(update_fields=["is_active"])
    cuenta_solicitante.refresh_from_db()
    assert cuenta_solicitante.nonce_verificacion != nonce_intermedio

    # 4. GET enlace viejo debe responder 400 (token invalidado permanentemente)
    resp_viejo = client.get(
        reverse("cuentas:reset_confirm", kwargs={"uidb64": uidb64, "token": token_viejo})
    )
    assert resp_viejo.status_code == 400
    assert resp_viejo.headers.get("Referrer-Policy") == "no-referrer"

    # 5. Nuevo enlace posterior sí genera 302 hacia set-password
    mail.outbox.clear()
    resp_rec2 = client.post(reverse("cuentas:recuperar"), {"email": cuenta_solicitante.email})
    assert resp_rec2.status_code == 302
    assert len(mail.outbox) == 1

    match2 = re.search(
        r"/cuentas/recuperar/([A-Za-z0-9_\-]+)/([A-Za-z0-9_\-]+)/", mail.outbox[0].body
    )
    assert match2 is not None
    uidb64_2, token_nuevo = match2.group(1), match2.group(2)

    resp_nuevo = client.get(
        reverse("cuentas:reset_confirm", kwargs={"uidb64": uidb64_2, "token": token_nuevo})
    )
    assert resp_nuevo.status_code == 302

    # 6. Verificación previa de cuenta NO verificada queda inválida tras suspensión/reactivación
    cuenta_nueva = registrar_cuenta(
        nombre="Verif Suspendida",
        email="verif.suspendida@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    assert cuenta_nueva is not None
    token_verif_previo = token_verificacion(cuenta_nueva)

    # Suspender y reactivar usuario de la cuenta no verificada
    user_nueva = cuenta_nueva.user
    user_nueva.is_active = False
    user_nueva.save(update_fields=["is_active"])
    user_nueva.is_active = True
    user_nueva.save(update_fields=["is_active"])

    # El token previo debe ser rechazado con 400
    resp_verif = client.post(reverse("cuentas:verificar"), {"token": token_verif_previo})
    assert resp_verif.status_code == 400
    cuenta_nueva.refresh_from_db()
    assert cuenta_nueva.email_verificado_en is None
