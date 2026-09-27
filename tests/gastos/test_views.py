"""Pruebas de vistas de gastos (alta, listado, detalle, permisos y filtrado)."""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gastos.models import EstadoSolicitud, SolicitudGasto

User = get_user_model()


@pytest.mark.django_db
def test_alta_solicitud_valida(create_actor: Any, csrf_auth_client: Any) -> None:
    """I1-R01: Alta válida con capacidad gastos.presentar, sesión y CSRF válidos crea solicitud."""
    user, actor = create_actor("solicitante_a", ["gastos.presentar", "gastos.consultar_propias"])
    client, csrf_token = csrf_auth_client(user, actor)

    url = reverse("gastos:presentar")
    data = {
        "csrfmiddlewaretoken": csrf_token,
        "concepto": "Resmas de papel para secretaría",
        "monto_estimado": "45000.00",
        "unidad_requirente": "Secretaría Académica",
    }
    response = client.post(url, data)

    assert response.status_code == 302
    assert SolicitudGasto.objects.count() == 1

    solicitud = SolicitudGasto.objects.first()
    assert solicitud is not None
    assert response.url == reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    assert solicitud.concepto == "Resmas de papel para secretaría"
    assert solicitud.monto_estimado == Decimal("45000.00")
    assert solicitud.unidad_requirente == "Secretaría Académica"
    assert solicitud.solicitante == user
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert solicitud.fecha_creacion is not None


@pytest.mark.django_db
def test_alta_solicitud_campos_invalidos_no_crea(create_actor: Any, auth_client: Any) -> None:
    """I1-R01: Concepto vacío, unidad vacía o importe inválido no persisten."""
    user, actor = create_actor("solicitante_val", ["gastos.presentar", "gastos.consultar_propias"])
    client = auth_client(user, actor)
    url = reverse("gastos:presentar")

    # Concepto vacío
    resp1 = client.post(
        url, {"concepto": "   ", "monto_estimado": "1000.00", "unidad_requirente": "Lab"}
    )
    assert resp1.status_code == 200
    assert "concepto" in resp1.context["form"].errors
    assert SolicitudGasto.objects.count() == 0

    # Unidad vacía
    resp2 = client.post(
        url, {"concepto": "Insumos", "monto_estimado": "1000.00", "unidad_requirente": ""}
    )
    assert resp2.status_code == 200
    assert "unidad_requirente" in resp2.context["form"].errors
    assert SolicitudGasto.objects.count() == 0

    # Importe cero o negativo
    resp3 = client.post(
        url, {"concepto": "Insumos", "monto_estimado": "0.00", "unidad_requirente": "Lab"}
    )
    assert resp3.status_code == 200
    assert "monto_estimado" in resp3.context["form"].errors
    assert SolicitudGasto.objects.count() == 0

    resp4 = client.post(
        url, {"concepto": "Insumos", "monto_estimado": "-150.00", "unidad_requirente": "Lab"}
    )
    assert resp4.status_code == 200
    assert "monto_estimado" in resp4.context["form"].errors
    assert SolicitudGasto.objects.count() == 0


@pytest.mark.django_db
def test_ct06_manipulacion_payload_solicitante_estado_version_y_fecha(
    create_actor: Any, csrf_auth_client: Any
) -> None:
    """CT-06: Intento de manipular solicitante, estado, version o fecha vía POST con CSRF válido."""
    user, actor = create_actor("solicitante_ct06", ["gastos.presentar", "gastos.consultar_propias"])
    otro_user = User.objects.create_user("otro_usuario")
    client, csrf_token = csrf_auth_client(user, actor)

    url = reverse("gastos:presentar")
    payload = {
        "csrfmiddlewaretoken": csrf_token,
        "concepto": "Gasto con payload manipulado",
        "monto_estimado": "25000.00",
        "unidad_requirente": "Sistemas",
        "solicitante": otro_user.pk,
        "solicitante_id": otro_user.pk,
        "estado": EstadoSolicitud.ACEPTADA,
        "version": 15,
        "fecha_creacion": "2020-01-01 00:00:00",
    }

    response = client.post(url, payload)
    assert response.status_code == 302

    solicitud = SolicitudGasto.objects.get(concepto="Gasto con payload manipulado")
    assert solicitud.solicitante == user
    assert solicitud.solicitante != otro_user
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    # Verificación de que la fecha fue asignada por el servidor y no la inyectada
    assert solicitud.fecha_creacion.strftime("%Y-%m-%d") != "2020-01-01"


