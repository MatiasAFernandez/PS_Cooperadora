"""Pruebas funcionales de backend para alta administrativa mediante invitación (SPEC-027)."""

import re
import secrets
import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.utils import timezone

from identidad.cuentas import enviar_verificacion, verificar_correo
from identidad.invitaciones import (
    aceptar_invitacion,
    crear_cuenta_invitada,
    enviar_invitacion,
    validar_invitacion,
)
from identidad.models import CuentaLocal, InvitacionCuentaLocal
from identidad.services import Actor


def _crear_admin_local(
    *,
    username: str = "admin_invit",
    email: str = "admin.invit@example.invalid",
    is_active: bool = True,
    estado: str = CuentaLocal.Estado.APROBADA,
    verificada: bool = True,
    grupos: tuple[str, ...] = ("local_administracion",),
    is_staff: bool = False,
    is_superuser: bool = False,
    con_cuenta: bool = True,
) -> tuple[Any, Actor]:
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=username,
        email=email,
        password=secrets.token_urlsafe(16),
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    for nombre_grupo in grupos:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)

    if con_cuenta:
        CuentaLocal.objects.create(
            user=user,
            email=email,
            nombre_completo=f"Admin {username}",
            estado=estado,
            email_verificado_en=timezone.now() if verificada else None,
        )

    actor = Actor(
        subject_id=user.pk,
        capabilities=frozenset({"identidad.administrar_cuentas"}),
        email_registrado=user.email,
    )
    return user, actor


def _extraer_token_de_correo(body: str) -> str:
    match = re.search(r"https?://[^\s]+/cuentas/invitacion/\?token=([^\s]+)", body)
    assert match is not None, "No se encontró el enlace de invitación en el correo."
    parsed = urlsplit(match.group(0))
    tokens = parse_qs(parsed.query).get("token")
    assert tokens and len(tokens) == 1
    return tokens[0]


@pytest.mark.django_db
def test_crear_cuenta_invitada_exige_capacidad_antes_de_consultar(
    django_assert_num_queries: Any,
) -> None:
    actor_sin_permiso = Actor(
        subject_id=999,
        capabilities=frozenset({"gastos.presentar"}),
        email_registrado="sinpermiso@example.invalid",
    )

    with django_assert_num_queries(0):
        with pytest.raises(PermissionDenied):
            crear_cuenta_invitada(
                None,
                "Persona Invitada",
                "invitada.sinperm@example.invalid",
            )

    with django_assert_num_queries(0):
        with pytest.raises(PermissionDenied):
            crear_cuenta_invitada(
                actor_sin_permiso,
                "Persona Invitada",
                "invitada.sinperm@example.invalid",
            )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kwargs_actor",
    [
        {"is_active": False},
        {"estado": CuentaLocal.Estado.PENDIENTE},
        {"estado": CuentaLocal.Estado.RECHAZADA},
        {"verificada": False},
        {"grupos": ("local_solicitante",)},
        {"grupos": (), "is_staff": True, "is_superuser": True},
        {"con_cuenta": False, "is_staff": True, "is_superuser": True},
    ],
)
def test_crear_cuenta_invitada_revalida_actor_revocado(kwargs_actor: dict[str, Any]) -> None:
    _, actor = _crear_admin_local(
        username=f"actor_rev_{uuid.uuid4().hex[:6]}",
        email=f"actor_{uuid.uuid4().hex[:6]}@example.invalid",
        **kwargs_actor,
    )

    with pytest.raises(PermissionDenied):
        crear_cuenta_invitada(
            actor,
            "Persona Bloqueada",
            "bloqueada@example.invalid",
        )

    assert not CuentaLocal.objects.filter(email="bloqueada@example.invalid").exists()
    assert not get_user_model().objects.filter(email="bloqueada@example.invalid").exists()


@pytest.mark.django_db
def test_crear_cuenta_invitada_alta_atomica_sin_envio_ni_privilegios(mailoutbox: list[Any]) -> None:
    admin_user, actor = _crear_admin_local()

    cuenta = crear_cuenta_invitada(
        actor,
        "  Ana Pérez  ",
        "  Ana.Perez@Example.Invalid ",
        "Tesorería",
        "27-30111222-3",
        "LEG-123",
    )

    cuenta.refresh_from_db()
    invitacion = cuenta.invitacion_administrativa
    user = cuenta.user

    assert len(mailoutbox) == 0
    assert cuenta.email == "ana.perez@example.invalid"
    assert cuenta.nombre_completo == "Ana Pérez"
    assert cuenta.area_habitual == "Tesorería"
    assert cuenta.cuit_cuil == "27-30111222-3"
    assert cuenta.legajo == "LEG-123"
    assert cuenta.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta.email_verificado_en is None
    assert cuenta.ultimo_envio is None

    assert user.is_active is True
    assert user.has_usable_password() is False
    assert user.is_staff is False
    assert user.is_superuser is False
    assert list(user.groups.all()) == []

    assert invitacion.creada_por_id == admin_user.pk
    assert invitacion.aceptada_en is None
    assert invitacion.ultimo_intento_en is None
    assert invitacion.estado_envio == InvitacionCuentaLocal.EstadoEnvio.PENDIENTE


