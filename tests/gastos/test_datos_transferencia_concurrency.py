"""Serialización real entre corrección de datos y registro de pago (SPEC-013).

Ambas operaciones bloquean la misma fila de ``SolicitudGasto``. Si la
corrección gana el bloqueo, la revisión queda como actual antes del pago; si el
pago confirma primero, la corrección no escribe y devuelve el bloqueo.
"""

from decimal import Decimal
from threading import Barrier, Thread

import pytest
from django.db import connections

from gastos.datos_transferencia import (
    DatosTransferenciaBloqueadaError,
    registrar_revision_datos_transferencia,
)
from gastos.models import PagoExterno, RevisionDatosTransferencia
from gastos.payments import registrar_pago_externo
from tests.soporte_gastos import crear_gasto_sintetico

pytestmark = pytest.mark.django_db(transaction=True)

DATOS = {
    "titular_nombre": "Titular Concurrente Sintetico",
    "identificacion": "ID-CONC-741",
    "cbu_alias": "ALIAS.CONC.741",
    "correo_comprobante": "correo.conc.741@example.test",
    "centro_costo": "CC-CONC-741",
}


def test_concurrencia_correccion_y_pago_serializa_sobre_el_gasto(
    actor_factory, fake_document_provider
) -> None:
    titular, titular_actor = actor_factory(
        ("gastos.presentar", "gastos.consultar_propias")
    )
    _, pago_actor = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )
    gasto = crear_gasto_sintetico(
        concepto="Gasto concurrente de transferencia",
        monto_estimado=Decimal("2500.00"),
        unidad_requirente="Unidad concurrente",
        solicitante=titular,
        estado="aceptada",
    )

    barrera = Barrier(2)
    resultados: dict[str, object] = {}

    def corregir() -> None:
        connections.close_all()
        try:
            barrera.wait(timeout=10)
            resultados["correccion"] = registrar_revision_datos_transferencia(
                actor=titular_actor,
                solicitud_id=gasto.pk,
                datos=DATOS,
            )
        except Exception as exc:  # noqa: BLE001 - se evalúa como resultado del hilo
            resultados["correccion"] = exc
        finally:
            connections.close_all()

    def pagar() -> None:
        connections.close_all()
        try:
            barrera.wait(timeout=10)
            resultados["pago"] = registrar_pago_externo(
                actor=pago_actor,
                solicitud_id=gasto.pk,
                importe="1234.56",
                fecha_pago="2026-10-27",
                referencia_externa="TRF-CONC-74",
                referencia_documental="doc-conc-74",
                document_provider=fake_document_provider(),
            )
        except Exception as exc:  # noqa: BLE001 - se evalúa como resultado del hilo
            resultados["pago"] = exc
        finally:
            connections.close_all()

    hilos = [Thread(target=corregir), Thread(target=pagar)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=25)
    for hilo in hilos:
        assert not hilo.is_alive(), "Un hilo quedó bloqueado."

    assert isinstance(resultados.get("pago"), PagoExterno), resultados
    assert PagoExterno.objects.filter(solicitud_id=gasto.pk).count() == 1

    revisiones = list(
        RevisionDatosTransferencia.objects.filter(solicitud_id=gasto.pk).order_by(
            "numero_revision"
        )
    )
    resultado_correccion = resultados.get("correccion")
    if isinstance(resultado_correccion, RevisionDatosTransferencia):
        assert len(revisiones) == 1
        assert revisiones[0].numero_revision == 1
        assert revisiones[0].titular_nombre == DATOS["titular_nombre"]
    else:
        assert isinstance(resultado_correccion, DatosTransferenciaBloqueadaError), (
            resultados
        )
        assert revisiones == []

    # El pago no depende de los datos de destino y no modifica su contenido.
    pago = PagoExterno.objects.get(solicitud_id=gasto.pk)
    assert pago.importe == Decimal("1234.56")
