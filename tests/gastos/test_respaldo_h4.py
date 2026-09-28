"""Pruebas del componente de visualización de respaldo documental según H4 (I1-R05).

Cubre:
- Mensaje exacto para cada uno de los cuatro estados:
  - 'aceptada': «Respaldo del gasto (presupuesto o factura): por aportar»
  - 'presentada', 'postergada', 'rechazada':
    «No se solicita documentación en esta etapa de la demostración»
- Persistencia y consistencia del mensaje tras recargar la pantalla.
- Actualización dinámica tras decisiones autorizadas (presentada -> postergada -> aceptada).
- Filtrado de visibilidad y acceso no autorizado con datos sintéticos.
- Ausencia estricta de controles de carga de archivos (inputs de archivo, botones).
- Pruebas unitarias de modelo y función de mapeo de H4.
"""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gastos.models import (
    MENSAJE_RESPALDO_ACEPTADA,
    MENSAJE_RESPALDO_OTRAS,
    EstadoSolicitud,
    SolicitudGasto,
    get_mensaje_respaldo,
)

User = get_user_model()


@pytest.fixture
def solicitud_factory(
    demo_accounts: tuple[dict[str, Any], str],
) -> Any:
    """Fábrica de solicitudes sintéticas con estado parametrizable."""
    accounts, _ = demo_accounts

    def _create(
        *,
        estado: EstadoSolicitud = EstadoSolicitud.PRESENTADA,
        solicitante: Any = None,
        concepto: str = "Insumos para demostración H4",
        version: int = 0,
    ) -> SolicitudGasto:
        return SolicitudGasto.objects.create(
            concepto=concepto,
            monto_estimado=Decimal("15000.00"),
            unidad_requirente="Laboratorio de Informática",
            solicitante=solicitante or accounts["demo_a"],
            estado=estado,
            version=version,
        )

    return _create


# ==============================================================================
# 1. Pruebas de visualización por estado (I1-R05 / H4)
# ==============================================================================


@pytest.mark.django_db
def test_detalle_solicitud_aceptada_muestra_respaldo_por_aportar(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    """Solicitud aceptada muestra «Respaldo del gasto (presupuesto o factura): por aportar»."""
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)
    client = auth_client(accounts["demo_a"])

    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert MENSAJE_RESPALDO_ACEPTADA in content
    assert MENSAJE_RESPALDO_OTRAS not in content
    assert response.context["mensaje_respaldo"] == MENSAJE_RESPALDO_ACEPTADA
    assert response.context["solicitud"].mensaje_respaldo == MENSAJE_RESPALDO_ACEPTADA


@pytest.mark.django_db
@pytest.mark.parametrize(
    "estado_no_aceptado",
    [
        EstadoSolicitud.PRESENTADA,
        EstadoSolicitud.POSTERGADA,
        EstadoSolicitud.RECHAZADA,
    ],
)
def test_detalle_solicitud_no_aceptada_muestra_mensaje_alternativo(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
    estado_no_aceptado: EstadoSolicitud,
) -> None:
    """Solicitud presentada, postergada o rechazada muestra mensaje alternativo de H4."""
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=estado_no_aceptado)
    client = auth_client(accounts["demo_a"])

    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert MENSAJE_RESPALDO_OTRAS in content
    assert MENSAJE_RESPALDO_ACEPTADA not in content
    assert response.context["mensaje_respaldo"] == MENSAJE_RESPALDO_OTRAS
    assert response.context["solicitud"].mensaje_respaldo == MENSAJE_RESPALDO_OTRAS


# ==============================================================================
# 2. Persistencia y consistencia tras recarga (recarga del detalle)
# ==============================================================================


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("estado", "mensaje_esperado"),
    [
        (EstadoSolicitud.PRESENTADA, MENSAJE_RESPALDO_OTRAS),
        (EstadoSolicitud.POSTERGADA, MENSAJE_RESPALDO_OTRAS),
        (EstadoSolicitud.RECHAZADA, MENSAJE_RESPALDO_OTRAS),
        (EstadoSolicitud.ACEPTADA, MENSAJE_RESPALDO_ACEPTADA),
    ],
)
def test_recarga_detalle_conserva_mensaje_sin_alteracion(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
    estado: EstadoSolicitud,
    mensaje_esperado: str,
) -> None:
    """Múltiples recargas sucesivas de la pantalla de detalle conservan idéntico mensaje."""
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=estado)
    client = auth_client(accounts["demo_a"])
    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    for _ in range(3):
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert mensaje_esperado in content
        assert response.context["mensaje_respaldo"] == mensaje_esperado


