"""Exige cabecera documental tras completar el backfill de 0004."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comunes', '0001_initial'),
        ('documentos', '0004_documento_reemplaza_documento_referencia_version_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documento',
            name='tramite_base',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='documentos', to='comunes.tramitebase'),
        ),
    ]
