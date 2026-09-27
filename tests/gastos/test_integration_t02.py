"""Pruebas de integración del consumidor de gastos con el componente real de identidad (T02)."""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import Client, RequestFactory
from django.urls import reverse

from gastos.auth import has_capability, resolve_actor
from gastos.models import SolicitudGasto
from gastos.queries import visible_expenses

User = get_user_model()


def _request_with_session(user: Any) -> Any:
    """Helper para crear un request con sesión y usuario autenticado."""
    factory = RequestFactory()
    request = factory.get("/")
    # Usar un Client para configurar sesión válida de Django
    client = Client()
    if user.is_authenticated:
        client.force_login(user)
    session = client.session
    request.session = session
    request.user = user
    return request


@pytest.mark.django_db
def test_cuentas_demo_resolucion_y_capacidades_reales(demo_accounts: Any) -> None:
    """Las cuentas sintéticas A, B, O y L resuelven actor y capacidades según contrato."""
    accounts, _ = demo_accounts

    # 1. demo_a (solicitante)
    req_a = _request_with_session(accounts["demo_a"])
    actor_a = resolve_actor(req_a)
    assert actor_a is not None
    assert actor_a.subject_id == accounts["demo_a"].pk
    assert actor_a.capabilities == frozenset({"gastos.presentar", "gastos.consultar_propias"})
    assert has_capability(actor_a, "gastos.presentar") is True
    assert has_capability(actor_a, "gastos.consultar_propias") is True
    assert has_capability(actor_a, "gastos.consultar_todas") is False
    assert has_capability(actor_a, "gastos.decidir") is False

    # 2. demo_b (solicitante)
    req_b = _request_with_session(accounts["demo_b"])
    actor_b = resolve_actor(req_b)
    assert actor_b is not None
    assert actor_b.subject_id == accounts["demo_b"].pk
    assert actor_b.capabilities == frozenset({"gastos.presentar", "gastos.consultar_propias"})

    # 3. demo_o (operadora)
    req_o = _request_with_session(accounts["demo_o"])
    actor_o = resolve_actor(req_o)
    assert actor_o is not None
    assert actor_o.subject_id == accounts["demo_o"].pk
    assert actor_o.capabilities == frozenset({"gastos.consultar_todas", "gastos.decidir"})
    assert has_capability(actor_o, "gastos.consultar_todas") is True
    assert has_capability(actor_o, "gastos.decidir") is True
    assert has_capability(actor_o, "gastos.presentar") is False
    assert has_capability(actor_o, "gastos.consultar_propias") is False

    # 4. demo_l (lectura)
    req_l = _request_with_session(accounts["demo_l"])
    actor_l = resolve_actor(req_l)
    assert actor_l is not None
    assert actor_l.subject_id == accounts["demo_l"].pk
    assert actor_l.capabilities == frozenset({"gastos.consultar_todas"})
    assert has_capability(actor_l, "gastos.consultar_todas") is True
    assert has_capability(actor_l, "gastos.decidir") is False
    assert has_capability(actor_l, "gastos.presentar") is False


@pytest.mark.django_db
def test_cuenta_l_carece_de_capacidad_de_decision(demo_accounts: Any) -> None:
    """Verifica que Cuenta L carece de gastos.decidir según identidad.services.has_capability."""
    accounts, _ = demo_accounts

    actor_l = resolve_actor(_request_with_session(accounts["demo_l"]))
    actor_o = resolve_actor(_request_with_session(accounts["demo_o"]))

    assert has_capability(actor_l, "gastos.decidir") is False
    assert has_capability(actor_o, "gastos.decidir") is True


@pytest.mark.django_db
def test_has_capability_codigo_desconocido_y_actor_nulo(demo_accounts: Any) -> None:
    """has_capability retorna False para códigos no conocidos, valores no string o actor None."""
    accounts, _ = demo_accounts
    actor_a = resolve_actor(_request_with_session(accounts["demo_a"]))

    assert has_capability(actor_a, "codigo_inexistente") is False
    assert has_capability(actor_a, "gastos.inyeccion_falsa") is False
    assert has_capability(None, "gastos.presentar") is False
    assert has_capability(actor_a, 12345) is False  # type: ignore[arg-type]


