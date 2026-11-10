from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from documentos.models import Documento
from facturacion.comprobantes import registrar_comprobante
from facturacion.forms import SolicitudFacturacionForm
from facturacion.workflow import emitir_token, presentar_solicitud_facturacion
from gestion.formularios import configuracion, guardar_campo
from gestion.models import RespuestaFormulario, VersionFormulario
from gestion.reportes import reporte_facturacion

pytestmark = pytest.mark.django_db(transaction=True)


def campo(actor, circuito="FACTURACION", clave=None, **cambios):
    revision, _ = configuracion(circuito)
    entrada = dict(
        etiqueta="Dato sintético",
        ayuda="Leyenda sintética",
        tipo="texto",
        requerido=True,
        activo=True,
        orden=100,
        opciones="",
        revision=revision,
    )
    entrada.update(cambios)
    return guardar_campo(actor, circuito, clave, entrada)


def presentar(e, datos):
    return presentar_solicitud_facturacion(
        actor=e.actores["a"], datos=datos, token_presentacion=emitir_token(e.actores["a"])
    )


def test_permisos_y_menu(escenario, administrador):
    cliente = Client()
    url = reverse("gestion:configuracion", args=["FACTURACION"])
    cliente.force_login(escenario.usuarios["o"])
    assert cliente.get(url).status_code == 403
    assert cliente.post(reverse("gestion:campo_nuevo", args=["FACTURACION"])).status_code == 403
    cliente.force_login(administrador.user)
    pagina = cliente.get(url)
    assert pagina.status_code == 200
    nav = pagina.content.decode().split(">Gestión</h3>")[1].split(">General</h3>")[0]
    assert nav.count('class="app-nl"') == 2
    assert ">Reporte<" in nav and ">Configuración<" in nav
    with pytest.raises(PermissionDenied):
        campo(escenario.actores["o"])


def test_campo_obligatorio_respuestas_y_retiro(escenario, administrador, datos):
    clave = campo(administrador.actor)
    with pytest.raises(ValidationError):
        presentar(escenario, dict(datos, configuracion_revision=1))
    s = presentar(escenario, dict(datos, configuracion_revision=1, **{clave: "Respuesta original"}))
    respuesta = s.tramite_base.respuestas_formulario.get()
    assert respuesta.datos[clave]["valor"] == "Respuesta original"
    guardar_campo(
        administrador.actor,
        "FACTURACION",
        clave,
        dict(
            etiqueta="Nombre cambiado",
            ayuda="",
            tipo="texto",
            requerido=False,
            activo=False,
            orden=100,
            opciones="",
            revision=1,
        ),
    )
    assert clave not in SolicitudFacturacionForm().fields
    respuesta.refresh_from_db()
    assert respuesta.datos[clave]["etiqueta"] == "Dato sintético"
    with pytest.raises(IntegrityError), transaction.atomic():
        RespuestaFormulario.objects.filter(pk=respuesta.pk).update(datos={})


def test_campos_esenciales_no_pueden_retirarse(escenario, administrador):
    guardar_campo(
        administrador.actor,
        "FACTURACION",
        "importe_factura",
        dict(
            etiqueta="Importe a facturar",
            ayuda="Nuevo texto",
            tipo="base",
            requerido=False,
            activo=False,
            orden=1,
            opciones="",
            revision=0,
        ),
    )
    form = SolicitudFacturacionForm()
    assert form.fields["importe_factura"].required
    assert not form.fields["importe_factura"].widget.is_hidden
    assert form.fields["importe_factura"].label == "Importe a facturar"


def test_version_obsoleta_no_sobrescribe(escenario, administrador, datos):
    clave = campo(administrador.actor)
    with pytest.raises(ValidationError):
        presentar(escenario, dict(datos, configuracion_revision=0, **{clave: "Valor"}))
    with pytest.raises(ValidationError):
        guardar_campo(
            administrador.actor,
            "FACTURACION",
            clave,
            dict(
                etiqueta="Cambio",
                tipo="texto",
                activo=True,
                requerido=False,
                opciones="",
                orden=1,
                revision=0,
            ),
        )
    assert VersionFormulario.objects.count() == 1


def test_catalogo_con_opciones_nuevas(escenario, administrador, datos):
    guardar_campo(
        administrador.actor,
        "FACTURACION",
        "producto_servicio",
        dict(
            etiqueta="Servicio",
            ayuda="",
            tipo="base",
            activo=True,
            requerido=True,
            opciones="ANALISIS | Análisis\nSERVICIO_NUEVO | Servicio nuevo",
            orden=1,
            revision=0,
        ),
    )
    s = presentar(
        escenario, dict(datos, producto_servicio="SERVICIO_NUEVO", configuracion_revision=1)
    )
    assert s.producto_servicio == "SERVICIO_NUEVO"
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    pagina = cliente.get(reverse("facturacion:detalle", args=[s.pk]))
    assert pagina.context["datos_configurados"]["producto_servicio"] == "Servicio nuevo"
    assert "<dd>Servicio nuevo</dd>" in pagina.content.decode()


