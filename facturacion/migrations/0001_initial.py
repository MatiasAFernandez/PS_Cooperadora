"""Crea la solicitud técnica mínima y sus eventos; #23 añadirá el recorrido."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('comunes', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SolicitudFacturacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado', models.CharField(default='BORRADOR_TECNICO', max_length=40)),
                ('tramite_base', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='solicitud_facturacion', to='comunes.tramitebase')),
            ],
        ),
        migrations.CreateModel(
            name='EventoFacturacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_evento', models.CharField(max_length=40)),
                ('fecha_hora', models.DateTimeField(auto_now_add=True)),
                ('estado_resultante', models.CharField(max_length=40)),
                ('motivo_o_detalle', models.TextField(blank=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('solicitud', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='eventos', to='facturacion.solicitudfacturacion')),
            ],
            options={
                'ordering': ['fecha_hora', 'id'],
            },
        ),
    ]
