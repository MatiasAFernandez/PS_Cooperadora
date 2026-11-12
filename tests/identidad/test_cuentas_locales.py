"""Pruebas funcionales del núcleo de cuentas e identidades locales (SPEC-022)."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import Group
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections
from django.test import RequestFactory

from identidad.cuentas import (
    decidir_cuenta,
    enviar_verificacion,
    limitar,
    normalizar_correo,
    registrar_cuenta,
    token_verificacion,
    verificar_correo,
)
from identidad.models import CuentaLocal
from identidad.services import Actor, has_capability, resolve_actor


def _crear_request_autenticado(user: Any) -> Any:
    """Crea una petición simulada con sesión y usuario autenticado."""
    rf = RequestFactory()
    request = rf.get("/")
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return request


@pytest.fixture
def actor_admin(db: Any) -> Actor:
    """Actor administrativo con capacidad conocida para gestionar cuentas."""
    user_model = get_user_model()
    admin_user = user_model.objects.create_user(
        username="admin_local_test",
        email="admin@example.invalid",
        password="Clave-segura-sintetica-admin-123!",
    )
    grupo, _ = Group.objects.get_or_create(name="local_administracion")
    admin_user.groups.add(grupo)
    return Actor(
        subject_id=admin_user.pk,
        capabilities=frozenset({"identidad.administrar_cuentas"}),
        email_registrado="admin@example.invalid",
    )


@pytest.fixture
def cuenta_base(db: Any) -> CuentaLocal:
    """Cuenta local registrada en estado inicial pendiente."""
    cuenta = registrar_cuenta(
        nombre="Solicitante Prueba",
        email="solicitante@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
        area_habitual="Sistemas",
        cuit_cuil="20-12345678-9",
        legajo="LEG-1234",
    )
    assert cuenta is not None
    return cuenta


@pytest.fixture
def cuenta_verificada(cuenta_base: CuentaLocal) -> CuentaLocal:
    """Cuenta local con correo verificado pero pendiente de decisión."""
    token = token_verificacion(cuenta_base)
    return verificar_correo(token)


@pytest.mark.django_db
def test_registro_normaliza_correo_y_crea_usuario_sin_permisos() -> None:
    """El registro normaliza correo y crea el User Django sin grupos ni permisos."""
    cuenta = registrar_cuenta(
        nombre="  Carlos Prueba  ",
        email="  CARLOS.PRUEBA@EXAMPLE.INVALID  ",
        password="Clave-segura-sintetica-valida-123!",
        area_habitual="Compras",
    )
    assert cuenta is not None
    assert cuenta.email == "carlos.prueba@example.invalid"
    assert cuenta.nombre_completo == "Carlos Prueba"
    assert cuenta.user.email == "carlos.prueba@example.invalid"
    assert cuenta.user.username.startswith("local_")
    assert cuenta.user.has_usable_password() is True
    assert cuenta.user.groups.count() == 0
    assert cuenta.user.user_permissions.count() == 0
    assert cuenta.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta.email_verificado_en is None


@pytest.mark.django_db
def test_registro_duplicado_local_y_legado_devuelve_none() -> None:
    """El correo duplicado en CuentaLocal o en User legado devuelve None sin mutar."""
    c1 = registrar_cuenta(
        nombre="Primer Registro",
        email="repetido@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    assert c1 is not None

    # Duplicado contra CuentaLocal existente
    c2 = registrar_cuenta(
        nombre="Segundo Intento",
        email="  REPETIDO@EXAMPLE.INVALID  ",
        password="Clave-segura-sintetica-valida-123!",
    )
    assert c2 is None

    # Duplicado contra User preexistente sin CuentaLocal
    user_model = get_user_model()
    user_model.objects.create_user(
        username="legacy_user_alpha",
        email="legacy@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    c3 = registrar_cuenta(
        nombre="Intento Sobre Legado",
        email="LEGACY@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    assert c3 is None
    assert not CuentaLocal.objects.filter(email="legacy@example.invalid").exists()


@pytest.mark.django_db
def test_registro_password_debil_rechazada() -> None:
    """La contraseña que no cumple validadores estándar de Django genera ValidationError."""
    with pytest.raises(ValidationError):
        registrar_cuenta(
            nombre="Usuario Débil",
            email="debil@example.invalid",
            password="123",
        )


@pytest.mark.django_db
def test_registro_correo_invalido_rechazado() -> None:
    """Un formato de correo electrónico inválido arroja ValidationError."""
    with pytest.raises(ValidationError):
        registrar_cuenta(
            nombre="Usuario Formato",
            email="correo-sin-arroba-ni-dominio",
            password="Clave-segura-sintetica-valida-123!",
        )


@pytest.mark.django_db
def test_verificar_correo_no_aprueba_cuenta(cuenta_base: CuentaLocal) -> None:
    """Verificar el correo marca el timestamp y rota nonce, pero mantiene estado PENDIENTE."""
    nonce_previo = cuenta_base.nonce_verificacion
    token = token_verificacion(cuenta_base)
    cuenta_verif = verificar_correo(token)

    assert cuenta_verif.email_verificado_en is not None
    assert cuenta_verif.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta_verif.nonce_verificacion != nonce_previo


@pytest.mark.django_db
def test_verificar_correo_replay_invalido_y_vencido_rechazados(
    cuenta_base: CuentaLocal, settings: Any
) -> None:
    """Reutilizar un token, usar una firma corrupta o un token expirado falla con error."""
    token = token_verificacion(cuenta_base)
    verificar_correo(token)

    # Replay: el nonce ya rotó
    with pytest.raises(ValidationError, match="ya fue utilizado|no es válido"):
        verificar_correo(token)

    # Firma corrupta
    with pytest.raises(ValidationError, match="inválido"):
        verificar_correo("token-adulterado.firma.invalida")

    # Expiración
    cuenta_exp = registrar_cuenta(
        nombre="Usuario Vence",
        email="vence@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    assert cuenta_exp is not None
    token_exp = token_verificacion(cuenta_exp)
    settings.LOCAL_VERIFICATION_TIMEOUT = -1
    with pytest.raises(ValidationError, match="vencido"):
        verificar_correo(token_exp)


@pytest.mark.django_db
def test_cambio_password_invalida_token_verificacion(cuenta_base: CuentaLocal) -> None:
    """Modificar la contraseña del usuario invalida los tokens de verificación previos."""
    token = token_verificacion(cuenta_base)
    cuenta_base.user.set_password("Nueva-clave-sintetica-valida-456!")
    cuenta_base.user.save()

    with pytest.raises(ValidationError, match="cambio de contraseña"):
        verificar_correo(token)


@pytest.mark.django_db
def test_enviar_verificacion_fallo_correo_o_retorno_cero_da_false(
    cuenta_base: CuentaLocal, monkeypatch: Any
) -> None:
    """Si send_mail falla o devuelve 0, retorna False y la cuenta permanece intacta."""
    # Retorno 0 mensajes entregados
    monkeypatch.setattr("identidad.cuentas.send_mail", lambda *args, **kwargs: 0)
    res_cero = enviar_verificacion(cuenta_base, base_url="http://127.0.0.1:8000")
    assert res_cero is False
    assert CuentaLocal.objects.filter(pk=cuenta_base.pk).exists()

    # Excepción SMTP simulada
    falla_mock = MagicMock(side_effect=Exception("Fallo conexion SMTP simulada"))
    monkeypatch.setattr("identidad.cuentas.send_mail", falla_mock)
    res_error = enviar_verificacion(cuenta_base, base_url="http://127.0.0.1:8000")
    assert res_error is False
    assert CuentaLocal.objects.filter(pk=cuenta_base.pk).exists()


@pytest.mark.django_db
def test_enviar_verificacion_usa_url_servidor_y_limita_reenvio(
    cuenta_base: CuentaLocal, monkeypatch: Any
) -> None:
    """El envío construye la URL con la base explícita del servidor y aplica rate limit."""
    envios = []

    def mock_send_mail(**kwargs: Any) -> int:
        envios.append(kwargs)
        return 1

    monkeypatch.setattr("identidad.cuentas.send_mail", mock_send_mail)
    exito = enviar_verificacion(cuenta_base, base_url="http://127.0.0.1:8000")

    assert exito is True
    assert len(envios) == 1
    assert envios[0]["recipient_list"] == [cuenta_base.email]
    assert "http://127.0.0.1:8000/cuentas/verificar/?token=" in envios[0]["message"]

    # Reenvío inmediato dentro del minuto es rechazado por rate limit
    reintento = enviar_verificacion(cuenta_base, base_url="http://127.0.0.1:8000")
    assert reintento is False


@pytest.mark.django_db
def test_decidir_cuenta_aprobar_antes_de_verificar_denegado(
    actor_admin: Actor, cuenta_base: CuentaLocal
) -> None:
    """No se permite decidir administrativamente una cuenta que no verificó su casilla."""
    with pytest.raises(ValidationError, match="correo no verificado"):
        decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_base.pk, aprobar=True)


@pytest.mark.django_db
def test_decidir_cuenta_actor_sin_capacidad_denegado(cuenta_verificada: CuentaLocal) -> None:
    """Un actor sin 'identidad.administrar_cuentas' recibe PermissionDenied."""
    actor_raso = Actor(
        subject_id=9999,
        capabilities=frozenset({"gastos.presentar"}),
        email_registrado="raso@example.invalid",
    )
    with pytest.raises(PermissionDenied):
        decidir_cuenta(actor=actor_raso, cuenta_id=cuenta_verificada.pk, aprobar=True)


@pytest.mark.django_db
def test_decidir_cuenta_rechazo_sin_motivo_denegado(
    actor_admin: Actor, cuenta_verificada: CuentaLocal
) -> None:
    """El rechazo exige motivo no vacío."""
    with pytest.raises(ValidationError, match="motivo de rechazo es obligatorio"):
        decidir_cuenta(
            actor=actor_admin,
            cuenta_id=cuenta_verificada.pk,
            aprobar=False,
            motivo="   ",
        )


@pytest.mark.django_db
def test_decidir_cuenta_aprobacion_registra_grupo_actor_y_fecha(
    actor_admin: Actor, cuenta_verificada: CuentaLocal
) -> None:
    """Aprobar otorga el grupo 'local_solicitante' y deja trazabilidad de actor y fecha."""
    decidida = decidir_cuenta(
        actor=actor_admin,
        cuenta_id=cuenta_verificada.pk,
        aprobar=True,
        motivo="Documentación verificada",
    )
    assert decidida.estado == CuentaLocal.Estado.APROBADA
    assert decidida.decidida_en is not None
    assert decidida.decidida_por_id == actor_admin.subject_id
    assert decidida.user.groups.filter(name="local_solicitante").exists()


@pytest.mark.django_db
def test_decidir_cuenta_doble_decision_genera_conflicto(
    actor_admin: Actor, cuenta_verificada: CuentaLocal
) -> None:
    """Una cuenta ya aprobada o rechazada no admite una segunda decisión."""
    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_verificada.pk, aprobar=True)
    with pytest.raises(ValidationError, match="ya ha sido decidida"):
        decidir_cuenta(
            actor=actor_admin,
            cuenta_id=cuenta_verificada.pk,
            aprobar=False,
            motivo="rev",
        )


@pytest.mark.django_db
def test_decidir_cuenta_aprobar_no_bool_y_usuario_suspendido_denegados(
    actor_admin: Actor, cuenta_verificada: CuentaLocal
) -> None:
    """El parámetro aprobar debe ser bool estricto y el usuario no puede estar inactivo."""
    with pytest.raises(ValidationError, match="booleano"):
        decidir_cuenta(
            actor=actor_admin,
            cuenta_id=cuenta_verificada.pk,
            aprobar="True",  # type: ignore[arg-type]
        )

    cuenta_verificada.user.is_active = False
    cuenta_verificada.user.save()
    with pytest.raises(ValidationError, match="inactivo o suspendido"):
        decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_verificada.pk, aprobar=True)


@pytest.mark.django_db
def test_resolve_actor_cuenta_pendiente_rechazada_o_suspendida_retorna_none(
    cuenta_verificada: CuentaLocal, actor_admin: Actor, settings: Any
) -> None:
    """resolve_actor retorna None para cuentas no aprobadas o inactivas, aun con demo activo."""
    settings.LOCAL_IDENTITY_ENABLED = True
    settings.DEMO_IDENTITY_ENABLED = True

    # Estado PENDIENTE
    req_pendiente = _crear_request_autenticado(cuenta_verificada.user)
    assert resolve_actor(req_pendiente) is None

    # Estado RECHAZADA
    decidir_cuenta(
        actor=actor_admin,
        cuenta_id=cuenta_verificada.pk,
        aprobar=False,
        motivo="Falta acreditación",
    )
    req_rechazada = _crear_request_autenticado(cuenta_verificada.user)
    assert resolve_actor(req_rechazada) is None

    # Inactiva / Suspendida
    cuenta_verificada.user.is_active = False
    cuenta_verificada.user.save()
    req_suspendida = _crear_request_autenticado(cuenta_verificada.user)
    assert resolve_actor(req_suspendida) is None


@pytest.mark.django_db
def test_resolve_actor_flag_local_off_no_hace_bypass_a_demo(
    cuenta_verificada: CuentaLocal, actor_admin: Actor, settings: Any
) -> None:
    """Si LOCAL_IDENTITY_ENABLED es False, un usuario local no puede resolverse vía demo."""
    settings.LOCAL_IDENTITY_ENABLED = False
    settings.DEMO_IDENTITY_ENABLED = True

    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_verificada.pk, aprobar=True)
    request = _crear_request_autenticado(cuenta_verificada.user)
    assert resolve_actor(request) is None


@pytest.mark.django_db
def test_resolve_actor_cuenta_aprobada_capacidades_solicitante_propias(
    cuenta_verificada: CuentaLocal, actor_admin: Actor, settings: Any
) -> None:
    """Cuenta local aprobada resuelve Actor con capacidades propias de solicitante."""
    settings.LOCAL_IDENTITY_ENABLED = True
    settings.DEMO_IDENTITY_ENABLED = False

    decidir_cuenta(actor=actor_admin, cuenta_id=cuenta_verificada.pk, aprobar=True)
    request = _crear_request_autenticado(cuenta_verificada.user)
    actor = resolve_actor(request)

    assert actor is not None
    assert actor.subject_id == cuenta_verificada.user.pk
    assert actor.email_registrado == normalizar_correo(cuenta_verificada.email)

    # Capacidades propias concedidas
    assert has_capability(actor, "gastos.presentar") is True
    assert has_capability(actor, "gastos.consultar_propias") is True
    assert has_capability(actor, "facturacion.presentar") is True
    assert has_capability(actor, "facturacion.consultar_propias") is True
    assert has_capability(actor, "facturacion.corregir") is True
    assert has_capability(actor, "facturacion.informar_cobro") is True
    assert has_capability(actor, "documentos.incorporar") is True
    assert has_capability(actor, "documentos.consultar_metadatos") is True
    assert has_capability(actor, "documentos.descargar") is True

    # No facultades operativas de pago, configuración ni lectura global
    assert has_capability(actor, "gastos.registrar_pago") is False
    assert has_capability(actor, "gastos.consultar_todas") is False
    assert has_capability(actor, "facturacion.consultar_todas") is False
    assert has_capability(actor, "gestion.configurar") is False
    assert has_capability(actor, "identidad.administrar_cuentas") is False


@pytest.mark.django_db
def test_usuario_legacy_sin_cuenta_local_no_obtiene_local_administracion(settings: Any) -> None:
    """Un usuario legado de demo con grupo local_administracion ve filtrada esa capacidad."""
    settings.DEMO_IDENTITY_ENABLED = True
    settings.LOCAL_IDENTITY_ENABLED = True

    user_model = get_user_model()
    demo_user = user_model.objects.create_user(
        username="demo_legacy_sin_cuenta",
        email="demo.legacy@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    grupo_admin, _ = Group.objects.get_or_create(name="local_administracion")
    demo_user.groups.add(grupo_admin)

    request = _crear_request_autenticado(demo_user)
    actor = resolve_actor(request)

    assert actor is not None
    # No puede heredar la capacidad local por pertenecer al circuito legado
    assert has_capability(actor, "identidad.administrar_cuentas") is False


@pytest.mark.django_db
def test_flag_demo_off_retorna_none_para_usuario_sin_cuenta_local(settings: Any) -> None:
    """Si DEMO_IDENTITY_ENABLED está apagado, un usuario sin CuentaLocal retorna None."""
    settings.DEMO_IDENTITY_ENABLED = False
    settings.LOCAL_IDENTITY_ENABLED = True

    user_model = get_user_model()
    user_sin_cuenta = user_model.objects.create_user(
        username="user_huerfano",
        email="huerfano@example.invalid",
        password="Clave-segura-sintetica-valida-123!",
    )
    request = _crear_request_autenticado(user_sin_cuenta)
    assert resolve_actor(request) is None


@pytest.mark.django_db
def test_limitar_tasa_y_ventana() -> None:
    """limitar controla la cantidad de intentos permitidos dentro de la ventana."""
    clave = "test-rate-limit-key"
    assert limitar(clave, maximo=2, segundos=60) is True
    assert limitar(clave, maximo=2, segundos=60) is True
    assert limitar(clave, maximo=2, segundos=60) is False


@pytest.mark.django_db(transaction=True)
def test_aprobaciones_concurrentes_una_sola_exitosa(
    actor_admin: Actor, cuenta_verificada: CuentaLocal
) -> None:
    """Dos intentos concurrentes de decisión sobre la misma cuenta resuelven exactamente uno."""
    cuenta_id = cuenta_verificada.pk
    exitos: list[CuentaLocal] = []
    errores: list[Exception] = []

    def ejecutar_decision() -> None:
        try:
            res = decidir_cuenta(
                actor=actor_admin,
                cuenta_id=cuenta_id,
                aprobar=True,
                motivo="Decisión concurrente",
            )
            exitos.append(res)
        except Exception as exc:
            errores.append(exc)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(ejecutar_decision)
        f2 = executor.submit(ejecutar_decision)
        f1.result()
        f2.result()

    assert len(exitos) == 1
    assert len(errores) == 1
    assert isinstance(errores[0], ValidationError)
