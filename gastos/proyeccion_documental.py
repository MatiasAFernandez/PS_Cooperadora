"""Proyección de versiones y revisiones documentales en el detalle de gastos.

Reutiliza la consulta autorizada de documentos y los hechos inmutables de
revisión. No registra revisiones, no modifica pagos ni trámites y no expone
referencias internas de versión, serie, archivo o hash.
"""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import Exists, OuterRef, Prefetch

from comunes.contracts import EventoHistorialDTO
from documentos.acceso import documentos_visibles
from documentos.models import Documento, RevisionDocumento
from gastos.auth import has_capability
from gastos.models import SolicitudGasto
from identidad.services import Actor

CAPACIDAD_CONSULTA_DOCUMENTAL = "documentos.consultar_metadatos"
TIPO_EVENTO_APORTE = "aporte_documental"


@dataclass(frozen=True, slots=True)
class RevisionDocumentalProyectada:
    resultado: str
    resultado_mostrado: str
    motivo: str
    actor_id: int
    fecha: datetime


@dataclass(frozen=True, slots=True)
class VersionDocumentalProyectada:
    documento_id: int
    tipo: str
    tipo_mostrado: str
    nombre: str
    version: int
    actor_id: int
    fecha_incorporacion: datetime
    vigente: bool
    revisiones: tuple[RevisionDocumentalProyectada, ...]

    @property
    def revision_actual(self) -> RevisionDocumentalProyectada | None:
        return self.revisiones[-1] if self.revisiones else None


@dataclass(frozen=True, slots=True)
class ProyeccionDocumental:
    versiones: tuple[VersionDocumentalProyectada, ...]
    eventos: tuple[EventoHistorialDTO, ...]


def _proyectar_revision(revision: RevisionDocumento) -> RevisionDocumentalProyectada:
    return RevisionDocumentalProyectada(
        resultado=revision.resultado,
        resultado_mostrado=revision.get_resultado_display(),
        motivo=revision.motivo,
        actor_id=revision.actor_id,
        fecha=revision.fecha,
    )


def _evento_aporte(documento: Documento) -> EventoHistorialDTO:
    detalle = (
        f"{documento.get_tipo_display()} — {documento.nombre_original} — "
        f"versión {documento.version}."
    )
    return EventoHistorialDTO(
        evento_id=documento.pk,
        tramite_ref=f"gastos:{documento.solicitud_gasto_id}",
        tipo_evento=TIPO_EVENTO_APORTE,
        actor_id=str(documento.autor_id),
        fecha_hora=documento.fecha_incorporacion,
        estado_resultante="APORTADO",
        motivo_o_detalle=detalle,
    )


def proyectar_documentos(
    actor: Actor | None, gasto: SolicitudGasto
) -> ProyeccionDocumental | None:
    """Proyecta versiones y hechos o devuelve None si falta la capacidad.

    La visibilidad del gasto y de cada documento se resuelve con las consultas
    autorizadas existentes. Las versiones reemplazadas se conservan y cada una
    mantiene sus propias revisiones; ninguna hereda el resultado de otra.
    """
    if not has_capability(actor, CAPACIDAD_CONSULTA_DOCUMENTAL):
        return None

    documentos = list(
        documentos_visibles(actor)
        .filter(solicitud_gasto_id=gasto.pk)
        .annotate(
            reemplazada=Exists(Documento.objects.filter(reemplaza=OuterRef("pk")))
        )
        .prefetch_related(
            Prefetch(
                "revisiones",
                queryset=RevisionDocumento.objects.select_related(
                    "documento__tramite_base"
                ).order_by("fecha", "id"),
                to_attr="revisiones_proyectadas",
            )
        )
        .order_by("fecha_incorporacion", "pk")
    )

    versiones: list[VersionDocumentalProyectada] = []
    eventos: list[EventoHistorialDTO] = []
    for documento in documentos:
        revisiones = tuple(
            _proyectar_revision(revision)
            for revision in documento.revisiones_proyectadas
        )
        versiones.append(
            VersionDocumentalProyectada(
                documento_id=documento.pk,
                tipo=documento.tipo,
                tipo_mostrado=documento.get_tipo_display(),
                nombre=documento.nombre_original,
                version=documento.version,
                actor_id=documento.autor_id,
                fecha_incorporacion=documento.fecha_incorporacion,
                vigente=not documento.reemplazada,
                revisiones=revisiones,
            )
        )
        eventos.append(_evento_aporte(documento))
        eventos.extend(
            revision.como_historial()
            for revision in documento.revisiones_proyectadas
        )

    return ProyeccionDocumental(tuple(versiones), tuple(eventos))
