import pytest
from django.test import Client
from django.urls import reverse

from facturacion.models import SolicitudFacturacion
from facturacion.permissions import filtrar_solicitudes_visibles
from facturacion.workflow import (
    corregir_solicitud_facturacion,
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)
from gastos.services import crear_solicitud_gasto

pytestmark = pytest.mark.django_db(transaction=True)


def presentar(escenario, datos, clave="a"):
    actor = escenario.actores[clave]
    return presentar_solicitud_facturacion(
        actor=actor, datos=datos, token_presentacion=emitir_token(actor)
    )


def test_observaciones_opcionales_en_alta_correccion_y_sql(escenario, datos):
    entrada = {k: v for k, v in datos.items() if k != "observaciones"}
    solicitud = presentar(escenario, entrada)
    assert solicitud.observaciones == ""
    observar_solicitud_facturacion(
        actor=escenario.actores["o"], numero_publico=solicitud.pk,
        motivo="Corregir detalle", version_esperada=1,
    )
    solicitud = corregir_solicitud_facturacion(
        actor=escenario.actores["a"], numero_publico=solicitud.pk,
        datos=entrada, version_esperada=2,
    )
    solicitud.full_clean()
    assert solicitud.observaciones == ""
    SolicitudFacturacion.objects.filter(pk=solicitud.pk).update(observaciones="")
    assert solicitud.eventos.last().snapshot_datos["despues"]["observaciones"] == ""


def test_numeracion_por_titular_filtros_y_accesos(escenario, datos):
    a1 = presentar(escenario, datos)
    gasto = crear_solicitud_gasto(
        actor=escenario.actores["a"],
        concepto="Gasto ficticio",
        monto_estimado="10.00",
        unidad_requirente="Unidad ficticia",
    )
    b1 = presentar(escenario, datos, "b")
    a2 = presentar(escenario, datos)
    assert gasto.tramite_base.circuito == "GASTO"
    assert [b1.pk, a2.pk] == [a1.pk + 1, a1.pk + 2]
    assert [s.numero_solicitante for s in (a1, b1, a2)] == [1, 1, 2]
    visibles = filtrar_solicitudes_visibles(escenario.actores["o"]).order_by("pk")
    assert [s.numero_visible for s in visibles] == [a1.pk, b1.pk, a2.pk]
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    url = reverse("facturacion:lista")
    respuesta = cliente.get(url, {"q": "2"})
    assert [s.pk for s in respuesta.context["pagina"]] == [a2.pk]
    assert respuesta.context["pagina"][0].numero_visible == 2
    assert 'data-titulo="Solicitud #2"' in respuesta.content.decode()
    assert cliente.get(reverse("facturacion:detalle", args=[b1.pk])).status_code == 404
    cliente.force_login(escenario.usuarios["o"])
    respuesta = cliente.get(url, {"q": str(b1.pk)})
    assert [s.pk for s in respuesta.context["pagina"]] == [b1.pk]
    html = respuesta.content.decode()
    assert f'<td class="fac-number">#{b1.pk}</td>' in html
    assert f'data-titulo="Solicitud #{b1.pk}"' in html
    assert f"Solicitud #{b1.pk}</strong>" in html
    contenido = cliente.get(reverse("facturacion:detalle", args=[b1.pk])).content.decode()
    assert f"Solicitud {b1.pk} de {b1.correo_solicitante}" in contenido
    pdf = cliente.get(reverse("facturacion:exportar_pdf", args=[b1.pk]))
    assert pdf["Content-Disposition"] == f'attachment; filename="solicitud-facturacion-{b1.pk}.pdf"'
