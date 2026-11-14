"""Envío, validación, exclusión y conciliación de correos para avisos de Gastos."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.validators import URLValidator, validate_email
from django.db import connection
from django.db.models import F
from django.utils import timezone

from avisos.models import EstadoIntencionCorreo, IntencionCorreo, TipoAviso
from gastos.models import SolicitudGasto
from identidad.services import actor_para_usuario, has_capability

logger = logging.getLogger(__name__)
User = get_user_model()

ADVISORY_LOCK_NAMESPACE = 127029
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ConfiguracionCorreoInvalida(Exception):
    """Configuración inválida para construir o remitir avisos por correo."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


class ConciliacionError(Exception):
    """Error al intentar conciliar una intención de correo."""


@dataclass(frozen=True, slots=True)
class ResultadoEnvio:
    """Resumen acotado del intento de envío para una intención."""

    intencion_id: int
    estado: str
    ejecutado: bool
    codigo: str = ""


def _lock_key_intencion(intencion_id: int) -> int:
    return (ADVISORY_LOCK_NAMESPACE << 32) | int(intencion_id)


@contextmanager
def _advisory_lock_intencion(intencion_id: int) -> Iterator[bool]:
    """Exclusión no bloqueante por intención usando advisory lock de sesión en PostgreSQL."""
    if connection.vendor != "postgresql":
        yield True
        return

    key = _lock_key_intencion(intencion_id)
    adquirido = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        row = cursor.fetchone()
        adquirido = bool(row and row[0])
    try:
        yield adquirido
    finally:
        if adquirido:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
            except Exception:
                logger.warning(
                    "No se pudo liberar advisory lock de sesion para intencion_id=%s",
                    intencion_id,
                )


def validar_url_base_avisos(raw_url: str | None = None) -> str:
    """Valida y normaliza AVISOS_PUBLIC_BASE_URL como raíz HTTPS o HTTP loopback."""
    valor = (
        getattr(settings, "AVISOS_PUBLIC_BASE_URL", "")
        if raw_url is None
        else raw_url
    )
    if valor is None or not isinstance(valor, str):
        raise ConfiguracionCorreoInvalida("config_url_invalida")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in valor):
        raise ConfiguracionCorreoInvalida("config_url_invalida")

    url = valor.strip()
    if not url or any(ch.isspace() for ch in url):
        raise ConfiguracionCorreoInvalida("config_url_invalida")

    try:
        URLValidator(schemes=["http", "https"])(url)
    except ValidationError as exc:
        raise ConfiguracionCorreoInvalida("config_url_invalida") from exc

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ConfiguracionCorreoInvalida("config_url_invalida") from exc

    if parsed.username is not None or parsed.password is not None:
        raise ConfiguracionCorreoInvalida("config_url_invalida")
    if parsed.query or parsed.fragment:
        raise ConfiguracionCorreoInvalida("config_url_invalida")
    if parsed.path not in ("", "/"):
        raise ConfiguracionCorreoInvalida("config_url_invalida")
    if parsed.netloc.endswith(":"):
        raise ConfiguracionCorreoInvalida("config_url_invalida")
    if port is not None and not (1 <= port <= 65535):
        raise ConfiguracionCorreoInvalida("config_url_invalida")

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ConfiguracionCorreoInvalida("config_url_invalida")

    if scheme == "https":
        pass
    elif scheme == "http":
        if hostname not in LOOPBACK_HOSTS:
            raise ConfiguracionCorreoInvalida("config_url_invalida")
    else:
        raise ConfiguracionCorreoInvalida("config_url_invalida")

    return f"{scheme}://{parsed.netloc}"


def validar_remitente_avisos(raw_from: str | None = None) -> str:
    """Valida DEFAULT_FROM_EMAIL y devuelve el remitente configurado."""
    valor = (
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
        if raw_from is None
        else raw_from
    )
    if valor is None or not isinstance(valor, str) or "\r" in valor or "\n" in valor:
        raise ConfiguracionCorreoInvalida("config_from_invalido")
    remitente = valor.strip()
    if not remitente:
        raise ConfiguracionCorreoInvalida("config_from_invalido")

    _, direccion = parseaddr(remitente)
    if not direccion:
        raise ConfiguracionCorreoInvalida("config_from_invalido")

    try:
        validate_email(direccion)
    except ValidationError as exc:
        raise ConfiguracionCorreoInvalida("config_from_invalido") from exc

    return remitente


