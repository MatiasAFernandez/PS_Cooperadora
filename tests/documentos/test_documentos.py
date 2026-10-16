"""DOC-R01–R03 con PostgreSQL y almacenamiento temporal."""

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client
from django.urls import reverse

from documentos.models import Documento
from documentos.policy import ArchivoInvalido, validar_archivo
from documentos.services import TIPOS_ELEGIBLES_PAGO_GASTOS, almacenamiento
from gastos.models import SolicitudGasto

PDF = b"%PDF-1.7\nArchivo sintetico\n%%EOF"


def subida(contenido=PDF, nombre="prueba.pdf", content_type=None):
    if content_type is None:
        content_type = {
            ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png",
        }.get(Path(nombre).suffix, "application/octet-stream")
    return SimpleUploadedFile(nombre, contenido, content_type=content_type)


@pytest.fixture
def escenario(db, settings, tmp_path):
    settings.DEMO_IDENTITY_ENABLED = True
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "privado"
    User = get_user_model()
    a = User.objects.create_user(username="doc_a", password="demo")
    b = User.objects.create_user(username="doc_b", password="demo")
    grupos = (
        "demo_solicitante",
        "demo_documentos_aporte",
        "demo_documentos_metadatos",
        "demo_documentos_descarga",
    )
    for nombre in grupos:
        a.groups.add(Group.objects.get_or_create(name=nombre)[0])
    b.groups.add(Group.objects.get_or_create(name="demo_solicitante")[0])
    gasto = SolicitudGasto.objects.create(
        concepto="Ejemplo", monto_estimado="1.00", unidad_requirente="Prueba", solicitante=a
    )
    otro = SolicitudGasto.objects.create(
        concepto="Ajeno", monto_estimado="1.00", unidad_requirente="Prueba", solicitante=b
    )
    cliente = Client()
    cliente.force_login(a)
    return a, b, gasto, otro, cliente, Path(settings.DOCUMENT_STORAGE_ROOT)


def ruta(gasto):
    return reverse("documentos:tramite", kwargs={"modulo": "gastos", "tramite_id": gasto.pk})


def incorporar(
    cliente, gasto, archivo=None,
    tipo=Documento.Tipo.FACTURA_PROVEEDOR,
    procedencia=Documento.Procedencia.SOLICITANTE,
):
    return cliente.post(
        ruta(gasto),
        {"archivo": archivo or subida(), "tipo": tipo, "procedencia": procedencia},
    )


def test_alta_metadatos_y_descarga_privada(escenario):
    a, _, gasto, _, cliente, raiz = escenario
    respuesta = incorporar(cliente, gasto)
    assert respuesta.status_code == 201
    documento = Documento.objects.get()
    assert documento.solicitud_gasto_id == gasto.pk
    assert documento.autor_id == a.pk
    assert documento.referencia_tramite == f"gastos:{gasto.pk}"
    assert documento.formato == "application/pdf"
    assert documento.tipo == Documento.Tipo.FACTURA_PROVEEDOR
    assert documento.procedencia == Documento.Procedencia.SOLICITANTE
    assert documento.fecha_incorporacion is not None
    assert (raiz / documento.archivo).read_bytes() == PDF
    assert "archivo" not in respuesta.json()
    assert respuesta.json()["tamano"] == len(PDF)

    listado = cliente.get(ruta(gasto))
    detalle = cliente.get(reverse("documentos:detalle", args=[documento.pk]))
    descarga = cliente.get(reverse("documentos:archivo", args=[documento.pk]))
    assert listado.status_code == detalle.status_code == descarga.status_code == 200
    assert listado.json()["documentos"][0]["id"] == documento.pk
    assert b"".join(descarga.streaming_content) == PDF
    assert descarga["Cache-Control"] == "private, no-store"
    assert "attachment" in descarga["Content-Disposition"]


@pytest.mark.parametrize(
    ("contenido", "nombre"),
    [
        (b"texto", "prueba.pdf"),
        (PDF, "prueba.exe"),
        (b"", "prueba.pdf"),
    ],
)
def test_archivo_invalido_no_deja_registro_ni_bytes(escenario, contenido, nombre):
    _, _, gasto, _, cliente, raiz = escenario
    respuesta = incorporar(cliente, gasto, subida(contenido, nombre))
    assert respuesta.status_code == 400
    assert not Documento.objects.exists()
    assert not raiz.exists() or not list(raiz.rglob("*"))


