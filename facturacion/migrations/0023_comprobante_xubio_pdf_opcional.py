"""Referencias Xubio sin bytes; conserva revisión de archivos reales y cobros."""

from importlib import import_module

import django.db.models.deletion
from django.db import migrations, models


anterior = import_module("facturacion.migrations.0022_correccion_comprobante_externo")
sql_anterior = next(op.sql for op in anterior.Migration.operations if isinstance(op, migrations.RunSQL))
guarda = sql_anterior.split("CREATE FUNCTION facturacion_exigir_sucesor_comprobante")[0]
guarda_nueva = guarda.replace(
    "OR NOT EXISTS (\n            SELECT 1 FROM documentos_documento",
    "OR NOT ((NEW.documento_id IS NULL AND NEW.procedencia='EXTERNO_XUBIO') OR EXISTS (\n"
    "            SELECT 1 FROM documentos_documento",
).replace(
    "AND procedencia=NEW.procedencia AND formato='application/pdf'\n        ) THEN",
    "AND procedencia=NEW.procedencia AND formato='application/pdf'\n        )) THEN",
).replace(
    "    IF NEW.tipo <> 'FACTURA'",
    "    IF NEW.documento_id IS NULL AND NEW.reemplaza_id IS NOT NULL AND EXISTS (\n"
    "        SELECT 1 FROM facturacion_comprobanteexterno\n"
    "        WHERE id=NEW.reemplaza_id AND documento_id IS NOT NULL\n"
    "    ) THEN RAISE EXCEPTION 'No se permite retirar el respaldo existente'\n"
    "        USING ERRCODE='23514'; END IF;\n"
    "    IF NEW.tipo <> 'FACTURA'",
)
resolucion = anterior.RESOLUCION_CON_RECTIFICACION.replace(
    "FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id",
    "FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id AND NOT sustituido",
)
resolucion_nueva = resolucion.replace(
    "SELECT facturacion_respaldo_actual('comprobante',id,documento_id)\n"
    "            FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id AND NOT sustituido",
    "SELECT facturacion_respaldo_actual('comprobante',id,documento_id)\n"
    "            FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id AND NOT sustituido\n"
    "                AND documento_id IS NOT NULL",
)


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0022_correccion_comprobante_externo")]
    operations = [
        migrations.AlterField(
            model_name="comprobanteexterno",
            name="documento",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                to="documentos.documento",
            ),
        ),
        migrations.RunSQL(
            guarda_nueva + resolucion_nueva,
            reverse_sql="""
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM facturacion_comprobanteexterno WHERE documento_id IS NULL) THEN
        RAISE EXCEPTION 'Hay referencias sin archivo: migrar hacia adelante';
    END IF;
END; $$;
""" + guarda + resolucion,
        ),
    ]