def _marcar_resultado_seguro(
    intencion_id: int,
    estado: str,
    codigo: str,
    *,
    aceptado_en=None,
) -> bool:
    """Actualiza el estado de la intención sin propagar errores de persistencia."""
    ahora = timezone.now()
    campos: dict = {
        "estado": estado,
        "codigo_resultado": codigo[:64],
        "actualizada_en": ahora,
    }
    if aceptado_en is not None:
        campos["aceptado_en"] = aceptado_en
    try:
        IntencionCorreo.objects.filter(pk=intencion_id).update(**campos)
        return True
    except Exception:
        logger.error(
            "Error al persistir resultado de correo intencion_id=%s estado_objetivo=%s",
            intencion_id,
            estado,
        )
        return False


def _construir_mensaje(
    *,
    solicitud: SolicitudGasto,
    enlace: str,
    remitente: str,
    destinatario_email: str,
) -> EmailMessage:
    fecha_local = timezone.localtime(solicitud.fecha_creacion)
    fecha_texto = fecha_local.strftime("%d/%m/%Y %H:%M")
    asunto = f"[PS_Cooperadora] Nueva solicitud de gasto #{solicitud.pk}"
    cuerpo = (
        f"Se registró una nueva solicitud de gasto #{solicitud.pk}.\n"
        f"Fecha de presentación: {fecha_texto}\n"
        f"Ver solicitud: {enlace}\n"
    )
    return EmailMessage(
        subject=asunto,
        body=cuerpo,
        from_email=remitente,
        to=[destinatario_email],
    )


