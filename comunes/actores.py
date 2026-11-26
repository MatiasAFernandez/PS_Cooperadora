"""Resolución compartida de nombres visibles y presentación de historial."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth import get_user_model

from comunes.contracts import EventoHistorialDTO
from comunes.templatetags.formato_ars import actor_visible as _actor_visible
from comunes.templatetags.formato_ars import estado_historial as _estado_historial


@dataclass(frozen=True)
class EventoHistorialPresentacion:
    """Envoltorio de presentación para `comunes/historial_evento.html` sin `{% load %}`."""

    evento_id: int
    tramite_ref: str
    tipo_evento: str
    actor_id: str
    fecha_hora: datetime | None
    estado_resultante: str
    motivo_o_detalle: str
    actor_visible: str
    estado_visible: str


def resolver_actores_visibles(
    actor_ids: Iterable[object],
    *,
    puede_ver_internos: bool,
    titular_actor_id: object | None = None,
) -> dict[str, str]:
    """Resuelve `actor_id -> rótulo visible` respetando privacidad por rol.

    - Perfiles internos (`puede_ver_internos=True`): devuelve nombre completo o
      `username` en una única consulta `User.objects.filter(pk__in=...)`.
    - Solicitantes (`puede_ver_internos=False`): devuelve `Titular` para el actor
      propietario del trámite y `Cooperadora` para cualquier otro actor.
    """
    ids_texto = {str(raw) for raw in actor_ids if raw is not None and str(raw).strip()}
    if not ids_texto:
        return {}

    if puede_ver_internos:
        ids_int = [int(clave) for clave in ids_texto if clave.isdigit()]
        if not ids_int:
            return {}
        user_model = get_user_model()
        mapa: dict[str, str] = {}
        for usuario in user_model.objects.filter(pk__in=ids_int).only(
            "id", "username", "first_name", "last_name"
        ):
            nombre = usuario.get_full_name().strip() or usuario.get_username()
            mapa[str(usuario.pk)] = nombre
        return mapa

    titular_clave = str(titular_actor_id) if titular_actor_id is not None else ""
    return {
        clave: ("Titular" if titular_clave and clave == titular_clave else "Cooperadora")
        for clave in ids_texto
    }


def presentar_historial(
    eventos: Iterable[EventoHistorialDTO],
    actores_visibles: dict[str, str] | None = None,
) -> list[EventoHistorialPresentacion]:
    """Adapta `EventoHistorialDTO` con actor y estado humanizados sin mutar el DTO."""
    return [
        EventoHistorialPresentacion(
            evento_id=evento.evento_id,
            tramite_ref=evento.tramite_ref,
            tipo_evento=evento.tipo_evento,
            actor_id=evento.actor_id,
            fecha_hora=evento.fecha_hora,
            estado_resultante=evento.estado_resultante,
            motivo_o_detalle=evento.motivo_o_detalle,
            actor_visible=_actor_visible(evento.actor_id, actores_visibles),
            estado_visible=_estado_historial(evento.estado_resultante),
        )
        for evento in eventos
    ]
