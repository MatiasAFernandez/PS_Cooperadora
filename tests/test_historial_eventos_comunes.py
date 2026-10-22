from datetime import UTC, datetime

from django.template.loader import render_to_string

from comunes.contracts import EventoHistorialDTO


def test_historial_distingue_aporte_revision_y_comprobante_externo():
    fecha = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    historial = [
        EventoHistorialDTO(
            evento_id=1,
            tramite_ref="gastos:1",
            tipo_evento="aporte_documental",
            actor_id="7",
            fecha_hora=fecha,
            estado_resultante="APORTADO",
            motivo_o_detalle="Factura sintética, versión 1.",
        ),
        EventoHistorialDTO(
            evento_id=2,
            tramite_ref="gastos:1",
            tipo_evento="revision_documental",
            actor_id="8",
            fecha_hora=fecha,
            estado_resultante="ACEPTADO",
            motivo_o_detalle="",
        ),
        EventoHistorialDTO(
            evento_id=3,
            tramite_ref="facturacion:1",
            tipo_evento="comprobante_externo_registrado",
            actor_id="9",
            fecha_hora=fecha,
            estado_resultante="REGISTRADO",
            motivo_o_detalle="Comprobante sintético.",
        ),
    ]

    contenido = render_to_string(
        "comunes/historial_eventos.html", {"historial": historial}
    )

    assert "Aporte documental" in contenido
    assert "hecho documental: APORTADO" in contenido
    assert "Revisión documental" in contenido
    assert "resultado documental: ACEPTADO" in contenido
    assert "Comprobante externo registrado" in contenido
    assert "registro del comprobante: REGISTRADO" in contenido
