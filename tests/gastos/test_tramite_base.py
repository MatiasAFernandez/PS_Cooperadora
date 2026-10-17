"""Vínculo directo, alta atómica y defensa de identidad en PostgreSQL."""

from decimal import Decimal
from threading import Barrier, Thread
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, connection, connections, transaction
from django.db.models import ProtectedError

from comunes.models import Circuito, TramiteBase
from comunes.services import registrar_cabecera_gasto
from facturacion.models import SolicitudFacturacion
from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto
from gastos.services import crear_solicitud_gasto
from tests.soporte_gastos import (
    crear_gasto_sintetico,
    reservar_numero_solicitud_gasto,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


def _base(numero: int, titular_id: int, circuito: str = Circuito.GASTO) -> TramiteBase:
    return TramiteBase.objects.create(
        circuito=circuito,
        numero_publico=numero,
        solicitante_actor_id=str(titular_id),
        centro_costo_codigo=None,
    )


def test_servicio_crea_cabecera_y_solicitud_consistentes(actor_factory: Any) -> None:
    """El alta reserva el número y fija titular, estado, versión y centro NULL."""
    user, actor = actor_factory(["gastos.presentar"])

    solicitud = crear_solicitud_gasto(
        actor=actor,
        concepto="Compra sintética",
        monto_estimado=Decimal("250.00"),
        unidad_requirente="Unidad que no es centro de costo",
    )

    base = TramiteBase.objects.get()
    assert solicitud.pk == base.numero_publico
    assert solicitud.tramite_base_id == base.pk
    assert base.circuito == Circuito.GASTO
    assert base.solicitante_actor_id == str(user.pk)
    assert base.centro_costo_codigo is None
    assert solicitud.solicitante_id == user.pk
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert TramiteBase.objects.count() == 1


def test_servicio_rechaza_actor_sin_capacidad(actor_factory: Any) -> None:
    """La capacidad gastos.presentar se revalida dentro del servicio."""
    _, actor = actor_factory(["gastos.consultar_propias"])

    with pytest.raises(PermissionDenied):
        crear_solicitud_gasto(
            actor=actor,
            concepto="Intento sin permiso",
            monto_estimado=Decimal("1.00"),
            unidad_requirente="Unidad",
        )

    assert not SolicitudGasto.objects.exists()
    assert not TramiteBase.objects.exists()


def test_servicio_revierte_cabecera_si_falla_el_gasto(
    actor_factory: Any, monkeypatch: Any
) -> None:
    """La cabecera y la solicitud comparten la misma transacción atómica."""
    _, actor = actor_factory(["gastos.presentar"])

    def fallo(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("fallo sintético al crear la solicitud")

    monkeypatch.setattr("gastos.services.SolicitudGasto.objects.create", fallo)
    with pytest.raises(RuntimeError, match="fallo sintético"):
        crear_solicitud_gasto(
            actor=actor,
            concepto="Alta que debe revertirse",
            monto_estimado=Decimal("1.00"),
            unidad_requirente="Unidad",
        )

    assert not SolicitudGasto.objects.exists()
    assert not TramiteBase.objects.exists()


def test_servicio_descarta_numero_ocupado_por_gasto_historico(
    actor_factory: Any,
) -> None:
    """Una fila cargada con pk explícito no se reutiliza si la secuencia la alcanza."""
    user, actor = actor_factory(["gastos.presentar"])
    numero_reservado = reservar_numero_solicitud_gasto()
    existente = crear_gasto_sintetico(pk=numero_reservado + 1, solicitante=user)

    solicitud = crear_solicitud_gasto(
        actor=actor,
        concepto="Alta después de un número ocupado",
        monto_estimado=Decimal("1.00"),
        unidad_requirente="Unidad",
    )

    assert solicitud.pk == numero_reservado + 2
    assert existente.pk == numero_reservado + 1
    assert TramiteBase.objects.filter(numero_publico=existente.pk).count() == 1


def test_puente_existente_reutiliza_la_cabecera_del_gasto(actor_factory: Any) -> None:
    """La creación válida mantiene operativo el puente temporal de documentos."""
    user, actor = actor_factory(["gastos.presentar"])
    solicitud = crear_solicitud_gasto(
        actor=actor,
        concepto="Gasto para puente",
        monto_estimado=Decimal("1.00"),
        unidad_requirente="Unidad",
    )

    base = registrar_cabecera_gasto(solicitud)

    assert base.pk == solicitud.tramite_base_id
    assert base.solicitante_actor_id == str(user.pk)
    assert TramiteBase.objects.count() == 1


def test_modelo_rechaza_solicitud_sin_numero_o_sin_cabecera(actor_factory: Any) -> None:
    """La guarda ORM exige número reservado y cabecera coherente antes de escribir."""
    user, _ = actor_factory()

    with pytest.raises(IntegrityError, match="número público"):
        SolicitudGasto(
            concepto="Sin número",
            monto_estimado=Decimal("1.00"),
            unidad_requirente="Unidad",
            solicitante_id=user.pk,
        ).save()

    with pytest.raises(IntegrityError, match="cabecera"):
        SolicitudGasto(
            pk=9000001,
            concepto="Sin cabecera",
            monto_estimado=Decimal("1.00"),
            unidad_requirente="Unidad",
            solicitante_id=user.pk,
        ).save()

    assert not SolicitudGasto.objects.exists()


def test_modelo_rechaza_cabecera_de_otro_circuito_numero_o_titular(
    actor_factory: Any,
) -> None:
    """La guarda ORM informa el cruce antes de que PostgreSQL lo rechace."""
    user, _ = actor_factory()
    otro = User.objects.create_user(username="titular_ajeno")

    base_facturacion = _base(9000010, user.pk, Circuito.FACTURACION)
    with pytest.raises(IntegrityError, match="circuito GASTO"):
        SolicitudGasto(
            pk=9000010,
            tramite_base=base_facturacion,
            concepto="Cruce de circuito",
            monto_estimado=Decimal("1.00"),
            unidad_requirente="Unidad",
            solicitante_id=user.pk,
        ).save()

    base_otro_numero = _base(9000011, user.pk)
    with pytest.raises(IntegrityError, match="circuito GASTO"):
        SolicitudGasto(
            pk=9000012,
            tramite_base=base_otro_numero,
            concepto="Cruce de número",
            monto_estimado=Decimal("1.00"),
            unidad_requirente="Unidad",
            solicitante_id=user.pk,
        ).save()

    base_titular_ajeno = _base(9000013, otro.pk)
    with pytest.raises(IntegrityError, match="circuito GASTO"):
        SolicitudGasto(
            pk=9000013,
            tramite_base=base_titular_ajeno,
            concepto="Cruce de titular",
            monto_estimado=Decimal("1.00"),
            unidad_requirente="Unidad",
            solicitante_id=user.pk,
        ).save()

    assert not SolicitudGasto.objects.exists()


def test_postgresql_rechaza_inserciones_directas_incompatibles(
    actor_factory: Any,
) -> None:
    """El trigger cubre SQL directo para circuito, número, titular y NULL."""
    user, _ = actor_factory()
    otro = User.objects.create_user(username="titular_directo_ajeno")
    base_facturacion = _base(9000020, user.pk, Circuito.FACTURACION)
    base_otro_numero = _base(9000021, user.pk)
    base_titular_ajeno = _base(9000022, otro.pk)

    for numero, titular, base_id in (
        (9000020, user.pk, base_facturacion.pk),
        (9000023, user.pk, base_otro_numero.pk),
        (9000022, user.pk, base_titular_ajeno.pk),
        (9000024, user.pk, None),
    ):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gastos_solicitudgasto
                    (id, concepto, monto_estimado, unidad_requirente, solicitante_id,
                     fecha_creacion, estado, version, tramite_base_id)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                """,
                [
                    numero,
                    "Inserción directa",
                    Decimal("1.00"),
                    "Unidad",
                    titular,
                    EstadoSolicitud.PRESENTADA,
                    0,
                    base_id,
                ],
            )
        assert not SolicitudGasto.objects.filter(pk=numero).exists()


def test_postgresql_rechaza_reasignaciones_por_sql_directo(
    actor_factory: Any,
) -> None:
    """Un UPDATE directo de id, tramite_base o solicitante no deja cambios."""
    user, _ = actor_factory()
    otro = User.objects.create_user(username="reasignacion_ajena")
    solicitud = crear_gasto_sintetico(pk=9000030, solicitante=user)
    base_ajena = _base(9000031, otro.pk)
    original_base_id = solicitud.tramite_base_id

    intentos = (
        ("UPDATE gastos_solicitudgasto SET tramite_base_id = %s WHERE id = %s",
         [base_ajena.pk, solicitud.pk]),
        ("UPDATE gastos_solicitudgasto SET solicitante_id = %s WHERE id = %s",
         [otro.pk, solicitud.pk]),
        ("UPDATE gastos_solicitudgasto SET id = %s WHERE id = %s",
         [9000099, solicitud.pk]),
    )
    for sql, parametros in intentos:
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, parametros)
        solicitud.refresh_from_db()
        assert solicitud.pk == 9000030
        assert solicitud.tramite_base_id == original_base_id
        assert solicitud.solicitante_id == user.pk


def test_orm_rechaza_reasignaciones_por_save_update_y_bulk_update(
    actor_factory: Any,
) -> None:
    """Las guardas ORM bloquean los tres caminos antes de llegar a PostgreSQL."""
    user, _ = actor_factory()
    otro = User.objects.create_user(username="cambio_orm_ajeno")
    solicitud = crear_gasto_sintetico(pk=9000040, solicitante=user)
    base_ajena = _base(9000041, otro.pk)

    solicitud.tramite_base = base_ajena
    with pytest.raises(IntegrityError):
        solicitud.save()
    solicitud.refresh_from_db()
    assert solicitud.tramite_base_id != base_ajena.pk

    solicitud.solicitante_id = otro.pk
    with pytest.raises(IntegrityError):
        solicitud.save()
    solicitud.refresh_from_db()
    assert solicitud.solicitante_id == user.pk

    original_pk = solicitud.pk
    solicitud.pk = 9000098
    with pytest.raises(IntegrityError):
        solicitud.save()
    solicitud.pk = original_pk
    solicitud.refresh_from_db()

    with pytest.raises(IntegrityError):
        SolicitudGasto.objects.filter(pk=solicitud.pk).update(tramite_base=base_ajena)
    with pytest.raises(IntegrityError):
        SolicitudGasto.objects.filter(pk=solicitud.pk).update(solicitante=otro)
    with pytest.raises(IntegrityError):
        SolicitudGasto.objects.update(pk=9000097)
    with pytest.raises(IntegrityError):
        SolicitudGasto.objects.bulk_update([solicitud], ["tramite_base"])

    solicitud.refresh_from_db()
    assert solicitud.pk == original_pk
    assert solicitud.tramite_base_id != base_ajena.pk
    assert solicitud.solicitante_id == user.pk


def test_borrado_conserva_decisiones_y_protege_la_cabecera(actor_factory: Any) -> None:
    """Se conserva el DELETE de gasto y PROTECT sobre la cabecera."""
    user, _ = actor_factory()
    autor = User.objects.create_user(username="decide_borrado")
    solicitud = crear_gasto_sintetico(pk=9000050, solicitante=user)
    base_pk = solicitud.tramite_base_id
    DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=autor,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )

    with pytest.raises(ProtectedError):
        solicitud.tramite_base.delete()
    assert TramiteBase.objects.filter(pk=base_pk).exists()

    solicitud.delete()
    assert not DecisionGasto.objects.exists()
    assert TramiteBase.objects.filter(pk=base_pk).exists()


def test_mismo_numero_en_dos_circuitos_no_cruza_cabeceras(actor_factory: Any) -> None:
    """gastos:N y facturacion:N conservan cabeceras y vínculos distintos."""
    user, _ = actor_factory()
    numero = 9000060
    facturacion_base = _base(numero, user.pk, Circuito.FACTURACION)
    facturacion = SolicitudFacturacion.objects.create(
        pk=numero,
        tramite_base=facturacion_base,
    )
    gasto = crear_gasto_sintetico(pk=numero, solicitante=user)

    assert gasto.tramite_base_id != facturacion.tramite_base_id
    assert gasto.tramite_base.circuito == Circuito.GASTO
    assert facturacion.tramite_base.circuito == Circuito.FACTURACION
    assert gasto.tramite_base.numero_publico == facturacion.tramite_base.numero_publico == numero
    assert TramiteBase.objects.filter(numero_publico=numero).count() == 2


@pytest.mark.django_db(transaction=True)
def test_dos_altas_concurrentes_no_duplican_cabeceras(actor_factory: Any) -> None:
    """Dos conexiones reservan números distintos y dejan pares completos."""
    _, actor = actor_factory(["gastos.presentar"])
    barrier = Barrier(2)
    resultados: list[Any] = [None, None]

    def worker(indice: int) -> None:
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            resultados[indice] = crear_solicitud_gasto(
                actor=actor,
                concepto=f"Alta concurrente {indice}",
                monto_estimado=Decimal("1.00"),
                unidad_requirente="Unidad",
            )
        except Exception as exc:
            resultados[indice] = exc
        finally:
            connections.close_all()

    hilos = [Thread(target=worker, args=(indice,)) for indice in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=15)

    assert all(not hilo.is_alive() for hilo in hilos)
    assert all(isinstance(resultado, SolicitudGasto) for resultado in resultados)
    assert resultados[0].pk != resultados[1].pk
    assert TramiteBase.objects.count() == 2
    for solicitud in resultados:
        base = TramiteBase.objects.get(pk=solicitud.tramite_base_id)
        assert base.numero_publico == solicitud.pk
        assert base.solicitante_actor_id == str(actor.subject_id)
        assert base.centro_costo_codigo is None
