"""Regresión de prioridades, aislamiento y recorridos de atención #80/#78."""
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from django.test import Client
from django.urls import reverse

from facturacion.atencion import acciones_inmediatas, proximidad_cierre, solicitudes_atencion
from facturacion.forms import SolicitudFacturacionForm
from facturacion.permissions import filtrar_solicitudes_visibles
from facturacion.workflow import (
    corregir_solicitud_facturacion,
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)

pytestmark = pytest.mark.django_db(transaction=True)


def presentar(e, datos, actor="a"):
    return presentar_solicitud_facturacion(
        actor=e.actores[actor], datos=datos, token_presentacion=emitir_token(e.actores[actor])
    )


def observar(e, solicitud):
    return observar_solicitud_facturacion(
        actor=e.actores["o"], numero_publico=solicitud.pk,
        motivo="Precisá el servicio", version_esperada=solicitud.version_concurrencia,
    )


def test_paneles_priorizan_actualizacion_y_separan_responsabilidades(escenario, datos):
    e = escenario
    solicitudes = [presentar(e, datos) for _ in range(5)]
    ajena = presentar(e, datos, "b")
    # Una observación tardía mueve una solicitud antigua al primer lugar del titular.
    observar(e, solicitudes[0])
    observar(e, solicitudes[1])
    titular = e.actores["a"]
    panel = solicitudes_atencion(titular, filtrar_solicitudes_visibles(titular))
    assert [x["solicitud"].pk for x in panel] == [solicitudes[1].pk, solicitudes[0].pk]
    assert all("Corregir" in x["accion"].texto for x in panel)
    assert ajena.pk not in [x["solicitud"].pk for x in panel]
    operador = e.actores["o"]
    panel_op = solicitudes_atencion(operador, filtrar_solicitudes_visibles(operador))
    assert len(panel_op) == 3
    assert panel_op[0]["solicitud"].pk == ajena.pk
    assert all(x["solicitud"].pk not in {solicitudes[0].pk, solicitudes[1].pk}
               for x in panel_op)
    # Corregir devuelve la acción al operador y la quita al titular.
    corregir_solicitud_facturacion(
        actor=titular, numero_publico=solicitudes[0].pk, version_esperada=2, datos=datos,
    )
    panel_op = solicitudes_atencion(operador, filtrar_solicitudes_visibles(operador))
    assert panel_op[0]["solicitud"].pk == solicitudes[0].pk
    assert len(solicitudes_atencion(titular, filtrar_solicitudes_visibles(titular))) == 1
    lector = e.actores["l"]
    assert solicitudes_atencion(lector, filtrar_solicitudes_visibles(lector)) == []


def test_terminal_no_ofrece_acciones_y_permisos_limitan_sugerencias(escenario, datos):
    solicitud = presentar(escenario, datos)
    sin_escritura = replace(escenario.actores["o"], capabilities=frozenset({
        "facturacion.consultar_todas"
    }))
    assert acciones_inmediatas(sin_escritura, solicitud) == []
    solicitud.estado = "CERRADA"
    assert acciones_inmediatas(escenario.actores["o"], solicitud) == []
    solicitud.estado = "ANULADA"
    assert acciones_inmediatas(escenario.actores["a"], solicitud) == []


@pytest.mark.parametrize(("hoy", "creada", "esperado"), [
    (date(2026, 11, 23), datetime(2026, 11, 1, tzinfo=UTC), False),
    (date(2026, 11, 24), datetime(2026, 11, 1, tzinfo=UTC), True),
    (date(2026, 11, 30), datetime(2026, 11, 25, tzinfo=UTC), False),
    (date(2028, 2, 23), datetime(2028, 2, 20, tzinfo=UTC), True),
    (date(2028, 2, 29), datetime(2028, 2, 24, tzinfo=UTC), False),
])
def test_cierre_mes_calendario_local(hoy, creada, esperado):
    assert proximidad_cierre(SimpleNamespace(fecha_presentacion=creada), hoy) is esperado


def test_listado_escapado_panel_independiente_de_filtros(escenario, datos):
    s = presentar(escenario, dict(datos, nombre_receptor="<script>alert(1)</script>"))
    observar(escenario, s)
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    respuesta = cliente.get(reverse("facturacion:lista"), {"q": "sin coincidencia"})
    assert respuesta.status_code == 200
    assert len(respuesta.context["atencion"]) == 1
    assert len(respuesta.context["pagina"]) == 0
    assert f'id="resumen-solicitud-{s.pk}"' in respuesta.content.decode()
    detalle = cliente.get(reverse("facturacion:detalle", args=[s.pk]))
    html = detalle.content.decode()
    assert html.index("Acciones inmediatas") < html.index("Exportar solicitud")
    assert "<script>alert(1)</script>" not in html


