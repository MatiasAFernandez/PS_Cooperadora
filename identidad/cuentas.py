"""Funciones y lógica de negocio para la gestión de cuentas locales.

Satisface SPEC-022 y el contrato de identidad local permanente para
registro, verificación de correo y decisión administrativa.
"""

import datetime
import hashlib
import logging
import urllib.parse
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from identidad.models import CuentaLocal, LimiteAcceso
from identidad.services import Actor, has_capability

logger = logging.getLogger(__name__)


def normalizar_correo(valor: str) -> str:
    """Normaliza un correo electrónico aplicando strip y casefold."""
    if not valor or not isinstance(valor, str):
        return ""
    return valor.strip().casefold()


def limitar(clave: str, *, maximo: int = 5, segundos: int = 300) -> bool:
    """Limita operaciones de acceso por clave hash, controlando tasa en base de datos.

    Devuelve False si se supera el máximo dentro de la ventana de tiempo.
    Maneja la carrera de primera creación con savepoint para no abortar
    transacciones externas.
    """
    if maximo <= 0:
        return False

    digest = hashlib.sha256(clave.encode("utf-8")).hexdigest()
    now = timezone.now()
    delta = datetime.timedelta(seconds=segundos)

    with transaction.atomic():
        registro = LimiteAcceso.objects.select_for_update().filter(clave=digest).first()
        if registro is None:
            try:
                with transaction.atomic():
                    registro = LimiteAcceso.objects.create(
                        clave=digest,
                        inicio=now,
                        intentos=1,
                    )
                    created = True
            except IntegrityError:
                registro = LimiteAcceso.objects.select_for_update().get(clave=digest)
                created = False
        else:
            created = False

        if created:
            return 1 <= maximo

        if (now - registro.inicio) >= delta:
            registro.inicio = now
            registro.intentos = 1
            registro.save(update_fields=["inicio", "intentos"])
            return 1 <= maximo

        if registro.intentos >= maximo:
            return False

        registro.intentos += 1
        registro.save(update_fields=["intentos"])
        return True


def registrar_cuenta(
    *,
    nombre: str,
    email: str,
    password: str,
    area_habitual: str = "",
    cuit_cuil: str = "",
    legajo: str = "",
) -> CuentaLocal | None:
    """Registra una nueva cuenta local con usuario estándar de Django.

    Devuelve None de forma neutra ante correos duplicados en CuentaLocal
    o en User (preexistente o legado). Valida contraseña y formato en servidor.
    """
    nombre_limpio = (nombre or "").strip()
    if not nombre_limpio:
        raise ValidationError("El nombre completo es obligatorio.")
    if len(nombre_limpio) > 150:
        raise ValidationError("El nombre completo no debe superar 150 caracteres.")

    email_norm = normalizar_correo(email)
    if not email_norm:
        raise ValidationError("El correo electrónico es obligatorio.")
    if len(email_norm) > 254:
        raise ValidationError("El correo electrónico no debe superar 254 caracteres.")
    validate_email(email_norm)

    area_limpia = (area_habitual or "").strip()
    if len(area_limpia) > 150:
        raise ValidationError("El área habitual no debe superar 150 caracteres.")

    cuit_cuil_limpio = (cuit_cuil or "").strip()
    if len(cuit_cuil_limpio) > 20:
        raise ValidationError("El CUIT/CUIL no debe superar 20 caracteres.")

    legajo_limpio = (legajo or "").strip()
    if len(legajo_limpio) > 50:
        raise ValidationError("El legajo no debe superar 50 caracteres.")

    if not password:
        raise ValidationError("La contraseña es obligatoria.")

    user_model = get_user_model()
    temp_user = user_model(
        username=f"local_{uuid.uuid4().hex}",
        email=email_norm,
        first_name=nombre_limpio[:150],
    )
    validate_password(password, user=temp_user)

    try:
        with transaction.atomic():
            if CuentaLocal.objects.filter(email__iexact=email_norm).exists():
                return None
            if user_model.objects.filter(email__iexact=email_norm).exists():
                return None

            user = user_model.objects.create_user(
                username=f"local_{uuid.uuid4().hex}",
                email=email_norm,
                password=password,
                first_name=nombre_limpio[:150],
                is_active=True,
            )
            cuenta = CuentaLocal.objects.create(
                user=user,
                email=email_norm,
                nombre_completo=nombre_limpio[:150],
                area_habitual=area_limpia,
                cuit_cuil=cuit_cuil_limpio,
                legajo=legajo_limpio,
            )
            return cuenta
    except IntegrityError:
        return None


