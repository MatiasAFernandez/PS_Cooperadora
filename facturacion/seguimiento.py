"""Diagnóstico reproducible y resolución explícita del trámite de facturación."""

import hashlib
import json
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from comunes.models import TramiteBase
from documentos.acceso import documentos_visibles
from documentos.models import Documento, RevisionDocumento
from documentos.operaciones import operacion_documental
from documentos.policy import ArchivoInvalido, validar_archivo
from documentos.revision import version_aceptada
from documentos.services import bloquear_serie, incorporar
from identidad.services import has_capability

from .choices import ModalidadCobro
from .models import ActualizacionRespaldo, SolicitudFacturacion
from .permissions import ObjetoNoVisibleError, filtrar_solicitudes_visibles
from .workflow import ConflictoConcurrenciaError, _evento, _serializar

TERMINALES = {"CERRADA", "ANULADA"}


def estado_visible(solicitud):
    if solicitud.estado != "PRESENTADA":
        return solicitud.get_estado_display()
    comprobantes = list(solicitud.comprobantes.all())
    if not any(c.tipo == "FACTURA" for c in comprobantes):
        return "Presentada"
    neto = sum((-c.importe if c.tipo == "NOTA_CREDITO" else c.importe) for c in comprobantes)
    confirmado = sum(c.importe for c in solicitud.cobros.all() if c.resultado == "CONFIRMADO")
    return (
        "Cobrada en revisión"
        if neto >= 0 and confirmado >= neto
        else "Facturada pendiente de cobro"
    )


def exigir_abierta(solicitud):
    if solicitud.estado in TERMINALES:
        raise PermissionDenied("El trámite es terminal y sólo admite consulta.")


def motivo_valido(motivo):
    if not isinstance(motivo, str) or not motivo.strip() or len(motivo) > 2000 or "\x00" in motivo:
        raise ValidationError("Indicá un motivo con texto de hasta 2000 caracteres.")
    return motivo.strip()


def respaldo_actual(objeto):
    actualizacion = objeto.actualizaciones_respaldo.select_related("nuevo").last()
    return actualizacion.nuevo if actualizacion else objeto.documento


