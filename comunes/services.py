"""Resolución por circuito y puente temporal hacia gastos sin modificar su app."""

from django.db import transaction
from django.db.models import CharField
from django.db.models.functions import Cast

from gastos.models import SolicitudGasto

from .contracts import ReferenciaCruzadaError, TramiteNoDisponible, TramiteRef
from .models import Circuito, TramiteBase


def resolver_tramite_base(ref: TramiteRef, *, circuito_esperado: str | None = None) -> TramiteBase:
    """Consulta pura: valida circuito, existencia de la hija y coherencia del titular."""
    if circuito_esperado is not None and ref.circuito != circuito_esperado:
        raise ReferenciaCruzadaError("Referencia ajena al circuito consumidor.")
    base = TramiteBase.objects.filter(
        circuito=ref.circuito, numero_publico=ref.numero_publico
    ).first()
    if base is None:
        raise TramiteNoDisponible("Trámite inexistente o no disponible.")
    if base.circuito == Circuito.GASTO:
        # Franco incorporará el OneToOne en gastos. Mientras tanto se conserva
        # la FK documental original y se comprueba el ID público y el titular.
        valida = (
            SolicitudGasto.objects.annotate(titular_texto=Cast("solicitante_id", CharField()))
            .filter(pk=base.numero_publico, titular_texto=base.solicitante_actor_id)
            .exists()
        )
    else:
        from facturacion.models import SolicitudFacturacion

        valida = SolicitudFacturacion.objects.filter(
            pk=base.numero_publico, tramite_base=base
        ).exists()
    if not valida:
        raise TramiteNoDisponible("Cabecera sin solicitud coherente.")
    return base


@transaction.atomic
def registrar_cabecera_gasto(gasto: SolicitudGasto) -> TramiteBase:
    """Alta del puente en una escritura autorizada; nunca se llama desde un GET."""
    # Bloquear el gasto serializa altas del puente y conserva el orden C01:
    # gasto -> cabecera -> versión documental.
    actual = SolicitudGasto.objects.select_for_update().get(pk=gasto.pk)
    base, _ = TramiteBase.objects.get_or_create(
        circuito=Circuito.GASTO,
        numero_publico=actual.pk,
        defaults={"solicitante_actor_id": str(actual.solicitante_id)},
    )
    return resolver_tramite_base(base.referencia, circuito_esperado=Circuito.GASTO)
