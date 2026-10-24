"""La sección documental presenta hechos visibles, no pendientes inferidos por estado."""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gastos.models import EstadoSolicitud, SolicitudGasto
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()


@pytest.fixture
def solicitud_factory(demo_accounts: tuple[dict[str, Any], str]) -> Any:
    """Fábrica de solicitudes sintéticas con estado parametrizable."""
    accounts, _ = demo_accounts

    def _create(
        *,
        estado: EstadoSolicitud = EstadoSolicitud.PRESENTADA,
        solicitante: Any = None,
        concepto: str = "Insumos para demostración H4",
        version: int = 0,
    ) -> SolicitudGasto:
        return crear_gasto_sintetico(
            concepto=concepto,
            monto_estimado=Decimal("15000.00"),
            unidad_requirente="Laboratorio de Informática",
            solicitante=solicitante or accounts["demo_a"],
            estado=estado,
            version=version,
        )

    return _create


@pytest.mark.django_db
@pytest.mark.parametrize(
    "estado",
    [
        EstadoSolicitud.PRESENTADA,
        EstadoSolicitud.POSTERGADA,
        EstadoSolicitud.RECHAZADA,
        EstadoSolicitud.ACEPTADA,
    ],
)
def test_detalle_no_infiere_respaldo_por_estado(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
    estado: EstadoSolicitud,
) -> None:
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=estado)
    response = auth_client(accounts["demo_a"]).get(
        reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Esta vista no muestra metadatos ni estado de revisión" in content
    assert "por aportar" not in content
    assert "No se solicita documentación en esta etapa" not in content
    assert response.context["puede_ver_documentos"] is False


@pytest.mark.django_db
def test_decision_y_error_de_decision_no_alteran_mensaje_documental(
    csrf_auth_client: Any,
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=EstadoSolicitud.PRESENTADA, version=0)
    cliente_solicitante = auth_client(accounts["demo_a"])
    cliente_operadora, token = csrf_auth_client(accounts["demo_o"])
    detalle = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    decidir = reverse("gastos:decidir", kwargs={"pk": solicitud.pk})

    response = cliente_solicitante.get(detalle)
    assert response.status_code == 200
    assert "Esta vista no muestra metadatos ni estado de revisión" in response.content.decode()

    error = cliente_operadora.post(
        decidir,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "",
            "csrfmiddlewaretoken": token,
        },
    )
    assert error.status_code == 400
    assert "Esta vista no muestra metadatos ni estado de revisión" in error.content.decode()

    aceptada = cliente_operadora.post(
        decidir,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "",
            "csrfmiddlewaretoken": token,
        },
    )
    assert aceptada.status_code == 302
    final = cliente_solicitante.get(detalle)
    assert final.status_code == 200
    assert "Esta vista no muestra metadatos ni estado de revisión" in final.content.decode()


@pytest.mark.django_db
def test_solicitante_ajeno_no_consulta_detalle_ni_documentos(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=accounts["demo_a"])
    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    cliente_ajeno = auth_client(accounts["demo_b"])

    assert cliente_ajeno.get(url).status_code == 404
    url_documentos = reverse("gastos:documentos", kwargs={"pk": solicitud.pk})
    assert cliente_ajeno.get(url_documentos).status_code == 404


@pytest.mark.django_db
def test_usuario_sin_capacidades_no_accede_a_gasto(
    auth_client: Any,
    solicitud_factory: Any,
) -> None:
    usuario = User.objects.create_user("usuario_sin_caps")
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)
    cliente = auth_client(usuario)

    assert cliente.get(reverse("gastos:detalle", kwargs={"pk": solicitud.pk})).status_code == 404
    assert cliente.get(reverse("gastos:documentos", kwargs={"pk": solicitud.pk})).status_code == 404


@pytest.mark.django_db
def test_sin_capacidad_incorporar_no_ve_enlace_ni_formulario(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)
    cliente = auth_client(accounts["demo_a"])
    contenido = cliente.get(reverse("gastos:detalle", kwargs={"pk": solicitud.pk})).content.decode()

    assert "Cargar o reemplazar un respaldo" not in contenido
    assert 'type="file"' not in contenido
    assert cliente.get(reverse("gastos:documentos", kwargs={"pk": solicitud.pk})).status_code == 403


@pytest.mark.django_db
def test_acceso_anonimo_redirige_o_deniega(settings: Any, solicitud_factory: Any) -> None:
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)
    cliente = Client()
    url = reverse("gastos:documentos", kwargs={"pk": solicitud.pk})

    settings.DEMO_IDENTITY_ENABLED = True
    response = cliente.get(url)
    assert response.status_code == 302
    assert reverse("identidad:login") in response.url

    settings.DEMO_IDENTITY_ENABLED = False
    assert cliente.get(url).status_code == 403
