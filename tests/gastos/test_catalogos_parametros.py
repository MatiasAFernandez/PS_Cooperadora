"""Pruebas para catálogos dinámicos y parámetros operativos de gastos (Issue #89)."""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from gastos.forms import CentroCostoForm, ParametrosATPForm
from gastos.models import CentroCosto, ParametroOperativo
from gastos.services import (
    CLAVE_PARAMETRO_ATP_BASE,
    VALOR_DEFECTO_ATP_ALICUOTA,
    VALOR_DEFECTO_ATP_BASE,
    actualizar_parametro_decimal,
    obtener_alicuota_atp,
    obtener_base_imponible_atp,
    obtener_parametro_decimal,
)
from tests.gastos.conftest import issue_csrf_credentials

User = get_user_model()


# ---------------------------------------------------------------------------
# Pruebas de Modelos
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_creacion_centro_costo_valido() -> None:
    """Verifica que un CentroCosto se crea con código y nombre y está activo por defecto."""
    centro = CentroCosto.objects.create(
        codigo="lab-quimica",
        nombre="Laboratorio de Química",
    )
    assert centro.pk is not None
    assert centro.codigo == "lab-quimica"
    assert centro.nombre == "Laboratorio de Química"
    assert centro.activo is True
    assert str(centro) == "Laboratorio de Química (lab-quimica)"


@pytest.mark.django_db
def test_centro_costo_codigo_unico() -> None:
    """Verifica la unicidad del código de centro de costo."""
    CentroCosto.objects.create(codigo="cátedra-isi", nombre="Cátedra ISI")
    with pytest.raises(IntegrityError):
        CentroCosto.objects.create(codigo="cátedra-isi", nombre="Otra Cátedra")


@pytest.mark.django_db
def test_centro_costo_baja_logica() -> None:
    """Verifica la baja lógica de un centro de costo sin eliminarlo de la base."""
    centro = CentroCosto.objects.create(codigo="curso-2025", nombre="Curso 2025", activo=True)
    centro.activo = False
    centro.save(update_fields=["activo"])

    recuperado = CentroCosto.objects.get(pk=centro.pk)
    assert recuperado.activo is False


@pytest.mark.django_db
def test_creacion_parametro_operativo_valido() -> None:
    """Verifica la creación y representación de un ParametroOperativo."""
    param = ParametroOperativo.objects.create(
        clave="TEST_PARAM",
        valor_decimal=Decimal("12345.67"),
        descripcion="Parámetro de prueba",
    )
    assert param.pk is not None
    assert param.clave == "TEST_PARAM"
    assert param.valor_decimal == Decimal("12345.67")
    assert "TEST_PARAM: 12345.67" in str(param)


@pytest.mark.django_db
def test_parametro_operativo_clave_unica() -> None:
    """Verifica que no se admiten claves duplicadas en ParametroOperativo."""
    ParametroOperativo.objects.create(clave="CLAVE_DUPLICADA", valor_decimal=Decimal("10.00"))
    with pytest.raises(IntegrityError):
        ParametroOperativo.objects.create(clave="CLAVE_DUPLICADA", valor_decimal=Decimal("20.00"))


@pytest.mark.django_db
def test_parametro_operativo_modificado_por_opcional() -> None:
    """Garantiza que modificado_por puede ser nulo para no exigir usuarios obligatorios."""
    param = ParametroOperativo.objects.create(
        clave="SIN_USUARIO",
        valor_decimal=Decimal("50.00"),
        modificado_por=None,
    )
    assert param.modificado_por is None


# ---------------------------------------------------------------------------
# Pruebas de Servicios y Fallback Determinista
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_obtener_parametro_decimal_fallback() -> None:
    """Verifica que con la tabla vacía se retorna el valor por defecto sin excepciones."""
    assert ParametroOperativo.objects.count() == 0
    valor = obtener_parametro_decimal("PARAM_INEXISTENTE", Decimal("999.99"))
    assert valor == Decimal("999.99")


