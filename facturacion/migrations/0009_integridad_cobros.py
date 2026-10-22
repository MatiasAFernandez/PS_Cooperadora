from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0008_cobroexterno_verificacioncobro_and_more")]
    operations = [
        migrations.RunSQL(
            sql=r"""
        CREATE FUNCTION facturacion_proteger_cobro() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            blancos text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0'
                || U&'\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A'
                || U&'\2028\2029\202F\205F\3000';
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Hecho de cobro inmutable' USING ERRCODE = '23514';
            END IF;
            IF TG_TABLE_NAME = 'facturacion_cobroexterno' THEN
                IF length(btrim(NEW.numero_operacion, blancos)) = 0 OR
                   NEW.numero_operacion <> btrim(NEW.numero_operacion, blancos) OR NOT EXISTS (
                    SELECT 1 FROM facturacion_solicitudfacturacion s
                    JOIN documentos_documento d ON d.tramite_base_id = s.tramite_base_id
                    WHERE s.id = NEW.solicitud_id AND s.estado <> 'BORRADOR_TECNICO'
                    AND d.id = NEW.documento_id AND d.tipo = 'COMPROBANTE_COBRO'
                    AND d.procedencia IN ('SOLICITANTE', 'EXTERNO_BANCO')
                ) THEN
                    RAISE EXCEPTION 'Operacion o respaldo de cobro incompatible' USING ERRCODE = '23514';
                END IF;
            ELSE
                IF length(NEW.motivo) > 2000 OR
                   (NEW.resultado = 'RECHAZADO' AND length(btrim(NEW.motivo, blancos)) = 0) THEN
                    RAISE EXCEPTION 'Motivo de verificacion invalido' USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER facturacion_cobro_inmutable BEFORE INSERT OR UPDATE OR DELETE
            ON facturacion_cobroexterno FOR EACH ROW EXECUTE FUNCTION facturacion_proteger_cobro();
        CREATE TRIGGER facturacion_verificacion_cobro_inmutable BEFORE INSERT OR UPDATE OR DELETE
            ON facturacion_verificacioncobro FOR EACH ROW EXECUTE FUNCTION facturacion_proteger_cobro();
        """,
            reverse_sql="""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM facturacion_cobroexterno) THEN
                RAISE EXCEPTION 'Hay cobros: conservar historial y migrar hacia adelante';
            END IF;
        END; $$;
        DROP TRIGGER facturacion_verificacion_cobro_inmutable ON facturacion_verificacioncobro;
        DROP TRIGGER facturacion_cobro_inmutable ON facturacion_cobroexterno;
        DROP FUNCTION facturacion_proteger_cobro();
        """,
        )
    ]
