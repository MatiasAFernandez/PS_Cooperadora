"""Protege circuito, puente de gastos y cadena inmutable de versiones en SQL."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0005_alter_documento_tramite_base"),
        ("facturacion", "0002_integridad_y_eventos"),
    ]
    operations = [migrations.RunSQL(
        sql="""
        CREATE FUNCTION documentos_validar_version() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            base comunes_tramitebase%ROWTYPE;
            anterior documentos_documento%ROWTYPE;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Version documental inmutable' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF NEW IS DISTINCT FROM OLD THEN
                    RAISE EXCEPTION 'Version documental inmutable' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            SELECT * INTO base FROM comunes_tramitebase WHERE id = NEW.tramite_base_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Cabecera inexistente' USING ERRCODE = '23503';
            END IF;
            IF base.circuito = 'GASTO' THEN
                IF NEW.solicitud_gasto_id IS DISTINCT FROM base.numero_publico OR NOT EXISTS (
                    SELECT 1 FROM gastos_solicitudgasto WHERE id = NEW.solicitud_gasto_id
                        AND solicitante_id::text = base.solicitante_actor_id
                ) OR NEW.tipo NOT IN ('PRESUPUESTO_PROFORMA', 'FACTURA_PROVEEDOR',
                    'TICKET_NO_FISCAL', 'COMPROBANTE_PAGO', 'CONSTANCIA_RETENCION_ATP') THEN
                    RAISE EXCEPTION 'Documento de gastos incompatible' USING ERRCODE = '23514';
                END IF;
            ELSE
                IF NEW.solicitud_gasto_id IS NOT NULL OR NOT EXISTS (
                    SELECT 1 FROM facturacion_solicitudfacturacion
                        WHERE tramite_base_id = base.id AND id = base.numero_publico
                ) OR NEW.tipo NOT IN ('FACTURA_EMITIDA_XUBIO', 'NOTA_CREDITO_XUBIO',
                    'NOTA_DEBITO_XUBIO', 'COMPROBANTE_COBRO') THEN
                    RAISE EXCEPTION 'Documento de facturacion incompatible' USING ERRCODE = '23514';
                END IF;
            END IF;
            IF NEW.reemplaza_id IS NULL THEN
                IF NEW.version <> 1 THEN
                    RAISE EXCEPTION 'Version inicial invalida' USING ERRCODE = '23514';
                END IF;
            ELSE
                -- Un bloqueo sobre la raíz serializa todos los reemplazos y
                -- la verificación C01, incluso si se escribe mediante SQL.
                PERFORM 1 FROM documentos_documento WHERE serie = NEW.serie AND version = 1
                    FOR UPDATE;
                SELECT * INTO anterior FROM documentos_documento WHERE id = NEW.reemplaza_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Version previa inexistente' USING ERRCODE = '23503';
                END IF;
                IF (NEW.serie, NEW.tramite_base_id, NEW.tipo, NEW.version)
                    IS DISTINCT FROM
                   (anterior.serie, anterior.tramite_base_id, anterior.tipo, anterior.version + 1)
                THEN
                    RAISE EXCEPTION 'Cadena de versiones incompatible' USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER documentos_version BEFORE INSERT OR UPDATE OR DELETE
            ON documentos_documento FOR EACH ROW EXECUTE FUNCTION documentos_validar_version();
        """,
        reverse_sql="""
        DROP TRIGGER documentos_version ON documentos_documento;
        DROP FUNCTION documentos_validar_version();
        """,
    )]
