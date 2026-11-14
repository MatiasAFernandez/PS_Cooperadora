"""Servicios de alta administrativa mediante invitación de cuentas locales (SPEC-027)."""

import hashlib
import logging
import urllib.parse
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from identidad.administracion_cuentas import (
    CAPACIDAD_ADMINISTRAR,
    es_admin_local_habilitado,
    grupos_admin_locales,
)
from identidad.cuentas import limitar, normalizar_correo
from identidad.models import CuentaLocal, InvitacionCuentaLocal
from identidad.services import Actor, has_capability

logger = logging.getLogger(__name__)

SALT_INVITACION = "identidad.invitacion-cuenta"
_ERROR_ENLACE_GENERICO = "El enlace de invitación es inválido o ha vencido."


def _bloquear_y_revalidar_actor(actor: Actor) -> Any:
    """Bloquea en orden User -> CuentaLocal y revalida la capacidad vigente del actor.

    Debe ejecutarse dentro de ``transaction.atomic()``.
    """
    grupos_admin = grupos_admin_locales()
    if not grupos_admin:
        raise PermissionDenied("No existen grupos habilitados para administrar cuentas.")

    user_model = get_user_model()
    candidatos_admin_pks = list(
        user_model.objects.filter(
            cuenta_local__isnull=False,
            groups__name__in=grupos_admin,
        )
        .values_list("pk", flat=True)
        .distinct()
    )

    user_pks_bloqueo = sorted(set(candidatos_admin_pks) | {actor.subject_id})
    usuarios_bloqueados = {
        u.pk: u
        for u in user_model.objects.select_for_update()
        .filter(pk__in=user_pks_bloqueo)
        .order_by("pk")
    }
    cuentas_bloqueadas = {
        c.user_id: c
        for c in CuentaLocal.objects.select_for_update()
        .filter(user_id__in=user_pks_bloqueo)
        .order_by("pk")
    }
    admin_group_user_ids = set(
        user_model.objects.filter(
            pk__in=user_pks_bloqueo,
            groups__name__in=grupos_admin,
        ).values_list("pk", flat=True)
    )

    actor_user = usuarios_bloqueados.get(actor.subject_id)
    actor_cuenta = cuentas_bloqueadas.get(actor.subject_id)
    if not es_admin_local_habilitado(actor_user, actor_cuenta, admin_group_user_ids):
        raise PermissionDenied("No posee capacidad vigente para administrar cuentas.")

    return actor_user


def _validar_datos_alta(
    nombre: Any,
    email: Any,
    area_habitual: Any,
    cuit_cuil: Any,
    legajo: Any,
) -> tuple[str, str, str, str, str]:
    """Valida y normaliza los campos del alta administrativa con las reglas vigentes."""
    if not isinstance(nombre, str):
        raise ValidationError("El nombre completo es obligatorio.")
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise ValidationError("El nombre completo es obligatorio.")
    if len(nombre_limpio) > 150:
        raise ValidationError("El nombre completo no debe superar 150 caracteres.")

    if not isinstance(email, str):
        raise ValidationError("El correo electrónico es obligatorio.")
    email_norm = normalizar_correo(email)
    if not email_norm:
        raise ValidationError("El correo electrónico es obligatorio.")
    if len(email_norm) > 254:
        raise ValidationError("El correo electrónico no debe superar 254 caracteres.")
    validate_email(email_norm)

    if area_habitual is None:
        area_habitual = ""
    if not isinstance(area_habitual, str):
        raise ValidationError("El área habitual no tiene un formato válido.")
    area_limpia = area_habitual.strip()
    if len(area_limpia) > 150:
        raise ValidationError("El área habitual no debe superar 150 caracteres.")

    if cuit_cuil is None:
        cuit_cuil = ""
    if not isinstance(cuit_cuil, str):
        raise ValidationError("El CUIT/CUIL no tiene un formato válido.")
    cuit_cuil_limpio = cuit_cuil.strip()
    if len(cuit_cuil_limpio) > 20:
        raise ValidationError("El CUIT/CUIL no debe superar 20 caracteres.")

    if legajo is None:
        legajo = ""
    if not isinstance(legajo, str):
        raise ValidationError("El legajo no tiene un formato válido.")
    legajo_limpio = legajo.strip()
    if len(legajo_limpio) > 50:
        raise ValidationError("El legajo no debe superar 50 caracteres.")

    return nombre_limpio, email_norm, area_limpia, cuit_cuil_limpio, legajo_limpio


