# Generated manually without active DB connection for avisos.Aviso

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Aviso",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[("nueva_solicitud_gasto", "Nueva solicitud de gasto")],
                        default="nueva_solicitud_gasto",
                        max_length=50,
                    ),
                ),
                ("solicitud_id", models.PositiveBigIntegerField()),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("leida_en", models.DateTimeField(blank=True, null=True)),
                (
                    "destinatario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="avisos",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-creada_en", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="aviso",
            index=models.Index(
                fields=["destinatario", "leida_en", "creada_en"],
                name="idx_aviso_dest_leida_creada",
            ),
        ),
        migrations.AddConstraint(
            model_name="aviso",
            constraint=models.UniqueConstraint(
                fields=("destinatario", "tipo", "solicitud_id"),
                name="unique_aviso_destinatario_tipo_solicitud",
            ),
        ),
    ]
