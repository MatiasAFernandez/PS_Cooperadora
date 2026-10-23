from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0010_actualizacionrespaldo_and_more")]
    operations = [
        migrations.RunSQL(
            sql=r"""
        CREATE FUNCTION facturacion_respaldo_actual(clase text, objeto bigint, original bigint)
        RETURNS bigint LANGUAGE sql STABLE AS $$
            SELECT COALESCE((SELECT nuevo_id FROM facturacion_actualizacionrespaldo
                WHERE (clase='comprobante' AND comprobante_id=objeto)
                   OR (clase='cobro' AND cobro_id=objeto) ORDER BY id DESC LIMIT 1), original);
        $$;
        CREATE FUNCTION facturacion_documento_aceptado(doc bigint) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT COALESCE((SELECT resultado='ACEPTADO' FROM documentos_revisiondocumento
                WHERE documento_id=doc ORDER BY id DESC LIMIT 1), false)
                AND NOT EXISTS (SELECT 1 FROM documentos_documento WHERE reemplaza_id=doc);
        $$;
        CREATE FUNCTION facturacion_bloquear_abierta(base bigint) RETURNS void LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM 1 FROM comunes_tramitebase WHERE id=base FOR UPDATE;
            IF EXISTS (SELECT 1 FROM facturacion_solicitudfacturacion
                WHERE tramite_base_id=base AND estado IN ('CERRADA','ANULADA')) THEN
                RAISE EXCEPTION 'Tramite terminal' USING ERRCODE='23514';
            END IF;
        END; $$;
        CREATE FUNCTION facturacion_guardar_operacion_abierta() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            base bigint;
            sol bigint;
            original bigint;
            previo bigint;
            blancos text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0'
                || U&'\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A'
                || U&'\2028\2029\202F\205F\3000';
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Actualizacion documental inmutable' USING ERRCODE='23514';
            END IF;
            IF TG_TABLE_NAME='documentos_documento' THEN
                base := NEW.tramite_base_id;
            ELSIF TG_TABLE_NAME='documentos_revisiondocumento' THEN
                SELECT tramite_base_id INTO base FROM documentos_documento WHERE id=NEW.documento_id;
            ELSIF TG_TABLE_NAME='facturacion_verificacioncobro' THEN
                SELECT s.tramite_base_id INTO base FROM facturacion_cobroexterno c
                    JOIN facturacion_solicitudfacturacion s ON s.id=c.solicitud_id WHERE c.id=NEW.cobro_id;
            ELSIF TG_TABLE_NAME='facturacion_actualizacionrespaldo' THEN
                IF NEW.comprobante_id IS NOT NULL THEN
                    SELECT solicitud_id, documento_id INTO sol,original
                        FROM facturacion_comprobanteexterno WHERE id=NEW.comprobante_id;
                ELSE
                    SELECT solicitud_id, documento_id INTO sol,original
                        FROM facturacion_cobroexterno WHERE id=NEW.cobro_id;
                END IF;
                SELECT tramite_base_id INTO base FROM facturacion_solicitudfacturacion WHERE id=sol;
            ELSE
                SELECT tramite_base_id INTO base FROM facturacion_solicitudfacturacion
                    WHERE id=NEW.solicitud_id;
            END IF;
            IF EXISTS (SELECT 1 FROM comunes_tramitebase WHERE id=base AND circuito='FACTURACION') THEN
                PERFORM facturacion_bloquear_abierta(base);
            END IF;
            IF TG_TABLE_NAME='facturacion_actualizacionrespaldo' THEN
                previo := facturacion_respaldo_actual(
                    CASE WHEN NEW.comprobante_id IS NOT NULL THEN 'comprobante' ELSE 'cobro' END,
                    COALESCE(NEW.comprobante_id,NEW.cobro_id),original);
                IF length(NEW.motivo)>2000 OR length(btrim(NEW.motivo,blancos))=0 OR
                   EXISTS (SELECT 1 FROM facturacion_actualizacionrespaldo WHERE nuevo_id=NEW.nuevo_id) OR
                   EXISTS (SELECT 1 FROM facturacion_comprobanteexterno
                       WHERE documento_id=NEW.nuevo_id AND id IS DISTINCT FROM NEW.comprobante_id) OR
                   EXISTS (SELECT 1 FROM facturacion_cobroexterno
                       WHERE documento_id=NEW.nuevo_id AND id IS DISTINCT FROM NEW.cobro_id) OR
                   NEW.anterior_id <> previo OR NOT EXISTS (
                    SELECT 1 FROM documentos_documento a JOIN documentos_documento n
                        ON n.serie=a.serie AND n.tipo=a.tipo AND n.tramite_base_id=a.tramite_base_id
                    WHERE a.id=previo AND n.id=NEW.nuevo_id AND n.version>a.version
                        AND n.tramite_base_id=base
                        AND (NEW.comprobante_id IS NULL OR n.formato='application/pdf')
                        AND NOT EXISTS (SELECT 1 FROM documentos_documento WHERE reemplaza_id=n.id)
                ) THEN
                    RAISE EXCEPTION 'Actualizacion de respaldo invalida' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER aaa_facturacion_abierta BEFORE INSERT ON documentos_documento
            FOR EACH ROW EXECUTE FUNCTION facturacion_guardar_operacion_abierta();
        CREATE TRIGGER aaa_facturacion_abierta BEFORE INSERT ON documentos_revisiondocumento
            FOR EACH ROW EXECUTE FUNCTION facturacion_guardar_operacion_abierta();
        CREATE TRIGGER aaa_facturacion_abierta BEFORE INSERT ON facturacion_comprobanteexterno
            FOR EACH ROW EXECUTE FUNCTION facturacion_guardar_operacion_abierta();
        CREATE TRIGGER aaa_facturacion_abierta BEFORE INSERT ON facturacion_cobroexterno
            FOR EACH ROW EXECUTE FUNCTION facturacion_guardar_operacion_abierta();
        CREATE TRIGGER aaa_facturacion_abierta BEFORE INSERT ON facturacion_verificacioncobro
            FOR EACH ROW EXECUTE FUNCTION facturacion_guardar_operacion_abierta();
        CREATE TRIGGER aaa_facturacion_abierta BEFORE INSERT OR UPDATE OR DELETE
            ON facturacion_actualizacionrespaldo FOR EACH ROW
            EXECUTE FUNCTION facturacion_guardar_operacion_abierta();

        CREATE FUNCTION facturacion_validar_resolucion() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE neto numeric; confirmado numeric; hay_factura boolean; doc bigint;
        BEGIN
            IF OLD.estado IN ('CERRADA','ANULADA') THEN
                RAISE EXCEPTION 'Tramite terminal inmutable' USING ERRCODE='23514';
            END IF;
            IF NEW.estado NOT IN ('CERRADA','ANULADA') THEN RETURN NEW; END IF;
            IF NEW.version_concurrencia <> OLD.version_concurrencia+1 THEN
                RAISE EXCEPTION 'Revision de resolucion invalida' USING ERRCODE='23514';
            END IF;
            PERFORM 1 FROM comunes_tramitebase WHERE id=NEW.tramite_base_id FOR UPDATE;
            SELECT COALESCE(SUM(CASE WHEN tipo='NOTA_CREDITO' THEN -importe ELSE importe END),0),
                COALESCE(bool_or(tipo='FACTURA'),false) INTO neto,hay_factura
                FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id;
            SELECT COALESCE(SUM(c.importe),0) INTO confirmado FROM facturacion_cobroexterno c
                JOIN facturacion_verificacioncobro v ON v.cobro_id=c.id
                WHERE c.solicitud_id=NEW.id AND v.resultado='CONFIRMADO';
            IF NEW.presento_comprobante_pago AND NEW.modalidad_cobro IN ('MERCADO_PAGO','BNA_COMUN','BNA_UVT','NBCH')
                AND NOT EXISTS (SELECT 1 FROM facturacion_cobroexterno WHERE solicitud_id=NEW.id
                    AND medio=NEW.modalidad_cobro AND numero_operacion=btrim(NEW.numero_operacion_declarado)) THEN
                RAISE EXCEPTION 'Operacion declarada sin registrar y verificar' USING ERRCODE='23514';
            END IF;
            IF EXISTS (SELECT 1 FROM facturacion_cobroexterno c
                WHERE c.solicitud_id=NEW.id AND NOT EXISTS (
                    SELECT 1 FROM facturacion_verificacioncobro WHERE cobro_id=c.id)) OR
                (NEW.estado='CERRADA' AND (NOT hay_factura OR neto<=0 OR confirmado<>neto
                    OR OLD.estado='OBSERVADA')) OR
                (NEW.estado='ANULADA' AND (confirmado<>0 OR (hay_factura AND neto<>0))) THEN
                RAISE EXCEPTION 'Resolucion con pendientes' USING ERRCODE='23514';
            END IF;
            FOR doc IN
                SELECT facturacion_respaldo_actual('comprobante',id,documento_id)
                    FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id
                UNION ALL
                SELECT facturacion_respaldo_actual('cobro',c.id,c.documento_id)
                    FROM facturacion_cobroexterno c JOIN facturacion_verificacioncobro v ON v.cobro_id=c.id
                    WHERE c.solicitud_id=NEW.id AND v.resultado='CONFIRMADO' AND NEW.estado='CERRADA'
            LOOP
                IF NOT facturacion_documento_aceptado(doc) THEN
                    RAISE EXCEPTION 'Respaldo pendiente de aceptacion vigente' USING ERRCODE='23514';
                END IF;
            END LOOP;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER facturacion_resolucion BEFORE UPDATE ON facturacion_solicitudfacturacion
            FOR EACH ROW EXECUTE FUNCTION facturacion_validar_resolucion();
        CREATE FUNCTION facturacion_exigir_evento_terminal() RETURNS trigger LANGUAGE plpgsql AS $$
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
        CREATE CONSTRAINT TRIGGER facturacion_evento_terminal AFTER UPDATE
            ON facturacion_solicitudfacturacion DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION facturacion_exigir_evento_terminal();
        CREATE UNIQUE INDEX uq_facturacion_evento_terminal ON facturacion_eventofacturacion(solicitud_id)
            WHERE tipo_evento IN ('CIERRE','ANULACION');
        CREATE FUNCTION facturacion_guardar_evento() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE base bigint; estado text; revision integer;
        BEGIN
            SELECT tramite_base_id INTO base FROM facturacion_solicitudfacturacion WHERE id=NEW.solicitud_id;
            PERFORM 1 FROM comunes_tramitebase WHERE id=base FOR UPDATE;
            SELECT s.estado,s.version_concurrencia INTO estado,revision
                FROM facturacion_solicitudfacturacion s WHERE s.id=NEW.solicitud_id;
            IF estado IN ('CERRADA','ANULADA') AND (
                NEW.tipo_evento <> CASE WHEN estado='CERRADA' THEN 'CIERRE' ELSE 'ANULACION' END
                OR NEW.estado_resultante <> estado
                OR (NEW.snapshot_datos->>'version_resultante') IS DISTINCT FROM revision::text
            ) THEN
                RAISE EXCEPTION 'Evento posterior a resolucion' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $$;
        CREATE TRIGGER facturacion_evento_abierto BEFORE INSERT ON facturacion_eventofacturacion
            FOR EACH ROW EXECUTE FUNCTION facturacion_guardar_evento();
        """,
            reverse_sql="""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM facturacion_solicitudfacturacion WHERE estado IN ('CERRADA','ANULADA'))
                OR EXISTS (SELECT 1 FROM facturacion_actualizacionrespaldo) THEN
                RAISE EXCEPTION 'Hay resoluciones o actualizaciones: migrar hacia adelante';
            END IF;
        END; $$;
        DROP INDEX uq_facturacion_evento_terminal;
        DROP TRIGGER facturacion_evento_abierto ON facturacion_eventofacturacion;
        DROP FUNCTION facturacion_guardar_evento();
        DROP TRIGGER facturacion_evento_terminal ON facturacion_solicitudfacturacion;
        DROP FUNCTION facturacion_exigir_evento_terminal();
        DROP TRIGGER facturacion_resolucion ON facturacion_solicitudfacturacion;
        DROP FUNCTION facturacion_validar_resolucion();
        DROP TRIGGER aaa_facturacion_abierta ON documentos_documento;
        DROP TRIGGER aaa_facturacion_abierta ON documentos_revisiondocumento;
        DROP TRIGGER aaa_facturacion_abierta ON facturacion_comprobanteexterno;
        DROP TRIGGER aaa_facturacion_abierta ON facturacion_cobroexterno;
        DROP TRIGGER aaa_facturacion_abierta ON facturacion_verificacioncobro;
        DROP TRIGGER aaa_facturacion_abierta ON facturacion_actualizacionrespaldo;
        DROP FUNCTION facturacion_guardar_operacion_abierta();
        DROP FUNCTION facturacion_bloquear_abierta(bigint);
        DROP FUNCTION facturacion_documento_aceptado(bigint);
        DROP FUNCTION facturacion_respaldo_actual(text,bigint,bigint);
        """,
        )
    ]
