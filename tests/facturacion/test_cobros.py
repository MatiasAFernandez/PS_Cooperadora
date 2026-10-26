from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from threading import Barrier

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse

from documentos.models import Documento, RevisionDocumento
from facturacion import cobros
from facturacion.cobros import registrar_cobro, resumen_cobros, verificar_cobro
from facturacion.models import CobroExterno, VerificacionCobro
from facturacion.permissions import ObjetoNoVisibleError
from facturacion.workflow import (
    ConflictoConcurrenciaError,
    emitir_token,
    presentar_solicitud_facturacion,
)


def pdf():
    return SimpleUploadedFile("cobro.pdf", b"%PDF-1.7\nFicticio\n%%EOF", "application/pdf")


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def solicitud(escenario, datos):
    return presentar_solicitud_facturacion(
        actor=escenario.actores["a"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )


@pytest.fixture
def entrada():
    return dict(
        medio="BNA_COMUN",
        numero_operacion="OPERACION-FICTICIA-001",
        fecha_operacion="2026-10-22",
        importe="60.10",
    )


def alta(e, solicitud, entrada, **cambios):
    return registrar_cobro(
        actor=e.actores["a"], numero=solicitud.pk, datos=dict(entrada, **cambios), archivo=pdf()
    )


def revisor(e):
    return replace(
        e.actores["o"], capabilities=e.actores["o"].capabilities | {"facturacion.verificar_cobro"}
    )


def operador_alta_confirmada(e):
    return replace(
        revisor(e), capabilities=revisor(e).capabilities | {"documentos.revisar"}
    )


def test_alta_confirmada_atomica_y_respaldo_sin_pendiente(escenario, solicitud, entrada):
    from facturacion.seguimiento import diagnostico

    actor = operador_alta_confirmada(escenario)
    cobro = registrar_cobro(
        actor=actor, numero=solicitud.pk,
        datos=dict(entrada, confirmar_al_registrar=True), archivo=pdf(),
    )
    assert cobro.procedencia == "INTERNO_COOPERADORA"
    assert cobro.resultado == "CONFIRMADO"
    revision = cobro.documento.revisiones.get()
    assert revision.resultado == "ACEPTADO"
    assert revision.actor_id == cobro.verificacion.actor_id == actor.subject_id
    assert "mismo actor" in revision.motivo
    assert not diagnostico(solicitud)["faltas_documentales"]
    assert resumen_cobros(solicitud)[1]["CONFIRMADO"] == Decimal("60.10")
    with pytest.raises(ConflictoConcurrenciaError):
        registrar_cobro(
            actor=actor, numero=solicitud.pk,
            datos=dict(entrada, confirmar_al_registrar=True), archivo=pdf(),
        )
    assert CobroExterno.objects.count() == VerificacionCobro.objects.count() == 1
    assert RevisionDocumento.objects.count() == 1


@pytest.mark.parametrize("capacidad", [
    "facturacion.registrar_cobro", "facturacion.verificar_cobro",
    "documentos.revisar", "documentos.consultar_metadatos",
])
def test_alta_confirmada_exige_capacidades(escenario, solicitud, entrada, capacidad):
    actor = operador_alta_confirmada(escenario)
    actor = replace(actor, capabilities=actor.capabilities - {capacidad})
    with pytest.raises(PermissionDenied):
        registrar_cobro(
            actor=actor, numero=solicitud.pk,
            datos=dict(entrada, confirmar_al_registrar="on"), archivo=pdf(),
        )
    assert not CobroExterno.objects.exists()
    assert not Documento.objects.exists()


def test_alta_confirmada_http_y_solicitante_no_puede_confirmar(escenario, solicitud, entrada):
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    url = reverse("facturacion:registrar_cobro", args=[solicitud.pk])
    assert "confirmar_al_registrar" not in cliente.get(url).context["form"].fields
    respuesta = cliente.post(url, dict(entrada, confirmar_al_registrar="on", archivo=pdf()))
    assert respuesta.status_code == 403
    escenario.usuarios["o"].groups.add(
        Group.objects.get(name="demo_verificacion_cobros"),
        Group.objects.get(name="demo_documentos_revision"),
    )
    cliente.force_login(escenario.usuarios["o"])
    formulario = cliente.get(url).context["form"]
    assert not formulario["confirmar_al_registrar"].value()
    respuesta = cliente.post(url, dict(entrada, confirmar_al_registrar="on", archivo=pdf()))
    assert respuesta.status_code == 302
    assert CobroExterno.objects.get().resultado == "CONFIRMADO"
    respuesta = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    assert not respuesta.context["pendientes_revision"]


def test_alta_confirmada_error_conserva_casilla_y_datos(escenario, solicitud, entrada):
    escenario.usuarios["o"].groups.add(
        Group.objects.get(name="demo_verificacion_cobros"),
        Group.objects.get(name="demo_documentos_revision"),
    )
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    respuesta = cliente.post(
        reverse("facturacion:registrar_cobro", args=[solicitud.pk]),
        dict(entrada, importe="-1", confirmar_al_registrar="on", archivo=pdf()),
    )
    assert respuesta.status_code == 400
    assert respuesta.context["form"]["confirmar_al_registrar"].value()
    assert respuesta.context["form"]["numero_operacion"].value() == entrada["numero_operacion"]
    assert not CobroExterno.objects.exists()
    assert not Documento.objects.exists()


def test_operadora_sin_casilla_conserva_pendiente(escenario, solicitud, entrada):
    cobro = registrar_cobro(
        actor=operador_alta_confirmada(escenario), numero=solicitud.pk,
        datos=entrada, archivo=pdf(),
    )
    assert cobro.resultado == "PENDIENTE"
    assert not RevisionDocumento.objects.exists()


def test_fallo_alta_confirmada_revierte_hechos_y_archivo(
    escenario, solicitud, entrada, monkeypatch
):
    original = cobros.verificar_cobro

    def fallar(**kwargs):
        original(**kwargs)
        raise RuntimeError("Fallo sintético después de confirmar")

    monkeypatch.setattr(cobros, "verificar_cobro", fallar)
    with pytest.raises(RuntimeError):
        registrar_cobro(
            actor=operador_alta_confirmada(escenario), numero=solicitud.pk,
            datos=dict(entrada, confirmar_al_registrar=True), archivo=pdf(),
        )
    assert not CobroExterno.objects.exists()
    assert not VerificacionCobro.objects.exists()
    assert not RevisionDocumento.objects.exists()
    assert not Documento.objects.exists()
    assert not list((escenario.raiz / "documentos").iterdir())


@pytest.mark.parametrize("resultado", [None, "ACEPTADO", "OBSERVADO", "RECHAZADO"])
def test_alta_confirmada_respaldo_existente_no_pisa_revision(
    escenario, solicitud, entrada, resultado
):
    from documentos.revision import revisar
    from documentos.services import incorporar

    actor = operador_alta_confirmada(escenario)
    documento = incorporar(
        actor=actor, referencia=f"facturacion:{solicitud.pk}", archivo=pdf(),
        tipo="COMPROBANTE_COBRO", procedencia="EXTERNO_BANCO",
    )
    if resultado:
        revisar(
            actor=actor, documento_id=documento.pk, resultado=resultado,
            motivo="Revisión previa sintética", revision_esperada=0,
        )
    kwargs = dict(
        actor=actor, numero=solicitud.pk,
        datos=dict(entrada, documento=str(documento.pk), confirmar_al_registrar=True),
    )
    if resultado in {"OBSERVADO", "RECHAZADO"}:
        with pytest.raises(ValidationError):
            registrar_cobro(**kwargs)
        assert not CobroExterno.objects.exists()
        assert not VerificacionCobro.objects.exists()
    else:
        assert registrar_cobro(**kwargs).resultado == "CONFIRMADO"
    assert documento.revisiones.count() == 1


def test_numeracion_por_solicitud_en_detalle_verificacion_e_historial(
    escenario, solicitud, entrada, datos
):
    primero = alta(escenario, solicitud, entrada)
    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["a"], datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )
    intercalado = alta(escenario, otra, entrada, numero_operacion="OTRA-SOLICITUD")
    segundo = alta(escenario, solicitud, entrada, numero_operacion="SEGUNDO")
    assert [c.numero_en_solicitud for c in (primero, intercalado, segundo)] == [1, 1, 2]
    assert intercalado.como_historial().motivo_o_detalle.startswith("Cobro #1.")
    assert segundo.como_historial().motivo_o_detalle.startswith("Cobro #2.")
    verificacion = verificar_cobro(
        actor=revisor(escenario), numero=solicitud.pk, cobro_id=segundo.pk,
        datos={"resultado": "CONFIRMADO"},
    )
    assert verificacion.como_historial().motivo_o_detalle.startswith("Cobro #2.")
    lista, _, eventos = resumen_cobros(solicitud)
    assert [c.numero_en_solicitud for c in lista] == [1, 2]
    assert [(e.tipo_evento, e.motivo_o_detalle.split(". ")[0]) for e in eventos] == [
        ("cobro_informado", "Cobro #1"),
        ("cobro_informado", "Cobro #2"),
        ("cobro_verificado", "Cobro #2"),
    ]
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    contenido = cliente.get(reverse("facturacion:detalle", args=[otra.pk])).content.decode()
    assert "Cobro #1:" in contenido and f"Cobro #{intercalado.pk}:" not in contenido
    assert "Cobro #1. 60.10 ARS." in contenido
    contenido = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk])).content.decode()
    assert "Cobro #1. 60.10 ARS." in contenido
    assert "Cobro #2. 60.10 ARS." in contenido
    escenario.usuarios["o"].groups.add(Group.objects.get(name="demo_verificacion_cobros"))
    cliente.force_login(escenario.usuarios["o"])
    respuesta = cliente.get(reverse("facturacion:verificar_cobro", args=[otra.pk, intercalado.pk]))
    assert respuesta.status_code == 200
    assert "Verificar ingreso del cobro #1" in respuesta.content.decode()


