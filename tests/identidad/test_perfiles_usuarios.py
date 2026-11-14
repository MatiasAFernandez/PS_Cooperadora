"""Pruebas de servicio y concurrencia para asignación de perfiles locales (SPEC-026)."""

import secrets
import threading

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections
from django.utils import timezone

from identidad.actividad_usuarios import cambiar_actividad_cuenta
from identidad.models import (
    CambioActividadCuentaLocal,
    CambioPerfilesCuentaLocal,
    CuentaLocal,
)
from identidad.perfiles_usuarios import (
    PERFILES_CATALOGO,
    PERFILES_POR_CLAVE,
    cambiar_perfiles_cuenta,
    generar_referencia_perfiles,
)
from identidad.services import GROUP_CAPABILITIES, Actor, resolve_actor


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
    user,
    capabilities: frozenset[str] = frozenset({"identidad.administrar_cuentas"}),
) -> Actor:
    return Actor(
        subject_id=user.pk,
        capabilities=capabilities,
        email_registrado=user.email,
    )


def test_catalogo_exacto_14_roles_sin_exponer_demo():
    assert len(PERFILES_CATALOGO) == 14
    grupos_catalogo = {p.grupo for p in PERFILES_CATALOGO}
    assert len(grupos_catalogo) == 14
    assert grupos_catalogo.issubset(set(GROUP_CAPABILITIES))
    assert "demo_solicitante" not in grupos_catalogo
    assert "demo_facturacion_solicitante" not in grupos_catalogo

    for perfil in PERFILES_CATALOGO:
        assert "demo_" not in perfil.nombre.lower()
        assert "demo_" not in perfil.descripcion.lower()
        assert "demo_" not in perfil.clave.lower()
        assert PERFILES_POR_CLAVE[perfil.clave] == perfil


