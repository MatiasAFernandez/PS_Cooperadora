"""Carga y reemplazo de respaldo desde la interfaz de gastos."""

from dataclasses import replace
from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from documentos.models import Documento, RevisionDocumento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno
from tests.soporte_gastos import crear_gasto_sintetico


def _pdf(nombre: str = "respaldo.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"%PDF-1.7\nContenido de prueba ficticio\n%%EOF",
        "application/pdf",
    )


def _cliente(usuario) -> Client:
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


def _subir(cliente, gasto_id: int, *, nombre: str = "respaldo.pdf", **campos):
    return cliente.post(
        reverse("gastos:documentos", kwargs={"pk": gasto_id}),
        {
            "archivo": _pdf(nombre),
            "tipo": Documento.Tipo.FACTURA_PROVEEDOR,
            "procedencia": Documento.Procedencia.SOLICITANTE,
            "reemplaza_id": "",
            **campos,
        },
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "estado",
    [
        EstadoSolicitud.PRESENTADA,
        EstadoSolicitud.POSTERGADA,
        EstadoSolicitud.RECHAZADA,
        EstadoSolicitud.ACEPTADA,
    ],
)
def test_aporte_depende_de_acceso_y_capacidad_no_del_estado(
    escenario_comun, estado
):
    e = escenario_comun
    gasto = crear_gasto_sintetico(
        concepto="Gasto sintético visible",
        monto_estimado="400.00",
        unidad_requirente="Unidad ficticia",
        solicitante=e.a,
        estado=estado,
    )

    respuesta = _subir(_cliente(e.a), gasto.pk, nombre=f"respaldo-{estado}.pdf")

    assert respuesta.status_code == 302
    assert Documento.objects.filter(solicitud_gasto=gasto).count() == 1


@pytest.mark.django_db(transaction=True)
def test_carga_revision_pago_y_reemplazo_preservan_hechos(
    escenario_comun, transactional_db, settings
):
    e = escenario_comun
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"
    gasto_id = e.gasto.pk
    url_detalle = reverse("gastos:detalle", kwargs={"pk": gasto_id})

    cliente_solicitante = _cliente(e.a)
    respuesta_carga = _subir(cliente_solicitante, gasto_id, nombre="respaldo-v1.pdf")
    assert respuesta_carga.status_code == 302
    assert respuesta_carga.url == url_detalle
    anterior = Documento.objects.get(solicitud_gasto=e.gasto)
    assert anterior.version == 1
    assert anterior.tipo == Documento.Tipo.FACTURA_PROVEEDOR
    assert RevisionDocumento.objects.filter(documento=anterior).count() == 0
    assert (e.raiz / anterior.archivo).is_file()

    revisor = replace(
        e.actor_staff,
        capabilities=e.actor_staff.capabilities | {"documentos.revisar"},
    )
    revisar(
        actor=revisor,
        documento_id=anterior.pk,
        resultado=RevisionDocumento.Resultado.ACEPTADO,
        motivo="",
        revision_esperada=0,
    )

    cliente_staff = _cliente(e.staff)
    referencia_pago = str(anterior.referencia_version)
    respuesta_pago = cliente_staff.post(
        reverse("gastos:pagar", kwargs={"pk": gasto_id}),
        {
            "importe": "1200.00",
            "fecha_pago": "2026-10-21",
            "referencia_externa": "SINTETICA-ISSUE50-001",
            "referencia_documental": referencia_pago,
        },
    )
    assert respuesta_pago.status_code == 302
    pago = PagoExterno.objects.get(solicitud=e.gasto)
    assert pago.fecha_pago == date(2026, 10, 21)
    assert pago.referencia_documental == referencia_pago
    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1

    respuesta_reemplazo = _subir(
        cliente_solicitante,
        gasto_id,
        nombre="respaldo-v2.pdf",
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
        reemplaza_id=str(anterior.pk),
    )
    assert respuesta_reemplazo.status_code == 302
    anterior.refresh_from_db()
    nueva = Documento.objects.get(reemplaza=anterior)
    assert nueva.version == 2
    assert nueva.tipo == anterior.tipo
    assert RevisionDocumento.objects.filter(documento=anterior).count() == 1
    assert RevisionDocumento.objects.filter(documento=nueva).count() == 0
    pago.refresh_from_db()
    assert pago.referencia_documental == referencia_pago
    assert EventoPagoExterno.objects.filter(pago=pago).count() == 1

    detalle = cliente_staff.get(url_detalle)
    assert detalle.status_code == 200
    assert detalle.context["respaldo_categoria"] is None
    assert [v.documento_id for v in detalle.context["versiones_documentales"]] == [
        anterior.pk,
        nueva.pk,
    ]
    contenido = detalle.content.decode()
    assert "respaldo-v1.pdf" in contenido and "Reemplazada" in contenido
    assert "respaldo-v2.pdf" in contenido and "Vigente" in contenido
    assert "PENDIENTE" in contenido and "ACEPTADO" in contenido
    assert (
        "La categoría de la versión referenciada al registrar el pago no está disponible"
        in contenido
    )
    assert "Los aportes y reemplazos posteriores no modifican el registro de pago" in contenido
    assert referencia_pago not in contenido
    assert str(nueva.referencia_version) not in contenido
    assert nueva.sha256 not in contenido and nueva.archivo not in contenido


