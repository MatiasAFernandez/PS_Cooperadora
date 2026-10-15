"""Pruebas de concurrencia real en PostgreSQL para el registro de pago externo.

Dos hilos con conexiones PostgreSQL independientes y barrera de sincronización
comptien por registrar un pago sobre la misma solicitud aceptada:
- mismo contenido: una sola fila de pago, un solo evento y el mismo pago retornado;
- contenido distinto: una sola fila de pago, un solo evento y un conflicto.
"""

from decimal import Decimal
from threading import Barrier, Thread

import pytest
from django.db import connections

from gastos.models import EventoPagoExterno, PagoExterno
from gastos.payments import PaymentConflictError, registrar_pago_externo

pytestmark = pytest.mark.django_db(transaction=True)

CAPS_PAGO = ("gastos.registrar_pago", "gastos.consultar_todas")


def _payload(**overrides):
    base = {
        "importe": Decimal("1234.56"),
        "fecha_pago": "2025-03-10",
        "referencia_externa": "TRF-0001",
        "referencia_documental": "doc-version-1",
    }
    base.update(overrides)
    return base


def _correr_en_paralelo(worker) -> list:
    resultados: list = [None, None]
    barrier = Barrier(2)

    def _envoltorio(indice: int) -> None:
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            resultados[indice] = worker(indice)
        except Exception as exc:  # noqa: BLE001 - se propaga como resultado del hilo
            resultados[indice] = exc
        finally:
            connections.close_all()

    hilos = [Thread(target=_envoltorio, args=(indice,)) for indice in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=25)
    for hilo in hilos:
        assert not hilo.is_alive(), "Un hilo quedó bloqueado."
    return resultados


def test_concurrencia_mismo_contenido_deja_una_fila_un_evento_y_mismo_pago(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)

    def worker(_indice: int) -> int:
        pago = registrar_pago_externo(
            actor=actor,
            solicitud_id=solicitud.pk,
            document_provider=fake_document_provider(),
            **_payload(),
        )
        return pago.pk

    resultados = _correr_en_paralelo(worker)

    assert all(isinstance(resultado, int) for resultado in resultados), resultados
    assert resultados[0] == resultados[1]
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert PagoExterno.objects.get().pk == resultados[0]


def test_concurrencia_contenido_distinto_deja_una_fila_un_evento_y_conflicto(
    actor_factory,
    solicitud_factory,
    fake_document_provider,
    capacidad_registrar_pago,
) -> None:
    user, actor = actor_factory(CAPS_PAGO)
    solicitud = solicitud_factory(solicitante=user)
    cargas = [
        _payload(),
        _payload(importe=Decimal("999.99"), referencia_externa="TRF-0002"),
    ]

    def worker(indice: int) -> int:
        pago = registrar_pago_externo(
            actor=actor,
            solicitud_id=solicitud.pk,
            document_provider=fake_document_provider(),
            **cargas[indice],
        )
        return pago.pk

    resultados = _correr_en_paralelo(worker)

    exitos = [resultado for resultado in resultados if isinstance(resultado, int)]
    conflictos = [
        resultado for resultado in resultados if isinstance(resultado, PaymentConflictError)
    ]
    assert len(exitos) == 1, resultados
    assert len(conflictos) == 1, resultados
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert PagoExterno.objects.get().pk == exitos[0]
