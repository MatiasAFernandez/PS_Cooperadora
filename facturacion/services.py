"""Fábrica técnica de solicitudes para contratos; sin formulario ni emisión fiscal."""

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction

from comunes.models import Circuito, TramiteBase
from identidad.services import Actor, has_capability

from .models import SolicitudFacturacion


@transaction.atomic
def crear_solicitud_tecnica(
    *, actor: Actor, centro_costo_codigo: str | None = None
) -> SolicitudFacturacion:
    """Reserva un número sin colisiones y crea cabecera y solicitud juntas.

    El número público conserva el PK del circuito. PostgreSQL reserva la
    secuencia antes de insertar ambas filas; un rollback puede dejar un hueco,
    pero nunca reutiliza el número de otro trámite concurrente.
    """
    if not has_capability(actor, "facturacion.presentar"):
        raise PermissionDenied("Capacidad de facturación insuficiente.")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence('facturacion_solicitudfacturacion', 'id'))"
        )
        numero = cursor.fetchone()[0]
    base = TramiteBase.objects.create(
        circuito=Circuito.FACTURACION,
        numero_publico=numero,
        solicitante_actor_id=str(actor.subject_id),
        centro_costo_codigo=centro_costo_codigo,
    )
    return SolicitudFacturacion.objects.create(pk=numero, tramite_base=base)
