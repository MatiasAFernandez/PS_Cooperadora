"""Búsqueda de concepto combinada con estado, acceso y conservación de datos."""

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from gastos.models import DecisionGasto, SolicitudGasto
from gastos.services import decide_expense
from identidad.services import Actor

pytestmark = pytest.mark.django_db


@pytest.fixture
def gastos_busqueda(demo_accounts: Any) -> dict[str, SolicitudGasto]:
    accounts, _ = demo_accounts
    ejemplos = {
        "a_presentada": ("demo_a", "presentada", "Insumos para laboratorio"),
        "a_aceptada": ("demo_a", "aceptada", "INSUMOS de oficina"),
        "a_rechazada": ("demo_a", "rechazada", "Mobiliario para oficina"),
        "b_aceptada": ("demo_b", "aceptada", "Insumos de depósito"),
        "b_presentada": ("demo_b", "presentada", "Concepto exclusivamente ajeno"),
    }
    return {
        name: SolicitudGasto.objects.create(
            solicitante=accounts[owner],
            estado=estado,
            concepto=concepto,
            monto_estimado="125.50",
            unidad_requirente="Unidad sintética",
        )
        for name, (owner, estado, concepto) in ejemplos.items()
    }


def _client(accounts: Any, username: str = "demo_a") -> Client:
    client = Client()
    client.force_login(accounts[username])
    return client


@pytest.mark.parametrize(
    "username,expected",
    [
        ("demo_a", {"a_presentada", "a_aceptada"}),
        ("demo_b", {"b_aceptada"}),
        ("demo_o", {"a_presentada", "a_aceptada", "b_aceptada"}),
        ("demo_l", {"a_presentada", "a_aceptada", "b_aceptada"}),
    ],
)
@pytest.mark.parametrize("estado", ["", "aceptada"])
def test_contenido_sin_distinguir_mayusculas_intersecta_estado_y_visibilidad(
    demo_accounts: Any, gastos_busqueda: Any, username: str, expected: set[str], estado: str
) -> None:
    accounts, _ = demo_accounts
    response = _client(accounts, username).get(
        reverse("gastos:lista"), {"q": "sUmOs", "estado": estado}
    )
    assert response.status_code == 200
    if estado:
        expected = {name for name in expected if gastos_busqueda[name].estado == estado}
    assert {s.pk for s in response.context["solicitudes"]} == {
        gastos_busqueda[name].pk for name in expected
    }
    content = response.content.decode()
    assert 'value="sUmOs"' in content
    if estado:
        assert '<option value="aceptada" selected>Aceptada</option>' in content
    assert '<a href="/gastos/">Quitar filtro</a>' in content


@pytest.mark.parametrize("q", ["", "   ", "  InSuMoS  "])
def test_espacios_y_texto_vacio_conservan_semantica_del_estado(
    demo_accounts: Any, gastos_busqueda: Any, q: str
) -> None:
    accounts, _ = demo_accounts
    response = _client(accounts).get(reverse("gastos:lista"), {"q": q, "estado": "aceptada"})
    assert list(response.context["solicitudes"]) == [gastos_busqueda["a_aceptada"]]
    assert response.context["filtro_form"].cleaned_data["q"] == q.strip()


def test_busqueda_sin_coincidencias_no_revela_gastos_ajenos(
    demo_accounts: Any, gastos_busqueda: Any
) -> None:
    accounts, _ = demo_accounts
    response = _client(accounts).get(reverse("gastos:lista"), {"q": "exclusivamente ajeno"})
    assert list(response.context["solicitudes"]) == []
    content = response.content.decode()
    assert "No se encontraron solicitudes visibles con el concepto buscado" in content
    assert gastos_busqueda["b_presentada"].concepto not in content


@pytest.mark.parametrize("query,expected", [("%", "literal_%"), ("_", "literal__")])
def test_porcentaje_y_guion_bajo_son_literales(
    demo_accounts: Any, gastos_busqueda: Any, query: str, expected: str
) -> None:
    accounts, _ = demo_accounts
    literals = {
        name: SolicitudGasto.objects.create(
            concepto=f"Referencia {character} literal",
            monto_estimado="10.00",
            unidad_requirente="Unidad sintética",
            solicitante=accounts["demo_a"],
        )
        for name, character in [("literal_%", "%"), ("literal__", "_")]
    }
    response = _client(accounts).get(reverse("gastos:lista"), {"q": query})
    assert list(response.context["solicitudes"]) == [literals[expected]]


