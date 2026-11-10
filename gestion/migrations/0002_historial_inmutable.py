from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("gestion", "0001_initial")]
    operations = [migrations.RunSQL(
        sql="""
CREATE FUNCTION gestion_historial_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'El historial del formulario es inmutable' USING ERRCODE='23514';
END; $$;
CREATE TRIGGER version_formulario_inmutable BEFORE UPDATE OR DELETE
ON gestion_versionformulario FOR EACH ROW EXECUTE FUNCTION gestion_historial_inmutable();
CREATE TRIGGER respuesta_formulario_inmutable BEFORE UPDATE OR DELETE
ON gestion_respuestaformulario FOR EACH ROW EXECUTE FUNCTION gestion_historial_inmutable();
""",
        reverse_sql="""
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM gestion_versionformulario)
        OR EXISTS (SELECT 1 FROM gestion_respuestaformulario) THEN
        RAISE EXCEPTION 'Hay historial: conservar y migrar hacia adelante';
    END IF;
END; $$;
DROP TRIGGER version_formulario_inmutable ON gestion_versionformulario;
DROP TRIGGER respuesta_formulario_inmutable ON gestion_respuestaformulario;
DROP FUNCTION gestion_historial_inmutable();
""",
    )]
