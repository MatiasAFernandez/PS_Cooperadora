"""Visibilidad y acciones propias de facturación; independientes de grupos concretos."""

from django.core.exceptions import PermissionDenied

from identidad.services import has_capability

from .models import SolicitudFacturacion


class ObjetoNoVisibleError(LookupError):
    pass


def filtrar_solicitudes_visibles(actor):
    qs = SolicitudFacturacion.objects.operativas().select_related("tramite_base")
    if has_capability(actor, "facturacion.consultar_todas"):
        return qs
    if has_capability(actor, "facturacion.consultar_propias"):
        return qs.filter(tramite_base__solicitante_actor_id=str(actor.subject_id))
    return qs.none()


def verificar_visible(actor, solicitud):
    if not filtrar_solicitudes_visibles(actor).filter(pk=solicitud.pk).exists():
        raise ObjetoNoVisibleError("Solicitud inexistente o no visible.")


def verificar_accion(actor, solicitud, accion):
    verificar_visible(actor, solicitud)
    if accion not in {"observar", "corregir"} or not has_capability(actor, f"facturacion.{accion}"):
        raise PermissionDenied("No tenés permiso para esta acción.")
    if accion == "corregir" and solicitud.tramite_base.solicitante_actor_id != str(
        actor.subject_id
    ):
        raise PermissionDenied("Solo el titular puede corregir.")