def test_aceptacion_documental_no_confirma_ingreso(escenario, solicitud, entrada):
    from documentos.revision import revisar

    cobro = alta(escenario, solicitud, entrada)
    actor = replace(
        escenario.actores["o"],
        capabilities=escenario.actores["o"].capabilities | {"documentos.revisar"},
    )
    revisar(
        actor=actor, documento_id=cobro.documento_id, resultado="ACEPTADO",
        motivo="", revision_esperada=0,
    )
    assert resumen_cobros(solicitud)[1]["PENDIENTE"] == Decimal("60.10")
    cliente = Client()
    cliente.force_login(escenario.usuarios["o"])
    contenido = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk])).content.decode()
    assert "Falta verificar el ingreso externo" in contenido
    respuesta = cliente.get(reverse("documentos:revision", args=[cobro.documento_id]))
    contenido = respuesta.content.decode()
    assert "Aceptar este comprobante no confirma el cobro" in contenido
    verificar_cobro(
        actor=revisor(escenario), numero=solicitud.pk, cobro_id=cobro.pk,
        datos={"resultado": "CONFIRMADO"},
    )
    _, totales, _ = resumen_cobros(solicitud)
    assert totales["CONFIRMADO"] == Decimal("60.10")
    assert totales["PENDIENTE"] == Decimal("0.00")


