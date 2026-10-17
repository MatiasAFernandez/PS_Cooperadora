"""Datos sintéticos compartidos por las pruebas de gastos.

Las solicitudes ahora comparten número público y titular con su cabecera. Esta
fábrica reserva el número y crea ambas filas en una transacción para que los
fixtures directos sigan representando gastos válidos sin duplicar la lógica de
producción ni reutilizar cabeceras.
"""

from decimal import Decimal
from typing import Any

from django.db import connection, transaction

from comunes.models import Circuito, TramiteBase
from gastos.models import EstadoSolicitud, SolicitudGasto


def reservar_numero_solicitud_gasto() -> int:
    """Reserva el siguiente entero de la secuencia de gastos para un fixture."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(pg_get_serial_sequence('gastos_solicitudgasto', 'id'))")
        return cursor.fetchone()[0]


def crear_gasto_sintetico(
    *,
    solicitante: Any = None,
    solicitante_id: int | None = None,
    pk: int | None = None,
    tramite_base: TramiteBase | None = None,
    **kwargs: Any,
) -> SolicitudGasto:
    """Crea una solicitud válida con su cabecera sintética y número explícito.

    Acepta los mismos campos de modelo que `SolicitudGasto.objects.create` para
    reemplazar fixtures existentes. `solicitante` o `solicitante_id` son
    obligatorios; una cabecera explícita debe ser coherente con la solicitud.
    """
    if (solicitante is None) == (solicitante_id is None):
        raise ValueError("Indicá exactamente uno de 'solicitante' o 'solicitante_id'.")
    if solicitante is not None:
        solicitante_id = solicitante.pk

    with transaction.atomic():
        numero = pk if pk is not None else reservar_numero_solicitud_gasto()
        if tramite_base is None:
            tramite_base = TramiteBase.objects.create(
                circuito=Circuito.GASTO,
                numero_publico=numero,
                solicitante_actor_id=str(solicitante_id),
                centro_costo_codigo=None,
            )
        datos = {
            "concepto": "Gasto sintético de prueba",
            "monto_estimado": Decimal("10.00"),
            "unidad_requirente": "Unidad sintética",
            "estado": EstadoSolicitud.PRESENTADA,
            "version": 0,
        }
        datos.update(kwargs)
        return SolicitudGasto.objects.create(
            pk=numero,
            tramite_base=tramite_base,
            solicitante_id=solicitante_id,
            **datos,
        )
