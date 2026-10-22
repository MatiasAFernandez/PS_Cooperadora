"""Protege vínculos y auditoría incluso en escrituras SQL directas."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0006_comprobantes_externos")]
    operations = [
        migrations.RunSQL(
            sql="""
        CREATE FUNCTION facturacion_proteger_comprobante() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            base_id bigint;
            estado_solicitud text;
            tipo_documental text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Comprobante registrado inmutable' USING ERRCODE = '23514';
            END IF;
            SELECT tramite_base_id, estado INTO base_id, estado_solicitud
                FROM facturacion_solicitudfacturacion WHERE id = NEW.solicitud_id;
            IF NOT FOUND OR estado_solicitud = 'BORRADOR_TECNICO' THEN
                RAISE EXCEPTION 'Solicitud no operativa' USING ERRCODE = '23514';
            END IF;
            tipo_documental := CASE NEW.tipo
                WHEN 'FACTURA' THEN 'FACTURA_EMITIDA_XUBIO'
                WHEN 'NOTA_CREDITO' THEN 'NOTA_CREDITO_XUBIO'
                WHEN 'NOTA_DEBITO' THEN 'NOTA_DEBITO_XUBIO' ELSE NULL END;
            IF NEW.procedencia <> 'EXTERNO_XUBIO' OR NEW.letra !~ '^[A-Z]$'
                OR NEW.cuit_emisor !~ '^[0-9]{11}$' OR NOT EXISTS (
                    SELECT 1 FROM documentos_documento WHERE id = NEW.documento_id
                        AND tramite_base_id = base_id AND tipo = tipo_documental
                        AND procedencia = 'EXTERNO_XUBIO' AND formato = 'application/pdf'
                ) THEN
                RAISE EXCEPTION 'Respaldo o identidad incompatible' USING ERRCODE = '23514';
            END IF;
            IF NEW.tipo <> 'FACTURA' AND NOT EXISTS (
                SELECT 1 FROM facturacion_comprobanteexterno
                WHERE id = NEW.factura_origen_id AND tipo = 'FACTURA'
                    AND solicitud_id = NEW.solicitud_id AND cuit_emisor = NEW.cuit_emisor
                    AND letra = NEW.letra
            ) THEN
                RAISE EXCEPTION 'Factura de origen incompatible' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER facturacion_comprobante_inmutable BEFORE INSERT OR UPDATE OR DELETE
            ON facturacion_comprobanteexterno FOR EACH ROW
            EXECUTE FUNCTION facturacion_proteger_comprobante();
        """,
            reverse_sql="""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM facturacion_comprobanteexterno) THEN
                RAISE EXCEPTION 'Hay comprobantes: conservar historial y migrar hacia adelante';
            END IF;
        END; $$;
        DROP TRIGGER facturacion_comprobante_inmutable ON facturacion_comprobanteexterno;
        DROP FUNCTION facturacion_proteger_comprobante();
        """,
        )
    ]
