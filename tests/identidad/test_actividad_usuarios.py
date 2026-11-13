"""Pruebas de servicio y concurrencia para actividad de cuentas locales (SPEC-025)."""

import secrets
import threading
from datetime import timedelta

import pytest
from django.contrib.auth import SESSION_KEY, authenticate, get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import connections
from django.utils import timezone

from identidad.actividad_usuarios import cambiar_actividad_cuenta
from identidad.models import CambioActividadCuentaLocal, CuentaLocal
from identidad.services import Actor
from identidad.tokens_local import token_recuperacion_local


def _crear_cuenta_local(
    *,
    username: str,
    email: str,
    is_active: bool = True,
    estado: str = CuentaLocal.Estado.APROBADA,
    verificada: bool = True,
    grupos: tuple[str, ...] = (),
    is_staff: bool = False,
    is_superuser: bool = False,
    password: str | None = None,
) -> tuple[CuentaLocal, str]:
    user_model = get_user_model()
    raw_password = password or secrets.token_urlsafe(16)
    user = user_model.objects.create_user(
        username=username,
        email=email,
        password=raw_password,
        first_name="NombreLegado",
        last_name="ApellidoLegado",
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    for nombre_grupo in grupos:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)

    cuenta = CuentaLocal.objects.create(
        user=user,
        email=email,
        nombre_completo=f"Persona {username}",
        area_habitual="Tesorería",
        cuit_cuil="27-12345678-9",
        legajo=f"LEG-{username}",
        estado=estado,
        email_verificado_en=timezone.now() if verificada else None,
    )
    return cuenta, raw_password


def _actor_desde_user(
    user, capabilities: frozenset[str] = frozenset({"identidad.administrar_cuentas"})
) -> Actor:
    return Actor(
        subject_id=user.pk,
        capabilities=capabilities,
        email_registrado=user.email,
    )


def _crear_sesion_usuario(user_id: int, *, expirada: bool = False) -> str:
    store = SessionStore()
    store[SESSION_KEY] = str(user_id)
    store.create()
    if expirada:
        Session.objects.filter(session_key=store.session_key).update(
            expire_date=timezone.now() - timedelta(hours=1)
        )
    return store.session_key


@pytest.mark.django_db
def test_exige_capacidad_antes_de_consultar(django_assert_num_queries):
    cuenta, _ = _crear_cuenta_local(username="objetivo1", email="objetivo1@example.org")
    actor_sin_permiso = Actor(
        subject_id=cuenta.user_id, capabilities=frozenset({"gastos.presentar"})
    )

    with django_assert_num_queries(0):
        with pytest.raises(PermissionDenied):
            cambiar_actividad_cuenta(None, cuenta.pk, False, "Motivo válido", True)

    with django_assert_num_queries(0):
        with pytest.raises(PermissionDenied):
            cambiar_actividad_cuenta(actor_sin_permiso, cuenta.pk, False, "Motivo válido", True)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kwargs_actor", "con_cuenta_local"),
    [
        ({"is_active": False, "grupos": ("local_administracion",)}, True),
        ({"estado": CuentaLocal.Estado.PENDIENTE, "grupos": ("local_administracion",)}, True),
        ({"estado": CuentaLocal.Estado.RECHAZADA, "grupos": ("local_administracion",)}, True),
        ({"verificada": False, "grupos": ("local_administracion",)}, True),
        ({"grupos": ("local_solicitante",)}, True),
        ({"grupos": (), "is_staff": True, "is_superuser": True}, True),
        ({"grupos": ("local_administracion",), "is_staff": True, "is_superuser": True}, False),
    ],
)
def test_revalidacion_actor_bajo_bloqueo_rechaza_no_habilitados(kwargs_actor, con_cuenta_local):
    objetivo, _ = _crear_cuenta_local(username="objetivo_rev", email="objetivo_rev@example.org")
    user_model = get_user_model()

    if con_cuenta_local:
        cuenta_actor, _ = _crear_cuenta_local(
            username="actor_invalido",
            email="actor_invalido@example.org",
            **kwargs_actor,
        )
        actor_user = cuenta_actor.user
    else:
        actor_user = user_model.objects.create_user(
            username="staff_sin_cuenta",
            email="staff_sin_cuenta@example.org",
            password=secrets.token_urlsafe(16),
            is_active=True,
            is_staff=kwargs_actor.get("is_staff", False),
            is_superuser=kwargs_actor.get("is_superuser", False),
        )
        for nombre_grupo in kwargs_actor.get("grupos", ()):
            grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
            actor_user.groups.add(grupo)

    actor = _actor_desde_user(actor_user)
    with pytest.raises(PermissionDenied):
        cambiar_actividad_cuenta(actor, objetivo.pk, False, "Intento sin facultad real", True)

    objetivo.user.refresh_from_db()
    assert objetivo.user.is_active is True
    assert CambioActividadCuentaLocal.objects.count() == 0


