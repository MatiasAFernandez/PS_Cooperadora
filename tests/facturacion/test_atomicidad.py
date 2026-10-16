"""Carreras reales, rollback y recuperación de bytes del recorrido funcional."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

import pytest
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.db import OperationalError, connections
from test_recorrido import observar, pdf, presentar

from documentos.models import Documento
from facturacion import workflow
from facturacion.models import EventoFacturacion, SolicitudFacturacion

pytestmark = pytest.mark.django_db(transaction=True)


def test_dos_observaciones_concurrentes_un_solo_evento(escenario, datos):
    e = escenario
    solicitud = presentar(e, datos)
    barrera = Barrier(2)

    def worker():
        try:
            barrera.wait(timeout=10)
            workflow.observar_solicitud_facturacion(
                actor=e.actores["o"],
                numero_publico=solicitud.pk,
                motivo="Concurrente",
                version_esperada=1,
            )
            return "ok"
        except workflow.ConflictoConcurrenciaError:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(resultados) == ["conflicto", "ok"]
    solicitud.refresh_from_db()
    assert solicitud.version_concurrencia == 2
    assert solicitud.eventos.filter(tipo_evento="OBSERVACION").count() == 1


def test_dos_altas_concurrentes_restriccion_uuid(escenario, datos, monkeypatch):
    e = escenario
    token = workflow.emitir_token(e.actores["a"])
    barrera = Barrier(2)
    validar = workflow._datos

    def sincronizar(*args, **kwargs):
        resultado = validar(*args, **kwargs)
        barrera.wait(timeout=10)
        return resultado

    monkeypatch.setattr(workflow, "_datos", sincronizar)

    def worker():
        try:
            presentar(e, datos, token=token, archivo_comprobante=pdf())
            return "ok"
        except workflow.PresentacionDuplicadaError:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(resultados) == ["conflicto", "ok"]
    assert SolicitudFacturacion.objects.count() == 1
    assert EventoFacturacion.objects.count() == 1
    assert Documento.objects.count() == 1
    assert len(list((e.raiz / "documentos").iterdir())) == 1


def test_dos_correcciones_concurrentes_un_solo_evento(escenario, datos):
    e = escenario
    solicitud = presentar(e, datos)
    observar(e, solicitud)
    barrera = Barrier(2)

    def worker():
        try:
            barrera.wait(timeout=10)
            workflow.corregir_solicitud_facturacion(
                actor=e.actores["a"],
                numero_publico=solicitud.pk,
                datos=datos,
                version_esperada=2,
            )
            return "ok"
        except workflow.ConflictoConcurrenciaError:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(resultados) == ["conflicto", "ok"]
    solicitud.refresh_from_db()
    assert solicitud.version_concurrencia == 3
    assert solicitud.eventos.filter(tipo_evento="CORRECCION").count() == 1


def _fallar_evento(**kwargs):
    raise RuntimeError("Fallo de evento sintético")


@pytest.mark.parametrize("correccion", [False, True])
def test_fallo_evento_revierte_datos_y_bytes(escenario, datos, monkeypatch, correccion):
    e = escenario
    if correccion:
        solicitud = presentar(e, datos, archivo_comprobante=pdf())
        anterior = solicitud.documento_comprobante_inicial
        observar(e, solicitud)
    monkeypatch.setattr(EventoFacturacion.objects, "create", _fallar_evento)
    with pytest.raises(RuntimeError, match="Fallo de evento"):
        if correccion:
            workflow.corregir_solicitud_facturacion(
                actor=e.actores["a"],
                numero_publico=solicitud.pk,
                datos=dict(datos, centro_costo="QUITEX", detalle_factura="No persistir"),
                archivo_comprobante=pdf(),
                version_esperada=2,
            )
        else:
            presentar(e, datos, archivo_comprobante=pdf())
    if correccion:
        solicitud.refresh_from_db()
        assert solicitud.estado == "OBSERVADA" and solicitud.version_concurrencia == 2
        assert (
            solicitud.centro_costo == "GISTAQ"
            and solicitud.detalle_factura == datos["detalle_factura"]
        )
        assert solicitud.documento_comprobante_inicial_id == anterior.pk
        assert Documento.objects.count() == 1
        assert [p.name for p in (e.raiz / "documentos").iterdir()] == [
            anterior.archivo.split("/")[-1]
        ]
    else:
        assert not SolicitudFacturacion.objects.exists()
        assert not Documento.objects.exists()
        assert not list((e.raiz / "documentos").iterdir())
    assert not list((e.raiz / ".operaciones").glob("*.json"))


def test_borrado_fallido_conserva_error_y_recupera_manifiesto(
    escenario, datos, monkeypatch, caplog
):
    e = escenario
    monkeypatch.setattr(EventoFacturacion.objects, "create", _fallar_evento)
    borrar = FileSystemStorage.delete

    def falla(*args, **kwargs):
        raise OSError("Fallo de borrado sintético")

    monkeypatch.setattr(FileSystemStorage, "delete", falla)
    with pytest.raises(RuntimeError, match="Fallo de evento"):
        presentar(e, datos, archivo_comprobante=pdf())
    assert "Limpieza documental pendiente" in caplog.text
    assert list((e.raiz / ".operaciones").glob("*.json"))
    monkeypatch.setattr(FileSystemStorage, "delete", borrar)
    call_command("reconciliar_archivos", aplicacion_detenida=True, stdout=StringIO())
    assert not list((e.raiz / "documentos").iterdir())
    assert not list((e.raiz / ".operaciones").glob("*.json"))


def test_storage_escribe_y_falla_luego_se_compensa(escenario, datos, monkeypatch):
    save = FileSystemStorage.save

    def escribir_y_fallar(self, name, content, **kwargs):
        save(self, name, content, **kwargs)
        raise OSError("Fallo después de escribir")

    monkeypatch.setattr(FileSystemStorage, "save", escribir_y_fallar)
    with pytest.raises(OSError, match="después de escribir"):
        presentar(escenario, datos, archivo_comprobante=pdf())
    assert not SolicitudFacturacion.objects.exists()
    assert not list((escenario.raiz / "documentos").iterdir())


def test_commit_incierto_no_borra_archivo_confirmado(escenario, datos, monkeypatch):
    conn = connections["default"]
    commit = conn.commit

    def confirmar_y_perder_respuesta():
        commit()
        raise OperationalError("Respuesta de commit perdida")

    monkeypatch.setattr(conn, "commit", confirmar_y_perder_respuesta)
    with pytest.raises(OperationalError):
        presentar(escenario, datos, archivo_comprobante=pdf())
    monkeypatch.setattr(conn, "commit", commit)
    documento = Documento.objects.get()
    assert (escenario.raiz / documento.archivo).exists()
    assert list((escenario.raiz / ".operaciones").glob("*.json"))
    call_command("reconciliar_archivos", aplicacion_detenida=True, stdout=StringIO())
    assert (escenario.raiz / documento.archivo).exists()
    assert not list((escenario.raiz / ".operaciones").glob("*.json"))
