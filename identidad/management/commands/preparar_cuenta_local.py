"""Comando de gestión para preparar técnicamente una cuenta local preexistente."""

from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from identidad.cuentas import normalizar_correo
from identidad.models import CuentaLocal


class Command(BaseCommand):
    """Bootstrap técnico explícito de un usuario preexistente a cuenta local aprobada."""

    help = "Prepara técnicamente una CuentaLocal aprobada para un User preexistente de Django."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--username",
            type=str,
            required=True,
            help="Nombre de usuario del User existente en Django.",
        )
        parser.add_argument(
            "--correo-verificado",
            action="store_true",
            default=False,
            help="Confirma la comprobación previa de la casilla de correo por quien ejecuta.",
        )
        parser.add_argument(
            "--administrador",
            action="store_true",
            default=False,
            help="Concede únicamente pertenencia al grupo 'local_administracion'.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not getattr(settings, "LOCAL_IDENTITY_ENABLED", False):
            raise CommandError("El acceso local no está habilitado (LOCAL_IDENTITY_ENABLED=False).")

        if not options.get("correo_verificado"):
            raise CommandError(
                "Debe confirmar explícitamente que el correo fue comprobado mediante el flag "
                "--correo-verificado."
            )

        username = options["username"]
        es_admin = bool(options.get("administrador"))
        user_model = get_user_model()

        with transaction.atomic():
            user = user_model.objects.select_for_update().filter(username=username).first()
            if user is None:
                raise CommandError(f"El usuario '{username}' no existe.")

            if not user.is_active:
                raise CommandError(f"El usuario '{username}' se encuentra inactivo.")

            if not user.has_usable_password():
                raise CommandError(
                    f"El usuario '{username}' no tiene una contraseña utilizable configurada."
                )

            email_norm = normalizar_correo(user.email or "")
            if not email_norm:
                raise CommandError(
                    f"El usuario '{username}' no posee un correo electrónico registrado."
                )

            try:
                validate_email(email_norm)
            except ValidationError:
                raise CommandError(
                    f"El correo electrónico '{email_norm}' no tiene un formato válido."
                ) from None

            # Rechazar colisiones con otras cuentas o usuarios
            if (
                CuentaLocal.objects.filter(email__iexact=email_norm)
                .exclude(user_id=user.pk)
                .exists()
            ):
                raise CommandError(
                    "El correo electrónico ya se encuentra registrado en otra cuenta local."
                )

            if (
                user_model.objects.filter(email__iexact=email_norm)
                .exclude(pk=user.pk)
                .exists()
            ):
                raise CommandError(
                    "El correo electrónico ya pertenece a otro usuario registrado."
                )

            cuenta = CuentaLocal.objects.select_for_update().filter(user_id=user.pk).first()

            if cuenta is not None:
                if normalizar_correo(cuenta.email) != email_norm:
                    raise CommandError(
                        "La cuenta local existente tiene un correo diferente al del usuario."
                    )

                if cuenta.estado in (CuentaLocal.Estado.PENDIENTE, CuentaLocal.Estado.RECHAZADA):
                    raise CommandError(
                        f"La cuenta local ya existe en estado {cuenta.get_estado_display()}. "
                        "Debe resolverse por la bandeja administrativa."
                    )
            else:
                now = timezone.now()
                nombre = (user.get_full_name() or "").strip() or user.get_username()
                cuenta = CuentaLocal.objects.create(
                    user=user,
                    email=email_norm,
                    nombre_completo=nombre[:150],
                    estado=CuentaLocal.Estado.APROBADA,
                    email_verificado_en=now,
                    decidida_en=now,
                    motivo="Habilitación técnica explícita por comando local.",
                )

            # Asignar grupo de solicitante local
            grupo_sol, _ = Group.objects.get_or_create(name="local_solicitante")
            user.groups.add(grupo_sol)

            if es_admin:
                grupo_admin, _ = Group.objects.get_or_create(name="local_administracion")
                user.groups.add(grupo_admin)

        self.stdout.write(
            self.style.SUCCESS(f"Cuenta local preparada exitosamente para el usuario '{username}'.")
        )
