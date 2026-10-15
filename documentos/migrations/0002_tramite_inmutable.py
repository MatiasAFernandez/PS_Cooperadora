"""La relación documental con el trámite no puede reasignarse tras el alta."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("documentos", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION documentos_impedir_reasignacion() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.solicitud_gasto_id IS DISTINCT FROM OLD.solicitud_gasto_id THEN
                        RAISE EXCEPTION 'No se puede reasignar un documento a otro tramite'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END;
                $$;
                CREATE TRIGGER documentos_tramite_inmutable
                BEFORE UPDATE OF solicitud_gasto_id ON documentos_documento
                FOR EACH ROW EXECUTE FUNCTION documentos_impedir_reasignacion();
            """,
            reverse_sql="""
                DROP TRIGGER documentos_tramite_inmutable ON documentos_documento;
                DROP FUNCTION documentos_impedir_reasignacion();
            """,
        )
    ]