@pytest.mark.django_db
def test_ct06_inyeccion_capacidades_cliente_no_escala_privilegios(
    create_actor: Any, csrf_auth_client: Any
) -> None:
    """CT-06: Inyección de capabilities en payload/headers por actor no autorizado no da acceso."""
    user_no_autorizado, actor_no_autorizado = create_actor(
        "cuenta_sin_presentar", ["gastos.consultar_propias"]
    )
    client, csrf_token = csrf_auth_client(user_no_autorizado, actor_no_autorizado)

    url = reverse("gastos:presentar")
    payload = {
        "csrfmiddlewaretoken": csrf_token,
        "concepto": "Gasto con escalada de privilegios",
        "monto_estimado": "30000.00",
        "unidad_requirente": "Auditoría",
        "capabilities": ["gastos.presentar", "gastos.decidir"],
    }

    response = client.post(
        url,
        payload,
        HTTP_X_CAPABILITIES="gastos.presentar",
    )
    assert response.status_code == 403
    assert not SolicitudGasto.objects.filter(concepto="Gasto con escalada de privilegios").exists()


@pytest.mark.django_db
def test_aislamiento_consultas_propias_a_y_b(create_actor: Any, auth_client: Any) -> None:
    """I1-R02 / ID-R02 / CT-04: A y B aislados recíprocamente en lista y detalle (404)."""
    user_a, actor_a = create_actor(
        "solicitante_a", ["gastos.presentar", "gastos.consultar_propias"]
    )
    user_b, actor_b = create_actor(
        "solicitante_b", ["gastos.presentar", "gastos.consultar_propias"]
    )

    solicitud_a = SolicitudGasto.objects.create(
        concepto="Gasto exclusivo de A",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Unidad A",
        solicitante=user_a,
    )
    solicitud_b = SolicitudGasto.objects.create(
        concepto="Gasto exclusivo de B",
        monto_estimado=Decimal("8000.00"),
        unidad_requirente="Unidad B",
        solicitante=user_b,
    )

    client_a = auth_client(user_a, actor_a)
    client_b = auth_client(user_b, actor_b)

    # Listado para A
    resp_list_a = client_a.get(reverse("gastos:lista"))
    assert resp_list_a.status_code == 200
    solicitudes_a = list(resp_list_a.context["solicitudes"])
    assert solicitud_a in solicitudes_a
    assert solicitud_b not in solicitudes_a

    # Listado para B
    resp_list_b = client_b.get(reverse("gastos:lista"))
    assert resp_list_b.status_code == 200
    solicitudes_b = list(resp_list_b.context["solicitudes"])
    assert solicitud_b in solicitudes_b
    assert solicitud_a not in solicitudes_b

    # Detalle directo propio
    assert client_a.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})).status_code == 200
    assert client_b.get(reverse("gastos:detalle", kwargs={"pk": solicitud_b.pk})).status_code == 200

    # Detalle directo ajeno: responde 404 estricto (no 403, para no filtrar existencia)
    assert client_b.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})).status_code == 404
    assert client_a.get(reverse("gastos:detalle", kwargs={"pk": solicitud_b.pk})).status_code == 404

    # Identificador inexistente responde 404
    assert client_a.get(reverse("gastos:detalle", kwargs={"pk": 99999})).status_code == 404


@pytest.mark.django_db
def test_consulta_global_operadora_y_lectura(create_actor: Any, auth_client: Any) -> None:
    """CT-04 / Consulta global: Operadora O y Cuenta L ven todas las solicitudes."""
    user_a, _ = create_actor("solicitante_a", ["gastos.presentar", "gastos.consultar_propias"])
    user_b, _ = create_actor("solicitante_b", ["gastos.presentar", "gastos.consultar_propias"])
    user_o, actor_o = create_actor("operadora_o", ["gastos.consultar_todas", "gastos.decidir"])
    user_l, actor_l = create_actor("cuenta_l", ["gastos.consultar_todas"])

    solicitud_a = SolicitudGasto.objects.create(
        concepto="Gasto de A",
        monto_estimado=Decimal("1000.00"),
        unidad_requirente="Unidad A",
        solicitante=user_a,
    )
    solicitud_b = SolicitudGasto.objects.create(
        concepto="Gasto de B",
        monto_estimado=Decimal("2000.00"),
        unidad_requirente="Unidad B",
        solicitante=user_b,
    )

    client_o = auth_client(user_o, actor_o)
    client_l = auth_client(user_l, actor_l)

    # Operadora O
    resp_o = client_o.get(reverse("gastos:lista"))
    assert resp_o.status_code == 200
    solicitudes_o = list(resp_o.context["solicitudes"])
    assert solicitud_a in solicitudes_o
    assert solicitud_b in solicitudes_o
    assert client_o.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})).status_code == 200
    assert client_o.get(reverse("gastos:detalle", kwargs={"pk": solicitud_b.pk})).status_code == 200

    # Cuenta L
    resp_l = client_l.get(reverse("gastos:lista"))
    assert resp_l.status_code == 200
    solicitudes_l = list(resp_l.context["solicitudes"])
    assert solicitud_a in solicitudes_l
    assert solicitud_b in solicitudes_l
    assert client_l.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk})).status_code == 200
    assert client_l.get(reverse("gastos:detalle", kwargs={"pk": solicitud_b.pk})).status_code == 200


