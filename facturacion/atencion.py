"""Acciones sugeridas por actor; no escriben estados ni conceden permisos."""

from calendar import monthrange
from dataclasses import dataclass

from django.db.models import CharField, DateTimeField, F, OuterRef, Subquery
from django.db.models.functions import Cast, Coalesce, Greatest
from django.urls import reverse
from django.utils import timezone

from documentos.models import Documento, RevisionDocumento
from documentos.revision import ultima_revision, version_aceptada
from documentos.services import documentos_visibles
from identidad.services import has_capability

from .models import (
    CobroExterno,
    ComprobanteExterno,
    EventoFacturacion,
    RectificacionCobro,
    VerificacionCobro,
)
from .seguimiento import (
    TERMINALES,
    diagnostico_visible,
    importes_cobro,
    puede_actualizar_respaldo,
    respaldo_actual,
    respaldos_solo_rectificados,
)


@dataclass(frozen=True)
class Accion:
    texto: str
    url: str
    descripcion: str = ""


def mensaje_espera(actor, solicitud, importes):
    if solicitud.estado in TERMINALES:
        return ""
    if has_capability(actor, "facturacion.consultar_todas"):
        if solicitud.estado == "OBSERVADA":
            return "El solicitante debe corregir la observación para continuar."
        if importes["hay_factura"] and not importes["registrado"] and importes["neto"] > 0:
            return "El solicitante aún no cargó el cobro correspondiente."
        if importes["hay_factura"] and importes["registrado"] < importes["neto"]:
            return "El solicitante aún debe registrar el cobro del importe restante."
    elif solicitud.tramite_base.solicitante_actor_id == str(actor.subject_id):
        if not importes["hay_factura"]:
            return "Estamos creando la factura, te notificaremos cuando esté lista."
        if importes["pendiente"]:
            return "Estamos validando tus cobros, te notificaremos cuando estén listos."
    return ""


def acciones_inmediatas(actor, solicitud):
    """Orden de trabajo vigente, limitado a acciones que esta cuenta puede ejecutar."""
    if solicitud.estado in TERMINALES:
        return []

    def capacidad(codigo):
        return has_capability(actor, codigo)

    titular = solicitud.tramite_base.solicitante_actor_id == str(actor.subject_id)
    operador = capacidad("facturacion.consultar_todas") and any(
        capacidad(c)
        for c in (
            "facturacion.observar",
            "facturacion.registrar_factura_externa",
            "facturacion.verificar_cobro",
            "facturacion.cerrar",
            "documentos.revisar",
        )
    )
    detalle = reverse("facturacion:detalle", args=[solicitud.pk])
    if solicitud.estado == "OBSERVADA":
        if titular and capacidad("facturacion.corregir"):
            return [
                Accion(
                    "Corregir la solicitud observada",
                    reverse("facturacion:corregir", args=[solicitud.pk]),
                )
            ]
        return []
    acciones = []
    comprobantes = list(solicitud.comprobantes.all())
    cobros = list(solicitud.cobros.all())
    importes = importes_cobro(comprobantes, cobros)
    factura, neto, cubierto = importes["hay_factura"], importes["neto"], importes["registrado"]
    if operador:
        if (
            not factura
            and capacidad("facturacion.registrar_factura_externa")
        ):
            acciones.append(
                Accion(
                    "Registrar factura externa",
                    reverse("facturacion:registrar_comprobante", args=[solicitud.pk]),
                    "Revisá los datos en Ver Detalle y registrá el comprobante emitido.",
                )
            )
        if capacidad("documentos.consultar_metadatos") and capacidad("documentos.revisar"):
            for documento in (
                documentos_visibles(actor)
                .filter(tramite_base=solicitud.tramite_base, sucesor__isnull=True)
                .exclude(pk__in=respaldos_solo_rectificados(cobros))
                .prefetch_related("revisiones")
            ):
                revision = ultima_revision(documento)
                if revision is None:
                    acciones.append(
                        Accion(
                            "Revisar el documento de respaldo",
                            reverse("documentos:revision", args=[documento.pk]),
                            f"Revisá el documento {documento.nombre_original}.",
                        )
                    )
                # Observado/rechazado espera un reemplazo, no otra aprobación sugerida.
        for cobro in cobros:
            if cobro.resultado == "RECTIFICADO":
                continue
            if (
                cobro.resultado == "PENDIENTE"
                and capacidad("facturacion.verificar_cobro")
                and version_aceptada(respaldo_actual(cobro))
            ):
                acciones.append(
                    Accion(
                        "Constatar Ingreso",
                        reverse("facturacion:verificar_cobro", args=[solicitud.pk, cobro.pk]),
                        f"Cotejá el movimiento de la operación {cobro.numero_operacion}.",
                    )
                )
            if puede_actualizar_respaldo(actor):
                anterior = respaldo_actual(cobro)
                revision = ultima_revision(anterior)
                if revision and revision.resultado in {"OBSERVADO", "RECHAZADO"}:
                    acciones.append(
                        Accion(
                            "Modificar cobro",
                            reverse("facturacion:corregir_cobro", args=[solicitud.pk, cobro.pk]),
                            "Vinculá un documento de respaldo válido a la operación "
                            f"{cobro.numero_operacion}.",
                        )
                    )
        if puede_actualizar_respaldo(actor):
            for comprobante in comprobantes:
                documento = respaldo_actual(comprobante)
                if documento is None:
                    continue
                revision = ultima_revision(documento)
                if (revision and revision.resultado in {"OBSERVADO", "RECHAZADO"}) or (
                    Documento.objects.filter(reemplaza=documento).exists()
                ):
                    acciones.append(
                        Accion(
                            "Modificar comprobante externo",
                            reverse(
                                "facturacion:modificar_comprobante",
                                args=[solicitud.pk, comprobante.pk],
                            ),
                            "Vinculá el documento de respaldo vigente a "
                            f"{comprobante.identificacion}.",
                        )
                    )
        if (
            solicitud.presento_comprobante_pago
            and not cobros
            and capacidad("facturacion.registrar_cobro")
            and capacidad("documentos.incorporar")
        ):
            acciones.append(
                Accion(
                    "Registrar cobro declarado",
                    reverse("facturacion:registrar_cobro", args=[solicitud.pk]),
                    "Registrá el ingreso declarado y vinculá su documento de respaldo.",
                )
            )
        if (
            factura
            and 0 < neto <= importes["confirmado"]
            and not importes["pendiente"]
            and capacidad("facturacion.cerrar")
            and capacidad("documentos.consultar_metadatos")
        ):
            diagnostico = diagnostico_visible(actor, solicitud)
            if not diagnostico["faltas_cierre"]:
                acciones.append(
                    Accion(
                        "Ir a resolución",
                        detalle + "#resolucion",
                        "El neto está cubierto y los documentos de respaldo están aceptados.",
                    )
                )
        return acciones
    if titular and capacidad("facturacion.informar_cobro") and capacidad("documentos.incorporar"):
        from .cobros import puede_corregir_cobro

        for cobro in cobros:
            if cobro.resultado == "RECTIFICADO":
                continue
            revision = ultima_revision(respaldo_actual(cobro))
            if puede_corregir_cobro(actor, cobro) and (
                cobro.resultado == "RECHAZADO"
                or (revision and revision.resultado in {"OBSERVADO", "RECHAZADO"})
            ):
                acciones.append(
                    Accion(
                        "Modificar cobro",
                        reverse("facturacion:corregir_cobro", args=[solicitud.pk, cobro.pk]),
                        f"Revisá los datos y el documento de la operación "
                        f"{cobro.numero_operacion}.",
                    )
                )
        # No pedir un segundo ingreso cuando el existente sólo espera a Cooperadora.
        if not acciones and (
            (factura and cubierto < neto) or (solicitud.presento_comprobante_pago and not cobros)
        ):
            acciones.append(
                Accion(
                    "Informar el cobro y aportar su comprobante",
                    reverse("facturacion:registrar_cobro", args=[solicitud.pk]),
                )
            )
    return acciones


