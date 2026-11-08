from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse

from comunes.models import TramiteBase
from documentos.models import Documento, RevisionDocumento
from documentos.revision import revisar
from documentos.services import incorporar
from facturacion import seguimiento
from facturacion.cobros import registrar_cobro, verificar_cobro
from facturacion.comprobantes import registrar_comprobante
from facturacion.models import (
    ActualizacionRespaldo,
    CobroExterno,
    ComprobanteExterno,
    RectificacionCobro,
)
from facturacion.seguimiento import (
    actualizar_respaldo,
    diagnostico,
    resolver_tramite,
    respaldo_actual,
)
from facturacion.workflow import (
    ConflictoConcurrenciaError,
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)

pytestmark = pytest.mark.django_db(transaction=True)


def pdf():
    return SimpleUploadedFile("sintetico.pdf", b"%PDF-1.7\nFicticio\n%%EOF", "application/pdf")


def operador(e):
    return replace(
        e.actores["o"],
        capabilities=e.actores["o"].capabilities
        | {
            "facturacion.cerrar",
            "facturacion.anular",
            "facturacion.actualizar_respaldo",
            "facturacion.verificar_cobro",
            "documentos.revisar",
        },
    )


@pytest.fixture
def solicitud(escenario, datos):
    return presentar_solicitud_facturacion(
        actor=escenario.actores["a"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )


def factura(e, s, **cambios):
    datos = dict(
        tipo="FACTURA",
        cuit_emisor="30712345671",
        letra="A",
        punto_venta="1",
        numero="1",
        fecha_emision="2026-10-22",
        importe="100.25",
    )
    return registrar_comprobante(
        actor=e.actores["o"], numero_publico=s.pk, datos=dict(datos, **cambios), archivo_pdf=pdf()
    )


def cobro(e, s, importe="100.25", operacion="CIERRE-FICTICIO", confirmar=True):
    c = registrar_cobro(
        actor=e.actores["a"],
        numero=s.pk,
        archivo=pdf(),
        datos=dict(
            medio="BNA_COMUN",
            numero_operacion=operacion,
            fecha_operacion="2026-10-22",
            importe=importe,
        ),
    )
    if confirmar:
        aceptar(e, c.documento)
        verificar_cobro(
            actor=operador(e), numero=s.pk, cobro_id=c.pk, datos={"resultado": "CONFIRMADO"}
        )
    return c


def aceptar(e, documento):
    return revisar(
        actor=operador(e),
        documento_id=documento.pk,
        resultado="ACEPTADO",
        motivo="",
        revision_esperada=documento.revisiones.order_by("-pk").values_list("pk", flat=True).first()
        or 0,
    )


def preparado(e, s):
    f, c = factura(e, s), cobro(e, s)
    aceptar(e, f.documento)
    return f, c


def resolver(e, s, accion="cerrar", **cambios):
    s.refresh_from_db()
    return resolver_tramite(
        actor=operador(e),
        numero=s.pk,
        accion=accion,
        **dict(
            dict(motivo="Resolución sintética", revision_esperada=diagnostico(s)["revision"]),
            **cambios,
        ),
    )


def test_cierre_completo_historial_y_terminal_solo_consulta(escenario, solicitud):
    f, c = preparado(escenario, solicitud)
    assert solicitud.estado_seguimiento == "Cobrada en revisión"
    assert diagnostico(solicitud)["faltas_cierre"] == []
    resolver(escenario, solicitud)
    solicitud.refresh_from_db()
    assert solicitud.estado == "CERRADA" and solicitud.version_concurrencia == 2
    evento = solicitud.eventos.last()
    assert evento.tipo_evento == "CIERRE" and evento.actor_id == escenario.usuarios["o"].pk
    assert evento.snapshot_datos["antes"]["estado"] == "PRESENTADA"
    with pytest.raises(ConflictoConcurrenciaError):
        resolver(escenario, solicitud)
    with pytest.raises(PermissionDenied):
        factura(escenario, solicitud, tipo="NOTA_CREDITO", numero="2", importe="1.00")
    with pytest.raises(PermissionDenied):
        cobro(escenario, solicitud, operacion="OTRA")
    with pytest.raises(PermissionDenied):
        aceptar(escenario, c.documento)
    with pytest.raises(PermissionDenied):
        incorporar(
            actor=operador(escenario),
            referencia=f"facturacion:{solicitud.pk}",
            archivo=pdf(),
            tipo="COMPROBANTE_COBRO",
            procedencia="EXTERNO_BANCO",
        )
    with pytest.raises(PermissionDenied):
        observar_solicitud_facturacion(
            actor=operador(escenario),
            numero_publico=solicitud.pk,
            motivo="Otra",
            version_esperada=2,
        )
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    contenido = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk])).content.decode()
    assert "Cerrada" in contenido and "CIERRE" in contenido
    assert 'id="titulo-acciones"' not in contenido
    assert 'id="titulo-motivo-anulacion"' not in contenido
    assert "Informar cobro o anticipo" not in contenido
    assert "Registrar factura o nota externa" not in contenido
    respuesta = cliente.get(reverse("documentos:archivo", args=[f.documento_id]))
    assert respuesta.status_code == 200
    respuesta.close()
    assert ComprobanteExterno.objects.count() == CobroExterno.objects.count() == 1