def procesar_intencion_correo(intencion_id: int) -> ResultadoEnvio:
    """Reclama atómicamente una intención elegible, revalida y ejecuta el envío SMTP."""
    if not getattr(settings, "AVISOS_EMAIL_ENABLED", False):
        return ResultadoEnvio(
            intencion_id=intencion_id,
            estado=EstadoIntencionCorreo.PENDIENTE,
            ejecutado=False,
            codigo="canal_deshabilitado",
        )

    with _advisory_lock_intencion(intencion_id) as adquirido:
        if not adquirido:
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.EN_PROCESO,
                ejecutado=False,
                codigo="emisor_activo",
            )

        ahora = timezone.now()
        actualizadas = IntencionCorreo.objects.filter(
            pk=intencion_id,
            estado__in=[
                EstadoIntencionCorreo.PENDIENTE,
                EstadoIntencionCorreo.FALLIDO,
            ],
        ).update(
            estado=EstadoIntencionCorreo.EN_PROCESO,
            intentos=F("intentos") + 1,
            ultimo_intento_en=ahora,
            actualizada_en=ahora,
            codigo_resultado="",
        )
        if actualizadas == 0:
            estado_actual = (
                IntencionCorreo.objects.filter(pk=intencion_id)
                .values_list("estado", flat=True)
                .first()
                or ""
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=estado_actual,
                ejecutado=False,
                codigo="no_reclamable",
            )

        intencion = IntencionCorreo.objects.select_related("aviso").get(pk=intencion_id)
        aviso = intencion.aviso
        solicitud = SolicitudGasto.objects.filter(pk=aviso.solicitud_id).first()
        if solicitud is None:
            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.OMITIDO,
                "solicitud_inexistente",
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.OMITIDO,
                ejecutado=True,
                codigo="solicitud_inexistente",
            )

        user = (
            User.objects.filter(pk=aviso.destinatario_id)
            .select_related("cuenta_local")
            .prefetch_related("groups")
            .first()
        )
        if user is None:
            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.OMITIDO,
                "usuario_inexistente",
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.OMITIDO,
                ejecutado=True,
                codigo="usuario_inexistente",
            )

        if user.pk == solicitud.solicitante_id:
            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.OMITIDO,
                "autor_excluido",
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.OMITIDO,
                ejecutado=True,
                codigo="autor_excluido",
            )

        group_names = [group.name for group in user.groups.all()]
        actor = actor_para_usuario(user, group_names=group_names)
        if (
            actor is None
            or not has_capability(actor, "gastos.consultar_todas")
            or not has_capability(actor, "gastos.decidir")
        ):
            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.OMITIDO,
                "sin_permisos",
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.OMITIDO,
                ejecutado=True,
                codigo="sin_permisos",
            )

        email_destinatario = (actor.email_registrado or "").strip()
        if email_destinatario:
            IntencionCorreo.objects.filter(pk=intencion_id).update(
                direccion_ultimo_intento=email_destinatario[:254],
                actualizada_en=timezone.now(),
            )

        try:
            validate_email(email_destinatario)
        except ValidationError:
            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.FALLIDO,
                "correo_destinatario_invalido",
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.FALLIDO,
                ejecutado=True,
                codigo="correo_destinatario_invalido",
            )

        try:
            base_url = validar_url_base_avisos()
            remitente = validar_remitente_avisos()
        except ConfiguracionCorreoInvalida as exc:
            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.FALLIDO,
                exc.codigo,
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.FALLIDO,
                ejecutado=True,
                codigo=exc.codigo,
            )

        try:
            enlace = f"{base_url}{aviso.get_absolute_url()}"
            mensaje = _construir_mensaje(
                solicitud=solicitud,
                enlace=enlace,
                remitente=remitente,
                destinatario_email=email_destinatario,
            )
            mail_conn = get_connection(fail_silently=False)
        except Exception:
            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.FALLIDO,
                "error_preparacion_correo",
            )
            logger.error(
                "Error al preparar envio de correo para intencion_id=%s "
                "codigo=error_preparacion_correo",
                intencion_id,
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.FALLIDO,
                ejecutado=True,
                codigo="error_preparacion_correo",
            )

        abierta = False
        try:
            try:
                mail_conn.open()
                abierta = True
            except Exception:
                _marcar_resultado_seguro(
                    intencion_id,
                    EstadoIntencionCorreo.FALLIDO,
                    "smtp_conexion_error",
                )
                logger.warning(
                    "No se pudo abrir conexion SMTP para intencion_id=%s "
                    "codigo=smtp_conexion_error",
                    intencion_id,
                )
                return ResultadoEnvio(
                    intencion_id=intencion_id,
                    estado=EstadoIntencionCorreo.FALLIDO,
                    ejecutado=True,
                    codigo="smtp_conexion_error",
                )

            try:
                enviados = mail_conn.send_messages([mensaje])
            except Exception:
                persistido = _marcar_resultado_seguro(
                    intencion_id,
                    EstadoIntencionCorreo.INCIERTO,
                    "smtp_envio_incierto",
                )
                logger.warning(
                    "Resultado incierto al enviar correo intencion_id=%s "
                    "codigo=smtp_envio_incierto persistido=%s",
                    intencion_id,
                    persistido,
                )
                return ResultadoEnvio(
                    intencion_id=intencion_id,
                    estado=(
                        EstadoIntencionCorreo.INCIERTO
                        if persistido
                        else EstadoIntencionCorreo.EN_PROCESO
                    ),
                    ejecutado=True,
                    codigo="smtp_envio_incierto",
                )

            if enviados and enviados > 0:
                persistido = _marcar_resultado_seguro(
                    intencion_id,
                    EstadoIntencionCorreo.ACEPTADO,
                    "smtp_aceptado",
                    aceptado_en=timezone.now(),
                )
                logger.info(
                    "Correo aceptado por servidor intencion_id=%s persistido=%s",
                    intencion_id,
                    persistido,
                )
                return ResultadoEnvio(
                    intencion_id=intencion_id,
                    estado=(
                        EstadoIntencionCorreo.ACEPTADO
                        if persistido
                        else EstadoIntencionCorreo.EN_PROCESO
                    ),
                    ejecutado=True,
                    codigo="smtp_aceptado" if persistido else "db_persistencia_post_envio",
                )

            _marcar_resultado_seguro(
                intencion_id,
                EstadoIntencionCorreo.FALLIDO,
                "smtp_rechazado",
            )
            logger.warning(
                "Correo rechazado por servidor intencion_id=%s codigo=smtp_rechazado",
                intencion_id,
            )
            return ResultadoEnvio(
                intencion_id=intencion_id,
                estado=EstadoIntencionCorreo.FALLIDO,
                ejecutado=True,
                codigo="smtp_rechazado",
            )
        finally:
            if abierta:
                try:
                    mail_conn.close()
                except Exception:
                    logger.warning(
                        "Error al cerrar conexion SMTP para intencion_id=%s",
                        intencion_id,
                    )


