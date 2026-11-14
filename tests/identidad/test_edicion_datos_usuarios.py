"""Pruebas de servicio y formulario para edición administrativa de datos locales (SPEC-024)."""

import secrets

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError

from identidad.datos_usuarios import editar_datos_cuenta, generar_referencia_edicion
from identidad.forms_usuarios import EdicionDatosCuentaForm
from identidad.models import CambioDatosCuentaLocal, CuentaLocal
from identidad.services import Actor


def _crear_cuenta(
    *,
    username: str = "usuaria_local",
    email: str = "usuaria@example.org",
    nombre_completo: str = "Ana García",
    area_habitual: str = "Tesorería",
    cuit_cuil: str = "27-12345678-9",
    legajo: str = "L-100",
    estado: str = CuentaLocal.Estado.APROBADA,
) -> CuentaLocal:
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=username,
        email=email,
        password=secrets.token_urlsafe(16),
        first_name="Legado",
        last_name="SinTocar",
        is_active=True,
    )
    return CuentaLocal.objects.create(
        user=user,
        email=email,
        nombre_completo=nombre_completo,
        area_habitual=area_habitual,
        cuit_cuil=cuit_cuil,
        legajo=legajo,
        estado=estado,
    )


def _crear_actor_admin(*, username: str = "admin_local") -> tuple[Actor, object]:
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=username,
        email=f"{username}@example.org",
        password=secrets.token_urlsafe(16),
    )
    actor = Actor(
        subject_id=user.pk,
        capabilities=frozenset({"identidad.administrar_cuentas"}),
        email_registrado=user.email,
    )
    return actor, user


@pytest.mark.django_db
def test_editar_datos_cuenta_guarda_y_registra_evento_exacto():
    cuenta = _crear_cuenta()
    actor, admin_user = _crear_actor_admin()
    referencia = generar_referencia_edicion(cuenta)

    cuenta_actualizada, evento = editar_datos_cuenta(
        actor,
        cuenta.pk,
        {
            "nombre_completo": "  Ana María García  ",
            "area_habitual": "  Tesorería  ",
            "cuit_cuil": "27-99887766-1",
            "legajo": "",
        },
        referencia,
    )

    assert evento is not None
    cuenta_actualizada.refresh_from_db()
    cuenta_actualizada.user.refresh_from_db()

    assert cuenta_actualizada.nombre_completo == "Ana María García"
    assert cuenta_actualizada.area_habitual == "Tesorería"
    assert cuenta_actualizada.cuit_cuil == "27-99887766-1"
    assert cuenta_actualizada.legajo == ""

    # User legado permanece intacto
    assert cuenta_actualizada.user.first_name == "Legado"
    assert cuenta_actualizada.user.last_name == "SinTocar"

    assert evento.cuenta_id == cuenta.pk
    assert evento.autor_id == admin_user.pk
    assert evento.cambios == {
        "nombre_completo": {"anterior": "Ana García", "nuevo": "Ana María García"},
        "cuit_cuil": {"anterior": "27-12345678-9", "nuevo": "27-99887766-1"},
        "legajo": {"anterior": "L-100", "nuevo": ""},
    }
    assert "area_habitual" not in evento.cambios


@pytest.mark.django_db
def test_editar_datos_cuenta_noop_no_crea_evento():
    cuenta = _crear_cuenta()
    actor, _ = _crear_actor_admin()
    referencia = generar_referencia_edicion(cuenta)

    cuenta_res, evento = editar_datos_cuenta(
        actor,
        cuenta.pk,
        {
            "nombre_completo": "  Ana García ",
            "area_habitual": "Tesorería",
            "cuit_cuil": "27-12345678-9",
            "legajo": "L-100",
        },
        referencia,
    )

    assert cuenta_res.pk == cuenta.pk
    assert evento is None
    assert CambioDatosCuentaLocal.objects.count() == 0