def test_formulario_ordena_pago_y_rechaza_opcion_retirada(datos):
    form = SolicitudFacturacionForm()
    campos = list(form.fields)
    assert campos.index("presento_comprobante_pago") + 1 == campos.index(
        "fecha_operacion_declarada"
    )
    assert "OPCION_35" not in dict(form.fields["centro_costo"].choices)
    assert not SolicitudFacturacionForm(dict(datos, centro_costo="OPCION_35")).is_valid()

def test_operador_conserva_trabajo_despues_de_su_actualizacion(escenario, datos):
    from tests.facturacion.test_cierre import aceptar, cobro, factura, operador, resolver

    s = presentar(escenario, datos)
    op = operador(escenario)
    detalle = reverse("facturacion:detalle", args=[s.pk])
    cliente_titular = Client()
    cliente_titular.force_login(escenario.usuarios["a"])
    detalle_titular = cliente_titular.get(detalle).content.decode()
    assert "Estamos creando la factura" in detalle_titular
    assert "Estado de cobro" in detalle_titular and 'id="resolucion"' not in detalle_titular
    cliente_operador = Client()
    cliente_operador.force_login(escenario.usuarios["o"])
    lista = cliente_operador.get(reverse("facturacion:lista")).content.decode()
    assert "Registrar factura externa" in lista and datos["email_envio_factura"] in lista
    f = factura(escenario, s)
    # El operador acaba de intervenir; todavía debe revisar su respaldo.
    assert solicitudes_atencion(op, filtrar_solicitudes_visibles(op))
    aceptar(escenario, f.documento)
    # Sólo falta un cobro del titular: no inventar una tarea para el operador.
    assert solicitudes_atencion(op, filtrar_solicitudes_visibles(op)) == []
    detalle_operador = cliente_operador.get(detalle).content.decode()
    assert "El solicitante aún no cargó el cobro" in detalle_operador
    assert 'id="resolucion"' in detalle_operador
    assert "Informar" in acciones_inmediatas(escenario.actores["a"], s)[0].texto
    c = cobro(escenario, s, confirmar=False)
    # Un ingreso pendiente ya aportado no pide duplicarlo al titular.
    assert acciones_inmediatas(escenario.actores["a"], s) == []
    assert "Estamos validando tus cobros" in cliente_titular.get(detalle).content.decode()
    acciones = acciones_inmediatas(op, s)
    assert "Revisar el documento de respaldo" in acciones[0].texto
    aceptar(escenario, c.documento)
    assert acciones_inmediatas(op, s)[0].texto == "Constatar Ingreso"
    from facturacion.cobros import verificar_cobro
    verificar_cobro(actor=op, numero=s.pk, cobro_id=c.pk, datos={"resultado": "CONFIRMADO"})
    assert acciones_inmediatas(op, s)[0].texto == "Ir a resolución"
    resolver(escenario, s)
    assert solicitudes_atencion(op, filtrar_solicitudes_visibles(op)) == []


def test_rectificacion_deja_el_cobro_en_historial_sin_pendientes(escenario, datos):
    from django.contrib.auth.models import Group

    from documentos.revision import revisar
    from facturacion.cobros import rectificar_cobro
    from tests.facturacion.test_cierre import aceptar, cobro, factura, operador

    solicitud = presentar(escenario, datos)
    op = operador(escenario)
    comprobante = factura(escenario, solicitud)
    aceptar(escenario, comprobante.documento)
    erroneo = cobro(escenario, solicitud, importe="200.00")
    revisar(
        actor=op,
        documento_id=erroneo.documento_id,
        resultado="RECHAZADO",
        motivo="El importe informado no coincide",
        revision_esperada=erroneo.documento.revisiones.get().pk,
    )
    modificar = reverse("facturacion:corregir_cobro", args=[solicitud.pk, erroneo.pk])
    assert modificar in [accion.url for accion in acciones_inmediatas(op, solicitud)]
    rectificar_cobro(
        actor=op, numero=solicitud.pk, cobro_id=erroneo.pk, motivo="Importe incorrecto"
    )
    cobro(escenario, solicitud, operacion="OPERACION-CORRECTA")
    assert [accion.texto for accion in acciones_inmediatas(op, solicitud)] == ["Ir a resolución"]
    assert not acciones_inmediatas(escenario.actores["a"], solicitud)

    operador_http = escenario.usuarios["o"]
    operador_http.groups.add(Group.objects.get(name="demo_resolucion_facturacion"))
    cliente = Client()
    cliente.force_login(operador_http)
    respuesta = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    assert list(respuesta.context["pendientes_revision"]) == []
    html = respuesta.content.decode()
    assert f'href="{modificar}"' in html
    assert "RECTIFICADO" in html and "RECHAZADO" in html
    assert "Sin pendientes para el cierre normal" in html