def test_anticipos_parciales_verificacion_y_factura_posterior(escenario, solicitud, entrada):
    from facturacion.comprobantes import registrar_comprobante

    c1 = alta(escenario, solicitud, entrada)
    c2 = alta(escenario, solicitud, entrada, numero_operacion="OTRA", importe="40.15")
    c3 = alta(escenario, solicitud, entrada, numero_operacion="RECHAZADA", importe="1.01")
    assert c1.resultado == "PENDIENTE" and not solicitud.comprobantes.exists()
    assert not RevisionDocumento.objects.exists()
    assert resumen_cobros(solicitud)[1]["PENDIENTE"] == Decimal("101.26")
    for c in (c1, c2):
        verificar_cobro(
            actor=revisor(escenario),
            numero=solicitud.pk,
            cobro_id=c.pk,
            datos={"resultado": "CONFIRMADO"},
        )
    verificar_cobro(
        actor=revisor(escenario),
        numero=solicitud.pk,
        cobro_id=c3.pk,
        datos={"resultado": "RECHAZADO", "motivo": "No corresponde el ingreso"},
    )
    factura = registrar_comprobante(
        actor=escenario.actores["o"],
        numero_publico=solicitud.pk,
        datos=dict(
            tipo="FACTURA",
            cuit_emisor="30712345671",
            letra="A",
            punto_venta="1",
            numero="1",
            fecha_emision="2026-10-22",
            importe="100.25",
        ),
        archivo_pdf=pdf(),
    )
    assert factura.solicitud_id == c1.solicitud_id
    solicitud.refresh_from_db()
    assert solicitud.estado == "PRESENTADA" and solicitud.version_concurrencia == 1
    assert resumen_cobros(solicitud)[1] == {
        "CONFIRMADO": Decimal("100.25"),
        "PENDIENTE": Decimal("0.00"),
        "RECHAZADO": Decimal("1.01"),
    }
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    respuesta = cliente.get(reverse("facturacion:detalle", args=[solicitud.pk]))
    assert respuesta.status_code == 200
    assert len(respuesta.context["historial"]) == 8
    assert "CONFIRMADO" in respuesta.content.decode()


