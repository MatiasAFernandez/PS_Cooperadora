"""Envío declarado y recepción voluntaria con actores y datos sintéticos."""

from dataclasses import replace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from facturacion.comprobantes import registrar_comprobante
from facturacion.envios import confirmar_recepcion, declarar_envio
from facturacion.models import ComprobanteExterno, ConfirmacionRecepcion, EnvioComprobante
from facturacion.workflow import emitir_token, presentar_solicitud_facturacion
from tests.facturacion.test_cierre import cobro, resolver

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def solicitud(escenario, datos):
    return presentar_solicitud_facturacion(
        actor=escenario.actores["a"], datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )


@pytest.fixture
def entrada():
    return dict(tipo="FACTURA", cuit_emisor="30712345671", letra="A", punto_venta="1",
                numero="1", fecha_emision="2026-01-01", importe="100.25",
                enviado=True, destinatario="destino@example.invalid",
                fecha_envio=timezone.localdate().isoformat())


def registrar(e, s, datos):
    return registrar_comprobante(
        actor=e.actores["o"], numero_publico=s.pk, datos=datos, archivo_pdf=None
    )


def test_alta_con_envio_y_reenvio_idempotente(escenario, solicitud, entrada):
    comprobante = registrar(escenario, solicitud, entrada)
    envio = comprobante.envios.get()
    assert envio.actor_id == escenario.usuarios["o"].pk
    assert declarar_envio(actor=escenario.actores["o"], comprobante=comprobante,
                         datos=entrada).pk == envio.pk
    assert not ConfirmacionRecepcion.objects.exists()


def test_envio_invalido_revierte_comprobante(escenario, solicitud, entrada):
    with pytest.raises(ValidationError):
        registrar(escenario, solicitud, dict(entrada, fecha_envio="2025-01-01"))
    assert not ComprobanteExterno.objects.exists()
    assert not EnvioComprobante.objects.exists()


def test_confirmacion_solo_titular_y_reintento(escenario, solicitud, entrada):
    envio = registrar(escenario, solicitud, entrada).envios.get()
    with pytest.raises(PermissionDenied):
        confirmar_recepcion(actor=escenario.actores["o"], numero=solicitud.pk, envio_id=envio.pk)
    primero = confirmar_recepcion(actor=escenario.actores["a"], numero=solicitud.pk,
                                  envio_id=envio.pk)
    assert confirmar_recepcion(actor=escenario.actores["a"], numero=solicitud.pk,
                               envio_id=envio.pk).pk == primero.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        ConfirmacionRecepcion.objects.create(envio=envio, actor=escenario.usuarios["b"])


def test_cierre_no_exige_acuse_y_permite_confirmarlo_despues(escenario, solicitud, entrada):
    envio = registrar(escenario, solicitud, entrada).envios.get()
    cobro(escenario, solicitud)
    resolver(escenario, solicitud)
    assert confirmar_recepcion(actor=escenario.actores["a"], numero=solicitud.pk,
                               envio_id=envio.pk)
    with pytest.raises(PermissionDenied):
        declarar_envio(actor=escenario.actores["o"], comprobante=envio.comprobante,
                       datos=entrada)


def test_correccion_envio_conserva_hechos_y_acuse_anterior(escenario, solicitud, entrada):
    comprobante = registrar(escenario, solicitud, entrada)
    anterior = comprobante.envios.get()
    confirmar_recepcion(actor=escenario.actores["a"], numero=solicitud.pk, envio_id=anterior.pk)
    nuevo = declarar_envio(actor=escenario.actores["o"], comprobante=comprobante,
                          datos=dict(entrada, destinatario="otro@example.invalid"))
    assert nuevo.pk != anterior.pk
    assert ConfirmacionRecepcion.objects.get().envio_id == anterior.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        EnvioComprobante.objects.filter(pk=anterior.pk).update(destinatario="x@example.invalid")


def test_http_acciones_historial_csrf_y_visibilidad(escenario, solicitud, entrada):
    envio = registrar(escenario, solicitud, entrada).envios.get()
    url = reverse("facturacion:confirmar_recepcion", args=[solicitud.pk, envio.pk])
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    detalle = reverse("facturacion:detalle", args=[solicitud.pk])
    assert "Confirmar que recibí" in cliente.get(detalle).content.decode()
    assert cliente.get(url).status_code == 405
    assert cliente.post(url).status_code == 302
    contenido = cliente.get(detalle).content.decode()
    assert "Recepción confirmada" in contenido
    assert "hecho de comunicación" in contenido
    cliente.force_login(escenario.usuarios["b"])
    assert cliente.post(url).status_code == 404
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(escenario.usuarios["a"])
    assert csrf.post(url).status_code == 403


def test_declarar_sin_capacidad_denegado(escenario, solicitud, entrada):
    comprobante = registrar(escenario, solicitud, dict(entrada, enviado=False))
    actor = replace(escenario.actores["o"], capabilities=frozenset())
    with pytest.raises((PermissionDenied, LookupError)):
        declarar_envio(actor=actor, comprobante=comprobante, datos=entrada)


def test_fecha_precargada_usa_formato_html(escenario, solicitud):
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    respuesta = cliente.get(reverse("facturacion:registrar_comprobante", args=[solicitud.pk]))
    campo = str(respuesta.context["form"]["fecha_envio"])
    assert f'value="{timezone.localdate().isoformat()}"' in campo
