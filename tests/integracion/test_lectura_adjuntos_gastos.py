"""Alcance del lector global en el detalle y las rutas documentales compartidas."""

from dataclasses import replace
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento, RevisionDocumento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.datos_transferencia import registrar_revision_datos_transferencia
from gastos.models import PagoExterno
from gastos.payments import consultar_pago_externo, registrar_pago_externo
from gastos.services import cerrar_solicitud_gasto
from identidad.services import actor_para_usuario
from tests.soporte_pagos import pdf_comprobante, pdf_constancia


@pytest.fixture
def lector(escenario_comun):
    usuario = get_user_model().objects.create_user(username="demo_l")
    usuario.groups.add(
        Group.objects.get_or_create(name="demo_lectura")[0],
        Group.objects.get_or_create(name="demo_facturacion_lectura")[0],
    )
    cliente = Client()
    cliente.force_login(usuario)
    return usuario, cliente


def _aportar(e, tipo, nombre, **kwargs):
    return incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=pdf_comprobante(nombre),
        tipo=tipo,
        procedencia=Documento.Procedencia.SOLICITANTE,
        **kwargs,
    )


@pytest.mark.django_db(transaction=True)
def test_lector_accede_a_tipos_autorizados_y_conserva_guardas_en_cierre(escenario_comun, lector):
    e = escenario_comun
    usuario, cliente = lector
    anterior = _aportar(e, Documento.Tipo.FACTURA_PROVEEDOR, "factura-anterior.pdf")
    factura = _aportar(
        e, Documento.Tipo.FACTURA_PROVEEDOR, "factura-definitiva.pdf", reemplaza_id=anterior.pk
    )
    presupuesto = _aportar(e, Documento.Tipo.PRESUPUESTO_PROFORMA, "presupuesto-demo.pdf")
    ticket = _aportar(e, Documento.Tipo.TICKET_NO_FISCAL, "ticket-demo.pdf")
    anexo = _aportar(e, Documento.Tipo.ANEXO_SOLICITUD, "anexo-reservado.pdf")
    cobro = incorporar(
        actor=e.actor_staff,
        referencia=f"facturacion:{e.factura.pk}",
        archivo=pdf_comprobante("cobro-reservado.pdf"),
        tipo=Documento.Tipo.COMPROBANTE_COBRO,
        procedencia=Documento.Procedencia.EXTERNO_BANCO,
    )
    registrar_revision_datos_transferencia(
        actor=e.actor_a,
        solicitud_id=e.gasto.pk,
        datos={
            "titular_nombre": "Beneficiario reservado demo",
            "identificacion": "20-00000000-0",
            "cbu_alias": "alias.reservado.demo",
            "correo_comprobante": "banco@example.invalid",
            "centro_costo": "Laboratorio",
        },
    )
    pago = registrar_pago_externo(
        actor=e.actor_staff,
        solicitud_id=e.gasto.pk,
        monto_bruto="100.00",
        monto_retencion_atp="5.00",
        fecha_pago=date(2026, 11, 15),
        referencia_documental=str(presupuesto.referencia_version),
        comprobante_bancario=pdf_comprobante("banco-reservado.pdf"),
        constancia_atp=pdf_constancia("constancia-atp-demo.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )
    consulta = consultar_pago_externo(actor_para_usuario(usuario), e.gasto.pk)
    assert consulta.tiene_comprobante_bancario
    assert consulta.comprobante_bancario_id is None
    assert consulta.comprobante_bancario_nombre == ""
    assert consulta.comprobante_bancario_tamano is None
    assert consulta.constancia_atp_id == pago.constancia_atp_id

    admitidos = (factura, presupuesto, ticket, pago.constancia_atp)
    excluidos = (anexo, pago.comprobante_bancario, cobro)
    for documento in (anterior, *admitidos):
        respuesta = cliente.get(reverse("documentos:archivo", args=[documento.pk]))
        assert respuesta.status_code == 200
        assert documento.nombre_original in respuesta["Content-Disposition"]
        assert b"".join(respuesta.streaming_content).startswith(b"%PDF")
    for documento in excluidos:
        assert cliente.get(reverse("documentos:archivo", args=[documento.pk])).status_code == 403
    inexistente = max(documento.pk for documento in (*admitidos, *excluidos)) + 1
    assert cliente.get(reverse("documentos:archivo", args=[inexistente])).status_code == 403
    for documento in (*admitidos, *excluidos):
        assert cliente.get(reverse("documentos:detalle", args=[documento.pk])).status_code == 403
        assert cliente.get(reverse("documentos:revision", args=[documento.pk])).status_code == 403
    assert cliente.post(reverse("documentos:revision", args=[factura.pk])).status_code == 403
    ruta_tramite = reverse("documentos:tramite", args=["gastos", e.gasto.pk])
    assert cliente.get(ruta_tramite).status_code == 403
    assert (
        cliente.post(
            ruta_tramite,
            {
                "archivo": pdf_comprobante(),
                "tipo": Documento.Tipo.FACTURA_PROVEEDOR,
                "procedencia": Documento.Procedencia.INTERNO_COOPERADORA,
            },
        ).status_code
        == 403
    )

    detalle = reverse("gastos:detalle", args=[e.gasto.pk])
    abierto = cliente.get(detalle).content.decode()
    for documento in admitidos:
        assert reverse("documentos:archivo", args=[documento.pk]) in abierto
    assert "factura-anterior.pdf · versión 1" in abierto
    assert 'id="visor-documento-dialogo"' in abierto
    assert "Incorporado" in abierto

    operador = replace(
        e.actor_staff,
        capabilities=e.actor_staff.capabilities | {"documentos.revisar", "gastos.cerrar"},
    )
    for documento in (factura, pago.constancia_atp, pago.comprobante_bancario):
        revisar(
            actor=operador,
            documento_id=documento.pk,
            resultado=RevisionDocumento.Resultado.ACEPTADO,
            motivo="Revisión sintética reservada",
            revision_esperada=0,
        )
    cerrar_solicitud_gasto(
        actor=operador, solicitud_id=e.gasto.pk, expected_version=e.gasto.version
    )
    cerrado = cliente.get(detalle).content.decode()
    assert "Documentación obligatoria verificada y aceptada." in cerrado
    for html in (abierto, cerrado):
        assert "/revision/" not in html
        assert "Descarga no disponible" not in html
        assert "alias.reservado.demo" not in html
        for documento in excluidos:
            assert documento.nombre_original not in html
            assert reverse("documentos:archivo", args=[documento.pk]) not in html

    # El permiso general preexistente sigue autorizando el archivo de Facturación.
    usuario.groups.add(Group.objects.get_or_create(name="demo_documentos_descarga")[0])
    respuesta_general = cliente.get(reverse("documentos:archivo", args=[cobro.pk]))
    assert respuesta_general.status_code == 200
    respuesta_general.close()


@pytest.mark.django_db
def test_lector_tiene_visor_con_solo_la_constancia_atp_del_pago(escenario_comun, lector):
    e = escenario_comun
    _, cliente = lector
    atp = incorporar(
        actor=e.actor_staff,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=pdf_constancia(),
        tipo=Documento.Tipo.CONSTANCIA_RETENCION_ATP,
        procedencia=Documento.Procedencia.EXTERNO_ATP,
    )
    PagoExterno.objects.create(
        solicitud=e.gasto,
        importe="95.00",
        monto_bruto="100.00",
        monto_retencion_atp="5.00",
        fecha_pago=date(2026, 11, 15),
        referencia_documental="referencia-historica-prueba",
        huella_idempotencia="a" * 64,
        constancia_atp=atp,
    )
    respuesta = cliente.get(reverse("gastos:detalle", args=[e.gasto.pk]))
    assert respuesta.status_code == 200
    assert not respuesta.context["detalle_versiones_actuales"]
    assert respuesta.context["puede_descargar_constancia_atp"] is True
    contenido = respuesta.content.decode()
    assert 'id="visor-documento-dialogo"' in contenido
    assert reverse("documentos:archivo", args=[atp.pk]) in contenido


@pytest.mark.django_db
@pytest.mark.parametrize("capacidad", ["gastos.consultar_adjuntos", "documentos.descargar"])
def test_capacidad_sola_no_habilita_la_ruta_compartida(escenario_comun, monkeypatch, capacidad):
    e = escenario_comun
    factura = _aportar(e, Documento.Tipo.FACTURA_PROVEEDOR, "factura-demo.pdf")
    actor = replace(e.actor_a, capabilities=frozenset({"gastos.consultar_propias", capacidad}))
    monkeypatch.setattr("documentos.views.resolve_actor", lambda request: actor)
    assert Client().get(reverse("documentos:archivo", args=[factura.pk])).status_code == 403