@pytest.mark.django_db
def test_revocacion_y_cambio_de_grupo_se_refleja_inmediatamente(
    demo_accounts: Any, client: Client, demo_groups: dict[str, Group]
) -> None:
    """La revocación o cambio de grupos se refleja de inmediato sin cachear permisos en sesión."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    client.force_login(user_a)

    # 1. Con grupo demo_solicitante activo, puede abrir formulario de presentación
    resp1 = client.get(reverse("gastos:presentar"))
    assert resp1.status_code == 200

    # 2. Revocación de grupos en BD
    user_a.groups.clear()

    # 3. La siguiente petición sin re-login deniega inmediatamente con 403
    resp2 = client.get(reverse("gastos:presentar"))
    assert resp2.status_code == 403

    # 4. Cambio a grupo demo_operadora en BD
    user_a.groups.add(demo_groups["demo_operadora"])

    # 5. La siguiente petición sin re-login refleja inmediatamente las nuevas capacidades
    resp3 = client.get(reverse("gastos:presentar"))
    assert resp3.status_code == 403  # Operadora no tiene gastos.presentar
    resp4 = client.get(reverse("gastos:lista"))
    assert resp4.status_code == 200  # Operadora sí tiene gastos.consultar_todas


@pytest.mark.django_db
def test_demo_deshabilitada_con_sesion_previa_produce_ausencia_actor(
    demo_accounts: Any, client: Client, settings: Any
) -> None:
    """Con sesión activa previa, si DEMO_IDENTITY_ENABLED=False produce ausencia de actor."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    client.force_login(user_a)

    # Desactivar demo
    settings.DEMO_IDENTITY_ENABLED = False

    # resolve_actor retorna None
    req = _request_with_session(user_a)
    assert resolve_actor(req) is None

    # Acceso a gastos responde 403 sin ofrecer login
    resp_gastos = client.get(reverse("gastos:lista"))
    assert resp_gastos.status_code == 403

    # Acceso a demo responde 404 (adaptador desactivado)
    resp_demo = client.get(reverse("identidad:login"))
    assert resp_demo.status_code == 404


@pytest.mark.django_db
def test_usuario_activo_sin_grupos_obtiene_actor_sin_capacidades(client: Client) -> None:
    """Un usuario activo sin grupos obtiene un Actor con capacidades vacías."""
    user = User.objects.create_user(username="usuario_neutro")
    client.force_login(user)

    req = _request_with_session(user)
    actor = resolve_actor(req)
    assert actor is not None
    assert actor.subject_id == user.pk
    assert actor.capabilities == frozenset()

    assert has_capability(actor, "gastos.presentar") is False
    assert has_capability(actor, "gastos.consultar_todas") is False

    # En vistas: formulario denegado (403), lista vacía (200)
    assert client.get(reverse("gastos:presentar")).status_code == 403
    resp_list = client.get(reverse("gastos:lista"))
    assert resp_list.status_code == 200
    assert list(resp_list.context["solicitudes"]) == []


@pytest.mark.django_db
def test_usuario_inactivo_o_anonimo_retorna_none(demo_accounts: Any) -> None:
    """resolve_actor retorna None para usuarios anónimos o inactivos."""
    accounts, _ = demo_accounts

    # Anónimo
    factory = RequestFactory()
    req_anon = factory.get("/")
    req_anon.user = AnonymousUser()
    assert resolve_actor(req_anon) is None

    # Inactivo
    user_inactivo = accounts["demo_b"]
    user_inactivo.is_active = False
    user_inactivo.save()

    req_inactivo = _request_with_session(user_inactivo)
    assert resolve_actor(req_inactivo) is None


