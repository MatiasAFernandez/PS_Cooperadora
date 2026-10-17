"""Agrega la cabecera común anulable para poder migrar datos existentes."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("comunes", "0002_identidad_inmutable"),
        ("gastos", "0003_pagoexterno_eventopagoexterno"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitudgasto",
            name="tramite_base",
            field=models.OneToOneField(
                editable=False,
                help_text=(
                    "Cabecera común protegida; número y titular coinciden con la solicitud."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="solicitud_gasto",
                to="comunes.tramitebase",
            ),
        ),
    ]
