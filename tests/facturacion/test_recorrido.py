"""Recorrido funcional, permisos por objeto y errores de formularios/servicios."""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from comunes.models import TramiteBase
from documentos.models import Documento
from documentos.operaciones import TransaccionAnidadaNoPermitidaError
from facturacion.models import EventoFacturacion, SolicitudFacturacion
from facturacion.permissions import ObjetoNoVisibleError
from facturacion.services import crear_solicitud_tecnica
from facturacion.workflow import (
    ConflictoConcurrenciaError,
    PresentacionDuplicadaError,
    corregir_solicitud_facturacion,
    emitir_token,
    observar_solicitud_facturacion,
    presentar_solicitud_facturacion,
)
from identidad.services import Actor, has_capability, resolve_actor

pytestmark = pytest.mark.django_db(transaction=True)


def cliente(user):
    client = Client()
    client.force_login(user)
    return client


def pdf():
    return SimpleUploadedFile("ficticio.pdf", b"%PDF-1.7\nFicticio\n%%EOF", "application/pdf")


def presentar(e, datos, **kwargs):
    return presentar_solicitud_facturacion(
        actor=e.actores["a"],
        datos=datos,
        token_presentacion=kwargs.pop("token", emitir_token(e.actores["a"])),
        **kwargs,
    )


def observar(e, solicitud):
    return observar_solicitud_facturacion(
        actor=e.actores["o"],
        numero_publico=solicitud.pk,
        motivo="Precisar el período",
        version_esperada=solicitud.version_concurrencia,
    )


def test_recorrido_conserva_identidad_versiones_y_observacion(escenario, datos):
    e = escenario
    datos.update(correo_solicitante="inyectado@example.invalid", estado="CERRADA")
    solicitud = presentar(e, datos)
    assert solicitud.estado == "PRESENTADA"
    assert solicitud.correo_solicitante == e.usuarios["a"].email
    observar(e, solicitud)
    nueva = corregir_solicitud_facturacion(
        actor=e.actores["a"],
        numero_publico=solicitud.pk,
        version_esperada=2,
        datos=dict(datos, detalle_factura="Período octubre", centro_costo="QUITEX"),
    )
    assert nueva.version_concurrencia == 3 and nueva.estado == "PRESENTADA"
    assert nueva.centro_costo == "QUITEX" and nueva.observacion_vigente == ""
    eventos = list(nueva.eventos.all())
    assert [x.tipo_evento for x in eventos] == ["PRESENTACION", "OBSERVACION", "CORRECCION"]
    snapshot = eventos[-1].snapshot_datos
    assert snapshot["antes"]["detalle_factura"] == "Servicio ficticio"
    assert snapshot["despues"]["detalle_factura"] == "Período octubre"
    assert snapshot["observacion_atendida"] == "Precisar el período"
    assert snapshot["despues"]["importe_factura"] == "100.25"
    assert nueva.correo_solicitante == solicitud.correo_solicitante
    with pytest.raises(ConflictoConcurrenciaError):
        corregir_solicitud_facturacion(
            actor=e.actores["a"],
            numero_publico=nueva.pk,
            version_esperada=2,
            datos=datos,
        )
    assert nueva.eventos.count() == 3
    respuesta = cliente(e.usuarios["a"]).get(reverse("facturacion:detalle", args=[nueva.pk]))
    assert respuesta.status_code == 200
    assert "Servicio ficticio" in respuesta.content.decode()


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("cuit_receptor", "30712345679"),
        ("importe_factura", "-1.00"),
        ("importe_factura", "1.001"),
        ("importe_factura", "NaN"),
        ("importe_factura", "10000000000.00"),
        ("email_envio_factura", "inválido"),
        ("centro_costo", "NO_EXISTE"),
        ("nombre_solicitante", "   "),
        ("presento_comprobante_pago", ""),
        ("producto_servicio", "NO_EXISTE"),
    ],
)
def test_invalido_no_crea_tramite_evento_ni_archivo(escenario, datos, campo, valor):
    with pytest.raises(ValidationError):
        presentar(escenario, dict(datos, **{campo: valor}))
    assert not SolicitudFacturacion.objects.exists()
    assert not TramiteBase.objects.exists()
    assert not EventoFacturacion.objects.exists()
    assert not escenario.raiz.exists()


def test_d01_documentos_y_reemplazo_conservan_version_anterior(escenario, datos):
    e = escenario
    datos.update(
        presento_comprobante_pago=True,
        modalidad_cobro="BNA_COMUN",
        fecha_operacion_declarada="2026-10-12",
        numero_operacion_declarado="FICTICIA-1",
    )
    with pytest.raises(ValidationError):
        presentar(e, datos)
    solicitud = presentar(e, datos, archivo_comprobante=pdf())
    anterior = solicitud.documento_comprobante_inicial
    observar(e, solicitud)
    nueva = corregir_solicitud_facturacion(
        actor=e.actores["a"],
        numero_publico=solicitud.pk,
        datos=datos,
        version_esperada=2,
        archivo_comprobante=pdf(),
    )
    doc = nueva.documento_comprobante_inicial
    assert doc.version == 2 and doc.reemplaza_id == anterior.pk and doc.serie == anterior.serie
    assert (e.raiz / anterior.archivo).exists() and (e.raiz / doc.archivo).exists()
    assert nueva.eventos.last().snapshot_datos["antes"]["documento_comprobante_inicial"][
        "referencia_version"
    ] == str(anterior.referencia_version)