@pytest.mark.parametrize(
    "caso", ["sin_factura", "faltante", "pendiente", "pdf", "observada"]
)
def test_cierre_con_pendientes_no_modifica_hechos(escenario, solicitud, caso):
    if caso != "sin_factura":
        f = factura(escenario, solicitud)
        if caso != "pdf":
            aceptar(escenario, f.documento)
    importe = "99.25" if caso == "faltante" else "100.25"
    c = cobro(escenario, solicitud, importe=importe, confirmar=caso != "pendiente")
    if caso == "pendiente":
        aceptar(escenario, c.documento)
    if caso == "observada":
        observar_solicitud_facturacion(
            actor=operador(escenario),
            numero_publico=solicitud.pk,
            motivo="Falta aclarar",
            version_esperada=1,
        )
    solicitud.refresh_from_db()
    antes = (solicitud.estado, solicitud.version_concurrencia, solicitud.eventos.count())
    assert diagnostico(solicitud)["faltas_cierre"]
    with pytest.raises(ValidationError):
        resolver(escenario, solicitud)
    solicitud.refresh_from_db()
    assert (solicitud.estado, solicitud.version_concurrencia, solicitud.eventos.count()) == antes


@pytest.mark.parametrize("neto", [None, "positivo", "cero", "negativo"])
def test_anulacion_sin_ingresos_con_cualquier_neto(escenario, solicitud, neto):
    if neto:
        f = factura(escenario, solicitud)
        aceptar(escenario, f.documento)
        if neto != "positivo":
            n = factura(
                escenario, solicitud, tipo="NOTA_CREDITO", numero="2",
                importe="101.25" if neto == "negativo" else "100.25",
            )
            aceptar(escenario, n.documento)
    resolver(escenario, solicitud, "anular")
    solicitud.refresh_from_db()
    assert solicitud.estado == "ANULADA"
    assert solicitud.eventos.last().tipo_evento == "ANULACION"


@pytest.mark.parametrize(
    "caso", ["pendiente", "pdf"]
)
def test_anulacion_bloqueada_por_ingreso_pendiente_o_respaldo(escenario, solicitud, caso):
    f = factura(escenario, solicitud)
    n = factura(
        escenario,
        solicitud,
        tipo="NOTA_CREDITO",
        numero="2",
    )
    if caso != "pdf":
        aceptar(escenario, f.documento)
        aceptar(escenario, n.documento)
    if caso == "pendiente":
        cobro(escenario, solicitud, confirmar=False)
    with pytest.raises(ValidationError):
        resolver(escenario, solicitud, "anular")
    solicitud.refresh_from_db()
    assert solicitud.estado == "PRESENTADA" and solicitud.eventos.count() == 1


@pytest.mark.parametrize("clase", ["comprobante", "cobro"])
def test_reemplazo_y_actualizacion_conservan_operacion_y_exigen_nueva_revision(
    escenario, solicitud, clase
):
    f, c = preparado(escenario, solicitud)
    objeto = f if clase == "comprobante" else c
    anterior = objeto.documento
    actualizar_respaldo(
        actor=operador(escenario),
        numero=solicitud.pk,
        clase=clase,
        objeto_id=objeto.pk,
        archivo=pdf(),
        motivo="Respaldo legible",
        revision_esperada=diagnostico(solicitud)["revision"],
    )
    objeto.refresh_from_db()
    assert objeto.documento_id == anterior.pk and objeto.importe == Decimal("100.25")
    nueva = respaldo_actual(objeto)
    assert nueva.reemplaza_id == anterior.pk and nueva.version == 2
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    revision = cliente.get(reverse("documentos:revision", args=[nueva.pk]))
    assert revision.status_code == 200
    assert [cobro for cobro, _ in revision.context["cobros_revision"]] == (
        [c] if clase == "cobro" else []
    )
    assert diagnostico(solicitud)["faltas_cierre"]
    assert ActualizacionRespaldo.objects.get().anterior_id == anterior.pk
    with pytest.raises(ValidationError):
        resolver(escenario, solicitud)
    aceptar(escenario, nueva)
    resolver(escenario, solicitud)
    assert solicitud.cobros.get().resultado == "CONFIRMADO"
    with pytest.raises(IntegrityError), transaction.atomic():
        ActualizacionRespaldo.objects.all().update(motivo="Alterar")