@pytest.mark.django_db
def test_crear_cuenta_invitada_rechaza_duplicados_legados_y_casefold_sin_huerfanos() -> None:
    _, actor = _crear_admin_local()
    user_model = get_user_model()

    # Usuario legado sin CuentaLocal
    clave_legada = secrets.token_urlsafe(16)
    legado = user_model.objects.create_user(
        username="legado_demo",
        email="Legado.Existente@Example.Invalid",
        password=clave_legada,
    )

    # CuentaLocal existente
    crear_cuenta_invitada(actor, "Original", "ocupada@example.invalid")

    users_antes = user_model.objects.count()
    cuentas_antes = CuentaLocal.objects.count()
    invitaciones_antes = InvitacionCuentaLocal.objects.count()

    with pytest.raises(ValidationError):
        crear_cuenta_invitada(actor, "Dup Legado", "legado.existente@example.invalid")

    with pytest.raises(ValidationError):
        crear_cuenta_invitada(actor, "Dup Cuenta", "  OCUPADA@example.invalid ")

    assert user_model.objects.count() == users_antes
    assert CuentaLocal.objects.count() == cuentas_antes
    assert InvitacionCuentaLocal.objects.count() == invitaciones_antes

    legado.refresh_from_db()
    assert legado.check_password(clave_legada) is True
    assert not hasattr(legado, "cuenta_local")


@pytest.mark.django_db
def test_crear_cuenta_invitada_rollback_si_falla_persistencia(monkeypatch: Any) -> None:
    _, actor = _crear_admin_local()
    user_model = get_user_model()
    users_antes = user_model.objects.count()
    cuentas_antes = CuentaLocal.objects.count()

    def fallar_create(*args: Any, **kwargs: Any) -> Any:
        raise IntegrityError("Fallo simulado de persistencia")

    monkeypatch.setattr(InvitacionCuentaLocal.objects, "create", fallar_create)

    with pytest.raises(ValidationError):
        crear_cuenta_invitada(actor, "Rollback Test", "rollback@example.invalid")

    assert user_model.objects.count() == users_antes
    assert CuentaLocal.objects.count() == cuentas_antes
    assert not user_model.objects.filter(email="rollback@example.invalid").exists()


@pytest.mark.django_db
def test_enviar_invitacion_exito_smtp_y_url_canonica(mailoutbox: list[Any], caplog: Any) -> None:
    _, actor = _crear_admin_local()
    cuenta = crear_cuenta_invitada(actor, "Lucía Gómez", "lucia@example.invalid")

    assert enviar_invitacion(cuenta, "ftp://invalido.example.invalid") is False
    assert enviar_invitacion(cuenta, "https://invalido.example.invalid/ruta") is False
    assert len(mailoutbox) == 0

    ok = enviar_invitacion(cuenta, "https://cooperadora.example.invalid")
    assert ok is True
    assert len(mailoutbox) == 1

    correo = mailoutbox[0]
    assert correo.to == ["lucia@example.invalid"]
    token = _extraer_token_de_correo(correo.body)
    assert "https://cooperadora.example.invalid/cuentas/invitacion/?token=" in correo.body

    cuenta.refresh_from_db()
    invitacion = cuenta.invitacion_administrativa
    assert invitacion.estado_envio == InvitacionCuentaLocal.EstadoEnvio.ENVIADA
    assert invitacion.ultimo_intento_en is not None
    assert cuenta.ultimo_envio is not None
    assert token not in caplog.text


@pytest.mark.django_db
def test_enviar_invitacion_fallo_smtp_conserva_cuenta_y_marca_error(
    monkeypatch: Any, mailoutbox: list[Any], caplog: Any
) -> None:
    _, actor = _crear_admin_local()
    cuenta = crear_cuenta_invitada(actor, "Carlos Ruiz", "carlos@example.invalid")

    def fallar_smtp(*args: Any, **kwargs: Any) -> int:
        raise OSError("SMTP secreto interno caido")

    monkeypatch.setattr("identidad.invitaciones.send_mail", fallar_smtp)

    ok = enviar_invitacion(cuenta, "http://127.0.0.1:8000")
    assert ok is False
    assert len(mailoutbox) == 0

    cuenta.refresh_from_db()
    invitacion = cuenta.invitacion_administrativa
    assert CuentaLocal.objects.filter(pk=cuenta.pk).exists()
    assert invitacion.estado_envio == InvitacionCuentaLocal.EstadoEnvio.ERROR
    assert invitacion.ultimo_intento_en is not None
    assert cuenta.ultimo_envio is None
    assert "SMTP secreto interno caido" not in caplog.text


