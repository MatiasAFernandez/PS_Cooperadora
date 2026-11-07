from django.db import migrations


GUARDA_COBRO = r"""
CREATE OR REPLACE FUNCTION facturacion_proteger_cobro() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    blancos text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0'
        || U&'\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A'
        || U&'\2028\2029\202F\205F\3000';
BEGIN
    IF TG_OP='UPDATE' AND TG_TABLE_NAME='facturacion_cobroexterno' THEN
        PERFORM facturacion_bloquear_abierta(
            (SELECT tramite_base_id FROM facturacion_solicitudfacturacion
             WHERE id=OLD.solicitud_id));
        IF NOT OLD.sustituido AND NEW.sustituido
            AND (to_jsonb(NEW)-'sustituido')=(to_jsonb(OLD)-'sustituido')
            {sustitucion} THEN
            RETURN NEW;
        END IF;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Hecho de cobro inmutable' USING ERRCODE='23514';
    END IF;

    IF TG_TABLE_NAME = 'facturacion_cobroexterno' THEN
        IF NEW.sustituido OR (NEW.reemplaza_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM facturacion_cobroexterno c
            JOIN facturacion_solicitudfacturacion s ON s.id=c.solicitud_id
            JOIN comunes_tramitebase b ON b.id=s.tramite_base_id
            WHERE c.id=NEW.reemplaza_id AND c.sustituido
            AND c.solicitud_id=NEW.solicitud_id
            AND length(btrim(NEW.motivo_correccion,blancos)) BETWEEN 1 AND 2000
            {sucesor}
        )) THEN
            RAISE EXCEPTION 'Correccion de cobro incompatible' USING ERRCODE='23514';
        END IF;
        IF length(btrim(NEW.numero_operacion, blancos)) = 0 OR
           NEW.numero_operacion <> btrim(NEW.numero_operacion, blancos) OR NOT EXISTS (
            SELECT 1 FROM facturacion_solicitudfacturacion s
            JOIN documentos_documento d ON d.tramite_base_id = s.tramite_base_id
            WHERE s.id = NEW.solicitud_id AND s.estado <> 'BORRADOR_TECNICO'
            AND d.id = NEW.documento_id AND d.tipo = 'COMPROBANTE_COBRO'
            AND d.procedencia IN ('SOLICITANTE', 'EXTERNO_BANCO')
        ) THEN
            RAISE EXCEPTION 'Operacion o respaldo de cobro incompatible' USING ERRCODE='23514';
        END IF;
    ELSE
        IF NOT EXISTS (SELECT 1 FROM facturacion_cobroexterno
            WHERE id=NEW.cobro_id AND NOT sustituido) THEN
            RAISE EXCEPTION 'Cobro sustituido no verificable' USING ERRCODE='23514';
        END IF;
        IF length(NEW.motivo) > 2000 OR
           (NEW.resultado = 'RECHAZADO' AND length(btrim(NEW.motivo, blancos)) = 0) THEN
            RAISE EXCEPTION 'Motivo de verificacion invalido' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END; $$;
"""


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0020_rectificacion_cobro")]
    operations = [
        migrations.RunSQL(
            sql=GUARDA_COBRO.format(
                sustitucion="""
                    AND NOT EXISTS (
                        SELECT 1 FROM facturacion_verificacioncobro v
                        LEFT JOIN facturacion_rectificacioncobro r ON r.verificacion_id=v.id
                        WHERE v.cobro_id=OLD.id AND v.resultado='CONFIRMADO' AND r.id IS NULL
                    )
                """,
                sucesor="""
                    AND (NEW.procedencia='INTERNO_COOPERADORA' OR (
                        NEW.procedencia='SOLICITANTE'
                        AND b.solicitante_actor_id=NEW.actor_id::text
                        AND EXISTS (
                            WITH RECURSIVE cadena AS (
                                SELECT c.actor_id, c.procedencia, c.reemplaza_id
                                UNION ALL
                                SELECT a.actor_id, a.procedencia, a.reemplaza_id
                                FROM facturacion_cobroexterno a
                                JOIN cadena h ON a.id=h.reemplaza_id
                            )
                            SELECT 1 FROM cadena WHERE reemplaza_id IS NULL
                            AND actor_id=NEW.actor_id AND procedencia='SOLICITANTE'
                        )
                    ))
                """,
            ),
            reverse_sql=GUARDA_COBRO.format(
                sustitucion="""
                    AND OLD.procedencia='SOLICITANTE'
                    AND NOT EXISTS (SELECT 1 FROM facturacion_verificacioncobro
                        WHERE cobro_id=OLD.id AND resultado='CONFIRMADO')
                """,
                sucesor="""
                    AND c.actor_id=NEW.actor_id
                    AND NEW.procedencia='SOLICITANTE' AND c.procedencia='SOLICITANTE'
                    AND b.solicitante_actor_id=NEW.actor_id::text
                    AND NOT EXISTS (SELECT 1 FROM facturacion_verificacioncobro
                        WHERE cobro_id=c.id AND resultado='CONFIRMADO')
                """,
            ),
        ),
    ]
