"""Cambios acordados tras el ensayo: consultas, origen, respaldos y exportación."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from comunes.filtros import FiltroFechaForm
from documentos.models import Documento
from documentos.revision import revisar
from facturacion.comprobantes import registrar_comprobante
from facturacion.consultas import filtrar_solicitudes
from facturacion.forms import FiltroFacturacionForm
from facturacion.models import ComprobanteExterno, SolicitudFacturacion
from facturacion.permissions import filtrar_solicitudes_visibles
from facturacion.seguimiento import diagnostico
from facturacion.workflow import emitir_token, presentar_solicitud_facturacion

pytestmark = pytest.mark.django_db(transaction=True)


def presentar(e, datos, actor="a", **cambios):
    return presentar_solicitud_facturacion(
        actor=e.actores[actor],
        datos=dict(datos, **cambios),
        token_presentacion=emitir_token(e.actores[actor]),
    )


def factura(e, solicitud, **cambios):
    datos = dict(
        tipo="FACTURA",
        cuit_emisor="30712345671",
        letra="B",
        punto_venta="1",
        numero=str(solicitud.pk),
        fecha_emision="2026-10-25",
        importe="100.25",
    )
    return registrar_comprobante(
        actor=e.actores["o"],
        numero_publico=solicitud.pk,
        datos=dict(datos, **cambios),
        archivo_pdf=SimpleUploadedFile("respaldo.pdf", b"%PDF-1.7\nDemo\n%%EOF", "application/pdf"),
    )


@pytest.mark.parametrize("tipo", ["FACTURA", "NOTA_CREDITO", "NOTA_DEBITO"])
def test_origen_otro_para_tres_tipos_y_historial(escenario, datos, tipo):
    s = presentar(escenario, datos)
    if tipo != "FACTURA":
        factura(escenario, s)
    c = factura(
        escenario,
        s,
        tipo=tipo,
        procedencia="EXTERNO_OTRO",
        origen_aclaracion="Sistema externo de prueba",
    )
    assert c.procedencia == c.documento.procedencia == "EXTERNO_OTRO"
    assert "Sistema externo de prueba" in c.como_historial().motivo_o_detalle
    with pytest.raises(IntegrityError), transaction.atomic():
        ComprobanteExterno.objects.filter(pk=c.pk).update(origen_aclaracion="Cambio")


def test_otro_exige_aclaracion_sin_archivo_residual(escenario, datos):
    s = presentar(escenario, datos)
    with pytest.raises(ValidationError):
        factura(escenario, s, procedencia="EXTERNO_OTRO", origen_aclaracion="   ")
    assert not Documento.objects.exists()
    c = factura(escenario, s)
    assert c.procedencia == "EXTERNO_XUBIO" and c.origen_aclaracion == ""


def test_busqueda_y_fecha_no_amplian_visibilidad(escenario, datos):
    s = presentar(escenario, datos, nombre_receptor="Receptor buscable")
    ajena = presentar(escenario, datos, actor="b", nombre_receptor="Receptor buscable")
    # 02:59 UTC es el dia anterior en Buenos Aires; 03:00 UTC inicia el día.
    SolicitudFacturacion.objects.filter(pk=s.pk).update(
        fecha_presentacion=datetime(2026, 10, 25, 3, tzinfo=UTC)
    )
    SolicitudFacturacion.objects.filter(pk=ajena.pk).update(
        fecha_presentacion=datetime(2026, 10, 25, 2, 59, tzinfo=UTC)
    )
    parametros = dict(q="buscable", periodo="dia", dia="2026-10-25")
    for actor in ("a", "o", "l"):
        resultado = filtrar_solicitudes(
            filtrar_solicitudes_visibles(escenario.actores[actor]),
            FiltroFacturacionForm(parametros),
        )
        assert list(resultado.values_list("pk", flat=True)) == [s.pk]
    for parametros in (
        dict(periodo="mes", mes="10", anio="2026"),
        dict(periodo="anio", anio="2026"),
    ):
        assert (
            filtrar_solicitudes(
                SolicitudFacturacion.objects.all(), FiltroFacturacionForm(parametros)
            ).count()
            == 2
        )
    assert not filtrar_solicitudes(
        SolicitudFacturacion.objects.all(), FiltroFacturacionForm(dict(periodo="mes", mes="13"))
    ).exists()


@pytest.mark.parametrize(
    "campo", ["nombre_solicitante", "nombre_receptor", "cuit_receptor", "detalle_factura", "pk"]
)
def test_campos_busqueda(escenario, datos, campo):
    s = presentar(escenario, datos)
    qs = filtrar_solicitudes(
        SolicitudFacturacion.objects.all(), FiltroFacturacionForm({"q": str(getattr(s, campo))})
    )
    assert qs.get() == s


def test_estados_financieros_se_calculan_sin_escribir(escenario, datos):
    s = presentar(escenario, datos)
    consulta = SolicitudFacturacion.objects.all()
    assert filtrar_solicitudes(consulta, FiltroFacturacionForm({"estado": "PRESENTADA"})).exists()
    factura(escenario, s)
    assert not filtrar_solicitudes(
        consulta, FiltroFacturacionForm({"estado": "PRESENTADA"})
    ).exists()
    assert filtrar_solicitudes(
        consulta, FiltroFacturacionForm({"estado": "FACTURADA_PENDIENTE_COBRO"})
    ).exists()
    factura(escenario, s, tipo="NOTA_CREDITO")
    assert filtrar_solicitudes(
        consulta, FiltroFacturacionForm({"estado": "COBRADA_EN_REVISION"})
    ).exists()
    s.refresh_from_db()
    assert s.estado == "PRESENTADA" and s.version_concurrencia == 1


def test_pendientes_incluyen_factura_y_omiten_aceptada(escenario, datos):
    s = presentar(escenario, datos)
    c = factura(escenario, s)
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url = reverse("facturacion:detalle", args=[s.pk])
    assert list(cliente.get(url).context["pendientes_revision"]) == [c.documento]
    actor = replace(
        escenario.actores["o"],
        capabilities=escenario.actores["o"].capabilities | {"documentos.revisar"},
    )
    rev = revisar(
        actor=actor,
        documento_id=c.documento_id,
        resultado="OBSERVADO",
        motivo="Archivo observado",
        revision_esperada=0,
    )
    assert list(cliente.get(url).context["pendientes_revision"]) == [c.documento]
    revisar(
        actor=actor,
        documento_id=c.documento_id,
        resultado="ACEPTADO",
        motivo="",
        revision_esperada=rev.pk,
    )
    respuesta = cliente.get(url)
    assert not respuesta.context["pendientes_revision"]
    assert list(respuesta.context["respaldos"]) == [c.documento]


def test_diferencia_y_nombre_de_respaldo(escenario, datos):
    s = presentar(escenario, datos)
    c = factura(escenario, s)
    d = diagnostico(s)
    assert d["diferencia"] == Decimal("100.25")
    assert any(
        c.identificacion in mensaje and '"respaldo.pdf"' in mensaje
        for mensaje in d["faltas_cierre"]
    )
    assert not any("El respaldo #" in mensaje for mensaje in d["faltas_cierre"])


def test_pdf_autorizado_propietario_operador_lector_y_ajeno_404(escenario, datos):
    s = presentar(escenario, datos, detalle_factura="Servicio <prueba> & capacitación")
    url = reverse("facturacion:exportar_pdf", args=[s.pk])
    cliente = Client()
    assert cliente.get(url).status_code == 302
    for actor in ("a", "o", "l"):
        cliente.force_login(escenario.usuarios[actor])
        respuesta = cliente.get(url)
        assert respuesta.status_code == 200
        assert respuesta.content.startswith(b"%PDF-")
        assert respuesta["Cache-Control"] == "private, no-store"
    cliente.force_login(escenario.usuarios["b"])
    assert cliente.get(url).status_code == 404


@pytest.mark.parametrize(
    "datos",
    [
        dict(periodo="dia"),
        dict(periodo="mes", mes=10),
        dict(periodo="anio"),
        dict(periodo="otro"),
        dict(periodo="dia", dia="9999-12-31"),
    ],
)
def test_periodos_invalidos(datos):
    assert not FiltroFechaForm(datos).is_valid()