def test_frescura_se_invalida_por_nota_o_revision_sin_cambiar_estado(escenario, solicitud):
    f, c = preparado(escenario, solicitud)
    revision = diagnostico(solicitud)["revision"]
    revisar(
        actor=operador(escenario),
        documento_id=c.documento_id,
        resultado="OBSERVADO",
        motivo="Revisar",
        revision_esperada=c.documento.revisiones.last().pk,
    )
    with pytest.raises(ConflictoConcurrenciaError):
        resolver(escenario, solicitud, revision_esperada=revision)
    assert solicitud.estado == "PRESENTADA"


def test_fallo_evento_revierte_resolucion_y_sql_no_elude_reglas(escenario, solicitud, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("Fallo sintético")

    monkeypatch.setattr(seguimiento, "_evento", falla)
    with pytest.raises(RuntimeError):
        resolver(escenario, solicitud, "anular")
    solicitud.refresh_from_db()
    assert solicitud.estado == "PRESENTADA" and solicitud.eventos.count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        type(solicitud).objects.filter(pk=solicitud.pk).update(estado="CERRADA")
    with pytest.raises(IntegrityError), transaction.atomic():
        type(solicitud).objects.filter(pk=solicitud.pk).update(estado="ANULADA")  # Sin evento.


def test_http_permisos_csrf_y_cierre_sin_motivo(escenario, solicitud):
    preparado(escenario, solicitud)
    url = reverse("facturacion:resolver", args=[solicitud.pk])
    c = Client(enforce_csrf_checks=True)
    c.force_login(escenario.usuarios["o"])
    c.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    token = c.cookies["csrftoken"].value
    datos = dict(accion="cerrar", revision=diagnostico(solicitud)["revision"])
    assert c.post(url, datos).status_code == 403
    datos["csrfmiddlewaretoken"] = token
    assert c.post(url, datos).status_code == 403  # Capacidad independiente.
    escenario.usuarios["o"].groups.add(Group.objects.get(name="demo_resolucion_facturacion"))
    r = c.post(url, dict(datos, revision="obsoleta"))
    assert r.status_code == 409 and '<textarea' not in r.content.decode()
    assert c.post(url, datos).status_code == 302
    assert solicitud.eventos.get(tipo_evento="CIERRE").motivo_o_detalle == ""
    assert c.post(url, datos).status_code == 409
    b = Client()
    b.force_login(escenario.usuarios["b"])
    assert b.get(reverse("facturacion:detalle", args=[solicitud.pk])).status_code == 404


def test_http_anulacion_exige_y_conserva_motivo(escenario, solicitud):
    _, ingreso = preparado(escenario, solicitud)
    revisar(
        actor=operador(escenario),
        documento_id=ingreso.documento_id,
        resultado="RECHAZADO",
        motivo="El respaldo requiere corrección",
        revision_esperada=ingreso.documento.revisiones.get().pk,
    )
    estado = diagnostico(solicitud)
    assert estado["confirmado"] == ingreso.importe
    assert estado["faltas_cierre"] and not estado["faltas_anulacion"]
    escenario.usuarios["o"].groups.add(Group.objects.get(name="demo_resolucion_facturacion"))
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    url = reverse("facturacion:resolver", args=[solicitud.pk])
    datos = dict(accion="anular", revision=diagnostico(solicitud)["revision"])
    assert cliente.post(url, datos).status_code == 400
    assert cliente.post(url, dict(datos, motivo="\t\n")).status_code == 400
    motivo = "Motivo sintético de anulación"
    respuesta = cliente.post(url, dict(datos, motivo=motivo, revision="obsoleta"))
    assert respuesta.status_code == 409 and motivo in respuesta.content.decode()
    assert cliente.post(url, dict(datos, motivo=motivo)).status_code == 302
    assert solicitud.eventos.get(tipo_evento="ANULACION").motivo_o_detalle == motivo
    assert solicitud.cobros.get().resultado == "CONFIRMADO"
    assert ingreso.documento.revisiones.latest("pk").resultado == "RECHAZADO"
    detalle = reverse("facturacion:detalle", args=[solicitud.pk])
    for rol in ("o", "a"):
        cliente.force_login(escenario.usuarios[rol])
        respuesta = cliente.get(detalle)
        assert respuesta.status_code == 200
        html = respuesta.content.decode()
        assert 'id="titulo-acciones"' not in html
        assert html.index('id="titulo-motivo-anulacion"') < html.index(motivo)
        assert html.index(motivo) < html.index('id="titulo-estado-cobro"')


def test_rectificar_confirma_trazabilidad_y_recalcula_cierre(escenario, solicitud):
    _, ingreso = preparado(escenario, solicitud)
    revision = diagnostico(solicitud)["revision"]
    url = reverse("facturacion:rectificar_cobro", args=[solicitud.pk, ingreso.pk])
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    assert cliente.post(url, {"motivo": "Error al cotejar"}).status_code == 403
    escenario.usuarios["o"].groups.add(
        Group.objects.get(name="demo_verificacion_cobros"),
        Group.objects.get(name="demo_resolucion_facturacion"),
    )
    cliente.force_login(escenario.usuarios["o"])
    assert cliente.get(url).status_code == 200
    assert cliente.post(url, {"motivo": "\t\n"}).status_code == 400
    assert cliente.post(url, {"motivo": "Error al cotejar"}).status_code == 302
    assert cliente.post(url, {"motivo": "Reenvío"}).status_code == 409
    ingreso.refresh_from_db()
    assert ingreso.verificacion.resultado == "CONFIRMADO" and ingreso.resultado == "RECTIFICADO"
    rectificacion = ingreso.verificacion.rectificacion
    assert rectificacion.motivo == "Error al cotejar"
    assert rectificacion.actor_id == escenario.usuarios["o"].pk
    assert diagnostico(solicitud)["confirmado"] == 0
    assert diagnostico(solicitud)["restante"] == ingreso.importe
    lista = reverse("facturacion:lista")
    assert not list(cliente.get(lista, {"estado": "COBRADA_EN_REVISION"}).context["pagina"])
    cierre = reverse("facturacion:resolver", args=[solicitud.pk])
    assert cliente.post(cierre, {"accion": "cerrar", "revision": revision}).status_code == 409
    with pytest.raises(IntegrityError, match="Resolucion con pendientes"), transaction.atomic():
        type(solicitud).objects.filter(pk=solicitud.pk).update(
            estado="CERRADA", version_concurrencia=2
        )
    with pytest.raises(IntegrityError, match="Rectificacion inmutable"), transaction.atomic():
        RectificacionCobro.objects.filter(pk=rectificacion.pk).update(motivo="Modificar")
    html = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk])).content.decode()
    assert "Ingreso rectificado" in html and "Ingreso verificado" in html
    assert 'href="#cobros-externos">El total confirmado debe cubrir' in html
    assert 'id="cobros-externos"' in html