def proximidad_cierre(solicitud, hoy=None):
    hoy = hoy or timezone.localdate()
    limite = hoy.replace(day=monthrange(hoy.year, hoy.month)[1] - 6)
    creacion = timezone.localdate(solicitud.fecha_presentacion)
    return hoy >= limite and creacion < limite


def solicitudes_atencion(actor, visibles):
    """Panel independiente de los filtros; orden estable por actualización pertinente."""
    operador = has_capability(actor, "facturacion.consultar_todas")
    eventos = EventoFacturacion.objects.filter(solicitud_id=OuterRef("pk"))
    documentos = Documento.objects.filter(tramite_base_id=OuterRef("tramite_base_id"))
    cobros = CobroExterno.objects.filter(solicitud_id=OuterRef("pk"))
    if operador:
        eventos = eventos.annotate(sujeto=Cast("actor_id", CharField())).filter(
            sujeto=OuterRef("tramite_base__solicitante_actor_id")
        )
        documentos = documentos.annotate(sujeto=Cast("autor_id", CharField())).filter(
            sujeto=OuterRef("tramite_base__solicitante_actor_id")
        )
        cobros = cobros.annotate(sujeto=Cast("actor_id", CharField())).filter(
            sujeto=OuterRef("tramite_base__solicitante_actor_id")
        )
    fuentes = [
        (eventos, "fecha_hora"),
        (documentos, "fecha_incorporacion"),
        (cobros, "fecha_registro"),
    ]
    if not operador:
        fuentes += [
            (
                RevisionDocumento.objects.filter(
                    documento__tramite_base_id=OuterRef("tramite_base_id")
                ),
                "fecha",
            ),
            (ComprobanteExterno.objects.filter(solicitud_id=OuterRef("pk")), "fecha_registro"),
            (VerificacionCobro.objects.filter(cobro__solicitud_id=OuterRef("pk")), "fecha"),
            (
                RectificacionCobro.objects.filter(verificacion__cobro__solicitud_id=OuterRef("pk")),
                "fecha",
            ),
        ]
    fechas = [
        Coalesce(
            Subquery(
                q.order_by("-" + campo, "-pk").values(campo)[:1], output_field=DateTimeField()
            ),
            F("fecha_presentacion"),
        )
        for q, campo in fuentes
    ]
    consulta = (
        visibles.exclude(estado__in=TERMINALES)
        .annotate(ultima_atencion=Greatest(*fechas))
        .prefetch_related("comprobantes", "cobros__verificacion__rectificacion")
        .order_by("-ultima_atencion", "-pk")
    )
    tarjetas = []
    for solicitud in consulta.iterator(chunk_size=25):
        acciones = acciones_inmediatas(actor, solicitud)
        if acciones:
            tarjetas.append(
                dict(
                    solicitud=solicitud,
                    accion=acciones[0],
                    fecha=solicitud.ultima_atencion,
                    cierre_mes=not operador and proximidad_cierre(solicitud),
                )
            )
            if len(tarjetas) == (3 if operador else 2):
                break
    return tarjetas