@pytest.mark.django_db
def test_reenvio_invalida_token_anterior_y_aplica_rate_limit(
    settings: Any, mailoutbox: list[Any]
) -> None:
    _, actor = _crear_admin_local()
    cuenta = crear_cuenta_invitada(actor, "Marta Díaz", "marta@example.invalid")

    settings.LOCAL_VERIFY_RESEND_MIN_INTERVAL = 60
    assert enviar_invitacion(cuenta, "http://127.0.0.1:8000") is True
    token_1 = _extraer_token_de_correo(mailoutbox[0].body)

    # Reenvío inmediato bloqueado por rate limit
    assert enviar_invitacion(cuenta, "http://127.0.0.1:8000") is False
    assert len(mailoutbox) == 1

    # Al habilitar reenvío, rota el nonce e invalida el token previo
    settings.LOCAL_VERIFY_RESEND_MIN_INTERVAL = 0
    assert enviar_invitacion(cuenta, "http://127.0.0.1:8000") is True
    assert len(mailoutbox) == 2
    token_2 = _extraer_token_de_correo(mailoutbox[1].body)
    assert token_2 != token_1

    with pytest.raises(ValidationError):
        validar_invitacion(token_1)

    assert validar_invitacion(token_2).pk == cuenta.pk


@pytest.mark.django_db
def test_validar_invitacion_get_no_consume_y_exige_password_unusable(
    mailoutbox: list[Any],
) -> None:
    _, actor = _crear_admin_local()
    cuenta = crear_cuenta_invitada(actor, "Sofía Vega", "sofia@example.invalid")
    assert enviar_invitacion(cuenta, "http://127.0.0.1:8000") is True
    token = _extraer_token_de_correo(mailoutbox[0].body)

    nonce_inicial = cuenta.nonce_verificacion
    for _ in range(2):
        resultado = validar_invitacion(token)
        assert resultado.pk == cuenta.pk

    cuenta.refresh_from_db()
    assert cuenta.email_verificado_en is None
    assert cuenta.nonce_verificacion == nonce_inicial
    assert cuenta.invitacion_administrativa.aceptada_en is None
    assert cuenta.user.has_usable_password() is False


@pytest.mark.django_db
def test_aceptar_invitacion_verifica_establece_clave_y_preserva_pending_grupos_actividad(
    mailoutbox: list[Any],
) -> None:
    _, actor = _crear_admin_local()
    cuenta = crear_cuenta_invitada(actor, "Diego Luna", "diego@example.invalid")
    assert enviar_invitacion(cuenta, "http://127.0.0.1:8000") is True
    token = _extraer_token_de_correo(mailoutbox[0].body)
    nonce_previo = cuenta.nonce_verificacion

    nueva_clave = secrets.token_urlsafe(16)
    aceptada = aceptar_invitacion(token, nueva_clave)
    aceptada.refresh_from_db()

    assert aceptada.estado == CuentaLocal.Estado.PENDIENTE
    assert aceptada.email_verificado_en is not None
    assert aceptada.nonce_verificacion != nonce_previo
    assert aceptada.invitacion_administrativa.aceptada_en is not None
    assert aceptada.user.is_active is True
    assert aceptada.user.check_password(nueva_clave) is True
    assert aceptada.user.is_staff is False
    assert aceptada.user.is_superuser is False
    assert list(aceptada.user.groups.all()) == []

    # La verificación normal posterior no puede reutilizarse para alterar estado o clave
    assert enviar_verificacion(aceptada, base_url="http://127.0.0.1:8000") is False
    with pytest.raises(ValidationError):
        verificar_correo(token)


@pytest.mark.django_db
def test_aceptar_invitacion_preserva_cuenta_previamente_aprobada(
    settings: Any, mailoutbox: list[Any]
) -> None:
    _, actor = _crear_admin_local()
    cuenta = crear_cuenta_invitada(actor, "Laura Paz", "laura@example.invalid")
    assert enviar_invitacion(cuenta, "http://127.0.0.1:8000") is True
    token = _extraer_token_de_correo(mailoutbox[0].body)

    grupo_sol, _ = Group.objects.get_or_create(name="local_solicitante")
    cuenta.estado = CuentaLocal.Estado.APROBADA
    cuenta.save(update_fields=["estado"])
    cuenta.user.groups.add(grupo_sol)

    nueva_clave = secrets.token_urlsafe(16)
    aceptar_invitacion(token, nueva_clave)
    cuenta.refresh_from_db()

    assert cuenta.estado == CuentaLocal.Estado.APROBADA
    assert cuenta.user.check_password(nueva_clave) is True
    assert list(cuenta.user.groups.values_list("name", flat=True)) == ["local_solicitante"]


