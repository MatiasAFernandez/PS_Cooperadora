"""Corrección de cobros conserva hechos, saldo y verificación por versión."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connections, transaction
from django.test import Client
from django.urls import reverse

from documentos.services import incorporar
from facturacion.atencion import acciones_inmediatas
from facturacion.cobros import (
    corregir_cobro,
    rectificar_cobro,
    registrar_cobro,
    resumen_cobros,
    verificar_cobro,
)
from facturacion.consultas import filtrar_solicitudes
from facturacion.forms import FiltroFacturacionForm
from facturacion.models import CobroExterno
from facturacion.permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles
from facturacion.seguimiento import diagnostico, respaldo_actual
from facturacion.workflow import ConflictoConcurrenciaError
from tests.facturacion.test_atencion import presentar
from tests.facturacion.test_cierre import aceptar, cobro, factura, operador, pdf, resolver

pytestmark = pytest.mark.django_db(transaction=True)


def datos_correccion(c, **cambios):
    return dict(
        dict(
            medio=c.medio,
            numero_operacion=c.numero_operacion,
            fecha_operacion=c.fecha_operacion.isoformat(),
            importe=str(c.importe),
            motivo="Corregir importe informado",
            resultado_esperado=c.resultado,
            revision=diagnostico(c.solicitud)["revision"],
        ),
        **cambios,
    )


def corregir(e, s, c, **cambios):
    return corregir_cobro(
        actor=e.actores["a"], numero=s.pk, cobro_id=c.pk, datos=datos_correccion(c, **cambios)
    )


def test_correccion_rechazada_historia_saldo_filtro_y_cierre(escenario, datos):
    e = escenario
    s = presentar(e, datos)
    f = factura(e, s)
    aceptar(e, f.documento)
    c = cobro(e, s, importe="25.00", confirmar=False)
    verificar_cobro(
        actor=operador(e),
        numero=s.pk,
        cobro_id=c.pk,
        datos={"resultado": "RECHAZADO", "motivo": "Importe incorrecto"},
    )
    assert acciones_inmediatas(e.actores["a"], s)[0].texto == "Modificar cobro"
    nuevo = corregir(e, s, c, importe="100.25")
    c.refresh_from_db()
    assert c.sustituido and str(c.importe) == "25.00"
    assert c.resultado == "RECHAZADO"
    assert nuevo.resultado == "PENDIENTE" and nuevo.reemplaza_id == c.pk
    assert nuevo.numero_en_solicitud == c.numero_en_solicitud == 1
    assert nuevo.documento.reemplaza_id == c.documento_id
    assert not nuevo.documento.revisiones.exists()
    activos, totales, historia = resumen_cobros(s)
    assert [x.pk for x in activos] == [nuevo.pk]
    assert str(totales["PENDIENTE"]) == "100.25" and not totales["RECHAZADO"]
    assert len(historia) == 3
    assert diagnostico(s)["faltas_cierre"]
    aceptar(e, nuevo.documento)
    verificar_cobro(
        actor=operador(e), numero=s.pk, cobro_id=nuevo.pk, datos={"resultado": "CONFIRMADO"}
    )
    filtro = FiltroFacturacionForm({"estado": "COBRADA_EN_REVISION"})
    assert list(filtrar_solicitudes(filtrar_solicitudes_visibles(e.actores["a"]), filtro)) == [s]
    assert not diagnostico(s)["faltas_cierre"]
    resolver(e, s)
    assert CobroExterno.todos.count() == 2


def test_titular_corrige_confirmado_con_rectificacion_y_revision_nueva(escenario, datos):
    e = escenario
    s = presentar(e, datos)
    c = cobro(e, s, confirmar=False)
    cliente = Client()
    cliente.force_login(e.usuarios["b"])
    url = reverse("facturacion:corregir_cobro", args=[s.pk, c.pk])
    assert cliente.get(url).status_code == 404
    with pytest.raises(ObjetoNoVisibleError):
        corregir_cobro(actor=e.actores["b"], numero=s.pk, cobro_id=c.pk, datos=datos_correccion(c))
    aceptar(e, factura(e, s).documento)
    aceptar(e, c.documento)
    verificar_cobro(
        actor=operador(e), numero=s.pk, cobro_id=c.pk, datos={"resultado": "CONFIRMADO"}
    )
    c.refresh_from_db()
    with pytest.raises(IntegrityError), transaction.atomic():
        CobroExterno.objects.filter(pk=c.pk).update(sustituido=True)
    cliente.force_login(e.usuarios["a"])
    pagina = cliente.get(url)
    assert pagina.status_code == 200
    assert "data-aviso-rectificacion" in pagina.content.decode()
    assert cliente.post(url, datos_correccion(c, resultado_esperado="PENDIENTE")).status_code == 409
    assert cliente.post(url, datos_correccion(c)).status_code == 400
    respuesta = cliente.post(
        url, datos_correccion(c, importe="110.00", resultado_esperado="CONFIRMADO")
    )
    assert respuesta.status_code == 302
    previo = CobroExterno.todos.get(pk=c.pk)
    nuevo = CobroExterno.objects.get(solicitud=s)
    assert previo.sustituido and previo.resultado == "RECTIFICADO"
    rectificacion = previo.verificacion.rectificacion
    assert rectificacion.actor_id == e.usuarios["a"].pk
    assert rectificacion.motivo == nuevo.motivo_correccion
    assert previo.verificacion.resultado == "CONFIRMADO"
    assert nuevo.reemplaza_id == previo.pk and nuevo.numero_operacion == previo.numero_operacion
    assert nuevo.resultado == "PENDIENTE" and not nuevo.documento.revisiones.exists()
    assert diagnostico(s)["confirmado"] == 0
    assert diagnostico(s)["faltas_cierre"]
    with pytest.raises(ValidationError, match="primero aceptá"):
        verificar_cobro(
            actor=operador(e), numero=s.pk, cobro_id=nuevo.pk, datos={"resultado": "CONFIRMADO"}
        )
    aceptar(e, nuevo.documento)
    verificar_cobro(
        actor=operador(e), numero=s.pk, cobro_id=nuevo.pk, datos={"resultado": "CONFIRMADO"}
    )
    assert str(diagnostico(s)["confirmado"]) == "110.00"
    resolver(e, s)


def test_operadora_corrige_rectificado_y_el_titular_conserva_su_cobro(escenario, datos):
    e = escenario
    s = presentar(e, datos)
    c = cobro(e, s)
    rectificar_cobro(actor=operador(e), numero=s.pk, cobro_id=c.pk, motivo="Fecha incorrecta")
    url = reverse("facturacion:corregir_cobro", args=[s.pk, c.pk])
    cliente = Client()
    cliente.force_login(e.usuarios["o"])
    assert cliente.get(url).status_code == 200
    respuesta = cliente.post(
        url, datos_correccion(c, fecha_operacion="2026-10-23", resultado_esperado="RECTIFICADO")
    )
    assert respuesta.status_code == 302
    nuevo = CobroExterno.objects.get(solicitud=s)
    assert nuevo.procedencia == "INTERNO_COOPERADORA"
    assert nuevo.actor_id == e.usuarios["o"].pk and nuevo.reemplaza_id == c.pk
    assert str(nuevo.fecha_operacion) == "2026-10-23"
    assert corregir(e, s, nuevo, importe="100.30").cobro_original.pk == c.pk


def test_cobro_interno_confirmado_exige_permiso_de_verificacion(escenario, datos):
    e = escenario
    s = presentar(e, datos)
    c = registrar_cobro(
        actor=operador(e),
        numero=s.pk,
        datos={
            "medio": "BNA_COMUN",
            "numero_operacion": "INTERNA-FICTICIA",
            "fecha_operacion": "2026-10-22",
            "importe": "99.25",
            "confirmar_al_registrar": True,
        },
        archivo=pdf(),
    )
    with pytest.raises(PermissionDenied):
        corregir(e, s, c, importe="100.25")
    url = reverse("facturacion:corregir_cobro", args=[s.pk, c.pk])
    cliente = Client()
    cliente.force_login(e.usuarios["o"])
    assert cliente.get(url).status_code == 403
    e.usuarios["o"].groups.add(Group.objects.get(name="demo_verificacion_cobros"))
    assert cliente.get(url).status_code == 200
    assert cliente.post(url, datos_correccion(c, importe="100.25")).status_code == 302
    assert CobroExterno.todos.get(pk=c.pk).resultado == "RECTIFICADO"


@pytest.mark.parametrize("cambio", ["vincular", "corregir", "adjuntar"])
def test_modificar_confirmado_con_documento(escenario, datos, cambio):
    e = escenario
    s = presentar(e, datos)
    c = cobro(e, s)
    sucesor = incorporar(
        actor=operador(e),
        referencia=f"facturacion:{s.pk}",
        archivo=pdf(),
        tipo="COMPROBANTE_COBRO",
        procedencia="EXTERNO_BANCO",
        reemplaza_id=c.documento_id,
    )
    aceptar(e, sucesor)
    cliente = Client()
    url = reverse("facturacion:corregir_cobro", args=[s.pk, c.pk])
    cliente.force_login(e.usuarios["a"])
    assert cliente.post(url, datos_correccion(c, archivo=pdf())).status_code == 403
    c.refresh_from_db()
    e.usuarios["o"].groups.add(Group.objects.get(name="demo_resolucion_facturacion"))
    cliente.force_login(e.usuarios["o"])
    assert cliente.post(
        url, datos_correccion(c, nuevo_id=sucesor.pk, importe="105.00")
    ).status_code == 403
    e.usuarios["o"].groups.add(Group.objects.get(name="demo_verificacion_cobros"))
    legado = reverse("facturacion:actualizar_respaldo", args=[s.pk, "cobro", c.pk])
    assert cliente.get(legado).url == url
    assert cliente.get(url).context["form"].fields["nuevo_id"].queryset.get() == sucesor
    assert cliente.post(
        url, datos_correccion(c, nuevo_id=sucesor.pk, archivo=pdf())
    ).status_code == 400
    importe = "105.00" if cambio == "corregir" else str(c.importe)
    respaldo = {"archivo": pdf()} if cambio == "adjuntar" else {"nuevo_id": sucesor.pk}
    respuesta = cliente.post(url, datos_correccion(c, importe=importe, **respaldo))
    assert respuesta.status_code == 302
    vigente = CobroExterno.objects.get(solicitud=s)
    if cambio == "corregir":
        assert vigente.reemplaza_id == c.pk and vigente.resultado == "PENDIENTE"
        assert vigente.documento.reemplaza_id == sucesor.pk
        assert not vigente.documento.revisiones.exists()
        assert CobroExterno.todos.get(pk=c.pk).resultado == "RECTIFICADO"
    else:
        assert vigente.pk == c.pk and vigente.resultado == "CONFIRMADO"
        documento = respaldo_actual(vigente)
        if cambio == "adjuntar":
            assert documento.reemplaza_id == sucesor.pk
            assert not documento.revisiones.exists()
        else:
            assert documento == sucesor


def test_duplicado_y_update_directo_no_dejan_cambios(escenario, datos):
    e = escenario
    s = presentar(e, datos)
    c = cobro(e, s, confirmar=False)
    otro = cobro(e, s, operacion="OTRA", confirmar=False)
    with pytest.raises(ValidationError):
        corregir(e, s, c, numero_operacion=otro.numero_operacion)
    c.refresh_from_db()
    assert not c.sustituido
    with pytest.raises(IntegrityError), transaction.atomic():
        CobroExterno.objects.filter(pk=c.pk).update(importe="1.00")
    # Una marca de sustitución sin su sucesor falla al confirmar la transacción.
    with pytest.raises(IntegrityError), transaction.atomic():
        CobroExterno.objects.filter(pk=c.pk).update(sustituido=True)
    assert CobroExterno.objects.count() == 2


def test_titular_reenvia_rechazado_cambiando_solo_el_archivo(escenario, datos):
    e = escenario
    s = presentar(e, datos)
    c = cobro(e, s, confirmar=False)
    verificar_cobro(
        actor=operador(e),
        numero=s.pk,
        cobro_id=c.pk,
        datos={"resultado": "RECHAZADO", "motivo": "El archivo no permite cotejar el ingreso"},
    )
    c.refresh_from_db()
    cliente = Client()
    cliente.force_login(e.usuarios["a"])
    url = reverse("facturacion:corregir_cobro", args=[s.pk, c.pk])
    assert cliente.post(url, datos_correccion(c, archivo=pdf())).status_code == 302
    vigente = CobroExterno.objects.get(solicitud=s)
    assert vigente.reemplaza_id == c.pk and vigente.resultado == "PENDIENTE"
    assert vigente.importe == c.importe


def test_dos_correcciones_concurrentes_un_sucesor(escenario, datos):
    e = escenario
    s = presentar(e, datos)
    c = cobro(e, s, confirmar=False)
    barrera = Barrier(2)

    def intentar():
        connections.close_all()
        try:
            barrera.wait()
            try:
                corregir(e, s, c, importe="100.25")
                return "ok"
            except ConflictoConcurrenciaError:
                return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: intentar(), range(2)))
    assert sorted(resultados) == ["conflicto", "ok"]
    assert CobroExterno.objects.count() == 1 and CobroExterno.todos.count() == 2


def test_fallo_al_crear_sucesor_revierte_marca_y_archivo(escenario, datos, monkeypatch):
    e = escenario
    s = presentar(e, datos)
    c = cobro(e, s)
    archivos = {p for p in e.raiz.rglob("*") if p.is_file()}
    original = CobroExterno.save

    def fallar_sucesor(self, *args, **kwargs):
        if self.reemplaza_id:
            raise RuntimeError("Fallo sintético al guardar sucesor")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(CobroExterno, "save", fallar_sucesor)
    with pytest.raises(RuntimeError):
        corregir(e, s, c, importe="10.00")
    c.refresh_from_db()
    assert not c.sustituido
    assert CobroExterno.todos.get(pk=c.pk).resultado == "CONFIRMADO"
    assert CobroExterno.todos.count() == 1
    assert {p for p in e.raiz.rglob("*") if p.is_file()} == archivos


def test_reversa_con_correcciones_se_rechaza_sin_perder_datos(escenario, datos):
    from django.db import DatabaseError, connection
    from django.db.migrations.executor import MigrationExecutor

    s = presentar(escenario, datos)
    c = cobro(escenario, s, confirmar=False)
    corregir(escenario, s, c)
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    try:
        with pytest.raises(DatabaseError, match="conservar historial"):
            executor.migrate([("facturacion", "0014_observaciones_opcionales")])
    finally:
        MigrationExecutor(connection).migrate(finales)
    assert CobroExterno.todos.count() == 2
    assert CobroExterno.objects.count() == 1


def test_migracion_conserva_cobro_anterior(escenario, datos):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    s = presentar(escenario, datos)
    c = cobro(escenario, s, confirmar=False)
    esperado = (c.pk, c.importe, c.documento_id, c.actor_id, c.numero_operacion)
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("facturacion", "0014_observaciones_opcionales")])
    finally:
        MigrationExecutor(connection).migrate(finales)
    c = CobroExterno.objects.get(pk=c.pk)
    assert (c.pk, c.importe, c.documento_id, c.actor_id, c.numero_operacion) == esperado
    assert not c.sustituido and c.reemplaza_id is None


def test_sql_no_verifica_version_sustituida(escenario, datos):
    from facturacion.models import VerificacionCobro

    s = presentar(escenario, datos)
    c = cobro(escenario, s, confirmar=False)
    nuevo = corregir(escenario, s, c)
    with pytest.raises(IntegrityError), transaction.atomic():
        VerificacionCobro.objects.create(
            cobro_id=c.pk,
            actor_id=escenario.actores["o"].subject_id,
            resultado="CONFIRMADO",
        )
    assert CobroExterno.objects.get(pk=nuevo.pk).resultado == "PENDIENTE"


def test_http_correccion_con_csrf_y_reenvio(escenario, datos):
    s = presentar(escenario, datos)
    c = cobro(escenario, s, confirmar=False)
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(escenario.usuarios["a"])
    url = reverse("facturacion:corregir_cobro", args=[s.pk, c.pk])
    pagina = cliente.get(url)
    assert pagina.status_code == 200
    assert c.fecha_operacion.isoformat() in pagina.content.decode()
    assert cliente.post(url, datos_correccion(c)).status_code == 403
    respuesta = cliente.post(
        url,
        datos_correccion(c, importe="90.00"),
        HTTP_X_CSRFTOKEN=cliente.cookies["csrftoken"].value,
    )
    assert respuesta.status_code == 302
    assert cliente.get(url).status_code == 404
    actual = CobroExterno.objects.get(solicitud=s)
    assert str(actual.importe) == "90.00" and actual.resultado == "PENDIENTE"
    assert CobroExterno.todos.count() == 2
