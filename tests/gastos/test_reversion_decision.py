"""Reversión operativa de una decisión de gasto y su concurrencia con el pago."""

import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.db import connections
from django.test import Client, override_settings
from django.urls import reverse

from gastos.models import EstadoSolicitud, PagoExterno, SolicitudGasto
from gastos.payments import PaymentInvalidExpenseStateError, registrar_pago_externo
from gastos.services import ConcurrencyConflictError, InvalidTransitionError, decide_expense
from tests.soporte_pagos import pdf_comprobante

MOTIVO_ORIGINAL = "Resultado inicial de la evaluación"
MOTIVO_REVERSION = "El respaldo se revisó en el trámite equivocado"


@pytest.fixture
def gasto_decidido(create_actor, solicitud_factory):
    def crear(accion="aceptar"):
        titular, _ = create_actor("titular_reversion", ["gastos.presentar"])
        operadora, actor = create_actor("operadora_reversion", ["gastos.decidir"])
        solicitud = solicitud_factory(solicitante=titular, estado=EstadoSolicitud.PRESENTADA)
        solicitud = decide_expense(
            actor=actor,
            solicitud_id=solicitud.pk,
            action=accion,
            expected_version=solicitud.version,
            motivo=MOTIVO_ORIGINAL,
        )
        return solicitud, titular, operadora, actor

    return crear


@pytest.fixture
def registrar_pago(actor_factory, fake_document_provider):
    _, actor_pago = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas", "documentos.incorporar")
    )

    def registrar(solicitud):
        return registrar_pago_externo(
            actor=actor_pago,
            solicitud_id=solicitud.pk,
            monto_bruto="1000.00",
            fecha_pago="2025-03-10",
            referencia_externa="TRF-0001",
            referencia_documental="doc-version-1",
            document_provider=fake_document_provider(),
            comprobante_bancario=pdf_comprobante(),
        )

    return registrar


def _panel_reversion(respuesta):
    html = respuesta.content.decode()
    return re.search(r'<details\b[^>]*\sid="revertir-decision"[^>]*>', html)


@pytest.mark.parametrize(
    ("accion", "estado_anterior"),
    [("aceptar", EstadoSolicitud.ACEPTADA), ("rechazar", EstadoSolicitud.RECHAZADA)],
)
def test_reversion_conserva_historial_bandeja_y_permite_una_nueva_decision(
    accion, estado_anterior, gasto_decidido, create_actor, auth_client
):
    solicitud, titular, _, _ = gasto_decidido(accion)
    operadora, _ = create_actor("segunda_operadora", ["gastos.decidir"])
    lector, _ = create_actor("lector_reversion", ["gastos.consultar_todas"])
    client = auth_client(operadora)
    detalle = reverse("gastos:detalle", args=[solicitud.pk])
    decidir = reverse("gastos:decidir", args=[solicitud.pk])
    bandeja = "atencion=1&q=laboratorio"
    query = urlencode({"bandeja": bandeja})
    original = solicitud.decisiones.get()
    panel = _panel_reversion(client.get(f"{detalle}?{query}"))
    assert panel is not None
    assert re.search(r"\sopen(?:\s|=|>)", panel.group()) is None

    datos = {
        "action": "revertir",
        "version": solicitud.version,
        "motivo": f"  {MOTIVO_REVERSION}  ",
    }
    respuesta = client.post(f"{decidir}?{query}", datos)
    assert respuesta.status_code == 302
    destino = urlsplit(respuesta.headers["Location"])
    assert destino.path == detalle
    assert parse_qs(destino.query) == {"bandeja": [bandeja]}

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == datos["version"] + 1
    reversion = solicitud.decisiones.exclude(pk=original.pk).get()
    original.refresh_from_db()
    assert (original.estado_resultante, original.motivo) == (estado_anterior, MOTIVO_ORIGINAL)
    assert not original.es_reversion
    assert (reversion.estado_anterior, reversion.estado_resultante) == (
        estado_anterior,
        EstadoSolicitud.PRESENTADA,
    )
    assert reversion.autor_id == operadora.pk
    assert reversion.motivo == MOTIVO_REVERSION
    assert reversion.es_reversion
    assert reversion.como_historial().tipo_evento == "reversion_decision_gasto"

    for usuario in (titular, lector):
        vista = auth_client(usuario).get(detalle)
        assert vista.status_code == 200
        assert "Decisión revertida" in vista.content.decode()
        assert MOTIVO_REVERSION.encode() in vista.content
        assert MOTIVO_ORIGINAL.encode() in vista.content

    assert client.post(decidir, datos).status_code == 409
    assert client.post(decidir, {**datos, "version": solicitud.version}).status_code == 409
    assert solicitud.decisiones.count() == 2
    nueva = client.post(
        decidir, {"action": "aceptar", "version": solicitud.version, "motivo": "Nueva decisión"}
    )
    assert nueva.status_code == 302
    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.ACEPTADA
    assert solicitud.version == datos["version"] + 2
    assert solicitud.decisiones.count() == 3