def test_documento_adicional_gasto_protegido(escenario, administrador):
    clave = campo(administrador.actor, circuito="GASTO", tipo="documento")
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    respuesta = cliente.post(
        reverse("gastos:presentar"),
        dict(
            concepto="Compra sintética",
            monto_estimado="100.25",
            unidad_requirente="Laboratorio",
            tipo_flujo="COMPRA_DIRECTA",
            configuracion_revision=1,
            **{
                clave: SimpleUploadedFile(
                    "ficticio.pdf", b"%PDF-1.7\nFicticio\n%%EOF", "application/pdf"
                )
            },
        ),
    )
    assert respuesta.status_code == 302
    doc = Documento.objects.get(tipo="ANEXO_SOLICITUD")
    assert RespuestaFormulario.objects.get().datos[clave]["documento_id"] == doc.pk
    cliente.force_login(escenario.usuarios["b"])
    assert cliente.get(reverse("documentos:archivo", args=[doc.pk])).status_code == 404
    cliente.force_login(escenario.usuarios["l"])
    contenido = cliente.get(
        reverse("gastos:detalle", args=[doc.solicitud_gasto_id])
    ).content.decode()
    assert "Información documental no disponible" in contenido
    assert "ficticio.pdf" not in contenido


def test_reporte_decimal_separa_solicitado_factura_y_cobro(escenario, datos):
    s = presentar(escenario, datos)
    registrar_comprobante(
        actor=escenario.actores["o"],
        numero_publico=s.pk,
        archivo_pdf=None,
        datos=dict(
            tipo="FACTURA",
            cuit_emisor="30712345671",
            letra="A",
            punto_venta=1,
            numero=1,
            fecha_emision="2026-01-01",
            importe="90.15",
        ),
    )
    registrar_comprobante(
        actor=escenario.actores["o"],
        numero_publico=s.pk,
        archivo_pdf=None,
        datos=dict(
            tipo="NOTA_CREDITO",
            cuit_emisor="30712345671",
            letra="A",
            punto_venta=1,
            numero=2,
            fecha_emision="2026-01-01",
            importe="10.10",
        ),
    )
    resumen = reporte_facturacion(s.fecha_presentacion.year)
    assert resumen["cantidad"] == 1 and resumen["facturas"] == 1
    assert resumen["solicitado"] == Decimal("100.25")
    assert resumen["neto"] == Decimal("80.05")
    assert resumen["promedio_factura"] == Decimal("90.15")
    assert resumen["confirmado"] == Decimal("0.00")
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    assert cliente.get(reverse("gestion:reporte_facturacion")).status_code == 403
    cliente.force_login(escenario.usuarios["o"])
    assert cliente.get(reverse("gestion:reporte_facturacion")).status_code == 200
    assert cliente.get(reverse("gestion:reporte_facturacion"), {"anio": "no"}).status_code == 400


def test_archivo_facturacion_y_correccion_conservan_adjunto(escenario, administrador, datos):
    from facturacion.models import SolicitudFacturacion
    from facturacion.workflow import corregir_solicitud_facturacion, observar_solicitud_facturacion

    clave = campo(administrador.actor, tipo="documento")
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    respuesta = cliente.post(
        reverse("facturacion:presentar"),
        dict(
            datos,
            configuracion_revision=1,
            token_presentacion=emitir_token(escenario.actores["a"]),
            **{
                clave: SimpleUploadedFile(
                    "ficticio.pdf", b"%PDF-1.7\nFicticio\n%%EOF", "application/pdf"
                )
            },
        ),
    )
    assert respuesta.status_code == 302
    solicitud = SolicitudFacturacion.objects.get()
    documento = Documento.objects.get(tipo="ANEXO_SOLICITUD")
    observar_solicitud_facturacion(
        actor=escenario.actores["o"],
        numero_publico=solicitud.pk,
        motivo="Corregir texto",
        version_esperada=1,
    )
    corregir_solicitud_facturacion(
        actor=escenario.actores["a"],
        numero_publico=solicitud.pk,
        datos=dict(datos, configuracion_revision=1),
        version_esperada=2,
    )
    respuestas = solicitud.tramite_base.respuestas_formulario.order_by("pk")
    assert respuestas.count() == 2
    assert respuestas.last().datos[clave]["documento_id"] == documento.pk
    assert Documento.objects.count() == 1


def test_configuracion_gastos_incluye_atp(escenario, administrador):
    cliente = Client()
    cliente.force_login(administrador.user)
    pagina = cliente.get(reverse("gestion:configuracion", args=["GASTO"]))
    assert pagina.status_code == 200
    assert 'name="base_imponible_atp"' in pagina.content.decode()


@pytest.mark.parametrize(
    "tipo,valor,esperado",
    [
        ("texto", "Dato", "Dato"),
        ("parrafo", "Primera\nSegunda", "Primera\nSegunda"),
        ("seleccion", "b", "Segundo"),
        ("multiple", ["b", "a"], "Segundo, Primero"),
        ("radio", "a", "Primero"),
        ("casilla", True, "Sí"),
    ],
)
def test_tipos_de_respuesta(escenario, administrador, datos, tipo, valor, esperado):
    opciones = "a | Primero\nb | Segundo" if tipo in {"seleccion", "multiple", "radio"} else ""
    clave = campo(administrador.actor, tipo=tipo, opciones=opciones)
    s = presentar(escenario, dict(datos, configuracion_revision=1, **{clave: valor}))
    assert s.tramite_base.respuestas_formulario.get().datos[clave]["valor"] == esperado