@pytest.mark.parametrize(
    "cambios",
    [
        {"importe": "0"},
        {"importe": "-1"},
        {"importe": "1.001"},
        {"importe": "NaN"},
        {"importe": 1.01},
        {"importe": True},
        {"importe": "10000000000.00"},
        {"medio": "CUENTA_CORRIENTE"},
        {"numero_operacion": "\t\n"},
        {"fecha_operacion": "invalida"},
    ],
)
def test_datos_invalidos_sin_altas(escenario, solicitud, entrada, cambios):
    with pytest.raises(ValidationError):
        alta(escenario, solicitud, entrada, **cambios)
    assert not CobroExterno.objects.exists() and not Documento.objects.exists()


def test_reutiliza_comprobante_inicial_sin_copiar(escenario, datos, entrada):
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
    assert not CobroExterno.objects.exists()
    documento = solicitud.documento_comprobante_inicial
    original = (escenario.raiz / documento.archivo).read_bytes()
    c = registrar_cobro(
        actor=escenario.actores["a"],
        numero=solicitud.pk,
        datos=dict(entrada, documento=str(documento.pk)),
    )
    assert c.documento_id == documento.pk and Documento.objects.count() == 1
    assert (escenario.raiz / documento.archivo).read_bytes() == original
    assert c.importe == Decimal("60.10") and c.resultado == "PENDIENTE"
    with pytest.raises(ValidationError):
        registrar_cobro(
            actor=escenario.actores["a"],
            numero=solicitud.pk,
            datos=dict(entrada, documento=str(documento.pk), numero_operacion="OTRA"),
        )


def test_permisos_y_objetos(escenario, solicitud, entrada, datos):
    for clave, error in (("b", ObjetoNoVisibleError), ("l", PermissionDenied)):
        with pytest.raises(error):
            registrar_cobro(
                actor=escenario.actores[clave], numero=solicitud.pk, datos=entrada, archivo=pdf()
            )
    c = alta(escenario, solicitud, entrada)
    for clave in ("a", "o", "l"):
        with pytest.raises(PermissionDenied):
            verificar_cobro(
                actor=escenario.actores[clave],
                numero=solicitud.pk,
                cobro_id=c.pk,
                datos={"resultado": "CONFIRMADO"},
            )
    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["b"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["b"]),
    )
    with pytest.raises(ObjetoNoVisibleError):
        verificar_cobro(
            actor=revisor(escenario),
            numero=otra.pk,
            cobro_id=c.pk,
            datos={"resultado": "CONFIRMADO"},
        )
    with pytest.raises(ValidationError):
        verificar_cobro(
            actor=revisor(escenario),
            numero=solicitud.pk,
            cobro_id=c.pk,
            datos={"resultado": "RECHAZADO", "motivo": "\t\n"},
        )
    assert not VerificacionCobro.objects.exists()