@pytest.mark.parametrize(
    "respuesta,modalidad",
    [
        (True, "CUENTA_CORRIENTE"),
        (False, "BNA_COMUN"),
        (False, "CUENTA_CORRIENTE"),
    ],
)
def test_opcionales_no_inventan_restricciones(escenario, datos, respuesta, modalidad):
    solicitud = presentar(
        escenario,
        dict(
            datos,
            presento_comprobante_pago=respuesta,
            modalidad_cobro=modalidad,
            numero_operacion_declarado="DATO-OPCIONAL",
        ),
        archivo_comprobante=pdf(),
    )
    assert solicitud.numero_operacion_declarado == "DATO-OPCIONAL"
    assert solicitud.documento_comprobante_inicial_id is not None


def test_correccion_sin_archivo_conserva_y_retirada_explicita_preserva_historia(escenario, datos):
    e = escenario
    solicitud = presentar(e, datos, archivo_comprobante=pdf())
    doc = solicitud.documento_comprobante_inicial
    observar(e, solicitud)
    nueva = corregir_solicitud_facturacion(
        actor=e.actores["a"],
        numero_publico=solicitud.pk,
        datos=datos,
        version_esperada=2,
    )
    assert nueva.documento_comprobante_inicial_id == doc.pk
    observar(e, nueva)
    nueva = corregir_solicitud_facturacion(
        actor=e.actores["a"],
        numero_publico=solicitud.pk,
        datos=dict(datos, retirar_comprobante=True),
        version_esperada=4,
    )
    assert nueva.documento_comprobante_inicial_id is None
    assert Documento.objects.filter(pk=doc.pk).exists() and (e.raiz / doc.archivo).exists()


def test_autorizacion_objeto_y_servicio_directo(escenario, datos):
    e = escenario
    solicitud = presentar(e, datos)
    with pytest.raises(ObjetoNoVisibleError):
        observar_solicitud_facturacion(
            actor=e.actores["b"],
            numero_publico=solicitud.pk,
            motivo="Ajeno",
            version_esperada=1,
        )
    with pytest.raises(PermissionDenied):
        observar_solicitud_facturacion(
            actor=e.actores["l"],
            numero_publico=solicitud.pk,
            motivo="Lectura",
            version_esperada=1,
        )
    detalle = reverse("facturacion:detalle", args=[solicitud.pk])
    assert cliente(e.usuarios["b"]).get(detalle).status_code == 404
    assert cliente(e.usuarios["l"]).get(detalle).status_code == 200
    lista = cliente(e.usuarios["b"]).get(reverse("facturacion:lista"))
    assert list(lista.context["pagina"]) == []
    assert (
        cliente(e.usuarios["l"])
        .post(reverse("facturacion:observar", args=[solicitud.pk]), {"version_esperada": 1})
        .status_code
        == 403
    )
    tecnico = crear_solicitud_tecnica(actor=e.actores["a"])
    assert (
        cliente(e.usuarios["a"]).get(reverse("facturacion:detalle", args=[tecnico.pk])).status_code
        == 404
    )


def test_token_repetido_manipulado_y_otra_identidad(escenario, datos):
    e = escenario
    token = emitir_token(e.actores["a"])
    presentar(e, datos, token=token)
    with pytest.raises(PresentacionDuplicadaError):
        presentar(e, datos, token=token)
    for value in (token + "x", "", emitir_token(e.actores["b"])):
        with pytest.raises(ValidationError):
            presentar(e, datos, token=value)
    assert SolicitudFacturacion.objects.count() == 1
    assert TramiteBase.objects.count() == 1


def test_http_formulario_errores_metadatos_y_csrf(escenario, datos):
    e = escenario
    c = cliente(e.usuarios["a"])
    url = reverse("facturacion:presentar")
    respuesta = c.get(url)
    assert respuesta.status_code == 200 and not SolicitudFacturacion.objects.exists()
    token = respuesta.context["token"]
    invalidos = dict(datos, cuit_receptor="inválido", token_presentacion=token)
    respuesta = c.post(url, invalidos)
    assert respuesta.status_code == 400 and respuesta.context["token"] == token
    respuesta = c.post(url, dict(datos, token_presentacion=token, estado="CERRADA"))
    assert respuesta.status_code == 302
    solicitud = SolicitudFacturacion.objects.get()
    assert solicitud.estado == "PRESENTADA"
    assert c.get(reverse("facturacion:observar", args=[solicitud.pk])).status_code == 405
    protegido = Client(enforce_csrf_checks=True)
    protegido.force_login(e.usuarios["a"])
    for ruta in (
        url,
        reverse("facturacion:corregir", args=[solicitud.pk]),
        reverse("facturacion:observar", args=[solicitud.pk]),
    ):
        assert protegido.post(ruta, datos).status_code == 403
    assert EventoFacturacion.objects.count() == 1


