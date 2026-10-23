"""Recorridos cruzados sobre main; no sustituyen la UI de gastos pendiente en #66."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from comunes.models import TramiteBase
from documentos.models import Documento
from facturacion.models import SolicitudFacturacion
from gastos.models import EventoPagoExterno, PagoExterno, SolicitudGasto

from .helpers import archivo_pdf

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def recorridos(settings, tmp_path):
    settings.DEMO_IDENTITY_ENABLED = True
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "documentos"
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"
    call_command(
        "preparar_identidad_demo",
        facturacion=True,
        revision_documental=True,
        verificacion_cobros=True,
        resolucion_facturacion=True,
        verbosity=0,
    )
    usuarios, clientes = {}, {}
    for rol in ("a", "b", "o", "l"):
        usuarios[rol] = get_user_model().objects.get(username=f"demo_{rol}")
        clientes[rol] = Client()
        clientes[rol].force_login(usuarios[rol])
    # Pagar es independiente de decidir: se concede explícitamente para este escenario.
    usuarios["o"].groups.add(Group.objects.get(name="demo_gastos_pago"))
    a, b = clientes["a"], clientes["b"]
    respuesta = a.post(
        reverse("gastos:presentar"),
        {"concepto": "Insumo ficticio", "monto_estimado": "100.25", "unidad_requirente": "Demo"},
    )
    assert respuesta.status_code == 302
    gasto = SolicitudGasto.objects.get()
    formulario = b.get(reverse("facturacion:presentar"))
    respuesta = b.post(
        reverse("facturacion:presentar"),
        {
            "token_presentacion": formulario.context["token"],
            "presento_comprobante_pago": "False",
            "nombre_solicitante": "Solicitante ficticio",
            "cuit_receptor": "30712345671",
            "nombre_receptor": "Receptor ficticio",
            "condicion_iva": "IVA_RESPONSABLE_INSCRIPTO",
            "email_envio_factura": "destino@example.invalid",
            "detalle_factura": "Servicio ficticio",
            "importe_factura": "100.25",
            "producto_servicio": "ANALISIS",
            "centro_costo": "GISTAQ",
            "modalidad_cobro": "CUENTA_CORRIENTE",
            "observaciones": "Demostración sintética de integración",
        },
    )
    assert respuesta.status_code == 302, respuesta.context["form"].errors
    return SimpleNamespace(
        clientes=clientes,
        usuarios=usuarios,
        gasto=gasto,
        solicitud=SolicitudFacturacion.objects.get(),
        raiz=settings.DOCUMENT_STORAGE_ROOT,
    )


def aceptar_documento(cliente, documento):
    respuesta = cliente.post(
        reverse("documentos:revision", args=[documento.pk]),
        {"resultado": "ACEPTADO", "motivo": "", "revision_esperada": 0},
    )
    assert respuesta.status_code == 302, respuesta.content


def test_dos_recorridos_http_preservan_estados_documentos_e_historial(recorridos):
    e = recorridos
    a, b, o = (e.clientes[r] for r in ("a", "b", "o"))
    for cliente in (a, b, o):
        inicio = cliente.get(reverse("identidad:inicio"))
        assert inicio.status_code == 200
        for ruta in ("gastos:lista", "facturacion:lista"):
            assert f'href="{reverse(ruta)}"' in inicio.content.decode()
            assert cliente.get(reverse(ruta)).status_code == 200

    # Gasto real: presentación -> decisión -> proveedor C01 -> pago externo.
    assert (
        o.post(
            reverse("gastos:decidir", args=[e.gasto.pk]),
            {"action": "aceptar", "version": "0", "motivo": "Decisión sintética"},
        ).status_code
        == 302
    )
    # Usa la interfaz documental compartida; la pantalla de carga es aporte de #66.
    respuesta = a.post(
        reverse("documentos:tramite", args=["gastos", e.gasto.pk]),
        {"archivo": archivo_pdf(), "tipo": "FACTURA_PROVEEDOR", "procedencia": "SOLICITANTE"},
    )
    assert respuesta.status_code == 201, respuesta.content
    documento_gasto = Documento.objects.get(pk=respuesta.json()["id"])
    aceptar_documento(o, documento_gasto)
    pago_url = reverse("gastos:pagar", args=[e.gasto.pk])
    assert o.get(pago_url).status_code == 200
    datos_pago = {
        "importe": "100.25",
        "fecha_pago": "2026-10-23",
        "referencia_externa": "PAGO-SINTETICO-28",
        "referencia_documental": str(documento_gasto.referencia_version),
    }
    assert o.post(pago_url, datos_pago).status_code == 302
    assert o.post(pago_url, datos_pago).status_code == 302
    assert PagoExterno.objects.count() == EventoPagoExterno.objects.count() == 1

    # Facturación real: factura, cobro, verificación y aceptación no cierran solos.
    s = e.solicitud
    assert (
        o.post(
            reverse("facturacion:registrar_comprobante", args=[s.pk]),
            {
                "tipo": "FACTURA",
                "cuit_emisor": "30712345671",
                "letra": "A",
                "punto_venta": "1",
                "numero": "28",
                "fecha_emision": "2026-10-23",
                "importe": "100.25",
                "archivo_pdf": archivo_pdf(),
            },
        ).status_code
        == 302
    )
    assert (
        b.post(
            reverse("facturacion:registrar_cobro", args=[s.pk]),
            {
                "medio": "BNA_COMUN",
                "numero_operacion": "COBRO-SINTETICO-28",
                "fecha_operacion": "2026-10-23",
                "importe": "100.25",
                "archivo": archivo_pdf(),
            },
        ).status_code
        == 302
    )
    cobro = s.cobros.get()
    assert (
        o.post(
            reverse("facturacion:verificar_cobro", args=[s.pk, cobro.pk]),
            {"resultado": "CONFIRMADO"},
        ).status_code
        == 302
    )
    for documento in (s.comprobantes.get().documento, cobro.documento):
        aceptar_documento(o, documento)
    s.refresh_from_db()
    assert s.estado == "PRESENTADA"
    detalle_url = reverse("facturacion:detalle", args=[s.pk])
    detalle = o.get(detalle_url)
    revision = detalle.context["diagnostico"]["revision"]
    assert (
        o.post(
            reverse("facturacion:resolver", args=[s.pk]),
            {"accion": "cerrar", "motivo": "Cierre sintético", "revision": revision},
        ).status_code
        == 302
    )
    s.refresh_from_db()
    e.gasto.refresh_from_db()
    assert s.estado == "CERRADA" and e.gasto.estado == "aceptada"
    assert e.gasto.tramite_base_id != s.tramite_base_id
    assert documento_gasto.tramite_base_id == e.gasto.tramite_base_id
    assert cobro.documento.tramite_base_id == s.tramite_base_id
    for cliente, ruta in ((a, reverse("gastos:detalle", args=[e.gasto.pk])), (b, detalle_url)):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 200
        html = respuesta.content.decode()
        eventos = respuesta.context["cronologia" if cliente is a else "historial"]
        assert eventos
        for evento in eventos:
            assert f"actor #{evento.actor_id}" in html
            assert timezone.localtime(evento.fecha_hora).strftime("%d/%m/%Y %H:%M:%S") in html
            assert evento.tramite_ref == (
                f"gastos:{e.gasto.pk}" if cliente is a else f"facturacion:{s.pk}"
            )
    for cliente, documento in ((a, documento_gasto), (b, cobro.documento)):
        respuesta = cliente.get(reverse("documentos:archivo", args=[documento.pk]))
        assert respuesta.status_code == 200
        assert b"Ejemplo ficticio" in b"".join(respuesta.streaming_content)
    assert (
        "Pago externo registrado"
        in a.get(reverse("gastos:detalle", args=[e.gasto.pk])).content.decode()
    )
    assert "CIERRE" in b.get(detalle_url).content.decode()


@pytest.mark.parametrize(
    "circuito,titular,ajeno", [("gastos", "a", "b"), ("facturacion", "b", "a")]
)
def test_aislamiento_documental_y_relaciones_sin_cambios_parciales(
    recorridos, circuito, titular, ajeno
):
    e = recorridos
    solicitud = e.gasto if circuito == "gastos" else e.solicitud
    otro = e.solicitud if circuito == "gastos" else e.gasto
    tipo = "FACTURA_PROVEEDOR" if circuito == "gastos" else "COMPROBANTE_COBRO"
    url = reverse("documentos:tramite", args=[circuito, solicitud.pk])
    respuesta = e.clientes[titular].post(
        url, {"archivo": archivo_pdf(), "tipo": tipo, "procedencia": "SOLICITANTE"}
    )
    assert respuesta.status_code == 201
    documento = Documento.objects.get(pk=respuesta.json()["id"])
    for ruta in (
        url,
        reverse("documentos:archivo", args=[documento.pk]),
        reverse("documentos:revision", args=[documento.pk]),
    ):
        assert e.clientes[ajeno].get(ruta).status_code == 404
    antes = Documento.objects.count()
    archivos = {p for p in e.raiz.rglob("*") if p.is_file()}
    assert (
        e.clientes[ajeno]
        .post(url, {"archivo": archivo_pdf(), "tipo": tipo, "procedencia": "SOLICITANTE"})
        .status_code
        == 404
    )
    assert Documento.objects.count() == antes
    assert {p for p in e.raiz.rglob("*") if p.is_file()} == archivos
    with pytest.raises(IntegrityError), transaction.atomic():
        Documento.objects.filter(pk=documento.pk).update(tramite_base_id=otro.tramite_base_id)
    documento.refresh_from_db()
    assert documento.tramite_base_id == solicitud.tramite_base_id
    assert TramiteBase.objects.count() == 2


def test_revocar_capacidad_en_un_circuito_no_revoca_el_otro(recorridos):
    e = recorridos
    cliente = e.clientes["o"]
    e.usuarios["o"].groups.remove(Group.objects.get(name="demo_gastos_pago"))
    assert cliente.get(reverse("gastos:pagar", args=[e.gasto.pk])).status_code == 403
    assert (
        cliente.get(reverse("facturacion:registrar_comprobante", args=[e.solicitud.pk])).status_code
        == 200
    )
    e.usuarios["o"].groups.remove(Group.objects.get(name="demo_facturacion_operadora"))
    assert cliente.get(reverse("facturacion:detalle", args=[e.solicitud.pk])).status_code == 404
    assert cliente.get(reverse("gastos:detalle", args=[e.gasto.pk])).status_code == 200
    assert not PagoExterno.objects.exists() and not e.solicitud.comprobantes.exists()


def test_lector_global_consulta_sin_adquirir_escritura_ni_documentos(recorridos):
    e = recorridos
    lector = e.clientes["l"]
    for ruta in (
        reverse("gastos:detalle", args=[e.gasto.pk]),
        reverse("facturacion:detalle", args=[e.solicitud.pk]),
    ):
        assert lector.get(ruta).status_code == 200
    for ruta, datos in (
        (
            reverse("gastos:decidir", args=[e.gasto.pk]),
            {"action": "aceptar", "version": "0", "motivo": "Intento no autorizado"},
        ),
        (
            reverse("facturacion:resolver", args=[e.solicitud.pk]),
            {"accion": "anular", "motivo": "Intento no autorizado", "revision": "inventada"},
        ),
    ):
        assert lector.post(ruta, datos).status_code == 403
    for circuito, solicitud in (("gastos", e.gasto), ("facturacion", e.solicitud)):
        assert (
            lector.get(reverse("documentos:tramite", args=[circuito, solicitud.pk])).status_code
            == 403
        )
    e.gasto.refresh_from_db()
    e.solicitud.refresh_from_db()
    assert e.gasto.estado == "presentada" and e.solicitud.estado == "PRESENTADA"
    assert not e.gasto.decisiones.exists()
    assert e.solicitud.eventos.count() == 1
