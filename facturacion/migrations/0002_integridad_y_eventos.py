"""Restringe la hija a su circuito y protege los eventos propios de facturación."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0001_initial"), ("comunes", "0002_identidad_inmutable"),
    ]
    operations = [migrations.RunSQL(
        sql="""
        CREATE FUNCTION facturacion_validar_cabecera() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'No se borra la solicitud auditable' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF (NEW.id, NEW.tramite_base_id) IS DISTINCT FROM (OLD.id, OLD.tramite_base_id)
                THEN
                    RAISE EXCEPTION 'Cabecera inmutable' USING ERRCODE = '23514';
                END IF;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM comunes_tramitebase
                WHERE id = NEW.tramite_base_id AND circuito = 'FACTURACION'
                    AND numero_publico = NEW.id) THEN
                RAISE EXCEPTION 'Solicitud y cabecera incompatibles' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER facturacion_cabecera BEFORE INSERT OR UPDATE OR DELETE
            ON facturacion_solicitudfacturacion FOR EACH ROW
            EXECUTE FUNCTION facturacion_validar_cabecera();
        CREATE FUNCTION facturacion_evento_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Evento de facturacion inmutable' USING ERRCODE = '23514';
        END; $$;
        CREATE TRIGGER facturacion_evento_inmutable BEFORE UPDATE OR DELETE
            ON facturacion_eventofacturacion FOR EACH ROW
            EXECUTE FUNCTION facturacion_evento_inmutable();
        """,
        reverse_sql="""
        DROP TRIGGER facturacion_evento_inmutable ON facturacion_eventofacturacion;
        DROP FUNCTION facturacion_evento_inmutable();
        DROP TRIGGER facturacion_cabecera ON facturacion_solicitudfacturacion;
        DROP FUNCTION facturacion_validar_cabecera();
        """,
    )]
