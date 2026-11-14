"""Pruebas focalizadas de plantillas texto/HTML para correos de decisión de Gastos."""

from datetime import UTC, datetime
from decimal import Decimal

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings
from django.utils import timezone

from avisos.correo import _construir_mensaje
from avisos.models import Aviso, TipoAviso
from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto


def _solicitud_sintetica(
    *,
    numero: int = 42,
    estado_actual: str = EstadoSolicitud.ACEPTADA,
) -> SolicitudGasto:
    return SolicitudGasto(
        pk=numero,
        concepto="Compra confidencial de equipamiento",
        monto_estimado=Decimal("234567.89"),
        unidad_requirente="Laboratorio CBU 2850590940090418135201",
        estado=estado_actual,
        fecha_creacion=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    )


def _decision_sintetica(
    solicitud: SolicitudGasto,
    *,
    estado_resultante: str = EstadoSolicitud.POSTERGADA,
    fecha: datetime | None = None,
) -> DecisionGasto:
    decision = DecisionGasto(
        pk=501,
        solicitud=solicitud,
        solicitud_id=solicitud.pk,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=estado_resultante,
        motivo="Motivo confidencial de la decisión",
    )
    decision.fecha = fecha or datetime(2026, 11, 14, 2, 15, tzinfo=UTC)
    return decision


@override_settings(
    TIME_ZONE="America/Argentina/Buenos_Aires",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_correo_decision_usa_evento_historico_y_excluye_datos_sensibles():
    solicitud = _solicitud_sintetica(
        numero=42,
        estado_actual=EstadoSolicitud.ACEPTADA,
    )
    decision = _decision_sintetica(
        solicitud,
        estado_resultante=EstadoSolicitud.POSTERGADA,
        fecha=datetime(2026, 11, 14, 2, 15, tzinfo=UTC),
    )
    aviso = Aviso(
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
        decision_id=decision.pk,
    )
    enlace = "http://127.0.0.1:8000/gastos/42/"

    with timezone.override("America/Argentina/Buenos_Aires"):
        mensaje = _construir_mensaje(
            solicitud=solicitud,
            enlace=enlace,
            remitente="avisos@sintetico.test",
            destinatario_email="titular@sintetico.test",
            aviso=aviso,
            decision=decision,
        )

    assert isinstance(mensaje, EmailMultiAlternatives)
    assert mensaje.subject == "[PS_Cooperadora] Decisión sobre solicitud de gasto #42"
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
        assert "Postergada" in contenido
        assert "El 13/11/2026 23:15 se registró la decisión Postergada" in contenido
        assert "Aceptada" not in contenido
        assert "Ver solicitud" in contenido
        assert enlace in contenido

    datos_prohibidos = (
        "Motivo confidencial",
        "Compra confidencial",
        "234567",
        "234.567",
        "2850590940090418135201",
        "CBU",
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
def test_correo_decision_respeta_timezone_utc():
    solicitud = _solicitud_sintetica(numero=77, estado_actual=EstadoSolicitud.RECHAZADA)
    decision = _decision_sintetica(
        solicitud,
        estado_resultante=EstadoSolicitud.RECHAZADA,
        fecha=datetime(2026, 11, 14, 2, 15, tzinfo=UTC),
    )
    aviso = Aviso(
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
        decision_id=decision.pk,
    )

    with timezone.override("UTC"):
        mensaje = _construir_mensaje(
            solicitud=solicitud,
            enlace="https://cooperadora.sintetico.test/gastos/77/",
            remitente="avisos@sintetico.test",
            destinatario_email="titular@sintetico.test",
            aviso=aviso,
            decision=decision,
        )

    html, _ = mensaje.alternatives[0]
    assert "14/11/2026 02:15" in mensaje.body
    assert "14/11/2026 02:15" in html