def enviar_correos_nueva_solicitud(
    solicitud_id: int,
    *,
    incluir_fallidos: bool = False,
) -> list[ResultadoEnvio]:
    """Envía de forma independiente las intenciones elegibles de una solicitud."""
    if not getattr(settings, "AVISOS_EMAIL_ENABLED", False):
        return []

    estados = [EstadoIntencionCorreo.PENDIENTE]
    if incluir_fallidos:
        estados.append(EstadoIntencionCorreo.FALLIDO)

    intencion_ids = list(
        IntencionCorreo.objects.filter(
            aviso__solicitud_id=solicitud_id,
            aviso__tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
            estado__in=estados,
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    resultados: list[ResultadoEnvio] = []
    for intencion_id in intencion_ids:
        try:
            resultados.append(procesar_intencion_correo(intencion_id))
        except Exception:
            logger.error(
                "Error inesperado procesando intencion_id=%s solicitud_id=%s",
                intencion_id,
                solicitud_id,
            )
    return resultados


def conciliar_intencion_correo(
    solicitud_id: int,
    intencion_id: int,
    *,
    resultado: str,
    confirmar_riesgo_duplicado: bool = False,
) -> IntencionCorreo:
    """Concilia manualmente una intención en estado incierto o en proceso."""
    if resultado not in {"aceptado", "reintentar"}:
        raise ConciliacionError("Resultado de conciliación inválido.")
    if resultado == "reintentar" and not confirmar_riesgo_duplicado:
        raise ConciliacionError(
            "Reintentar una intención incierta o en proceso requiere confirmar riesgo de duplicado."
        )

    with _advisory_lock_intencion(intencion_id) as adquirido:
        if not adquirido:
            raise ConciliacionError(
                f"La intención #{intencion_id} tiene un emisor activo; no puede conciliarse ahora."
            )

        try:
            intencion = IntencionCorreo.objects.select_related("aviso").get(
                pk=intencion_id,
                aviso__solicitud_id=solicitud_id,
                aviso__tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
            )
        except IntencionCorreo.DoesNotExist as exc:
            raise ConciliacionError(
                f"No existe la intención #{intencion_id} para la solicitud #{solicitud_id}."
            ) from exc

        if intencion.estado not in {
            EstadoIntencionCorreo.INCIERTO,
            EstadoIntencionCorreo.EN_PROCESO,
        }:
            raise ConciliacionError(
                f"La intención #{intencion_id} está en estado '{intencion.estado}' "
                "y no requiere conciliación."
            )

        ahora = timezone.now()
        if resultado == "aceptado":
            intencion.estado = EstadoIntencionCorreo.ACEPTADO
            intencion.aceptado_en = intencion.aceptado_en or ahora
            intencion.codigo_resultado = "conciliado_aceptado"
            intencion.save(
                update_fields=["estado", "aceptado_en", "codigo_resultado", "actualizada_en"]
            )
        else:
            intencion.estado = EstadoIntencionCorreo.FALLIDO
            intencion.codigo_resultado = "conciliado_reintentar"
            intencion.save(
                update_fields=["estado", "codigo_resultado", "actualizada_en"]
            )
        return intencion
