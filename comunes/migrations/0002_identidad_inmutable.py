"""Defensa de identidad en PostgreSQL, también frente a QuerySet y SQL directo."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("comunes", "0001_initial")]
    operations = [migrations.RunSQL(
        sql="""
        CREATE FUNCTION comunes_identidad_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.id, NEW.circuito, NEW.numero_publico, NEW.solicitante_actor_id, NEW.creado_en)
                IS DISTINCT FROM
               (OLD.id, OLD.circuito, OLD.numero_publico, OLD.solicitante_actor_id, OLD.creado_en)
            THEN
                RAISE EXCEPTION 'Identidad de tramite inmutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER comunes_identidad_inmutable BEFORE UPDATE ON comunes_tramitebase
            FOR EACH ROW EXECUTE FUNCTION comunes_identidad_inmutable();
        """,
        reverse_sql="""
        DROP TRIGGER comunes_identidad_inmutable ON comunes_tramitebase;
        DROP FUNCTION comunes_identidad_inmutable();
        """,
    )]
