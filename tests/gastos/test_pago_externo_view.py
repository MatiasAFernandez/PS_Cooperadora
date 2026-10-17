"""Presentación del pago externo en el detalle visible de un gasto."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from comunes.contracts import EventoHistorialDTO
from gastos.models import DecisionGasto, EstadoSolicitud
from gastos.payments import registrar_pago_externo
from identidad.services import Actor

User = get_user_model()


@pytest.mark.django_db
def test_detalle_muestra_pago_y_cronologia_sin_referencia_documental(
    create_actor: Any,
    solicitud_factory: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
    auth_client: Any,
) -> None:
    """La persona con visibilidad de consulta ve el pago sin permiso de registro."""
    user, read_actor = create_actor(
        "consulta_pago_ui",
        ["gastos.presentar", "gastos.consultar_propias"],
    )
    payment_actor = Actor(
        subject_id=user.pk,
        capabilities=read_actor.capabilities | {"gastos.registrar_pago"},
    )
    solicitud = solicitud_factory(
        estado=EstadoSolicitud.ACEPTADA,
        solicitante=user,
        monto="900.00",
    )
    decision_author = User.objects.create_user(username="autor_decision_ui")
    DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=decision_author,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
        motivo="Compra autorizada para la demo.",
    )

    referencia_documental = "doc-privado-pago-ui-01"
    registrar_pago_externo(
        actor=payment_actor,
        solicitud_id=solicitud.pk,
        importe="825.40",
        fecha_pago=date(2026, 10, 14),
        referencia_externa="ref-sintetica-001",
        referencia_documental=referencia_documental,
        document_provider=fake_document_provider(),
    )

    response = auth_client(user, read_actor).get(
        reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    )

    assert response.status_code == 200
    assert response.context["tramite_id"] == f"gastos:{solicitud.pk}"
    assert response.context["pago_consulta"].importe == Decimal("825.40")
    assert not hasattr(response.context["pago_consulta"], "referencia_documental")
    cronologia = response.context["cronologia"]
    assert all(isinstance(evento, EventoHistorialDTO) for evento in cronologia)
    assert [evento.tipo_evento for evento in cronologia] == [
        "decision_gasto",
        "pago_externo_registrado",
    ]
    assert [evento.tramite_ref for evento in cronologia] == [
        f"gastos:{solicitud.pk}",
        f"gastos:{solicitud.pk}",
    ]
    assert cronologia[0].actor_id == str(decision_author.pk)
    assert cronologia[0].estado_resultante == EstadoSolicitud.ACEPTADA
    assert "Estado anterior: Presentada" in cronologia[0].motivo_o_detalle
    assert "Compra autorizada para la demo." in cronologia[0].motivo_o_detalle
    assert cronologia[1].actor_id == str(user.pk)
    assert cronologia[1].estado_resultante == solicitud.estado
    assert "Importe: 825.40 ARS" in cronologia[1].motivo_o_detalle
    assert "Fecha del hecho: 2026-10-14" in cronologia[1].motivo_o_detalle
    assert "Referencia externa: ref-sintetica-001" in cronologia[1].motivo_o_detalle
    assert [evento.fecha_hora for evento in cronologia] == sorted(
        evento.fecha_hora for evento in cronologia
    )
    assert not hasattr(cronologia[1], "referencia_documental")

    content = response.content
    assert b"Pago externo registrado" in content
    assert b"825,40 ARS" in content
    assert b"825.40 ARS" not in content
    assert b"14/10/2026" in content
    assert b"ref-sintetica-001" in content
    assert b"Compra autorizada para la demo." in content
    assert b"Estado anterior: Presentada" in content
    assert b"Importe: 825.40 ARS" in content
    assert f"Usuario #{user.pk}".encode() in content
    assert b"no confirma que el importe estimado est\xc3\xa9 saldado" in content
    assert b"no equivale a aprobaci\xc3\xb3n documental" in content
    assert referencia_documental.encode() not in content
    assert b"huella_idempotencia" not in content


@pytest.mark.django_db
def test_error_de_decision_conserva_pago_y_cronologia_en_el_detalle(
    create_actor: Any,
    solicitud_factory: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
    auth_client: Any,
) -> None:
    """Un POST inválido conserva el identificador y los datos informativos del pago."""
    user, decision_actor = create_actor(
        "operador_error_pago_ui",
        ["gastos.consultar_todas", "gastos.decidir"],
    )
    payment_actor = Actor(
        subject_id=user.pk,
        capabilities=decision_actor.capabilities | {"gastos.registrar_pago"},
    )
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, monto="900.00")
    decision_author = User.objects.create_user(username="autor_decision_error_ui")
    DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=decision_author,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
        motivo="Compra autorizada para la demo.",
    )
    referencia_documental = "doc-privado-error-ui-01"
    registrar_pago_externo(
        actor=payment_actor,
        solicitud_id=solicitud.pk,
        importe="825.40",
        fecha_pago=date(2026, 10, 14),
        referencia_externa="ref-error-sintetica-001",
        referencia_documental=referencia_documental,
        document_provider=fake_document_provider(),
    )

    response = auth_client(user, decision_actor).post(
        reverse("gastos:decidir", kwargs={"pk": solicitud.pk}),
        {"action": "accion_invalida", "version": str(solicitud.version), "motivo": ""},
    )

    assert response.status_code == 400
    assert response.context["tramite_id"] == f"gastos:{solicitud.pk}"
    assert response.context["pago_consulta"].importe == Decimal("825.40")
    assert [evento.tipo_evento for evento in response.context["cronologia"]] == [
        "decision_gasto",
        "pago_externo_registrado",
    ]
    assert b"Acci\xc3\xb3n de decisi\xc3\xb3n desconocida" in response.content
    assert b"825,40 ARS" in response.content
    assert b"ref-error-sintetica-001" in response.content
    assert referencia_documental.encode() not in response.content
