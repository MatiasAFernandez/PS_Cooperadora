"""Pruebas de concurrencia real y atomicidad transaccional en PostgreSQL.

Cubre:
- T04-21: Concurrencia simultánea real en PostgreSQL utilizando dos hilos
  (threading.Thread), conexiones PostgreSQL independientes (connections.close_all())
  y barrera de sincronización (threading.Barrier).
  Exactamente un hilo tiene éxito (HTTP 302) y el otro recibe conflicto (HTTP 409).
- T04-22: Reversión atómica ante fallo al guardar evento de decisión (rollback total).
"""

from decimal import Decimal
from threading import Barrier, Thread
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client
from django.urls import reverse

from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto
from gastos.services import decide_expense
from identidad.services import Actor

User = get_user_model()


@pytest.mark.django_db(transaction=True)
def test_t04_21_concurrencia_simultanea_real_postgresql(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-21: Concurrencia simultánea real en PostgreSQL.

    Dos hilos con conexiones y transacciones independientes en PostgreSQL intentan
    decidir simultáneamente sobre la misma solicitud en v=0 con barrera de sincronización.
    Exactamente 1 hilo confirma transacción (HTTP 302, v=1).
    El segundo hilo recibe HTTP 409 Conflict.
    En BD se registra exactamente 1 evento y la versión avanza a 1.
    """
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]

    solicitud = SolicitudGasto.objects.create(
        concepto="Servidor de cómputo para cálculo numérico",
        monto_estimado=Decimal("85000.00"),
        unidad_requirente="Cálculo Científico",
        solicitante=user_a,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    url = reverse("gastos:decidir", kwargs={"pk": solicitud.pk})
    barrier = Barrier(2)
    results: list[int | Exception | None] = [None, None]

    def worker(worker_index: int) -> None:
        # Forzar conexión independiente a PostgreSQL para cada hilo
        connections.close_all()
        try:
            client = Client()
            client.force_login(user_o)

            # Sincronización exacta de ambos hilos antes del POST
            barrier.wait(timeout=10)

            response = client.post(
                url,
                {
                    "action": "aceptar",
                    "version": "0",
                    "motivo": f"Aprobación concurrente hilo {worker_index}",
                },
            )
            results[worker_index] = response.status_code
        except Exception as exc:
            results[worker_index] = exc
        finally:
            connections.close_all()

    thread_1 = Thread(target=worker, args=(0,))
    thread_2 = Thread(target=worker, args=(1,))

    thread_1.start()
    thread_2.start()

    thread_1.join(timeout=15)
    thread_2.join(timeout=15)

    # Verificar que ambos hilos terminaron
    assert not thread_1.is_alive(), "El hilo 1 quedó bloqueado."
    assert not thread_2.is_alive(), "El hilo 2 quedó bloqueado."

    # Los resultados deben ser exactamente un 302 (éxito) y un 409 (conflicto de concurrencia)
    status_codes = sorted([r for r in results if isinstance(r, int)])
    assert status_codes == [302, 409], f"Resultados inesperados de concurrencia: {results}"

    # Verificación en base de datos: avance único de versión y un único evento
    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.ACEPTADA
    assert solicitud.version == 1

    decisiones = solicitud.decisiones.all()
    assert decisiones.count() == 1
    assert decisiones.first().autor == user_o


@pytest.mark.django_db(transaction=True)
def test_t04_22_reversion_atomica_ante_fallo_guardar_evento(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    """T04-22: Reversión atómica ante fallo al guardar evento.

    Se simula una excepción en la inserción de DecisionGasto dentro de la transacción.
    La transacción completa hace rollback: solicitud conserva estado="presentada",
    version=0 y 0 registros en DecisionGasto.
    """
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]

    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos con fallo de auditoría",
        monto_estimado=Decimal("15000.00"),
        unidad_requirente="Laboratorio Central",
        solicitante=user_a,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )

    actor_o = Actor(
        subject_id=user_o.pk,
        capabilities=frozenset({"gastos.decidir", "gastos.consultar_todas"}),
    )

    # Simular fallo durante la creación del registro histórico DecisionGasto
    with patch(
        "gastos.services.DecisionGasto.objects.create",
        side_effect=RuntimeError("Fallo simulado en BD"),
    ):
        with pytest.raises(RuntimeError, match="Fallo simulado en BD"):
            decide_expense(
                actor=actor_o,
                solicitud_id=solicitud.pk,
                action="aceptar",
                expected_version=0,
                motivo="Aprobación que debe fallar",
            )

    # Verificar que el rollback restableció completamente el estado
    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert DecisionGasto.objects.count() == 0
