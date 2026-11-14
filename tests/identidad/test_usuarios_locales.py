"""Pruebas HTTP de la consulta administrativa de usuarios locales (SPEC-023)."""

import urllib.parse

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from identidad.models import CuentaLocal

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
    estado=CuentaLocal.Estado.APROBADA,
    verificado=True,
    activo=True,
    area="",
    grupos=(),
    decidida_por=None,
):
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password=CLAVE,
        is_active=activo,
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
        decidida_por=decidida_por,
    )


@pytest.fixture
def grupo_administracion(db):
    return Group.objects.create(name="local_administracion")


@pytest.fixture
def admin(grupo_administracion):
    return _crear_cuenta(
        "Admin Local",
        "admin.usuarios@example.invalid",
        area="Administración",
        grupos=(grupo_administracion,),
    )


@pytest.fixture
def admin_client(admin):
    cliente = Client()
    cliente.force_login(admin.user)
    return cliente


@pytest.fixture
def grupo_solicitante(db):
    return Group.objects.create(name="local_solicitante")


@pytest.fixture
def solicitante(grupo_solicitante):
    return _crear_cuenta(
        "Solicitante Local",
        "solicitante.usuarios@example.invalid",
        area="Compras",
        grupos=(grupo_solicitante,),
    )


@pytest.fixture
def cliente_solicitante(solicitante):
    cliente = Client()
    cliente.force_login(solicitante.user)
    return cliente


@pytest.fixture
def staff_sin_capacidad(db):
    cuenta = _crear_cuenta("Staff Sin Capacidad", "staff.usuarios@example.invalid")
    cuenta.user.is_staff = True
    cuenta.user.save(update_fields=["is_staff"])
    return cuenta


@pytest.fixture
def superusuario_sin_capacidad(db):
    cuenta = _crear_cuenta("Superusuario Sin Capacidad", "super.usuarios@example.invalid")
    cuenta.user.is_staff = True
    cuenta.user.is_superuser = True
    cuenta.user.save(update_fields=["is_staff", "is_superuser"])
    return cuenta


def test_administrador_lee_listado_y_ficha(admin, admin_client, solicitante):
    otra = _crear_cuenta("Beatriz Consultada", "beatriz.usuarios@example.invalid")

    listado = admin_client.get(reverse("cuentas:usuarios"))
    assert listado.status_code == 200
    assert listado.context["actor"].subject_id == admin.user_id
    assert listado.context["acceso_local"] is True
    assert listado.context["total"] == 3
    nombres = [cuenta.nombre_completo for cuenta in listado.context["cuentas"]]
    assert nombres == sorted(nombres)
    assert "no-store" in listado.headers["Cache-Control"]
    html_listado = listado.content.decode()
    assert "Beatriz Consultada" in html_listado
    assert "beatriz.usuarios@example.invalid" in html_listado
    assert CLAVE not in html_listado
    assert str(otra.nonce_verificacion) not in html_listado

    ficha = admin_client.get(reverse("cuentas:usuario_detalle", args=[otra.pk]))
    assert ficha.status_code == 200
    assert ficha.context["cuenta"].pk == otra.pk
    assert ficha.context["actor"].subject_id == admin.user_id
    assert ficha.context["acceso_local"] is True
    assert "no-store" in ficha.headers["Cache-Control"]
    html_ficha = ficha.content.decode()
    assert "Beatriz Consultada" in html_ficha
    assert "beatriz.usuarios@example.invalid" in html_ficha
    assert CLAVE not in html_ficha
    assert str(otra.nonce_verificacion) not in html_ficha


def test_sin_capacidad_no_consulta_ni_siquiera_objetos_inexistentes(
    solicitante,
    cliente_solicitante,
    staff_sin_capacidad,
    superusuario_sin_capacidad,
):
    cliente_staff = Client()
    cliente_staff.force_login(staff_sin_capacidad.user)
    cliente_super = Client()
    cliente_super.force_login(superusuario_sin_capacidad.user)

    for cliente in (Client(), cliente_solicitante, cliente_staff, cliente_super):
        assert cliente.get(reverse("cuentas:usuarios")).status_code == 403
        ficha = reverse("cuentas:usuario_detalle", args=[solicitante.pk])
        assert cliente.get(ficha).status_code == 403
        inexistente = reverse("cuentas:usuario_detalle", args=[999999])
        assert cliente.get(inexistente).status_code == 403


def test_objeto_ajeno_lo_consulta_admin_pero_no_el_solicitante(
    admin_client, solicitante, cliente_solicitante
):
    ficha = reverse("cuentas:usuario_detalle", args=[solicitante.pk])
    assert admin_client.get(ficha).status_code == 200
    assert cliente_solicitante.get(ficha).status_code == 403


def test_flag_local_apagada_da_404(admin, admin_client, settings):
    settings.LOCAL_IDENTITY_ENABLED = False
    assert admin_client.get(reverse("cuentas:usuarios")).status_code == 404
    ficha = reverse("cuentas:usuario_detalle", args=[admin.pk])
    assert admin_client.get(ficha).status_code == 404


def test_ficha_inexistente_da_404_tras_autorizar(admin_client):
    ficha = reverse("cuentas:usuario_detalle", args=[999999])
    assert admin_client.get(ficha).status_code == 404


