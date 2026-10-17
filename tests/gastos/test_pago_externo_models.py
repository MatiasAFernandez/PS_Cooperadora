"""Pruebas sintéticas PostgreSQL de modelo para PagoExterno y EventoPagoExterno.

Cubre restricciones de base de datos (importe positivo, moneda ARS), cardinalidad
máxima de un pago por gasto y un evento por pago, protección de borrado (PROTECT),
fecha sin hipótesis artificial de futuro, ausencia de duplicación de actor/fecha en
el pago y huella de idempotencia sin UNIQUE redundante.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.models import ProtectedError

from gastos.models import (
    EstadoSolicitud,
    EventoPagoExterno,
    PagoExterno,
    SolicitudGasto,
)
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()

pytestmark = pytest.mark.django_db


def _solicitud(solicitante, estado: str = EstadoSolicitud.ACEPTADA) -> SolicitudGasto:
    return crear_gasto_sintetico(
        concepto="Gasto sintético para pago externo",
        monto_estimado=Decimal("1000.00"),
        unidad_requirente="Unidad sintética",
        solicitante=solicitante,
        estado=estado,
    )


def _pago(solicitud: SolicitudGasto, **overrides) -> PagoExterno:
    data = {
        "solicitud": solicitud,
        "importe": Decimal("500.00"),
        "moneda": "ARS",
        "fecha_pago": date(2025, 1, 10),
        "referencia_externa": "EXT-0001",
        "referencia_documental": "doc-version-1",
        "huella_idempotencia": "a" * 64,
    }
    data.update(overrides)
    return PagoExterno.objects.create(**data)


def test_pago_importe_cero_o_negativo_rechazado_en_bd() -> None:
    """La restricción de base de datos rechaza importes no estrictamente positivos."""
    solicitante = User.objects.create_user(username="pago_importe_user")
    solicitud = _solicitud(solicitante)

    for importe in (Decimal("0.00"), Decimal("-1.00")):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _pago(solicitud, importe=importe)


def test_pago_moneda_distinta_de_ars_rechazada_en_bd() -> None:
    """La restricción de base de datos fija la moneda en ARS."""
    solicitante = User.objects.create_user(username="pago_moneda_user")
    solicitud = _solicitud(solicitante)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _pago(solicitud, moneda="USD")


def test_pago_moneda_por_defecto_es_ars() -> None:
    """Sin valor explícito, la moneda del pago es ARS."""
    solicitante = User.objects.create_user(username="pago_moneda_def")
    solicitud = _solicitud(solicitante)

    pago = PagoExterno.objects.create(
        solicitud=solicitud,
        importe=Decimal("10.00"),
        fecha_pago=date(2025, 2, 1),
        referencia_externa="EXT-DEF",
        referencia_documental="doc-def",
        huella_idempotencia="b" * 64,
    )
    assert pago.moneda == "ARS"


def test_pago_unico_por_solicitud() -> None:
    """La relación OneToOne impide más de un pago por solicitud."""
    solicitante = User.objects.create_user(username="pago_unico_user")
    solicitud = _solicitud(solicitante)
    _pago(solicitud)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _pago(solicitud, referencia_externa="EXT-0002")

    campo = PagoExterno._meta.get_field("solicitud")
    assert campo.one_to_one is True
    assert campo.unique is True


def test_pago_protege_eliminacion_de_solicitud() -> None:
    """PROTECT impide borrar una solicitud con pago registrado."""
    solicitante = User.objects.create_user(username="pago_protect_user")
    solicitud = _solicitud(solicitante)
    _pago(solicitud)

    with pytest.raises(ProtectedError):
        solicitud.delete()

    campo = PagoExterno._meta.get_field("solicitud")
    assert campo.remote_field.on_delete is models.PROTECT


def test_evento_unico_por_pago() -> None:
    """La relación OneToOne impide más de un evento por pago."""
    solicitante = User.objects.create_user(username="evento_unico_user")
    actor = User.objects.create_user(username="evento_actor_user")
    solicitud = _solicitud(solicitante)
    pago = _pago(solicitud)
    EventoPagoExterno.objects.create(pago=pago, actor=actor)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EventoPagoExterno.objects.create(pago=pago, actor=actor)


def test_evento_protege_eliminacion_de_pago() -> None:
    """PROTECT impide borrar un pago con evento de auditoría."""
    solicitante = User.objects.create_user(username="evento_protect_user")
    actor = User.objects.create_user(username="evento_protect_actor")
    solicitud = _solicitud(solicitante)
    pago = _pago(solicitud)
    EventoPagoExterno.objects.create(pago=pago, actor=actor)

    with pytest.raises(ProtectedError):
        pago.delete()

    campo = EventoPagoExterno._meta.get_field("pago")
    assert campo.remote_field.on_delete is models.PROTECT


def test_fecha_pago_futura_sin_restriccion_artificial() -> None:
    """El modelo no impone una hipótesis de fecha futura sobre el hecho del pago."""
    solicitante = User.objects.create_user(username="pago_futuro_user")
    solicitud = _solicitud(solicitante)
    futura = date.today() + timedelta(days=3650)

    pago = PagoExterno(
        solicitud=solicitud,
        importe=Decimal("25.00"),
        moneda="ARS",
        fecha_pago=futura,
        referencia_externa="EXT-FUTURA",
        referencia_documental="doc-futura",
        huella_idempotencia="c" * 64,
    )
    pago.full_clean()
    pago.save()
    pago.refresh_from_db()
    assert pago.fecha_pago == futura


def test_pago_no_duplica_actor_ni_fecha_del_evento() -> None:
    """El evento es la autoridad única de actor y fecha; el pago no los duplica."""
    nombres_pago = {campo.name for campo in PagoExterno._meta.get_fields()}
    assert {"actor", "fecha", "fecha_hora"}.isdisjoint(nombres_pago)

    nombres_evento = {campo.name for campo in EventoPagoExterno._meta.get_fields()}
    assert {"actor", "fecha_hora"}.issubset(nombres_evento)


def test_huella_idempotencia_sin_unique_redundante() -> None:
    """La huella no es UNIQUE: la cardinalidad la impone el OneToOne de la solicitud."""
    campo = PagoExterno._meta.get_field("huella_idempotencia")
    assert campo.unique is False
    assert not any(
        isinstance(constraint, models.UniqueConstraint)
        for constraint in PagoExterno._meta.constraints
    )


def test_importe_invalido_rechazado_por_validacion_de_modelo() -> None:
    """El validador de modelo rechaza importes no positivos antes de persistir."""
    solicitante = User.objects.create_user(username="pago_fullclean_user")
    solicitud = _solicitud(solicitante)
    pago = PagoExterno(
        solicitud=solicitud,
        importe=Decimal("0.00"),
        moneda="ARS",
        fecha_pago=date(2025, 1, 10),
        referencia_externa="EXT-VAL",
        referencia_documental="doc-val",
        huella_idempotencia="d" * 64,
    )

    with pytest.raises(ValidationError):
        pago.full_clean()


def test_pago_solicitud_no_puede_reasignarse_mediante_save() -> None:
    """Una vez creado el pago, su solicitud queda congelada y no puede reasignarse vía save()."""
    solicitante = User.objects.create_user(username="reassign_sol_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago = _pago(sol1)

    pago.solicitud = sol2
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            pago.save()

    pago.refresh_from_db()
    assert pago.solicitud_id == sol1.pk


def test_pago_referencia_documental_no_puede_reasignarse_mediante_save() -> None:
    """Una vez creado el pago, su referencia documental no puede reasignarse vía save()."""
    solicitante = User.objects.create_user(username="reassign_doc_user")
    sol = _solicitud(solicitante)
    pago = _pago(sol, referencia_documental="doc-original-v1")

    pago.referencia_documental = "doc-modificada-v2"
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            pago.save()

    pago.refresh_from_db()
    assert pago.referencia_documental == "doc-original-v1"


def test_pago_links_no_pueden_reasignarse_mediante_queryset_update() -> None:
    """QuerySet.update() no permite reasignar solicitud ni referencia documental."""
    solicitante = User.objects.create_user(username="reassign_qs_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago = _pago(sol1, referencia_documental="doc-qs-v1")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PagoExterno.objects.filter(pk=pago.pk).update(solicitud=sol2)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PagoExterno.objects.filter(pk=pago.pk).update(referencia_documental="doc-qs-hack")

    pago.refresh_from_db()
    assert pago.solicitud_id == sol1.pk
    assert pago.referencia_documental == "doc-qs-v1"


def test_pago_links_no_pueden_reasignarse_mediante_bulk_update() -> None:
    """bulk_update() rechaza solicitud y referencia documental."""
    solicitante = User.objects.create_user(username="reassign_bulk_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago = _pago(sol1, referencia_documental="doc-bulk-v1")

    pago.solicitud = sol2
    with pytest.raises(IntegrityError):
        PagoExterno.objects.bulk_update([pago], ["solicitud"])

    pago.solicitud = sol1
    pago.referencia_documental = "doc-bulk-hack"
    with pytest.raises(IntegrityError):
        PagoExterno.objects.bulk_update([pago], ["referencia_documental"])

    pago.refresh_from_db()
    assert pago.solicitud_id == sol1.pk
    assert pago.referencia_documental == "doc-bulk-v1"


def test_pago_clean_rechaza_reasignacion_de_solicitud_y_documento() -> None:
    """full_clean() detecta y rechaza la reasignación con ValidationError."""
    solicitante = User.objects.create_user(username="clean_reassign_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago = _pago(sol1, referencia_documental="doc-clean-v1")

    pago.solicitud = sol2
    with pytest.raises(ValidationError):
        pago.full_clean()

    pago.solicitud = sol1
    pago.referencia_documental = "doc-clean-v2"
    with pytest.raises(ValidationError):
        pago.full_clean()


def test_evento_pago_no_puede_reasignarse_mediante_save() -> None:
    """Una vez creado el evento, su pago vinculado no puede reasignarse vía save()."""
    solicitante = User.objects.create_user(username="reassign_ev_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago1 = _pago(sol1, referencia_externa="EXT-EV-1")
    pago2 = _pago(sol2, referencia_externa="EXT-EV-2")
    evento = EventoPagoExterno.objects.create(pago=pago1, actor=solicitante)

    evento.pago = pago2
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            evento.save()

    evento.refresh_from_db()
    assert evento.pago_id == pago1.pk


def test_evento_pago_no_puede_reasignarse_mediante_queryset_update() -> None:
    """QuerySet.update() no permite reasignar el pago de un evento existente."""
    solicitante = User.objects.create_user(username="reassign_ev_qs_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago1 = _pago(sol1, referencia_externa="EXT-EV-QS1")
    pago2 = _pago(sol2, referencia_externa="EXT-EV-QS2")
    evento = EventoPagoExterno.objects.create(pago=pago1, actor=solicitante)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EventoPagoExterno.objects.filter(pk=evento.pk).update(pago=pago2)

    evento.refresh_from_db()
    assert evento.pago_id == pago1.pk


def test_evento_pago_no_puede_reasignarse_mediante_bulk_update() -> None:
    """bulk_update() rechaza la reasignación del pago de un evento."""
    solicitante = User.objects.create_user(username="reassign_event_bulk_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago1 = _pago(sol1, referencia_externa="EXT-EV-BULK1")
    pago2 = _pago(sol2, referencia_externa="EXT-EV-BULK2")
    evento = EventoPagoExterno.objects.create(pago=pago1, actor=solicitante)

    evento.pago = pago2
    with pytest.raises(IntegrityError):
        EventoPagoExterno.objects.bulk_update([evento], ["pago"])

    evento.refresh_from_db()
    assert evento.pago_id == pago1.pk


@pytest.mark.parametrize("campo", ["actor", "tipo_evento", "fecha_hora"])
def test_evento_auditoria_no_puede_modificarse_mediante_save(campo: str) -> None:
    """save() no altera actor, tipo ni hora del evento una vez creado."""
    actor = User.objects.create_user(username=f"immutable_save_{campo}")
    actor_alterno = User.objects.create_user(username=f"immutable_save_alt_{campo}")
    solicitud = _solicitud(actor)
    pago = _pago(solicitud, referencia_externa=f"EXT-IMM-SAVE-{campo}")
    evento = EventoPagoExterno.objects.create(pago=pago, actor=actor)
    original = {
        "actor_id": evento.actor_id,
        "tipo_evento": evento.tipo_evento,
        "fecha_hora": evento.fecha_hora,
    }

    if campo == "actor":
        evento.actor = actor_alterno
    elif campo == "tipo_evento":
        evento.tipo_evento = "pago_externo_modificado"
    else:
        evento.fecha_hora = evento.fecha_hora - timedelta(minutes=1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            evento.save()

    evento.refresh_from_db()
    assert evento.actor_id == original["actor_id"]
    assert evento.tipo_evento == original["tipo_evento"]
    assert evento.fecha_hora == original["fecha_hora"]


@pytest.mark.parametrize("campo", ["actor", "tipo_evento", "fecha_hora"])
def test_evento_auditoria_no_puede_modificarse_mediante_queryset_update(campo: str) -> None:
    """QuerySet.update() rechaza cambios a los datos de auditoría."""
    actor = User.objects.create_user(username=f"immutable_update_{campo}")
    actor_alterno = User.objects.create_user(username=f"immutable_update_alt_{campo}")
    solicitud = _solicitud(actor)
    pago = _pago(solicitud, referencia_externa=f"EXT-IMM-UPD-{campo}")
    evento = EventoPagoExterno.objects.create(pago=pago, actor=actor)
    fecha_hora_original = evento.fecha_hora
    valores = {
        "actor": actor_alterno,
        "tipo_evento": "pago_externo_modificado",
        "fecha_hora": evento.fecha_hora + timedelta(minutes=1),
    }

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EventoPagoExterno.objects.filter(pk=evento.pk).update(**{campo: valores[campo]})

    evento.refresh_from_db()
    assert evento.actor_id == actor.pk
    assert evento.tipo_evento == "pago_externo_registrado"
    assert evento.fecha_hora == fecha_hora_original


@pytest.mark.parametrize("campo", ["actor", "tipo_evento", "fecha_hora"])
def test_evento_auditoria_no_puede_modificarse_mediante_bulk_update(campo: str) -> None:
    """bulk_update() rechaza cambios a los datos de auditoría."""
    actor = User.objects.create_user(username=f"immutable_bulk_{campo}")
    actor_alterno = User.objects.create_user(username=f"immutable_bulk_alt_{campo}")
    solicitud = _solicitud(actor)
    pago = _pago(solicitud, referencia_externa=f"EXT-IMM-BULK-{campo}")
    evento = EventoPagoExterno.objects.create(pago=pago, actor=actor)
    fecha_hora_original = evento.fecha_hora
    valores = {
        "actor": actor_alterno,
        "tipo_evento": "pago_externo_modificado",
        "fecha_hora": evento.fecha_hora + timedelta(minutes=1),
    }
    setattr(evento, campo, valores[campo])

    with pytest.raises(IntegrityError):
        EventoPagoExterno.objects.bulk_update([evento], [campo])

    evento.refresh_from_db()
    assert evento.actor_id == actor.pk
    assert evento.tipo_evento == "pago_externo_registrado"
    assert evento.fecha_hora == fecha_hora_original


def test_evento_auditoria_no_puede_borrarse_mediante_modelo_ni_queryset() -> None:
    """No se puede eliminar el historial del pago a través del ORM."""
    actor = User.objects.create_user(username="immutable_event_delete_user")
    solicitud = _solicitud(actor)
    pago = _pago(solicitud, referencia_externa="EXT-IMM-DELETE")
    evento = EventoPagoExterno.objects.create(pago=pago, actor=actor)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            evento.delete()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EventoPagoExterno.objects.filter(pk=evento.pk).delete()

    assert EventoPagoExterno.objects.filter(pk=evento.pk).exists()


def test_evento_clean_rechaza_reasignacion_de_pago() -> None:
    """full_clean() en evento detecta y rechaza la reasignación de pago."""
    solicitante = User.objects.create_user(username="clean_ev_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    pago1 = _pago(sol1, referencia_externa="EXT-EV-CL1")
    pago2 = _pago(sol2, referencia_externa="EXT-EV-CL2")
    evento = EventoPagoExterno.objects.create(pago=pago1, actor=solicitante)

    evento.pago = pago2
    with pytest.raises(ValidationError):
        evento.full_clean()


@pytest.mark.parametrize("campo", ["actor", "tipo_evento", "fecha_hora"])
def test_evento_clean_rechaza_cambios_a_datos_de_auditoria(campo: str) -> None:
    """full_clean() marca como inválido cualquier cambio de auditoría."""
    actor = User.objects.create_user(username=f"immutable_clean_{campo}")
    actor_alterno = User.objects.create_user(username=f"immutable_clean_alt_{campo}")
    solicitud = _solicitud(actor)
    pago = _pago(solicitud, referencia_externa=f"EXT-IMM-CLEAN-{campo}")
    evento = EventoPagoExterno.objects.create(pago=pago, actor=actor)

    if campo == "actor":
        evento.actor = actor_alterno
    elif campo == "tipo_evento":
        evento.tipo_evento = "pago_externo_modificado"
    else:
        evento.fecha_hora = evento.fecha_hora - timedelta(minutes=1)

    with pytest.raises(ValidationError):
        evento.full_clean()


def test_pago_y_evento_guardar_sin_modificar_links_permitido() -> None:
    """Guardar cambios en campos mutables (referencia_externa) o sin cambios es válido."""
    solicitante = User.objects.create_user(username="safe_upd_user")
    sol = _solicitud(solicitante)
    pago = _pago(sol, referencia_externa="EXT-INIT", referencia_documental="doc-init")
    evento = EventoPagoExterno.objects.create(pago=pago, actor=solicitante)

    # Actualizar campo no restringido vía save()
    pago.referencia_externa = "EXT-UPDATED"
    pago.save()
    pago.refresh_from_db()
    assert pago.referencia_externa == "EXT-UPDATED"
    assert pago.solicitud_id == sol.pk
    assert pago.referencia_documental == "doc-init"

    # QuerySet.update sobre campo no restringido
    PagoExterno.objects.filter(pk=pago.pk).update(referencia_externa="EXT-QS-UPDATED")
    pago.refresh_from_db()
    assert pago.referencia_externa == "EXT-QS-UPDATED"

    # Evento guardar sin cambios
    evento.save()
    evento.refresh_from_db()
    assert evento.pago_id == pago.pk


def test_triggers_postgresql_impiden_reasignacion_por_sql_crudo() -> None:
    """Los triggers PostgreSQL protegen los vínculos aunque se omita el ORM."""
    solicitante = User.objects.create_user(username="raw_sql_links_user")
    sol1 = _solicitud(solicitante)
    sol2 = _solicitud(solicitante)
    sol3 = _solicitud(solicitante)
    pago1 = _pago(sol1, referencia_documental="doc-raw-v1")
    pago2 = _pago(sol3, referencia_externa="EXT-RAW-2")
    evento = EventoPagoExterno.objects.create(pago=pago1, actor=solicitante)
    fecha_hora_original = evento.fecha_hora

    quote = connection.ops.quote_name
    pago_table = quote(PagoExterno._meta.db_table)
    pago_pk = quote(PagoExterno._meta.pk.column)
    solicitud_col = quote(PagoExterno._meta.get_field("solicitud").column)
    documento_col = quote(PagoExterno._meta.get_field("referencia_documental").column)
    evento_table = quote(EventoPagoExterno._meta.db_table)
    evento_pk = quote(EventoPagoExterno._meta.pk.column)
    evento_pago_col = quote(EventoPagoExterno._meta.get_field("pago").column)
    evento_actor_col = quote(EventoPagoExterno._meta.get_field("actor").column)
    evento_tipo_col = quote(EventoPagoExterno._meta.get_field("tipo_evento").column)
    evento_fecha_col = quote(EventoPagoExterno._meta.get_field("fecha_hora").column)

    updates = (
        (
            f"UPDATE {pago_table} SET {solicitud_col} = %s WHERE {pago_pk} = %s",
            [sol2.pk, pago1.pk],
        ),
        (
            f"UPDATE {pago_table} SET {documento_col} = %s WHERE {pago_pk} = %s",
            ["doc-raw-v2", pago1.pk],
        ),
        (
            f"UPDATE {evento_table} SET {evento_pago_col} = %s WHERE {evento_pk} = %s",
            [pago2.pk, evento.pk],
        ),
        (
            f"UPDATE {evento_table} SET {evento_actor_col} = %s WHERE {evento_pk} = %s",
            [User.objects.create_user(username="raw_sql_other_actor").pk, evento.pk],
        ),
        (
            f"UPDATE {evento_table} SET {evento_tipo_col} = %s WHERE {evento_pk} = %s",
            ["pago_externo_modificado", evento.pk],
        ),
        (
            f"UPDATE {evento_table} SET {evento_fecha_col} = %s WHERE {evento_pk} = %s",
            [evento.fecha_hora + timedelta(minutes=1), evento.pk],
        ),
    )

    for sql, params in updates:
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)

        pago1.refresh_from_db()
        evento.refresh_from_db()
        assert pago1.solicitud_id == sol1.pk
        assert pago1.referencia_documental == "doc-raw-v1"
        assert evento.pago_id == pago1.pk
        assert evento.actor_id == solicitante.pk
        assert evento.tipo_evento == "pago_externo_registrado"
        assert evento.fecha_hora == fecha_hora_original

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {evento_table} WHERE {evento_pk} = %s",
                    [evento.pk],
                )

    assert EventoPagoExterno.objects.filter(pk=evento.pk).exists()