@pytest.mark.django_db
def test_sin_metadatos_puede_aportar_pero_no_reemplazar_por_id(
    escenario_comun,
):
    e = escenario_comun
    e.a.groups.remove(Group.objects.get(name="demo_documentos_metadatos"))
    cliente = _cliente(e.a)
    url = reverse("gastos:documentos", kwargs={"pk": e.gasto.pk})

    formulario = cliente.get(url)
    assert formulario.status_code == 200
    assert "Puede aportar un documento nuevo" in formulario.content.decode()
    assert "respaldo-viejo.pdf" not in formulario.content.decode()

    incorporado = _subir(cliente, e.gasto.pk, nombre="respaldo-viejo.pdf")
    assert incorporado.status_code == 302
    documento = Documento.objects.get(solicitud_gasto=e.gasto)

    intento = _subir(
        cliente,
        e.gasto.pk,
        nombre="respaldo-2.pdf",
        reemplaza_id=str(documento.pk),
    )
    assert intento.status_code == 400
    assert "Seleccione una versión vigente" in intento.content.decode()
    assert Documento.objects.filter(solicitud_gasto=e.gasto).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("actor_subida", "usuario_consulta", "tipo", "procedencia", "nombre"),
    [
        (
            "actor_a",
            "staff",
            Documento.Tipo.PRESUPUESTO_PROFORMA,
            Documento.Procedencia.SOLICITANTE,
            "presupuesto-sintetico.pdf",
        ),
        (
            "actor_staff",
            "a",
            Documento.Tipo.COMPROBANTE_PAGO,
            Documento.Procedencia.EXTERNO_BANCO,
            "comprobante-sintetico.pdf",
        ),
    ],
)
def test_selector_no_ofrece_tipos_que_el_actor_no_puede_incorporar(
    escenario_comun, actor_subida, usuario_consulta, tipo, procedencia, nombre
):
    e = escenario_comun
    documento = incorporar(
        actor=getattr(e, actor_subida),
        referencia=f"gastos:{e.gasto.pk}",
        archivo=_pdf(nombre),
        tipo=tipo,
        procedencia=procedencia,
    )
    usuario = getattr(e, usuario_consulta)
    cliente = _cliente(usuario)

    detalle = cliente.get(reverse("gastos:detalle", kwargs={"pk": e.gasto.pk}))
    formulario = cliente.get(reverse("gastos:documentos", kwargs={"pk": e.gasto.pk}))

    assert detalle.status_code == 200
    assert nombre in detalle.content.decode()
    assert formulario.status_code == 200
    assert nombre not in formulario.content.decode()
    valores_reemplazables = {
        valor for valor, _etiqueta in formulario.context["form"].fields["reemplaza_id"].choices
    }
    assert str(documento.pk) not in valores_reemplazables