def diagnostico(solicitud):
    comprobantes = list(solicitud.comprobantes.select_related("documento"))
    cobros = list(solicitud.cobros.select_related("documento", "verificacion"))
    neto = sum(
        ((-c.importe if c.tipo == "NOTA_CREDITO" else c.importe) for c in comprobantes),
        Decimal("0.00"),
    )
    confirmado = sum((c.importe for c in cobros if c.resultado == "CONFIRMADO"), Decimal("0.00"))
    pendientes = [c for c in cobros if c.resultado == "PENDIENTE"]
    factura = any(c.tipo == "FACTURA" for c in comprobantes)
    faltas_cierre, faltas_anulacion = [], []
    if not factura:
        faltas_cierre.append("Falta registrar la factura.")
    if neto <= 0:
        faltas_cierre.append("El cierre normal exige neto positivo.")
    if confirmado != neto:
        faltas_cierre.append("El total confirmado debe ser exactamente igual al neto.")
    if solicitud.estado == "OBSERVADA":
        faltas_cierre.append("La observación de la solicitud sigue pendiente de corrección.")
    if pendientes:
        mensaje = "Hay ingresos pendientes de verificación."
        faltas_cierre.append(mensaje)
        faltas_anulacion.append(mensaje)
    if (
        solicitud.presento_comprobante_pago
        and solicitud.modalidad_cobro in {"MERCADO_PAGO", "BNA_COMUN", "BNA_UVT", "NBCH"}
        and not any(
            c.medio == solicitud.modalidad_cobro
            and c.numero_operacion == solicitud.numero_operacion_declarado.strip()
            for c in cobros
        )
    ):
        mensaje = (
            "La operación declarada inicialmente aún debe registrarse y verificarse como cobro."
        )
        faltas_cierre.append(mensaje)
        faltas_anulacion.append(mensaje)
    if confirmado:
        faltas_anulacion.append(
            "Hay ingresos confirmados; falta definir su regularización/devolución."
        )
    if factura and neto != 0:
        faltas_anulacion.append(
            "La factura sólo permite anulación cuando su neto es exactamente cero."
        )
    documentos, faltas_documentales = [], []
    for objeto in [*comprobantes, *(c for c in cobros if c.resultado == "CONFIRMADO")]:
        documento = respaldo_actual(objeto)
        documentos.append(documento)
        if not version_aceptada(documento):
            etiqueta = (
                objeto.identificacion
                if objeto in comprobantes
                else (
                    f"Cobro {objeto.numero_operacion} "
                    f"({dict(ModalidadCobro.choices).get(objeto.medio, objeto.medio)})"
                )
            )
            mensaje = (
                f'{etiqueta} — respaldo "{documento.nombre_original}", '
                f"versión {documento.version}: debe ser vigente y estar ACEPTADO."
            )
            faltas_documentales.append(mensaje)
            faltas_cierre.append(mensaje)
            if objeto in comprobantes:
                faltas_anulacion.append(mensaje)
    # Incluye todos los aportes/revisiones: una pantalla anterior no resuelve un trámite cambiado.
    docs = list(
        Documento.objects.filter(tramite_base=solicitud.tramite_base).values_list(
            "pk", "reemplaza_id"
        )
    )
    revisiones = list(
        RevisionDocumento.objects.filter(
            documento__tramite_base=solicitud.tramite_base
        ).values_list("pk", flat=True)
    )
    actualizaciones = list(
        ActualizacionRespaldo.objects.filter(comprobante__solicitud=solicitud).values_list(
            "pk", flat=True
        )
    ) + list(
        ActualizacionRespaldo.objects.filter(cobro__solicitud=solicitud).values_list(
            "pk", flat=True
        )
    )
    datos = [
        solicitud.pk,
        solicitud.estado,
        solicitud.version_concurrencia,
        sorted(c.pk for c in comprobantes),
        sorted((c.pk, c.resultado) for c in cobros),
        sorted(docs),
        sorted(revisiones),
        sorted(actualizaciones),
    ]
    revision = hashlib.sha256(json.dumps(datos).encode()).hexdigest()
    estado = solicitud.estado
    if estado == "PRESENTADA" and factura:
        estado = (
            "COBRADA_EN_REVISION"
            if neto >= 0 and confirmado >= neto
            else "FACTURADA_PENDIENTE_COBRO"
        )
    return dict(
        neto=neto,
        confirmado=confirmado,
        diferencia=neto - confirmado,
        exceso=max(confirmado - neto, Decimal("0.00")),
        estado=estado,
        faltas_cierre=faltas_cierre,
        faltas_anulacion=faltas_anulacion,
        revision=revision,
        terminal=solicitud.estado in TERMINALES,
        documentos=documentos,
        faltas_documentales=faltas_documentales,
    )


def diagnostico_visible(actor, solicitud):
    resultado = diagnostico(solicitud)
    if not has_capability(actor, "documentos.consultar_metadatos"):
        for campo in ("faltas_cierre", "faltas_anulacion"):
            resultado[campo] = [
                m for m in resultado[campo] if m not in resultado["faltas_documentales"]
            ]
            resultado[campo].append("Condiciones documentales no disponibles para esta cuenta.")
        resultado["documentos"] = []
        resultado["faltas_documentales"] = []
    return resultado


def _bloquear(actor, numero, capacidad):
    if not filtrar_solicitudes_visibles(actor).filter(pk=numero).exists():
        raise ObjetoNoVisibleError
    if not has_capability(actor, capacidad):
        raise PermissionDenied("No tenés permiso para esta acción del trámite.")
    if not has_capability(actor, "documentos.consultar_metadatos"):
        raise PermissionDenied("Se requiere permiso de metadatos para resolver el trámite.")
    base = TramiteBase.objects.select_for_update().get(
        circuito="FACTURACION", numero_publico=numero
    )
    solicitud = SolicitudFacturacion.objects.select_for_update().get(tramite_base=base)
    if solicitud.estado in TERMINALES:
        raise ConflictoConcurrenciaError("El trámite ya tiene una resolución definitiva.")
    return solicitud