@pytest.mark.django_db
def test_validacion_motivo_y_booleanos_estrictos():
    admin, _ = _crear_cuenta_local(
        username="admin_motivo",
        email="admin_motivo@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(username="obj_motivo", email="obj_motivo@example.org")
    actor = _actor_desde_user(admin.user)

    for motivo_invalido in ("", "   \n\t  ", None, 123, "x" * 2001):
        with pytest.raises(ValidationError):
            cambiar_actividad_cuenta(actor, objetivo.pk, False, motivo_invalido, True)

    with pytest.raises(ValidationError):
        cambiar_actividad_cuenta(actor, objetivo.pk, 0, "Motivo válido", True)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        cambiar_actividad_cuenta(actor, objetivo.pk, False, "Motivo válido", 1)  # type: ignore[arg-type]

    motivo_limite = "a" * 2000
    cuenta_res, evento = cambiar_actividad_cuenta(
        actor,
        objetivo.pk,
        False,
        f"  {motivo_limite}  ",
        True,
    )
    assert evento is not None
    assert evento.motivo == motivo_limite
    assert cuenta_res.user.is_active is False


@pytest.mark.django_db
def test_noop_y_conflicto_actividad_esperada_obsoleta():
    admin, _ = _crear_cuenta_local(
        username="admin_noop",
        email="admin_noop@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(
        username="obj_noop",
        email="obj_noop@example.org",
        is_active=True,
    )
    actor = _actor_desde_user(admin.user)
    nonce_inicial = objetivo.nonce_verificacion
    sesion_key = _crear_sesion_usuario(objetivo.user_id)

    # Ya está activa -> activar=True es no-op incluso si actividad_esperada estaba obsoleta
    cuenta_noop, evento_noop = cambiar_actividad_cuenta(
        actor, objetivo.pk, True, "Reenvío idempotente", False
    )
    assert evento_noop is None
    assert cuenta_noop.nonce_verificacion == nonce_inicial
    assert CambioActividadCuentaLocal.objects.count() == 0
    assert Session.objects.filter(session_key=sesion_key).exists()

    # Está activa y se intenta desactivar con actividad_esperada=False (obsoleta) -> ValidationError
    with pytest.raises(ValidationError):
        cambiar_actividad_cuenta(actor, objetivo.pk, False, "Confirmación vieja", False)

    objetivo.user.refresh_from_db()
    assert objetivo.user.is_active is True
    assert CambioActividadCuentaLocal.objects.count() == 0


@pytest.mark.django_db
def test_no_permite_autodesactivacion():
    admin1, _ = _crear_cuenta_local(
        username="admin_auto_1",
        email="admin_auto_1@example.org",
        grupos=("local_administracion",),
    )
    _crear_cuenta_local(
        username="admin_auto_2",
        email="admin_auto_2@example.org",
        grupos=("local_administracion",),
    )
    actor = _actor_desde_user(admin1.user)

    with pytest.raises(ValidationError):
        cambiar_actividad_cuenta(actor, admin1.pk, False, "Autodesactivación", True)

    admin1.user.refresh_from_db()
    assert admin1.user.is_active is True
    assert CambioActividadCuentaLocal.objects.count() == 0


@pytest.mark.django_db
def test_candidatos_no_habilitados_no_cuentan_como_admin_alternativo(monkeypatch):
    """Un staff/superuser o admin pendiente/sin verificar no habilita desactivar al único admin."""
    admin_unico, _ = _crear_cuenta_local(
        username="admin_unico",
        email="admin_unico@example.org",
        grupos=("local_administracion",),
    )
    _crear_cuenta_local(
        username="admin_pendiente",
        email="admin_pendiente@example.org",
        estado=CuentaLocal.Estado.PENDIENTE,
        grupos=("local_administracion",),
    )
    _crear_cuenta_local(
        username="admin_sin_verif",
        email="admin_sin_verif@example.org",
        verificada=False,
        grupos=("local_administracion",),
    )
    _crear_cuenta_local(
        username="admin_inactivo",
        email="admin_inactivo@example.org",
        is_active=False,
        grupos=("local_administracion",),
    )
    _crear_cuenta_local(
        username="staff_sin_grupo",
        email="staff_sin_grupo@example.org",
        is_staff=True,
        is_superuser=True,
        grupos=(),
    )

    # Simular que el caller intenta desactivar al único admin local habilitado sin ser él mismo
    # (por ejemplo mediante una extensión futura o bypass del chequeo de autodesactivación)
    actor_externo, _ = _crear_cuenta_local(
        username="actor_simul_otro",
        email="actor_simul_otro@example.org",
        grupos=("local_administracion",),
    )
    # Desactivar actor_simul_otro en memoria? No: verificar que el helper de elegibilidad
    # excluye a los candidatos no habilitados y sólo reconoce a admin_unico y actor_simul_otro.
    from identidad.actividad_usuarios import _es_admin_local_habilitado

    assert _es_admin_local_habilitado(admin_unico.user, admin_unico, {admin_unico.user_id}) is True
    pendiente = CuentaLocal.objects.select_related("user").get(email="admin_pendiente@example.org")
    assert _es_admin_local_habilitado(pendiente.user, pendiente, {pendiente.user_id}) is False
    sin_verif = CuentaLocal.objects.select_related("user").get(email="admin_sin_verif@example.org")
    assert _es_admin_local_habilitado(sin_verif.user, sin_verif, {sin_verif.user_id}) is False
    inactivo = CuentaLocal.objects.select_related("user").get(email="admin_inactivo@example.org")
    assert _es_admin_local_habilitado(inactivo.user, inactivo, {inactivo.user_id}) is False
    staff = CuentaLocal.objects.select_related("user").get(email="staff_sin_grupo@example.org")
    assert _es_admin_local_habilitado(staff.user, staff, set()) is False
    assert actor_externo.user.is_active is True


@pytest.mark.django_db
def test_desactivar_y_reactivar_conserva_campos_protegidos_e_invalida_enlaces_y_sesiones():
    admin, _ = _crear_cuenta_local(
        username="admin_ciclo",
        email="admin_ciclo@example.org",
        grupos=("local_administracion",),
    )
    objetivo, raw_password = _crear_cuenta_local(
        username="obj_ciclo",
        email="obj_ciclo@example.org",
        estado=CuentaLocal.Estado.PENDIENTE,
        verificada=False,
        grupos=("local_solicitante",),
    )
    otro, _ = _crear_cuenta_local(username="otro_usuario", email="otro_usuario@example.org")

    hash_original = objetivo.user.password
    nonce_inicial = objetivo.nonce_verificacion
    token_inicial = token_recuperacion_local.make_token(objetivo.user)
    assert token_recuperacion_local.check_token(objetivo.user, token_inicial) is True

    sesion_obj_vigente = _crear_sesion_usuario(objetivo.user_id)
    sesion_otro_vigente = _crear_sesion_usuario(otro.user_id)
    _crear_sesion_usuario(objetivo.user_id, expirada=True)

    actor = _actor_desde_user(admin.user)

    # 1) Desactivar
    cuenta_desact, ev_desact = cambiar_actividad_cuenta(
        actor, objetivo.pk, False, "  Suspensión preventiva  ", True
    )
    assert ev_desact is not None
    assert ev_desact.cuenta_id == objetivo.pk
    assert ev_desact.autor_id == admin.user_id
    assert ev_desact.motivo == "Suspensión preventiva"
    assert ev_desact.actividad_anterior is True
    assert ev_desact.actividad_nueva is False

    cuenta_desact.user.refresh_from_db()
    assert cuenta_desact.user.is_active is False
    assert cuenta_desact.nonce_verificacion != nonce_inicial
    assert token_recuperacion_local.check_token(cuenta_desact.user, token_inicial) is False
    assert not Session.objects.filter(session_key=sesion_obj_vigente).exists()
    assert Session.objects.filter(session_key=sesion_otro_vigente).exists()
    assert authenticate(username="obj_ciclo", password=raw_password) is None

    # 2) Reactivar
    nonce_desactivada = cuenta_desact.nonce_verificacion
    cuenta_react, ev_react = cambiar_actividad_cuenta(
        actor, objetivo.pk, True, "  Habilitación confirmada  ", False
    )
    assert ev_react is not None
    assert ev_react.actividad_anterior is False
    assert ev_react.actividad_nueva is True

    cuenta_react.refresh_from_db()
    cuenta_react.user.refresh_from_db()
    assert cuenta_react.user.is_active is True
    assert cuenta_react.nonce_verificacion != nonce_desactivada
    # Campos protegidos intactos
    assert cuenta_react.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta_react.email_verificado_en is None
    assert cuenta_react.user.password == hash_original
    assert cuenta_react.user.first_name == "NombreLegado"
    assert cuenta_react.user.last_name == "ApellidoLegado"
    assert list(cuenta_react.user.groups.values_list("name", flat=True)) == ["local_solicitante"]
    # Enlace y sesión viejos NO reviven
    assert token_recuperacion_local.check_token(cuenta_react.user, token_inicial) is False
    assert not Session.objects.filter(session_key=sesion_obj_vigente).exists()
    assert Session.objects.filter(session_key=sesion_otro_vigente).exists()
    # Login vuelve a funcionar con credenciales originales
    assert authenticate(username="obj_ciclo", password=raw_password) == cuenta_react.user


@pytest.mark.django_db
def test_rollback_completo_si_falla_creacion_de_historia(monkeypatch):
    admin, _ = _crear_cuenta_local(
        username="admin_rb",
        email="admin_rb@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(username="obj_rb", email="obj_rb@example.org")
    actor = _actor_desde_user(admin.user)
    nonce_inicial = objetivo.nonce_verificacion
    sesion_key = _crear_sesion_usuario(objetivo.user_id)

    def _fallar_create(*args, **kwargs):
        raise RuntimeError("Fallo simulado al persistir historia")

    monkeypatch.setattr(CambioActividadCuentaLocal.objects, "create", _fallar_create)

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        cambiar_actividad_cuenta(actor, objetivo.pk, False, "Motivo rollback", True)

    objetivo.refresh_from_db()
    objetivo.user.refresh_from_db()
    assert objetivo.user.is_active is True
    assert objetivo.nonce_verificacion == nonce_inicial
    assert CambioActividadCuentaLocal.objects.count() == 0
    assert Session.objects.filter(session_key=sesion_key).exists()


@pytest.mark.django_db
def test_rechaza_motor_sesiones_no_db(settings):
    admin, _ = _crear_cuenta_local(
        username="admin_motor",
        email="admin_motor@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(username="obj_motor", email="obj_motor@example.org")
    settings.SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
    actor = _actor_desde_user(admin.user)

    with pytest.raises(ImproperlyConfigured):
        cambiar_actividad_cuenta(actor, objetivo.pk, False, "Motor no DB", True)

    objetivo.user.refresh_from_db()
    assert objetivo.user.is_active is True
    assert CambioActividadCuentaLocal.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_carrera_cruzada_dos_admins_en_postgresql_deja_un_admin_activo():
    admin_a, _ = _crear_cuenta_local(
        username="admin_carrera_a",
        email="admin_carrera_a@example.org",
        grupos=("local_administracion",),
    )
    admin_b, _ = _crear_cuenta_local(
        username="admin_carrera_b",
        email="admin_carrera_b@example.org",
        grupos=("local_administracion",),
    )
    actor_a = _actor_desde_user(admin_a.user)
    actor_b = _actor_desde_user(admin_b.user)

    barrera = threading.Barrier(2, timeout=10)
    resultados: list[tuple[str, str]] = []
    lock_res = threading.Lock()

    def _trabajar(nombre: str, actor: Actor, target_cuenta_id: int) -> None:
        try:
            barrera.wait()
            cambiar_actividad_cuenta(actor, target_cuenta_id, False, f"Cruce {nombre}", True)
            estado = "ok"
        except PermissionDenied:
            estado = "permission_denied"
        except ValidationError:
            estado = "validation_error"
        except Exception as exc:  # pragma: no cover
            estado = f"error:{type(exc).__name__}"
        finally:
            connections.close_all()

        with lock_res:
            resultados.append((nombre, estado))

    t1 = threading.Thread(target=_trabajar, args=("A->B", actor_a, admin_b.pk))
    t2 = threading.Thread(target=_trabajar, args=("B->A", actor_b, admin_a.pk))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert len(resultados) == 2

    estados = sorted(estado for _, estado in resultados)
    assert estados == ["ok", "permission_denied"]

    admin_a.user.refresh_from_db()
    admin_b.user.refresh_from_db()
    activos = [admin_a.user.is_active, admin_b.user.is_active]
    assert activos.count(True) == 1
    assert activos.count(False) == 1
    assert CambioActividadCuentaLocal.objects.count() == 1