@pytest.mark.parametrize("estado", ["CERRADA", "ANULADA"])
def test_sql_exige_evento_terminal_y_motivo_de_anulacion(escenario, solicitud, estado):
    if estado == "CERRADA":
        preparado(escenario, solicitud)
    with pytest.raises(IntegrityError, match="Falta evento de resolucion"), transaction.atomic():
        type(solicitud).objects.filter(pk=solicitud.pk).update(
            estado=estado, version_concurrencia=2
        )
        if estado == "ANULADA":
            solicitud.eventos.create(
                actor_id=escenario.usuarios["o"].pk,
                tipo_evento="ANULACION",
                estado_resultante=estado,
                motivo_o_detalle="\t\n\u00a0",
                snapshot_datos={"version_resultante": 2},
            )


def test_dos_cierres_concurrentes_un_solo_evento(escenario, solicitud):
    preparado(escenario, solicitud)
    revision = diagnostico(solicitud)["revision"]

    def worker(_):
        try:
            resolver_tramite(
                actor=operador(escenario),
                numero=solicitud.pk,
                accion="cerrar",
                motivo="Resolución",
                revision_esperada=revision,
            )
            return "ok"
        except ConflictoConcurrenciaError:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, [1, 2])) == ["conflicto", "ok"]
    assert solicitud.eventos.filter(tipo_evento="CIERRE").count() == 1


