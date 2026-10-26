from datetime import UTC, datetime, timedelta

import pytest
from django.template.loader import render_to_string

from comunes.contracts import EventoHistorialDTO


def test_historial_no_requiere_bibliotecas_personalizadas(settings):
    from django.template import Context, Engine

    engine = Engine(dirs=settings.TEMPLATES[0]["DIRS"], libraries={})
    contenido = engine.get_template("comunes/historial_eventos.html").render(Context({
        "historial": [EventoHistorialDTO(
            evento_id=1, tramite_ref="facturacion:1", tipo_evento="cobro_informado",
            actor_id="1", fecha_hora=datetime(2026, 10, 25, tzinfo=UTC),
            estado_resultante="PENDIENTE", motivo_o_detalle="Cobro sintético",
        )],
    }))
    assert "Último evento" in contenido
    assert "Cobro sintético" in contenido


@pytest.mark.parametrize("cantidad", [0, 1, 3, 4, 8])
def test_historial_reciente_destacado_y_anteriores_colapsados(cantidad):
    from html.parser import HTMLParser

    class HistorialParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.en_detalles = False
            self.visibles = 0
            self.ocultos = 0
            self.destacados = 0
            self.desplegables = 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "details":
                assert "open" not in attrs
                self.en_detalles = True
                self.desplegables += 1
            if tag == "li":
                if self.en_detalles:
                    self.ocultos += 1
                else:
                    self.visibles += 1
                if "history-latest" in attrs.get("class", ""):
                    assert not self.en_detalles and self.visibles == 1
                    self.destacados += 1

        def handle_endtag(self, tag):
            if tag == "details":
                self.en_detalles = False

    fecha = datetime(2026, 10, 25, 12, tzinfo=UTC)
    eventos = [
        EventoHistorialDTO(
            evento_id=i, tramite_ref="facturacion:1", tipo_evento="cobro_verificado",
            actor_id="1", fecha_hora=fecha + timedelta(seconds=i),
            estado_resultante="CONFIRMADO", motivo_o_detalle=f"Evento sintético {i} <script>",
        )
        for i in range(cantidad)
    ]
    # Entrada desordenada: la presentación no depende del orden del consumidor.
    entrada = eventos[::2] + eventos[1::2]
    original = list(entrada)
    contenido = render_to_string("comunes/historial_eventos.html", {"historial": entrada})
    assert entrada == original
    parser = HistorialParser()
    parser.feed(contenido)
    assert parser.visibles == min(cantidad, 3)
    assert parser.ocultos == max(cantidad - 3, 0)
    assert parser.destacados == min(cantidad, 1)
    assert parser.desplegables == int(cantidad > 3)
    if cantidad:
        posiciones = [contenido.index(f"Evento sintético {i} ") for i in reversed(range(cantidad))]
        assert posiciones == sorted(posiciones)
        assert "<script>" not in contenido
    else:
        assert "Sin eventos para este trámite." in contenido


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