def crear_cuenta_invitada(
    actor: Actor | None,
    nombre: str,
    email: str,
    area_habitual: str = "",
    cuit_cuil: str = "",
    legajo: str = "",
) -> CuentaLocal:
    """Crea atómicamente una CuentaLocal pendiente con contraseña no utilizable e invitación.

    Exige ``identidad.administrar_cuentas`` antes de consultar la base y revalida al
    actor bajo bloqueo. No envía correo ni asigna aprobación, perfiles o privilegios.
    """
    if not has_capability(actor, CAPACIDAD_ADMINISTRAR) or actor is None:
        raise PermissionDenied("No posee capacidad para administrar cuentas.")
    if not grupos_admin_locales():
        raise PermissionDenied("No existen grupos habilitados para administrar cuentas.")

    nombre_limpio, email_norm, area_limpia, cuit_cuil_limpio, legajo_limpio = _validar_datos_alta(
        nombre, email, area_habitual, cuit_cuil, legajo
    )

    user_model = get_user_model()
    try:
        with transaction.atomic():
            actor_user = _bloquear_y_revalidar_actor(actor)

            if CuentaLocal.objects.filter(email__iexact=email_norm).exists():
                raise ValidationError("Ya existe una cuenta registrada con ese correo electrónico.")
            if user_model.objects.filter(email__iexact=email_norm).exists():
                raise ValidationError("Ya existe una cuenta registrada con ese correo electrónico.")

            user = user_model.objects.create_user(
                username=f"local_{uuid.uuid4().hex}",
                email=email_norm,
                password=None,
                first_name=nombre_limpio[:150],
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            cuenta = CuentaLocal.objects.create(
                user=user,
                email=email_norm,
                nombre_completo=nombre_limpio[:150],
                area_habitual=area_limpia,
                cuit_cuil=cuit_cuil_limpio,
                legajo=legajo_limpio,
                estado=CuentaLocal.Estado.PENDIENTE,
                email_verificado_en=None,
            )
            InvitacionCuentaLocal.objects.create(
                cuenta=cuenta,
                creada_por=actor_user,
                estado_envio=InvitacionCuentaLocal.EstadoEnvio.PENDIENTE,
            )
            return cuenta
    except IntegrityError:
        raise ValidationError(
            "Ya existe una cuenta registrada con ese correo electrónico."
        ) from None


def _token_invitacion(cuenta: CuentaLocal, user: Any) -> str:
    """Genera un token firmado temporal para aceptar una invitación administrativa."""
    pwd_fp = hashlib.sha256(user.password.encode("utf-8")).hexdigest()
    payload = {
        "pk": cuenta.pk,
        "email": cuenta.email,
        "nonce": str(cuenta.nonce_verificacion),
        "pwd_fp": pwd_fp,
    }
    return signing.dumps(payload, salt=SALT_INVITACION)


def _cargar_y_validar_payload(token: str) -> tuple[int, str, str, str]:
    """Deserializa y valida la firma temporal del token de invitación."""
    if not isinstance(token, str) or not token.strip():
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    max_age = getattr(settings, "LOCAL_VERIFICATION_TIMEOUT", 86400)
    try:
        payload = signing.loads(
            token,
            salt=SALT_INVITACION,
            max_age=max_age,
        )
    except (signing.SignatureExpired, signing.BadSignature):
        raise ValidationError(_ERROR_ENLACE_GENERICO) from None

    if not isinstance(payload, dict):
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    pk = payload.get("pk")
    email = payload.get("email")
    nonce = payload.get("nonce")
    pwd_fp = payload.get("pwd_fp")

    if isinstance(pk, bool) or not isinstance(pk, int) or pk <= 0:
        raise ValidationError(_ERROR_ENLACE_GENERICO)
    if not email or not nonce or not pwd_fp:
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    return pk, str(email), str(nonce), str(pwd_fp)


def _validar_estado_invitacion(
    cuenta: CuentaLocal | None,
    user: Any,
    invitacion: InvitacionCuentaLocal | None,
    email: str,
    nonce: str,
    pwd_fp: str,
) -> None:
    """Comprueba que la cuenta, usuario e invitación sigan habilitados para el token."""
    if cuenta is None or user is None or invitacion is None:
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    if cuenta.email.casefold() != email.casefold():
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    if str(cuenta.nonce_verificacion) != nonce:
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    current_pwd_fp = hashlib.sha256(user.password.encode("utf-8")).hexdigest()
    if pwd_fp != current_pwd_fp:
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    if not user.is_active:
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    if cuenta.estado == CuentaLocal.Estado.RECHAZADA:
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    if invitacion.aceptada_en is not None:
        raise ValidationError(_ERROR_ENLACE_GENERICO)

    if user.has_usable_password():
        raise ValidationError(_ERROR_ENLACE_GENERICO)


def validar_invitacion(token: str) -> CuentaLocal:
    """Valida un token de invitación para consulta (GET) sin consumirlo ni escribir en DB."""
    pk, email, nonce, pwd_fp = _cargar_y_validar_payload(token)
    cuenta = (
        CuentaLocal.objects.select_related("user", "invitacion_administrativa")
        .filter(pk=pk)
        .first()
    )
    user = cuenta.user if cuenta is not None else None
    invitacion = getattr(cuenta, "invitacion_administrativa", None) if cuenta is not None else None
    _validar_estado_invitacion(cuenta, user, invitacion, email, nonce, pwd_fp)
    assert cuenta is not None
    return cuenta


def aceptar_invitacion(token: str, password: str) -> CuentaLocal:
    """Acepta una invitación (POST) estableciendo contraseña, verificación y consumo atómicos."""
    pk, email, nonce, pwd_fp = _cargar_y_validar_payload(token)
    if not isinstance(password, str) or not password:
        raise ValidationError("La contraseña es obligatoria.")

    user_model = get_user_model()
    with transaction.atomic():
        user_id = CuentaLocal.objects.filter(pk=pk).values_list("user_id", flat=True).first()
        if user_id is None:
            raise ValidationError(_ERROR_ENLACE_GENERICO)

        user = user_model.objects.select_for_update().filter(pk=user_id).first()
        cuenta = CuentaLocal.objects.select_for_update().filter(pk=pk).first()
        invitacion = InvitacionCuentaLocal.objects.select_for_update().filter(cuenta_id=pk).first()

        _validar_estado_invitacion(cuenta, user, invitacion, email, nonce, pwd_fp)
        assert user is not None and cuenta is not None and invitacion is not None

        validate_password(password, user=user)

        now = timezone.now()
        user.set_password(password)
        user.save(update_fields=["password"])

        if cuenta.email_verificado_en is None:
            cuenta.email_verificado_en = now
        cuenta.nonce_verificacion = uuid.uuid4()
        cuenta.save(update_fields=["email_verificado_en", "nonce_verificacion"])

        invitacion.aceptada_en = now
        invitacion.save(update_fields=["aceptada_en"])

        cuenta.user = user
        return cuenta


def _base_url_valida(base_url: str) -> bool:
    """Comprueba que la URL base interna sea http/https sin usuario, consulta ni ruta."""
    if not isinstance(base_url, str) or not base_url:
        return False
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    if parsed.path not in ("", "/"):
        return False
    return True


def enviar_invitacion(cuenta: CuentaLocal, base_url: str | None = None) -> bool:
    """Envía o reenvía la invitación por correo electrónico aplicando rate limit y rotación.

    El envío SMTP ocurre fuera de la transacción de base de datos; un guard sobre el
    nonce evita que un resultado tardío sobrescriba un envío más reciente.
    """
    if cuenta is None or not getattr(cuenta, "pk", None) or not getattr(cuenta, "user_id", None):
        return False

    url_base = getattr(settings, "LOCAL_PUBLIC_BASE_URL", "") if base_url is None else base_url
    if not _base_url_valida(url_base):
        return False

    user_model = get_user_model()
    with transaction.atomic():
        user = user_model.objects.select_for_update().filter(pk=cuenta.user_id).first()
        cuenta_locked = CuentaLocal.objects.select_for_update().filter(pk=cuenta.pk).first()
        invitacion = (
            InvitacionCuentaLocal.objects.select_for_update().filter(cuenta_id=cuenta.pk).first()
        )
        if user is None or cuenta_locked is None or invitacion is None:
            return False
        if not user.is_active:
            return False
        if cuenta_locked.estado == CuentaLocal.Estado.RECHAZADA:
            return False
        if invitacion.aceptada_en is not None:
            return False
        if user.has_usable_password():
            return False

        min_interval = getattr(settings, "LOCAL_VERIFY_RESEND_MIN_INTERVAL", 60)
        max_hourly = getattr(settings, "LOCAL_VERIFY_RESEND_MAX_HOURLY", 5)
        now = timezone.now()

        if min_interval > 0 and cuenta_locked.ultimo_envio is not None:
            if (now - cuenta_locked.ultimo_envio).total_seconds() < min_interval:
                return False

        if min_interval > 0 and not limitar(
            f"invit_min:{cuenta_locked.pk}", maximo=1, segundos=min_interval
        ):
            return False
        if not limitar(f"invit_hora:{cuenta_locked.pk}", maximo=max_hourly, segundos=3600):
            return False

        cuenta_locked.nonce_verificacion = uuid.uuid4()
        cuenta_locked.save(update_fields=["nonce_verificacion"])

        invitacion.ultimo_intento_en = now
        invitacion.save(update_fields=["ultimo_intento_en"])

        intento_nonce = cuenta_locked.nonce_verificacion
        recipient = cuenta_locked.email
        nombre_completo = cuenta_locked.nombre_completo
        token = _token_invitacion(cuenta_locked, user)

    query = urllib.parse.urlencode({"token": token})
    url = f"{url_base.rstrip('/')}/cuentas/invitacion/?{query}"

    subject = "Invitación para activar tu cuenta local"
    message = (
        f"Hola {nombre_completo},\n\n"
        "Se creó una cuenta local para tu correo electrónico. "
        f"Para elegir tu contraseña y confirmar la casilla, ingresá al siguiente enlace:\n\n"
        f"{url}\n\n"
        "Si no esperabas esta invitación, ignorá este mensaje.\n"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)

    envio_ok = False
    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        envio_ok = sent == 1
    except Exception as exc:
        logger.warning(
            "Fallo en envío de invitación para cuenta_id=%s: %s",
            cuenta.pk,
            type(exc).__name__,
        )
        envio_ok = False

    with transaction.atomic():
        user_post = user_model.objects.select_for_update().filter(pk=cuenta.user_id).first()
        cuenta_post = CuentaLocal.objects.select_for_update().filter(pk=cuenta.pk).first()
        invitacion_post = (
            InvitacionCuentaLocal.objects.select_for_update().filter(cuenta_id=cuenta.pk).first()
        )
        if (
            user_post is None
            or cuenta_post is None
            or invitacion_post is None
            or cuenta_post.nonce_verificacion != intento_nonce
        ):
            return envio_ok

        if envio_ok:
            invitacion_post.estado_envio = InvitacionCuentaLocal.EstadoEnvio.ENVIADA
            invitacion_post.save(update_fields=["estado_envio"])
            cuenta_post.ultimo_envio = timezone.now()
            cuenta_post.save(update_fields=["ultimo_envio"])
            cuenta.ultimo_envio = cuenta_post.ultimo_envio
        else:
            invitacion_post.estado_envio = InvitacionCuentaLocal.EstadoEnvio.ERROR
            invitacion_post.save(update_fields=["estado_envio"])

        cuenta.nonce_verificacion = cuenta_post.nonce_verificacion

    return envio_ok
