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


def test_shell_fase_a_popover_cuenta_sin_role_menu_y_separadores_protegidos() -> None:
    actor = Actor(subject_id=17, capabilities=frozenset({"gastos.consultar_todas"}))
    request_local = RequestFactory().get(reverse("cuentas:inicio"))
    request_local.resolver_match = resolve(reverse("cuentas:inicio"))
    request_local.user = SimpleNamespace(
        cuenta_local=True,
        email="elena.vargas@example.invalid",
        get_full_name=lambda: "Elena Vargas",
        get_username=lambda: "elena",
    )

    html_local = render_to_string(
        "comunes/navegacion_tramites.html",
        {"actor": actor},
        request=request_local,
    )
    assert 'class="utn-logo"' in html_local
    assert "UTN · FRRe" in html_local
    assert "brand-badge" not in html_local
    assert 'id="app-account-menu"' in html_local
    assert 'role="menu"' not in html_local
    assert 'role="menuitem"' not in html_local
    assert f'href="{reverse("cuentas:estado")}"' in html_local
    assert f'href="{reverse("cuentas:cambiar_clave")}"' in html_local
    assert "data-avisos-dot" in html_local
    assert html_local.count('class="app-account-sep"') == 2

    # Cuenta demo (sin cuenta_local): un solo separador antes de Cerrar sesión.
    request_demo = RequestFactory().get(reverse("identidad:inicio"))
    request_demo.resolver_match = resolve(reverse("identidad:inicio"))
    request_demo.user = SimpleNamespace(
        cuenta_local=None,
        email="",
        get_full_name=lambda: "Demo Cooperadora",
        get_username=lambda: "demo",
    )
    html_demo = render_to_string(
        "comunes/navegacion_tramites.html",
        {"actor": actor},
        request=request_demo,
    )
    assert html_demo.count('class="app-account-sep"') == 1
    assert html_demo.count('class="app-account-sep app-theme-only-js"') == 1
    assert 'data-theme-choice="light"' in html_demo
    assert 'data-theme-choice="dark"' in html_demo
    assert 'data-theme-choice="system"' in html_demo
    assert f'href="{reverse("cuentas:estado")}"' not in html_demo
    assert f'href="{reverse("cuentas:cambiar_clave")}"' not in html_demo


def test_favicon_e_identidad_utn_en_base_y_500() -> None:
    html_base = render_to_string("base.html", {})
    assert 'rel="icon" type="image/svg+xml"' in html_base
    assert "img/favicon.svg" in html_base
    assert 'class="utn-logo"' in html_base
    assert "localStorage.getItem('theme')" in html_base

    html_500 = render_to_string("500.html", {})
    assert 'rel="icon" type="image/svg+xml" href="data:image/svg+xml,' in html_500
    assert "prefers-color-scheme: dark" in html_500
    assert "Asociación Cooperadora" in html_500
    assert '<span class="brand-lockup-inst">Universidad Tecnológica Nacional</span>' in html_500
    assert '<span class="brand-lockup-inst">Facultad Regional Resistencia</span>' in html_500
    assert "Universidad Tecnológica Nacional ·</span>" not in html_500