@pytest.mark.django_db
def test_usuario_autenticado_sin_capacidades(create_actor: Any, auth_client: Any) -> None:
    """Usuario sin grupos ni capacidades de gastos no ve ninguna solicitud."""
    user_a, _ = create_actor("solicitante_a", ["gastos.presentar", "gastos.consultar_propias"])
    solicitud_a = SolicitudGasto.objects.create(
        concepto="Gasto de A",
        monto_estimado=Decimal("1000.00"),
        unidad_requirente="Unidad A",
        solicitante=user_a,
    )

    user_c, actor_c = create_actor("usuario_sin_permisos", [])
    client_c = auth_client(user_c, actor_c)

    resp_list = client_c.get(reverse("gastos:lista"))
    assert resp_list.status_code == 200
    assert list(resp_list.context["solicitudes"]) == []

    resp_detail = client_c.get(reverse("gastos:detalle", kwargs={"pk": solicitud_a.pk}))
    assert resp_detail.status_code == 404


@pytest.mark.django_db
def test_denegacion_presentacion_sin_permiso_con_sesion_y_csrf_validos(
    create_actor: Any, csrf_auth_client: Any
) -> None:
    """Con sesión y CSRF válidos, Operadora O y Cuenta L reciben 403 y no escriben en BD."""
    user_o, actor_o = create_actor("operadora_o", ["gastos.consultar_todas", "gastos.decidir"])
    user_l, actor_l = create_actor("cuenta_l", ["gastos.consultar_todas"])

    url = reverse("gastos:presentar")

    # 1. Operadora O
    client_o, csrf_token_o = csrf_auth_client(user_o, actor_o)
    resp_get_o = client_o.get(url)
    assert resp_get_o.status_code == 403

    resp_post_o = client_o.post(
        url,
        {
            "csrfmiddlewaretoken": csrf_token_o,
            "concepto": "Intento no autorizado por O",
            "monto_estimado": "5000.00",
            "unidad_requirente": "Mantenimiento",
        },
    )
    assert resp_post_o.status_code == 403

    # 2. Cuenta L
    client_l, csrf_token_l = csrf_auth_client(user_l, actor_l)
    resp_get_l = client_l.get(url)
    assert resp_get_l.status_code == 403

    resp_post_l = client_l.post(
        url,
        {
            "csrfmiddlewaretoken": csrf_token_l,
            "concepto": "Intento no autorizado por L",
            "monto_estimado": "7500.00",
            "unidad_requirente": "Mantenimiento",
        },
    )
    assert resp_post_l.status_code == 403

    # Verificación explícita de ausencia absoluta de escrituras en base de datos
    assert not SolicitudGasto.objects.exists()


@pytest.mark.django_db
def test_ausencia_actor_alta_lista_detalle(settings: Any) -> None:
    """Sin actor: demo habilitada redirige a login; demo deshabilitada retorna 403."""
    user = User.objects.create_user("solicitante_base")
    solicitud = SolicitudGasto.objects.create(
        concepto="Gasto de prueba",
        monto_estimado=Decimal("500.00"),
        unidad_requirente="Unidad",
        solicitante=user,
    )

    anon_client = Client()
    url_lista = reverse("gastos:lista")
    url_presentar = reverse("gastos:presentar")
    url_detalle = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    # 1. Con DEMO_IDENTITY_ENABLED = True
    settings.DEMO_IDENTITY_ENABLED = True
    resp_l = anon_client.get(url_lista)
    assert resp_l.status_code == 302
    assert reverse("identidad:login") in resp_l.url

    resp_p = anon_client.get(url_presentar)
    assert resp_p.status_code == 302

    resp_d = anon_client.get(url_detalle)
    assert resp_d.status_code == 302

    resp_post = anon_client.post(
        url_presentar,
        {"concepto": "Intento anónimo", "monto_estimado": "100.00", "unidad_requirente": "Unidad"},
    )
    assert resp_post.status_code == 302
    assert SolicitudGasto.objects.count() == 1  # Solo la creada inicialmente

    # 2. Con DEMO_IDENTITY_ENABLED = False
    settings.DEMO_IDENTITY_ENABLED = False
    resp_l_off = anon_client.get(url_lista)
    assert resp_l_off.status_code == 403

    resp_p_off = anon_client.get(url_presentar)
    assert resp_p_off.status_code == 403

    resp_d_off = anon_client.get(url_detalle)
    assert resp_d_off.status_code == 403

    resp_post_off = anon_client.post(
        url_presentar,
        {"concepto": "Intento anónimo", "monto_estimado": "100.00", "unidad_requirente": "Unidad"},
    )
    assert resp_post_off.status_code == 403
    assert SolicitudGasto.objects.count() == 1  # Solo la creada inicialmente
