"""Pruebas del modelo SolicitudGasto (I1-R01, restricciones y tipos)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from gastos.models import EstadoSolicitud, SolicitudGasto

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