@pytest.mark.parametrize("length,valid", [(255, True), (256, False)])
def test_limite_coincide_con_longitud_del_concepto(
    demo_accounts: Any, length: int, valid: bool
) -> None:
    accounts, _ = demo_accounts
    solicitud = SolicitudGasto.objects.create(
        concepto="x" * 255,
        monto_estimado="10.00",
        unidad_requirente="Unidad sintética",
        solicitante=accounts["demo_a"],
    )
    response = _client(accounts).get(reverse("gastos:lista"), {"q": "x" * length})
    assert response.status_code == 200
    if valid:
        assert list(response.context["solicitudes"]) == [solicitud]
    else:
        assert list(response.context["solicitudes"]) == []
        assert "q" in response.context["filtro_form"].errors
        content = response.content.decode()
        assert "Corrija el filtro" in content
        assert 'id="id_q_error"' in content
        assert "255" in content


def test_estado_invalido_no_se_ignora_aunque_el_texto_coincida(
    demo_accounts: Any, gastos_busqueda: Any
) -> None:
    accounts, _ = demo_accounts
    response = _client(accounts).get(
        reverse("gastos:lista"), {"q": "insumos", "estado": "invalido"}
    )
    assert list(response.context["solicitudes"]) == []
    assert "estado" in response.context["filtro_form"].errors


def test_parametro_repetido_usa_ultimo_valor_validado(
    demo_accounts: Any, gastos_busqueda: Any
) -> None:
    accounts, _ = demo_accounts
    client = _client(accounts)
    url = reverse("gastos:lista")
    response = client.get(url + "?q=insumos&q=mobiliario")
    assert list(response.context["solicitudes"]) == [gastos_busqueda["a_rechazada"]]
    invalid = client.get(url, {"q": ["mobiliario", "x" * 256]})
    assert "q" in invalid.context["filtro_form"].errors
    assert list(invalid.context["solicitudes"]) == []


def test_sin_capacidades_no_obtiene_coincidencias(
    demo_accounts: Any, gastos_busqueda: Any
) -> None:
    accounts, _ = demo_accounts
    accounts["demo_a"].groups.clear()
    response = _client(accounts).get(reverse("gastos:lista"), {"q": "insumos"})
    assert response.status_code == 200
    assert list(response.context["solicitudes"]) == []


def test_consulta_combinada_y_recarga_no_escriben_solicitudes_o_decisiones(
    demo_accounts: Any, gastos_busqueda: Any
) -> None:
    accounts, _ = demo_accounts
    decide_expense(
        actor=Actor(
            subject_id=accounts["demo_o"].pk,
            capabilities=frozenset({"gastos.consultar_todas", "gastos.decidir"}),
        ),
        solicitud_id=gastos_busqueda["a_presentada"].pk,
        action="postergar",
        expected_version=0,
        motivo="Revisión sintética posterior",
    )
    before_solicitudes = list(SolicitudGasto.objects.order_by("pk").values())
    before_decisiones = list(DecisionGasto.objects.order_by("pk").values())
    client = _client(accounts)
    params = {"q": "  insumos  ", "estado": "postergada"}
    response = client.get(reverse("gastos:lista"), params)
    reload = client.get(reverse("gastos:lista"), params)
    assert response.status_code == reload.status_code == 200
    assert response.content == reload.content
    assert list(response.context["solicitudes"]) == [gastos_busqueda["a_presentada"]]
    content = response.content.decode()
    assert '<label for="id_q">Buscar en concepto:</label>' in content
    assert 'value="  insumos  "' in content
    assert '<option value="postergada" selected>Postergada</option>' in content
    assert list(SolicitudGasto.objects.order_by("pk").values()) == before_solicitudes
    assert list(DecisionGasto.objects.order_by("pk").values()) == before_decisiones
