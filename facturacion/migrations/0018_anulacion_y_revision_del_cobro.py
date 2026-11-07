from django.db import migrations

RESOLUCION_ANTERIOR = """
CREATE OR REPLACE FUNCTION facturacion_validar_resolucion() RETURNS trigger LANGUAGE plpgsql AS $$
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
        WHERE NOT c.sustituido AND c.solicitud_id=NEW.id AND v.resultado='CONFIRMADO';
    IF NEW.presento_comprobante_pago AND NEW.modalidad_cobro IN ('MERCADO_PAGO','BNA_COMUN','BNA_UVT','NBCH')
        AND NOT EXISTS (SELECT 1 FROM facturacion_cobroexterno WHERE solicitud_id=NEW.id
            AND medio=NEW.modalidad_cobro AND numero_operacion=btrim(NEW.numero_operacion_declarado)) THEN
        RAISE EXCEPTION 'Operacion declarada sin registrar y verificar' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM facturacion_cobroexterno c
        WHERE NOT c.sustituido AND c.solicitud_id=NEW.id AND NOT EXISTS (
            SELECT 1 FROM facturacion_verificacioncobro WHERE cobro_id=c.id)) OR
        (NEW.estado='CERRADA' AND (NOT hay_factura OR neto<=0 OR confirmado<neto
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
            WHERE NOT c.sustituido AND c.solicitud_id=NEW.id AND v.resultado='CONFIRMADO' AND NEW.estado='CERRADA'
    LOOP
        IF NOT facturacion_documento_aceptado(doc) THEN
            RAISE EXCEPTION 'Respaldo pendiente de aceptacion vigente' USING ERRCODE='23514';
        END IF;
    END LOOP;
    RETURN NEW;
END; $$;
"""

# La guarda aaa_facturacion_abierta toma la cabecera antes de esta comprobación.
VERIFICACION_CON_RESPALDO_ACEPTADO = """
CREATE FUNCTION facturacion_exigir_respaldo_para_confirmar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM facturacion_cobroexterno c WHERE c.id=NEW.cobro_id
            AND facturacion_documento_aceptado(
                facturacion_respaldo_actual('cobro',c.id,c.documento_id)
            )
    ) THEN
        RAISE EXCEPTION 'La confirmacion exige respaldo vigente aceptado' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER facturacion_verificacion_respaldo_aceptado
    BEFORE INSERT ON facturacion_verificacioncobro
    FOR EACH ROW WHEN (NEW.resultado='CONFIRMADO')
    EXECUTE FUNCTION facturacion_exigir_respaldo_para_confirmar();
"""


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0017_motivo_solo_para_anulacion")]

    operations = [
        migrations.RunSQL(
            RESOLUCION_ANTERIOR.replace(
                "(NEW.estado='ANULADA' AND (confirmado<>0 OR (hay_factura AND neto<>0)))",
                "(NEW.estado='ANULADA' AND confirmado<>0)",
            ),
            reverse_sql=RESOLUCION_ANTERIOR,
        ),
        migrations.RunSQL(
            VERIFICACION_CON_RESPALDO_ACEPTADO,
            reverse_sql="""
                DROP TRIGGER facturacion_verificacion_respaldo_aceptado
                    ON facturacion_verificacioncobro;
                DROP FUNCTION facturacion_exigir_respaldo_para_confirmar();
            """,
        ),
    ]
