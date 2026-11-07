from django.db import migrations

EVENTO_TERMINAL_ANTERIOR = r"""
CREATE OR REPLACE FUNCTION facturacion_exigir_evento_terminal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    blancos text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0'
        || U&'\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A'
        || U&'\2028\2029\202F\205F\3000';
BEGIN
    IF NEW.estado IN ('CERRADA','ANULADA') AND NOT EXISTS (
        SELECT 1 FROM facturacion_eventofacturacion WHERE solicitud_id=NEW.id
            AND estado_resultante=NEW.estado
            AND tipo_evento=CASE WHEN NEW.estado='CERRADA' THEN 'CIERRE' ELSE 'ANULACION' END
            AND length(btrim(motivo_o_detalle,blancos))>0
            AND snapshot_datos->>'version_resultante'=NEW.version_concurrencia::text
    ) THEN
        RAISE EXCEPTION 'Falta evento de resolucion' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END; $$;
"""


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0016_cierre_con_excedente")]

    operations = [
        migrations.RunSQL(
            EVENTO_TERMINAL_ANTERIOR.replace(
                "AND length(btrim(motivo_o_detalle,blancos))>0",
                "AND (NEW.estado='CERRADA' OR length(btrim(motivo_o_detalle,blancos))>0)",
            ),
            reverse_sql=EVENTO_TERMINAL_ANTERIOR,
        ),
    ]