@pytest.mark.django_db
def test_editar_datos_cuenta_ordena_historial_descendente():
    cuenta = _crear_cuenta()
    actor, _ = _crear_actor_admin()

    ref1 = generar_referencia_edicion(cuenta)
    cuenta, ev1 = editar_datos_cuenta(
        actor,
        cuenta.pk,
        {
            "nombre_completo": "Ana Uno",
            "area_habitual": cuenta.area_habitual,
            "cuit_cuil": cuenta.cuit_cuil,
            "legajo": cuenta.legajo,
        },
        ref1,
    )

    ref2 = generar_referencia_edicion(cuenta)
    _, ev2 = editar_datos_cuenta(
        actor,
        cuenta.pk,
        {
            "nombre_completo": "Ana Dos",
            "area_habitual": cuenta.area_habitual,
            "cuit_cuil": cuenta.cuit_cuil,
            "legajo": cuenta.legajo,
        },
        ref2,
    )

    assert ev1 is not None and ev2 is not None
    ids = list(cuenta.cambios_datos.values_list("pk", flat=True))
    assert ids == [ev2.pk, ev1.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("datos_invalidos", "campo_esperado"),
    [
        ({"nombre_completo": "   "}, "nombre_completo"),
        ({"nombre_completo": "x" * 151}, "nombre_completo"),
        ({"nombre_completo": "Ana", "area_habitual": "x" * 151}, "area_habitual"),
        ({"nombre_completo": "Ana", "cuit_cuil": "1" * 21}, "cuit_cuil"),
        ({"nombre_completo": "Ana", "legajo": "1" * 51}, "legajo"),
    ],
)
def test_editar_datos_cuenta_valida_longitudes_y_nombre_obligatorio(
    datos_invalidos, campo_esperado
):
    cuenta = _crear_cuenta()
    actor, _ = _crear_actor_admin()
    referencia = generar_referencia_edicion(cuenta)

    with pytest.raises(ValidationError) as exc_info:
        editar_datos_cuenta(actor, cuenta.pk, datos_invalidos, referencia)

    assert campo_esperado in exc_info.value.message_dict
    cuenta.refresh_from_db()
    assert cuenta.nombre_completo == "Ana García"
    assert CambioDatosCuentaLocal.objects.count() == 0


@pytest.mark.django_db
def test_editar_datos_cuenta_no_impone_checksum_cuit():
    cuenta = _crear_cuenta()
    actor, _ = _crear_actor_admin()
    referencia = generar_referencia_edicion(cuenta)

    cuenta_actualizada, evento = editar_datos_cuenta(
        actor,
        cuenta.pk,
        {
            "nombre_completo": "Ana García",
            "area_habitual": "",
            "cuit_cuil": "sin-checksum-123",
            "legajo": "",
        },
        referencia,
    )

    assert evento is not None
    assert cuenta_actualizada.cuit_cuil == "sin-checksum-123"


def test_editar_datos_cuenta_deniega_sin_capacidad_antes_de_consultar(monkeypatch):
    def _no_debe_consultar(*args, **kwargs):
        raise AssertionError("No debe consultar la base sin capacidad.")

    monkeypatch.setattr(CuentaLocal.objects, "select_for_update", _no_debe_consultar)

    actor_sin_permiso = Actor(
        subject_id=999,
        capabilities=frozenset({"gastos.decidir"}),
    )

    with pytest.raises(PermissionDenied):
        editar_datos_cuenta(None, 1, {"nombre_completo": "X"}, "ref")

    with pytest.raises(PermissionDenied):
        editar_datos_cuenta(actor_sin_permiso, 1, {"nombre_completo": "X"}, "ref")


@pytest.mark.django_db
def test_editar_datos_cuenta_deja_campos_protegidos_intactos():
    cuenta = _crear_cuenta()
    actor, _ = _crear_actor_admin()
    referencia = generar_referencia_edicion(cuenta)
    grupo = Group.objects.create(name="demo_solicitante")
    cuenta.user.groups.add(grupo)

    password_original = cuenta.user.password
    nonce_original = cuenta.nonce_verificacion

    datos_entrada = {
        "nombre_completo": "Ana Editada",
        "area_habitual": "Secretaría",
        "cuit_cuil": "27-00000000-0",
        "legajo": "L-200",
        "email": "otro@example.org",
        "password": "hacked",
        "estado": CuentaLocal.Estado.RECHAZADA,
        "nonce_verificacion": "00000000-0000-0000-0000-000000000000",
        "is_active": False,
        "groups": [],
    }

    cuenta_actualizada, evento = editar_datos_cuenta(
        actor, cuenta.pk, datos_entrada, referencia
    )

    cuenta_actualizada.refresh_from_db()
    cuenta_actualizada.user.refresh_from_db()

    assert evento is not None
    assert "email" not in evento.cambios
    assert "estado" not in evento.cambios
    assert cuenta_actualizada.email == "usuaria@example.org"
    assert cuenta_actualizada.estado == CuentaLocal.Estado.APROBADA
    assert cuenta_actualizada.nonce_verificacion == nonce_original
    assert cuenta_actualizada.user.email == "usuaria@example.org"
    assert cuenta_actualizada.user.password == password_original
    assert cuenta_actualizada.user.is_active is True
    assert list(cuenta_actualizada.user.groups.values_list("name", flat=True)) == [
        "demo_solicitante"
    ]
    # No muta el dict de entrada
    assert "email" in datos_entrada


