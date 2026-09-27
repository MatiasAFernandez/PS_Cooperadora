"""Pruebas de seguridad CSRF y métodos HTTP (CT-08)."""

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gastos.models import SolicitudGasto

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
    create_actor: Any, mock_identity_registry: dict[int, Any]
) -> None:
    """CT-08: POST autorizado sin CSRF válido es rechazado con 403 y no crea registros."""
    user, actor = create_actor("solicitante_csrf", ["gastos.presentar", "gastos.consultar_propias"])
    mock_identity_registry[user.pk] = actor

    # Test client con verificación estricta de CSRF activada
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    url = reverse("gastos:presentar")
    payload = {
        "concepto": "Gasto sin token CSRF",
        "monto_estimado": "10000.00",
        "unidad_requirente": "Laboratorio",
    }

    # Envío sin token CSRF
    response = client.post(url, payload)

    # Django CSRF middleware rechaza con 403 Forbidden antes de entrar a la vista
    assert response.status_code == 403

    # Verificación explícita de ausencia de escrituras
    assert not SolicitudGasto.objects.exists()
