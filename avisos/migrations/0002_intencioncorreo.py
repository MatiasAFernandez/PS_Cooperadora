# Generated manually for avisos.IntencionCorreo (additive, sin backfill)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("avisos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="IntencionCorreo",
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
                    "estado",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("en_proceso", "En proceso"),
                            ("aceptado", "Aceptado por el servidor"),
                            ("fallido", "Fallido"),
                            ("omitido", "Omitido"),
                            ("incierto", "Incierto"),
                        ],
                        default="pendiente",
                        max_length=20,
                    ),
                ),
                ("intentos", models.PositiveIntegerField(default=0)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                ("ultimo_intento_en", models.DateTimeField(blank=True, null=True)),
                ("aceptado_en", models.DateTimeField(blank=True, null=True)),
                (
                    "direccion_ultimo_intento",
                    models.EmailField(blank=True, default="", max_length=254),
                ),
                (
                    "codigo_resultado",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "aviso",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="intencion_correo",
                        to="avisos.aviso",
                    ),
                ),
            ],
            options={
                "ordering": ["pk"],
            },
        ),
        migrations.AddIndex(
            model_name="intencioncorreo",
            index=models.Index(
                fields=["estado"],
                name="idx_intencion_correo_estado",
            ),
        ),
    ]
