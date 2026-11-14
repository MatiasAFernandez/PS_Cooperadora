"""Pruebas focalizadas de plantillas texto/HTML para correos de pago externo (SPEC-031)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings
from django.utils import timezone

from avisos.correo import _construir_mensaje
from avisos.models import Aviso, TipoAviso
from gastos.models import (
    EstadoSolicitud,
    EventoPagoExterno,
    PagoExterno,
    SolicitudGasto,
)


def _solicitud_sintetica(*, numero: int = 42) -> SolicitudGasto:
    return SolicitudGasto(
        pk=numero,
        concepto="Compra confidencial de equipamiento",
        monto_estimado=Decimal("234567.89"),
        unidad_requirente="Laboratorio reservado",
        estado=EstadoSolicitud.ACEPTADA,
        fecha_creacion=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    )


def _evento_pago_sintetico(
    solicitud: SolicitudGasto,
    *,
    fecha_evento: datetime | None = None,
    fecha_pago: date = date(2026, 11, 20),
) -> EventoPagoExterno:
    pago = PagoExterno(
        pk=801,
        solicitud=solicitud,
        solicitud_id=solicitud.pk,
        importe=Decimal("145500.00"),
        monto_bruto=Decimal("150000.00"),
        monto_retencion_atp=Decimal("4500.00"),
        referencia_atp="ATP-CERT-4455",
        moneda="ARS",
        fecha_pago=fecha_pago,
        referencia_externa="REF-BANCARIA-7788",
        referencia_documental="doc-ref-801",
        version=1,
        huella_idempotencia="0" * 64,
    )
    evento = EventoPagoExterno(
        pk=901,
        pago=pago,
        pago_id=pago.pk,
        tipo_evento="pago_externo_registrado",
    )
    evento.fecha_hora = fecha_evento or datetime(2026, 11, 14, 2, 15, tzinfo=UTC)
    return evento


@override_settings(
    TIME_ZONE="America/Argentina/Buenos_Aires",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_correo_pago_usa_fecha_inmutable_evento_y_excluye_datos_sensibles():
    solicitud = _solicitud_sintetica(numero=42)
    evento = _evento_pago_sintetico(
        solicitud,
        fecha_evento=datetime(2026, 11, 14, 2, 15, tzinfo=UTC),
        fecha_pago=date(2026, 11, 20),
    )
    # Simular estado posterior tras rectificación de fecha_pago, importes y referencia
    evento.pago.fecha_pago = date(2026, 11, 28)
    evento.pago.monto_bruto = Decimal("199999.00")
    evento.pago.importe = Decimal("195499.00")
    evento.pago.referencia_externa = "REF-RECTIFICADA-9999"
    evento.pago.referencia_atp = "ATP-RECTIFICADA-8888"
    evento.pago.version = 2

    aviso = Aviso(
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=solicitud.pk,
        evento_pago_id=evento.pk,
    )
    enlace = "http://127.0.0.1:8000/gastos/42/"

    with timezone.override("America/Argentina/Buenos_Aires"):
        mensaje = _construir_mensaje(
            solicitud=solicitud,
            enlace=enlace,
            remitente="avisos@sintetico.test",
            destinatario_email="titular@sintetico.test",
            aviso=aviso,
            evento_pago=evento,
        )

    assert isinstance(mensaje, EmailMultiAlternatives)
    assert (
        mensaje.subject
        == "[PS_Cooperadora] Registro de pago externo de solicitud de gasto #42"
    )
    assert mensaje.to == ["titular@sintetico.test"]
    assert mensaje.cc == []
    assert mensaje.bcc == []
    assert mensaje.attachments == []

    assert mensaje.send() == 1
    assert len(mail.outbox) == 1
    enviado = mail.outbox[0]
    assert len(enviado.alternatives) == 1
    html, mimetype = enviado.alternatives[0]
    assert mimetype == "text/html"

    for contenido in (enviado.body, html):
        assert "#42" in contenido
        assert "13/11/2026 23:15" in contenido
        assert "El 13/11/2026 23:15 se registró un pago externo para la solicitud #42." in contenido
        assert "Ver solicitud" in contenido
        assert enlace in contenido

    datos_prohibidos = (
        "20/11/2026",
        "28/11/2026",
        "Compra confidencial",
        "Laboratorio reservado",
        "150000",
        "150.000",
        "199999",
        "199.999",
        "195499",
        "195.499",
        "145500",
        "145.500",
        "4500",
        "4.500",
        "234567",
        "REF-BANCARIA-7788",
        "REF-RECTIFICADA-9999",
        "ATP-CERT-4455",
        "ATP-RECTIFICADA-8888",
        "doc-ref-801",
    )
    for contenido in (enviado.body, html):
        for dato in datos_prohibidos:
            assert dato not in contenido

    assert f'href="{enlace}"' in html
    assert f">{enlace}<" in html
    html_lower = html.lower()
    for etiqueta in ("<img", "<script", "<link", "@import", "url(http"):
        assert etiqueta not in html_lower


@override_settings(TIME_ZONE="UTC")
def test_correo_pago_respeta_timezone_utc():
    solicitud = _solicitud_sintetica(numero=77)
    evento = _evento_pago_sintetico(
        solicitud,
        fecha_evento=datetime(2026, 11, 14, 2, 15, tzinfo=UTC),
    )
    aviso = Aviso(
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=solicitud.pk,
        evento_pago_id=evento.pk,
    )

    with timezone.override("UTC"):
        mensaje = _construir_mensaje(
            solicitud=solicitud,
            enlace="https://cooperadora.sintetico.test/gastos/77/",
            remitente="avisos@sintetico.test",
            destinatario_email="titular@sintetico.test",
            aviso=aviso,
            evento_pago=evento,
        )

    html, _ = mensaje.alternatives[0]
    assert "14/11/2026 02:15" in mensaje.body
    assert "14/11/2026 02:15" in html
