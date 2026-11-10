from importlib import import_module

from django.db import migrations

original = import_module("documentos.migrations.0006_integridad_versiones")
guarda = original.Migration.operations[0].sql.split("CREATE TRIGGER documentos_version")[0]
guarda = guarda.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
nueva = guarda.replace(
    "NEW.tipo NOT IN (", "NEW.tipo NOT IN ('ANEXO_SOLICITUD', "
)


class Migration(migrations.Migration):
    dependencies = [("documentos", "0011_alter_documento_tipo")]
    operations = [migrations.RunSQL(
        nueva,
        reverse_sql="""
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM documentos_documento WHERE tipo='ANEXO_SOLICITUD') THEN
        RAISE EXCEPTION 'Hay anexos de formulario: migrar hacia adelante';
    END IF;
END; $$;
""" + guarda,
    )]