def test_http_csrf_conflicto_y_descarga(escenario, solicitud, entrada, datos):
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(escenario.usuarios["a"])
    url = reverse("facturacion:registrar_cobro", args=[solicitud.pk])
    assert cliente.get(url).status_code == 200
    assert cliente.post(url, dict(entrada, archivo=pdf())).status_code == 403
    token = cliente.cookies["csrftoken"].value
    assert (
        cliente.post(url, dict(entrada, archivo=pdf(), csrfmiddlewaretoken=token)).status_code
        == 302
    )
    respuesta = cliente.post(url, dict(entrada, archivo=pdf(), csrfmiddlewaretoken=token))
    assert respuesta.status_code == 409
    assert respuesta.context["form"]["numero_operacion"].value() == entrada["numero_operacion"]
    assert "ya está registrada" in respuesta.content.decode()
    assert "volvé a seleccionarlo" in respuesta.content.decode()
    cobro = CobroExterno.objects.get()
    for clave, estado in (("a", 200), ("b", 404), ("l", 403)):
        c = Client()
        c.force_login(escenario.usuarios[clave])
        r = c.get(reverse("documentos:archivo", args=[cobro.documento_id]))
        assert r.status_code == estado
        r.close()
    escenario.usuarios["o"].groups.add(Group.objects.get(name="demo_verificacion_cobros"))
    operador = Client(enforce_csrf_checks=True)
    operador.force_login(escenario.usuarios["o"])
    url = reverse("facturacion:verificar_cobro", args=[solicitud.pk, cobro.pk])
    assert operador.get(url).status_code == 200
    assert operador.post(url, {"resultado": "CONFIRMADO"}).status_code == 403
    datos_post = dict(
        resultado="CONFIRMADO", csrfmiddlewaretoken=operador.cookies["csrftoken"].value
    )
    assert operador.post(url, datos_post).status_code == 302
    assert operador.post(url, datos_post).status_code == 409
    escenario.usuarios["o"].groups.remove(Group.objects.get(name="demo_verificacion_cobros"))
    assert operador.get(url).status_code == 403
    assert (
        CobroExterno.objects.count()
        == Documento.objects.count()
        == VerificacionCobro.objects.count()
        == 1
    )


def test_duplicado_global_y_documento_ajeno(escenario, solicitud, datos, entrada):
    c = alta(escenario, solicitud, entrada)
    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["b"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["b"]),
    )
    with pytest.raises(ConflictoConcurrenciaError):
        registrar_cobro(
            actor=escenario.actores["b"],
            numero=otra.pk,
            datos=dict(entrada, numero_operacion="  OPERACION-FICTICIA-001  "),
            archivo=pdf(),
        )
    with pytest.raises(ValidationError):
        registrar_cobro(
            actor=escenario.actores["b"],
            numero=otra.pk,
            datos=dict(entrada, numero_operacion="OTRA", documento=str(c.documento_id)),
        )
    assert CobroExterno.objects.count() == Documento.objects.count() == 1


def test_rollback_de_alta_compensa_pdf(escenario, solicitud, entrada, monkeypatch):
    crear = CobroExterno.objects.create

    def fallar(**kwargs):
        crear(**kwargs)
        raise RuntimeError("Fallo sintético")

    monkeypatch.setattr(CobroExterno.objects, "create", fallar)
    with pytest.raises(RuntimeError):
        alta(escenario, solicitud, entrada)
    assert not CobroExterno.objects.exists() and not Documento.objects.exists()
    assert not list((escenario.raiz / "documentos").iterdir())


def test_sql_historia_y_reversa(escenario, solicitud, entrada):
    c = alta(escenario, solicitud, entrada)
    v = verificar_cobro(
        actor=revisor(escenario),
        numero=solicitud.pk,
        cobro_id=c.pk,
        datos={"resultado": "CONFIRMADO"},
    )
    for modelo, pk in ((CobroExterno, c.pk), (VerificacionCobro, v.pk)):
        with pytest.raises(IntegrityError), transaction.atomic():
            modelo.objects.filter(pk=pk).update(actor_id=escenario.usuarios["b"].pk)
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {modelo._meta.db_table} WHERE id=%s", [pk])
    finales = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        with pytest.raises(DatabaseError, match="Hay cobros"):
            MigrationExecutor(connection).migrate(
                [("facturacion", "0008_cobroexterno_verificacioncobro_and_more")]
            )
    finally:
        MigrationExecutor(connection).migrate(finales)
    assert CobroExterno.objects.count() == VerificacionCobro.objects.count() == 1


