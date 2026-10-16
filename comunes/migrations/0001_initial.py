"""Crea la cabecera común sin copiar estados o reglas de los circuitos."""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='TramiteBase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('circuito', models.CharField(choices=[('GASTO', 'Gastos'), ('FACTURACION', 'Facturación')], editable=False, max_length=20)),
                ('numero_publico', models.PositiveIntegerField(editable=False)),
                ('solicitante_actor_id', models.CharField(editable=False, max_length=150)),
                ('centro_costo_codigo', models.CharField(blank=True, max_length=50, null=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('circuito', 'numero_publico'), name='uq_tramite_circuito_numero_publico'), models.CheckConstraint(condition=models.Q(('circuito__in', ['GASTO', 'FACTURACION'])), name='ck_tramite_circuito_valido'), models.CheckConstraint(condition=models.Q(('numero_publico__gt', 0)), name='ck_tramite_numero_positivo'), models.CheckConstraint(condition=models.Q(('solicitante_actor_id', ''), _negated=True), name='ck_tramite_titular_no_vacio')],
            },
        ),
    ]