@pytest.mark.django_db
def test_exige_capacidad_antes_de_consultar(django_assert_num_queries):
    cuenta, _ = _crear_cuenta_local(username="obj_cap", email="obj_cap@example.org")
    ref = generar_referencia_perfiles(cuenta)
    actor_sin_permiso = Actor(
        subject_id=cuenta.user_id, capabilities=frozenset({"gastos.presentar"})
    )

    with django_assert_num_queries(0):
        with pytest.raises(PermissionDenied):
            cambiar_perfiles_cuenta(None, cuenta.pk, ["solicitante"], "Motivo válido", ref)

    with django_assert_num_queries(0):
        with pytest.raises(PermissionDenied):
            cambiar_perfiles_cuenta(
                actor_sin_permiso, cuenta.pk, ["solicitante"], "Motivo válido", ref
            )


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
def test_revalidacion_actor_rechaza_no_habilitados_y_staff_implicito(
    kwargs_actor, con_cuenta_local
):
    objetivo, _ = _crear_cuenta_local(username="obj_auth", email="obj_auth@example.org")
    ref = generar_referencia_perfiles(objetivo)
    user_model = get_user_model()

    if con_cuenta_local:
        cuenta_actor, _ = _crear_cuenta_local(
            username="actor_inv",
            email="actor_inv@example.org",
            **kwargs_actor,
        )
        actor_user = cuenta_actor.user
    else:
        actor_user = user_model.objects.create_user(
            username="actor_sin_cuenta",
            email="actor_sin_cuenta@example.org",
            password=secrets.token_urlsafe(12),
            is_staff=kwargs_actor.get("is_staff", False),
            is_superuser=kwargs_actor.get("is_superuser", False),
        )
        for nombre_grupo in kwargs_actor.get("grupos", ()):
            grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
            actor_user.groups.add(grupo)

    with pytest.raises(PermissionDenied):
        cambiar_perfiles_cuenta(
            _actor_desde_user(actor_user),
            objetivo.pk,
            ["solicitante"],
            "Intento no autorizado",
            ref,
        )

    assert CambioPerfilesCuentaLocal.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "seleccion_invalida",
    [
        "solicitante",
        123,
        None,
        {"solicitante": True},
        [123],
        ["solicitante", "solicitante"],
        ["perfil_inexistente"],
        ["demo_solicitante"],
    ],
)
def test_valida_tipos_duplicados_y_claves_desconocidas_sin_500(
    seleccion_invalida, django_assert_num_queries
):
    admin, _ = _crear_cuenta_local(
        username="admin_val",
        email="admin_val@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(username="obj_val", email="obj_val@example.org")
    ref = generar_referencia_perfiles(objetivo)
    actor = _actor_desde_user(admin.user)

    with django_assert_num_queries(0):
        with pytest.raises(ValidationError):
            cambiar_perfiles_cuenta(actor, objetivo.pk, seleccion_invalida, "Motivo válido", ref)


@pytest.mark.django_db
@pytest.mark.parametrize("motivo_invalido", ["", "   ", "\n\t", None, 123, "x" * 2001])
def test_valida_motivo_obligatorio_y_limite(motivo_invalido):
    admin, _ = _crear_cuenta_local(
        username="admin_mot",
        email="admin_mot@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(username="obj_mot", email="obj_mot@example.org")
    ref = generar_referencia_perfiles(objetivo)
    actor = _actor_desde_user(admin.user)

    with pytest.raises(ValidationError):
        cambiar_perfiles_cuenta(actor, objetivo.pk, ["solicitante"], motivo_invalido, ref)


@pytest.mark.django_db
def test_prohibe_cambios_propios_y_permite_noop_identico():
    admin, _ = _crear_cuenta_local(
        username="admin_self",
        email="admin_self@example.org",
        grupos=("local_administracion",),
    )
    actor = _actor_desde_user(admin.user)
    ref = generar_referencia_perfiles(admin)

    with pytest.raises(ValidationError, match="propios perfiles"):
        cambiar_perfiles_cuenta(
            actor,
            admin.pk,
            ["administracion_cuentas", "solicitante"],
            "Autoasignación",
            ref,
        )

    cuenta, evento = cambiar_perfiles_cuenta(
        actor,
        admin.pk,
        ["administracion_cuentas"],
        "Sin cambios",
        ref,
    )
    assert evento is None
    assert list(cuenta.user.groups.values_list("name", flat=True)) == ["local_administracion"]


@pytest.mark.django_db
def test_conserva_grupos_ajenos_y_crea_grupos_faltantes_y_vacio_retira_gestionados():
    admin, _ = _crear_cuenta_local(
        username="admin_cons",
        email="admin_cons@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(
        username="obj_cons",
        email="obj_cons@example.org",
        grupos=(
            "local_solicitante",
            "demo_solicitante",
            "demo_facturacion_solicitante",
            "grupo_custom",
        ),
    )
    # Asegurar que demo_gastos_pago no existe previamente para probar get_or_create
    Group.objects.filter(name="demo_gastos_pago").delete()

    actor = _actor_desde_user(admin.user)
    ref1 = generar_referencia_perfiles(objetivo)

    cuenta1, ev1 = cambiar_perfiles_cuenta(
        actor,
        objetivo.pk,
        ["registro_pagos", "operacion_gastos"],
        "  Habilita pagos y operación  ",
        ref1,
    )
    assert ev1 is not None
    assert ev1.motivo == "Habilita pagos y operación"
    assert ev1.perfiles_anteriores == ["solicitante"]
    assert ev1.perfiles_nuevos == ["operacion_gastos", "registro_pagos"]

    grupos_tras_1 = set(cuenta1.user.groups.values_list("name", flat=True))
    assert grupos_tras_1 == {
        "demo_gastos_pago",
        "demo_operadora",
        "demo_solicitante",
        "demo_facturacion_solicitante",
        "grupo_custom",
    }

    # Selección vacía retira sólo los gestionados y conserva los ajenos
    ref2 = generar_referencia_perfiles(cuenta1)
    cuenta2, ev2 = cambiar_perfiles_cuenta(
        actor,
        objetivo.pk,
        [],
        "Retira perfiles gestionados",
        ref2,
    )
    assert ev2 is not None
    assert ev2.perfiles_anteriores == ["operacion_gastos", "registro_pagos"]
    assert ev2.perfiles_nuevos == []

    grupos_tras_2 = set(cuenta2.user.groups.values_list("name", flat=True))
    assert grupos_tras_2 == {"demo_solicitante", "demo_facturacion_solicitante", "grupo_custom"}


@pytest.mark.django_db
def test_estados_credenciales_y_nonce_intactos_y_pendiente_no_habilita(rf, settings):
    settings.LOCAL_IDENTITY_ENABLED = True
    admin, _ = _crear_cuenta_local(
        username="admin_prot",
        email="admin_prot@example.org",
        grupos=("local_administracion",),
    )
    pendiente, raw_password = _crear_cuenta_local(
        username="obj_pend",
        email="obj_pend@example.org",
        estado=CuentaLocal.Estado.PENDIENTE,
        verificada=False,
        grupos=(),
    )
    hash_original = pendiente.user.password
    nonce_original = pendiente.nonce_verificacion
    ref = generar_referencia_perfiles(pendiente)

    cuenta, evento = cambiar_perfiles_cuenta(
        _actor_desde_user(admin.user),
        pendiente.pk,
        ["administracion_cuentas", "solicitante"],
        "Asignación anticipada",
        ref,
    )
    assert evento is not None
    cuenta.refresh_from_db()
    cuenta.user.refresh_from_db()

    assert cuenta.estado == CuentaLocal.Estado.PENDIENTE
    assert cuenta.email_verificado_en is None
    assert cuenta.user.is_active is True
    assert cuenta.user.password == hash_original
    assert cuenta.nonce_verificacion == nonce_original
    assert authenticate(username="obj_pend", password=raw_password) == cuenta.user

    # Asignar perfil administrativo a cuenta pendiente NO la habilita como Actor
    req = rf.get("/")
    req.session = {}
    req.user = cuenta.user
    from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY

    req.session[SESSION_KEY] = str(cuenta.user.pk)
    req.session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    req.session[HASH_SESSION_KEY] = cuenta.user.get_session_auth_hash()
    assert resolve_actor(req) is None


@pytest.mark.django_db
def test_noop_doble_envio_y_referencias_invalidas_u_obsoletas():
    admin, _ = _crear_cuenta_local(
        username="admin_ref",
        email="admin_ref@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(
        username="obj_ref",
        email="obj_ref@example.org",
        grupos=("local_solicitante",),
    )
    otra, _ = _crear_cuenta_local(username="otra_ref", email="otra_ref@example.org")
    actor = _actor_desde_user(admin.user)

    ref_inicial = generar_referencia_perfiles(objetivo)
    ref_otra = generar_referencia_perfiles(otra)

    for ref_bad in ("", "   ", "firma-invalida", f"{ref_inicial}x", ref_otra):
        with pytest.raises(ValidationError):
            cambiar_perfiles_cuenta(actor, objetivo.pk, ["lectura_gastos"], "Motivo", ref_bad)

    # Cambio legítimo
    _, ev1 = cambiar_perfiles_cuenta(
        actor, objetivo.pk, ["lectura_gastos"], "Cambio 1", ref_inicial
    )
    assert ev1 is not None

    # Doble envío con la referencia anterior y mismo destino final -> no-op sin evento
    _, ev_doble = cambiar_perfiles_cuenta(
        actor, objetivo.pk, ["lectura_gastos"], "Reenvío", ref_inicial
    )
    assert ev_doble is None
    assert CambioPerfilesCuentaLocal.objects.count() == 1

    # Otro cambio con referencia obsoleta -> ValidationError
    with pytest.raises(ValidationError, match="cambiaron"):
        cambiar_perfiles_cuenta(actor, objetivo.pk, ["operacion_gastos"], "Cambio 2", ref_inicial)
    assert CambioPerfilesCuentaLocal.objects.count() == 1


@pytest.mark.django_db
def test_rollback_m2m_e_historia_si_falla_evento(monkeypatch):
    admin, _ = _crear_cuenta_local(
        username="admin_rb_perf",
        email="admin_rb_perf@example.org",
        grupos=("local_administracion",),
    )
    objetivo, _ = _crear_cuenta_local(
        username="obj_rb_perf",
        email="obj_rb_perf@example.org",
        grupos=("local_solicitante", "demo_solicitante"),
    )
    ref = generar_referencia_perfiles(objetivo)

    def _fallar_create(*args, **kwargs):
        raise RuntimeError("Fallo simulado al persistir historial de perfiles")

    monkeypatch.setattr(CambioPerfilesCuentaLocal.objects, "create", _fallar_create)

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        cambiar_perfiles_cuenta(
            _actor_desde_user(admin.user),
            objetivo.pk,
            ["operacion_gastos"],
            "Motivo rollback",
            ref,
        )

    objetivo.user.refresh_from_db()
    assert set(objetivo.user.groups.values_list("name", flat=True)) == {
        "local_solicitante",
        "demo_solicitante",
    }
    assert CambioPerfilesCuentaLocal.objects.count() == 0


@pytest.mark.django_db
def test_retirar_admin_bloqueado_si_es_ultimo_pero_conserva_si_otro_grupo_otorga_cap(monkeypatch):
    admin1, _ = _crear_cuenta_local(
        username="admin_ult_1",
        email="admin_ult_1@example.org",
        grupos=("local_administracion",),
    )
    admin2, _ = _crear_cuenta_local(
        username="admin_ult_2",
        email="admin_ult_2@example.org",
        grupos=("local_administracion", "grupo_admin_conservado"),
    )
    monkeypatch.setitem(
        GROUP_CAPABILITIES,
        "grupo_admin_conservado",
        frozenset({"identidad.administrar_cuentas"}),
    )

    ref2 = generar_referencia_perfiles(admin2)
    # Retirar administracion_cuentas de admin2 es válido porque conserva grupo_admin_conservado
    cuenta2, ev2 = cambiar_perfiles_cuenta(
        _actor_desde_user(admin1.user),
        admin2.pk,
        ["solicitante"],
        "Mantiene cap por grupo conservado",
        ref2,
    )
    assert ev2 is not None
    assert set(cuenta2.user.groups.values_list("name", flat=True)) == {
        "local_solicitante",
        "grupo_admin_conservado",
    }


@pytest.mark.django_db(transaction=True)
def test_carrera_dos_admins_retirandose_perfil_deja_un_admin():
    admin_a, _ = _crear_cuenta_local(
        username="perf_carrera_a",
        email="perf_carrera_a@example.org",
        grupos=("local_administracion",),
    )
    admin_b, _ = _crear_cuenta_local(
        username="perf_carrera_b",
        email="perf_carrera_b@example.org",
        grupos=("local_administracion",),
    )
    actor_a = _actor_desde_user(admin_a.user)
    actor_b = _actor_desde_user(admin_b.user)
    ref_b = generar_referencia_perfiles(admin_b)
    ref_a = generar_referencia_perfiles(admin_a)

    barrera = threading.Barrier(2, timeout=10)
    resultados: list[tuple[str, str]] = []
    lock_res = threading.Lock()

    def _trabajar(nombre: str, actor: Actor, target_id: int, ref: str) -> None:
        try:
            barrera.wait()
            cambiar_perfiles_cuenta(actor, target_id, ["solicitante"], f"Cruce {nombre}", ref)
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

    t1 = threading.Thread(target=_trabajar, args=("A->B", actor_a, admin_b.pk, ref_b))
    t2 = threading.Thread(target=_trabajar, args=("B->A", actor_b, admin_a.pk, ref_a))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert sorted(estado for _, estado in resultados) == ["ok", "permission_denied"]

    tiene_admin_a = admin_a.user.groups.filter(name="local_administracion").exists()
    tiene_admin_b = admin_b.user.groups.filter(name="local_administracion").exists()
    assert [tiene_admin_a, tiene_admin_b].count(True) == 1
    assert [tiene_admin_a, tiene_admin_b].count(False) == 1
    assert CambioPerfilesCuentaLocal.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_carrera_mixta_perfil_vs_actividad_deja_un_admin_habilitado():
    admin_a, _ = _crear_cuenta_local(
        username="mix_carrera_a",
        email="mix_carrera_a@example.org",
        grupos=("local_administracion",),
    )
    admin_b, _ = _crear_cuenta_local(
        username="mix_carrera_b",
        email="mix_carrera_b@example.org",
        grupos=("local_administracion",),
    )
    actor_a = _actor_desde_user(admin_a.user)
    actor_b = _actor_desde_user(admin_b.user)
    ref_b = generar_referencia_perfiles(admin_b)

    barrera = threading.Barrier(2, timeout=10)
    resultados: list[tuple[str, str]] = []
    lock_res = threading.Lock()

    def _retirar_perfil() -> None:
        try:
            barrera.wait()
            cambiar_perfiles_cuenta(actor_a, admin_b.pk, ["solicitante"], "Retira perfil B", ref_b)
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
            resultados.append(("perfil", estado))

    def _desactivar() -> None:
        try:
            barrera.wait()
            cambiar_actividad_cuenta(actor_b, admin_a.pk, False, "Desactiva A", True)
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
            resultados.append(("actividad", estado))

    t1 = threading.Thread(target=_retirar_perfil)
    t2 = threading.Thread(target=_desactivar)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert sorted(estado for _, estado in resultados) == ["ok", "permission_denied"]

    admin_a.user.refresh_from_db()
    admin_b.user.refresh_from_db()
    habilitado_a = (
        admin_a.user.is_active and admin_a.user.groups.filter(name="local_administracion").exists()
    )
    habilitado_b = (
        admin_b.user.is_active and admin_b.user.groups.filter(name="local_administracion").exists()
    )
    assert [habilitado_a, habilitado_b].count(True) == 1
    assert (
        CambioPerfilesCuentaLocal.objects.count() + CambioActividadCuentaLocal.objects.count()
    ) == 1