def test_reversa_terminal_bloqueada_y_sql_terminal_inmutable(escenario, solicitud):
    f, _ = preparado(escenario, solicitud)
    resolver(escenario, solicitud)
    finales = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        with pytest.raises(DatabaseError, match="Hay resoluciones"):
            MigrationExecutor(connection).migrate(
                [("facturacion", "0010_actualizacionrespaldo_and_more")]
            )
    finally:
        MigrationExecutor(connection).migrate(finales)
    with pytest.raises(IntegrityError), transaction.atomic():
        type(solicitud).objects.filter(pk=solicitud.pk).update(estado="PRESENTADA")
    with pytest.raises(IntegrityError), transaction.atomic():
        RevisionDocumento.objects.create(
            documento=f.documento,
            resultado="OBSERVADO",
            motivo="Tardía",
            actor=escenario.usuarios["o"],
        )


@pytest.mark.parametrize("operacion", ["nota", "cobro", "revision"])
def test_resolucion_serializada_con_operaciones_documentales_y_financieras(
    escenario, solicitud, operacion
):
    _, c = preparado(escenario, solicitud)
    revision = diagnostico(solicitud)["revision"]
    barrera = Barrier(2)

    def cierre():
        try:
            barrera.wait(timeout=10)
            resolver_tramite(
                actor=operador(escenario),
                numero=solicitud.pk,
                accion="cerrar",
                motivo="Resolución concurrente",
                revision_esperada=revision,
            )
            return "cerrado"
        except ConflictoConcurrenciaError:
            return "obsoleto"
        finally:
            connections.close_all()

    def mutacion():
        try:
            barrera.wait(timeout=10)
            if operacion == "nota":
                factura(escenario, solicitud, tipo="NOTA_CREDITO", numero="2", importe="1.00")
            elif operacion == "cobro":
                cobro(
                    escenario, solicitud, importe="1.00", operacion="CONCURRENTE", confirmar=False
                )
            else:
                revisar(
                    actor=operador(escenario),
                    documento_id=c.documento_id,
                    resultado="OBSERVADO",
                    motivo="Revisión concurrente",
                    revision_esperada=c.documento.revisiones.last().pk,
                )
            return "mutado"
        except PermissionDenied:
            return "bloqueado"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(cierre), pool.submit(mutacion)
        resultado = (a.result(timeout=15), b.result(timeout=15))
    assert resultado in {("cerrado", "bloqueado"), ("obsoleto", "mutado")}
    solicitud.refresh_from_db()
    assert solicitud.eventos.filter(tipo_evento="CIERRE").count() == (solicitud.estado == "CERRADA")


def test_http_actualizacion_upload_atomico_y_motivo_conservado(escenario, solicitud):
    f, _ = preparado(escenario, solicitud)
    escenario.usuarios["o"].groups.add(Group.objects.get(name="demo_resolucion_facturacion"))
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(escenario.usuarios["o"])
    url = reverse("facturacion:actualizar_respaldo", args=[solicitud.pk, "comprobante", f.pk])
    assert cliente.get(url).status_code == 200
    contenido = dict(
        revision=diagnostico(solicitud)["revision"],
        motivo="\t\n",
        csrfmiddlewaretoken=cliente.cookies["csrftoken"].value,
    )
    respuesta = cliente.post(url, dict(contenido, archivo=pdf()))
    assert respuesta.status_code == 400 and not ActualizacionRespaldo.objects.exists()
    assert not Documento.objects.filter(reemplaza=f.documento).exists()
    archivo_invalido = SimpleUploadedFile("respaldo.txt", b"Texto", "text/plain")
    respuesta = cliente.post(url, dict(contenido, motivo="PDF legible", archivo=archivo_invalido))
    assert respuesta.status_code == 400
    assert respuesta.context["error_archivo"] == (
        "Tipo de archivo no soportado. Adjuntá un archivo en formato PDF (.pdf)."
    )
    assert not respuesta.context.get("errores")
    respuesta = cliente.post(url, dict(contenido, motivo="PDF legible", archivo=pdf()))
    assert respuesta.status_code == 302
    assert respaldo_actual(f).version == 2 and f.documento.version == 1
    detalle = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    assert "Vínculo documental actualizado" in detalle.content.decode()


