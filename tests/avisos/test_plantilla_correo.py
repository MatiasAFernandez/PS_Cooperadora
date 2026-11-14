"""Pruebas focalizadas de la plantilla y construcción del correo de nueva solicitud."""

from datetime import UTC, datetime
from decimal import Decimal

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings
from django.utils import timezone

from avisos.correo import _construir_mensaje
from gastos.models import EstadoSolicitud, SolicitudGasto


def _solicitud_sintetica(
    *, numero: int = 42, fecha_creacion: datetime | None = None
) -> SolicitudGasto:
    return SolicitudGasto(
        pk=numero,
        concepto="Compra confidencial de laboratorio",
        monto_estimado=Decimal("123456.78"),
        unidad_requirente="Laboratorio CBU 2850590940090418135201",
        estado=EstadoSolicitud.PRESENTADA,
        fecha_creacion=fecha_creacion or datetime(2026, 11, 14, 15, 30, tzinfo=UTC),
    )


@override_settings(
    TIME_ZONE="America/Argentina/Buenos_Aires",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_construir_mensaje_y_salida_locmem_texto_html_y_asunto_exacto():
    solicitud = _solicitud_sintetica(
        numero=42,
        fecha_creacion=datetime(2026, 11, 14, 2, 15, tzinfo=UTC),
    )
    enlace = "http://127.0.0.1:8000/gastos/42/"

    with timezone.override("America/Argentina/Buenos_Aires"):
        mensaje = _construir_mensaje(
            solicitud=solicitud,
            enlace=enlace,
            remitente="avisos@sintetico.test",
            destinatario_email="operadora@sintetico.test",
        )

    assert isinstance(mensaje, EmailMultiAlternatives)
    assert mensaje.subject == "[PS_Cooperadora] Nueva solicitud de gasto #42"
    assert mensaje.to == ["operadora@sintetico.test"]
    assert mensaje.cc == []
    assert mensaje.bcc == []
    assert mensaje.attachments == []

    enviados = mensaje.send()
    assert enviados == 1
    assert len(mail.outbox) == 1

    enviado = mail.outbox[0]
    assert enviado.subject == "[PS_Cooperadora] Nueva solicitud de gasto #42"
    assert enviado.to == ["operadora@sintetico.test"]
    assert enviado.cc == []
    assert enviado.bcc == []
    assert enviado.attachments == []
    assert len(enviado.alternatives) == 1

    html, mimetype = enviado.alternatives[0]
    assert mimetype == "text/html"

    for contenido in (enviado.body, html):
        assert "#42" in contenido
        assert "13/11/2026 23:15" in contenido
        assert enlace in contenido
        assert "Ver solicitud" in contenido


@override_settings(TIME_ZONE="UTC")
def test_construir_mensaje_respeta_timezone_app_con_override():
    solicitud = _solicitud_sintetica(
        numero=77,
        fecha_creacion=datetime(2026, 11, 14, 2, 15, tzinfo=UTC),
    )

    with timezone.override("UTC"):
        mensaje = _construir_mensaje(
            solicitud=solicitud,
            enlace="https://cooperadora.sintetico.test/gastos/77/",
            remitente="avisos@sintetico.test",
            destinatario_email="operadora@sintetico.test",
        )

    html, _ = mensaje.alternatives[0]
    assert "14/11/2026 02:15" in mensaje.body
    assert "14/11/2026 02:15" in html


@override_settings(TIME_ZONE="America/Argentina/Buenos_Aires")
def test_construir_mensaje_solo_datos_minimos_y_sin_recursos_remotos():
    solicitud = _solicitud_sintetica(numero=99)
    enlace = "http://localhost:8080/gastos/99/"

    with timezone.override("America/Argentina/Buenos_Aires"):
        mensaje = _construir_mensaje(
            solicitud=solicitud,
            enlace=enlace,
            remitente="avisos@sintetico.test",
            destinatario_email="operadora@sintetico.test",
        )

    html, mimetype = mensaje.alternatives[0]
    assert mimetype == "text/html"
    assert enlace in mensaje.body
    assert f'href="{enlace}"' in html
    assert f">{enlace}<" in html

    datos_prohibidos = (
        "Compra confidencial",
        "laboratorio",
        "123456",
        "123.456",
        "2850590940090418135201",
        "CBU",
    )
    for contenido in (mensaje.body, html):
        for dato in datos_prohibidos:
            assert dato not in contenido

    html_lower = html.lower()
    for etiqueta_prohibida in ("<img", "<script", "<link", "@import", "url(http"):
        assert etiqueta_prohibida not in html_lower
