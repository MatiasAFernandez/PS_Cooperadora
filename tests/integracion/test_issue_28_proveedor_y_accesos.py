"""Preparación de #28: proveedor real y documentos, sin declarar recorridos completos."""

from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from documentos.c01 import TIPOS_C01, ProveedorDocumentalGastos
from documentos.models import Documento
from documentos.services import TIPOS_ELEGIBLES_PAGO_GASTOS, incorporar
from gastos.contracts import DocumentVerificationError
from gastos.models import EventoPagoExterno, PagoExterno
from gastos.payments import registrar_pago_externo
from tests.soporte_gastos import crear_gasto_sintetico

from .helpers import archivo_pdf


def cargar_gasto(e, tipo=Documento.Tipo.FACTURA_PROVEEDOR, **extras):
    return incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=archivo_pdf(),
        tipo=tipo,
        procedencia="SOLICITANTE",
        **extras,
    )


def pagar(e, documento, proveedor=None):
    return registrar_pago_externo(
        actor=e.actor_staff,
        solicitud_id=e.gasto.pk,
        importe="1.00",
        fecha_pago=date(2026, 10, 16),
        referencia_externa="SINTETICA",
        referencia_documental=str(documento.referencia_version),
        document_provider=proveedor or ProveedorDocumentalGastos(),
    )


def test_c01_traduce_catalogo_y_excluye_ticket(escenario_comun):
    e = escenario_comun
    factura = cargar_gasto(e)
    presupuesto = cargar_gasto(e, Documento.Tipo.PRESUPUESTO_PROFORMA)
    ticket = cargar_gasto(e, Documento.Tipo.TICKET_NO_FISCAL)
    proveedor = ProveedorDocumentalGastos()
    opciones = proveedor.listar_opciones_para_pago(actor=e.actor_staff, gasto=e.gasto)
    assert {o.referencia_documental for o in opciones} == {
        str(factura.referencia_version),
        str(presupuesto.referencia_version),
    }
    assert {o.tipo_documento for o in opciones} == {"factura", "presupuesto"}
    assert set(TIPOS_C01) == TIPOS_ELEGIBLES_PAGO_GASTOS
    assert (
        proveedor.listar_opciones_para_pago(
            actor=e.actor_staff, gasto=e.gasto, tipos_admitidos=("proforma", "ticket")
        )
        == []
    )
    with pytest.raises(DocumentVerificationError):
        pagar(e, ticket)
    assert not PagoExterno.objects.exists()
    assert not EventoPagoExterno.objects.exists()
    pago = pagar(e, factura)
    assert pago.referencia_documental == str(factura.referencia_version)
    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1
    assert pagar(e, factura, proveedor=object()).pk == pago.pk  # Reintento sin proveedor.


def test_reemplazo_conserva_archivos_y_rechaza_version_obsoleta(escenario_comun):
    e = escenario_comun
    anterior = cargar_gasto(e)
    nuevo = cargar_gasto(e, reemplaza_id=anterior.pk)
    assert nuevo.version == 2 and anterior.version == 1
    assert nuevo.serie == anterior.serie
    assert nuevo.referencia_version != anterior.referencia_version
    assert (e.raiz / anterior.archivo).exists()
    assert (e.raiz / nuevo.archivo).exists()
    with pytest.raises(DocumentVerificationError):
        pagar(e, anterior)
    assert not PagoExterno.objects.exists()
    assert pagar(e, nuevo).referencia_documental == str(nuevo.referencia_version)
    with pytest.raises(IntegrityError), transaction.atomic():
        Documento.objects.filter(pk=nuevo.pk).update(version=3)
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM documentos_documento WHERE id = %s", [anterior.pk])


def test_descarga_directa_ajena_y_revocacion_facturacion(escenario_comun):
    e = escenario_comun
    documento = incorporar(
        actor=e.actor_staff,
        referencia=f"facturacion:{e.factura.pk}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.FACTURA_EMITIDA_XUBIO,
        procedencia="EXTERNO_XUBIO",
    )
    ajeno = Client()
    ajeno.force_login(e.a)
    for ruta in (
        reverse("documentos:detalle", args=[documento.pk]),
        reverse("documentos:archivo", args=[documento.pk]),
        reverse("documentos:tramite", args=["facturacion", e.factura.pk]),
    ):
        assert ajeno.get(ruta).status_code == 404
    titular = Client()
    titular.force_login(e.b)
    url = reverse("documentos:archivo", args=[documento.pk])
    respuesta = titular.get(url)
    assert respuesta.status_code == 200
    assert b"Ejemplo ficticio" in b"".join(respuesta.streaming_content)
    e.b.groups.remove(Group.objects.get(name="demo_documentos_descarga"))
    assert titular.get(url).status_code == 403
    assert Documento.objects.count() == 1


def test_c01_rechaza_documento_facturacion_y_referencia_inexistente(escenario_comun):
    e = escenario_comun
    documento = incorporar(
        actor=e.actor_staff,
        referencia=f"facturacion:{e.factura.pk}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.FACTURA_EMITIDA_XUBIO,
        procedencia="EXTERNO_XUBIO",
    )
    with pytest.raises(DocumentVerificationError):
        pagar(e, documento)
    with pytest.raises(DocumentVerificationError):
        ProveedorDocumentalGastos().verificar_y_bloquear_documento(
            actor=e.actor_staff,
            gasto=e.gasto,
            referencia_documental="no-es-uuid",
        )
    assert not PagoExterno.objects.exists()


def test_c01_rechaza_una_factura_valida_de_otro_gasto(escenario_comun):
    e = escenario_comun
    otro_gasto = crear_gasto_sintetico(
        pk=e.gasto.pk + 100000,
        solicitante=e.a,
        concepto="Otro",
        monto_estimado="1.00",
        unidad_requirente="Ficticia",
        estado="aceptada",
    )
    documento = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{otro_gasto.pk}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    with pytest.raises(DocumentVerificationError):
        pagar(e, documento)
    assert not PagoExterno.objects.exists()
    assert not EventoPagoExterno.objects.exists()


def test_c01_sin_transaccion_exterior_se_deniega(escenario_comun, transactional_db):
    e = escenario_comun
    documento = cargar_gasto(e)
    with pytest.raises(DocumentVerificationError):
        ProveedorDocumentalGastos().verificar_y_bloquear_documento(
            actor=e.actor_staff,
            gasto=e.gasto,
            referencia_documental=str(documento.referencia_version),
        )


def test_capacidad_pago_independiente_y_revocacion_en_consumidor_existente(
    escenario_comun, settings
):
    e = escenario_comun
    documento = cargar_gasto(e)
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"
    cliente = Client()
    cliente.force_login(e.staff)
    url = reverse("gastos:pagar", kwargs={"pk": e.gasto.pk})
    assert cliente.get(url).status_code == 200
    e.staff.groups.remove(Group.objects.get(name="demo_gastos_pago"))
    assert e.staff.groups.filter(name="demo_operadora").exists()
    assert cliente.get(url).status_code == 403
    cantidad_archivos = len(list(e.raiz.rglob("*")))
    respuesta = cliente.post(
        url,
        {
            "importe": "1.00",
            "fecha_pago": "2026-10-16",
            "referencia_externa": "SINTETICA",
            "referencia_documental": str(documento.referencia_version),
        },
    )
    assert respuesta.status_code == 403
    assert not PagoExterno.objects.exists()
    assert not EventoPagoExterno.objects.exists()
    assert len(list(e.raiz.rglob("*"))) == cantidad_archivos