def test_reversion_denegada_segun_alcance_titularidad_y_csrf(
    gasto_decidido, create_actor, demo_groups, auth_client
):
    solicitud, titular, operadora, _ = gasto_decidido()
    lector, _ = create_actor("lector_reversion", ["gastos.consultar_todas"])
    ajeno, _ = create_actor("tercero_reversion", ["gastos.presentar"])
    detalle = reverse("gastos:detalle", args=[solicitud.pk])
    decidir = reverse("gastos:decidir", args=[solicitud.pk])
    datos = {"action": "revertir", "version": solicitud.version, "motivo": MOTIVO_REVERSION}

    for usuario in (titular, lector):
        cliente = auth_client(usuario)
        assert _panel_reversion(cliente.get(detalle)) is None
        assert cliente.post(decidir, datos).status_code == 403

    titular.groups.add(demo_groups["demo_operadora"])
    cliente_titular = auth_client(titular)
    assert _panel_reversion(cliente_titular.get(detalle)) is None
    assert cliente_titular.post(decidir, datos).status_code == 403

    assert auth_client(ajeno).post(decidir, datos).status_code == 404
    cliente_csrf = Client(enforce_csrf_checks=True)
    cliente_csrf.force_login(operadora)
    assert cliente_csrf.get(decidir).status_code == 405
    assert cliente_csrf.post(decidir, datos).status_code == 403

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.ACEPTADA
    assert solicitud.version == datos["version"]
    assert solicitud.decisiones.count() == 1


@pytest.mark.parametrize(
    ("motivo", "version", "estado_http"),
    [("   ", 1, 400), ("\x00", 1, 400), (MOTIVO_REVERSION, 0, 409)],
)
def test_reversion_invalida_reabre_panel_sin_cambiar_la_decision(
    gasto_decidido, auth_client, motivo, version, estado_http
):
    solicitud, _, operadora, _ = gasto_decidido()
    decidir = reverse("gastos:decidir", args=[solicitud.pk])
    respuesta = auth_client(operadora).post(
        decidir, {"action": "revertir", "version": version, "motivo": motivo}
    )
    assert respuesta.status_code == estado_http
    panel = _panel_reversion(respuesta)
    assert panel is not None
    assert re.search(r"\sopen(?:\s|=|>)", panel.group()) is not None
    if motivo == MOTIVO_REVERSION:
        assert MOTIVO_REVERSION.encode() in respuesta.content
    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.ACEPTADA
    assert solicitud.version == 1
    assert solicitud.decisiones.count() == 1


@pytest.mark.django_db(transaction=True)
@override_settings(AVISOS_EMAIL_ENABLED=False)
def test_pago_registrado_impide_revertir_incluso_desde_el_formulario_previo(
    gasto_decidido, registrar_pago, auth_client
):
    solicitud, _, operadora, _ = gasto_decidido()
    detalle = reverse("gastos:detalle", args=[solicitud.pk])
    decidir = reverse("gastos:decidir", args=[solicitud.pk])
    client = auth_client(operadora)
    assert _panel_reversion(client.get(detalle)) is not None

    pago = registrar_pago(solicitud)
    assert _panel_reversion(client.get(detalle)) is None
    respuesta = client.post(
        decidir,
        {"action": "revertir", "version": solicitud.version, "motivo": MOTIVO_REVERSION},
    )
    assert respuesta.status_code == 409
    assert b"Pagada" in respuesta.content
    assert _panel_reversion(respuesta) is None
    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.ACEPTADA
    assert solicitud.pago_externo.pk == pago.pk
    assert solicitud.decisiones.count() == 1


def _carrera(primera, segunda):
    barrera = Barrier(2)

    def ejecutar(operacion):
        try:
            barrera.wait(timeout=10)
            return operacion()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = [executor.submit(ejecutar, operacion) for operacion in (primera, segunda)]
        return [futuro.exception(timeout=25) or futuro.result() for futuro in resultados]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("contra_pago", [False, True], ids=["doble-confirmacion", "contra-pago"])
@override_settings(AVISOS_EMAIL_ENABLED=False)
def test_reversion_concurrente_sobre_la_misma_solicitud(
    gasto_decidido, registrar_pago, contra_pago
):
    solicitud, _, _, actor = gasto_decidido()
    version = solicitud.version

    def revertir():
        return decide_expense(
            actor=actor,
            solicitud_id=solicitud.pk,
            action="revertir",
            expected_version=version,
            motivo=MOTIVO_REVERSION,
        )

    if contra_pago:
        resultado_reversion, resultado_pago = _carrera(revertir, lambda: registrar_pago(solicitud))
        solicitud.refresh_from_db()
        if isinstance(resultado_pago, PagoExterno):
            assert isinstance(resultado_reversion, InvalidTransitionError)
            assert solicitud.estado == EstadoSolicitud.ACEPTADA
            assert solicitud.version == version
            assert solicitud.pago_externo.pk == resultado_pago.pk
            assert solicitud.decisiones.count() == 1
            return

        assert isinstance(resultado_pago, PaymentInvalidExpenseStateError)
        assert isinstance(resultado_reversion, SolicitudGasto)
    else:
        resultados = _carrera(revertir, revertir)
        assert sum(isinstance(resultado, ConcurrencyConflictError) for resultado in resultados) == 1
        assert sum(isinstance(resultado, SolicitudGasto) for resultado in resultados) == 1
        solicitud.refresh_from_db()

    assert not PagoExterno.objects.filter(solicitud=solicitud).exists()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == version + 1
    assert solicitud.decisiones.count() == 2