def test_limite_exacto_y_exceso(settings):
    assert settings.DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES == 10 * 1024 * 1024
    contenido = b"%PDF-" + b"x" * (settings.DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES - 5)
    assert validar_archivo(subida(contenido)).contenido == contenido
    with pytest.raises(ArchivoInvalido):
        validar_archivo(subida(contenido + b"x"))


@pytest.mark.parametrize(
    ("contenido", "nombre", "formato"),
    [
        (b"\xff\xd8\xffdatos\xff\xd9", "imagen.jpeg", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\ndatos", "imagen.png", "image/png"),
    ],
)
def test_formatos_de_imagen_admitidos(settings, contenido, nombre, formato):
    assert validar_archivo(subida(contenido, nombre)).formato == formato


def test_mime_declarado_debe_coincidir_con_firma():
    with pytest.raises(ArchivoInvalido):
        validar_archivo(subida(PDF, content_type="image/png"))


def test_catalogos_y_procedencia_del_solicitante_se_validan_antes_de_escribir(escenario):
    _, _, gasto, _, cliente, raiz = escenario
    assert incorporar(
        cliente, gasto, tipo=Documento.Tipo.COMPROBANTE_PAGO,
        procedencia=Documento.Procedencia.EXTERNO_BANCO,
    ).status_code == 403
    assert incorporar(
        cliente, gasto, tipo=Documento.Tipo.FACTURA_EMITIDA,
        procedencia=Documento.Procedencia.SOLICITANTE,
    ).status_code == 403
    assert incorporar(cliente, gasto, tipo="respaldo").status_code == 400
    assert incorporar(cliente, gasto, procedencia="desconocida").status_code == 400
    assert not Documento.objects.exists()
    assert not raiz.exists() or not any(p.is_file() for p in raiz.rglob("*"))


def test_factura_y_ticket_se_clasifican_distintos_para_el_contrato_c01(escenario):
    _, _, gasto, _, cliente, _ = escenario
    assert incorporar(cliente, gasto, tipo=Documento.Tipo.FACTURA_PROVEEDOR).status_code == 201
    assert incorporar(cliente, gasto, tipo=Documento.Tipo.TICKET_PROVEEDOR).status_code == 201
    factura, ticket = Documento.objects.filter(solicitud_gasto=gasto).order_by("id")
    assert factura.tipo == Documento.Tipo.FACTURA_PROVEEDOR
    assert ticket.tipo == Documento.Tipo.TICKET_PROVEEDOR
    assert factura.tipo in TIPOS_ELEGIBLES_PAGO_GASTOS
    assert ticket.tipo not in TIPOS_ELEGIBLES_PAGO_GASTOS


def test_personal_aporta_procedencias_admitidas_y_admite_multiples_versiones(escenario):
    usuario, _, gasto, otro, cliente, _ = escenario
    usuario.groups.add(Group.objects.get_or_create(name="demo_operadora")[0])
    assert incorporar(
        cliente, gasto, tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.INTERNO_COOPERADORA,
    ).status_code == 201
    assert incorporar(
        cliente, gasto, tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.INTERNO_COOPERADORA,
    ).status_code == 201
    assert incorporar(
        cliente, otro, tipo=Documento.Tipo.COMPROBANTE_PAGO,
        procedencia=Documento.Procedencia.EXTERNO_BANCO,
    ).status_code == 201
    assert incorporar(
        cliente, gasto, tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.EXTERNO_BANCO,
    ).status_code == 400
    assert incorporar(cliente, gasto).status_code == 403
    assert Documento.objects.filter(solicitud_gasto=gasto).count() == 2
    assert Documento.objects.filter(solicitud_gasto=otro).count() == 1


def test_no_permite_almacenar_bajo_archivos_estaticos(settings):
    settings.DOCUMENT_STORAGE_ROOT = settings.STATIC_ROOT / "documentos"
    with pytest.raises(ImproperlyConfigured):
        almacenamiento()


def test_ajeno_y_referencia_cruzada_no_revelan_documentos(escenario):
    _, b, gasto, otro, cliente, _ = escenario
    assert incorporar(cliente, otro).status_code == 404
    referencia_cruzada = reverse("documentos:tramite", args=["facturacion", gasto.pk])
    assert cliente.get(referencia_cruzada).status_code == 404
    assert incorporar(cliente, gasto).status_code == 201
    documento = Documento.objects.get()
    for nombre in ("demo_documentos_metadatos", "demo_documentos_descarga"):
        b.groups.add(Group.objects.get(name=nombre))
    ajeno = Client()
    ajeno.force_login(b)
    assert ajeno.get(ruta(gasto)).status_code == 404
    assert ajeno.get(reverse("documentos:detalle", args=[documento.pk])).status_code == 404
    assert ajeno.get(reverse("documentos:archivo", args=[documento.pk])).status_code == 404
    intento = ajeno.post(
        ruta(gasto), {"archivo": subida(), "tipo": "x", "procedencia": "x"}
    )
    assert intento.status_code == 404
    assert Documento.objects.count() == 1


def test_capacidades_documentales_independientes_y_sesion(escenario):
    a, _, gasto, _, cliente, _ = escenario
    assert incorporar(cliente, gasto).status_code == 201
    documento = Documento.objects.get()
    Group.objects.get(name="demo_documentos_descarga").user_set.remove(a)
    assert cliente.get(reverse("documentos:detalle", args=[documento.pk])).status_code == 200
    assert cliente.get(reverse("documentos:archivo", args=[documento.pk])).status_code == 403
    Group.objects.get(name="demo_documentos_metadatos").user_set.remove(a)
    assert cliente.get(reverse("documentos:detalle", args=[documento.pk])).status_code == 403
    Group.objects.get(name="demo_documentos_aporte").user_set.remove(a)
    assert incorporar(cliente, gasto).status_code == 403
    assert Documento.objects.count() == 1
    assert Client().get(reverse("documentos:detalle", args=[documento.pk])).status_code == 403


def test_fallo_despues_de_escribir_limpia_archivo_y_metadatos(escenario, monkeypatch):
    _, _, gasto, _, cliente, raiz = escenario

    class FallaDespuesDeEscribir(FileSystemStorage):
        def save(self, name, content, max_length=None):
            super().save(name, content, max_length=max_length)
            raise OSError("fallo simulado")

    monkeypatch.setattr(
        "documentos.services.almacenamiento",
        lambda: FallaDespuesDeEscribir(location=raiz, base_url=None),
    )
    assert incorporar(cliente, gasto).status_code == 503
    assert not Documento.objects.exists()
    assert not list(raiz.rglob("*")) or not any(p.is_file() for p in raiz.rglob("*"))


def test_fallo_de_base_despues_de_guardar_limpia_archivo(escenario, monkeypatch):
    _, _, gasto, _, cliente, raiz = escenario

    def fallo(*args, **kwargs):
        raise IntegrityError("fallo simulado")

    monkeypatch.setattr(Documento.objects, "create", fallo)
    with pytest.raises(IntegrityError):
        incorporar(cliente, gasto)
    assert not Documento.objects.exists()
    assert not any(p.is_file() for p in raiz.rglob("*"))


def test_descarga_si_falta_archivo_responde_indisponible(escenario):
    _, _, gasto, _, cliente, raiz = escenario
    assert incorporar(cliente, gasto).status_code == 201
    documento = Documento.objects.get()
    (raiz / documento.archivo).unlink()
    respuesta = cliente.get(reverse("documentos:archivo", args=[documento.pk]))
    assert respuesta.status_code == 503


def test_csrf_protege_incorporacion(escenario):
    a, _, gasto, _, _, _ = escenario
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(a)
    assert incorporar(cliente, gasto).status_code == 403
    assert not Documento.objects.exists()


def test_fk_no_se_puede_reasignar_por_orm_ni_sql(escenario):
    _, b, gasto, otro, cliente_a, _ = escenario
    for nombre in ("demo_documentos_metadatos", "demo_documentos_descarga"):
        b.groups.add(Group.objects.get(name=nombre))
    cliente_b = Client()
    cliente_b.force_login(b)
    assert incorporar(cliente_a, gasto).status_code == 201
    documento = Documento.objects.get()
    url_archivo = reverse("documentos:archivo", args=[documento.pk])
    assert cliente_b.get(url_archivo).status_code == 404

    def sql_update():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE documentos_documento SET solicitud_gasto_id = %s WHERE id = %s",
                [otro.pk, documento.pk],
            )

    intentos = (
        lambda: Documento.objects.filter(pk=documento.pk).update(solicitud_gasto=otro),
        sql_update,
    )
    documento.solicitud_gasto = otro
    with pytest.raises(IntegrityError), transaction.atomic():
        documento.save(update_fields=["solicitud_gasto"])
    for intento in intentos:
        with pytest.raises(IntegrityError), transaction.atomic():
            intento()
        documento.refresh_from_db()
        assert documento.solicitud_gasto_id == gasto.pk
        assert cliente_b.get(url_archivo).status_code == 404
        assert b"".join(cliente_a.get(url_archivo).streaming_content) == PDF

    with pytest.raises(ProtectedError):
        gasto.delete()
    assert Documento.objects.filter(pk=documento.pk, solicitud_gasto=gasto).exists()