def token_verificacion(cuenta: CuentaLocal) -> str:
    """Genera un token firmado temporal para verificación de casilla de correo."""
    pwd_fp = hashlib.sha256(cuenta.user.password.encode("utf-8")).hexdigest()
    payload = {
        "pk": cuenta.pk,
        "email": cuenta.email,
        "nonce": str(cuenta.nonce_verificacion),
        "pwd_fp": pwd_fp,
    }
    return signing.dumps(payload, salt="identidad.verificar-correo")


def verificar_correo(token: str) -> CuentaLocal:
    """Verifica el correo de una cuenta a partir de un token firmado y válido.

    Invalida el token rotando el nonce. No aprueba la cuenta.
    """
    max_age = getattr(settings, "LOCAL_VERIFICATION_TIMEOUT", 86400)
    try:
        payload = signing.loads(
            token,
            salt="identidad.verificar-correo",
            max_age=max_age,
        )
    except signing.SignatureExpired:
        raise ValidationError("El enlace de verificación ha vencido.") from None
    except signing.BadSignature:
        raise ValidationError("El enlace de verificación es inválido.") from None

    if not isinstance(payload, dict):
        raise ValidationError("El enlace de verificación es inválido.")

    pk = payload.get("pk")
    email = payload.get("email")
    nonce = payload.get("nonce")
    pwd_fp = payload.get("pwd_fp")

    if not pk or not email or not nonce or not pwd_fp:
        raise ValidationError("El enlace de verificación es inválido.")

    with transaction.atomic():
        try:
            cuenta = CuentaLocal.objects.select_for_update().select_related("user").get(pk=pk)
        except CuentaLocal.DoesNotExist:
            raise ValidationError("La cuenta no existe.") from None

        if cuenta.email.casefold() != str(email).casefold():
            raise ValidationError("El enlace no corresponde a la cuenta indicada.")

        if str(cuenta.nonce_verificacion) != str(nonce):
            raise ValidationError("El enlace de verificación ya fue utilizado o no es válido.")

        current_pwd_fp = hashlib.sha256(cuenta.user.password.encode("utf-8")).hexdigest()
        if str(pwd_fp) != current_pwd_fp:
            raise ValidationError(
                "El enlace de verificación ya no es válido por cambio de contraseña."
            )

        if cuenta.email_verificado_en is not None:
            raise ValidationError("El correo electrónico ya ha sido verificado.")

        if not cuenta.user.is_active:
            raise ValidationError("La cuenta de usuario se encuentra inactiva o suspendida.")

        if cuenta.estado != CuentaLocal.Estado.PENDIENTE:
            raise ValidationError("La cuenta no se encuentra en estado pendiente.")

        cuenta.email_verificado_en = timezone.now()
        cuenta.nonce_verificacion = uuid.uuid4()
        cuenta.save(update_fields=["email_verificado_en", "nonce_verificacion"])
        return cuenta