def test_filtros_combinados_e_invalidos(admin_client):
    objetivo = _crear_cuenta(
        "Ana Compradora",
        "ana.compras@example.invalid",
        area="Compras",
        estado=CuentaLocal.Estado.APROBADA,
        verificado=True,
        activo=True,
    )
    _crear_cuenta(
        "Ana Rechazada",
        "ana.rechazada@example.invalid",
        area="Compras",
        estado=CuentaLocal.Estado.RECHAZADA,
        verificado=True,
        activo=True,
    )
    _crear_cuenta(
        "Ana Sin Correo",
        "ana.sin-correo@example.invalid",
        area="Compras",
        estado=CuentaLocal.Estado.APROBADA,
        verificado=False,
        activo=True,
    )
    _crear_cuenta(
        "Ana Inactiva",
        "ana.inactiva@example.invalid",
        area="Compras",
        estado=CuentaLocal.Estado.APROBADA,
        verificado=True,
        activo=False,
    )

    combinado = admin_client.get(
        reverse("cuentas:usuarios"),
        {
            "q": "ana",
            "estado": CuentaLocal.Estado.APROBADA,
            "verificado": "si",
            "actividad": "activa",
        },
    )
    assert combinado.status_code == 200
    assert combinado.context["total"] == 1
    assert [cuenta.pk for cuenta in combinado.context["cuentas"]] == [objetivo.pk]

    por_estado = admin_client.get(
        reverse("cuentas:usuarios"), {"estado": CuentaLocal.Estado.RECHAZADA}
    )
    assert por_estado.context["total"] == 1
    assert por_estado.context["cuentas"][0].estado == CuentaLocal.Estado.RECHAZADA

    por_area = admin_client.get(reverse("cuentas:usuarios"), {"q": "Compras"})
    assert por_area.context["total"] == 4

    sin_correo = admin_client.get(reverse("cuentas:usuarios"), {"verificado": "no"})
    assert [cuenta.nombre_completo for cuenta in sin_correo.context["cuentas"]] == [
        "Ana Sin Correo"
    ]

    inactiva = admin_client.get(reverse("cuentas:usuarios"), {"actividad": "inactiva"})
    assert [cuenta.nombre_completo for cuenta in inactiva.context["cuentas"]] == [
        "Ana Inactiva"
    ]

    invalido = admin_client.get(reverse("cuentas:usuarios"), {"estado": "INVALIDO"})
    assert invalido.status_code == 400
    assert "estado" in invalido.context["form"].errors
    assert invalido.context["total"] == 0
    assert list(invalido.context["cuentas"]) == []
    assert "no-store" in invalido.headers["Cache-Control"]

    extenso = admin_client.get(reverse("cuentas:usuarios"), {"q": "x" * 151})
    assert extenso.status_code == 400
    assert "q" in extenso.context["form"].errors
    assert extenso.context["total"] == 0


def test_paginacion_orden_y_conservacion_de_filtros(admin_client):
    for numero in range(26, 0, -1):
        _crear_cuenta(
            f"Persona {numero:02d}",
            f"paginacion{numero:02d}@example.invalid",
            area="Paginación",
        )

    listado = reverse("cuentas:usuarios")
    primera = admin_client.get(listado, {"q": "Paginación"})
    assert primera.status_code == 200
    assert primera.context["total"] == 26
    assert len(primera.context["cuentas"]) == 25
    assert [cuenta.nombre_completo for cuenta in primera.context["cuentas"]] == [
        f"Persona {numero:02d}" for numero in range(1, 26)
    ]
    filtros = urllib.parse.parse_qs(primera.context["filtros_query"])
    assert filtros == {"q": ["Paginación"]}

    segunda = admin_client.get(listado, {"q": "Paginación", "page": 2})
    assert segunda.status_code == 200
    assert segunda.context["total"] == 26
    assert [cuenta.nombre_completo for cuenta in segunda.context["cuentas"]] == ["Persona 26"]
    conservado = urllib.parse.parse_qs(segunda.context["listado_query"])
    assert conservado == {"q": ["Paginación"], "page": ["2"]}


def test_detalle_normaliza_listado_query_y_descarta_next(admin_client, solicitante):
    ficha = reverse("cuentas:usuario_detalle", args=[solicitante.pk])
    consulta = urllib.parse.urlencode(
        {
            "q": "<b>ana</b>",
            "estado": CuentaLocal.Estado.APROBADA,
            "page": "2",
            "next": "https://externo.invalid/",
        }
    )
    respuesta = admin_client.get(f"{ficha}?{consulta}")
    assert respuesta.status_code == 200
    normalizado = urllib.parse.parse_qs(respuesta.context["listado_query"])
    assert normalizado == {
        "q": ["<b>ana</b>"],
        "estado": [CuentaLocal.Estado.APROBADA],
        "page": ["2"],
    }
    assert "next" not in respuesta.context["listado_query"]
    assert "externo.invalid" not in respuesta.context["listado_query"]

    sin_pagina = admin_client.get(f"{ficha}?page=cero")
    assert sin_pagina.status_code == 200
    assert "page" not in urllib.parse.parse_qs(sin_pagina.context["listado_query"])


def test_post_no_admitido_y_datos_intactos(admin_client, solicitante):
    antes = list(
        CuentaLocal.objects.order_by("pk").values_list("pk", "nombre_completo", "estado")
    )
    listado = reverse("cuentas:usuarios")
    ficha = reverse("cuentas:usuario_detalle", args=[solicitante.pk])
    assert admin_client.post(listado).status_code == 405
    assert admin_client.post(ficha).status_code == 405
    despues = list(
        CuentaLocal.objects.order_by("pk").values_list("pk", "nombre_completo", "estado")
    )
    assert despues == antes
