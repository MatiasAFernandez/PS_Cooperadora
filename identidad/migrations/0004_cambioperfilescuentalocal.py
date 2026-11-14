# Generated manually for SPEC-026 (CambioPerfilesCuentaLocal)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identidad", "0003_cambioactividadcuentalocal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CambioPerfilesCuentaLocal",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("fecha", models.DateTimeField(auto_now_add=True)),
                ("motivo", models.TextField(max_length=2000)),
                ("perfiles_anteriores", models.JSONField()),
                ("perfiles_nuevos", models.JSONField()),
                (
                    "autor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cambios_perfiles_realizados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cuenta",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cambios_perfiles",
                        to="identidad.cuentalocal",
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha", "-pk"],
            },
        ),
    ]
