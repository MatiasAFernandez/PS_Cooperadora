"""La navegación común sólo ofrece circuitos autorizados por capacidades."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import resolve, reverse

from comunes.contracts import EventoHistorialDTO
from identidad.services import Actor

_RUTAS = {
    "gastos.consultar_propias": "gastos:lista",
    "gastos.consultar_todas": "gastos:lista",
    "gastos.presentar": "gastos:presentar",
    "facturacion.consultar_propias": "facturacion:lista",
    "facturacion.consultar_todas": "facturacion:lista",
    "facturacion.presentar": "facturacion:presentar",
}
_PLANTILLAS_CON_NAVEGACION = (
    "base.html",
    "facturacion/base.html",
    "identidad/inicio.html",
)


@pytest.mark.parametrize(
    ("capacidades", "rutas_visibles"),
    [
        ((), set()),
        (("gastos.consultar_propias",), {"gastos:lista"}),
        (("gastos.consultar_todas",), {"gastos:lista"}),
        (("gastos.presentar",), {"gastos:presentar"}),
        (("facturacion.consultar_propias",), {"facturacion:lista"}),
        (("facturacion.consultar_todas",), {"facturacion:lista"}),
        (("facturacion.presentar",), {"facturacion:presentar"}),
        (
            (
                "gastos.consultar_propias",
                "gastos.presentar",
                "facturacion.consultar_todas",
                "facturacion.presentar",
            ),
            {
                "gastos:lista",
                "gastos:presentar",
                "facturacion:lista",
                "facturacion:presentar",
            },
        ),
    ],
)
@pytest.mark.parametrize("plantilla", _PLANTILLAS_CON_NAVEGACION)
def test_navegacion_por_capacidad_en_bases_y_inicio(
    capacidades: tuple[str, ...], rutas_visibles: set[str], plantilla: str
) -> None:
    actor = Actor(subject_id=17, capabilities=frozenset(capacidades))

    html = render_to_string(plantilla, {"actor": actor})

    rutas_visibles = set(rutas_visibles)
    for circuito in ("gastos", "facturacion"):
        if any(circuito + "." + permiso in capacidades for permiso in (
            "consultar_propias", "consultar_todas"
        )):
            rutas_visibles.discard(circuito + ":presentar")

    for _capacidad, nombre_ruta in _RUTAS.items():
        enlace = f'href="{reverse(nombre_ruta)}"'
        if nombre_ruta in rutas_visibles:
            assert enlace in html
        else:
            assert enlace not in html


def test_navegacion_no_ofrece_rutas_pendientes() -> None:
    actor = Actor(subject_id=17, capabilities=frozenset(_RUTAS))

    for plantilla in _PLANTILLAS_CON_NAVEGACION:
        html = render_to_string(plantilla, {"actor": actor})
        assert reverse("gastos:decidir", kwargs={"pk": 1}) not in html
        assert reverse("gastos:pagar", kwargs={"pk": 1}) not in html
        assert reverse("facturacion:observar", kwargs={"numero": 1}) not in html
        assert reverse("facturacion:corregir", kwargs={"numero": 1}) not in html


def test_parcial_comun_renderiza_campos_del_dto_y_escapa_el_detalle() -> None:
    evento = EventoHistorialDTO(
        evento_id=3,
        tramite_ref="gastos:17",
        tipo_evento="pago_externo_registrado",
        actor_id="28",
        fecha_hora=datetime(2026, 10, 17, 15, 30, tzinfo=UTC),
        estado_resultante="aceptada",
        motivo_o_detalle=(
            "Importe: 825,40 ARS. Fecha del hecho: 14/10/2026. "
            "Referencia externa: <script>falso</script>"
        ),
    )

    html = render_to_string("comunes/historial_eventos.html", {"historial": [evento]})

    assert "Pago externo registrado" in html
    assert "gastos:17" in html
    assert "actor #28" in html
    assert "estado del trámite: aceptada" in html
    assert "Importe: 825,40 ARS" in html
    assert "Fecha del hecho: 14/10/2026" in html
    assert "&lt;script&gt;falso&lt;/script&gt;" in html
    assert "<script>falso</script>" not in html


def test_navegacion_marca_subrutas_de_usuarios_y_usa_sentence_case() -> None:
    actor = Actor(
        subject_id=17,
        capabilities=frozenset(
            {
                "identidad.administrar_cuentas",
                "gastos.presentar",
                "facturacion.presentar",
            }
        ),
    )
    ruta_editar = reverse("cuentas:usuario_editar", kwargs={"pk": 9})
    request = RequestFactory().get(ruta_editar)
    request.resolver_match = resolve(ruta_editar)
    request.user = SimpleNamespace(
        cuenta_local=True,
        get_full_name=lambda: "Admin QA",
        get_username=lambda: "admin_qa",
    )

    html = render_to_string(
        "comunes/navegacion_tramites.html",
        {"actor": actor},
        request=request,
    )

    assert f'<a href="{reverse("cuentas:usuarios")}" title="Usuarios" aria-current="page">' in html
    assert '<span class="app-nl">Solicitud de gasto</span>' in html
    assert '<span class="app-nl">Solicitud de facturación</span>' in html
    assert "Solicitud de Gasto" not in html
    assert "Solicitud de Facturación" not in html