def test_seleccion_sucesora_ajena_rechazada_y_sql_motivo(escenario, solicitud, datos):
    f, c = preparado(escenario, solicitud)
    with pytest.raises(ValidationError):
        actualizar_respaldo(
            actor=operador(escenario),
            numero=solicitud.pk,
            clase="comprobante",
            objeto_id=f.pk,
            nuevo_id=c.documento_id,
            motivo="No corresponde",
            revision_esperada=diagnostico(solicitud)["revision"],
        )
    nueva = incorporar(
        actor=operador(escenario),
        referencia=f"facturacion:{solicitud.pk}",
        tipo=f.documento.tipo,
        procedencia="EXTERNO_XUBIO",
        archivo=pdf(),
        reemplaza_id=f.documento_id,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ActualizacionRespaldo.objects.create(
            comprobante=f,
            anterior=f.documento,
            nuevo=nueva,
            actor=escenario.usuarios["o"],
            motivo="\t\n\u00a0",
        )
    actualizar_respaldo(
        actor=operador(escenario),
        numero=solicitud.pk,
        clase="comprobante",
        objeto_id=f.pk,
        nuevo_id=nueva.pk,
        motivo="Versión sustituta",
        revision_esperada=diagnostico(solicitud)["revision"],
    )
    assert respaldo_actual(f).pk == nueva.pk
    assert diagnostico(solicitud)["faltas_cierre"]


def test_upgrade_reversa_vacia_preservan_tramite_y_archivo(escenario, solicitud):
    f = factura(escenario, solicitud)
    contenido = (escenario.raiz / f.documento.archivo).read_bytes()
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("facturacion", "0009_integridad_cobros")])
        MigrationExecutor(connection).migrate(finales)
        solicitud.refresh_from_db()
        assert solicitud.estado == "PRESENTADA" and solicitud.eventos.count() == 1
        assert (escenario.raiz / f.documento.archivo).read_bytes() == contenido
    finally:
        MigrationExecutor(connection).migrate(finales)


@pytest.mark.parametrize("segundo_importe", ["40.15", "41.15"])
def test_dos_parciales_aceptados_cubren_o_superan_neto(escenario, solicitud, segundo_importe):
    f = factura(escenario, solicitud)
    cobro(escenario, solicitud, importe="60.10", operacion="PARCIAL-1")
    c2 = cobro(
        escenario, solicitud, importe=segundo_importe, operacion="PARCIAL-2", confirmar=False
    )
    escenario.usuarios["o"].groups.add(Group.objects.get(name="demo_verificacion_cobros"))
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    lista_url = reverse("facturacion:lista")
    inicio_resumen = f'<template id="resumen-solicitud-{solicitud.pk}"'
    html = cliente.get(lista_url).content.decode()
    resumen = html.split(inicio_resumen, 1)[1].split("</template>", 1)[0]
    assert "Facturada pendiente de cobro" in resumen
    assert ("· Excedente" in resumen) == (segundo_importe == "41.15")
    assert ('class="fac-covered"' in resumen) == (segundo_importe == "40.15")
    url = reverse("facturacion:verificar_cobro", args=[solicitud.pk, c2.pk])
    respuesta = cliente.get(url)
    assert respuesta.status_code == 200
    assert ("el total confirmado superará el neto" in respuesta.content.decode()) == (
        segundo_importe == "41.15"
    )
    aceptar(escenario, c2.documento)
    assert cliente.post(url, {"resultado": "CONFIRMADO"}).status_code == 302
    html = cliente.get(lista_url).content.decode()
    fila = html.split(f'<tr data-resumen="{solicitud.pk}">', 1)[1].split("</tr>", 1)[0]
    resumen = html.split(inicio_resumen, 1)[1].split("</template>", 1)[0]
    detalle = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk])).content.decode()
    estado_detalle = detalle.split('class="fac-statuses"', 1)[1].split("</div>", 1)[0]
    for vista in (fila, resumen, estado_detalle):
        assert "Cobrada en revisión" in vista
        assert ">Presentada<" not in vista
    aceptar(escenario, f.documento)
    assert diagnostico(solicitud)["confirmado"] == Decimal("60.10") + Decimal(segundo_importe)
    escenario.usuarios["o"].groups.add(Group.objects.get(name="demo_resolucion_facturacion"))
    detalle_url = reverse("facturacion:detalle", args=[solicitud.pk])
    detalle_para_cerrar = cliente.get(detalle_url)
    assert "Sin pendientes para el cierre normal" in detalle_para_cerrar.content.decode()
    respuesta = cliente.post(
        reverse("facturacion:resolver", args=[solicitud.pk]),
        {"accion": "cerrar", "revision": detalle_para_cerrar.context["diagnostico"]["revision"]},
    )
    assert respuesta.status_code == 302 and respuesta.url == detalle_url
    solicitud.refresh_from_db()
    assert solicitud.estado == "CERRADA"
    assert solicitud.eventos.get(tipo_evento="CIERRE").motivo_o_detalle == ""


