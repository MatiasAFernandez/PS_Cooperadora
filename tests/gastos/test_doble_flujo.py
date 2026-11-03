"""Pruebas para el doble flujo de gastos y sincronización de Centro de Costo (Issue #90).

Cubre:
- GAST-R01: Registro del tipo_flujo (COMPRA_DIRECTA / REINTEGRO) en SolicitudGasto.
- GAST-R02: Sincronización automática de CentroCosto hacia RevisionDatosTransferencia.
- GAST-R03: Exigencia de FACTURA_PROVEEDOR para pagos de REINTEGRO (rechazando presupuestos),
  mientras que COMPRA_DIRECTA admite tanto presupuesto como factura.
- Filtrado de centros de costo activos en el formulario de alta.
- Vistas de presentación y detalle con modalidad y centro de costo.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gastos.contracts import DocumentoVerificado, DocumentVerificationError, OpcionDocumental
from gastos.datos_transferencia import registrar_revision_datos_transferencia
from gastos.forms import DatosTransferenciaForm, PagoExternoForm, SolicitudGastoForm
from gastos.models import (
    CentroCosto,
    EstadoSolicitud,
    PagoExterno,
    RevisionDatosTransferencia,
    SolicitudGasto,
    TipoFlujoGasto,
)
from gastos.payments import registrar_pago_externo
from gastos.services import crear_solicitud_gasto
from tests.gastos.conftest import FakeDocumentVerificationPort, issue_csrf_credentials
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# 1. Modelos y defaults retrocompatibles (GAST-R01)
# ---------------------------------------------------------------------------


def test_modelo_solicitud_tipo_flujo_default_compra_directa(create_actor: Any) -> None:
    """Verifica que SolicitudGasto tiene COMPRA_DIRECTA por defecto y centro_costo nulo."""
    user, _ = create_actor("demo_solicitante_1", ["gastos.presentar"])
    solicitud = crear_gasto_sintetico(solicitante=user)

    assert solicitud.tipo_flujo == TipoFlujoGasto.COMPRA_DIRECTA
    assert solicitud.centro_costo is None
    assert solicitud.get_tipo_flujo_display() == "Compra directa a proveedor"


def test_modelo_solicitud_con_tipo_flujo_reintegro_y_centro_costo(create_actor: Any) -> None:
    """Verifica la persistencia de REINTEGRO y la relación con CentroCosto."""
    user, _ = create_actor("demo_solicitante_2", ["gastos.presentar"])
    centro = CentroCosto.objects.create(
        codigo="lab-fisica",
        nombre="Laboratorio de Física",
        activo=True,
    )
    solicitud = crear_gasto_sintetico(
        solicitante=user,
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
        centro_costo=centro,
    )

    solicitud.refresh_from_db()
    assert solicitud.tipo_flujo == TipoFlujoGasto.REINTEGRO
    assert solicitud.centro_costo == centro
    assert solicitud.get_tipo_flujo_display() == "Reintegro a solicitante"
    assert list(centro.solicitudes.all()) == [solicitud]


# ---------------------------------------------------------------------------
# 2. Servicio de creación y sincronización de Centro de Costo (GAST-R02)
# ---------------------------------------------------------------------------


def test_crear_solicitud_gasto_con_flujo_y_centro_costo(create_actor: Any) -> None:
    """crear_solicitud_gasto asigna tipo_flujo, centro_costo y sincroniza TramiteBase."""
    user, actor = create_actor("demo_solicitante_3", ["gastos.presentar"])
    centro = CentroCosto.objects.create(
        codigo="dpto-sistemas",
        nombre="Departamento de Sistemas",
        activo=True,
    )

    solicitud = crear_solicitud_gasto(
        actor=actor,
        concepto="Servidores de desarrollo",
        monto_estimado=Decimal("150000.00"),
        unidad_requirente="Área de Infraestructura",
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
        centro_costo=centro,
    )

    assert solicitud.tipo_flujo == TipoFlujoGasto.REINTEGRO
    assert solicitud.centro_costo == centro
    assert solicitud.tramite_base.centro_costo_codigo == "dpto-sistemas"


def test_sincronizacion_automatica_centro_costo_en_transferencia_gast_r02(
    create_actor: Any,
) -> None:
    """GAST-R02: Si centro_costo viene vacío en transferencia pero seleccionado en el alta,

    se auto-puebla RevisionDatosTransferencia.centro_costo con centro_costo.nombre en el servidor.
    """
    user, actor = create_actor("demo_solicitante_4", ["gastos.presentar"])
    centro = CentroCosto.objects.create(
        codigo="lab-quimica",
        nombre="Laboratorio de Química",
        activo=True,
    )

    datos_transferencia = {
        "titular_nombre": "Docente Investigador",
        "identificacion": "20-30405060-7",
        "cbu_alias": "investigador.quimica",
        "correo_comprobante": "docente@investigacion.edu.ar",
        "centro_costo": "",  # Vacío deliberadamente
    }

    solicitud = crear_solicitud_gasto(
        actor=actor,
        concepto="Reactivos de ensayo",
        monto_estimado=Decimal("45000.00"),
        unidad_requirente="Cátedra Química General",
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
        centro_costo=centro,
        datos_transferencia=datos_transferencia,
    )

    revision = solicitud.revisiones_datos_transferencia.get(numero_revision=1)
    assert revision.titular_nombre == "Docente Investigador"
    assert revision.centro_costo == "Laboratorio de Química"


def test_sincronizacion_centro_costo_respeta_valor_explicito(create_actor: Any) -> None:
    """Si el usuario escribe explícitamente un centro_costo textual, no se sobreescribe."""
    user, actor = create_actor("demo_solicitante_5", ["gastos.presentar"])
    centro = CentroCosto.objects.create(
        codigo="secretaria-academica",
        nombre="Secretaría Académica",
        activo=True,
    )

    datos_transferencia = {
        "titular_nombre": "Bedelía",
        "identificacion": "27-11223344-5",
        "cbu_alias": "bedelia.frre",
        "correo_comprobante": "bedelia@frre.utn.edu.ar",
        "centro_costo": "Subsecretaría Estudiantil",
    }

    solicitud = crear_solicitud_gasto(
        actor=actor,
        concepto="Libretas universitarias",
        monto_estimado=Decimal("30000.00"),
        unidad_requirente="Bedelía Central",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=centro,
        datos_transferencia=datos_transferencia,
    )

    revision = solicitud.revisiones_datos_transferencia.get(numero_revision=1)
    assert revision.centro_costo == "Subsecretaría Estudiantil"


def test_sincronizacion_en_nueva_revision_posterior(create_actor: Any) -> None:
    """Al registrar una revisión posterior con centro_costo vacío, hereda centro_costo.nombre."""
    user, actor = create_actor("demo_solicitante_6", ["gastos.presentar"])
    centro = CentroCosto.objects.create(
        codigo="cadi",
        nombre="Centro de Apoyo al Desarrollo Infantil",
        activo=True,
    )

    solicitud = crear_solicitud_gasto(
        actor=actor,
        concepto="Material didáctico",
        monto_estimado=Decimal("25000.00"),
        unidad_requirente="CADI",
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
        centro_costo=centro,
    )

    revision = registrar_revision_datos_transferencia(
        actor=actor,
        solicitud_id=solicitud.pk,
        datos={
            "titular_nombre": "Maestra Coordinadora",
            "identificacion": "27-99887766-5",
            "cbu_alias": "cadi.cooperadora",
            "correo_comprobante": "cadi@frre.utn.edu.ar",
            "centro_costo": "",
        },
    )

    assert revision.numero_revision == 1
    assert revision.centro_costo == "Centro de Apoyo al Desarrollo Infantil"


# ---------------------------------------------------------------------------
# 3. Formularios y filtrado de centros de costo activos
# ---------------------------------------------------------------------------


def test_solicitud_gasto_form_filtra_centros_activos() -> None:
    """El formulario sólo incluye centros de costo activos en las opciones."""
    c_activo = CentroCosto.objects.create(
        codigo="activo-1",
        nombre="Centro Activo",
        activo=True,
    )
    c_inactivo = CentroCosto.objects.create(
        codigo="inactivo-1",
        nombre="Centro Inactivo",
        activo=False,
    )

    form = SolicitudGastoForm()
    qs = form.fields["centro_costo"].queryset
    assert c_activo in qs
    assert c_inactivo not in qs


def test_solicitud_gasto_form_validacion_tipo_flujo() -> None:
    """Valida opciones válidas de tipo_flujo y rechaza valores espurios."""
    c_activo = CentroCosto.objects.create(
        codigo="activo-2",
        nombre="Centro Activo 2",
        activo=True,
    )

    # Válido con REINTEGRO
    form_valido = SolicitudGastoForm(
        data={
            "concepto": "Insumos de soldadura",
            "monto_estimado": "12500.00",
            "unidad_requirente": "Taller Mecánico",
            "tipo_flujo": TipoFlujoGasto.REINTEGRO,
            "centro_costo": str(c_activo.pk),
        }
    )
    assert form_valido.is_valid()
    assert form_valido.cleaned_data["tipo_flujo"] == TipoFlujoGasto.REINTEGRO
    assert form_valido.cleaned_data["centro_costo"] == c_activo

    # Inválido
    form_invalido = SolicitudGastoForm(
        data={
            "concepto": "Insumos de soldadura",
            "monto_estimado": "12500.00",
            "unidad_requirente": "Taller Mecánico",
            "tipo_flujo": "FLUJO_FANTASMA",
        }
    )
    assert not form_invalido.is_valid()
    assert "tipo_flujo" in form_invalido.errors


def test_datos_transferencia_form_centro_costo_default() -> None:
    """DatosTransferenciaForm completa el centro_costo por defecto si el usuario lo omitió."""
    form = DatosTransferenciaForm(
        data={
            "titular_nombre": "Profesor Adjunto",
            "identificacion": "20-11223344-5",
            "cbu_alias": "prof.cuenta",
            "correo_comprobante": "prof@frre.utn.edu.ar",
            "centro_costo": "",
        },
        centro_costo_default="Departamento de Electrónica",
    )
    assert form.is_valid()
    assert form.cleaned_data["centro_costo"] == "Departamento de Electrónica"
    assert form.datos_transferencia["centro_costo"] == "Departamento de Electrónica"


# ---------------------------------------------------------------------------
# 4. Exigencia de Contrato C01 en Pagos de Reintegro (GAST-R03)
# ---------------------------------------------------------------------------


def test_reintegro_exige_factura_proveedor_y_rechaza_presupuesto_gast_r03(
    create_actor: Any,
    actor_factory: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """GAST-R03: En REINTEGRO, registrar_pago_externo exige tipos_admitidos=('factura',).

    Si el proveedor sólo tiene o valida presupuestos, el pago es rechazado con
    DocumentVerificationError.
    """
    _, solicitante = create_actor("solic_reintegro", ["gastos.presentar"])
    _, pagador = actor_factory(["gastos.registrar_pago", "gastos.consultar_todas"])

    solicitud = crear_solicitud_gasto(
        actor=solicitante,
        concepto="Reintegro por compra menor de tornillos",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Mantenimiento",
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
    )
    solicitud.estado = EstadoSolicitud.ACEPTADA
    solicitud.save(update_fields=["estado"])

    # Proveedor configurado para devolver un presupuesto
    provider = FakeDocumentVerificationPort(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud.pk,
            referencia_documental="uuid-presupuesto-1",
            tipo_documento="presupuesto",
        )
    )

    with pytest.raises(DocumentVerificationError, match="tipo no admitido para la modalidad"):
        registrar_pago_externo(
            actor=pagador,
            solicitud_id=solicitud.pk,
            document_provider=provider,
            importe=Decimal("5000.00"),
            fecha_pago=date(2026, 11, 3),
            referencia_externa="TRF-REINT-001",
            referencia_documental="uuid-presupuesto-1",
        )

    # Verificar que al proveedor se le exigió exclusivamente ('factura',)
    assert provider.llamadas[0]["tipos_admitidos"] == ("factura",)
    assert not PagoExterno.objects.filter(solicitud=solicitud).exists()


def test_reintegro_admite_pago_con_factura_proveedor_gast_r03(
    create_actor: Any,
    actor_factory: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """GAST-R03: En REINTEGRO, el pago con factura fiscal de proveedor se registra con éxito."""
    _, solicitante = create_actor("solic_reintegro_ok", ["gastos.presentar"])
    _, pagador = actor_factory(["gastos.registrar_pago", "gastos.consultar_todas"])

    solicitud = crear_solicitud_gasto(
        actor=solicitante,
        concepto="Reintegro por combustible para viaje académico",
        monto_estimado=Decimal("18000.00"),
        unidad_requirente="Cátedra Vías de Comunicación",
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
    )
    solicitud.estado = EstadoSolicitud.ACEPTADA
    solicitud.save(update_fields=["estado"])

    provider = FakeDocumentVerificationPort(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud.pk,
            referencia_documental="uuid-factura-1",
            tipo_documento="factura",
        )
    )

    pago = registrar_pago_externo(
        actor=pagador,
        solicitud_id=solicitud.pk,
        document_provider=provider,
        importe=Decimal("18000.00"),
        fecha_pago=date(2026, 11, 3),
        referencia_externa="TRF-REINT-002",
        referencia_documental="uuid-factura-1",
    )

    assert pago.pk is not None
    assert pago.solicitud == solicitud
    assert pago.importe == Decimal("18000.00")
    assert provider.llamadas[0]["tipos_admitidos"] == ("factura",)


def test_compra_directa_admite_presupuesto_y_factura(
    create_actor: Any,
    actor_factory: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """En COMPRA_DIRECTA se admite tanto presupuesto como factura para pagar."""
    _, solicitante = create_actor("solic_directa", ["gastos.presentar"])
    _, pagador = actor_factory(["gastos.registrar_pago", "gastos.consultar_todas"])

    # 1. Pago con presupuesto
    solicitud_pres = crear_solicitud_gasto(
        actor=solicitante,
        concepto="Compra de equipamiento con presupuesto",
        monto_estimado=Decimal("80000.00"),
        unidad_requirente="Laboratorio Central",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
    )
    solicitud_pres.estado = EstadoSolicitud.ACEPTADA
    solicitud_pres.save(update_fields=["estado"])

    provider_pres = FakeDocumentVerificationPort(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud_pres.pk,
            referencia_documental="uuid-presupuesto-dir",
            tipo_documento="presupuesto",
        )
    )

    pago_pres = registrar_pago_externo(
        actor=pagador,
        solicitud_id=solicitud_pres.pk,
        document_provider=provider_pres,
        importe=Decimal("80000.00"),
        fecha_pago=date(2026, 11, 3),
        referencia_externa="TRF-DIR-001",
        referencia_documental="uuid-presupuesto-dir",
    )
    assert pago_pres.pk is not None
    assert "presupuesto" in provider_pres.llamadas[0]["tipos_admitidos"]
    assert "factura" in provider_pres.llamadas[0]["tipos_admitidos"]

    # 2. Pago con factura
    solicitud_fac = crear_solicitud_gasto(
        actor=solicitante,
        concepto="Compra directa con factura en mano",
        monto_estimado=Decimal("60000.00"),
        unidad_requirente="Laboratorio Central",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
    )
    solicitud_fac.estado = EstadoSolicitud.ACEPTADA
    solicitud_fac.save(update_fields=["estado"])

    provider_fac = FakeDocumentVerificationPort(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud_fac.pk,
            referencia_documental="uuid-factura-dir",
            tipo_documento="factura",
        )
    )

    pago_fac = registrar_pago_externo(
        actor=pagador,
        solicitud_id=solicitud_fac.pk,
        document_provider=provider_fac,
        importe=Decimal("60000.00"),
        fecha_pago=date(2026, 11, 3),
        referencia_externa="TRF-DIR-002",
        referencia_documental="uuid-factura-dir",
    )
    assert pago_fac.pk is not None


def test_pago_form_etiqueta_factura_o_ticket() -> None:
    """PagoExternoForm rotula opciones de factura como 'Factura o Ticket-Factura de proveedor'."""
    opcion = OpcionDocumental(
        referencia_documental="uuid-fac-rotulo",
        tipo_documento="factura",
        etiqueta="",
    )
    etiqueta = PagoExternoForm._etiqueta_opcion(opcion)
    assert etiqueta == "Factura o Ticket-Factura de proveedor"


# ---------------------------------------------------------------------------
# 5. Vistas (SolicitudGastoCreateView y SolicitudGastoDetailView)
# ---------------------------------------------------------------------------


def test_view_presentar_solicitud_con_doble_flujo_y_centro_costo(
    create_actor: Any,
    auth_client: Any,
) -> None:
    """POST a gastos:presentar persiste tipo_flujo y centro_costo correctamente."""
    user, _ = create_actor("solic_view", ["gastos.presentar"])
    client = auth_client(user)

    centro = CentroCosto.objects.create(
        codigo="lab-ensayos",
        nombre="Laboratorio de Ensayos",
        activo=True,
    )

    url = reverse("gastos:presentar")
    csrf_token = issue_csrf_credentials(client)
    response = client.post(
        url,
        data={
            "csrfmiddlewaretoken": csrf_token,
            "concepto": "Microscopio binocular",
            "monto_estimado": "75000.00",
            "unidad_requirente": "Laboratorio Central",
            "tipo_flujo": TipoFlujoGasto.REINTEGRO,
            "centro_costo": str(centro.pk),
        },
    )

    assert response.status_code == 302
    solicitud = SolicitudGasto.objects.latest("id")
    assert solicitud.concepto == "Microscopio binocular"
    assert solicitud.tipo_flujo == TipoFlujoGasto.REINTEGRO
    assert solicitud.centro_costo == centro


def test_view_detalle_muestra_tipo_flujo_y_centro_costo(
    create_actor: Any,
    auth_client: Any,
) -> None:
    """GET a gastos:detalle renderiza el badge de modalidad y el centro de costo."""
    user, _ = create_actor("solic_view_det", ["gastos.presentar"])
    client = auth_client(user)

    centro = CentroCosto.objects.create(
        codigo="secretaria-posgrado",
        nombre="Secretaría de Posgrado",
        activo=True,
    )

    solicitud = crear_gasto_sintetico(
        solicitante=user,
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
        centro_costo=centro,
    )

    url = reverse("gastos:detalle", kwargs={"pk": solicitud.pk})
    response = client.get(url)

    assert response.status_code == 200
    contenido = response.content.decode("utf-8")
    assert "Modalidad de Gasto" in contenido
    assert "Reintegro a solicitante" in contenido
    assert "Secretaría de Posgrado" in contenido
    assert "(secretaria-posgrado)" in contenido


def test_view_pagar_reintegro_no_lista_presupuesto(
    actor_factory: Any,
    auth_client: Any,
    settings: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    """Criterio #2: En solicitudes de REINTEGRO, GET /gastos/<pk>/pagar/ excluye presupuestos."""
    user, actor = actor_factory(
        ("gastos.consultar_todas", "gastos.registrar_pago", "documentos.ver_metadatos")
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    client = auth_client(user, actor)

    solicitud = crear_gasto_sintetico(
        solicitante=user,
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
        estado=EstadoSolicitud.ACEPTADA,
    )

    opciones = [
        OpcionDocumental(
            referencia_documental="ref-factura-001",
            tipo_documento="factura",
            etiqueta="Factura A-0001",
        ),
        OpcionDocumental(
            referencia_documental="ref-presupuesto-002",
            tipo_documento="presupuesto",
            etiqueta="Presupuesto Prev-002",
        ),
    ]

    class ProviderFiltrado(FakeDocumentVerificationPort):
        def listar_opciones_para_pago(
            self, *, actor: Any, gasto: Any, tipos_admitidos: Any = ()
        ) -> list[OpcionDocumental]:
            return [op for op in opciones if op.tipo_documento in tipos_admitidos]

    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = ProviderFiltrado(opciones=opciones)

    url = reverse("gastos:pagar", kwargs={"pk": solicitud.pk})
    response = client.get(url)

    assert response.status_code == 200
    form = response.context["form"]
    choices = [c[0] for c in form.fields["referencia_documental"].choices]
    assert "ref-factura-001" in choices
    assert "ref-presupuesto-002" not in choices


def test_view_presentar_solicitud_con_datos_transferencia_sincroniza_nombre_centro(
    create_actor: Any,
    auth_client: Any,
) -> None:
    """Previene colisión de centro_costo en POST: inyecta el nombre del centro en transferencia."""
    user, _ = create_actor("solic_trf_sync", ["gastos.presentar"])
    client = auth_client(user)

    centro = CentroCosto.objects.create(
        codigo="lab-electronica",
        nombre="Laboratorio de Electrónica",
        activo=True,
    )

    url = reverse("gastos:presentar")
    csrf_token = issue_csrf_credentials(client)
    response = client.post(
        url,
        data={
            "csrfmiddlewaretoken": csrf_token,
            "concepto": "Osciloscopio digital para laboratorio",
            "monto_estimado": "120000.00",
            "unidad_requirente": "Departamento de Electrónica",
            "tipo_flujo": TipoFlujoGasto.COMPRA_DIRECTA,
            "centro_costo": str(centro.pk),
            "titular_nombre": "Carlos Gómez",
            "identificacion": "20-33445566-7",
            "cbu_alias": "carlos.gomez.lab",
            "correo_comprobante": "carlos.gomez@frre.utn.edu.ar",
        },
    )

    assert response.status_code == 302
    solicitud = SolicitudGasto.objects.latest("id")
    assert solicitud.centro_costo == centro

    rev = RevisionDatosTransferencia.objects.filter(solicitud=solicitud).latest("id")
    assert rev.centro_costo == "Laboratorio de Electrónica"
    assert rev.centro_costo != str(centro.pk)


def test_crear_solicitud_gasto_con_datos_transferencia_vacios_no_falla(
    create_actor: Any,
) -> None:
    """Guardia ante diccionario de transferencia con campos vacíos: no autocompleta ni falla."""
    _, solicitante = create_actor("solic_vacio", ["gastos.presentar"])
    centro = CentroCosto.objects.create(
        codigo="depto-quimica",
        nombre="Departamento de Química",
        activo=True,
    )

    solicitud = crear_solicitud_gasto(
        actor=solicitante,
        concepto="Reactivos para laboratorio",
        monto_estimado=Decimal("45000.00"),
        unidad_requirente="Lab Química",
        centro_costo=centro,
        datos_transferencia={
            "titular_nombre": "",
            "identificacion": "",
            "cbu_alias": "",
            "correo_comprobante": "",
            "centro_costo": "",
        },
    )

    assert solicitud.pk is not None
    assert solicitud.centro_costo == centro
    assert not RevisionDatosTransferencia.objects.filter(solicitud=solicitud).exists()

