"""Pruebas de integración de vistas para decisiones humanas e historial de gastos.

Cubre los casos de la matriz de pruebas aprobada (plan_t04_gastos.md):
- T04-01 a T04-06: Transiciones válidas y persistencia de DecisionGasto.
- T04-07 a T04-09: Transiciones inválidas y respuesta 409 Conflict.
- T04-10 y T04-11: Motivo obligatorio vacío en postergar/rechazar (400 Bad Request).
- T04-12: Objeto ajeno + contenido inválido (404 Not Found por precedencia de visibilidad).
- T04-13: Solicitante intenta auto-decisión sobre gasto propio (403 Forbidden).
- T04-14: Objeto visible sin permiso + contenido inválido
  (403 Forbidden por precedencia de autorización).
- T04-15: Cuenta con múltiples grupos intentando auto-decisión (403 Forbidden).
- T04-16: Capacidad gastos.decidir sin visibilidad efectiva (404 Not Found).
- T04-17: Parámetros manipulados por cliente ignorados por servidor.
- T04-18: Actor autorizado con acción desconocida (400 Bad Request).
- T04-19: Actor autorizado con versión no entera o booleana (400 Bad Request).
- T04-20: Versión desactualizada rechazada con 409 Conflict.
- T04-26: Consulta del historial de decisiones en detalle y aislamiento de B.
- Renderizado condicional del formulario de decisión según can_decide.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto

User = get_user_model()


@pytest.fixture
def solicitud_a(demo_accounts: tuple[dict[str, Any], str]) -> SolicitudGasto:
    """Crea una solicitud de gasto presentada por la cuenta sintética A."""
    accounts, _ = demo_accounts
    return SolicitudGasto.objects.create(
        concepto="Insumos de prueba para laboratorio",
        monto_estimado=Decimal("12000.00"),
        unidad_requirente="Laboratorio de Química",
        solicitante=accounts["demo_a"],
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )


@pytest.mark.django_db
def test_t04_01_transicion_presentada_a_aceptada_sin_motivo(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-01: Transición válida: presentada a aceptada sin motivo.

    O decide sobre solicitud de A en presentada, v=0, action="aceptar", motivo="".
    HTTP 302 a detalle. Solicitud estado="aceptada", version=1.
    1 registro en DecisionGasto con motivo="".
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.ACEPTADA
    assert solicitud_a.version == 1

    decisiones = solicitud_a.decisiones.all()
    assert decisiones.count() == 1
    decision = decisiones.first()
    assert decision.autor == accounts["demo_o"]
    assert decision.estado_anterior == EstadoSolicitud.PRESENTADA
    assert decision.estado_resultante == EstadoSolicitud.ACEPTADA
    assert decision.motivo == ""


@pytest.mark.django_db
def test_t04_02_transicion_presentada_a_aceptada_con_motivo(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-02: Transición válida: presentada a aceptada con motivo.

    O decide sobre solicitud de A, v=0, action="aceptar", motivo="Aprobado por comisión".
    HTTP 302. Solicitud estado="aceptada", version=1. 1 registro con motivo persistido.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "Aprobado por comisión directiva",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.ACEPTADA
    assert solicitud_a.version == 1

    decision = solicitud_a.decisiones.first()
    assert decision.motivo == "Aprobado por comisión directiva"


@pytest.mark.django_db
def test_t04_03_transicion_presentada_a_postergada_con_motivo(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-03: Transición válida: presentada a postergada con motivo.

    O decide sobre solicitud de A, v=0, action="postergar", motivo="Falta presupuesto".
    HTTP 302. Solicitud estado="postergada", version=1. 1 registro con motivo persistido.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client.post(
        url,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "Falta presupuesto asignado para el período",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.POSTERGADA
    assert solicitud_a.version == 1

    decision = solicitud_a.decisiones.first()
    assert decision.estado_anterior == EstadoSolicitud.PRESENTADA
    assert decision.estado_resultante == EstadoSolicitud.POSTERGADA
    assert decision.motivo == "Falta presupuesto asignado para el período"


@pytest.mark.django_db
def test_t04_04_transicion_presentada_a_rechazada_con_motivo(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-04: Transición válida: presentada a rechazada con motivo.

    O decide sobre solicitud de A, v=0, action="rechazar", motivo="Gasto no prioritario".
    HTTP 302. Solicitud estado="rechazada", version=1. 1 registro con motivo persistido.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client.post(
        url,
        {
            "action": "rechazar",
            "version": "0",
            "motivo": "Gasto no prioritario según plan anual",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.RECHAZADA
    assert solicitud_a.version == 1

    decision = solicitud_a.decisiones.first()
    assert decision.estado_anterior == EstadoSolicitud.PRESENTADA
    assert decision.estado_resultante == EstadoSolicitud.RECHAZADA
    assert decision.motivo == "Gasto no prioritario según plan anual"


@pytest.mark.django_db
def test_t04_05_transicion_postergada_a_aceptada_con_motivo(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-05: Transición válida: postergada a aceptada con motivo.

    Solicitud en postergada (v=1). O decide action="aceptar", motivo="Presupuesto adjuntado".
    HTTP 302. Solicitud estado="aceptada", version=2. 2 registros en DecisionGasto.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    # Paso previo: postergar
    client.post(
        url,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "A la espera de fondos",
            "csrfmiddlewaretoken": token,
        },
    )

    # Segundo paso: aceptar sobre v=1
    response = client.post(
        url,
        {
            "action": "aceptar",
            "version": "1",
            "motivo": "Presupuesto complementario adjuntado",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.ACEPTADA
    assert solicitud_a.version == 2

    decisiones = list(solicitud_a.decisiones.all())
    assert len(decisiones) == 2
    assert decisiones[0].estado_anterior == EstadoSolicitud.PRESENTADA
    assert decisiones[0].estado_resultante == EstadoSolicitud.POSTERGADA
    assert decisiones[1].estado_anterior == EstadoSolicitud.POSTERGADA
    assert decisiones[1].estado_resultante == EstadoSolicitud.ACEPTADA
    assert decisiones[1].motivo == "Presupuesto complementario adjuntado"


@pytest.mark.django_db
def test_t04_06_transicion_postergada_a_rechazada_con_motivo(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-06: Transición válida: postergada a rechazada con motivo.

    Solicitud en postergada (v=1). O decide action="rechazar", motivo="Plazo vencido".
    HTTP 302. Solicitud estado="rechazada", version=2. 2 registros en DecisionGasto.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    # Postergar primero
    client.post(
        url,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "Esperando presupuesto",
            "csrfmiddlewaretoken": token,
        },
    )

    # Rechazar después
    response = client.post(
        url,
        {
            "action": "rechazar",
            "version": "1",
            "motivo": "Plazo de presentación de presupuesto vencido",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.RECHAZADA
    assert solicitud_a.version == 2

    decisiones = list(solicitud_a.decisiones.all())
    assert len(decisiones) == 2
    assert decisiones[1].estado_anterior == EstadoSolicitud.POSTERGADA
    assert decisiones[1].estado_resultante == EstadoSolicitud.RECHAZADA


@pytest.mark.django_db
def test_t04_07_transicion_invalida_postergada_a_postergada(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-07: Transición inválida: postergada a postergada.

    Solicitud en postergada. O intenta action="postergar".
    HTTP 409 Conflict. Estado y versión intactos; 0 eventos adicionales.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    # Establecer estado postergada
    solicitud_a.estado = EstadoSolicitud.POSTERGADA
    solicitud_a.version = 1
    solicitud_a.save()
    DecisionGasto.objects.create(
        solicitud=solicitud_a,
        autor=accounts["demo_o"],
        motivo="Pausa previa",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.POSTERGADA,
    )

    response = client.post(
        url,
        {
            "action": "postergar",
            "version": "1",
            "motivo": "Segunda postergación no permitida",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 409
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.POSTERGADA
    assert solicitud_a.version == 1
    assert solicitud_a.decisiones.count() == 1


@pytest.mark.django_db
def test_t04_08_transicion_invalida_aceptada_a_cualquier_estado(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-08: Transición inválida: aceptada a cualquier estado.

    Solicitud en aceptada. O intenta action="rechazar", "postergar" o "aceptar".
    HTTP 409 Conflict. Estado y versión intactos; 0 eventos adicionales.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    solicitud_a.estado = EstadoSolicitud.ACEPTADA
    solicitud_a.version = 1
    solicitud_a.save()

    for invalid_action in ("rechazar", "postergar", "aceptar"):
        response = client.post(
            url,
            {
                "action": invalid_action,
                "version": "1",
                "motivo": "Intento de mutar estado terminal",
                "csrfmiddlewaretoken": token,
            },
        )
        assert response.status_code == 409

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.ACEPTADA
    assert solicitud_a.version == 1
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_09_transicion_invalida_rechazada_a_cualquier_estado(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-09: Transición inválida: rechazada a cualquier estado.

    Solicitud en rechazada. O intenta action="aceptar" o "postergar".
    HTTP 409 Conflict. Estado y versión intactos; 0 eventos adicionales.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    solicitud_a.estado = EstadoSolicitud.RECHAZADA
    solicitud_a.version = 1
    solicitud_a.save()

    for invalid_action in ("aceptar", "postergar", "rechazar"):
        response = client.post(
            url,
            {
                "action": invalid_action,
                "version": "1",
                "motivo": "Intento de mutar solicitud rechazada",
                "csrfmiddlewaretoken": token,
            },
        )
        assert response.status_code == 409

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.RECHAZADA
    assert solicitud_a.version == 1
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_10_motivo_vacio_en_postergacion_retorna_400(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-10: Actor autorizado + motivo obligatorio vacío en postergación.

    O decide sobre solicitud visible de A con action="postergar" y motivo="" o motivo="   ".
    HTTP 400 Bad Request. Formulario con error; 0 escrituras en BD.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client.post(
        url,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "   ",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 400
    assert "error_decision" in response.context
    assert "motivo" in response.context["decision_form"].errors

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_11_motivo_vacio_en_rechazo_retorna_400(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-11: Actor autorizado + motivo obligatorio vacío en rechazo.

    O decide sobre solicitud visible de A con action="rechazar" y motivo="" o motivo="   ".
    HTTP 400 Bad Request. Formulario con error; 0 escrituras en BD.
    """
    accounts, _ = demo_accounts
    client, token = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client.post(
        url,
        {
            "action": "rechazar",
            "version": "0",
            "motivo": "",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 400
    assert "error_decision" in response.context
    assert "motivo" in response.context["decision_form"].errors

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_12_objeto_ajeno_con_contenido_invalido_retorna_404(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-12: Objeto ajeno + contenido inválido (precedencia de visibilidad).

    Solicitante A intenta decidir vía POST sobre solicitud de B con CSRF válido pero
    con acción desconocida ("invalida") y versión corrupta ("xyz").
    HTTP 404 Not Found (visibilidad evaluada antes que el contenido; no revela existencia).
    0 modificaciones en BD.
    """
    accounts, _ = demo_accounts
    user_b = accounts["demo_b"]

    solicitud_b = SolicitudGasto.objects.create(
        concepto="Insumos exclusivos de B",
        monto_estimado=Decimal("3000.00"),
        unidad_requirente="Laboratorio B",
        solicitante=user_b,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    client_a, token_a = csrf_auth_client(accounts["demo_a"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_b.pk})

    response = client_a.post(
        url,
        {
            "action": "accion_invalida",
            "version": "xyz",
            "motivo": "",
            "csrfmiddlewaretoken": token_a,
        },
    )

    # Debe retornar 404 estricto (precedencia de visibilidad)
    assert response.status_code == 404

    # B3 y B4 sobre objeto ajeno: 404 estricto antes de evaluar contenido
    resp_b3_b4 = client_a.post(
        url,
        {
            "action": "aceptar",
            "version": "\u00b2",
            "motivo": "Texto con byte\x00nulo",
            "csrfmiddlewaretoken": token_a,
        },
    )
    assert resp_b3_b4.status_code == 404

    solicitud_b.refresh_from_db()
    assert solicitud_b.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_b.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_13_solicitante_auto_decision_retorna_403(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-13: Solicitante intenta decidir sobre gasto propio.

    Solicitante A intenta decidir vía POST sobre su propia solicitud (con CSRF válido).
    HTTP 403 Forbidden (falta capacidad y denegación auto-decisión). 0 modificaciones.
    """
    accounts, _ = demo_accounts
    client_a, token_a = csrf_auth_client(accounts["demo_a"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client_a.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "Auto-aprobación indebida",
            "csrfmiddlewaretoken": token_a,
        },
    )

    assert response.status_code == 403

    # Auto-decisión con B3 o B4 sigue lanzando 403 (precedencia de permisos)
    resp_propia = client_a.post(
        url,
        {
            "action": "aceptar",
            "version": "\u00b2",
            "motivo": "Texto con byte\x00nulo",
            "csrfmiddlewaretoken": token_a,
        },
    )
    assert resp_propia.status_code == 403

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_14_objeto_visible_sin_permiso_con_contenido_invalido_retorna_403(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-14: Objeto visible sin permiso + contenido inválido (precedencia de autorización).

    Cuenta L (solo lectura, ve la solicitud) intenta decidir vía POST con CSRF válido
    sobre solicitud visible pero con acción desconocida o versión corrupta.
    HTTP 403 Forbidden (autorización evaluada antes que el contenido). 0 modificaciones en BD.
    """
    accounts, _ = demo_accounts
    client_l, token_l = csrf_auth_client(accounts["demo_l"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client_l.post(
        url,
        {
            "action": "accion_inexistente",
            "version": "version_corrupta",
            "motivo": "",
            "csrfmiddlewaretoken": token_l,
        },
    )

    assert response.status_code == 403

    # Sin permiso con B3 o B4 sigue lanzando 403 (precedencia de permisos)
    resp_l_b3 = client_l.post(
        url,
        {
            "action": "aceptar",
            "version": "1" * 4301,
            "motivo": "Texto con byte\x00nulo",
            "csrfmiddlewaretoken": token_l,
        },
    )
    assert resp_l_b3.status_code == 403

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_15_combinacion_grupos_auto_decision_retorna_403(
    csrf_auth_client: Any,
    demo_groups: dict[str, Group],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-15: Combinación de grupos intentando auto-decisión.

    Usuario con gastos.presentar + gastos.consultar_todas + gastos.decidir
    intenta decidir su propio gasto.
    HTTP 403 Forbidden (H2 auto-decisión denegada). 0 modificaciones en BD.
    """
    # Otorgar al usuario A pertenencia a operadora además de solicitante
    user_a = solicitud_a.solicitante
    user_a.groups.add(demo_groups["demo_operadora"])

    client_a, token_a = csrf_auth_client(user_a)
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client_a.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "Auto-aprobación con grupo operadora asignado",
            "csrfmiddlewaretoken": token_a,
        },
    )

    assert response.status_code == 403
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_16_capacidad_decidir_sin_visibilidad_retorna_404(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-16: Capacidad gastos.decidir sin visibilidad.

    Actor con gastos.decidir intenta decidir sobre solicitud no visible en visible_expenses.
    HTTP 404 Not Found (no filtra existencia). 0 modificaciones en BD.
    """
    accounts, _ = demo_accounts
    client_o, token_o = csrf_auth_client(accounts["demo_o"])

    # ID de solicitud inexistente
    inexistente_pk = 999999
    url = reverse("gastos:decidir", kwargs={"pk": inexistente_pk})

    response = client_o.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "Aprobando inexistente",
            "csrfmiddlewaretoken": token_o,
        },
    )

    assert response.status_code == 404

    # Simular que visible_expenses no incluye la solicitud para este actor
    with patch("gastos.services.visible_expenses") as mock_visible:
        mock_visible.return_value = SolicitudGasto.objects.none()
        url_real = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})
        resp = client_o.post(
            url_real,
            {
                "action": "aceptar",
                "version": "0",
                "motivo": "",
                "csrfmiddlewaretoken": token_o,
            },
        )
        assert resp.status_code == 404


@pytest.mark.django_db
def test_t04_17_parametros_manipulados_ignorados_por_servidor(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-17: Parámetros manipulados por cliente.

    Payload incluye autor_id=999, fecha="2020-01-01", estado_anterior="x".
    Servidor ignora campos inyectados; fija autor real de sesión, fecha de servidor
    y estados legítimos.
    """
    accounts, _ = demo_accounts
    client_o, token_o = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    response = client_o.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "Gasto aprobado",
            "autor_id": "999",
            "fecha": "2020-01-01 00:00:00",
            "estado_anterior": "invalido",
            "estado_resultante": "invalido",
            "csrfmiddlewaretoken": token_o,
        },
    )

    assert response.status_code == 302
    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.ACEPTADA
    assert solicitud_a.version == 1

    decision = solicitud_a.decisiones.first()
    assert decision.autor == accounts["demo_o"]
    assert decision.autor_id != 999
    assert decision.estado_anterior == EstadoSolicitud.PRESENTADA
    assert decision.estado_resultante == EstadoSolicitud.ACEPTADA


@pytest.mark.django_db
def test_t04_18_actor_autorizado_accion_desconocida_retorna_400(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-18: Actor autorizado + acción desconocida.

    O envía POST sobre solicitud visible de A con action="aprobar" o action="cancelar".
    HTTP 400 Bad Request. 0 modificaciones en BD.
    """
    accounts, _ = demo_accounts
    client_o, token_o = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    for bad_action in ("aprobar", "cancelar", "invalid"):
        response = client_o.post(
            url,
            {
                "action": bad_action,
                "version": "0",
                "motivo": "Texto cualquiera",
                "csrfmiddlewaretoken": token_o,
            },
        )
        assert response.status_code == 400

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_19_actor_autorizado_version_no_entera_o_negativa_retorna_400(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-19: Actor autorizado + versión no entera, booleana o negativa.

    O envía POST sobre solicitud visible con version="True", "1.5", "-1".
    HTTP 400 Bad Request (no trunca fracciones ni admite booleanos). 0 modificaciones en BD.
    """
    accounts, _ = demo_accounts
    client_o, token_o = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    for bad_version in ("True", "False", "1.5", "-1", "abc", "\u00b2", "1" * 4301):
        response = client_o.post(
            url,
            {
                "action": "aceptar",
                "version": bad_version,
                "motivo": "",
                "csrfmiddlewaretoken": token_o,
            },
        )
        assert response.status_code == 400

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_b4_motivo_con_caracter_nul_retorna_400(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """B4: POST con motivo que contiene carácter NUL (0x00) retorna 400 Bad Request.

    Verifica las tres acciones ('aceptar', 'postergar', 'rechazar') con CSRF estricto.
    Formulario con error en motivo; estado, versión e historial intactos (0 escrituras).
    """
    accounts, _ = demo_accounts
    client_o, token_o = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    for act in ("aceptar", "postergar", "rechazar"):
        response = client_o.post(
            url,
            {
                "action": act,
                "version": "0",
                "motivo": f"Motivo con byte\x00nulo para {act}",
                "csrfmiddlewaretoken": token_o,
            },
        )
        assert response.status_code == 400
        assert "error_decision" in response.context
        assert "motivo" in response.context["decision_form"].errors

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.PRESENTADA
    assert solicitud_a.version == 0
    assert not DecisionGasto.objects.exists()


@pytest.mark.django_db
def test_t04_20_decision_repetida_con_version_desactualizada_retorna_409(
    csrf_auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-20: Decisión repetida con versión desactualizada.

    Pantalla en v=0. Tras una decisión que avanzó a v=1, se reenvía la petición con v=0.
    HTTP 409 Conflict. Solicitud permanece en v=1; 0 eventos adicionales.
    """
    accounts, _ = demo_accounts
    client_o, token_o = csrf_auth_client(accounts["demo_o"])
    url = reverse("gastos:decidir", kwargs={"pk": solicitud_a.pk})

    # Primera decisión válida: pasa de v=0 a v=1 (postergada)
    resp1 = client_o.post(
        url,
        {
            "action": "postergar",
            "version": "0",
            "motivo": "Postergado para análisis",
            "csrfmiddlewaretoken": token_o,
        },
    )
    assert resp1.status_code == 302

    # Segunda decisión reintentando con versión vieja v=0
    resp2 = client_o.post(
        url,
        {
            "action": "aceptar",
            "version": "0",
            "motivo": "Intento con versión vieja",
            "csrfmiddlewaretoken": token_o,
        },
    )
    assert resp2.status_code == 409

    solicitud_a.refresh_from_db()
    assert solicitud_a.estado == EstadoSolicitud.POSTERGADA
    assert solicitud_a.version == 1
    assert solicitud_a.decisiones.count() == 1


@pytest.mark.django_db
def test_t04_26_consulta_historial_decisiones_y_aislamiento(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """T04-26: Consulta del historial de decisiones.

    Solicitud postergada y luego aceptada.
    A consulta detalle de su solicitud; O consulta detalle -> HTTP 200 OK.
    Ambos visualizan la tabla con los 2 eventos en orden cronológico con sus motivos y fechas.
    B recibe HTTP 404 al intentar consultar el detalle de A.
    """
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_b = accounts["demo_b"]
    user_o = accounts["demo_o"]

    # Crear eventos históricos
    solicitud_a.estado = EstadoSolicitud.ACEPTADA
    solicitud_a.version = 2
    solicitud_a.save()

    DecisionGasto.objects.create(
        solicitud=solicitud_a,
        autor=user_o,
        motivo="Postergado preliminar",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.POSTERGADA,
    )
    DecisionGasto.objects.create(
        solicitud=solicitud_a,
        autor=user_o,
        motivo="Aprobación definitiva",
        estado_anterior=EstadoSolicitud.POSTERGADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )

    url_detalle = reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})

    # Consulta por solicitante A (dueño de la solicitud)
    client_a = auth_client(user_a)
    resp_a = client_a.get(url_detalle)
    assert resp_a.status_code == 200
    assert "Historial de Decisiones" in resp_a.content.decode()
    assert "Postergado preliminar" in resp_a.content.decode()
    assert "Aprobación definitiva" in resp_a.content.decode()
    assert resp_a.context["decisiones"].count() == 2
    # El solicitante NO debe ver el formulario de decisión (H2 y estado terminal)
    assert resp_a.context["can_decide"] is False
    assert resp_a.context["decision_form"] is None

    # Consulta por operadora O
    client_o = auth_client(user_o)
    resp_o = client_o.get(url_detalle)
    assert resp_o.status_code == 200
    assert "Postergado preliminar" in resp_o.content.decode()
    assert "Aprobación definitiva" in resp_o.content.decode()
    # La solicitud ya está aceptada (terminal), por lo que tampoco O puede decidir
    assert resp_o.context["can_decide"] is False

    # Consulta por solicitante B sobre solicitud ajena no visible
    client_b = auth_client(user_b)
    resp_b = client_b.get(url_detalle)
    assert resp_b.status_code == 404


@pytest.mark.django_db
def test_formulario_decision_renderizado_segun_permisos(
    auth_client: Any,
    demo_accounts: tuple[dict[str, Any], str],
    solicitud_a: SolicitudGasto,
) -> None:
    """Verifica el renderizado condicional del formulario de decisión.

    - Operadora O sobre solicitud de A en 'presentada': can_decide=True, formulario visible.
    - Cuenta L sobre solicitud de A en 'presentada': can_decide=False, formulario no visible.
    - Solicitante A sobre su propia solicitud: can_decide=False, formulario no visible.
    """
    accounts, _ = demo_accounts
    url_detalle = reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})

    # Operadora O: ve formulario
    client_o = auth_client(accounts["demo_o"])
    resp_o = client_o.get(url_detalle)
    assert resp_o.status_code == 200
    assert resp_o.context["can_decide"] is True
    assert resp_o.context["decision_form"] is not None
    assert "Registrar Decisión Humana" in resp_o.content.decode()
    assert 'name="action" value="aceptar"' in resp_o.content.decode()

    # Cuenta de solo lectura L: no ve formulario
    client_l = auth_client(accounts["demo_l"])
    resp_l = client_l.get(url_detalle)
    assert resp_l.status_code == 200
    assert resp_l.context["can_decide"] is False
    assert resp_l.context["decision_form"] is None
    assert "Registrar Decisión Humana" not in resp_l.content.decode()

    # Solicitante A: no ve formulario sobre solicitud propia
    client_a = auth_client(accounts["demo_a"])
    resp_a = client_a.get(url_detalle)
    assert resp_a.status_code == 200
    assert resp_a.context["can_decide"] is False
    assert resp_a.context["decision_form"] is None
    assert "Registrar Decisión Humana" not in resp_a.content.decode()