def test_declaracion_inicial_no_se_ignora_al_anular(escenario, datos):
    solicitud = presentar_solicitud_facturacion(
        actor=escenario.actores["a"],
        datos=dict(
            datos,
            presento_comprobante_pago=True,
            modalidad_cobro="BNA_COMUN",
            fecha_operacion_declarada="2026-10-22",
            numero_operacion_declarado="DECLARADA",
        ),
        archivo_comprobante=pdf(),
        token_presentacion=emitir_token(escenario.actores["a"]),
    )
    with pytest.raises(ValidationError, match="declarada"):
        resolver(escenario, solicitud, "anular")
    c = registrar_cobro(
        actor=operador(escenario),
        numero=solicitud.pk,
        datos=dict(
            medio="BNA_COMUN",
            numero_operacion="DECLARADA",
            fecha_operacion="2026-10-22",
            importe="1.00",
            documento=str(solicitud.documento_comprobante_inicial_id),
        ),
    )
    verificar_cobro(
        actor=operador(escenario),
        numero=solicitud.pk,
        cobro_id=c.pk,
        datos={"resultado": "RECHAZADO", "motivo": "No ingresó la transferencia declarada"},
    )
    resolver(escenario, solicitud, "anular")
    solicitud.refresh_from_db()
    assert solicitud.estado == "ANULADA"


def test_correccion_con_archivo_continua_serie_reemplazada_por_operador(escenario, datos):
    from facturacion.workflow import corregir_solicitud_facturacion

    solicitud = presentar_solicitud_facturacion(
        actor=escenario.actores["a"],
        datos=dict(
            datos,
            presento_comprobante_pago=True,
            modalidad_cobro="BNA_COMUN",
            fecha_operacion_declarada="2026-10-22",
            numero_operacion_declarado="INICIAL",
        ),
        archivo_comprobante=pdf(),
        token_presentacion=emitir_token(escenario.actores["a"]),
    )
    c = registrar_cobro(
        actor=operador(escenario),
        numero=solicitud.pk,
        datos=dict(
            medio="BNA_COMUN",
            numero_operacion="INICIAL",
            fecha_operacion="2026-10-22",
            importe="1.00",
            documento=str(solicitud.documento_comprobante_inicial_id),
        ),
    )
    anterior = solicitud.documento_comprobante_inicial
    actualizar_respaldo(
        actor=operador(escenario),
        numero=solicitud.pk,
        clase="cobro",
        objeto_id=c.pk,
        archivo=pdf(),
        motivo="Documento actualizado",
        revision_esperada=diagnostico(solicitud)["revision"],
    )
    observar_solicitud_facturacion(
        actor=operador(escenario),
        numero_publico=solicitud.pk,
        motivo="Corregir datos",
        version_esperada=1,
    )
    corregida = corregir_solicitud_facturacion(
        actor=escenario.actores["a"],
        numero_publico=solicitud.pk,
        datos=dict(
            datos,
            presento_comprobante_pago=True,
            modalidad_cobro="BNA_COMUN",
            fecha_operacion_declarada="2026-10-22",
            numero_operacion_declarado="INICIAL",
        ),
        version_esperada=2,
        archivo_comprobante=pdf(),
    )
    assert corregida.documento_comprobante_inicial.version == 3
    assert corregida.documento_comprobante_inicial.serie == anterior.serie
    assert c.documento_id == anterior.pk and respaldo_actual(c).version == 2


def test_diagnostico_y_actualizacion_no_filtran_metadatos_al_lector(escenario, solicitud):
    f, _ = preparado(escenario, solicitud)
    a = actualizar_respaldo(
        actor=operador(escenario),
        numero=solicitud.pk,
        clase="comprobante",
        objeto_id=f.pk,
        archivo=pdf(),
        motivo="Motivo documental reservado",
        revision_esperada=diagnostico(solicitud)["revision"],
    )
    lector = Client()
    lector.force_login(escenario.usuarios["l"])
    respuesta = lector.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    contenido = respuesta.content.decode()
    assert "Condiciones documentales no disponibles" in contenido
    assert f"Documento de respaldo #{a.nuevo_id}" not in contenido
    assert "Motivo documental reservado" not in contenido
    actor_sin_meta = replace(
        operador(escenario),
        capabilities=operador(escenario).capabilities
        - {"documentos.consultar_metadatos", "documentos.ver_metadatos"},
    )
    with pytest.raises(PermissionDenied):
        resolver_tramite(
            actor=actor_sin_meta,
            numero=solicitud.pk,
            accion="cerrar",
            motivo="Resolver",
            revision_esperada=diagnostico(solicitud)["revision"],
        )


