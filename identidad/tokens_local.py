"""Generador de tokens y señales de revocación de enlaces para acceso local (SPEC-022)."""

import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db.models.signals import pre_save
from django.dispatch import receiver

from identidad.models import CuentaLocal


class TokenRecuperacionLocal(PasswordResetTokenGenerator):
    """Generador de tokens de recuperación enlazado al estado fresco y nonce de CuentaLocal."""

    def _make_hash_value(self, user: Any, timestamp: int) -> str:
        base = super()._make_hash_value(user, timestamp)
        if not getattr(user, "pk", None):
            return f"{base}|sin_pk|{getattr(user, 'is_active', False)}"

        # Consulta fresca directa para evitar cache de relación en memoria
        cuenta_data = (
            CuentaLocal.objects.filter(user_id=user.pk)
            .values("nonce_verificacion", "estado", "email", "email_verificado_en")
            .first()
        )
        if cuenta_data is None:
            return f"{base}|sin_cuenta|{user.is_active}"

        nonce = cuenta_data["nonce_verificacion"]
        estado = cuenta_data["estado"]
        email = cuenta_data["email"]
        verificado = cuenta_data["email_verificado_en"]
        verificado_str = verificado.isoformat() if verificado else ""

        return f"{base}|{nonce}|{estado}|{email}|{verificado_str}|{user.is_active}"


token_recuperacion_local = TokenRecuperacionLocal()


@receiver(
    pre_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="identidad.revocar_enlaces_actividad",
)
def revocar_enlaces_por_cambio_actividad(
    sender: Any,
    instance: Any,
    update_fields: Any = None,
    **kwargs: Any,
) -> None:
    """Invalida enlaces pendientes al cambiar el estado de actividad del usuario."""
    if not instance.pk:
        return

    # Si se especificaron update_fields y no contiene is_active, saltear de inmediato
    # sin consultar la base de datos (por ejemplo al registrar last_login en sesión).
    if update_fields is not None and "is_active" not in update_fields:
        return

    is_active_previo = (
        sender.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
    )
    if is_active_previo is None:
        return

    if is_active_previo != instance.is_active:
        # Rotar nonce_verificacion atómicamente; si no existe CuentaLocal no afecta nada
        CuentaLocal.objects.filter(user_id=instance.pk).update(nonce_verificacion=uuid.uuid4())