def enviar_verificacion(cuenta: CuentaLocal, *, base_url: str) -> bool:
    """Envía correo de verificación con enlace temporal.

    Devuelve True si el envío fue exitoso, o False si falló o fue limitado.
    """
    if cuenta.estado != CuentaLocal.Estado.PENDIENTE:
        return False
    if cuenta.email_verificado_en is not None:
        return False
    if not cuenta.user.is_active:
        return False

    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    if parsed.path not in ("", "/"):
        return False

    min_interval = getattr(settings, "LOCAL_VERIFY_RESEND_MIN_INTERVAL", 60)
    max_hourly = getattr(settings, "LOCAL_VERIFY_RESEND_MAX_HOURLY", 5)

    if cuenta.ultimo_envio is not None:
        if (timezone.now() - cuenta.ultimo_envio).total_seconds() < min_interval:
            return False

    clave_min = f"verif_min:{cuenta.pk}"
    clave_hora = f"verif_hora:{cuenta.pk}"
    if not limitar(clave_min, maximo=1, segundos=min_interval):
        return False
    if not limitar(clave_hora, maximo=max_hourly, segundos=3600):
        return False

    token = token_verificacion(cuenta)
    query = urllib.parse.urlencode({"token": token})
    url = f"{base_url.rstrip('/')}/cuentas/verificar/?{query}"

    subject = "Verificación de correo electrónico"
    message = (
        f"Hola {cuenta.nombre_completo},\n\n"
        "Para verificar su correo electrónico y continuar con la solicitud de acceso, "
        f"ingrese al siguiente enlace:\n\n{url}\n\n"
        "Si no solicitó esta cuenta, ignore este mensaje.\n"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)

    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[cuenta.email],
            fail_silently=False,
        )
        if sent != 1:
            return False
    except Exception as exc:
        logger.warning(
            "Fallo en envío de correo de verificación para cuenta_id=%s: %s",
            cuenta.pk,
            type(exc).__name__,
        )
        return False

    cuenta.ultimo_envio = timezone.now()
    cuenta.save(update_fields=["ultimo_envio"])
    return True


def decidir_cuenta(
    *,
    actor: Any,
    cuenta_id: int,
    aprobar: bool,
    motivo: str = "",
) -> CuentaLocal:
    """Decide administrativamente la aprobación o rechazo de una cuenta local."""
    if not isinstance(aprobar, bool):
        raise ValidationError("El parámetro aprobar debe ser un valor booleano.")

    if not has_capability(actor, "identidad.administrar_cuentas"):
        raise PermissionDenied("No posee capacidad para administrar cuentas.")

    with transaction.atomic():
        try:
            cuenta = (
                CuentaLocal.objects.select_for_update().select_related("user").get(pk=cuenta_id)
            )
        except CuentaLocal.DoesNotExist:
            raise ValidationError("La cuenta local no existe.") from None

        if not cuenta.user.is_active:
            raise ValidationError(
                "No se puede decidir una cuenta con usuario inactivo o suspendido."
            )

        if cuenta.estado != CuentaLocal.Estado.PENDIENTE or cuenta.decidida_en is not None:
            raise ValidationError("La cuenta ya ha sido decidida previamente.")

        if cuenta.email_verificado_en is None:
            raise ValidationError("No se puede decidir una cuenta con correo no verificado.")

        actor_user_id = None
        if isinstance(actor, Actor):
            actor_user_id = actor.subject_id
        elif hasattr(actor, "pk"):
            actor_user_id = actor.pk

        if actor_user_id is not None and actor_user_id == cuenta.user_id:
            raise PermissionDenied("Un usuario no puede decidir sobre su propia cuenta.")

        motivo_limpio = (motivo or "").strip()
        if len(motivo_limpio) > 2000:
            raise ValidationError("El motivo no debe superar 2000 caracteres.")

        now = timezone.now()
        cuenta.decidida_en = now
        if actor_user_id is not None:
            cuenta.decidida_por_id = actor_user_id

        if aprobar:
            cuenta.estado = CuentaLocal.Estado.APROBADA
            cuenta.motivo = motivo_limpio
            grupo, _ = Group.objects.get_or_create(name="local_solicitante")
            cuenta.user.groups.add(grupo)
        else:
            if not motivo_limpio:
                raise ValidationError("El motivo de rechazo es obligatorio.")
            cuenta.estado = CuentaLocal.Estado.RECHAZADA
            cuenta.motivo = motivo_limpio

        cuenta.save(update_fields=["estado", "motivo", "decidida_en", "decidida_por"])
        return cuenta