def insertar_terminal_sql(solicitud, estado):
    """Copia datos operativos válidos; sólo cambia identidad reservada, clave y estado."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence('facturacion_solicitudfacturacion','id'))"
        )
        numero = cursor.fetchone()[0]
        base = TramiteBase.objects.create(
            circuito="FACTURACION",
            numero_publico=numero,
            solicitante_actor_id=solicitud.tramite_base.solicitante_actor_id,
        )
        valores = {
            "id": numero,
            "tramite_base_id": base.pk,
            "estado": estado,
            "clave_idempotencia": uuid4(),
        }
        columnas = [f.column for f in type(solicitud)._meta.concrete_fields]
        seleccion = ["%s" if c in valores else connection.ops.quote_name(c) for c in columnas]
        cursor.execute(
            "INSERT INTO facturacion_solicitudfacturacion ("
            + ",".join(connection.ops.quote_name(c) for c in columnas)
            + ") SELECT "
            + ",".join(seleccion)
            + " FROM facturacion_solicitudfacturacion WHERE id=%s",
            [*(valores[c] for c in columnas if c in valores), solicitud.pk],
        )


@pytest.mark.parametrize("estado", ["CERRADA", "ANULADA"])
def test_sql_rechaza_alta_terminal_sin_resolucion(escenario, solicitud, estado):
    cantidad = type(solicitud).objects.count()
    cabeceras = TramiteBase.objects.count()
    with pytest.raises(IntegrityError), transaction.atomic():
        insertar_terminal_sql(solicitud, estado)
    assert type(solicitud).objects.count() == cantidad
    assert TramiteBase.objects.count() == cabeceras
    assert solicitud.eventos.count() == 1


@pytest.mark.parametrize("accion", ["cerrar", "anular"])
def test_centro_costo_terminal_protegido_por_orm_y_sql(escenario, solicitud, accion):
    base_id = solicitud.tramite_base_id
    assert TramiteBase.objects.filter(pk=base_id).update(centro_costo_codigo="PREVIO") == 1
    if accion == "cerrar":
        preparado(escenario, solicitud)
    resolver(escenario, solicitud, accion)
    with pytest.raises(IntegrityError), transaction.atomic():
        TramiteBase.objects.filter(pk=base_id).update(centro_costo_codigo="POSTERIOR")
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE comunes_tramitebase SET centro_costo_codigo=NULL WHERE id=%s", [base_id]
        )
    assert TramiteBase.objects.get(pk=base_id).centro_costo_codigo == "PREVIO"
    assert solicitud.eventos.filter(tipo_evento__in=["CIERRE", "ANULACION"]).count() == 1


def test_guarda_terminal_no_bloquea_centro_costo_de_gastos(escenario):
    base = TramiteBase.objects.create(
        circuito="GASTO",
        numero_publico=1000000,
        solicitante_actor_id=str(escenario.usuarios["a"].pk),
    )
    assert TramiteBase.objects.filter(pk=base.pk).update(centro_costo_codigo="GASTOS") == 1
    assert TramiteBase.objects.get(pk=base.pk).centro_costo_codigo == "GASTOS"


def test_upgrade_guardas_preserva_resolucion_existente(escenario, solicitud):
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("facturacion", "0011_resolucion_integridad")])
        # Construir el hecho con los modelos historicos: el servicio actual usa campos nuevos.
        anteriores = (
            MigrationExecutor(connection)
            .loader.project_state([("facturacion", "0011_resolucion_integridad")])
            .apps
        )
        SolicitudAnterior = anteriores.get_model("facturacion", "SolicitudFacturacion")
        EventoAnterior = anteriores.get_model("facturacion", "EventoFacturacion")
        with transaction.atomic():
            SolicitudAnterior.objects.filter(pk=solicitud.pk).update(
                estado="ANULADA", version_concurrencia=2
            )
            evento = EventoAnterior.objects.create(
                solicitud_id=solicitud.pk,
                actor_id=escenario.usuarios["o"].pk,
                tipo_evento="ANULACION",
                estado_resultante="ANULADA",
                motivo_o_detalle="Resolucion previa sintetica",
                snapshot_datos={"version_resultante": 2},
            )
        MigrationExecutor(connection).migrate(finales)
        solicitud.refresh_from_db()
        assert solicitud.estado == "ANULADA"
        assert solicitud.eventos.get(tipo_evento="ANULACION").pk == evento.pk
        with pytest.raises(IntegrityError), transaction.atomic():
            insertar_terminal_sql(solicitud, "ANULADA")
        with pytest.raises(IntegrityError), transaction.atomic():
            TramiteBase.objects.filter(pk=solicitud.tramite_base_id).update(
                centro_costo_codigo="POSTERIOR"
            )
    finally:
        MigrationExecutor(connection).migrate(finales)
