"""Pruebas sintéticas PostgreSQL del servicio de registro de pago externo.

Cubre normalización estricta, precedencia 404/403, exigencia de estado aceptado,
separación respecto de `gastos.decidir`, invocación del puerto documental dentro
de la transacción atómica, validación exacta de la evidencia, fallo del proveedor
sin escrituras, idempotencia por contenido completo, conflicto, atomicidad de
pago+evento, consulta pura sin exposición de la referencia documental y huella
canónica no ambigua.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gastos.contracts import DocumentoVerificado, DocumentVerificationError
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno
from gastos.payments import (
    PaymentConflictError,
    PaymentExpenseNotFoundError,
    PaymentInvalidExpenseStateError,
    PaymentInvalidInputError,
    PaymentPermissionDeniedError,
    calcular_huella_pago,
    consultar_pago_externo,
    registrar_pago_externo,
    validate_payment_input,
)

pytestmark = pytest.mark.django_db(transaction=True)

CAPS_PAGO = ("gastos.registrar_pago", "gastos.consultar_todas")


def _payload(**overrides):
    base = {
        "importe": Decimal("1234.56"),
        "fecha_pago": date(2025, 3, 10),
        "referencia_externa": "TRF-0001",
        "referencia_documental": "doc-version-1",
    }
    base.update(overrides)
    return base


def _registrar(actor, solicitud, provider, **overrides) -> PagoExterno:
    return registrar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        document_provider=provider,
        **_payload(**overrides),
    )


# --------------------------------------------------------------------------- #
# Normalización estricta de importe, fecha y referencias
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("valor", [True, False, 10, 10.5, None, [], {}])
def test_importe_rechaza_tipos_no_admitidos(valor) -> None:
    with pytest.raises(PaymentInvalidInputError):
        validate_payment_input(
            importe=valor,
            fecha_pago=date(2025, 1, 1),
            referencia_externa="EXT",
            referencia_documental="DOC",
        )


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "   ",
        "abc",
        "1e3",
        "1E3",
        "1_000",
        "1,50",
        "nan",
        "NaN",
        "inf",
        "Infinity",
        "-Infinity",
        "0x10",
        "1.2.3",
        ".5",
        "5.",
        "\uff11\uff10",
        "0",
        "0.00",
        "-1",
        "1.234",
        "10000000000.00",
        "99999999999.99",
    ],
)
def test_importe_rechaza_strings_invalidos(valor) -> None:
    with pytest.raises(PaymentInvalidInputError):
        validate_payment_input(
            importe=valor,
            fecha_pago=date(2025, 1, 1),
            referencia_externa="EXT",
            referencia_documental="DOC",
        )


@pytest.mark.parametrize(
    "valor",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("0"),
        Decimal("-1"),
        Decimal("1.234"),
        Decimal("10000000000.00"),
    ],
)
def test_importe_rechaza_decimales_invalidos(valor) -> None:
    with pytest.raises(PaymentInvalidInputError):
        validate_payment_input(
            importe=valor,
            fecha_pago=date(2025, 1, 1),
            referencia_externa="EXT",
            referencia_documental="DOC",
        )


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("10"), Decimal("10.00")),
        ("10", Decimal("10.00")),
        (" 10.5 ", Decimal("10.50")),
        (Decimal("0.01"), Decimal("0.01")),
        ("9999999999.99", Decimal("9999999999.99")),
        ("+7.25", Decimal("7.25")),
    ],
)
def test_importe_valido_se_normaliza_sin_redondeo(valor, esperado) -> None:
    importe, _, _, _ = validate_payment_input(
        importe=valor,
        fecha_pago=date(2025, 1, 1),
        referencia_externa="EXT",
        referencia_documental="DOC",
    )
    assert importe == esperado
    assert importe.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "valor",
    [
        datetime(2025, 1, 1, 10, 0, 0),
        "2025-1-1",
        "2025/01/01",
        "20250101",
        "2025-W01-1",
        "2025-13-01",
        "2025-02-30",
        "",
        "ayer",
        20250101,
        True,
        None,
        Decimal("1"),
    ],
)
def test_fecha_rechaza_formatos_y_tipos_invalidos(valor) -> None:
    with pytest.raises(PaymentInvalidInputError):
        validate_payment_input(
            importe="1.00",
            fecha_pago=valor,
            referencia_externa="EXT",
            referencia_documental="DOC",
        )


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (date(2025, 1, 2), date(2025, 1, 2)),
        ("2025-01-02", date(2025, 1, 2)),
        (" 2025-01-02 ", date(2025, 1, 2)),
    ],
)
def test_fecha_valida_se_normaliza(valor, esperado) -> None:
    _, fecha, _, _ = validate_payment_input(
        importe="1.00",
        fecha_pago=valor,
        referencia_externa="EXT",
        referencia_documental="DOC",
    )
    assert fecha == esperado


def test_fecha_futura_no_se_rechaza_por_hipotesis() -> None:
    """No se inventa una regla de fecha futura: sólo se valida el formato."""
    futura = date.today() + timedelta(days=3650)
    _, fecha, _, _ = validate_payment_input(
        importe="1.00",
        fecha_pago=futura,
        referencia_externa="EXT",
        referencia_documental="DOC",
    )
    assert fecha == futura


def test_referencia_externa_se_trim_y_documental_se_preserva() -> None:
    _, _, referencia, documental = validate_payment_input(
        importe="1.00",
        fecha_pago=date(2025, 1, 1),
        referencia_externa="  EXT-9  ",
        referencia_documental="  DOC-9  ",
    )
    assert referencia == "EXT-9"
    assert documental == "  DOC-9  "


def test_registro_preserva_referencia_documental_opaca_exacta(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    """El selector de versión entrega una referencia opaca sin normalización."""
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider()
    referencia_documental = "  doc-version-1  "

    pago = _registrar(
        actor,
        solicitud,
        provider,
        referencia_documental=referencia_documental,
    )

    assert provider.llamadas[0]["referencia_documental"] == referencia_documental
    assert pago.referencia_documental == referencia_documental
    assert pago.huella_idempotencia == calcular_huella_pago(
        solicitud_id=solicitud.pk,
        importe=Decimal("1234.56"),
        moneda="ARS",
        fecha_pago=date(2025, 3, 10),
        referencia_externa="TRF-0001",
        referencia_documental=referencia_documental,
    )


@pytest.mark.parametrize("campo", ["referencia_externa", "referencia_documental"])
@pytest.mark.parametrize("valor", ["", "   ", "a\x00b", 123, None, True, object()])
def test_referencias_rechazan_tipos_y_contenidos_invalidos(campo, valor) -> None:
    kwargs = {
        "importe": "1.00",
        "fecha_pago": date(2025, 1, 1),
        "referencia_externa": "EXT",
        "referencia_documental": "DOC",
    }
    kwargs[campo] = valor
    with pytest.raises(PaymentInvalidInputError):
        validate_payment_input(**kwargs)


def test_referencias_respetan_limites_de_longitud() -> None:
    validate_payment_input(
        importe="1.00",
        fecha_pago=date(2025, 1, 1),
        referencia_externa="E" * 128,
        referencia_documental="D" * 255,
    )

    with pytest.raises(PaymentInvalidInputError):
        validate_payment_input(
            importe="1.00",
            fecha_pago=date(2025, 1, 1),
            referencia_externa="E" * 129,
            referencia_documental="D" * 255,
        )

    with pytest.raises(PaymentInvalidInputError):
        validate_payment_input(
            importe="1.00",
            fecha_pago=date(2025, 1, 1),
            referencia_externa="E" * 128,
            referencia_documental="D" * 256,
        )


# --------------------------------------------------------------------------- #
# Huella canónica
# --------------------------------------------------------------------------- #


def test_huella_canonica_determinista_y_no_ambigua() -> None:
    base = {
        "solicitud_id": 7,
        "importe": Decimal("10.00"),
        "moneda": "ARS",
        "fecha_pago": date(2025, 1, 1),
    }
    h1 = calcular_huella_pago(referencia_externa="AB", referencia_documental="C", **base)
    h2 = calcular_huella_pago(referencia_externa="AB", referencia_documental="C", **base)
    assert h1 == h2
    assert len(h1) == 64

    # Fronteras distintas no deben colisionar por concatenación ambigua.
    h3 = calcular_huella_pago(referencia_externa="A", referencia_documental="BC", **base)
    assert h3 != h1

    h4 = calcular_huella_pago(
        referencia_externa="AB",
        referencia_documental="C",
        **{**base, "importe": Decimal("10.01")},
    )
    assert h4 != h1


# --------------------------------------------------------------------------- #
# Visibilidad, permisos y estado
# --------------------------------------------------------------------------- #


def test_pago_exitoso_llama_al_proveedor_dentro_de_atomic(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider()

    with CaptureQueriesContext(connection) as ctx:
        pago = _registrar(actor, solicitud, provider)

    assert pago.pk is not None
    assert pago.solicitud_id == solicitud.pk
    assert pago.importe == Decimal("1234.56")
    assert pago.moneda == "ARS"
    assert pago.fecha_pago == date(2025, 3, 10)
    assert pago.referencia_externa == "TRF-0001"
    assert pago.referencia_documental == "doc-version-1"
    assert pago.huella_idempotencia == calcular_huella_pago(
        solicitud_id=solicitud.pk,
        importe=Decimal("1234.56"),
        moneda="ARS",
        fecha_pago=date(2025, 3, 10),
        referencia_externa="TRF-0001",
        referencia_documental="doc-version-1",
    )

    assert provider.llamado_en_atomic is True
    assert len(provider.llamadas) == 1
    assert provider.llamadas[0]["gasto_id"] == solicitud.pk
    assert provider.llamadas[0]["referencia_documental"] == "doc-version-1"
    assert provider.llamadas[0]["tipos_admitidos"] == (
        "factura",
        "presupuesto",
        "proforma",
    )
    assert any("FOR UPDATE" in query["sql"].upper() for query in ctx.captured_queries)

    assert EventoPagoExterno.objects.count() == 1
    evento = EventoPagoExterno.objects.get()
    assert evento.actor_id == actor.subject_id
    assert evento.tipo_evento == "pago_externo_registrado"
    assert evento.fecha_hora is not None


def test_gasto_no_visible_da_404_antes_que_403(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user_a, _ = actor_factory()
    solicitud = solicitud_factory(solicitante=user_a)
    _, actor_sin_capacidades = actor_factory(())
    provider = fake_document_provider()

    with pytest.raises(PaymentExpenseNotFoundError):
        _registrar(actor_sin_capacidades, solicitud, provider)

    assert provider.llamadas == []
    assert PagoExterno.objects.count() == 0


def test_gasto_ajeno_con_capacidad_propia_da_404(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user_a, _ = actor_factory()
    solicitud = solicitud_factory(solicitante=user_a)
    _, actor_b = actor_factory(("gastos.registrar_pago", "gastos.consultar_propias"))

    with pytest.raises(PaymentExpenseNotFoundError):
        _registrar(actor_b, solicitud, fake_document_provider())


def test_gasto_propio_visible_con_capacidad_propia(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(("gastos.registrar_pago", "gastos.consultar_propias"))
    solicitud = solicitud_factory(solicitante=user)

    pago = _registrar(actor, solicitud, fake_document_provider())
    assert pago.solicitud_id == solicitud.pk


def test_gasto_visible_sin_permiso_da_403(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user_a, _ = actor_factory()
    solicitud = solicitud_factory(solicitante=user_a)
    _, actor_lectura = actor_factory(("gastos.consultar_todas",))
    provider = fake_document_provider()

    with pytest.raises(PaymentPermissionDeniedError):
        _registrar(actor_lectura, solicitud, provider)

    assert provider.llamadas == []
    assert PagoExterno.objects.count() == 0


def test_decidir_no_concede_registrar_pago(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user_a, _ = actor_factory()
    solicitud = solicitud_factory(solicitante=user_a)
    _, actor_decision = actor_factory(("gastos.decidir", "gastos.consultar_todas"))
    provider = fake_document_provider()

    with pytest.raises(PaymentPermissionDeniedError):
        _registrar(actor_decision, solicitud, provider)

    assert provider.llamadas == []
    assert PagoExterno.objects.count() == 0


@pytest.mark.parametrize(
    "estado",
    [EstadoSolicitud.PRESENTADA, EstadoSolicitud.POSTERGADA, EstadoSolicitud.RECHAZADA],
)
def test_solo_gasto_aceptado_admite_pago(
    estado,
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user, estado=estado)
    provider = fake_document_provider()

    with pytest.raises(PaymentInvalidExpenseStateError):
        _registrar(actor, solicitud, provider)

    assert provider.llamadas == []
    assert PagoExterno.objects.count() == 0


# --------------------------------------------------------------------------- #
# Proveedor documental: ausencia, evidencia exacta y fallo
# --------------------------------------------------------------------------- #


def test_sin_provider_solo_se_exige_al_crear_registro_nuevo(
    actor_factory, solicitud_factory, capacidad_registrar_pago
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    with pytest.raises(PaymentInvalidInputError):
        registrar_pago_externo(actor=actor, solicitud_id=solicitud.pk, **_payload())

    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0


def test_sin_provider_no_se_exige_antes_del_404(
    actor_factory, solicitud_factory, capacidad_registrar_pago
) -> None:
    user_a, _ = actor_factory()
    solicitud = solicitud_factory(solicitante=user_a)
    _, actor_ajeno = actor_factory(())

    with pytest.raises(PaymentExpenseNotFoundError):
        registrar_pago_externo(
            actor=actor_ajeno,
            solicitud_id=solicitud.pk,
            document_provider=None,
            **_payload(),
        )


def test_sin_provider_no_se_exige_antes_del_403(
    actor_factory, solicitud_factory, capacidad_registrar_pago
) -> None:
    user_a, _ = actor_factory()
    solicitud = solicitud_factory(solicitante=user_a)
    _, actor_lectura = actor_factory(("gastos.consultar_todas",))

    with pytest.raises(PaymentPermissionDeniedError):
        registrar_pago_externo(
            actor=actor_lectura,
            solicitud_id=solicitud.pk,
            document_provider=None,
            **_payload(),
        )


def test_sin_provider_no_se_exige_antes_del_estado(
    actor_factory, solicitud_factory, capacidad_registrar_pago
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user, estado=EstadoSolicitud.PRESENTADA)

    with pytest.raises(PaymentInvalidExpenseStateError):
        registrar_pago_externo(
            actor=actor,
            solicitud_id=solicitud.pk,
            document_provider=None,
            **_payload(),
        )


def test_evidencia_con_gasto_distinto_es_rechazada(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud.pk + 1,
            referencia_documental="doc-version-1",
            tipo_documento="factura",
        )
    )

    with pytest.raises(DocumentVerificationError):
        _registrar(actor, solicitud, provider)

    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0


def test_evidencia_con_referencia_distinta_es_rechazada(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud.pk,
            referencia_documental="doc-version-OTRA",
            tipo_documento="factura",
        )
    )

    with pytest.raises(DocumentVerificationError):
        _registrar(actor, solicitud, provider)

    assert PagoExterno.objects.count() == 0


def test_evidencia_con_tipo_no_admitido_es_rechazada(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider(
        resultado=DocumentoVerificado(
            solicitud_id=solicitud.pk,
            referencia_documental="doc-version-1",
            tipo_documento="informe_interno",
        )
    )

    with pytest.raises(DocumentVerificationError):
        _registrar(actor, solicitud, provider)

    assert PagoExterno.objects.count() == 0


def test_fallo_del_proveedor_no_deja_escrituras(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider(
        error=DocumentVerificationError("La versión documental no existe.")
    )

    with pytest.raises(DocumentVerificationError):
        _registrar(actor, solicitud, provider)

    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0


def test_aliasing_gasto_id_de_la_evidencia() -> None:
    evidencia = DocumentoVerificado(
        solicitud_id=42, referencia_documental="doc-1", tipo_documento="factura"
    )
    assert evidencia.solicitud_id == 42
    assert evidencia.gasto_id == 42


# --------------------------------------------------------------------------- #
# Idempotencia, conflicto y atomicidad
# --------------------------------------------------------------------------- #


def test_reenvio_identico_retorna_mismo_pago_sin_evento_nuevo(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider()

    primero = _registrar(actor, solicitud, provider)
    segundo = _registrar(actor, solicitud, provider)

    assert primero.pk == segundo.pk
    assert len(provider.llamadas) == 1
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1


def test_reenvio_identico_no_reconsulta_documento_ni_provider(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider()

    primero = _registrar(actor, solicitud, provider)
    segundo = registrar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        document_provider=None,
        **_payload(),
    )

    assert segundo.pk == primero.pk
    assert len(provider.llamadas) == 1
    assert EventoPagoExterno.objects.count() == 1


def test_contenido_distinto_genera_conflicto(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    provider = fake_document_provider()

    pago = _registrar(actor, solicitud, provider)
    with pytest.raises(PaymentConflictError):
        _registrar(actor, solicitud, provider, importe=Decimal("50.00"))

    assert len(provider.llamadas) == 1
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    pago.refresh_from_db()
    assert pago.importe == Decimal("1234.56")


def test_huella_igual_pero_campo_distinto_no_es_idempotente(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    """El hash no reemplaza la comparación de todos los campos normalizados."""
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    huella = calcular_huella_pago(
        solicitud_id=solicitud.pk,
        importe=Decimal("1234.56"),
        moneda="ARS",
        fecha_pago=date(2025, 3, 10),
        referencia_externa="TRF-0001",
        referencia_documental="doc-version-1",
    )
    PagoExterno.objects.create(
        solicitud=solicitud,
        importe=Decimal("1234.56"),
        moneda="ARS",
        fecha_pago=date(2025, 3, 10),
        referencia_externa="TRF-ALTERADA",
        referencia_documental="doc-version-1",
        huella_idempotencia=huella,
    )
    provider = fake_document_provider()

    with pytest.raises(PaymentConflictError):
        _registrar(actor, solicitud, provider)

    assert provider.llamadas == []
    assert PagoExterno.objects.count() == 1


def test_rollback_completo_si_falla_la_creacion_del_evento(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    with patch(
        "gastos.payments.EventoPagoExterno.objects.create",
        side_effect=RuntimeError("Fallo simulado al crear el evento"),
    ):
        with pytest.raises(RuntimeError, match="Fallo simulado al crear el evento"):
            _registrar(actor, solicitud, fake_document_provider())

    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0


# --------------------------------------------------------------------------- #
# Consulta pura
# --------------------------------------------------------------------------- #


def test_consulta_pura_omite_referencia_documental(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    _registrar(actor, solicitud, fake_document_provider())

    consulta = consultar_pago_externo(actor, solicitud.pk)

    assert consulta is not None
    assert consulta.solicitud_id == solicitud.pk
    assert consulta.importe == Decimal("1234.56")
    assert consulta.moneda == "ARS"
    assert consulta.fecha_pago == date(2025, 3, 10)
    assert consulta.referencia_externa == "TRF-0001"
    assert consulta.actor_id == actor.subject_id
    assert consulta.fecha_registro is not None
    assert not hasattr(consulta, "referencia_documental")

    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1


def test_consulta_no_visible_retorna_none(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    _registrar(actor, solicitud, fake_document_provider())
    _, actor_ajeno = actor_factory(())

    assert consultar_pago_externo(actor_ajeno, solicitud.pk) is None
    assert consultar_pago_externo(None, solicitud.pk) is None


def test_consulta_sin_pago_retorna_none(
    actor_factory, solicitud_factory, capacidad_registrar_pago
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    assert consultar_pago_externo(actor, solicitud.pk) is None
