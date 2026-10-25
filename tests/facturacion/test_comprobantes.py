"""Registro externo, identidad global, permisos, rollback y concurrencia reales."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from threading import Barrier

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse

from documentos.models import Documento
from documentos.policy import ArchivoInvalido
from documentos.services import incorporar
from facturacion import comprobantes
from facturacion.comprobantes import registrar_comprobante, resumen_comprobantes
from facturacion.models import ComprobanteExterno, EventoFacturacion
from facturacion.permissions import ObjetoNoVisibleError
from facturacion.workflow import (
    ConflictoConcurrenciaError,
    emitir_token,
    presentar_solicitud_facturacion,
)

pytestmark = pytest.mark.django_db(transaction=True)


def pdf():
    return SimpleUploadedFile("externo.pdf", b"%PDF-1.7\nFicticio\n%%EOF", "application/pdf")


@pytest.fixture
def entrada():
    return dict(
        tipo="FACTURA",
        cuit_emisor="30712345671",
        letra="A",
        punto_venta="1",
        numero="1",
        fecha_emision="2026-10-01",
        importe="100.25",
    )


@pytest.fixture
def solicitud(escenario, datos):
    return presentar_solicitud_facturacion(
        actor=escenario.actores["a"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )


def registrar(e, solicitud, entrada, **cambios):
    return registrar_comprobante(
        actor=e.actores["o"],
        numero_publico=solicitud.pk,
        datos=dict(entrada, **cambios),
        archivo_pdf=pdf(),
    )


def test_factura_notas_neto_historial_y_estado(escenario, solicitud, entrada):
    factura = registrar(escenario, solicitud, entrada)
    credito = registrar(escenario, solicitud, entrada, tipo="NOTA_CREDITO", importe="10.10")
    debito = registrar(escenario, solicitud, entrada, tipo="NOTA_DEBITO", importe="1.05")
    registrar(escenario, solicitud, entrada, tipo="NOTA_CREDITO", numero="2", importe="1.00")
    assert credito.factura_origen_id == debito.factura_origen_id == factura.pk
    assert resumen_comprobantes(solicitud)[1] == Decimal("90.20")
    assert factura.actor_id == escenario.usuarios["o"].pk
    assert factura.fecha_registro.tzinfo is not None
    assert factura.procedencia == factura.documento.procedencia == "EXTERNO_XUBIO"
    assert factura.documento.tramite_base_id == solicitud.tramite_base_id
    assert not factura.documento.revisiones.exists()
    solicitud.refresh_from_db()
    assert solicitud.estado == "PRESENTADA" and solicitud.version_concurrencia == 1
    assert solicitud.eventos.count() == 1  # Comprobantes son hechos propios, no cobros.
    c = Client()
    c.force_login(escenario.usuarios["a"])
    detalle = c.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    assert len(detalle.context["historial"]) == 5
    assert b"90,20" in detalle.content and b"Nota de" in detalle.content


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("importe", "0"),
        ("importe", "1.001"),
        ("importe", "NaN"),
        ("importe", 1.5),
        ("importe", True),
        ("importe", "10000000000.00"),
        ("cuit_emisor", "30712345679"),
        ("letra", "a"),
        ("punto_venta", "0"),
        ("numero", "0"),
        ("tipo", "DESCONOCIDO"),
        ("fecha_emision", "inválida"),
    ],
)
def test_datos_invalidos_sin_registro_ni_pdf(escenario, solicitud, entrada, campo, valor):
    with pytest.raises(ValidationError):
        registrar(escenario, solicitud, entrada, **{campo: valor})
    assert not ComprobanteExterno.objects.exists() and not Documento.objects.exists()


def test_pdf_obligatorio_y_solo_pdf(escenario, solicitud, entrada):
    for archivo in (None, SimpleUploadedFile("x.png", b"\x89PNG\r\n\x1a\nX", "image/png")):
        with pytest.raises((ValidationError, ArchivoInvalido)):
            registrar_comprobante(
                actor=escenario.actores["o"],
                numero_publico=solicitud.pk,
                datos=entrada,
                archivo_pdf=archivo,
            )
    assert not Documento.objects.exists() and not ComprobanteExterno.objects.exists()


def test_una_factura_y_nota_solo_con_origen_valido(escenario, solicitud, entrada):
    with pytest.raises(ValidationError):
        registrar(escenario, solicitud, entrada, tipo="NOTA_CREDITO")
    registrar(escenario, solicitud, entrada)
    with pytest.raises(ConflictoConcurrenciaError):
        registrar(escenario, solicitud, entrada, numero="2")
    with pytest.raises(ValidationError):
        registrar(escenario, solicitud, entrada, tipo="NOTA_DEBITO", letra="B")
    assert ComprobanteExterno.objects.count() == Documento.objects.count() == 1


def test_duplicado_global_y_ceros_iniciales(escenario, solicitud, datos, entrada):
    registrar(escenario, solicitud, entrada)
    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["b"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["b"]),
    )
    with pytest.raises(ConflictoConcurrenciaError):
        registrar(escenario, otra, entrada, punto_venta="00001", numero="00000001")
    assert ComprobanteExterno.objects.count() == Documento.objects.count() == 1


def test_permisos_independientes_y_objeto(escenario, solicitud, entrada):
    for clave in ("a", "l"):
        with pytest.raises(PermissionDenied):
            registrar_comprobante(
                actor=escenario.actores[clave],
                numero_publico=solicitud.pk,
                datos=entrada,
                archivo_pdf=pdf(),
            )
    with pytest.raises(ObjetoNoVisibleError):
        registrar_comprobante(
            actor=escenario.actores["b"],
            numero_publico=solicitud.pk,
            datos=entrada,
            archivo_pdf=pdf(),
        )
    with pytest.raises(PermissionDenied):
        registrar_comprobante(
            actor=replace(
                escenario.actores["o"], capabilities=frozenset({"facturacion.consultar_todas"})
            ),
            numero_publico=solicitud.pk,
            datos=entrada,
            archivo_pdf=pdf(),
        )
    assert not ComprobanteExterno.objects.exists()


@pytest.mark.parametrize("duplicado_global", [False, True])
def test_http_csrf_detalle_y_descarga_ajena(escenario, solicitud, entrada, datos, duplicado_global):
    url = reverse("facturacion:registrar_comprobante", args=[solicitud.pk])
    c = Client(enforce_csrf_checks=True)
    c.force_login(escenario.usuarios["o"])
    assert c.get(url).status_code == 200
    assert c.post(url, dict(entrada, archivo_pdf=pdf())).status_code == 403
    contenido = dict(entrada, archivo_pdf=pdf(), csrfmiddlewaretoken=c.cookies["csrftoken"].value)
    assert c.post(url, contenido).status_code == 302
    destino = url
    if duplicado_global:
        otra = presentar_solicitud_facturacion(
            actor=escenario.actores["b"],
            datos=datos,
            token_presentacion=emitir_token(escenario.actores["b"]),
        )
        destino = reverse("facturacion:registrar_comprobante", args=[otra.pk])
    respuesta = c.post(destino, dict(contenido, archivo_pdf=pdf()))
    assert respuesta.status_code == 409
    assert respuesta.templates[0].name == "facturacion/comprobante_form.html"
    form = respuesta.context["form"]
    for campo, valor in entrada.items():
        assert form[campo].value() == valor
        assert str(form[campo]) in respuesta.content.decode()
    mensaje = (
        "Ese comprobante externo ya está registrado."
        if duplicado_global
        else "Esta solicitud ya tiene una factura."
    )
    assert mensaje in form.non_field_errors()
    assert mensaje in respuesta.content.decode()
    assert "volvé a seleccionarlo" in respuesta.content.decode()
    assert 'type="file"' in respuesta.content.decode()
    assert ComprobanteExterno.objects.count() == Documento.objects.count() == 1
    registro = ComprobanteExterno.objects.get()
    archivo = reverse("documentos:archivo", args=[registro.documento_id])
    for usuario, estado in (("a", 200), ("b", 404), ("l", 403)):
        otro = Client()
        otro.force_login(escenario.usuarios[usuario])
        respuesta = otro.get(archivo)
        assert respuesta.status_code == estado
        respuesta.close()
    ajeno = Client()
    ajeno.force_login(escenario.usuarios["b"])
    assert ajeno.get(url).status_code == 404
    assert ajeno.get(reverse("facturacion:detalle", args=[solicitud.pk])).status_code == 404


def test_fallo_despues_de_escribir_revierte_registro_y_bytes(
    escenario, solicitud, entrada, monkeypatch
):
    crear = ComprobanteExterno.objects.create

    def falla(**kwargs):
        crear(**kwargs)
        raise RuntimeError("Fallo sintético")

    monkeypatch.setattr(ComprobanteExterno.objects, "create", falla)
    with pytest.raises(RuntimeError):
        registrar(escenario, solicitud, entrada)
    assert not ComprobanteExterno.objects.exists() and not Documento.objects.exists()
    assert not list((escenario.raiz / "documentos").iterdir())
    assert EventoFacturacion.objects.count() == 1


def test_sql_protege_inmutabilidad_e_importe_no_finito(escenario, solicitud, entrada):
    registro = registrar(escenario, solicitud, entrada)
    for sql in (
        "UPDATE facturacion_comprobanteexterno SET numero=2 WHERE id=%s",
        "DELETE FROM facturacion_comprobanteexterno WHERE id=%s",
    ):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, [registro.pk])
    documento = incorporar(
        actor=escenario.actores["o"],
        referencia=f"facturacion:{solicitud.pk}",
        archivo=pdf(),
        tipo="NOTA_DEBITO_XUBIO",
        procedencia="EXTERNO_XUBIO",
    )
    with (
        pytest.raises(IntegrityError) as error,
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "INSERT INTO facturacion_comprobanteexterno "
            "(solicitud_id,tipo,cuit_emisor,letra,punto_venta,numero,fecha_emision,importe,"
            "procedencia,factura_origen_id,documento_id,actor_id,fecha_registro) "
            "VALUES (%s,'NOTA_DEBITO',%s,'A',1,2,%s,%s,'EXTERNO_XUBIO',%s,%s,%s,NOW())",
            [
                solicitud.pk,
                registro.cuit_emisor,
                registro.fecha_emision,
                Decimal("NaN"),
                registro.pk,
                documento.pk,
                escenario.usuarios["o"].pk,
            ],
        )
    assert error.value.__cause__.diag.constraint_name == "ck_comprobante_importe"
    assert ComprobanteExterno.objects.count() == 1


@pytest.mark.parametrize("cruce", ["documento", "factura_origen"])
def test_sql_rechaza_vinculos_ajenos(escenario, solicitud, datos, entrada, cruce):
    factura = registrar(escenario, solicitud, entrada)
    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["b"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["b"]),
    )
    factura_ajena = registrar(escenario, otra, entrada, numero="2")
    documento = incorporar(
        actor=escenario.actores["o"],
        referencia=f"facturacion:{otra.pk if cruce == 'documento' else solicitud.pk}",
        archivo=pdf(),
        tipo="NOTA_CREDITO_XUBIO",
        procedencia="EXTERNO_XUBIO",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ComprobanteExterno.objects.create(
            solicitud=solicitud,
            tipo="NOTA_CREDITO",
            cuit_emisor=factura.cuit_emisor,
            letra="A",
            punto_venta=1,
            numero=3,
            fecha_emision=factura.fecha_emision,
            importe="1.00",
            documento=documento,
            actor=escenario.usuarios["o"],
            factura_origen=factura_ajena if cruce == "factura_origen" else factura,
        )
    assert ComprobanteExterno.objects.count() == 2


def test_reversa_con_comprobantes_preserva_historial(escenario, solicitud, entrada):
    registro = registrar(escenario, solicitud, entrada)
    finales = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        with pytest.raises(DatabaseError, match="Hay comprobantes"):
            MigrationExecutor(connection).migrate([("facturacion", "0006_comprobantes_externos")])
    finally:
        # Una reversa multipaso puede haber deshecho migraciones posteriores antes del rechazo.
        MigrationExecutor(connection).migrate(finales)
    assert ComprobanteExterno.objects.get().pk == registro.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        ComprobanteExterno.objects.filter(pk=registro.pk).update(numero=2)


def test_upgrade_y_reversa_vacia_preservan_solicitud_y_pdf(escenario, solicitud):
    documento = incorporar(
        actor=escenario.actores["o"],
        referencia=f"facturacion:{solicitud.pk}",
        archivo=pdf(),
        tipo="FACTURA_EMITIDA_XUBIO",
        procedencia="EXTERNO_XUBIO",
    )
    contenido = (escenario.raiz / documento.archivo).read_bytes()
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("facturacion", "0005_integridad_respaldo")])
        assert "facturacion_comprobanteexterno" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(finales)
        solicitud.refresh_from_db()
        documento.refresh_from_db()
        assert solicitud.estado == "PRESENTADA" and solicitud.eventos.count() == 1
        assert (escenario.raiz / documento.archivo).read_bytes() == contenido
        assert not ComprobanteExterno.objects.exists()
    finally:
        MigrationExecutor(connection).migrate(finales)


def test_carrera_identidad_global_compensa_archivo_perdedor(
    escenario, solicitud, datos, entrada, monkeypatch
):
    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["b"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["b"]),
    )
    barrera = Barrier(2)
    original = comprobantes.incorporar

    def sincronizar(**kwargs):
        barrera.wait(timeout=10)
        return original(**kwargs)

    monkeypatch.setattr(comprobantes, "incorporar", sincronizar)

    def worker(solicitud_actual):
        try:
            registrar(escenario, solicitud_actual, entrada)
            return "ok"
        except ConflictoConcurrenciaError:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, [solicitud, otra])) == ["conflicto", "ok"]
    assert ComprobanteExterno.objects.count() == Documento.objects.count() == 1
    assert len(list((escenario.raiz / "documentos").iterdir())) == 1
