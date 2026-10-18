"""Conserva hechos de revisión incluso ante UPDATE/DELETE SQL directos."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("documentos", "0007_revision_documental")]
    operations = [
        migrations.RunSQL(
            sql="""
        CREATE FUNCTION documentos_proteger_revision() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Revision documental inmutable' USING ERRCODE = '23514';
            END IF;
            IF length(NEW.motivo) > 2000 OR
               (NEW.resultado <> 'ACEPTADO' AND length(btrim(NEW.motivo)) = 0) THEN
                RAISE EXCEPTION 'Motivo de revision invalido' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER documentos_revision_inmutable BEFORE INSERT OR UPDATE OR DELETE
            ON documentos_revisiondocumento FOR EACH ROW
            EXECUTE FUNCTION documentos_proteger_revision();
        """,
            reverse_sql="""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM documentos_revisiondocumento) THEN
                RAISE EXCEPTION 'Hay revisiones: conservar historial y migrar hacia adelante';
            END IF;
        END; $$;
        DROP TRIGGER documentos_revision_inmutable ON documentos_revisiondocumento;
        DROP FUNCTION documentos_proteger_revision();
        """,
        )
    ]