def test_fallo_respuesta_compensa_documento(escenario, administrador, datos, monkeypatch):
    from facturacion.models import SolicitudFacturacion

    clave = campo(administrador.actor, tipo="documento")

    def fallar(**kwargs):
        raise RuntimeError("Fallo sintético de respuesta")

    monkeypatch.setattr(RespuestaFormulario.objects, "create", fallar)
    with pytest.raises(RuntimeError):
        presentar_solicitud_facturacion(
            actor=escenario.actores["a"],
            datos=dict(datos, configuracion_revision=1),
            token_presentacion=emitir_token(escenario.actores["a"]),
            archivos_adicionales={
                clave: SimpleUploadedFile(
                    "ficticio.pdf", b"%PDF-1.7\nFicticio\n%%EOF", "application/pdf"
                )
            },
        )
    assert not SolicitudFacturacion.objects.exists()
    assert not Documento.objects.exists()
    assert not list(escenario.raiz.glob("documentos/*"))


def test_preparar_administrador_no_cambia_password(escenario):
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    call_command("preparar_administrador", username="admin_sintetico")
    user = get_user_model().objects.get(username="admin_sintetico")
    assert not user.has_usable_password()
    assert not user.is_staff and not user.is_superuser
    user.set_password("clave-sintetica-solo-prueba")
    user.save()
    anterior = user.password
    call_command("preparar_administrador", username="admin_sintetico")
    user.refresh_from_db()
    assert user.password == anterior
    assert user.groups.filter(name="demo_administracion").exists()


def test_reporte_excluye_anuladas_y_solo_suma_ingresos_confirmados(escenario, datos):
    from tests.facturacion.test_cierre import cobro, resolver

    s = presentar(escenario, datos)
    cobro(escenario, s, importe="40.10", operacion="COBRO-FICTICIO-CONFIRMADO")
    cobro(escenario, s, importe="5.00", operacion="COBRO-FICTICIO-PENDIENTE", confirmar=False)
    anulada = presentar(escenario, datos)
    resolver(escenario, anulada, accion="anular", motivo="Cancelación sintética")
    resumen = reporte_facturacion(s.fecha_presentacion.year)
    assert resumen["cantidad"] == 1 and resumen["anuladas"] == 1
    assert resumen["confirmado"] == Decimal("40.10")
    assert resumen["solicitado"] == Decimal("100.25")


def test_reporte_conserva_nombre_de_grupo_retirado(escenario, administrador, datos):
    guardar_campo(
        administrador.actor,
        "FACTURACION",
        "centro_costo",
        dict(
            etiqueta="Grupo",
            ayuda="",
            tipo="base",
            requerido=True,
            activo=True,
            opciones="GRUPO_X | Grupo histórico",
            orden=1,
            revision=0,
        ),
    )
    s = presentar(escenario, dict(datos, centro_costo="GRUPO_X", configuracion_revision=1))
    guardar_campo(
        administrador.actor,
        "FACTURACION",
        "centro_costo",
        dict(
            etiqueta="Grupo",
            ayuda="",
            tipo="base",
            requerido=True,
            activo=True,
            opciones="GRUPO_Y | Grupo nuevo",
            orden=1,
            revision=1,
        ),
    )
    assert (
        reporte_facturacion(s.fecha_presentacion.year)["centros"][0]["nombre"] == "Grupo histórico"
    )
    assert (
        s.tramite_base.respuestas_formulario.get().datos["centro_costo"]["valor"]
        == "Grupo histórico"
    )


def test_no_agrega_codigo_de_modalidad_financiera(escenario, administrador):
    with pytest.raises(ValidationError):
        guardar_campo(
            administrador.actor,
            "FACTURACION",
            "modalidad_cobro",
            dict(
                etiqueta="Medio",
                ayuda="",
                tipo="base",
                requerido=True,
                activo=True,
                opciones="DESCONOCIDO | Código sin regla financiera",
                orden=1,
                revision=0,
            ),
        )
    assert VersionFormulario.objects.count() == 0


def test_centro_requerido_no_obliga_a_completar_banco(escenario, administrador):
    from gastos.models import CentroCosto

    centro = CentroCosto.objects.create(codigo="LAB_TEST", nombre="Laboratorio sintético")
    campo(administrador.actor, circuito="GASTO", clave="centro_costo", tipo="base", requerido=True)
    cliente = Client()
    cliente.force_login(escenario.usuarios["a"])
    respuesta = cliente.post(
        reverse("gastos:presentar"),
        dict(
            concepto="Solicitud sintética",
            monto_estimado="100.25",
            unidad_requirente="Laboratorio",
            centro_costo=centro.pk,
            configuracion_revision=1,
        ),
    )
    assert respuesta.status_code == 302