@pytest.mark.django_db
def test_editar_datos_cuenta_rechaza_referencia_invalida_u_obsoleta():
    cuenta = _crear_cuenta()
    otra_cuenta = _crear_cuenta(username="otra", email="otra@example.org")
    actor, _ = _crear_actor_admin()

    # Firma inválida
    with pytest.raises(ValidationError):
        editar_datos_cuenta(
            actor,
            cuenta.pk,
            {"nombre_completo": "Nuevo Nombre"},
            "firma-invalida",
        )

    # Referencia de otra cuenta
    ref_otra = generar_referencia_edicion(otra_cuenta)
    with pytest.raises(ValidationError):
        editar_datos_cuenta(
            actor,
            cuenta.pk,
            {"nombre_completo": "Nuevo Nombre"},
            ref_otra,
        )

    # Referencia obsoleta por cambio concurrente
    ref_vieja = generar_referencia_edicion(cuenta)
    editar_datos_cuenta(
        actor,
        cuenta.pk,
        {
            "nombre_completo": "Cambio Concurrente",
            "area_habitual": cuenta.area_habitual,
            "cuit_cuil": cuenta.cuit_cuil,
            "legajo": cuenta.legajo,
        },
        ref_vieja,
    )

    with pytest.raises(ValidationError) as exc_info:
        editar_datos_cuenta(
            actor,
            cuenta.pk,
            {"nombre_completo": "Sobrescritura Obsoleta"},
            ref_vieja,
        )

    assert "cambiaron" in " ".join(exc_info.value.messages).lower()
    cuenta.refresh_from_db()
    assert cuenta.nombre_completo == "Cambio Concurrente"
    assert CambioDatosCuentaLocal.objects.count() == 1


@pytest.mark.django_db
def test_editar_datos_cuenta_hace_rollback_si_falla_evento(monkeypatch):
    cuenta = _crear_cuenta()
    actor, _ = _crear_actor_admin()
    referencia = generar_referencia_edicion(cuenta)

    def _fallar_evento(*args, **kwargs):
        raise RuntimeError("Fallo simulado al registrar evento")

    monkeypatch.setattr(CambioDatosCuentaLocal.objects, "create", _fallar_evento)

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        editar_datos_cuenta(
            actor,
            cuenta.pk,
            {
                "nombre_completo": "Nombre Revertido",
                "area_habitual": "Área Revertida",
                "cuit_cuil": cuenta.cuit_cuil,
                "legajo": cuenta.legajo,
            },
            referencia,
        )

    cuenta.refresh_from_db()
    assert cuenta.nombre_completo == "Ana García"
    assert cuenta.area_habitual == "Tesorería"
    assert CambioDatosCuentaLocal.objects.count() == 0


@pytest.mark.django_db
def test_edicion_datos_cuenta_form_whitelist_strip_y_conserva_referencia():
    cuenta = _crear_cuenta()
    form_inicial = EdicionDatosCuentaForm(instance=cuenta)

    assert list(form_inicial.fields.keys()) == [
        "nombre_completo",
        "area_habitual",
        "cuit_cuil",
        "legajo",
        "referencia",
    ]
    assert form_inicial.fields["referencia"].widget.is_hidden
    referencia_inicial = form_inicial.fields["referencia"].initial
    assert isinstance(referencia_inicial, str) and len(referencia_inicial) > 0

    # En POST inválido conserva la referencia enviada, sin regenerarla silenciosamente
    form_invalido = EdicionDatosCuentaForm(
        data={
            "nombre_completo": "   ",
            "area_habitual": "  Compras  ",
            "cuit_cuil": "",
            "legajo": "",
            "referencia": "ref-original-post",
        },
        instance=cuenta,
    )
    assert not form_invalido.is_valid()
    assert "nombre_completo" in form_invalido.errors
    assert form_invalido.data["referencia"] == "ref-original-post"
    assert form_invalido["referencia"].value() == "ref-original-post"

    # En POST válido hace strip y conserva referencia
    form_valido = EdicionDatosCuentaForm(
        data={
            "nombre_completo": "  Ana Nueva  ",
            "area_habitual": "  Compras  ",
            "cuit_cuil": "  20-11111111-2 ",
            "legajo": "  L-9  ",
            "referencia": referencia_inicial,
            "email": "ignorado@example.org",
        },
        instance=cuenta,
    )
    assert form_valido.is_valid()
    assert form_valido.cleaned_data["nombre_completo"] == "Ana Nueva"
    assert form_valido.cleaned_data["area_habitual"] == "Compras"
    assert form_valido.cleaned_data["cuit_cuil"] == "20-11111111-2"
    assert form_valido.cleaned_data["legajo"] == "L-9"
    assert form_valido.cleaned_data["referencia"] == referencia_inicial
    assert "email" not in form_valido.cleaned_data
