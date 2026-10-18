"""Aceptación del ciclo por pantallas con CSRF real y reenvíos sin efectos."""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from comunes.models import TramiteBase
from facturacion.models import EventoFacturacion, SolicitudFacturacion


@pytest.mark.django_db(transaction=True)
def test_ciclo_http_con_csrf_historial_y_reenvios(escenario, datos):
    clientes = {}
    for nombre, usuario in escenario.usuarios.items():
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(usuario)
        clientes[nombre] = cliente
    a, b, operadora, lector = (clientes[n] for n in ("a", "b", "o", "l"))

    def post(cliente, url, contenido):
        return cliente.post(
            url, dict(contenido, csrfmiddlewaretoken=cliente.cookies["csrftoken"].value)
        )

    alta = reverse("facturacion:presentar")
    inicio = a.get(reverse("identidad:inicio"))
    assert f'href="{alta}"' in inicio.content.decode()
    formulario = a.get(alta)
    token = formulario.context["token"]
    contenido = dict(datos, token_presentacion=token)
    assert post(a, alta, dict(contenido, cuit_receptor="invalido")).status_code == 400
    assert not SolicitudFacturacion.objects.exists()
    assert not TramiteBase.objects.exists()
    assert not EventoFacturacion.objects.exists()

    antes = timezone.now()
    respuesta = post(
        a,
        alta,
        dict(contenido, correo_solicitante="inyectado@example.invalid", estado="CERRADA"),
    )
    assert respuesta.status_code == 302
    solicitud = SolicitudFacturacion.objects.get()
    detalle = reverse("facturacion:detalle", args=[solicitud.pk])
    observar = reverse("facturacion:observar", args=[solicitud.pk])
    corregir = reverse("facturacion:corregir", args=[solicitud.pk])
    assert respuesta.url == detalle
    assert solicitud.correo_solicitante == escenario.usuarios["a"].email
    assert antes <= solicitud.fecha_presentacion <= timezone.now()
    assert solicitud.tramite_base.solicitante_actor_id == str(escenario.usuarios["a"].pk)
    assert solicitud.estado == "PRESENTADA" and solicitud.version_concurrencia == 1
    assert post(a, alta, contenido).status_code == 409

    # La falta de CSRF no alcanza los servicios ni cambia el hecho registrado.
    assert a.post(corregir, datos).status_code == 403
    assert (
        operadora.post(observar, {"version_esperada": 1, "motivo": "No grabar"}).status_code
        == 403
    )
    assert b.get(detalle).status_code == 404
    assert list(b.get(reverse("facturacion:lista")).context["pagina"]) == []
    assert lector.get(detalle).status_code == 200
    # Obtener una cookie CSRF real sin conceder facultades de negocio al lector.
    lector.get(reverse("identidad:inicio"))
    assert (
        post(lector, observar, {"version_esperada": 1, "motivo": "No autorizado"}).status_code
        == 403
    )
    assert solicitud.eventos.count() == 1

    # Tampoco se permite corregir PRESENTADA con una versión vigente.
    assert post(a, corregir, dict(datos, version_esperada=1)).status_code == 409
    operadora.get(detalle)
    observacion = {"version_esperada": 1, "motivo": "Precisar el período sintético"}
    assert post(operadora, observar, observacion).status_code == 302
    assert post(operadora, observar, observacion).status_code == 409
    solicitud.refresh_from_db()
    assert solicitud.estado == "OBSERVADA" and solicitud.version_concurrencia == 2
    assert solicitud.observacion_vigente == observacion["motivo"]
    assert post(operadora, observar, dict(observacion, version_esperada=2)).status_code == 409

    formulario = a.get(corregir)
    assert formulario.status_code == 200
    assert observacion["motivo"] in formulario.content.decode()
    correccion = dict(datos, version_esperada=2, detalle_factura="Servicio de octubre sintético")
    assert post(a, corregir, correccion).status_code == 302
    assert post(a, corregir, correccion).status_code == 409
    solicitud.refresh_from_db()
    assert solicitud.estado == "PRESENTADA" and solicitud.version_concurrencia == 3
    assert solicitud.detalle_factura == correccion["detalle_factura"]
    assert solicitud.observacion_vigente == ""
    eventos = list(solicitud.eventos.all())
    assert [e.tipo_evento for e in eventos] == ["PRESENTACION", "OBSERVACION", "CORRECCION"]
    assert [e.actor_id for e in eventos] == [
        escenario.usuarios[n].pk for n in ("a", "o", "a")
    ]
    assert [e.fecha_hora for e in eventos] == sorted(e.fecha_hora for e in eventos)
    assert all(antes <= e.fecha_hora <= timezone.now() for e in eventos)
    snapshot = eventos[-1].snapshot_datos
    assert snapshot["antes"]["detalle_factura"] == datos["detalle_factura"]
    assert snapshot["despues"]["detalle_factura"] == correccion["detalle_factura"]
    assert snapshot["observacion_atendida"] == observacion["motivo"]
    final = a.get(detalle)
    assert [e.tipo_evento for e in final.context["historial"]] == [
        "PRESENTACION", "OBSERVACION", "CORRECCION"
    ]
    assert observacion["motivo"] in final.content.decode()
    assert datos["detalle_factura"] in final.content.decode()
    assert SolicitudFacturacion.objects.count() == TramiteBase.objects.count() == 1
    assert EventoFacturacion.objects.count() == 3
