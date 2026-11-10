from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

GRUPOS = (
    "demo_operadora",
    "demo_gastos_pago",
    "demo_facturacion_operadora",
    "demo_documentos_aporte",
    "demo_documentos_revision",
    "demo_verificacion_cobros",
    "demo_resolucion_facturacion",
    "demo_documentos_metadatos",
    "demo_documentos_descarga",
    "demo_administracion",
)


class Command(BaseCommand):
    help = "Prepara un administrador local; no cambia contraseñas ni otorga superusuario."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEMO_IDENTITY_ENABLED:
            raise CommandError("Habilitá la identidad local de demo antes de preparar esta cuenta.")
        usuario, nuevo = get_user_model().objects.get_or_create(username=options["username"])
        if nuevo:
            usuario.set_unusable_password()
            usuario.email = "admin@example.invalid"
            usuario.save()
        if not usuario.is_active:
            raise CommandError(
                "La cuenta está desactivada; revisá su situación antes de asignarle permisos."
            )
        for nombre in GRUPOS:
            usuario.groups.add(Group.objects.get_or_create(name=nombre)[0])
        self.stdout.write(
            "Administrador local preparado. La contraseña se administra con changepassword."
        )
