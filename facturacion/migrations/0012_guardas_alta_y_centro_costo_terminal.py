from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0011_resolucion_integridad")]

    operations = [
        migrations.RunSQL(
            sql="""
        CREATE FUNCTION facturacion_impedir_alta_terminal() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.estado IN ('CERRADA','ANULADA') THEN
                RAISE EXCEPTION 'La resolucion requiere una solicitud existente y su evento'
                    USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER facturacion_alta_no_terminal BEFORE INSERT
            ON facturacion_solicitudfacturacion FOR EACH ROW
            EXECUTE FUNCTION facturacion_impedir_alta_terminal();

        CREATE FUNCTION facturacion_proteger_centro_costo_terminal() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.circuito='FACTURACION'
                AND NEW.centro_costo_codigo IS DISTINCT FROM OLD.centro_costo_codigo
                AND EXISTS (SELECT 1 FROM facturacion_solicitudfacturacion
                    WHERE tramite_base_id=OLD.id AND estado IN ('CERRADA','ANULADA')) THEN
                RAISE EXCEPTION 'Centro de costo de solicitud resuelta inmutable'
                    USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER facturacion_centro_costo_terminal BEFORE UPDATE
            ON comunes_tramitebase FOR EACH ROW
            EXECUTE FUNCTION facturacion_proteger_centro_costo_terminal();
        """,
            reverse_sql="""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM facturacion_solicitudfacturacion WHERE estado IN ('CERRADA','ANULADA'))
                OR EXISTS (SELECT 1 FROM facturacion_actualizacionrespaldo) THEN
                RAISE EXCEPTION 'Hay resoluciones o actualizaciones: migrar hacia adelante';
            END IF;
        END; $$;
        DROP TRIGGER facturacion_centro_costo_terminal ON comunes_tramitebase;
        DROP FUNCTION facturacion_proteger_centro_costo_terminal();
        DROP TRIGGER facturacion_alta_no_terminal ON facturacion_solicitudfacturacion;
        DROP FUNCTION facturacion_impedir_alta_terminal();
        """,
        )
    ]
