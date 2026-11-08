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


TIPOS_RESPALDO_COMERCIAL = (
    Documento.Tipo.FACTURA_PROVEEDOR,
    Documento.Tipo.PRESUPUESTO_PROFORMA,
    Documento.Tipo.TICKET_NO_FISCAL,
)


@dataclass(frozen=True, slots=True)
class RespaldoTitularProyectado:
    documento_id: int
    tipo: str
    tipo_mostrado: str
    nombre: str
    fecha: datetime
    estado_revision: str
    resultado: str | None
    motivo: str | None
    puede_reemplazar: bool = False
    version: int = 1


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


def _ids_vinculados_pago(gasto_pk: int) -> set[int]:
    ids: set[int] = set()
    from gastos.models import PagoExterno

    pago = (
        PagoExterno.objects.filter(solicitud_id=gasto_pk)
        .select_related("original")
        .prefetch_related("cambios")
        .first()
    )
    if pago is not None:
        if pago.comprobante_bancario_id:
            ids.add(pago.comprobante_bancario_id)
        if pago.constancia_atp_id:
            ids.add(pago.constancia_atp_id)
        original = getattr(pago, "original", None)
        if original is not None:
            if original.comprobante_bancario_id:
                ids.add(original.comprobante_bancario_id)
            if original.constancia_atp_id:
                ids.add(original.constancia_atp_id)
        for cambio in pago.cambios.all():
            if cambio.documento_anterior_id:
                ids.add(cambio.documento_anterior_id)
            if cambio.documento_nuevo_id:
                ids.add(cambio.documento_nuevo_id)
    return ids


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

    ids_vinculados_pago = _ids_vinculados_pago(gasto.pk)

    qs = documentos_visibles(actor).filter(solicitud_gasto_id=gasto.pk)
    if ids_vinculados_pago:
        qs = qs.exclude(pk__in=ids_vinculados_pago)

    documentos = list(
        qs
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


def proyectar_respaldos_titular(
    actor: Actor | None, gasto: SolicitudGasto
) -> list[RespaldoTitularProyectado] | None:
    """Proyecta metadatos mínimos de respaldos comerciales vigentes para su titular.

    Autoriza únicamente la titularidad del gasto y la consulta en documentos_visibles.
    Sólo incluye FACTURA_PROVEEDOR, PRESUPUESTO_PROFORMA y TICKET_NO_FISCAL.
    Metadatos mínimos: tipo, nombre, fecha, estado de última revisión y motivo
    cuando la versión fue observada o rechazada. No expone historial, revisiones
    previas, enlaces de descarga ni referencias internas.
    Devuelve None si no aplica, o una lista (vacía si no tiene documentos).
    """
    if actor is None or getattr(actor, "subject_id", None) != gasto.solicitante_id:
        return None

    ids_vinculados_pago = _ids_vinculados_pago(gasto.pk)

    qs = (
        documentos_visibles(actor)
        .filter(
            solicitud_gasto_id=gasto.pk,
            tipo__in=TIPOS_RESPALDO_COMERCIAL,
        )
    )
    if ids_vinculados_pago:
        qs = qs.exclude(pk__in=ids_vinculados_pago)

    documentos = list(
        qs.annotate(
            reemplazada=Exists(Documento.objects.filter(reemplaza=OuterRef("pk")))
        )
        .filter(reemplazada=False)
        .prefetch_related(
            Prefetch(
                "revisiones",
                queryset=RevisionDocumento.objects.order_by("fecha", "id"),
                to_attr="revisiones_proyectadas",
            )
        )
        .order_by("fecha_incorporacion", "pk")
    )

    puede_incorporar = has_capability(actor, "documentos.incorporar")
    respaldos: list[RespaldoTitularProyectado] = []
    for doc in documentos:
        revisiones = getattr(doc, "revisiones_proyectadas", ())
        if revisiones:
            ultima = revisiones[-1]
            resultado = ultima.resultado
            estado_revision = ultima.get_resultado_display()
            motivo = (
                ultima.motivo
                if ultima.resultado
                in (
                    RevisionDocumento.Resultado.OBSERVADO,
                    RevisionDocumento.Resultado.RECHAZADO,
                )
                else None
            )
        else:
            resultado = None
            estado_revision = "Pendiente de revisión"
            motivo = None

        puede_reemplazar = bool(
            puede_incorporar
            and doc.autor_id == actor.subject_id
            and doc.procedencia == Documento.Procedencia.SOLICITANTE
            and doc.procedencia != Documento.Procedencia.INTERNO_COOPERADORA
            and resultado
            in (
                RevisionDocumento.Resultado.OBSERVADO,
                RevisionDocumento.Resultado.RECHAZADO,
            )
            and doc.tipo in TIPOS_RESPALDO_COMERCIAL
        )

        respaldos.append(
            RespaldoTitularProyectado(
                documento_id=doc.pk,
                tipo=doc.tipo,
                tipo_mostrado=doc.get_tipo_display(),
                nombre=doc.nombre_original,
                fecha=doc.fecha_incorporacion,
                estado_revision=estado_revision,
                resultado=resultado,
                motivo=motivo,
                puede_reemplazar=puede_reemplazar,
                version=doc.version,
            )
        )

    return respaldos


def obtener_versiones_reemplazables_titular(
    actor: Actor | None,
    gasto: SolicitudGasto,
    combinaciones: dict[str, tuple[str, ...]],
) -> tuple[VersionDocumentalProyectada, ...]:
    """Obtiene opciones de reemplazo para versiones observadas o rechazadas del titular.

    Excluye archivos aportados por Cooperadora, versiones aceptadas o pendientes,
    versiones ya reemplazadas y tipos no permitidos por combinaciones actuales
    para el actor.
    """
    if actor is None or getattr(actor, "subject_id", None) != gasto.solicitante_id:
        return ()
    if not has_capability(actor, "documentos.incorporar"):
        return ()

    ids_vinculados_pago = _ids_vinculados_pago(gasto.pk)

    qs = (
        documentos_visibles(actor)
        .filter(
            solicitud_gasto_id=gasto.pk,
            autor_id=actor.subject_id,
            procedencia=Documento.Procedencia.SOLICITANTE,
            tipo__in=tuple(combinaciones),
        )
        .exclude(procedencia=Documento.Procedencia.INTERNO_COOPERADORA)
    )
    if ids_vinculados_pago:
        qs = qs.exclude(pk__in=ids_vinculados_pago)

    documentos = list(
        qs.annotate(
            reemplazada=Exists(Documento.objects.filter(reemplaza=OuterRef("pk")))
        )
        .filter(reemplazada=False)
        .prefetch_related(
            Prefetch(
                "revisiones",
                queryset=RevisionDocumento.objects.order_by("fecha", "id"),
                to_attr="revisiones_proyectadas",
            )
        )
        .order_by("fecha_incorporacion", "pk")
    )

    versiones: list[VersionDocumentalProyectada] = []
    for doc in documentos:
        revs = getattr(doc, "revisiones_proyectadas", ())
        if not revs:
            continue
        ultima = revs[-1]
        if ultima.resultado not in (
            RevisionDocumento.Resultado.OBSERVADO,
            RevisionDocumento.Resultado.RECHAZADO,
        ):
            continue

        rev_proyectada = RevisionDocumentalProyectada(
            resultado=ultima.resultado,
            resultado_mostrado=ultima.get_resultado_display(),
            motivo=ultima.motivo,
            actor_id=ultima.actor_id,
            fecha=ultima.fecha,
        )
        versiones.append(
            VersionDocumentalProyectada(
                documento_id=doc.pk,
                tipo=doc.tipo,
                tipo_mostrado=doc.get_tipo_display(),
                nombre=doc.nombre_original,
                version=doc.version,
                actor_id=doc.autor_id,
                fecha_incorporacion=doc.fecha_incorporacion,
                vigente=True,
                revisiones=(rev_proyectada,),
            )
        )

    return tuple(versiones)
