"""Servicios de negocio para el módulo de gastos."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection, transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from comunes.models import Circuito, TramiteBase
from documentos.models import Documento, RevisionDocumento
from gastos.auth import has_capability
from gastos.datos_transferencia import validar_datos_transferencia
from gastos.models import (
    CentroCosto,
    DecisionGasto,
    EstadoSolicitud,
    PagoExterno,
    ParametroOperativo,
    RevisionDatosTransferencia,
    SolicitudGasto,
    SubsanacionGasto,
    TipoFlujoGasto,
)
from gastos.queries import visible_expenses


class ExpenseError(Exception):
    """Excepción base para errores de negocio del módulo de gastos."""


class ExpenseNotFoundError(ExpenseError):
    """Solicitud no encontrada o no visible para el actor (HTTP 404)."""


class ExpensePermissionDeniedError(ExpenseError):
    """Actor no autorizado para decidir sobre la solicitud (HTTP 403)."""


class InvalidDecisionInputError(ExpenseError):
    """Acción, versión o motivo inválidos validados dentro del servicio (HTTP 400)."""


class InvalidSubsanacionInputError(ExpenseError):
    """Datos o versión inválidos al subsanar una solicitud observada (HTTP 400)."""


class ConcurrencyConflictError(ExpenseError):
    """Versión desactualizada de la solicitud (HTTP 409)."""


class InvalidTransitionError(ExpenseError):
    """Transición no permitida desde el estado actual en base de datos (HTTP 409)."""


class DeudaDocumentalBloqueoError(ExpenseError):
    """Lanzada cuando un solicitante supera el máximo permitido de trámites en mora documental."""

    def __init__(
        self,
        mensaje: str,
        solicitudes_en_mora: tuple[Any, ...] | list[Any] = (),
    ) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.solicitudes_en_mora = tuple(solicitudes_en_mora)


def can_decide_expense(actor: Any, expense: SolicitudGasto, action: str) -> bool:
    """Verifica si el actor puede ejecutar una acción de decisión sobre la solicitud.

    Garantías del contrato v1:
    - Consulta pura sin escrituras ni efectos secundarios en base de datos.
    - Actor ausente o acción desconocida retorna False.
    - Exige capacidad 'gastos.decidir'.
    - Exige que la solicitud sea visible para el actor según visible_expenses(actor).
    - Exige que el solicitante sea distinto del actor (prohibición de auto-decisión H2).
    - Exige que la transición solicitada sea válida desde el estado actual.
    """
    if actor is None or not action:
        return False

    if action not in {"aceptar", "observar", "postergar", "rechazar"}:
        return False

    if not has_capability(actor, "gastos.decidir"):
        return False

    # Prohibición provisional de auto-decisión de demo (H2)
    if expense.solicitante_id == actor.subject_id:
        return False

    # Comprobación de visibilidad efectiva
    if not visible_expenses(actor).filter(pk=expense.pk).exists():
        return False

    # Matriz de transiciones permitidas
    if expense.estado == EstadoSolicitud.PRESENTADA:
        return action in {"aceptar", "observar", "postergar", "rechazar"}

    if expense.estado == EstadoSolicitud.POSTERGADA:
        return action in {"aceptar", "observar", "rechazar"}

    # Estados OBSERVADA, ACEPTADA y RECHAZADA no admiten decisión del operador
    return False


def _validar_version_entera(expected_version: Any, exc_cls: type[ExpenseError]) -> int:
    """Valida que expected_version sea un entero no negativo sin truncar ni aceptar bool."""
    if isinstance(expected_version, bool) or expected_version is None:
        raise exc_cls("La versión esperada debe ser un entero no negativo.")

    if isinstance(expected_version, str):
        val = expected_version.strip()
        if not (val.isascii() and val.isdigit()):
            raise exc_cls("La versión esperada debe ser un entero no negativo.")
        try:
            return int(val)
        except ValueError:
            raise exc_cls("La versión esperada debe ser un entero no negativo.") from None
    if isinstance(expected_version, int) and not isinstance(expected_version, bool):
        if expected_version < 0:
            raise exc_cls("La versión esperada debe ser un entero no negativo.")
        return expected_version
    raise exc_cls("La versión esperada debe ser un entero no negativo.")


def validate_decision_content(
    *,
    action: Any,
    expected_version: Any,
    motivo: Any,
) -> tuple[str, int, str]:
    """Valida acción, versión y motivo dentro del servicio tras verificar acceso."""
    if action not in {"aceptar", "observar", "postergar", "rechazar"}:
        raise InvalidDecisionInputError(f"Acción de decisión desconocida: '{action}'.")

    version_int = _validar_version_entera(expected_version, InvalidDecisionInputError)

    motivo_raw = str(motivo) if motivo is not None else ""
    if "\x00" in motivo_raw:
        raise InvalidDecisionInputError("El motivo no puede contener caracteres nulos (NUL).")

    motivo_limpio = motivo_raw.strip()
    if action in {"observar", "postergar", "rechazar"} and not motivo_limpio:
        raise InvalidDecisionInputError(
            f"El motivo es obligatorio para la acción '{action}' y no puede contener sólo espacios."
        )

    return action, version_int, motivo_limpio


@transaction.atomic
def decide_expense(
    *,
    actor: Any,
    solicitud_id: int,
    action: Any,
    expected_version: Any,
    motivo: Any,
) -> SolicitudGasto:
    """Ejecuta la decisión de gasto de forma atómica bajo la secuencia definitiva:

    1. Inicio de transacción y bloqueo de la solicitud visible (404 si es ajena o inexistente).
    2. Comprobación de capacidad y prohibición de decisión propia (403).
    3. Validación de acción, versión y motivo dentro del servicio (400).
    4. Comprobación de versión vigente y transición sobre la fila bloqueada (409).
    5. Escritura conjunta de estado, versión y evento.
    """
    if actor is None:
        raise ExpensePermissionDeniedError("Se requiere un actor autenticado.")

    # 1. Obtener y bloquear exclusivamente sobre visible_expenses(actor)
    solicitud = (
        visible_expenses(actor)
        .select_for_update()
        .filter(pk=solicitud_id)
        .first()
    )
    if solicitud is None:
        # Objeto ajeno o inexistente: 404 estricto (precede a validación de contenido)
        raise ExpenseNotFoundError(f"Solicitud #{solicitud_id} no visible o inexistente.")

    # 2. Comprobar capacidad gastos.decidir y solicitante != actor
    if not has_capability(actor, "gastos.decidir"):
        # Visible sin permiso: 403 (precede a validación de contenido)
        raise ExpensePermissionDeniedError("El actor no posee la capacidad 'gastos.decidir'.")

    if solicitud.solicitante_id == actor.subject_id:
        # Intento de decisión sobre gasto propio: 403 (precede a validación de contenido)
        raise ExpensePermissionDeniedError(
            "No está permitido decidir sobre una solicitud propia (H2)."
        )

    # 3. Validación de acción, versión y motivo dentro del servicio tras accesos
    valid_action, valid_version, valid_motivo = validate_decision_content(
        action=action,
        expected_version=expected_version,
        motivo=motivo,
    )

    # 4. Comprobación de versión vigente sobre la fila bloqueada
    if solicitud.version != valid_version:
        raise ConcurrencyConflictError(
            f"Conflicto de concurrencia: versión esperada {valid_version}, "
            f"actual en BD {solicitud.version}."
        )

    # 5. Comprobación de transición permitida sobre el estado actual bloqueado
    mapa_estados = {
        "aceptar": EstadoSolicitud.ACEPTADA,
        "observar": EstadoSolicitud.OBSERVADA,
        "postergar": EstadoSolicitud.POSTERGADA,
        "rechazar": EstadoSolicitud.RECHAZADA,
    }
    transiciones_validas = {
        EstadoSolicitud.PRESENTADA: {"aceptar", "observar", "postergar", "rechazar"},
        EstadoSolicitud.POSTERGADA: {"aceptar", "observar", "rechazar"},
    }
    acciones_permitidas = transiciones_validas.get(solicitud.estado, set())
    if valid_action not in acciones_permitidas:
        raise InvalidTransitionError(
            f"Transición '{valid_action}' no permitida desde estado actual '{solicitud.estado}'."
        )

    # 6. Escritura conjunta atómica de estado, versión y evento
    nuevo_estado = mapa_estados[valid_action]
    estado_anterior = solicitud.estado

    solicitud.estado = nuevo_estado
    solicitud.version += 1
    solicitud.save(update_fields=["estado", "version"])

    decision = DecisionGasto.objects.create(
        solicitud=solicitud,
        autor_id=actor.subject_id,
        motivo=valid_motivo,
        estado_anterior=estado_anterior,
        estado_resultante=nuevo_estado,
    )

    from avisos.services import programar_aviso_decision_gasto

    programar_aviso_decision_gasto(decision.pk)

    return solicitud


def _reservar_numero_solicitud_gasto() -> int:
    """Reserva un número libre y avanza la secuencia propia de gastos.

    PostgreSQL entrega valores únicos por transacción concurrente. Si la
    secuencia quedó detrás de números históricos cargados explícitamente, se
    descarta el valor ocupado y se solicita el siguiente; nunca se reutiliza una
    cabecera huérfana.
    """
    with connection.cursor() as cursor:
        while True:
            cursor.execute(
                "SELECT nextval(pg_get_serial_sequence('gastos_solicitudgasto', 'id'))"
            )
            numero = cursor.fetchone()[0]
            ocupado = SolicitudGasto.objects.filter(pk=numero).exists() or (
                TramiteBase.objects.filter(
                    circuito=Circuito.GASTO, numero_publico=numero
                ).exists()
            )
            if not ocupado:
                return numero


DIAS_GRACIA_RENDICION_FACTURA = 15
MAX_TRAMITES_MORA_PERMITIDOS = 2


@dataclass(frozen=True)
class TramiteDeudaDocumentalDTO:
    """Detalle de una solicitud en seguimiento por deuda documental."""

    solicitud: SolicitudGasto
    fecha_pago: date
    dias_transcurridos: int
    en_mora: bool

    @property
    def solicitud_id(self) -> int:
        return self.solicitud.pk

    @property
    def concepto(self) -> str:
        return self.solicitud.concepto


@dataclass(frozen=True)
class ResumenDeudaDocumentalDTO:
    """Consolidado de deudas documentales para un solicitante."""

    solicitudes_pendientes: tuple[TramiteDeudaDocumentalDTO, ...] = ()
    solicitudes_en_mora: tuple[TramiteDeudaDocumentalDTO, ...] = ()
    dias_gracia: int = DIAS_GRACIA_RENDICION_FACTURA
    max_mora_permitida: int = MAX_TRAMITES_MORA_PERMITIDOS

    @property
    def total_pendientes(self) -> int:
        return len(self.solicitudes_pendientes)

    @property
    def total_en_mora(self) -> int:
        return len(self.solicitudes_en_mora)

    @property
    def tiene_deuda(self) -> bool:
        return len(self.solicitudes_pendientes) > 0

    @property
    def tiene_bloqueo(self) -> bool:
        return len(self.solicitudes_en_mora) > self.max_mora_permitida


def verificar_deuda_documental_solicitante(
    actor: Any,
    *,
    fecha_referencia: date | None = None,
) -> ResumenDeudaDocumentalDTO:
    """Evalúa la deuda documental de compras directas pagadas para un solicitante.

    Reglas canónicas (GAST-R07):
    - Sólo aplica al solicitante (solicitante_id == actor.subject_id).
    - Sólo audita compras directas (tipo_flujo == COMPRA_DIRECTA). Los reintegros
      quedan rendidos al pagar y no generan deuda documental posterior.
    - Requiere pago efectivo registrado (pago_externo existente).
    - Un trámite adeuda factura definitiva si carece de un Documento de tipo
      FACTURA_PROVEEDOR vigente (no reemplazado) pendiente de revisión o aceptado.
    - Se computa la antigüedad en días respecto a fecha_referencia (o fecha local).
    - Mora: días_transcurridos > DIAS_GRACIA_RENDICION_FACTURA (15 días).
    - Bloqueo: total_en_mora > MAX_TRAMITES_MORA_PERMITIDOS (2 trámites).
    """
    user_id = (
        getattr(actor, "subject_id", None)
        or getattr(actor, "pk", None)
        or getattr(actor, "id", None)
    )
    if user_id is None:
        return ResumenDeudaDocumentalDTO()

    fecha_actual = fecha_referencia if fecha_referencia is not None else timezone.localdate()

    solicitudes = list(
        SolicitudGasto.objects.filter(
            solicitante_id=user_id,
            tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
            pago_externo__isnull=False,
        )
        .select_related("pago_externo")
        .order_by("pago_externo__fecha_pago", "pk")
    )

    if not solicitudes:
        return ResumenDeudaDocumentalDTO()

    solicitudes_ids = [s.pk for s in solicitudes]
    tramites_ids = [s.tramite_base_id for s in solicitudes if s.tramite_base_id]

    documentos_candidatos = (
        Documento.objects.filter(
            Q(solicitud_gasto_id__in=solicitudes_ids) | Q(tramite_base_id__in=tramites_ids),
            tipo=Documento.Tipo.FACTURA_PROVEEDOR,
            sucesor__isnull=True,
        )
        .prefetch_related(
            Prefetch(
                "revisiones",
                queryset=RevisionDocumento.objects.order_by("-id"),
                to_attr="revisiones_ordenadas",
            )
        )
    )

    solicitudes_con_factura_valida: set[int] = set()
    tramite_a_solicitud = {s.tramite_base_id: s.pk for s in solicitudes if s.tramite_base_id}

    for doc in documentos_candidatos:
        ultima_rev = (
            doc.revisiones_ordenadas[0]
            if getattr(doc, "revisiones_ordenadas", None)
            else None
        )
        if ultima_rev is None or ultima_rev.resultado == RevisionDocumento.Resultado.ACEPTADO:
            if doc.solicitud_gasto_id:
                solicitudes_con_factura_valida.add(doc.solicitud_gasto_id)
            elif doc.tramite_base_id and doc.tramite_base_id in tramite_a_solicitud:
                solicitudes_con_factura_valida.add(tramite_a_solicitud[doc.tramite_base_id])

    pendientes: list[TramiteDeudaDocumentalDTO] = []
    en_mora: list[TramiteDeudaDocumentalDTO] = []

    for s in solicitudes:
        if s.pk not in solicitudes_con_factura_valida:
            fecha_pago = s.pago_externo.fecha_pago
            dias = max(0, (fecha_actual - fecha_pago).days)
            mora = dias > DIAS_GRACIA_RENDICION_FACTURA
            item = TramiteDeudaDocumentalDTO(
                solicitud=s,
                fecha_pago=fecha_pago,
                dias_transcurridos=dias,
                en_mora=mora,
            )
            pendientes.append(item)
            if mora:
                en_mora.append(item)

    return ResumenDeudaDocumentalDTO(
        solicitudes_pendientes=tuple(pendientes),
        solicitudes_en_mora=tuple(en_mora),
    )


@transaction.atomic
def crear_solicitud_gasto(
    *,
    actor: Any,
    concepto: str,
    monto_estimado: Any,
    unidad_requirente: str,
    tipo_flujo: str = TipoFlujoGasto.COMPRA_DIRECTA,
    centro_costo: Any = None,
    datos_transferencia: Mapping[str, Any] | None = None,
    fecha_referencia: date | None = None,
    datos_formulario=None, archivos_formulario=None, _escrituras=None,
) -> SolicitudGasto:
    """Crea cabecera y solicitud juntas con valores fijados por el servidor.

    La capacidad se revalida dentro del servicio, el número público se reserva
    con la secuencia de PostgreSQL. Admite la especificación de la modalidad
    operativa (tipo_flujo) y la imputación a un centro de costo del catálogo.
    Si se selecciona un centro de costo y no se ingresó texto libre en la
    transferencia, el nombre del centro se sincroniza automáticamente en la
    revisión de datos de transferencia.
    Aplica control determinista de mora documental (GAST-R07) para compras directas.
    """
    if not has_capability(actor, "gastos.presentar"):
        raise PermissionDenied("El actor no posee la capacidad 'gastos.presentar'.")

    from django.core.exceptions import ValidationError

    from gastos.forms import SolicitudGastoForm
    from gestion.formularios import guardar_respuesta

    entrada = datos_formulario.copy() if datos_formulario is not None else {}
    entrada.update(concepto=concepto, monto_estimado=monto_estimado,
                   unidad_requirente=unidad_requirente, tipo_flujo=tipo_flujo,
                   centro_costo=getattr(centro_costo, "pk", centro_costo) or "")
    formulario = SolicitudGastoForm(entrada, archivos_formulario)
    if formulario.config_revision:
        if not formulario.is_valid():
            raise ValidationError({k: list(v) for k, v in formulario.errors.items()})

    # Control determinista de deuda documental (GAST-R07)
    resumen_deuda = verificar_deuda_documental_solicitante(actor, fecha_referencia=fecha_referencia)
    if resumen_deuda.tiene_bloqueo:
        raise DeudaDocumentalBloqueoError(
            f"El solicitante registra {resumen_deuda.total_en_mora} trámites con rendición de "
            f"factura definitiva vencida (límite permitido: {resumen_deuda.max_mora_permitida}). "
            f"Debe regularizar los comprobantes pendientes antes de presentar nuevas solicitudes.",
            solicitudes_en_mora=resumen_deuda.solicitudes_en_mora,
        )

    if tipo_flujo not in TipoFlujoGasto.values:
        tipo_flujo = TipoFlujoGasto.COMPRA_DIRECTA

    centro_costo_obj = None
    if isinstance(centro_costo, CentroCosto):
        centro_costo_obj = centro_costo
    elif isinstance(centro_costo, int):
        centro_costo_obj = CentroCosto.objects.filter(pk=centro_costo).first()

    # Sincronización automática de Centro de Costo (GAST-R02)
    tiene_otros_campos = (
        isinstance(datos_transferencia, Mapping)
        and any(
            bool((datos_transferencia.get(k) or "").strip())
            for k in ("titular_nombre", "identificacion", "cbu_alias", "correo_comprobante")
        )
    )
    if (
        centro_costo_obj is not None
        and tiene_otros_campos
        and not (datos_transferencia.get("centro_costo") or "").strip()
    ):
        datos_transferencia = dict(datos_transferencia)
        datos_transferencia["centro_costo"] = centro_costo_obj.nombre

    datos_validos = validar_datos_transferencia(datos_transferencia)

    numero = _reservar_numero_solicitud_gasto()
    base = TramiteBase.objects.create(
        circuito=Circuito.GASTO,
        numero_publico=numero,
        solicitante_actor_id=str(actor.subject_id),
        centro_costo_codigo=centro_costo_obj.codigo[:50] if centro_costo_obj else None,
    )
    solicitud = SolicitudGasto.objects.create(
        pk=numero,
        tramite_base=base,
        concepto=concepto,
        monto_estimado=monto_estimado,
        unidad_requirente=unidad_requirente,
        solicitante_id=actor.subject_id,
        tipo_flujo=tipo_flujo,
        centro_costo=centro_costo_obj,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )
    if datos_validos is not None:
        RevisionDatosTransferencia.objects.create(
            solicitud=solicitud,
            numero_revision=1,
            actor_id=actor.subject_id,
            **datos_validos,
        )
    guardar_respuesta(actor=actor, tramite=base, form=formulario, escrituras=_escrituras)

    from avisos.services import programar_aviso_nueva_solicitud

    programar_aviso_nueva_solicitud(solicitud.pk)
    return solicitud


CLAVE_PARAMETRO_ATP_BASE = "ATP_BASE_IMPONIBLE"
CLAVE_PARAMETRO_ATP_ALICUOTA = "ATP_ALICUOTA_DEFECTO"
VALOR_DEFECTO_ATP_BASE = Decimal("90000.00")
VALOR_DEFECTO_ATP_ALICUOTA = Decimal("3.50")


def obtener_parametro_decimal(clave: str, default: Decimal) -> Decimal:
    """Recupera un parámetro decimal de base de datos con fallback determinista en código.

    Garantiza que sobre bases vacías o en ejecuciones de prueba (como muestra_entrega)
    sin filas en ParametroOperativo no se produzcan excepciones ni se altere el hash.
    """
    try:
        valor = (
            ParametroOperativo.objects.filter(clave=clave)
            .values_list("valor_decimal", flat=True)
            .first()
        )
        if valor is not None:
            return Decimal(str(valor))
    except (DatabaseError, InvalidOperation, TypeError, ValueError):
        pass
    return default


def obtener_base_imponible_atp() -> Decimal:
    """Devuelve la base imponible vigente para retenciones de ATP provincial."""
    return obtener_parametro_decimal(CLAVE_PARAMETRO_ATP_BASE, VALOR_DEFECTO_ATP_BASE)


def obtener_alicuota_atp() -> Decimal:
    """Devuelve la alícuota porcentual sugerida por defecto para retenciones de ATP."""
    return obtener_parametro_decimal(CLAVE_PARAMETRO_ATP_ALICUOTA, VALOR_DEFECTO_ATP_ALICUOTA)


@transaction.atomic
def actualizar_parametro_decimal(
    *,
    clave: str,
    valor: Decimal,
    actor: Any = None,
    descripcion: str = "",
) -> ParametroOperativo:
    """Crea o actualiza un parámetro decimal operativo registrando al actor responsable."""
    user_id = getattr(actor, "subject_id", None) or getattr(actor, "pk", None)
    param, _ = ParametroOperativo.objects.update_or_create(
        clave=clave,
        defaults={
            "valor_decimal": valor,
            "descripcion": descripcion,
            "modificado_por_id": user_id,
        },
    )
    return param


@transaction.atomic
def actualizar_parametros_atp(
    *,
    base_imponible: Decimal,
    alicuota: Decimal,
    actor: Any = None,
) -> tuple[ParametroOperativo, ParametroOperativo]:
    """Actualiza de forma atómica y conjunta ambos parámetros operativos de ATP."""
    p_base = actualizar_parametro_decimal(
        clave=CLAVE_PARAMETRO_ATP_BASE,
        valor=base_imponible,
        actor=actor,
        descripcion="Base imponible mínima sujeta a retención ATP",
    )
    p_alicuota = actualizar_parametro_decimal(
        clave=CLAVE_PARAMETRO_ATP_ALICUOTA,
        valor=alicuota,
        actor=actor,
        descripcion="Alícuota porcentual por defecto para retención ATP",
    )
    return p_base, p_alicuota


def puede_corregir_solicitud(actor: Any, solicitud: SolicitudGasto | None) -> bool:
    """Indica si el titular efectivo puede corregir y reenviar una solicitud observada."""
    if actor is None or solicitud is None:
        return False
    if solicitud.solicitante_id != actor.subject_id:
        return False
    if not has_capability(actor, "gastos.presentar"):
        return False
    if solicitud.estado != EstadoSolicitud.OBSERVADA:
        return False
    if PagoExterno.objects.filter(solicitud_id=solicitud.pk).exists():
        return False
    return visible_expenses(actor).filter(pk=solicitud.pk).exists()


def _validar_centro_costo_subsanacion(
    centro_costo: Any,
    centro_actual_id: int | None,
) -> CentroCosto | None:
    """Valida que el centro de costo sea None, activo o el ya asignado a la solicitud."""
    if centro_costo is None or centro_costo == "":
        return None
    if isinstance(centro_costo, CentroCosto):
        obj = centro_costo
    else:
        try:
            cc_id = int(str(centro_costo).strip())
        except (TypeError, ValueError) as exc:
            raise InvalidSubsanacionInputError("El centro de costo indicado no es válido.") from exc
        obj = CentroCosto.objects.filter(pk=cc_id).first()
        if obj is None:
            raise InvalidSubsanacionInputError("El centro de costo seleccionado no existe.")
    if not obj.activo and obj.pk != centro_actual_id:
        raise InvalidSubsanacionInputError(
            "El centro de costo seleccionado se encuentra inactivo."
        )
    return obj


@transaction.atomic
def corregir_solicitud_gasto(
    *,
    actor: Any,
    solicitud_id: int,
    expected_version: Any,
    concepto: Any,
    monto_estimado: Any,
    centro_costo: Any = None,
) -> SolicitudGasto:
    """Subsanación atómica por el titular de una solicitud observada.

    Orden de guardas:
    1. Actor autenticado y visibilidad (404 si ajena/inexistente).
    2. Titularidad efectiva y capacidad 'gastos.presentar' (403).
    3. Estado OBSERVADA, ausencia de PagoExterno y última decisión OBSERVADA sin subsanar (409).
    4. Validación de versión y campos editables (400).
    5. Control de concurrencia optimista por versión (409).
    6. Actualización de SolicitudGasto, TramiteBase y creación de SubsanacionGasto.
    """
    if actor is None:
        raise ExpensePermissionDeniedError("Se requiere un actor autenticado.")

    solicitud = (
        visible_expenses(actor)
        .select_for_update()
        .filter(pk=solicitud_id)
        .first()
    )
    if solicitud is None:
        raise ExpenseNotFoundError(f"Solicitud #{solicitud_id} no visible o inexistente.")

    if solicitud.solicitante_id != actor.subject_id:
        raise ExpensePermissionDeniedError(
            "Solo el titular de la solicitud puede corregirla."
        )
    if not has_capability(actor, "gastos.presentar"):
        raise ExpensePermissionDeniedError(
            "El actor no posee la capacidad 'gastos.presentar'."
        )

    if solicitud.estado != EstadoSolicitud.OBSERVADA:
        raise InvalidTransitionError(
            f"Solo se pueden corregir solicitudes observadas (estado actual: '{solicitud.estado}')."
        )
    if PagoExterno.objects.filter(solicitud_id=solicitud.pk).exists():
        raise InvalidTransitionError(
            "No se puede corregir una solicitud que ya registra un pago externo."
        )

    ultima_decision = solicitud.decisiones.order_by("-fecha", "-id").first()
    if (
        ultima_decision is None
        or ultima_decision.solicitud_id != solicitud.pk
        or ultima_decision.estado_resultante != EstadoSolicitud.OBSERVADA
        or SubsanacionGasto.objects.filter(decision_observacion=ultima_decision).exists()
    ):
        raise InvalidTransitionError(
            "No existe una observación vigente pendiente de subsanar para esta solicitud."
        )

    version_int = _validar_version_entera(expected_version, InvalidSubsanacionInputError)

    concepto_raw = "" if concepto is None else str(concepto)
    if "\x00" in concepto_raw:
        raise InvalidSubsanacionInputError("El concepto no puede contener caracteres nulos.")
    concepto_limpio = concepto_raw.strip()
    if not concepto_limpio:
        raise InvalidSubsanacionInputError("El concepto o justificación es obligatorio.")
    if len(concepto_limpio) > 255:
        raise InvalidSubsanacionInputError("El concepto no puede superar los 255 caracteres.")

    if isinstance(monto_estimado, bool) or monto_estimado is None:
        raise InvalidSubsanacionInputError("El importe estimado debe ser un monto positivo en ARS.")
    try:
        monto_dec = Decimal(str(monto_estimado).strip())
    except (InvalidOperation, ValueError) as exc:
        raise InvalidSubsanacionInputError(
            "El importe estimado debe ser un monto válido en ARS."
        ) from exc
    if not monto_dec.is_finite() or monto_dec <= Decimal("0") or monto_dec.as_tuple().exponent < -2:
        raise InvalidSubsanacionInputError(
            "El importe estimado debe ser positivo con hasta dos decimales."
        )
    if monto_dec > Decimal("9999999999.99"):
        raise InvalidSubsanacionInputError("El importe estimado excede el máximo permitido.")

    centro_nuevo = _validar_centro_costo_subsanacion(centro_costo, solicitud.centro_costo_id)

    if solicitud.version != version_int:
        raise ConcurrencyConflictError(
            f"Conflicto de concurrencia: versión esperada {version_int}, "
            f"actual en BD {solicitud.version}."
        )

    concepto_anterior = solicitud.concepto
    monto_anterior = solicitud.monto_estimado
    centro_anterior = solicitud.centro_costo

    solicitud.concepto = concepto_limpio
    solicitud.monto_estimado = monto_dec.quantize(Decimal("0.01"))
    solicitud.centro_costo = centro_nuevo
    solicitud.estado = EstadoSolicitud.PRESENTADA
    solicitud.version += 1
    solicitud.save(
        update_fields=["concepto", "monto_estimado", "centro_costo", "estado", "version"]
    )

    tramite_base = solicitud.tramite_base
    nuevo_codigo = centro_nuevo.codigo[:50] if centro_nuevo else None
    if tramite_base.centro_costo_codigo != nuevo_codigo:
        tramite_base.centro_costo_codigo = nuevo_codigo
        tramite_base.save(update_fields=["centro_costo_codigo"])

    SubsanacionGasto.objects.create(
        solicitud=solicitud,
        decision_observacion=ultima_decision,
        autor_id=actor.subject_id,
        concepto_anterior=concepto_anterior,
        concepto_nuevo=solicitud.concepto,
        monto_anterior=monto_anterior,
        monto_nuevo=solicitud.monto_estimado,
        centro_costo_anterior=centro_anterior,
        centro_costo_nuevo=centro_nuevo,
        estado_anterior=EstadoSolicitud.OBSERVADA,
        estado_resultante=EstadoSolicitud.PRESENTADA,
    )
    return solicitud

