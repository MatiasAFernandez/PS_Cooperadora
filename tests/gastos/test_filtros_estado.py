"""Contrato de consulta por estado: subconjuntos visibles y ausencia de escrituras."""

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.html import escape

from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto
from gastos.services import decide_expense
from identidad.services import Actor

pytestmark = pytest.mark.django_db


@pytest.fixture
def gastos_por_estado(demo_accounts: Any) -> dict[tuple[str, str], SolicitudGasto]:
    accounts, _ = demo_accounts
    return {
        (username, estado): SolicitudGasto.objects.create(
            concepto=f"Ejemplo {username} {estado}",
            monto_estimado="125.50",
            unidad_requirente="Unidad sintética",
            solicitante=accounts[username],
            estado=estado,
        )
        for username in ("demo_a", "demo_b")
        for estado in EstadoSolicitud.values
    }


@pytest.mark.parametrize("estado", EstadoSolicitud.values)
@pytest.mark.parametrize("username", ["demo_a", "demo_b", "demo_o", "demo_l"])
def test_estado_intersecta_visibilidad_y_conserva_seleccion(
    demo_accounts: Any, gastos_por_estado: Any, username: str, estado: str
) -> None:
    accounts, _ = demo_accounts
    client = Client()
    client.force_login(accounts[username])

    response = client.get(reverse("gastos:lista"), {"estado": estado})

    assert response.status_code == 200
    propietarios = (username,) if username in {"demo_a", "demo_b"} else ("demo_a", "demo_b")
    expected = {gastos_por_estado[(owner, estado)].pk for owner in propietarios}
    assert {s.pk for s in response.context["solicitudes"]} == expected
    content = response.content.decode()
    label = EstadoSolicitud(estado).label
    assert f'<option value="{estado}" selected>{label}</option>' in content
    for solicitud in gastos_por_estado.values():
        detail_url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
        if solicitud.pk in expected:
            assert f'href="{detail_url}"' in content
            assert client.get(detail_url).status_code == 200
        else:
            assert escape(solicitud.concepto) not in content
    if username in {"demo_a", "demo_b"}:
        other = "demo_b" if username == "demo_a" else "demo_a"
        other_url = reverse("gastos:detalle", kwargs={"pk": gastos_por_estado[(other, estado)].pk})
        assert client.get(other_url).status_code == 404
    if username == "demo_l":
        detail_url = reverse("gastos:detalle", kwargs={"pk": next(iter(expected))})
        assert client.get(detail_url).context["can_decide"] is False


@pytest.mark.parametrize("params", [{}, {"estado": ""}])
def test_sin_filtro_conserva_resultados_y_orden(
    demo_accounts: Any, gastos_por_estado: Any, params: dict[str, str]
) -> None:
    accounts, _ = demo_accounts
    client = Client()
    client.force_login(accounts["demo_a"])
    response = client.get(reverse("gastos:lista"), params)
    expected = sorted(
        (s for (owner, _), s in gastos_por_estado.items() if owner == "demo_a"),
        key=lambda s: (s.fecha_creacion, s.pk),
        reverse=True,
    )
    assert list(response.context["solicitudes"]) == expected
    content = response.content.decode()
    assert '<form method="get" action="/gastos/">' in content
    assert '<label for="id_estado">Estado:</label>' in content
    assert '<a href="/gastos/">Quitar filtro</a>' in content


@pytest.mark.parametrize(
    "query,invalid",
    [
        ("estado=desconocido", True),
        ("estado=aceptada&estado=desconocido", True),
        ("estado=desconocido&estado=aceptada", False),
    ],
)
def test_parametros_invalidos_y_repetidos(
    demo_accounts: Any, gastos_por_estado: Any, query: str, invalid: bool
) -> None:
    accounts, _ = demo_accounts
    client = Client()
    client.force_login(accounts["demo_a"])
    response = client.get(f'{reverse("gastos:lista")}?{query}')
    assert response.status_code == 200
    if invalid:
        assert list(response.context["solicitudes"]) == []
        assert "Seleccione un estado válido." in response.content.decode()
        assert "Corrija el filtro" in response.content.decode()
    else:
        assert list(response.context["solicitudes"]) == [gastos_por_estado[("demo_a", "aceptada")]]


def test_sin_coincidencias_no_muestra_tramites_ajenos(demo_accounts: Any) -> None:
    accounts, _ = demo_accounts
    SolicitudGasto.objects.create(
        concepto="Gasto aceptado ajeno",
        monto_estimado="10.00",
        unidad_requirente="Unidad sintética",
        solicitante=accounts["demo_b"],
        estado=EstadoSolicitud.ACEPTADA,
    )
    client = Client()
    client.force_login(accounts["demo_a"])
    response = client.get(reverse("gastos:lista"), {"estado": "aceptada"})
    assert list(response.context["solicitudes"]) == []
    assert "No se encontraron solicitudes visibles con el estado seleccionado." in (
        response.content.decode()
    )
    assert "Gasto aceptado ajeno" not in response.content.decode()


def test_filtro_no_cambia_condiciones_de_acceso(demo_accounts: Any, gastos_por_estado: Any) -> None:
    accounts, _ = demo_accounts
    url = reverse("gastos:lista") + "?estado=aceptada"
    client = Client()
    response = client.get(url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("identidad:login"))
    client.force_login(get_user_model().objects.create_user("sin_capacidades"))
    response = client.get(url)
    assert response.status_code == 200
    assert list(response.context["solicitudes"]) == []
    client.force_login(accounts["demo_a"])
    with override_settings(DEMO_IDENTITY_ENABLED=False):
        assert client.get(url).status_code == 403


def test_consulta_y_recarga_no_modifican_gastos_ni_historial(
    demo_accounts: Any, gastos_por_estado: Any
) -> None:
    accounts, _ = demo_accounts
    decide_expense(
        actor=Actor(
            subject_id=accounts["demo_o"].pk,
            capabilities=frozenset({"gastos.consultar_todas", "gastos.decidir"}),
        ),
        solicitud_id=gastos_por_estado[("demo_a", "presentada")].pk,
        action="postergar",
        expected_version=0,
        motivo="Revisión sintética posterior",
    )
    before_gastos = list(SolicitudGasto.objects.order_by("pk").values())
    before_decisiones = list(DecisionGasto.objects.order_by("pk").values())
    client = Client()
    client.force_login(accounts["demo_a"])
    url = reverse("gastos:lista")
    for estado in ["", *EstadoSolicitud.values, "invalido"]:
        params = {"estado": estado, "solicitante": accounts["demo_b"].pk}
        first = client.get(url, params)
        reload = client.get(url, params)
        assert first.status_code == reload.status_code == 200
        assert first.content == reload.content
        assert all(s.solicitante_id == accounts["demo_a"].pk for s in first.context["solicitudes"])
    assert list(SolicitudGasto.objects.order_by("pk").values()) == before_gastos
    assert list(DecisionGasto.objects.order_by("pk").values()) == before_decisiones
