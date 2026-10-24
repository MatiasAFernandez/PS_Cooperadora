from datetime import UTC, datetime

from django.template.loader import render_to_string

from comunes.contracts import EventoHistorialDTO


def test_historial_distingue_eventos_documentales_comprobante_y_cobros():
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
        EventoHistorialDTO(
            evento_id=4,
            tramite_ref="facturacion:2",
            tipo_evento="cobro_informado",
            actor_id="10",
            fecha_hora=fecha,
            estado_resultante="PENDIENTE",
            motivo_o_detalle="Cobro sintético informado.",
        ),
        EventoHistorialDTO(
            evento_id=5,
            tramite_ref="facturacion:2",
            tipo_evento="cobro_verificado",
            actor_id="11",
            fecha_hora=fecha,
            estado_resultante="CONFIRMADO",
            motivo_o_detalle="Verificación sintética.",
        ),
        EventoHistorialDTO(
            evento_id=6,
            tramite_ref="facturacion:2",
            tipo_evento="actualizacion_respaldo",
            actor_id="12",
            fecha_hora=fecha,
            estado_resultante="ACTUALIZADO",
            motivo_o_detalle="Comprobante #3. Respaldo #1 → #2. Corrección sintética.",
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
    assert "Cobro externo informado" in contenido
    assert "verificación del ingreso: PENDIENTE" in contenido
    assert "Ingreso verificado" in contenido
    assert "verificación del ingreso: CONFIRMADO" in contenido
    assert "Vínculo documental actualizado" in contenido
    assert "vínculo documental: ACTUALIZADO" in contenido
