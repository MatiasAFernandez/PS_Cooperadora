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

    def add_arguments(self, parser):
        parser.add_argument("--verificacion-cobros", action="store_true")
        parser.add_argument("--facturacion", action="store_true")
        parser.add_argument("--revision-documental", action="store_true")

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
            if options.get("facturacion"):
                perfil = (
                    "demo_facturacion_solicitante"
                    if username in {"demo_a", "demo_b"}
                    else "demo_facturacion_operadora"
                    if username == "demo_o"
                    else "demo_facturacion_lectura"
                )
                correo = {
                    "demo_a": "solicitante.a@example.invalid",
                    "demo_b": "solicitante.b@example.invalid",
                    "demo_o": "operador.o@example.invalid",
                    "demo_l": "lectura.l@example.invalid",
                }[username]
                if user.email and user.email != correo:
                    raise CommandError(f"La cuenta {username} ya tiene otro correo; revisala.")
                user.email = correo
                user.save(update_fields=["email"])
                user.groups.add(groups[perfil])
                if username != "demo_l":
                    user.groups.add(
                        *(
                            groups[g]
                            for g in (
                                "demo_documentos_aporte",
                                "demo_documentos_metadatos",
                                "demo_documentos_descarga",
                            )
                        )
                    )
            # Preparar un circuito no revoca grupos conocidos de otro.
            if options.get("revision_documental") and username == "demo_o":
                user.groups.add(*(
                    groups[g] for g in (
                        "demo_documentos_revision", "demo_documentos_metadatos",
                        "demo_documentos_descarga",
                    )
                ))
            if options.get("verificacion_cobros") and username == "demo_o":
                user.groups.add(groups["demo_verificacion_cobros"])
            user.groups.add(groups[group_name])

        self.stdout.write(self.style.SUCCESS("Grupos y cuentas sintéticas preparados."))
        self.stdout.write("Asigná una contraseña local a cada cuenta con changepassword.")
