"""Agrega referencias anulables, migra datos existentes y asigna versiones únicas."""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


CODIGOS = {
    'PRESUPUESTO': 'PRESUPUESTO_PROFORMA',
    'TICKET_PROVEEDOR': 'TICKET_NO_FISCAL',
    'FACTURA_EMITIDA': 'FACTURA_EMITIDA_XUBIO',
    'NOTA_CREDITO': 'NOTA_CREDITO_XUBIO',
    'NOTA_DEBITO': 'NOTA_DEBITO_XUBIO',
}


def completar_cabeceras(apps, schema_editor):
    """Migra referencias y códigos conocidos sin leer ni mover archivos."""
    alias = schema_editor.connection.alias
    Gasto = apps.get_model('gastos', 'SolicitudGasto')
    Base = apps.get_model('comunes', 'TramiteBase')
    Documento = apps.get_model('documentos', 'Documento')
    for gasto in Gasto.objects.using(alias).order_by('pk').iterator():
        base, _ = Base.objects.using(alias).get_or_create(
            circuito='GASTO', numero_publico=gasto.pk,
            defaults={'solicitante_actor_id': str(gasto.solicitante_id)},
        )
        for doc in Documento.objects.using(alias).filter(solicitud_gasto_id=gasto.pk).iterator():
            Documento.objects.using(alias).filter(pk=doc.pk).update(
                tramite_base_id=base.pk, serie=uuid.uuid4(), referencia_version=uuid.uuid4(),
                tipo=CODIGOS.get(doc.tipo, doc.tipo),
            )


def restaurar_codigos(apps, schema_editor):
    Documento = apps.get_model('documentos', 'Documento')
    documentos = Documento.objects.using(schema_editor.connection.alias)
    if documentos.filter(solicitud_gasto_id__isnull=True).exists() or documentos.filter(
        version__gt=1
    ).exists():
        raise IrreversibleError('No revertir después de crear documentos de facturación o versiones.')
    for anterior, nuevo in CODIGOS.items():
        documentos.filter(tipo=nuevo).update(tipo=anterior)


class Migration(migrations.Migration):

    dependencies = [
        ('comunes', '0001_initial'),
        ('documentos', '0003_alter_documento_procedencia_alter_documento_tipo'),
        ('gastos', '0003_pagoexterno_eventopagoexterno'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='documento',
            name='reemplaza',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sucesor', to='documentos.documento'),
        ),
        migrations.AddField(
            model_name='documento',
            name='referencia_version',
            field=models.UUIDField(null=True, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name='documento',
            name='serie',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.AddField(
            model_name='documento',
            name='tramite_base',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='documentos', to='comunes.tramitebase'),
        ),
        migrations.AddField(
            model_name='documento',
            name='version',
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
        migrations.AlterField(
            model_name='documento',
            name='solicitud_gasto',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='documentos', to='gastos.solicitudgasto'),
        ),
        migrations.AlterField(
            model_name='documento',
            name='tipo',
            field=models.CharField(choices=[('PRESUPUESTO_PROFORMA', 'Presupuesto o proforma'), ('FACTURA_PROVEEDOR', 'Factura de proveedor'), ('TICKET_NO_FISCAL', 'Ticket no fiscal'), ('COMPROBANTE_PAGO', 'Comprobante de pago'), ('CONSTANCIA_RETENCION_ATP', 'Constancia ATP'), ('FACTURA_EMITIDA_XUBIO', 'Factura emitida en Xubio'), ('NOTA_CREDITO_XUBIO', 'Nota de crédito de Xubio'), ('NOTA_DEBITO_XUBIO', 'Nota de débito de Xubio'), ('COMPROBANTE_COBRO', 'Comprobante de cobro')], max_length=64),
        ),
        migrations.AddConstraint(
            model_name='documento',
            constraint=models.UniqueConstraint(fields=('serie', 'version'), name='uq_documento_serie_version'),
        ),
        migrations.RunPython(completar_cabeceras, restaurar_codigos),
        migrations.AlterField(
            model_name='documento', name='referencia_version',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='documento', name='serie',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddConstraint(
            model_name='documento',
            constraint=models.CheckConstraint(condition=models.Q(('version__gt', 0)), name='ck_documento_version'),
        ),
    ]