@pytest.mark.django_db
def test_obtener_parametro_decimal_existente() -> None:
    """Verifica que si existe el registro, retorna el valor persistido."""
    ParametroOperativo.objects.create(clave="PARAM_EXISTE", valor_decimal=Decimal("1500.50"))
    valor = obtener_parametro_decimal("PARAM_EXISTE", Decimal("999.99"))
    assert valor == Decimal("1500.50")


@pytest.mark.django_db
def test_obtener_base_imponible_atp_defaults() -> None:
    """Verifica los valores por defecto de retención ATP según SPEC-019."""
    assert obtener_base_imponible_atp() == VALOR_DEFECTO_ATP_BASE
    assert obtener_alicuota_atp() == VALOR_DEFECTO_ATP_ALICUOTA


@pytest.mark.django_db
def test_actualizar_parametro_decimal(demo_accounts: tuple[dict[str, Any], str]) -> None:
    """Verifica la creación y actualización atómica de parámetros con registro del actor."""
    accounts, _ = demo_accounts
    operador = accounts["demo_o"]

    # 1. Crear nuevo
    param = actualizar_parametro_decimal(
        clave=CLAVE_PARAMETRO_ATP_BASE,
        valor=Decimal("120000.00"),
        actor=operador,
        descripcion="Nueva base ATP",
    )
    assert param.valor_decimal == Decimal("120000.00")
    assert param.modificado_por_id == operador.pk
    assert obtener_base_imponible_atp() == Decimal("120000.00")

    # 2. Actualizar existente
    param2 = actualizar_parametro_decimal(
        clave=CLAVE_PARAMETRO_ATP_BASE,
        valor=Decimal("150000.00"),
        actor=operador,
        descripcion="Actualización base ATP",
    )
    assert param2.pk == param.pk
    assert param2.valor_decimal == Decimal("150000.00")
    assert obtener_base_imponible_atp() == Decimal("150000.00")


# ---------------------------------------------------------------------------
# Pruebas de Formularios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_centro_costo_form_validacion() -> None:
    """Verifica validación y normalización en CentroCostoForm."""
    form_valido = CentroCostoForm(
        data={"codigo": "LAB-QUIMICA", "nombre": "  Química  ", "activo": True}
    )
    assert form_valido.is_valid()
    assert form_valido.cleaned_data["codigo"] == "lab-quimica"
    assert form_valido.cleaned_data["nombre"] == "Química"

    form_vacio = CentroCostoForm(data={"codigo": "", "nombre": ""})
    assert not form_vacio.is_valid()
    assert "codigo" in form_vacio.errors
    assert "nombre" in form_vacio.errors


def test_parametros_atp_form_validacion() -> None:
    """Verifica validación de rangos y valores en ParametrosATPForm."""
    form_valido = ParametrosATPForm(data={"base_imponible_atp": "95000.00", "alicuota_atp": "4.00"})
    assert form_valido.is_valid()
    assert form_valido.cleaned_data["base_imponible_atp"] == Decimal("95000.00")
    assert form_valido.cleaned_data["alicuota_atp"] == Decimal("4.00")

    form_negativo = ParametrosATPForm(data={"base_imponible_atp": "-100", "alicuota_atp": "120"})
    assert not form_negativo.is_valid()
    assert "base_imponible_atp" in form_negativo.errors
    assert "alicuota_atp" in form_negativo.errors


# ---------------------------------------------------------------------------
# Pruebas de Vistas y Permisos
# ---------------------------------------------------------------------------


@pytest.fixture
def grupo_pago(db: Any) -> Group:
    """Grupo con capacidad gastos.registrar_pago."""
    grupo, _ = Group.objects.get_or_create(name="demo_gastos_pago")
    return grupo