@pytest.mark.django_db
def test_aceptar_invitacion_replay_corrupto_y_vencimiento_temporal(
    settings: Any, monkeypatch: Any, mailoutbox: list[Any]
) -> None:
    _, actor = _crear_admin_local()
    cuenta = crear_cuenta_invitada(actor, "Tomás Rey", "tomas@example.invalid")

    t0 = 1_800_000_000.0
    monkeypatch.setattr("django.core.signing.time.time", lambda: t0)
    settings.LOCAL_VERIFICATION_TIMEOUT = 30

    assert enviar_invitacion(cuenta, "http://127.0.0.1:8000") is True
    token = _extraer_token_de_correo(mailoutbox[0].body)

    # Token corrupto
    with pytest.raises(ValidationError):
        validar_invitacion(f"{token}corrupto")

    # Vencimiento temporal simulado con reloj local
    monkeypatch.setattr("django.core.signing.time.time", lambda: t0 + 45)
    with pytest.raises(ValidationError):
        validar_invitacion(token)
    with pytest.raises(ValidationError):
        aceptar_invitacion(token, secrets.token_urlsafe(16))

    # Dentro de ventana sí acepta, pero el replay falla
    monkeypatch.setattr("django.core.signing.time.time", lambda: t0 + 10)
    aceptar_invitacion(token, secrets.token_urlsafe(16))
    with pytest.raises(ValidationError):
        aceptar_invitacion(token, secrets.token_urlsafe(16))


@pytest.mark.django_db
def test_rechazo_inactividad_cambio_nonce_y_password_ya_usable_bloquean(
    settings: Any, mailoutbox: list[Any]
) -> None:
    _, actor = _crear_admin_local()
    settings.LOCAL_VERIFY_RESEND_MIN_INTERVAL = 0

    # 1. Cambio de actividad (is_active=False) revoca token y bloquea reenvío
    cuenta_inact = crear_cuenta_invitada(actor, "Inactiva", "inactiva@example.invalid")
    assert enviar_invitacion(cuenta_inact, "http://127.0.0.1:8000") is True
    tok_inact = _extraer_token_de_correo(mailoutbox[-1].body)
    cuenta_inact.user.is_active = False
    cuenta_inact.user.save(update_fields=["is_active"])
    with pytest.raises(ValidationError):
        validar_invitacion(tok_inact)
    with pytest.raises(ValidationError):
        aceptar_invitacion(tok_inact, secrets.token_urlsafe(16))
    assert enviar_invitacion(cuenta_inact, "http://127.0.0.1:8000") is False

    # 2. Rechazo administrativo bloquea token y reenvío
    cuenta_rech = crear_cuenta_invitada(actor, "Rechazada", "rechazada@example.invalid")
    assert enviar_invitacion(cuenta_rech, "http://127.0.0.1:8000") is True
    tok_rech = _extraer_token_de_correo(mailoutbox[-1].body)
    cuenta_rech.estado = CuentaLocal.Estado.RECHAZADA
    cuenta_rech.save(update_fields=["estado"])
    with pytest.raises(ValidationError):
        validar_invitacion(tok_rech)
    assert enviar_invitacion(cuenta_rech, "http://127.0.0.1:8000") is False

    # 3. Cambio de nonce manual invalida token
    cuenta_nonce = crear_cuenta_invitada(actor, "Nonce", "nonce@example.invalid")
    assert enviar_invitacion(cuenta_nonce, "http://127.0.0.1:8000") is True
    tok_nonce = _extraer_token_de_correo(mailoutbox[-1].body)
    cuenta_nonce.nonce_verificacion = uuid.uuid4()
    cuenta_nonce.save(update_fields=["nonce_verificacion"])
    with pytest.raises(ValidationError):
        validar_invitacion(tok_nonce)

    # 4. Contraseña ya utilizable bloquea aceptación y envío
    cuenta_pwd = crear_cuenta_invitada(actor, "ConClave", "conclave@example.invalid")
    assert enviar_invitacion(cuenta_pwd, "http://127.0.0.1:8000") is True
    tok_pwd = _extraer_token_de_correo(mailoutbox[-1].body)
    cuenta_pwd.user.set_password(secrets.token_urlsafe(16))
    cuenta_pwd.user.save(update_fields=["password"])
    with pytest.raises(ValidationError):
        aceptar_invitacion(tok_pwd, secrets.token_urlsafe(16))
    assert enviar_invitacion(cuenta_pwd, "http://127.0.0.1:8000") is False
