"""Proyección de revisión documental en el detalle de gastos (#49).

Cubre versiones y revisiones, aportes en la cronología, permisos por actor y
objeto, privacidad y el efecto C01 sobre el selector de pagos nuevos.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from comunes.contracts import EventoHistorialDTO
from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno
from tests.soporte_gastos import crear_gasto_sintetico


def _pdf(nombre: str = "ejemplo.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre, b"%PDF-1.7\nEjemplo ficticio\n%%EOF", "application/pdf"
    )


def _cargar_gasto(e, *, nombre: str, **extras) -> Documento:
    return incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=_pdf(nombre),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
        **extras,
    )


def _revisor(e):
    return replace(
        e.actor_staff,
        capabilities=e.actor_staff.capabilities | {"documentos.revisar"},
    )


def test_detalle_proyecta_versiones_revisiones_y_enlaces_autorizados(escenario_comun):
    e = escenario_comun
    revisor = _revisor(e)
    v1 = _cargar_gasto(e, nombre="respaldo-v1.pdf")
    revisar(
        actor=revisor,
        documento_id=v1.pk,
        resultado="ACEPTADO",
        motivo="",
        revision_esperada=0,
    )
    v2 = _cargar_gasto(e, nombre="respaldo-v2.pdf", reemplaza_id=v1.pk)

    cliente = Client()
    cliente.force_login(e.staff)
    url = reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})
    with CaptureQueriesContext(connection) as consultas_iniciales:
        respuesta = cliente.get(url)
    assert respuesta.status_code == 200
    assert respuesta.context["puede_ver_documentos"] is True

    versiones = respuesta.context["versiones_documentales"]
    assert [version.documento_id for version in versiones] == [v1.pk, v2.pk]
    assert versiones[0].vigente is False
    assert versiones[1].vigente is True
    assert versiones[0].revision_actual.resultado == "ACEPTADO"
    assert versiones[1].revision_actual is None

    cronologia = respuesta.context["cronologia"]
    assert all(isinstance(evento, EventoHistorialDTO) for evento in cronologia)
    assert [evento.tipo_evento for evento in cronologia] == [
        "aporte_documental",
        "revision_documental",
        "aporte_documental",
    ]
    assert cronologia[0].actor_id == str(e.a.pk)
    assert cronologia[1].actor_id == str(e.staff.pk)
    assert cronologia[1].estado_resultante == "ACEPTADO"
    assert cronologia[2].actor_id == str(e.a.pk)
    assert [evento.fecha_hora for evento in cronologia] == sorted(
        evento.fecha_hora for evento in cronologia
    )
    assert "respaldo-v1.pdf" in cronologia[0].motivo_o_detalle
    assert "versión 1" in cronologia[0].motivo_o_detalle

    contenido = respuesta.content.decode()
    assert reverse("documentos:revision", args=[v1.pk]) in contenido
    assert reverse("documentos:revision", args=[v2.pk]) in contenido
    assert "Vigente" in contenido
    assert "Reemplazada" in contenido
    assert "PENDIENTE" in contenido
    assert "ACEPTADO" in contenido
    assert v1.get_tipo_display() in contenido
    assert "no equivale a aprobación" not in contenido.lower()
    assert "Aporte documental" in contenido
    assert "Revisión documental" in contenido

    for documento in (v1, v2):
        assert str(documento.referencia_version) not in contenido
        assert str(documento.serie) not in contenido
        assert documento.sha256 not in contenido
        assert documento.archivo not in contenido

    cliente_a = Client()
    cliente_a.force_login(e.a)
    respuesta_v1 = cliente_a.get(reverse("documentos:revision", args=[v1.pk]))
    assert respuesta_v1.status_code == 200
    contenido_v1 = respuesta_v1.content.decode()
    assert "ACEPTADO" in contenido_v1
    assert "Versión reemplazada" in contenido_v1
    respuesta_v2 = cliente_a.get(reverse("documentos:revision", args=[v2.pk]))
    assert respuesta_v2.status_code == 200
    assert "Pendiente" in respuesta_v2.content.decode()

    revisar(
        actor=revisor,
        documento_id=v2.pk,
        resultado="OBSERVADO",
        motivo="Falta detalle",
        revision_esperada=0,
    )
    with CaptureQueriesContext(connection) as consultas_con_revision:
        assert cliente.get(url).status_code == 200
    assert len(consultas_con_revision.captured_queries) == len(
        consultas_iniciales.captured_queries
    )


def test_pendiente_negativo_accesos_y_privacidad_de_otros_tramites(escenario_comun):
    e = escenario_comun
    revisor = _revisor(e)
    observada = _cargar_gasto(e, nombre="respaldo-observado.pdf")
    revisar(
        actor=revisor,
        documento_id=observada.pk,
        resultado="OBSERVADO",
        motivo="<script>ficticio</script>",
        revision_esperada=0,
    )
    pendiente = _cargar_gasto(
        e, nombre="respaldo-pendiente.pdf", reemplaza_id=observada.pk
    )

    otro_gasto = crear_gasto_sintetico(
        pk=e.gasto.pk + 100000,
        solicitante=e.b,
        concepto="Gasto ajeno sintético",
        monto_estimado="1.00",
        unidad_requirente="Unidad ajena",
        estado="aceptada",
    )
    ajeno = incorporar(
        actor=e.actor_b,
        referencia=f"gastos:{otro_gasto.pk}",
        archivo=_pdf("ajeno.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    doc_facturacion = incorporar(
        actor=e.actor_b,
        referencia=f"facturacion:{e.factura.pk}",
        archivo=_pdf("factura-ajena.pdf"),
        tipo=Documento.Tipo.COMPROBANTE_COBRO,
        procedencia="SOLICITANTE",
    )

    cliente = Client()
    cliente.force_login(e.a)
    respuesta = cliente.get(reverse("gastos:detalle", kwargs={"pk": e.gasto.pk}))
    assert respuesta.status_code == 200
    versiones = respuesta.context["versiones_documentales"]
    assert [version.documento_id for version in versiones] == [
        observada.pk,
        pendiente.pk,
    ]
    assert versiones[0].vigente is False
    assert versiones[0].revision_actual.resultado == "OBSERVADO"
    assert versiones[0].revision_actual.motivo == "<script>ficticio</script>"
    assert versiones[1].vigente is True
    assert versiones[1].revision_actual is None
    assert [evento.tipo_evento for evento in respuesta.context["cronologia"]] == [
        "aporte_documental",
        "revision_documental",
        "aporte_documental",
    ]

    contenido = respuesta.content.decode()
    assert "PENDIENTE" in contenido
    assert "OBSERVADO" in contenido
    assert "&lt;script&gt;ficticio&lt;/script&gt;" in contenido
    assert "<script>ficticio</script>" not in contenido
    assert "ajeno.pdf" not in contenido
    assert "factura-ajena.pdf" not in contenido
    for documento in (observada, pendiente, ajeno, doc_facturacion):
        assert str(documento.referencia_version) not in contenido
        assert str(documento.serie) not in contenido
        assert documento.sha256 not in contenido
        assert documento.archivo not in contenido

    cliente_b = Client()
    cliente_b.force_login(e.b)
    assert (
        cliente_b.get(reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})).status_code
        == 404
    )
    for documento in (ajeno, doc_facturacion):
        assert (
            cliente.get(reverse("documentos:revision", args=[documento.pk])).status_code
            == 404
        )

    lector = get_user_model().objects.create_user(username="lector_49", password="demo")
    lector.groups.add(Group.objects.get_or_create(name="demo_lectura")[0])
    cliente_lector = Client()
    cliente_lector.force_login(lector)
    respuesta_lector = cliente_lector.get(
        reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})
    )
    assert respuesta_lector.status_code == 200
    assert respuesta_lector.context["puede_ver_documentos"] is False
    assert respuesta_lector.context["versiones_documentales"] is None
    contenido_lector = respuesta_lector.content.decode()
    assert "respaldo-observado.pdf" not in contenido_lector
    assert "respaldo-pendiente.pdf" not in contenido_lector
    assert "OBSERVADO" not in contenido_lector
    assert "PENDIENTE" not in contenido_lector
    assert "No hay versiones documentales visibles" not in contenido_lector
    assert (
        cliente_lector.get(reverse("documentos:revision", args=[pendiente.pk])).status_code
        == 403
    )


def test_c01_omite_version_negativa_sin_mutar_pago_ni_ocultar_documento(
    escenario_comun, settings
):
    e = escenario_comun
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = (
        "documentos.c01.ProveedorDocumentalGastos"
    )
    revisor = _revisor(e)
    pagada = _cargar_gasto(e, nombre="respaldo-pagado.pdf")
    negativa = _cargar_gasto(e, nombre="respaldo-negativo.pdf")
    revisar(
        actor=revisor,
        documento_id=negativa.pk,
        resultado="OBSERVADO",
        motivo="No conforme",
        revision_esperada=0,
    )

    cliente = Client()
    cliente.force_login(e.staff)
    url_pagar = reverse("gastos:pagar", kwargs={"pk": e.gasto.pk})
    respuesta_form = cliente.get(url_pagar)
    assert respuesta_form.status_code == 200
    opciones = respuesta_form.context["opciones_documentales"]
    assert {opcion.referencia_documental for opcion in opciones} == {
        str(pagada.referencia_version)
    }
    assert str(negativa.referencia_version) not in respuesta_form.content.decode()

    respuesta_pago = cliente.post(
        url_pagar,
        {
            "importe": "1.00",
            "fecha_pago": date(2026, 10, 19).isoformat(),
            "referencia_externa": "SINTETICA-49",
            "referencia_documental": str(pagada.referencia_version),
        },
    )
    assert respuesta_pago.status_code == 302
    pago = PagoExterno.objects.get(solicitud=e.gasto)
    assert pago.referencia_documental == str(pagada.referencia_version)
    evento = EventoPagoExterno.objects.get(pago=pago)

    respuesta_pendiente = cliente.get(
        reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})
    )
    assert respuesta_pendiente.status_code == 200
    assert respuesta_pendiente.context["respaldo_categoria"] == "factura"
    versiones_pendiente = respuesta_pendiente.context["versiones_documentales"]
    assert [version.documento_id for version in versiones_pendiente] == [
        pagada.pk,
        negativa.pk,
    ]
    assert versiones_pendiente[0].revision_actual is None
    assert versiones_pendiente[1].revision_actual.resultado == "OBSERVADO"
    contenido_pendiente = respuesta_pendiente.content.decode()
    assert "PENDIENTE" in contenido_pendiente
    assert "desconocid" not in contenido_pendiente.lower()
    assert (
        "El tipo, la vigencia y la revisión de cada versión figuran por separado."
        in contenido_pendiente
    )

    revisar(
        actor=revisor,
        documento_id=pagada.pk,
        resultado="OBSERVADO",
        motivo="Revisión posterior",
        revision_esperada=0,
    )
    pago.refresh_from_db()
    assert pago.referencia_documental == str(pagada.referencia_version)
    assert pago.importe == Decimal("1.00")
    assert PagoExterno.objects.filter(solicitud=e.gasto).count() == 1
    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1
    evento.refresh_from_db()
    assert evento.actor_id == e.staff.pk
    assert evento.tipo_evento == "pago_externo_registrado"

    assert (
        ProveedorDocumentalGastos().listar_opciones_para_pago(
            actor=e.actor_staff, gasto=e.gasto
        )
        == []
    )

    respuesta_detalle = cliente.get(
        reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})
    )
    assert respuesta_detalle.status_code == 200
    assert respuesta_detalle.context["pago_consulta"] is not None
    assert not hasattr(
        respuesta_detalle.context["pago_consulta"], "referencia_documental"
    )
    assert respuesta_detalle.context["respaldo_categoria"] is None
    versiones = respuesta_detalle.context["versiones_documentales"]
    assert [version.documento_id for version in versiones] == [
        pagada.pk,
        negativa.pk,
    ]
    assert {version.revision_actual.resultado for version in versiones} == {
        "OBSERVADO"
    }
    assert [
        evento.tipo_evento for evento in respuesta_detalle.context["cronologia"]
    ] == [
        "aporte_documental",
        "aporte_documental",
        "revision_documental",
        "pago_externo_registrado",
        "revision_documental",
    ]

    contenido = respuesta_detalle.content.decode()
    assert "respaldo-pagado.pdf" in contenido
    assert "respaldo-negativo.pdf" in contenido
    assert "No conforme" in contenido
    assert "Revisión posterior" in contenido
    assert "No hay versiones documentales visibles" not in contenido
    assert "OBSERVADO" in contenido
    assert (
        "Las versiones cuyo último resultado de revisión sea observado o rechazado "
        "no se ofrecen para nuevos pagos; siguen existiendo y conservan su historial."
        in contenido
    )
    assert (
        "La categoría de la versión referenciada al registrar el pago no está disponible"
        in contenido
    )
    assert (
        "El tipo, la vigencia y la revisión de cada versión figuran por separado."
        in contenido
    )
    assert (
        "El tipo documental y su resultado de revisión se muestran por separado."
        in contenido
    )
    assert (
        "Esta vista no determina si el documento satisface un requisito del trámite."
        in contenido
    )
    assert (
        "Esta vista no muestra los metadatos ni el estado de revisión del comprobante."
        not in contenido
    )
    for documento in (pagada, negativa):
        assert str(documento.referencia_version) not in contenido
        assert str(documento.serie) not in contenido
        assert documento.sha256 not in contenido
        assert documento.archivo not in contenido
    assert pago.huella_idempotencia not in contenido
    pago.refresh_from_db()
    assert pago.referencia_documental == str(pagada.referencia_version)
    assert PagoExterno.objects.filter(solicitud=e.gasto).count() == 1
    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1

    e.gasto.refresh_from_db()
    assert e.gasto.estado == EstadoSolicitud.ACEPTADA
    assert e.gasto.monto_estimado == Decimal("1.00")

    lector = get_user_model().objects.create_user(
        username="lector_49_pago", password="demo"
    )
    lector.groups.add(Group.objects.get_or_create(name="demo_lectura")[0])
    cliente_lector = Client()
    cliente_lector.force_login(lector)
    respuesta_lector = cliente_lector.get(
        reverse("gastos:detalle", kwargs={"pk": e.gasto.pk})
    )
    assert respuesta_lector.status_code == 200
    assert respuesta_lector.context["puede_ver_documentos"] is False
    assert respuesta_lector.context["versiones_documentales"] is None
    contenido_lector = respuesta_lector.content.decode()
    assert "OBSERVADO" not in contenido_lector
    assert "PENDIENTE" not in contenido_lector
    assert "respaldo-pagado.pdf" not in contenido_lector
    assert "respaldo-negativo.pdf" not in contenido_lector
    assert "Versiones y revisión documental" not in contenido_lector
    assert "La categoría del respaldo no surge" not in contenido_lector
    assert (
        "Esta vista no muestra metadatos ni estado de revisión documental para esta cuenta. "
        "No se puede inferir desde aquí si hay archivos; el registro de pago tampoco "
        "equivale a aprobación o suficiencia documental."
        in contenido_lector
    )
    assert "No hay versiones documentales visibles" not in contenido_lector