@pytest.mark.django_db
def test_gestion_catalogos_permisos(
    client: Client,
    demo_accounts: tuple[dict[str, Any], str],
    grupo_pago: Group,
) -> None:
    """Verifica denegaciones y accesos a la vista de administración de catálogos."""
    accounts, password = demo_accounts
    url = reverse("gastos:gestion_catalogos")

    # 1. Anónimo -> redirige al acceso de demo
    resp_anon = client.get(url)
    assert resp_anon.status_code == 302

    # 2. Solicitante común (demo_a) -> 403 Forbidden
    client.login(username="demo_a", password=password)
    resp_solicitante = client.get(url)
    assert resp_solicitante.status_code == 403

    # 3. Lector global (demo_l) -> 403 Forbidden
    client.login(username="demo_l", password=password)
    resp_lector = client.get(url)
    assert resp_lector.status_code == 403

    # 4. Operadora (demo_o, gastos.decidir) -> 200 OK
    client.login(username="demo_o", password=password)
    resp_operadora = client.get(url)
    assert resp_operadora.status_code == 200
    assert "Parámetros de Retención ATP" in resp_operadora.content.decode("utf-8")

    # 5. Usuario con gastos.registrar_pago -> 200 OK
    user_pago = User.objects.create_user(username="pagador", password=password)
    user_pago.groups.add(grupo_pago)
    client.login(username="pagador", password=password)
    resp_pagador = client.get(url)
    assert resp_pagador.status_code == 200


@pytest.mark.django_db
def test_gestion_catalogos_crear_centro_post(
    client: Client,
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """Verifica la creación exitosa de un CentroCosto mediante POST."""
    accounts, password = demo_accounts
    client.login(username="demo_o", password=password)
    url = reverse("gastos:gestion_catalogos")

    csrf_token = issue_csrf_credentials(client)
    post_data = {
        "csrfmiddlewaretoken": csrf_token,
        "action": "crear_centro",
        "codigo": "lab-sistemas",
        "nombre": "Laboratorio de Sistemas",
        "activo": "on",
    }
    resp = client.post(url, data=post_data)
    assert resp.status_code == 302
    assert resp.url == url

    centro = CentroCosto.objects.get(codigo="lab-sistemas")
    assert centro.nombre == "Laboratorio de Sistemas"
    assert centro.activo is True


@pytest.mark.django_db
def test_gestion_catalogos_actualizar_atp_post(
    client: Client,
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """Verifica la actualización de los parámetros de retención ATP mediante POST."""
    accounts, password = demo_accounts
    client.login(username="demo_o", password=password)
    url = reverse("gastos:gestion_catalogos")

    csrf_token = issue_csrf_credentials(client)
    post_data = {
        "csrfmiddlewaretoken": csrf_token,
        "action": "actualizar_atp",
        "base_imponible_atp": "110000.00",
        "alicuota_atp": "4.50",
    }
    resp = client.post(url, data=post_data)
    assert resp.status_code == 302
    assert resp.url == url

    assert obtener_base_imponible_atp() == Decimal("110000.00")
    assert obtener_alicuota_atp() == Decimal("4.50")


@pytest.mark.django_db
def test_centro_costo_toggle_activo(
    client: Client,
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """Verifica activar/desactivar un centro de costo mediante toggle."""
    accounts, password = demo_accounts
    centro = CentroCosto.objects.create(
        codigo="lab-redes", nombre="Laboratorio de Redes", activo=True
    )
    toggle_url = reverse("gastos:centro_costo_toggle", kwargs={"pk": centro.pk})

    # GET no permitido
    client.login(username="demo_o", password=password)
    resp_get = client.get(toggle_url)
    assert resp_get.status_code == 405

    # POST desactiva
    csrf_token = issue_csrf_credentials(client)
    resp_post1 = client.post(toggle_url, data={"csrfmiddlewaretoken": csrf_token})
    assert resp_post1.status_code == 302
    centro.refresh_from_db()
    assert centro.activo is False

    # POST reactiva
    resp_post2 = client.post(toggle_url, data={"csrfmiddlewaretoken": csrf_token})
    assert resp_post2.status_code == 302
    centro.refresh_from_db()
    assert centro.activo is True