def resolver_tramite(*, actor, numero, accion, motivo, revision_esperada):
    if accion not in {"cerrar", "anular"}:
        raise ValidationError("Acción de resolución inválida.")
    with transaction.atomic():
        solicitud = _bloquear(actor, numero, f"facturacion.{accion}")
        motivo = motivo_valido(motivo)
        estado = diagnostico(solicitud)
        if revision_esperada != estado["revision"]:
            raise ConflictoConcurrenciaError("El trámite cambió. Recargá el detalle.")
        faltas = estado["faltas_cierre" if accion == "cerrar" else "faltas_anulacion"]
        if faltas:
            raise ValidationError(faltas)
        antes = _serializar(solicitud)
        solicitud.estado = "CERRADA" if accion == "cerrar" else "ANULADA"
        solicitud.version_concurrencia += 1
        solicitud.save(update_fields=["estado", "version_concurrencia"])
        _evento(
            solicitud, actor, "CIERRE" if accion == "cerrar" else "ANULACION", antes, nota=motivo
        )
        return solicitud


def actualizar_respaldo(
    *, actor, numero, clase, objeto_id, nuevo_id=None, archivo=None, motivo, revision_esperada
):
    with operacion_documental() as escrituras:
        solicitud = _bloquear(actor, numero, "facturacion.actualizar_respaldo")
        if not has_capability(actor, "documentos.consultar_metadatos"):
            raise PermissionDenied("Se requiere permiso de metadatos.")
        if revision_esperada != diagnostico(solicitud)["revision"]:
            raise ConflictoConcurrenciaError("El trámite cambió. Recargá el detalle.")
        if clase not in {"comprobante", "cobro"}:
            raise ValidationError("Tipo de registro inválido.")
        objeto = (
            (solicitud.comprobantes if clase == "comprobante" else solicitud.cobros)
            .filter(pk=objeto_id)
            .first()
        )
        if objeto is None:
            raise ObjetoNoVisibleError
        anterior = respaldo_actual(objeto)
        bloquear_serie(anterior)
        if bool(nuevo_id) == bool(archivo):
            raise ValidationError("Elegí una versión existente o un nuevo archivo, sólo uno.")
        if archivo:
            validado = validar_archivo(archivo)
            if clase == "comprobante" and validado.formato != "application/pdf":
                raise ArchivoInvalido("El comprobante externo requiere PDF.")
            nuevo = incorporar(
                actor=actor,
                referencia=f"facturacion:{numero}",
                archivo=validado,
                tipo=anterior.tipo,
                procedencia="EXTERNO_BANCO"
                if anterior.tipo == "COMPROBANTE_COBRO"
                else objeto.procedencia,
                reemplaza_id=anterior.pk,
                _escrituras=escrituras,
            )
            nuevo_id = nuevo.pk
        nuevo = (
            documentos_visibles(actor)
            .filter(
                pk=nuevo_id,
                tramite_base=solicitud.tramite_base,
                serie=anterior.serie,
                tipo=anterior.tipo,
                version__gt=anterior.version,
            )
            .first()
        )
        if nuevo is None or Documento.objects.filter(reemplaza=nuevo).exists():
            raise ValidationError(
                "Elegí la versión sucesora vigente del mismo trámite, tipo y serie."
            )
        if clase == "comprobante" and nuevo.procedencia != objeto.procedencia:
            raise ValidationError("La versión debe conservar el origen del comprobante.")
        if clase == "comprobante" and nuevo.formato != "application/pdf":
            raise ValidationError("El comprobante externo requiere PDF.")
        otros = solicitud.comprobantes if clase == "comprobante" else solicitud.cobros
        if otros.exclude(pk=objeto.pk).filter(documento=nuevo).exists() or (
            ActualizacionRespaldo.objects.filter(nuevo=nuevo).exists()
        ):
            raise ValidationError("Esa versión ya respalda otro registro.")
        return ActualizacionRespaldo.objects.create(
            **{clase: objeto},
            anterior=anterior,
            nuevo=nuevo,
            actor_id=actor.subject_id,
            motivo=motivo_valido(motivo),
        )