@pytest.mark.django_db
def test_actualizacion_mensaje_tras_decisiones_sucesivas(
    csrf_auth_client: Any,
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    """El mensaje se actualiza en el recorrido presentada -> postergada -> aceptada."""
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=EstadoSolicitud.PRESENTADA, version=0)

    client_a = auth_client(accounts["demo_a"])
    client_o, token_o = csrf_auth_client(accounts["demo_o"])
    url_detalle = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    url_decidir = reverse("gastos:decidir", kwargs={"pk": solicitud.pk})

    # 1. Estado inicial: presentada -> mensaje alternativo
    resp1 = client_a.get(url_detalle)
    assert resp1.status_code == 200
    assert MENSAJE_RESPALDO_OTRAS in resp1.content.decode()
    assert MENSAJE_RESPALDO_ACEPTADA not in resp1.content.decode()

    # 2. O posterga la solicitud
    resp_post = client_o.post(
        url_decidir,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "Falta información técnica",
            "csrfmiddlewaretoken": token_o,
        },
    )
    assert resp_post.status_code == 302

    # A recarga el detalle: postergada -> sigue con mensaje alternativo
    resp2 = client_a.get(url_detalle)
    assert resp2.status_code == 200
    assert MENSAJE_RESPALDO_OTRAS in resp2.content.decode()
    assert MENSAJE_RESPALDO_ACEPTADA not in resp2.content.decode()

    # 3. O acepta la solicitud
    resp_acep = client_o.post(
        url_decidir,
        {
            "action": "aceptar",
            "version": "1",
            "motivo": "Información complementaria satisfecha",
            "csrfmiddlewaretoken": token_o,
        },
    )
    assert resp_acep.status_code == 302

    # A recarga el detalle: aceptada -> muestra exactamente el pendiente H4
    resp3 = client_a.get(url_detalle)
    assert resp3.status_code == 200
    assert MENSAJE_RESPALDO_ACEPTADA in resp3.content.decode()
    assert MENSAJE_RESPALDO_OTRAS not in resp3.content.decode()


@pytest.mark.django_db
def test_renderizado_respaldo_en_error_400_decision(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    """Al producirse error 400 en decisión, el re-renderizado conserva el mensaje de respaldo."""
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=EstadoSolicitud.PRESENTADA, version=0)

    client_o, token_o = csrf_auth_client(accounts["demo_o"])
    url_decidir = reverse("gastos:decidir", kwargs={"pk": solicitud.pk})

    # POST con motivo vacío al postergar -> produce HTTP 400 y re-renderiza el detalle
    response = client_o.post(
        url_decidir,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "",
            "csrfmiddlewaretoken": token_o,
        },
    )

    assert response.status_code == 400
    content = response.content.decode()
    assert MENSAJE_RESPALDO_OTRAS in content
    assert response.context["mensaje_respaldo"] == MENSAJE_RESPALDO_OTRAS


# ==============================================================================
# 3. Filtrado de visibilidad y acceso no autorizado
# ==============================================================================


