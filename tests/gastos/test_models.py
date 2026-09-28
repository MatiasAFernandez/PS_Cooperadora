"""Pruebas del modelo SolicitudGasto y DecisionGasto (I1-R01, I1-R03, restricciones y tipos)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto

User = get_user_model()


@pytest.mark.django_db
def test_creacion_solicitud_valida() -> None:
    """I1-R01: Alta válida con campos requeridos y valores asignados por servidor."""
    solicitante = User.objects.create_user(username="solicitante_a")
    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos de laboratorio de física",
        monto_estimado=Decimal("15000.50"),
        unidad_requirente="Laboratorio de Física",
        solicitante=solicitante,
    )

    assert solicitud.pk is not None
    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert solicitud.version == 0
    assert solicitud.fecha_creacion is not None
    expected_str = f"Solicitud #{solicitud.pk} - Insumos de laboratorio de física ($15000.50)"
    assert str(solicitud) == expected_str


@pytest.mark.django_db
def test_restriccion_monto_estimado_positivo() -> None:
    """I1-R01: Rechazo de importe cero o negativo a nivel base de datos."""
    solicitante = User.objects.create_user(username="solicitante_monto")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SolicitudGasto.objects.create(
                concepto="Gasto importe cero",
                monto_estimado=Decimal("0.00"),
                unidad_requirente="Electrónica",
                solicitante=solicitante,
            )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SolicitudGasto.objects.create(
                concepto="Gasto importe negativo",
                monto_estimado=Decimal("-500.00"),
                unidad_requirente="Electrónica",
                solicitante=solicitante,
            )


@pytest.mark.django_db
def test_validador_modelo_monto_estimado() -> None:
    """I1-R01: Rechazo a nivel de validación de modelo."""
    solicitante = User.objects.create_user(username="solicitante_val")
    solicitud = SolicitudGasto(
        concepto="Gasto inválido",
        monto_estimado=Decimal("0.00"),
        unidad_requirente="Electrónica",
        solicitante=solicitante,
    )

    with pytest.raises(ValidationError):
        solicitud.full_clean()


@pytest.mark.django_db
def test_proteccion_eliminacion_usuario_solicitante() -> None:
    """El solicitante no puede eliminarse si tiene solicitudes asociadas (PROTECT)."""
    solicitante = User.objects.create_user(username="solicitante_protegido")
    SolicitudGasto.objects.create(
        concepto="Gasto protegido",
        monto_estimado=Decimal("1000.00"),
        unidad_requirente="Biblioteca",
        solicitante=solicitante,
    )

    with pytest.raises(ProtectedError):
        solicitante.delete()


@pytest.mark.django_db
def test_creacion_decision_gasto_valida() -> None:
    """I1-R03: Alta válida de evento DecisionGasto asociado a SolicitudGasto."""
    solicitante = User.objects.create_user(username="solicitante_dec")
    autor = User.objects.create_user(username="operador_dec")
    solicitud = SolicitudGasto.objects.create(
        concepto="Insumos varios",
        monto_estimado=Decimal("8000.00"),
        unidad_requirente="Taller",
        solicitante=solicitante,
    )

    decision = DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=autor,
        motivo="Gasto necesario para actividades prácticas",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )

    assert decision.pk is not None
    assert decision.fecha is not None
    assert decision.motivo == "Gasto necesario para actividades prácticas"
    assert decision.estado_anterior == EstadoSolicitud.PRESENTADA
    assert decision.estado_resultante == EstadoSolicitud.ACEPTADA
    expected_str = f"Decisión #{decision.pk} sobre Solicitud #{solicitud.pk}: aceptada"
    assert str(decision) == expected_str


@pytest.mark.django_db
def test_decision_gasto_eliminacion_cascada_solicitud() -> None:
    """Al eliminar una solicitud, sus eventos de decisión se eliminan en cascada (CASCADE)."""
    solicitante = User.objects.create_user(username="sol_cascada")
    autor = User.objects.create_user(username="op_cascada")
    solicitud = SolicitudGasto.objects.create(
        concepto="Gasto a eliminar",
        monto_estimado=Decimal("3000.00"),
        unidad_requirente="Informática",
        solicitante=solicitante,
    )
    DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=autor,
        motivo="Aceptado",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )

    assert DecisionGasto.objects.filter(solicitud=solicitud).count() == 1
    solicitud.delete()
    assert DecisionGasto.objects.count() == 0


@pytest.mark.django_db
def test_decision_gasto_proteccion_eliminacion_autor() -> None:
    """El autor de una decisión no puede eliminarse si tiene decisiones asociadas (PROTECT)."""
    solicitante = User.objects.create_user(username="sol_autor_prot")
    autor = User.objects.create_user(username="op_autor_prot")
    solicitud = SolicitudGasto.objects.create(
        concepto="Gasto autor protegido",
        monto_estimado=Decimal("4500.00"),
        unidad_requirente="Laboratorio",
        solicitante=solicitante,
    )
    DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=autor,
        motivo="Aceptado",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )

    with pytest.raises(ProtectedError):
        autor.delete()


@pytest.mark.django_db
def test_solicitud_mensaje_respaldo_h4() -> None:
    """I1-R05 / H4: Comprobar mensaje de respaldo según estado en SolicitudGasto."""
    solicitante = User.objects.create_user(username="sol_respaldo_model")
    solicitud = SolicitudGasto.objects.create(
        concepto="Gasto de prueba respaldo",
        monto_estimado=Decimal("2000.00"),
        unidad_requirente="Electrónica",
        solicitante=solicitante,
        estado=EstadoSolicitud.PRESENTADA,
    )
    assert (
        solicitud.mensaje_respaldo
        == "No se solicita documentación en esta etapa de la demostración"
    )

    solicitud.estado = EstadoSolicitud.ACEPTADA
    solicitud.save()
    assert (
        solicitud.mensaje_respaldo
        == "Respaldo del gasto (presupuesto o factura): por aportar"
    )

    solicitud.estado = EstadoSolicitud.POSTERGADA
    solicitud.save()
    assert (
        solicitud.mensaje_respaldo
        == "No se solicita documentación en esta etapa de la demostración"
    )

    solicitud.estado = EstadoSolicitud.RECHAZADA
    solicitud.save()
    assert (
        solicitud.mensaje_respaldo
        == "No se solicita documentación en esta etapa de la demostración"
    )
