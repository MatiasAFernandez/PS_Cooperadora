"""Permisos, historial, reemplazos y atomicidad de revisión con PostgreSQL real."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Event

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client
from django.urls import reverse

from documentos.acceso import DocumentoNoVisible
from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento, RevisionDocumento
from documentos.revision import (
    ConflictoRevision,
    consultar_revision,
    revisar,
    version_aceptada,
)
from documentos.services import incorporar
from gastos.contracts import DocumentVerificationError

from .helpers import archivo_pdf


@pytest.fixture
def revision(escenario_comun):
    e = escenario_comun
    e.revisor = replace(
        e.actor_staff, capabilities=e.actor_staff.capabilities | {"documentos.revisar"}
    )
    e.documento = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=archivo_pdf(),
        tipo="FACTURA_PROVEEDOR",
        procedencia="SOLICITANTE",
    )
    return e


def registrar(e, **cambios):
    return revisar(
        **(
            dict(
                actor=e.revisor,
                documento_id=e.documento.pk,
                resultado="ACEPTADO",
                motivo="",
                revision_esperada=0,
            )
            | cambios
        )
    )


@pytest.mark.parametrize("circuito", ["gastos", "facturacion"])
def test_revision_historial_y_resultado_no_cambian_tramite(revision, circuito):
    e = revision
    if circuito == "facturacion":
        e.documento = incorporar(
            actor=e.actor_b,
            referencia=f"facturacion:{e.factura.pk}",
            archivo=archivo_pdf(),
            tipo="COMPROBANTE_COBRO",
            procedencia="SOLICITANTE",
        )
    assert not version_aceptada(e.documento)
    primera = registrar(e)
    assert version_aceptada(e.documento)
    segunda = registrar(
        e, resultado="OBSERVADO", motivo="Falta un dato", revision_esperada=primera.pk
    )
    assert not version_aceptada(e.documento)
    _, historial = consultar_revision(actor=e.revisor, documento_id=e.documento.pk)
    eventos = [r.como_historial() for r in historial]
    assert [x.estado_resultante for x in eventos] == ["ACEPTADO", "OBSERVADO"]
    assert all(x.actor_id == str(e.staff.pk) and x.fecha_hora.tzinfo for x in eventos)
    assert eventos[0].tramite_ref == f"{circuito}:{e.gasto.pk}"
    assert primera.fecha <= segunda.fecha
    e.gasto.refresh_from_db()
    e.factura.refresh_from_db()
    assert e.gasto.estado == "aceptada" and e.factura.estado == "BORRADOR_TECNICO"


@pytest.mark.parametrize(
    "resultado,motivo",
    [
        ("DESCONOCIDO", ""),
        ("PENDIENTE", ""),
        ("OBSERVADO", "  "),
        ("RECHAZADO", ""),
        ("ACEPTADO", "x" * 2001),
        ("ACEPTADO", "nul\x00"),
    ],
)
def test_revision_invalida_sin_efectos(revision, resultado, motivo):
    with pytest.raises(ValidationError):
        registrar(revision, resultado=resultado, motivo=motivo)
    assert not RevisionDocumento.objects.exists()


def test_permisos_objeto_inexistente_y_capacidades_independientes(revision):
    e = revision
    with pytest.raises(PermissionDenied):
        registrar(e, actor=e.actor_staff)  # Leer y pagar no permiten revisar.
    ajeno = replace(e.actor_b, capabilities=e.actor_b.capabilities | {"documentos.revisar"})
    with pytest.raises(DocumentoNoVisible):
        registrar(e, actor=ajeno)
    with pytest.raises(DocumentoNoVisible):
        registrar(e, documento_id=2147483647)
    with pytest.raises(PermissionDenied):
        registrar(e, actor=replace(e.revisor, capabilities=frozenset({"documentos.revisar"})))
    assert not RevisionDocumento.objects.exists()


def test_repeticion_y_rollback_no_dejan_hechos_parciales(revision, monkeypatch):
    e = revision
    primera = registrar(e)
    with pytest.raises(ConflictoRevision):
        registrar(e)
    with pytest.raises(ConflictoRevision):
        registrar(e, revision_esperada=primera.pk)
    crear = RevisionDocumento.objects.create

    def fallar_despues(**kwargs):
        crear(**kwargs)
        raise RuntimeError("Fallo sintético después de escribir")

    monkeypatch.setattr(RevisionDocumento.objects, "create", fallar_despues)
    with pytest.raises(RuntimeError):
        registrar(e, resultado="RECHAZADO", motivo="Inválido", revision_esperada=primera.pk)
    assert RevisionDocumento.objects.count() == 1
    assert version_aceptada(e.documento)


def test_reemplazo_conserva_revision_y_empieza_pendiente(revision):
    e = revision
    original = registrar(e)
    nuevo = incorporar(
        actor=e.actor_a,
        referencia=e.documento.referencia_tramite,
        archivo=archivo_pdf(),
        tipo=e.documento.tipo,
        procedencia="SOLICITANTE",
        reemplaza_id=e.documento.pk,
    )
    assert not version_aceptada(nuevo) and not version_aceptada(e.documento)
    assert not nuevo.revisiones.exists() and e.documento.revisiones.count() == 1
    with pytest.raises(ConflictoRevision):
        registrar(e, resultado="OBSERVADO", motivo="Histórico", revision_esperada=original.pk)


def test_historial_inmutable_en_orm_y_sql(revision):
    registro = registrar(revision)
    registro.resultado = "RECHAZADO"
    with pytest.raises(IntegrityError):
        registro.save()
    for sql in (
        "UPDATE documentos_revisiondocumento SET motivo = 'alterado' WHERE id = %s",
        "DELETE FROM documentos_revisiondocumento WHERE id = %s",
    ):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, [registro.pk])
    with pytest.raises(IntegrityError), transaction.atomic():
        RevisionDocumento.objects.filter(pk=registro.pk).update(resultado="RECHAZADO")
    registro.refresh_from_db()
    assert registro.resultado == "ACEPTADO"


@pytest.mark.parametrize("resultado", ["OBSERVADO", "RECHAZADO"])
@pytest.mark.parametrize("motivo", [
    " ", "\t", "\n", "\r\n", " \t\n\r\v\f ", "\x1c\x1f", "\x85", "\xa0",
    "\u1680\u2000\u200a", "\u2028\u2029\u202f\u205f\u3000",
])
def test_sql_rechaza_motivo_solo_whitespace(revision, resultado, motivo):
    assert not motivo.strip()
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO documentos_revisiondocumento "
            "(documento_id, resultado, motivo, actor_id, fecha) VALUES (%s,%s,%s,%s,NOW())",
            [revision.documento.pk, resultado, motivo, revision.staff.pk],
        )
    assert not RevisionDocumento.objects.exists()


@pytest.mark.parametrize("resultado", ["OBSERVADO", "RECHAZADO"])
def test_sql_admite_motivo_con_texto(revision, resultado):
    motivo = "\tDetalle sintético\n"
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO documentos_revisiondocumento "
            "(documento_id, resultado, motivo, actor_id, fecha) VALUES (%s,%s,%s,%s,NOW())",
            [revision.documento.pk, resultado, motivo, revision.staff.pk],
        )
    assert RevisionDocumento.objects.get().motivo == motivo


@pytest.mark.parametrize("resultado", ["OBSERVADO", "RECHAZADO"])
def test_c01_no_ofrece_ni_verifica_revision_negativa(revision, resultado):
    e = revision
    proveedor = ProveedorDocumentalGastos()
    assert proveedor.listar_opciones_para_pago(actor=e.revisor, gasto=e.gasto)
    registro = registrar(e, resultado=resultado, motivo="No conforme")
    assert not proveedor.listar_opciones_para_pago(actor=e.revisor, gasto=e.gasto)
    with pytest.raises(DocumentVerificationError), transaction.atomic():
        proveedor.verificar_y_bloquear_documento(
            actor=e.revisor,
            gasto=e.gasto,
            referencia_documental=str(e.documento.referencia_version),
        )
    registrar(e, revision_esperada=registro.pk)
    with transaction.atomic():
        assert proveedor.verificar_y_bloquear_documento(
            actor=e.revisor,
            gasto=e.gasto,
            referencia_documental=str(e.documento.referencia_version),
        )


def test_http_csrf_resultados_historial_y_revocacion(revision):
    e = revision
    e.staff.groups.add(Group.objects.get_or_create(name="demo_documentos_revision")[0])
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(e.staff)
    url = reverse("documentos:revision", args=[e.documento.pk])
    respuesta = cliente.get(url)
    assert respuesta.status_code == 200 and b"Pendiente" in respuesta.content
    assert respuesta["Cache-Control"] == "private, no-store"
    datos = {
        "resultado": "RECHAZADO",
        "motivo": "<script>ficticio</script>",
        "revision_esperada": 0,
    }
    assert cliente.post(url, datos).status_code == 403
    datos["csrfmiddlewaretoken"] = cliente.cookies["csrftoken"].value
    assert cliente.post(url, dict(datos, resultado="")).status_code == 400
    assert not RevisionDocumento.objects.exists()
    assert cliente.post(url, datos).status_code == 302
    assert cliente.post(url, datos).status_code == 409
    html = cliente.get(url).content.decode()
    assert "RECHAZADO" in html and "&lt;script&gt;" in html
    assert "<script>ficticio</script>" not in html
    e.staff.groups.remove(Group.objects.get(name="demo_documentos_revision"))
    assert cliente.post(url, dict(datos, revision_esperada=1)).status_code == 403
    assert RevisionDocumento.objects.count() == 1
    ajeno = Client()
    ajeno.force_login(e.b)
    assert ajeno.get(url).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_dos_revisiones_concurrentes_un_solo_hecho(revision):
    e = revision
    barrera = Barrier(2)

    def worker():
        try:
            barrera.wait(timeout=10)
            registrar(e)
            return "ok"
        except ConflictoRevision:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: worker(), range(2))) == ["conflicto", "ok"]
    assert RevisionDocumento.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_revision_y_reemplazo_comparten_bloqueo(revision):
    e = revision
    barrera = Barrier(2)

    def revisar_en_paralelo():
        try:
            barrera.wait(timeout=10)
            registrar(e)
            return "ok"
        except ConflictoRevision:
            return "conflicto"
        finally:
            connections.close_all()

    def reemplazar():
        try:
            barrera.wait(timeout=10)
            return incorporar(
                actor=e.actor_a,
                referencia=e.documento.referencia_tramite,
                archivo=archivo_pdf(),
                tipo=e.documento.tipo,
                procedencia="SOLICITANTE",
                reemplaza_id=e.documento.pk,
            ).pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        tarea = pool.submit(revisar_en_paralelo)
        nuevo = pool.submit(reemplazar).result(timeout=20)
        assert tarea.result(timeout=20) in {"ok", "conflicto"}
    assert not version_aceptada(Documento.objects.get(pk=nuevo))
    assert not version_aceptada(e.documento)


@pytest.mark.django_db(transaction=True)
def test_c01_conserva_resultado_hasta_fin_de_transaccion(revision):
    e = revision
    inicio, fin = Event(), Event()

    def observar():
        try:
            inicio.set()
            registrar(e, resultado="OBSERVADO", motivo="Revisar respaldo")
        finally:
            connections.close_all()
            fin.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            ProveedorDocumentalGastos().verificar_y_bloquear_documento(
                actor=e.revisor,
                gasto=e.gasto,
                referencia_documental=str(e.documento.referencia_version),
            )
            tarea = pool.submit(observar)
            assert inicio.wait(timeout=5)
            assert not fin.wait(timeout=0.2)
            assert not e.documento.revisiones.exists()
        tarea.result(timeout=10)
    assert e.documento.revisiones.get().resultado == "OBSERVADO"


def test_preparacion_revision_es_optativa_y_no_otorga_pago(escenario_comun):
    from io import StringIO

    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    from identidad.services import resolve_actor

    call_command("preparar_identidad_demo", facturacion=True, stdout=StringIO())
    user = get_user_model().objects.get(username="demo_o")
    assert not user.groups.filter(name="demo_documentos_revision").exists()
    password = user.password
    call_command("preparar_identidad_demo", revision_documental=True, stdout=StringIO())
    call_command("preparar_identidad_demo", revision_documental=True, stdout=StringIO())
    user.refresh_from_db()
    assert user.password == password
    cliente = Client()
    cliente.force_login(user)
    actor = resolve_actor(cliente.get(reverse("identidad:inicio")).wsgi_request)
    assert "documentos.revisar" in actor.capabilities
    assert "gastos.registrar_pago" not in actor.capabilities