@pytest.mark.django_db
def test_acceso_no_autorizado_solicitante_ajeno_retorna_404(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    """Solicitante B no puede acceder al detalle de A ni visualizar su respaldo (404 estricto)."""
    accounts, _ = demo_accounts
    solicitud_a = solicitud_factory(
        estado=EstadoSolicitud.ACEPTADA,
        solicitante=accounts["demo_a"],
    )

    client_b = auth_client(accounts["demo_b"])
    url = reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})

    response = client_b.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_acceso_no_autorizado_usuario_sin_capacidades_retorna_404(
    auth_client: Any,
    solicitud_factory: Any,
) -> None:
    """Usuario autenticado sin capacidades de gastos recibe 404 al consultar el detalle."""
    user_sin_caps = User.objects.create_user("usuario_sin_caps")
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)

    client = auth_client(user_sin_caps)
    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_acceso_anonimo_redirige_o_deniega(
    settings: Any,
    solicitud_factory: Any,
) -> None:
    """Usuario sin sesión: con demo activa redirige a login; con demo inactiva retorna 403."""
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)
    anon_client = Client()
    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    # Con demo habilitada
    settings.DEMO_IDENTITY_ENABLED = True
    resp_demo_on = anon_client.get(url)
    assert resp_demo_on.status_code == 302
    assert reverse("identidad:login") in resp_demo_on.url

    # Con demo deshabilitada
    settings.DEMO_IDENTITY_ENABLED = False
    resp_demo_off = anon_client.get(url)
    assert resp_demo_off.status_code == 403


@pytest.mark.django_db
def test_consulta_global_operadora_y_lectura_visualizan_respaldo(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
) -> None:
    """Cuentas con permiso de consulta global (O y L) visualizan el respaldo correspondiente."""
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)

    client_o = auth_client(accounts["demo_o"])
    client_l = auth_client(accounts["demo_l"])
    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    for client in (client_o, client_l):
        resp = client.get(url)
        assert resp.status_code == 200
        assert MENSAJE_RESPALDO_ACEPTADA in resp.content.decode()


# ==============================================================================
# 4. Ausencia estricta de controles de carga de archivos (H4 / exclusiones)
# ==============================================================================


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
def test_ausencia_de_controles_de_carga_de_archivos(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_factory: Any,
    estado: EstadoSolicitud,
) -> None:
    """En ningún estado se habilitan inputs de archivo, botones ni multipart."""
    accounts, _ = demo_accounts
    solicitud = solicitud_factory(estado=estado)
    client = auth_client(accounts["demo_a"])

    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode().lower()

    assert 'type="file"' not in content
    assert "enctype=" not in content
    assert "multipart/form-data" not in content
    assert "subir archivo" not in content
    assert "cargar comprobante" not in content
    assert "adjuntar" not in content


# ==============================================================================
# 5. Pruebas unitarias de modelo y función de mapeo H4
# ==============================================================================


def test_get_mensaje_respaldo_unidades() -> None:
    """get_mensaje_respaldo retorna el texto exacto según el estado proporcionado."""
    assert (
        get_mensaje_respaldo(EstadoSolicitud.ACEPTADA)
        == "Respaldo del gasto (presupuesto o factura): por aportar"
    )
    assert (
        get_mensaje_respaldo(EstadoSolicitud.PRESENTADA)
        == "No se solicita documentación en esta etapa de la demostración"
    )
    assert (
        get_mensaje_respaldo(EstadoSolicitud.POSTERGADA)
        == "No se solicita documentación en esta etapa de la demostración"
    )
    assert (
        get_mensaje_respaldo(EstadoSolicitud.RECHAZADA)
        == "No se solicita documentación en esta etapa de la demostración"
    )


@pytest.mark.django_db
def test_solicitud_property_mensaje_respaldo() -> None:
    """La propiedad mensaje_respaldo de SolicitudGasto refleja el estado del objeto en memoria."""
    user = User.objects.create_user("solicitante_unit")
    solicitud = SolicitudGasto(
        concepto="Prueba de propiedad",
        monto_estimado=Decimal("100.00"),
        unidad_requirente="Unidad",
        solicitante=user,
        estado=EstadoSolicitud.PRESENTADA,
    )

    assert (
        solicitud.mensaje_respaldo
        == "No se solicita documentación en esta etapa de la demostración"
    )

    solicitud.estado = EstadoSolicitud.ACEPTADA
    assert (
        solicitud.mensaje_respaldo
        == "Respaldo del gasto (presupuesto o factura): por aportar"
    )

    solicitud.estado = EstadoSolicitud.POSTERGADA
    assert (
        solicitud.mensaje_respaldo
        == "No se solicita documentación en esta etapa de la demostración"
    )

    solicitud.estado = EstadoSolicitud.RECHAZADA
    assert (
        solicitud.mensaje_respaldo
        == "No se solicita documentación en esta etapa de la demostración"
    )
