"""Documentos y proforma en el seguimiento del pago (Issue #74 / SPEC-013).

Comprueba que una proforma se distingue de la factura definitiva posterior, que
la factura se incorpora y revisa como documento nuevo sin modificar el pago, y
que la falta de respaldo habilitado explica el bloqueo y el camino según
permisos. Usa almacenamiento temporal y archivos sintéticos.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documentos.models import Documento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.contracts import OpcionDocumental
from gastos.models import EstadoSolicitud, PagoExterno
from gastos.payments import registrar_pago_externo
from identidad.services import Actor
from tests.soporte_gastos import crear_gasto_sintetico


def _pdf(nombre: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre, b"%PDF-1.7\nEjemplo ficticio\n%%EOF", "application/pdf"
    )


@pytest.fixture
def escenario_documental(settings, tmp_path, actor_factory) -> SimpleNamespace:
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "privado"
    titular, actor_titular = actor_factory(
        (
            "gastos.presentar",
            "gastos.consultar_propias",
            "documentos.incorporar",
            "documentos.consultar_metadatos",
            "documentos.ver_metadatos",
            "documentos.recuperar_contenido",
        )
    )
    pago_user, actor_pago = actor_factory(
        (
            "gastos.registrar_pago",
            "gastos.consultar_todas",
            "documentos.incorporar",
            "documentos.consultar_metadatos",
            "documentos.ver_metadatos",
        )
    )
    gasto = crear_gasto_sintetico(
        concepto="Gasto sintético para seguimiento documental",
        monto_estimado="2500.00",
        unidad_requirente="Unidad sintética documental",
        solicitante=titular,
        estado=EstadoSolicitud.ACEPTADA,
    )
    return SimpleNamespace(
        titular=titular,
        actor_titular=actor_titular,
        pago_user=pago_user,
        actor_pago=actor_pago,
        gasto=gasto,
    )


def _proforma(e: SimpleNamespace) -> Documento:
    return incorporar(
        actor=e.actor_titular,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=_pdf("proforma-sintetica-74.pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )


def _factura(e: SimpleNamespace) -> Documento:
    return incorporar(
        actor=e.actor_titular,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=_pdf("factura-definitiva-74.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )


def _pago_con_proforma(e: SimpleNamespace, proveedor: object) -> PagoExterno:
    return registrar_pago_externo(
        actor=e.actor_pago,
        solicitud_id=e.gasto.pk,
        importe="1234.56",
        fecha_pago=date(2026, 10, 27),
        referencia_externa="TRF-DOC-74",
        referencia_documental="doc-proforma-74",
        document_provider=proveedor,
    )


def test_proforma_y_factura_posterior_se_distinguen_sin_modificar_el_pago(
    escenario_documental: SimpleNamespace,
    fake_document_provider,
    settings,
    monkeypatch,
    auth_client,
) -> None:
    e = escenario_documental
    proforma = _proforma(e)
    proveedor = fake_document_provider(
        tipo_documento="proforma",
        opciones=[
            OpcionDocumental(
                referencia_documental="doc-proforma-74",
                tipo_documento="proforma",
                etiqueta="Proforma sintética 74",
            )
        ],
    )
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = proveedor
    pago = _pago_con_proforma(e, proveedor)

    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: e.actor_pago)
    client = auth_client(e.pago_user, e.actor_pago)
    url = reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})

    primera = client.get(url)
    assert primera.status_code == 200
    assert primera.context["respaldo_categoria"] == "presupuesto"
    assert primera.context["factura_vigente"] is None
    assert primera.context["mostrar_seguimiento_factura"] is True
    contenido = primera.content.decode()
    assert proforma.nombre_original in contenido
    assert "Presupuesto o proforma" in contenido
    assert "Seguimiento de factura definitiva" in contenido
    assert "Una proforma no es una factura definitiva" in contenido
    assert "No hay una factura definitiva vigente incorporada" in contenido
    assert "no cierra el trámite" in contenido

    factura = _factura(e)
    revisor = Actor(
        e.titular.pk,
        e.actor_titular.capabilities | {"documentos.revisar"},
    )
    revisar(
        actor=revisor,
        documento_id=factura.pk,
        resultado="ACEPTADO",
        motivo="",
        revision_esperada=0,
    )

    segunda = client.get(url)
    assert segunda.status_code == 200
    assert segunda.context["factura_vigente"].documento_id == factura.pk
    assert segunda.context["respaldo_categoria"] == "presupuesto"
    contenido_posterior = segunda.content.decode()
    assert "Hay una factura vigente incorporada" in contenido_posterior
    assert "Último resultado propio de la factura" in contenido_posterior
    assert "Factura de proveedor" in contenido_posterior
    assert "Aceptado" in contenido_posterior
    assert "no modifica el pago" in contenido_posterior

    pago.refresh_from_db()
    assert pago.referencia_documental == "doc-proforma-74"
    assert PagoExterno.objects.get(solicitud_id=e.gasto.pk).referencia_documental == (
        "doc-proforma-74"
    )
    assert not hasattr(segunda.context["pago_consulta"], "referencia_documental")


def test_pagina_de_pago_sin_permiso_de_incorporacion_indica_a_quien_acudir(
    escenario_documental: SimpleNamespace,
    actor_factory,
    fake_document_provider,
    settings,
    monkeypatch,
    auth_client,
) -> None:
    e = escenario_documental
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(opciones=[])
    usuario, actor = actor_factory(
        (
            "gastos.registrar_pago",
            "gastos.consultar_todas",
            "documentos.ver_metadatos",
        )
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)

    response = auth_client(usuario, actor).get(
        reverse("gastos:pagar", kwargs={"pk": e.gasto.pk})
    )

    assert response.status_code == 200
    contenido = response.content.decode()
    assert "No hay opciones documentales disponibles" in contenido
    assert "Solicitá a un perfil con permiso de incorporación documental" in contenido
    assert reverse("gastos:documentos", kwargs={"pk": e.gasto.pk}) not in contenido


def test_pagina_de_pago_sin_opciones_muestra_camino(
    escenario_documental: SimpleNamespace,
    fake_document_provider,
    settings,
    monkeypatch,
    auth_client,
) -> None:
    e = escenario_documental
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(opciones=[])
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: e.actor_pago)

    response = auth_client(e.pago_user, e.actor_pago).get(
        reverse("gastos:pagar", kwargs={"pk": e.gasto.pk})
    )

    assert response.status_code == 200
    contenido = response.content.decode()
    assert "No hay opciones documentales disponibles" in contenido
    assert "Aportar factura, presupuesto o proforma" in contenido
    assert reverse("gastos:documentos", kwargs={"pk": e.gasto.pk}) in contenido
    assert 'type="submit" class="btn" disabled' in contenido
