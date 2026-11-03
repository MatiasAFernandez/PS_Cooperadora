"""Pruebas integrales de parametrización y retención provincial ATP en pagos (Issue #91).

Cubre:
- GAST-R04 / GAST-R05: Parametrización y cálculo de retención ATP.
- CheckConstraint SQL `pago_externo_identidad_neto_atp` a nivel PostgreSQL / BD.
- Retrocompatibilidad estricta en registrar_pago_externo y consultar_pago_externo.
- Idempotencia y detección de conflictos (409) si cambian datos impositivos.
- Presentación en vista de pago (GET/POST) y desglose en detalle de gasto.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from gastos.contracts import DocumentoVerificado, OpcionDocumental
from gastos.models import (
    EstadoSolicitud,
    PagoExterno,
    ParametroOperativo,
)
from gastos.payments import (
    PaymentConflictError,
    PaymentInvalidInputError,
    consultar_pago_externo,
    registrar_pago_externo,
    validate_retencion_atp_input,
)
from gastos.services import (
    CLAVE_PARAMETRO_ATP_ALICUOTA,
    CLAVE_PARAMETRO_ATP_BASE,
    obtener_alicuota_atp,
    obtener_base_imponible_atp,
)
from tests.gastos.conftest import FakeDocumentVerificationPort, issue_csrf_credentials
from tests.soporte_gastos import crear_gasto_sintetico

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# 1. Parámetros operativos y cálculo sugerido
# ---------------------------------------------------------------------------


def test_calculo_sugerido_parametros_default_y_personalizados(db: Any) -> None:
    """Verifica fallbacks seguros en Python y precedencia de valores en base de datos."""
    assert obtener_base_imponible_atp() == Decimal("90000.00")
    assert obtener_alicuota_atp() == Decimal("3.50")

    ParametroOperativo.objects.create(
        clave=CLAVE_PARAMETRO_ATP_BASE,
        valor_decimal=Decimal("120000.00"),
        descripcion="Base imponible actualizada",
    )
    ParametroOperativo.objects.create(
        clave=CLAVE_PARAMETRO_ATP_ALICUOTA,
        valor_decimal=Decimal("4.00"),
        descripcion="Alícuota incrementada",
    )

    assert obtener_base_imponible_atp() == Decimal("120000.00")
    assert obtener_alicuota_atp() == Decimal("4.00")


# ---------------------------------------------------------------------------
# 2. Validación de inputs y retrocompatibilidad en registrar_pago_externo
# ---------------------------------------------------------------------------


def test_validate_retencion_atp_input_casos() -> None:
    """Valida la función pura de normalización de retención ATP."""
    # Caso neutro: sin retención ni monto_bruto especificado
    bruto, ret, ref = validate_retencion_atp_input(
        importe=Decimal("500.00"),
        monto_bruto=None,
        monto_retencion_atp=Decimal("0.00"),
    )
    assert bruto == Decimal("500.00")
    assert ret == Decimal("0.00")
    assert ref == ""

    # Caso válido con retención
    bruto, ret, ref = validate_retencion_atp_input(
        importe=Decimal("96.50"),
        monto_bruto=Decimal("100.00"),
        monto_retencion_atp=Decimal("3.50"),
        referencia_atp=" CERT-001 ",
    )
    assert bruto == Decimal("100.00")
    assert ret == Decimal("3.50")
    assert ref == "CERT-001"

    # Inconsistencia contable
    with pytest.raises(PaymentInvalidInputError, match="Inconsistencia contable"):
        validate_retencion_atp_input(
            importe=Decimal("90.00"),
            monto_bruto=Decimal("100.00"),
            monto_retencion_atp=Decimal("3.50"),
        )

    # Retención informada pero sin monto_bruto
    with pytest.raises(PaymentInvalidInputError, match="monto_bruto"):
        validate_retencion_atp_input(
            importe=Decimal("96.50"),
            monto_bruto=None,
            monto_retencion_atp=Decimal("3.50"),
        )

    # Retención negativa
    with pytest.raises(PaymentInvalidInputError, match="no puede ser negativo"):
        validate_retencion_atp_input(
            importe=Decimal("100.00"),
            monto_bruto=Decimal("100.00"),
            monto_retencion_atp=Decimal("-5.00"),
        )


def test_pago_sin_retencion_retrocompatible(
    actor_factory: Any,
    solicitud_factory: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """Llamadas preexistentes sin monto_bruto ni retención asumen monto_bruto = importe."""
    user, pagador = actor_factory(["gastos.registrar_pago", "gastos.consultar_todas"])
    solicitud = solicitud_factory(solicitante=user, estado=EstadoSolicitud.ACEPTADA)

    provider = fake_document_provider()
    pago = registrar_pago_externo(
        actor=pagador,
        solicitud_id=solicitud.pk,
        importe=Decimal("50000.00"),
        fecha_pago=date(2026, 11, 3),
        referencia_externa="TRF-SIN-ATP",
        referencia_documental="doc-version-1",
        document_provider=provider,
    )

    assert pago.importe == Decimal("50000.00")
    assert pago.monto_bruto == Decimal("50000.00")
    assert pago.monto_retencion_atp == Decimal("0.00")
    assert pago.referencia_atp == ""

    # Reenvío idéntico
    reenvio = registrar_pago_externo(
        actor=pagador,
        solicitud_id=solicitud.pk,
        importe=Decimal("50000.00"),
        fecha_pago=date(2026, 11, 3),
        referencia_externa="TRF-SIN-ATP",
        referencia_documental="doc-version-1",
        document_provider=provider,
    )
    assert reenvio.pk == pago.pk


def test_pago_con_retencion_valida_y_consulta(
    actor_factory: Any,
    solicitud_factory: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """Pago con retención de ATP Chaco se persiste y consulta con su desglose contable."""
    user, pagador = actor_factory(["gastos.registrar_pago", "gastos.consultar_todas"])
    solicitud = solicitud_factory(
        solicitante=user,
        estado=EstadoSolicitud.ACEPTADA,
        monto="100000.00",
    )

    provider = fake_document_provider()
    pago = registrar_pago_externo(
        actor=pagador,
        solicitud_id=solicitud.pk,
        importe=Decimal("96500.00"),
        monto_bruto=Decimal("100000.00"),
        monto_retencion_atp=Decimal("3500.00"),
        referencia_atp="CERT-ATP-2026-0089",
        fecha_pago=date(2026, 11, 3),
        referencia_externa="TRF-CON-ATP",
        referencia_documental="doc-version-1",
        document_provider=provider,
    )

    assert pago.importe == Decimal("96500.00")
    assert pago.monto_bruto == Decimal("100000.00")
    assert pago.monto_retencion_atp == Decimal("3500.00")
    assert pago.referencia_atp == "CERT-ATP-2026-0089"

    # Comprobación de DTO de consulta
    consulta = consultar_pago_externo(pagador, solicitud.pk)
    assert consulta is not None
    assert consulta.importe == Decimal("96500.00")
    assert consulta.monto_bruto == Decimal("100000.00")
    assert consulta.monto_retencion_atp == Decimal("3500.00")
    assert consulta.referencia_atp == "CERT-ATP-2026-0089"


def test_conflicto_idempotencia_si_cambian_datos_retencion(
    actor_factory: Any,
    solicitud_factory: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """Reenviar sobre un pago existente con datos impositivos distintos dispara 409 Conflict."""
    user, pagador = actor_factory(["gastos.registrar_pago", "gastos.consultar_todas"])
    solicitud = solicitud_factory(solicitante=user, estado=EstadoSolicitud.ACEPTADA)

    provider = fake_document_provider()
    registrar_pago_externo(
        actor=pagador,
        solicitud_id=solicitud.pk,
        importe=Decimal("96500.00"),
        monto_bruto=Decimal("100000.00"),
        monto_retencion_atp=Decimal("3500.00"),
        referencia_atp="CERT-ORIGINAL",
        fecha_pago=date(2026, 11, 3),
        referencia_externa="TRF-IDEMP",
        referencia_documental="doc-version-1",
        document_provider=provider,
    )

    with pytest.raises(PaymentConflictError, match="datos diferentes"):
        registrar_pago_externo(
            actor=pagador,
            solicitud_id=solicitud.pk,
            importe=Decimal("96500.00"),
            monto_bruto=Decimal("100000.00"),
            monto_retencion_atp=Decimal("3500.00"),
            referencia_atp="CERT-CAMBIADO",
            fecha_pago=date(2026, 11, 3),
            referencia_externa="TRF-IDEMP",
            referencia_documental="doc-version-1",
            document_provider=provider,
        )


# ---------------------------------------------------------------------------
# 3. CheckConstraint a nivel Base de Datos
# ---------------------------------------------------------------------------


def test_check_constraint_db_identidad_neto_atp(
    solicitud_factory: Any,
    db: Any,
) -> None:
    """La base de datos rechaza a nivel SQL registros que violen importe = bruto - retencion."""
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)

    with transaction.atomic():
        with pytest.raises(IntegrityError):
            PagoExterno.objects.create(
                solicitud=solicitud,
                importe=Decimal("90000.00"),
                monto_bruto=Decimal("100000.00"),
                monto_retencion_atp=Decimal("5000.00"),  # 100000 - 5000 != 90000
                moneda="ARS",
                fecha_pago=date(2026, 11, 3),
                referencia_externa="TRF-SQL-TEST",
                referencia_documental="doc-1",
                huella_idempotencia="huella-test-1",
            )


# ---------------------------------------------------------------------------
# 4. Vistas y UI (GET / POST y Detalle)
# ---------------------------------------------------------------------------


def test_vista_pago_muestra_aviso_y_calculo_sugerido_atp(
    actor_factory: Any,
    auth_client: Any,
    settings: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    """GET /gastos/<pk>/pagar/ calcula y muestra aviso preventivo ATP cuando monto >= 90.000."""
    user, actor = actor_factory(
        ("gastos.consultar_todas", "gastos.registrar_pago", "documentos.ver_metadatos")
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    client = auth_client(user, actor)

    solicitud = crear_gasto_sintetico(
        solicitante=user,
        monto_estimado=Decimal("100000.00"),
        estado=EstadoSolicitud.ACEPTADA,
    )

    opciones = [
        OpcionDocumental(
            referencia_documental="ref-doc-1",
            tipo_documento="factura",
            etiqueta="Factura A-0001",
        )
    ]
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = FakeDocumentVerificationPort(opciones=opciones)

    url = reverse("gastos:pagar", kwargs={"pk": solicitud.pk})
    response = client.get(url)

    assert response.status_code == 200
    assert response.context["aplica_atp"] is True
    assert response.context["base_imponible_atp"] == Decimal("90000.00")
    assert response.context["alicuota_atp"] == Decimal("3.50")
    assert response.context["monto_retencion_sugerido"] == Decimal("3500.00")

    contenido = response.content.decode("utf-8")
    assert "Aviso preventivo de Retención ATP Chaco" in contenido
    assert ("3,50%" in contenido or "3.50%" in contenido)
    assert ("3500,00" in contenido or "3500.00" in contenido)
    assert "Desglose Impositivo y Retención Provincial ATP" in contenido


def test_vista_pago_post_con_retencion_y_desglose_en_detalle(
    actor_factory: Any,
    auth_client: Any,
    settings: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    """POST /gastos/<pk>/pagar/ con retención registra el pago y detalle muestra el desglose."""
    user, actor = actor_factory(
        ("gastos.consultar_todas", "gastos.registrar_pago", "documentos.ver_metadatos")
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    client = auth_client(user, actor)

    solicitud = crear_gasto_sintetico(
        solicitante=user,
        monto_estimado=Decimal("150000.00"),
        estado=EstadoSolicitud.ACEPTADA,
    )

    provider = FakeDocumentVerificationPort(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud.pk,
            referencia_documental="ref-doc-atp",
            tipo_documento="factura",
        ),
        opciones=[
            OpcionDocumental(
                referencia_documental="ref-doc-atp",
                tipo_documento="factura",
                etiqueta="Factura Proveedor #1",
            )
        ],
    )
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = provider

    url_pagar = reverse("gastos:pagar", kwargs={"pk": solicitud.pk})
    csrf = issue_csrf_credentials(client)
    response = client.post(
        url_pagar,
        data={
            "csrfmiddlewaretoken": csrf,
            "importe": "144750.00",
            "monto_bruto": "150000.00",
            "monto_retencion_atp": "5250.00",
            "referencia_atp": "CERT-ATP-2026-991",
            "fecha_pago": "2026-11-03",
            "referencia_externa": "TRF-ATP-SUCCESS",
            "referencia_documental": "ref-doc-atp",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("gastos:detalle", kwargs={"pk": solicitud.pk})

    pago = PagoExterno.objects.get(solicitud=solicitud)
    assert pago.importe == Decimal("144750.00")
    assert pago.monto_bruto == Decimal("150000.00")
    assert pago.monto_retencion_atp == Decimal("5250.00")
    assert pago.referencia_atp == "CERT-ATP-2026-991"

    # Verificación en vista de detalle
    res_detalle = client.get(response.url)
    assert res_detalle.status_code == 200
    contenido_det = res_detalle.content.decode("utf-8")
    assert "Monto Bruto" in contenido_det
    assert ("150000,00 ARS" in contenido_det or "150000.00 ARS" in contenido_det)
    assert "Retención ATP Chaco" in contenido_det
    assert ("5250,00 ARS" in contenido_det or "5250.00 ARS" in contenido_det)
    assert "Cert: CERT-ATP-2026-991" in contenido_det
    assert "Neto Transferido" in contenido_det
    assert ("144750,00 ARS" in contenido_det or "144750.00 ARS" in contenido_det)
