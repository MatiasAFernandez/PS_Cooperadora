# Generated manually for SPEC-027 (InvitacionCuentaLocal)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identidad", "0004_cambioperfilescuentalocal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InvitacionCuentaLocal",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("aceptada_en", models.DateTimeField(blank=True, null=True)),
                ("ultimo_intento_en", models.DateTimeField(blank=True, null=True)),
                (
                    "estado_envio",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente"),
                            ("ENVIADA", "Enviada"),
                            ("ERROR", "Error"),
                        ],
                        default="PENDIENTE",
                        max_length=20,
                    ),
                ),
                (
                    "creada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invitaciones_cuentas_creadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cuenta",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invitacion_administrativa",
                        to="identidad.cuentalocal",
                    ),
                ),
            ],
        ),
    ]
