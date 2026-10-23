"""Visibilidad documental por circuito; no deriva autoridad de staff ni superusuario."""

from dataclasses import dataclass

from django.db.models import CharField, F, Q
from django.db.models.functions import Cast

from comunes.contracts import TramiteNoDisponible, TramiteRef
from comunes.models import Circuito, TramiteBase
from comunes.services import resolver_tramite_base
from gastos.models import SolicitudGasto
from gastos.queries import visible_expenses
from identidad.services import Actor, has_capability

from .models import Documento


class DocumentoNoVisible(LookupError):
    """Error uniforme para objetos inexistentes o ajenos (HTTP 404)."""


def bloquear_facturacion_abierta(base):
    """Orden común con resolución: cabecera antes de raíz documental; gastos no cambia."""
    if base.circuito == Circuito.FACTURACION:
        from django.core.exceptions import PermissionDenied

        bloqueada = TramiteBase.objects.select_for_update().get(pk=base.pk)
        if bloqueada.solicitud_facturacion.estado in {"CERRADA", "ANULADA"}:
            raise PermissionDenied("El trámite es terminal y sólo admite consulta.")


@dataclass(frozen=True)
class DestinoDocumental:
    ref: TramiteRef
    base: TramiteBase | None
    gasto: SolicitudGasto | None


def destino_visible(actor: Actor | None, referencia: str) -> DestinoDocumental:
    """Resuelve sin escribir; los gastos nuevos pueden no tener aún cabecera."""
    try:
        ref = TramiteRef.desde_texto(referencia)
    except ValueError as exc:
        raise DocumentoNoVisible("Trámite inexistente o no visible.") from exc
    if ref.circuito == Circuito.GASTO:
        gasto = visible_expenses(actor).filter(pk=ref.numero_publico).first()
        if gasto is None:
            raise DocumentoNoVisible("Trámite inexistente o no visible.")
        base = TramiteBase.objects.filter(
            circuito=ref.circuito, numero_publico=ref.numero_publico
        ).first()
        if base and base.solicitante_actor_id != str(gasto.solicitante_id):
            raise DocumentoNoVisible("Trámite inexistente o no visible.")
        return DestinoDocumental(ref, base, gasto)
    try:
        base = resolver_tramite_base(ref)
    except TramiteNoDisponible as exc:
        raise DocumentoNoVisible("Trámite inexistente o no visible.") from exc
    puede_ver = has_capability(actor, "facturacion.consultar_todas") or (
        has_capability(actor, "facturacion.consultar_propias")
        and base.solicitante_actor_id == str(actor.subject_id)
    )
    if not puede_ver:
        raise DocumentoNoVisible("Trámite inexistente o no visible.")
    return DestinoDocumental(ref, base, None)


def documentos_visibles(actor: Actor | None):
    """Filtra también la coherencia del puente si cambia el gasto legado."""
    gastos = Q(
        solicitud_gasto__in=visible_expenses(actor),
        tramite_base__circuito=Circuito.GASTO,
        tramite_base__numero_publico=F("solicitud_gasto_id"),
        tramite_base__solicitante_actor_id=Cast(F("solicitud_gasto__solicitante_id"), CharField()),
    )
    facturacion = Q(pk__in=[])
    if has_capability(actor, "facturacion.consultar_todas"):
        facturacion = Q(tramite_base__solicitud_facturacion__isnull=False)
    elif has_capability(actor, "facturacion.consultar_propias"):
        facturacion = Q(
            tramite_base__solicitud_facturacion__isnull=False,
            tramite_base__solicitante_actor_id=str(actor.subject_id),
        )
    return Documento.objects.filter(gastos | facturacion).select_related("tramite_base")
