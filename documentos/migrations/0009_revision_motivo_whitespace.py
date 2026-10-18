"""Actualiza la guarda también en bases que ya aplicaron 0008 durante la revisión."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("documentos", "0008_revision_inmutable")]
    operations = [migrations.RunSQL(
        sql=r"""
        CREATE OR REPLACE FUNCTION documentos_proteger_revision()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            -- Whitespace de str.strip(), explícito para no depender de la locale SQL.
            blancos text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0'
                || U&'\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A'
                || U&'\2028\2029\202F\205F\3000';
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Revision documental inmutable' USING ERRCODE = '23514';
            END IF;
            IF length(NEW.motivo) > 2000 OR
               (NEW.resultado <> 'ACEPTADO' AND length(btrim(NEW.motivo, blancos)) = 0) THEN
                RAISE EXCEPTION 'Motivo de revision invalido' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        """,
        # No reinstalar una guarda más débil al volver a 0008. Su reversa propia
        # sigue protegiendo el historial y retira la función sólo con tabla vacía.
        reverse_sql=migrations.RunSQL.noop,
    )]
