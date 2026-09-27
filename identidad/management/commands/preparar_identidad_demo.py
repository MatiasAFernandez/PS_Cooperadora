"""Preparar cuentas sintéticas sin publicar contraseñas reutilizables."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identidad.services import GROUP_CAPABILITIES

DEMO_USERS = {
    "demo_a": "demo_solicitante",
    "demo_b": "demo_solicitante",
    "demo_o": "demo_operadora",
    "demo_l": "demo_lectura",
}


class Command(BaseCommand):
    help = "Crea los cuatro usuarios de demo sin contraseñas; se establecen con changepassword."

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEMO_IDENTITY_ENABLED:
            raise CommandError("Habilitá DEMO_IDENTITY_ENABLED sólo en el entorno local de demo.")

        user_model = get_user_model()
        groups = {name: Group.objects.get_or_create(name=name)[0] for name in GROUP_CAPABILITIES}

        for username, group_name in DEMO_USERS.items():
            user, created = user_model.objects.get_or_create(username=username)
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            elif (
                not user.is_active
                or user.is_staff
                or user.is_superuser
                or user.groups.exclude(name__in=GROUP_CAPABILITIES).exists()
            ):
                raise CommandError(
                    f"La cuenta {username} ya existe con otra configuración; revisala manualmente."
                )
            user.groups.set([groups[group_name]])

        self.stdout.write(self.style.SUCCESS("Grupos y cuentas sintéticas preparados."))
        self.stdout.write("Asigná una contraseña local a cada cuenta con changepassword.")
