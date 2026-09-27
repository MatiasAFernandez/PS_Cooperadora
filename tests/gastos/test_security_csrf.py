"""Pruebas de seguridad CSRF y métodos HTTP (CT-08 y T04-23 a T04-25)."""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto

User = get_user_model()


@pytest.mark.django_db
def test_ct08_get_presentar_no_crea_solicitudes(create_actor: Any, auth_client: Any) -> None:
    """CT-08: Petición GET a presentar muestra formulario y no tiene efectos de persistencia."""
    user, actor = create_actor("solicitante_get", ["gastos.presentar", "gastos.consultar_propias"])
    client = auth_client(user, actor)

    response = client.get(reverse("gastos:presentar"))
    assert response.status_code == 200
    assert "form" in response.context
    assert not SolicitudGasto.objects.exists()


@pytest.mark.django_db
def test_ct08_post_sin_csrf_rechazado_con_comprobacion_real(
    create_actor: Any,
) -> None:
    """CT-08: POST autorizado sin CSRF válido es rechazado con 403 y no crea registros."""
    user, actor = create_actor("solicitante_csrf", ["gastos.presentar", "gastos.consultar_propias"])

    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    url = reverse("gastos:presentar")
    payload = {
        "concepto": "Gasto sin token CSRF",
        "monto_estimado": "10000.00",
        "unidad_requirente": "Laboratorio",
    }

    response = client.post(url, payload)

    assert response.status_code == 403
    assert not SolicitudGasto.objects.exists()


@pytest.mark.django_db
def test_t04_23_post_decision_con_csrf_valido_exitoso(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-23: Comprobación CSRF real en decisiones (POST exitoso).

    POST con cuenta autorizada, sesión iniciada y token CSRF válido (enforce_csrf_checks=True).
    HTTP 302 Found al detalle. Transacción confirmada en BD.
    """
    accounts, _ = demo_accounts
    solicitud = SolicitudGasto.objects.create(
        concepto="Gasto para verificar CSRF válido",
        monto_estimado=Decimal("1500.00"),
        unidad_requirente="Laboratorio",
        solicitante=accounts["demo_a"],
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud.pk})

    response = client.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "Aprobación con CSRF válido",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.ACEPTADA
    assert solicitud.version == 1
    assert solicitud.decisiones.count() == 1


@pytest.mark.django_db
def test_t04_24_post_decision_sin_token_csrf_rechazado_con_403(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-24: POST sin token CSRF rechazado antes de sesión.

    POST anónimo o con sesión pero sin token CSRF (enforce_csrf_checks=True).
    HTTP 403 Forbidden estricto por CSRF middleware. 0 escrituras en BD (no redirige a login).
    """
    accounts, _ = demo_accounts
    solicitud = SolicitudGasto.objects.create(
        concepto="Gasto para verificar rechazo CSRF",
        monto_estimado=Decimal("2500.00"),
        unidad_requirente="Laboratorio",
        solicitante=accounts["demo_a"],
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    url = reverse("gastos:decidir", kwargs={"pk": solicitud.pk})

    # 1. Petición POST con sesión iniciada pero sin token CSRF
    client_auth = Client(enforce_csrf_checks=True)
    client_auth.force_login(accounts["demo_o"])

    resp_auth = client_auth.post(
        url,
        {"action": "aceptar", "version": "0", "motivo": "Sin token"},
    )
    assert resp_auth.status_code == 403

    # 2. Petición POST anónima sin token CSRF (middleware CSRF debe actuar antes que auth)
    client_anon = Client(enforce_csrf_checks=True)
    resp_anon = client_anon.post(
        url,
        {"action": "aceptar", "version": "0", "motivo": "Sin token ni sesión"},
    )
    assert resp_anon.status_code == 403

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_25_get_decidir_metodo_no_permitido(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-25: GET no registra decisiones.

    Petición GET a /gastos/<id>/decidir/ con o sin sesión.
    HTTP 405 Method Not Allowed. 0 modificaciones en BD.
    """
    accounts, _ = demo_accounts
    solicitud = SolicitudGasto.objects.create(
        concepto="Gasto para verificar método GET en endpoint de decisión",
        monto_estimado=Decimal("4000.00"),
        unidad_requirente="Laboratorio",
        solicitante=accounts["demo_a"],
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    url = reverse("gastos:decidir", kwargs={"pk": solicitud.pk})

    # GET autenticado
    client_auth = auth_client(accounts["demo_o"])
    resp_auth = client_auth.get(url)
    assert resp_auth.status_code == 405

    # GET anónimo
    client_anon = Client()
    resp_anon = client_anon.get(url)
    assert resp_anon.status_code == 405

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert not DecisionGasto.objects.exists()
