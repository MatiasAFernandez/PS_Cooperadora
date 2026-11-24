"""Pruebas UX/UI de Incremento 8B (detalle, subformularios, D-5 y microdetalles Inc 7)."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from facturacion.forms import FiltroFacturacionForm, SolicitudFacturacionForm
from facturacion.workflow import (
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)
from tests.facturacion.test_cierre import aceptar, cobro, factura

pytestmark = pytest.mark.django_db(transaction=True)


def _presentar(escenario, datos, actor="a"):
    return presentar_solicitud_facturacion(
        actor=escenario.actores[actor],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores[actor]),
    )


def test_detalle_layout_d5_actores_cuit_y_propagacion_bandeja(escenario, datos):
    solicitud = _presentar(escenario, datos)
    operador_user = escenario.usuarios["o"]
    operador_user.first_name = "Operadora"
    operador_user.last_name = "Demo"
    operador_user.save(update_fields=["first_name", "last_name"])
    operador_user.groups.add(Group.objects.get(name="demo_documentos_revision"))

    comp = factura(escenario, solicitud)
    cob = cobro(escenario, solicitud, confirmar=False)

    cliente_op = Client()
    cliente_op.force_login(operador_user)
    url = reverse("facturacion:detalle", args=[solicitud.pk]) + "?bandeja=atencion%3D1"
    resp_op = cliente_op.get(url)
    assert resp_op.status_code == 200
    html_op = resp_op.content.decode()

    assert "<h1" in html_op
    assert 'class="page-back page-back--arrow"' in html_op
    assert 'href="/facturacion/?atencion=1"' in html_op
    assert "30-71234567-1" in html_op
    assert "data-copy=" in html_op
    assert "Exportar PDF" in html_op
    assert "Operadora Demo" in html_op
    assert f"actor #{operador_user.pk}" not in html_op
    assert "Revisar documento" in html_op
    rev_comp = reverse("documentos:revision", args=[comp.documento_id])
    rev_cob = reverse("documentos:revision", args=[cob.documento_id])
    assert f"{rev_comp}?bandeja=atencion%3D1" in html_op
    assert f"{rev_cob}?bandeja=atencion%3D1" in html_op

    # Contrato DTO intacto: actor_id sigue siendo el identificador original.
    assert any(ev.actor_id == str(operador_user.pk) for ev in resp_op.context["historial"])

    # Aceptar el comprobante cambia el rótulo a «Ver revisión».
    aceptar(escenario, comp.documento)
    detalle_url = reverse("facturacion:detalle", args=[solicitud.pk])
    html_op_aceptado = cliente_op.get(detalle_url).content.decode()
    assert "Ver revisión" in html_op_aceptado

    # Solicitante ve etiquetas neutrales (Titular / Cooperadora), nunca datos internos ni actor #ID.
    cliente_sol = Client()
    cliente_sol.force_login(escenario.usuarios["a"])
    resp_sol = cliente_sol.get(detalle_url)
    assert resp_sol.status_code == 200
    html_sol = resp_sol.content.decode()
    assert "Titular" in html_sol
    assert "Cooperadora" in html_sol
    assert "Operadora Demo" not in html_sol
    assert operador_user.username not in html_sol
    assert f"actor #{operador_user.pk}" not in html_sol
    assert "te notificaremos" not in html_sol.lower()
    assert "Cooperadora está validando tus cobros" in html_sol


def test_guarda_cierre_d5_deshabilitada_con_pendientes_y_confirmacion_sin_spec(escenario, datos):
    solicitud = _presentar(escenario, datos)
    operador_user = escenario.usuarios["o"]
    operador_user.groups.add(
        Group.objects.get(name="demo_documentos_revision"),
        Group.objects.get(name="demo_verificacion_cobros"),
        Group.objects.get(name="demo_resolucion_facturacion"),
    )
    cliente = Client()
    cliente.force_login(operador_user)
    url = reverse("facturacion:detalle", args=[solicitud.pk])

    html_pendiente = cliente.get(url).content.decode()
    assert "Cerrar trámite (faltan requisitos)" in html_pendiente
    assert "Confirmar cierre del trámite" not in html_pendiente
    assert "SPEC-007" not in html_pendiente

    comp = factura(escenario, solicitud)
    aceptar(escenario, comp.documento)
    cobro(escenario, solicitud, importe="100.25", confirmar=True)

    resp_lista = cliente.get(url)
    html_lista = resp_lista.content.decode()
    assert "Confirmar cierre del trámite" in html_lista
    assert "El cierre es definitivo y conserva el historial y los respaldos." in html_lista
    assert "SPEC-007" not in html_lista

    revision = resp_lista.context["diagnostico"]["revision"]
    post_cierre = cliente.post(
        reverse("facturacion:resolver", args=[solicitud.pk]),
        {"accion": "cerrar", "revision": revision},
    )
    assert post_cierre.status_code == 302
    solicitud.refresh_from_db()
    assert solicitud.estado == "CERRADA"


def test_observar_inline_errores_400_y_409_sin_redirigir_a_error_html(escenario, datos):
    solicitud = _presentar(escenario, datos)
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url_observar = reverse("facturacion:observar", args=[solicitud.pk])

    resp_400 = cliente.post(
        url_observar,
        {"version_esperada": solicitud.version_concurrencia, "motivo": ""},
    )
    assert resp_400.status_code == 400
    html_400 = resp_400.content.decode()
    assert 'id="observar-solicitud" class="fd-details fd-details-top" open' in html_400
    assert "form-error-summary" in html_400
    assert "No se pudo completar la acción" not in html_400

    resp_409 = cliente.post(
        url_observar,
        {"version_esperada": 999, "motivo": "Falta adjuntar orden"},
    )
    assert resp_409.status_code == 409
    html_409 = resp_409.content.decode()
    assert 'id="observar-solicitud" class="fd-details fd-details-top" open' in html_409
    assert "Falta adjuntar orden" in html_409


def test_defaults_d5_selects_y_explicacion_inline_checkboxes(escenario, datos):
    form = SolicitudFacturacionForm()
    for campo in ("condicion_iva", "producto_servicio", "centro_costo", "modalidad_cobro"):
        assert form.fields[campo].choices[0] == ("", "Seleccioná…")

    solicitud = _presentar(escenario, datos)
    operador_user = escenario.usuarios["o"]
    operador_user.groups.add(
        Group.objects.get(name="demo_documentos_revision"),
        Group.objects.get(name="demo_verificacion_cobros"),
    )
    cliente = Client()
    cliente.force_login(operador_user)

    resp_cobro = cliente.get(reverse("facturacion:registrar_cobro", args=[solicitud.pk]))
    html_cobro = resp_cobro.content.decode()
    assert resp_cobro.context["form"]["confirmar_al_registrar"].value() is True
    assert 'class="fac-checkbox-card"' in html_cobro
    assert "Sin marcar, el cobro queda pendiente." in html_cobro
    assert 'class="page-back page-back--arrow"' in html_cobro

    resp_comp = cliente.get(reverse("facturacion:registrar_comprobante", args=[solicitud.pk]))
    html_comp = resp_comp.content.decode()
    assert resp_comp.context["form"]["aceptar_respaldo"].value() is True
    assert "Guarda la conformidad documental a tu nombre" in html_comp
    assert "Informar el envío es opcional" in html_comp

    # Al modificar un comprobante existente, no debe aparecer el texto de envío opcional.
    comp = factura(escenario, solicitud)
    resp_edit = cliente.get(
        reverse("facturacion:modificar_comprobante", args=[solicitud.pk, comp.pk])
    )
    assert resp_edit.status_code == 200
    assert "Informar el envío es opcional" not in resp_edit.content.decode()


def test_formulario_nueva_errores_debajo_y_resumen_enfocable(escenario, datos):
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    url = reverse("facturacion:presentar")
    token = cliente.get(url).context["token"]

    resp = cliente.post(url, dict(datos, cuit_receptor="30712345679", token_presentacion=token))
    assert resp.status_code == 400
    html = resp.content.decode()
    assert "data-auto-focus-error" in html
    assert 'tabindex="-1"' in html
    assert 'class="page-back page-back--arrow"' in html
    assert html.index('id="id_cuit_receptor"') < html.index('id="id_cuit_receptor_error"')


def test_microdetalles_inc7_en_listado_y_drawer(escenario, datos):
    solicitud = _presentar(escenario, datos)
    observar_solicitud_facturacion(
        actor=escenario.actores["o"],
        numero_publico=solicitud.pk,
        motivo="Revisar concepto",
        version_esperada=solicitud.version_concurrencia,
    )
    assert (
        FiltroFacturacionForm().fields["q"].widget.attrs["placeholder"]
        == "Buscar por #, solicitante, receptor o CUIT"
    )
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    html = cliente.get(reverse("facturacion:lista")).content.decode()
    assert "30-71234567-1" in html
    assert '<span class="fac-mobile-label">Importe</span>' in html


def test_css_facturacion_sin_important_ni_tokens_legacy():
    ruta = Path(settings.BASE_DIR) / "static" / "facturacion" / "css" / "facturacion.css"
    contenido = re.sub(r"/\*.*?\*/", "", ruta.read_text(encoding="utf-8"), flags=re.S)
    assert "!important" not in contenido
    assert "--ref-" not in contenido