@pytest.mark.django_db
def test_rechaza_id_invalido_ajeno_y_tipo_distinto_sin_escrituras(escenario_comun):
    e = escenario_comun
    cliente = _cliente(e.a)
    gasto_objetivo = e.gasto
    anterior = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{gasto_objetivo.pk}",
        archivo=_pdf("objetivo.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    gasto_ajeno = crear_gasto_sintetico(
        concepto="Gasto sintético ajeno",
        monto_estimado="500.00",
        unidad_requirente="Unidad ficticia",
        solicitante=e.b,
        estado="aceptada",
    )
    ajeno = incorporar(
        actor=e.actor_b,
        referencia=f"gastos:{gasto_ajeno.pk}",
        archivo=_pdf("ajeno.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    cantidad_inicial = Documento.objects.count()

    for reemplaza_id, tipo in (
        ("id-invalido", Documento.Tipo.FACTURA_PROVEEDOR),
        (str(ajeno.pk), Documento.Tipo.FACTURA_PROVEEDOR),
        (str(anterior.pk), Documento.Tipo.TICKET_NO_FISCAL),
    ):
        respuesta = cliente.post(
            reverse("gastos:documentos", kwargs={"pk": gasto_objetivo.pk}),
            {
                "archivo": _pdf("intento.pdf"),
                "tipo": tipo,
                "procedencia": Documento.Procedencia.SOLICITANTE,
                "reemplaza_id": reemplaza_id,
            },
        )
        assert respuesta.status_code == 400
        assert Documento.objects.count() == cantidad_inicial


@pytest.mark.django_db
def test_archivo_ausente_o_invalido_no_crea_documento(escenario_comun):
    e = escenario_comun
    cliente = _cliente(e.a)
    url = reverse("gastos:documentos", kwargs={"pk": e.gasto.pk})
    campos = {
        "tipo": Documento.Tipo.FACTURA_PROVEEDOR,
        "procedencia": Documento.Procedencia.SOLICITANTE,
        "reemplaza_id": "",
    }

    ausente = cliente.post(url, campos)
    assert ausente.status_code == 400
    invalido = cliente.post(
        url,
        {
            **campos,
            "archivo": SimpleUploadedFile("invalido.pdf", b"no es un PDF", "application/pdf"),
        },
    )
    assert invalido.status_code == 400
    assert Documento.objects.filter(solicitud_gasto=e.gasto).count() == 0
    assert not e.raiz.exists() or not any(e.raiz.rglob("*"))


@pytest.mark.django_db
def test_fallo_de_storage_devuelve_503_y_no_crea_documento(
    escenario_comun, monkeypatch
):
    e = escenario_comun

    def fallo_storage(self, nombre, contenido):
        raise OSError("fallo sintético de almacenamiento")

    monkeypatch.setattr(FileSystemStorage, "save", fallo_storage)
    respuesta = _subir(_cliente(e.a), e.gasto.pk)

    assert respuesta.status_code == 503
    assert "el documento no quedó incorporado" in respuesta.content.decode()
    assert Documento.objects.filter(solicitud_gasto=e.gasto).count() == 0
    assert not e.raiz.exists() or not any(e.raiz.rglob("*"))


@pytest.mark.django_db
def test_post_de_carga_exige_csrf(escenario_comun):
    e = escenario_comun
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(e.a)
    respuesta = cliente.post(
        reverse("gastos:documentos", kwargs={"pk": e.gasto.pk}),
        {
            "archivo": _pdf(),
            "tipo": Documento.Tipo.FACTURA_PROVEEDOR,
            "procedencia": Documento.Procedencia.SOLICITANTE,
        },
    )

    assert respuesta.status_code == 403
    assert Documento.objects.filter(solicitud_gasto=e.gasto).count() == 0