@pytest.mark.parametrize("correccion", [False, True])
def test_cuit_invalido_muestra_un_solo_error_y_conserva_datos(escenario, datos, correccion):
    e = escenario
    c = cliente(e.usuarios["a"])
    if correccion:
        solicitud = presentar(e, datos)
        observar(e, solicitud)
        url = reverse("facturacion:corregir", args=[solicitud.pk])
        controles = {"version_esperada": 2}
    else:
        url = reverse("facturacion:presentar")
        controles = {"token_presentacion": c.get(url).context["token"]}
    eventos_antes = EventoFacturacion.objects.count()
    solicitudes_antes = SolicitudFacturacion.objects.count()
    respuesta = c.post(url, dict(datos, cuit_receptor="30712345679", **controles))
    mensaje = "El dígito verificador del CUIT no es válido."
    assert respuesta.status_code == 400
    assert respuesta.content.decode().count(mensaje) == 1
    assert respuesta.context["form"]["detalle_factura"].value() == datos["detalle_factura"]
    assert EventoFacturacion.objects.count() == eventos_antes
    assert SolicitudFacturacion.objects.count() == solicitudes_antes
    if correccion:
        solicitud.refresh_from_db()
        assert solicitud.estado == "OBSERVADA" and solicitud.version_concurrencia == 2


def test_preparacion_compatible_revocacion_y_actor_sin_correo(escenario, datos):
    e = escenario
    user = e.usuarios["a"]
    user.set_password("ficticia")
    user.save()
    clave = user.password
    call_command("preparar_identidad_demo", facturacion=True, stdout=StringIO())
    call_command("preparar_identidad_demo", stdout=StringIO())
    user.refresh_from_db()
    assert user.password == clave and user.groups.filter(name="demo_solicitante").exists()
    assert user.groups.filter(name="demo_facturacion_solicitante").exists()
    o = e.usuarios["o"]
    o.groups.add(Group.objects.get(name="demo_facturacion_lectura"))
    c = cliente(o)
    req = c.get(reverse("facturacion:lista")).wsgi_request
    assert has_capability(resolve_actor(req), "facturacion.observar")
    o.groups.remove(Group.objects.get(name="demo_facturacion_operadora"))
    req = c.get(reverse("facturacion:lista")).wsgi_request
    assert not has_capability(resolve_actor(req), "facturacion.observar")
    assert Actor(1, frozenset()).email_registrado is None
    with pytest.raises(ValidationError):
        presentar_solicitud_facturacion(
            actor=Actor(user.pk, e.actores["a"].capabilities),
            token_presentacion=emitir_token(e.actores["a"]),
            datos=datos,
        )


def test_sql_rechaza_respaldo_ajeno_y_operativa_incompleta(escenario, datos):
    e = escenario
    a = presentar(e, datos)
    b = presentar_solicitud_facturacion(
        actor=e.actores["b"],
        token_presentacion=emitir_token(e.actores["b"]),
        datos=datos,
        archivo_comprobante=pdf(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        SolicitudFacturacion.objects.filter(pk=a.pk).update(
            documento_comprobante_inicial_id=b.documento_comprobante_inicial_id
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        SolicitudFacturacion.objects.filter(pk=a.pk).update(nombre_solicitante="")


def test_servicio_rechaza_transaccion_exterior(escenario, datos):
    with transaction.atomic(), pytest.raises(TransaccionAnidadaNoPermitidaError):
        presentar(escenario, datos)
    assert not SolicitudFacturacion.objects.exists()


def test_sesiones_anonimas_inactivas_y_superusuario(escenario, datos, settings):
    url = reverse("facturacion:lista")
    assert Client().get(url).status_code == 302
    superuser = get_user_model().objects.create_superuser("tecnico", password="demo")
    assert cliente(superuser).get(url).status_code == 403
    user = escenario.usuarios["a"]
    c = cliente(user)
    user.is_active = False
    user.save()
    assert c.get(url).status_code == 302
    settings.DEMO_IDENTITY_ENABLED = False
    assert c.get(url).status_code == 403


def test_fallo_storage_http_no_expone_detalles_privados(escenario, datos, monkeypatch):
    from facturacion import views

    def falla(**kwargs):
        raise OSError("ruta-privada-ficticia")

    monkeypatch.setattr(views, "presentar_solicitud_facturacion", falla)
    respuesta = cliente(escenario.usuarios["a"]).post(
        reverse("facturacion:presentar"),
        datos,
    )
    assert respuesta.status_code == 503
    assert "ruta-privada-ficticia" not in respuesta.content.decode()
