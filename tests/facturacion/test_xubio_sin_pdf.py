"""Referencias sintéticas sin duplicar bytes, con controles de cierre vigentes."""

from dataclasses import replace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from documentos.models import Documento
from facturacion.comprobantes import corregir_comprobante, registrar_comprobante
from facturacion.models import ComprobanteExterno
from facturacion.seguimiento import diagnostico
from facturacion.workflow import emitir_token, presentar_solicitud_facturacion
from tests.facturacion.test_cierre import cobro, resolver

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def entrada():
    return dict(tipo="FACTURA", cuit_emisor="30712345671", letra="A", punto_venta="1",
                numero="1", fecha_emision="2026-10-01", importe="100.25")


@pytest.fixture
def solicitud(escenario, datos):
    return presentar_solicitud_facturacion(
        actor=escenario.actores["a"], datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )


def registrar(e, s, datos):
    return registrar_comprobante(
        actor=e.actores["o"], numero_publico=s.pk, datos=datos, archivo_pdf=None
    )


def test_referencia_sin_bytes_detalle_y_cierre(escenario, solicitud, entrada):
    antes = Documento.objects.count()
    comprobante = registrar(escenario, solicitud, entrada)
    assert comprobante.documento_id is None
    assert Documento.objects.count() == antes
    assert not diagnostico(solicitud)["faltas_documentales"]
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    respuesta = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    assert respuesta.status_code == 200
    assert b"PDF opcional" in respuesta.content
    assert b"Descargar PDF vinculado" not in respuesta.content
    cobro(escenario, solicitud)
    resolver(escenario, solicitud)
    solicitud.refresh_from_db()
    assert solicitud.estado == "CERRADA"


def test_otro_origen_requiere_archivo_en_servicio_y_sql(escenario, solicitud, entrada):
    with pytest.raises(ValidationError):
        registrar(escenario, solicitud, dict(entrada, procedencia="EXTERNO_OTRO",
                                           origen_aclaracion="Sistema ficticio"))
    registro = registrar(escenario, solicitud, entrada)
    with pytest.raises(IntegrityError), transaction.atomic():
        ComprobanteExterno.todos.create(
            solicitud=solicitud, tipo="NOTA_DEBITO", cuit_emisor=registro.cuit_emisor,
            letra="A", punto_venta=1, numero=2, fecha_emision=registro.fecha_emision,
            importe="1.00", procedencia="EXTERNO_OTRO", origen_aclaracion="Ficticio",
            factura_origen=registro, documento=None, actor_id=registro.actor_id,
        )


def test_corregir_referencia_sin_pdf(escenario, solicitud, entrada):
    previo = registrar(escenario, solicitud, entrada)
    nuevo = corregir_comprobante(
        actor=escenario.actores["o"], numero=solicitud.pk, comprobante_id=previo.pk,
        datos=dict(entrada, numero="2", motivo="Corrección sintética",
                   revision=diagnostico(solicitud)["revision"]),
    )
    assert nuevo.documento_id is None and nuevo.reemplaza_id == previo.pk
    previo.refresh_from_db()
    assert previo.sustituido


def test_sin_permiso_de_bytes_puede_registrar_referencia(escenario, solicitud, entrada):
    actor = replace(escenario.actores["o"], capabilities=(
        escenario.actores["o"].capabilities - {"documentos.incorporar"}
    ))
    assert registrar_comprobante(
        actor=actor, numero_publico=solicitud.pk, datos=entrada, archivo_pdf=None
    ).documento_id is None


def test_primer_pdf_desde_modificar_y_revision_pendiente(escenario, solicitud, entrada):
    previo = registrar(escenario, solicitud, entrada)
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url = reverse("facturacion:modificar_comprobante", args=[solicitud.pk, previo.pk])
    assert cliente.get(url).status_code == 200
    respuesta = cliente.post(url, dict(
        entrada, revision=diagnostico(solicitud)["revision"], motivo="Adjunto posterior",
        archivo_pdf=SimpleUploadedFile("ficticio.pdf", b"%PDF-1.7\nFicticio\n%%EOF",
                                      "application/pdf"),
    ))
    assert respuesta.status_code == 302
    nuevo = solicitud.comprobantes.get()
    assert nuevo.documento_id and nuevo.reemplaza_id == previo.pk
    assert diagnostico(solicitud)["faltas_documentales"]


def test_http_factura_y_nota_sin_archivo(escenario, solicitud, entrada):
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url = reverse("facturacion:registrar_comprobante", args=[solicitud.pk])
    pagina = cliente.get(url)
    assert not pagina.context["form"].fields["archivo_pdf"].required
    assert "no necesitás volver a cargar el PDF" in pagina.content.decode()
    assert cliente.post(url, entrada).status_code == 302
    assert cliente.post(url, dict(entrada, tipo="NOTA_DEBITO", numero="2")).status_code == 302
    assert solicitud.comprobantes.count() == 2
    assert not Documento.objects.exists()