def test_carrera_global_compensa_perdedor(escenario, solicitud, entrada, datos, monkeypatch):
    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["a"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["a"]),
    )
    barrera = Barrier(2)
    original = cobros.incorporar

    def sincronizar(**kwargs):
        barrera.wait(timeout=10)
        return original(**kwargs)

    monkeypatch.setattr(cobros, "incorporar", sincronizar)

    def worker(s):
        try:
            alta(escenario, s, entrada)
            return "ok"
        except ConflictoConcurrenciaError:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, [solicitud, otra])) == ["conflicto", "ok"]
    assert CobroExterno.objects.count() == Documento.objects.count() == 1
    assert len(list((escenario.raiz / "documentos").iterdir())) == 1


def test_carrera_verificacion_unico_hecho(escenario, solicitud, entrada):
    c = alta(escenario, solicitud, entrada)

    def worker(resultado):
        try:
            verificar_cobro(
                actor=revisor(escenario),
                numero=solicitud.pk,
                cobro_id=c.pk,
                datos={"resultado": resultado, "motivo": "Ejemplo sintético"},
            )
            return "ok"
        except ConflictoConcurrenciaError:
            return "conflicto"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, ["CONFIRMADO", "RECHAZADO"])) == ["conflicto", "ok"]
    assert VerificacionCobro.objects.count() == 1


def test_fallo_verificacion_revierte_solo_el_nuevo_hecho(
    escenario, solicitud, entrada, monkeypatch
):
    c = alta(escenario, solicitud, entrada)
    crear = VerificacionCobro.objects.create

    def fallar(**kwargs):
        crear(**kwargs)
        raise RuntimeError("Fallo sintético")

    monkeypatch.setattr(VerificacionCobro.objects, "create", fallar)
    with pytest.raises(RuntimeError):
        verificar_cobro(
            actor=revisor(escenario),
            numero=solicitud.pk,
            cobro_id=c.pk,
            datos={"resultado": "CONFIRMADO"},
        )
    assert not VerificacionCobro.objects.exists()
    assert CobroExterno.objects.get().resultado == "PENDIENTE"
    assert Documento.objects.count() == 1


def test_sql_rechaza_blancos_nan_y_respaldo_ajeno(escenario, solicitud, entrada, datos):
    from documentos.services import incorporar

    otra = presentar_solicitud_facturacion(
        actor=escenario.actores["b"],
        datos=datos,
        token_presentacion=emitir_token(escenario.actores["b"]),
    )
    documento = incorporar(
        actor=escenario.actores["b"],
        referencia=f"facturacion:{otra.pk}",
        archivo=pdf(),
        tipo="COMPROBANTE_COBRO",
        procedencia="SOLICITANTE",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CobroExterno.objects.create(
            solicitud=solicitud,
            medio="BNA_COMUN",
            numero_operacion="X",
            importe="1.00",
            fecha_operacion="2026-10-22",
            documento=documento,
            actor=escenario.usuarios["a"],
            procedencia="SOLICITANTE",
        )
    for operacion, importe in (("\t\n", Decimal("1.00")), ("NAN", Decimal("NaN"))):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO facturacion_cobroexterno "
                "(solicitud_id,medio,numero_operacion,fecha_operacion,importe,moneda,procedencia,"
                "documento_id,actor_id,fecha_registro) "
                "VALUES (%s,'BNA_COMUN',%s,'2026-10-22',%s,'ARS','SOLICITANTE',%s,%s,NOW())",
                [otra.pk, operacion, importe, documento.pk, escenario.usuarios["b"].pk],
            )
    c = alta(escenario, solicitud, entrada)
    with pytest.raises(IntegrityError), transaction.atomic():
        VerificacionCobro.objects.create(
            cobro=c, resultado="RECHAZADO", motivo="\t\n\u00a0", actor=escenario.usuarios["o"]
        )
    assert CobroExterno.objects.count() == 1 and not VerificacionCobro.objects.exists()


def test_reversa_vacia_upgrade_preservan_solicitud(escenario, solicitud):
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("facturacion", "0007_integridad_comprobantes")])
        assert "facturacion_cobroexterno" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(finales)
        solicitud.refresh_from_db()
        assert solicitud.estado == "PRESENTADA" and solicitud.eventos.count() == 1
    finally:
        MigrationExecutor(connection).migrate(finales)