@pytest.mark.django_db
def test_visible_expenses_con_actores_reales(demo_accounts: Any) -> None:
    """visible_expenses filtra correctamente usando actores reales de A, B, O y L."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_b = accounts["demo_b"]

    s_a = SolicitudGasto.objects.create(
        concepto="Solicitud de A",
        monto_estimado=Decimal("1000.00"),
        unidad_requirente="Unidad A",
        solicitante=user_a,
    )
    s_b = SolicitudGasto.objects.create(
        concepto="Solicitud de B",
        monto_estimado=Decimal("2000.00"),
        unidad_requirente="Unidad B",
        solicitante=user_b,
    )

    actor_a = resolve_actor(_request_with_session(user_a))
    actor_b = resolve_actor(_request_with_session(user_b))
    actor_o = resolve_actor(_request_with_session(accounts["demo_o"]))
    actor_l = resolve_actor(_request_with_session(accounts["demo_l"]))

    # Solicitante A ve sólo s_a
    assert set(visible_expenses(actor_a)) == {s_a}
    # Solicitante B ve sólo s_b
    assert set(visible_expenses(actor_b)) == {s_b}
    # Operadora O ve ambas
    assert set(visible_expenses(actor_o)) == {s_a, s_b}
    # Lectura L ve ambas
    assert set(visible_expenses(actor_l)) == {s_a, s_b}
    # None ve ninguna
    assert list(visible_expenses(None)) == []


@pytest.mark.django_db
def test_recorrido_completo_cuentas_demo_a_b_o_l(
    demo_accounts: Any, csrf_auth_client: Any, auth_client: Any
) -> None:
    """Recorrido integrado reproducible A/B/O/L con cuentas y sesiones reales de demo."""
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_b = accounts["demo_b"]
    user_o = accounts["demo_o"]
    user_l = accounts["demo_l"]

    # 1. A presenta una solicitud por $45.000 con sesión y CSRF válidos
    client_a, csrf_token_a = csrf_auth_client(user_a)
    url_presentar = reverse("gastos:presentar")
    payload = {
        "csrfmiddlewaretoken": csrf_token_a,
        "concepto": "Resmas de papel para secretaría",
        "monto_estimado": "45000.00",
        "unidad_requirente": "Secretaría Académica",
    }
    resp_presentar = client_a.post(url_presentar, payload)
    assert resp_presentar.status_code == 302

    solicitud_a = SolicitudGasto.objects.get(concepto="Resmas de papel para secretaría")
    assert resp_presentar.url == reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})
    assert solicitud_a.solicitante == user_a

    # A consulta detalle y listado
    assert client_a.get(resp_presentar.url).status_code == 200
    resp_list_a = client_a.get(reverse("gastos:lista"))
    assert resp_list_a.status_code == 200
    assert solicitud_a in resp_list_a.context["solicitudes"]

    # 2. B consulta listado: no ve la solicitud de A
    client_b = auth_client(user_b)
    resp_list_b = client_b.get(reverse("gastos:lista"))
    assert resp_list_b.status_code == 200
    assert solicitud_a not in resp_list_b.context["solicitudes"]

    # B accede al detalle de A por URL directa: recibe 404 estricto (aislamiento recíproco)
    resp_detalle_ajeno = client_b.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk}))
    assert resp_detalle_ajeno.status_code == 404

    # 3. O consulta listado: ve la solicitud de A
    client_o = auth_client(user_o)
    resp_list_o = client_o.get(reverse("gastos:lista"))
    assert resp_list_o.status_code == 200
    assert solicitud_a in resp_list_o.context["solicitudes"]

    # O accede al detalle de A: 200 OK
    assert client_o.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})).status_code == 200

    # 4. L consulta listado: ve la solicitud de A (200 OK)
    client_l, csrf_token_l = csrf_auth_client(user_l)
    resp_list_l = client_l.get(reverse("gastos:lista"))
    assert resp_list_l.status_code == 200
    assert solicitud_a in resp_list_l.context["solicitudes"]

    # L accede al detalle de A: 200 OK
    assert client_l.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})).status_code == 200

    # L intenta presentar por POST directo: recibe 403 Forbidden y 0 escrituras adicionales
    resp_presentar_l = client_l.post(
        url_presentar,
        {
            "csrfmiddlewaretoken": csrf_token_l,
            "concepto": "Intento no autorizado por L",
            "monto_estimado": "12000.00",
            "unidad_requirente": "Mantenimiento",
        },
    )
    assert resp_presentar_l.status_code == 403
    assert SolicitudGasto.objects.count() == 1  # Solo la solicitud inicial de A


@pytest.mark.django_db
def test_recorrido_integrado_login_next_operacion_y_logout_con_csrf_estricto(
    demo_accounts: Any,
) -> None:
    """B3: Recorrido HTTP integrado de entrada/salida sin force_login con CSRF estricto.

    - Acceso anónimo a gastos redirige al login con next.
    - POST de credenciales sintéticas con CSRF obtenido del formulario.
    - Regreso a la pantalla de gastos solicitada y acceso permitido.
    - Logout mediante POST con token vigente.
    - Nuevo acceso a gastos sin sesión redirigido/denegado, sin exponer datos.
    """
    accounts, password = demo_accounts
    client = Client(enforce_csrf_checks=True)
    url_presentar = reverse("gastos:presentar")
    url_login = reverse("identidad:login")
    url_logout = reverse("identidad:logout")

    # 1. Acceso anónimo a gastos redirige al login con next
    resp_anon = client.get(url_presentar)
    assert resp_anon.status_code == 302
    assert resp_anon.url.startswith(url_login)
    assert "next=" in resp_anon.url

    # 2. Acceso a la página de login para obtener el formulario y cookie CSRF
    resp_login_page = client.get(resp_anon.url)
    assert resp_login_page.status_code == 200
    assert "form" in resp_login_page.context
    csrf_token = client.cookies["csrftoken"].value

    # POST de credenciales sintéticas de demo_a con CSRF obtenido del formulario
    resp_login_post = client.post(
        resp_anon.url,
        {
            "csrfmiddlewaretoken": csrf_token,
            "username": "demo_a",
            "password": password,
            "next": url_presentar,
        },
    )
    assert resp_login_post.status_code == 302
    assert resp_login_post.url == url_presentar

    # 3. Regreso a la pantalla de gastos solicitada y acceso permitido
    resp_pantalla = client.get(url_presentar)
    assert resp_pantalla.status_code == 200
    assert "form" in resp_pantalla.context
    assert resp_pantalla.context["actor"].subject_id == accounts["demo_a"].pk

    # Operación de presentación con CSRF válido
    csrf_token_gasto = client.cookies["csrftoken"].value
    resp_crear = client.post(
        url_presentar,
        {
            "csrfmiddlewaretoken": csrf_token_gasto,
            "concepto": "Insumos solicitados en ciclo completo login",
            "monto_estimado": "18000.00",
            "unidad_requirente": "Secretaría Académica",
        },
    )
    assert resp_crear.status_code == 302
    solicitud = SolicitudGasto.objects.get(concepto="Insumos solicitados en ciclo completo login")
    assert solicitud.solicitante == accounts["demo_a"]
    assert resp_crear.url == reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    # Acceso al detalle permitido
    assert client.get(resp_crear.url).status_code == 200

    # 4. Logout mediante POST con token vigente
    csrf_token_logout = client.cookies["csrftoken"].value
    resp_logout = client.post(url_logout, {"csrfmiddlewaretoken": csrf_token_logout})
    assert resp_logout.status_code == 302

    # 5. Nuevo acceso a gastos sin sesión redirigido sin exponer datos
    resp_lista_post_logout = client.get(reverse("gastos:lista"))
    assert resp_lista_post_logout.status_code == 302
    assert resp_lista_post_logout.url.startswith(url_login)

    resp_detalle_post_logout = client.get(reverse("gastos:detalle", kwargs={"pk": solicitud.pk}))
    assert resp_detalle_post_logout.status_code == 302
    assert resp_detalle_post_logout.url.startswith(url_login)
