from importlib import import_module

import django.db.models.deletion
from django.db import migrations, models


RESOLUCION_CON_RECTIFICACION = import_module(
    "facturacion.migrations.0020_rectificacion_cobro"
).RESOLUCION_ANTERIOR.replace(
    "AND v.resultado='CONFIRMADO'",
    "AND v.resultado='CONFIRMADO'\n"
    "            AND NOT EXISTS (SELECT 1 FROM facturacion_rectificacioncobro r"
    " WHERE r.verificacion_id=v.id)",
)

GUARDA_COMPROBANTE = """
CREATE OR REPLACE FUNCTION facturacion_proteger_comprobante() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    base_id bigint;
    estado_solicitud text;
    tipo_documental text;
BEGIN
    {sustitucion}
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Comprobante registrado inmutable' USING ERRCODE='23514';
    END IF;
    SELECT tramite_base_id, estado INTO base_id, estado_solicitud
        FROM facturacion_solicitudfacturacion WHERE id=NEW.solicitud_id;
    IF NOT FOUND OR estado_solicitud='BORRADOR_TECNICO' THEN
        RAISE EXCEPTION 'Solicitud no operativa' USING ERRCODE='23514';
    END IF;
    tipo_documental := CASE NEW.tipo
        WHEN 'FACTURA' THEN 'FACTURA_EMITIDA_XUBIO'
        WHEN 'NOTA_CREDITO' THEN 'NOTA_CREDITO_XUBIO'
        WHEN 'NOTA_DEBITO' THEN 'NOTA_DEBITO_XUBIO' ELSE NULL END;
    IF NEW.procedencia NOT IN ('EXTERNO_XUBIO', 'EXTERNO_OTRO') OR NEW.letra !~ '^[A-Z]$'
        OR NEW.cuit_emisor !~ '^[0-9]{{11}}$' OR NOT EXISTS (
            SELECT 1 FROM documentos_documento WHERE id=NEW.documento_id
                AND tramite_base_id=base_id AND tipo=tipo_documental
                AND procedencia=NEW.procedencia AND formato='application/pdf'
        ) THEN
        RAISE EXCEPTION 'Respaldo o identidad incompatible' USING ERRCODE='23514';
    END IF;
    IF NEW.tipo <> 'FACTURA' AND NOT EXISTS (
        SELECT 1 FROM facturacion_comprobanteexterno
        WHERE id=NEW.factura_origen_id AND tipo='FACTURA'
            AND solicitud_id=NEW.solicitud_id AND cuit_emisor=NEW.cuit_emisor
            AND letra=NEW.letra {factura_vigente}
    ) THEN
        RAISE EXCEPTION 'Factura de origen incompatible' USING ERRCODE='23514';
    END IF;
    {sucesor}
    RETURN NEW;
END; $$;
"""


class Migration(migrations.Migration):
    dependencies = [("facturacion", "0021_correccion_datos_cobro")]

    operations = [
        migrations.RemoveConstraint(
            model_name="comprobanteexterno", name="uq_comprobante_identidad_externa"
        ),
        migrations.RemoveConstraint(
            model_name="comprobanteexterno", name="uq_una_factura_por_solicitud"
        ),
        migrations.AddField(
            model_name="comprobanteexterno",
            name="sustituido",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="comprobanteexterno",
            name="motivo_correccion",
            field=models.TextField(blank=True, max_length=2000),
        ),
        migrations.AddField(
            model_name="comprobanteexterno",
            name="reemplaza",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="correccion",
                to="facturacion.comprobanteexterno",
            ),
        ),
        migrations.AddConstraint(
            model_name="comprobanteexterno",
            constraint=models.UniqueConstraint(
                condition=models.Q(sustituido=False),
                fields=("cuit_emisor", "tipo", "letra", "punto_venta", "numero"),
                name="uq_comprobante_identidad_externa",
            ),
        ),
        migrations.AddConstraint(
            model_name="comprobanteexterno",
            constraint=models.UniqueConstraint(
                condition=models.Q(tipo="FACTURA", sustituido=False),
                fields=("solicitud",),
                name="uq_una_factura_por_solicitud",
            ),
        ),
        migrations.RunSQL(
            GUARDA_COMPROBANTE.format(
                sustitucion="""
                    IF TG_OP='UPDATE' AND NOT OLD.sustituido AND NEW.sustituido
                        AND (to_jsonb(NEW)-'sustituido')=(to_jsonb(OLD)-'sustituido') THEN
                        PERFORM facturacion_bloquear_abierta(
                            (SELECT tramite_base_id FROM facturacion_solicitudfacturacion
                             WHERE id=OLD.solicitud_id));
                        RETURN NEW;
                    END IF;
                """,
                factura_vigente="AND NOT sustituido",
                sucesor=r"""
                    IF NEW.sustituido OR (NEW.reemplaza_id IS NOT NULL AND (
                        NEW.motivo_correccion !~ '\S' OR length(NEW.motivo_correccion)>2000
                        OR NOT EXISTS (
                            SELECT 1 FROM facturacion_comprobanteexterno
                            WHERE id=NEW.reemplaza_id AND sustituido
                                AND solicitud_id=NEW.solicitud_id AND tipo=NEW.tipo
                        )
                    )) THEN
                        RAISE EXCEPTION 'Correccion de comprobante incompatible'
                            USING ERRCODE='23514';
                    END IF;
                    IF NEW.tipo='FACTURA' AND EXISTS (
                        SELECT 1 FROM facturacion_comprobanteexterno
                        WHERE solicitud_id=NEW.solicitud_id AND tipo<>'FACTURA' AND NOT sustituido
                            AND (cuit_emisor<>NEW.cuit_emisor OR letra<>NEW.letra)
                    ) THEN
                        RAISE EXCEPTION 'Las notas vigentes deben coincidir con la factura'
                            USING ERRCODE='23514';
                    END IF;
                """,
            )
            + """
CREATE FUNCTION facturacion_exigir_sucesor_comprobante() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.sustituido AND NOT EXISTS (
        SELECT 1 FROM facturacion_comprobanteexterno WHERE reemplaza_id=NEW.id
    ) THEN
        RAISE EXCEPTION 'Falta sucesor de comprobante corregido' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END; $$;
CREATE CONSTRAINT TRIGGER facturacion_comprobante_sucesor AFTER UPDATE
ON facturacion_comprobanteexterno DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION facturacion_exigir_sucesor_comprobante();
"""
            + RESOLUCION_CON_RECTIFICACION.replace(
                "FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id",
                "FROM facturacion_comprobanteexterno WHERE solicitud_id=NEW.id AND NOT sustituido",
            ),
            reverse_sql="""
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM facturacion_comprobanteexterno WHERE reemplaza_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Hay correcciones de comprobantes: conservar historial';
    END IF;
END; $$;
DROP TRIGGER facturacion_comprobante_sucesor ON facturacion_comprobanteexterno;
DROP FUNCTION facturacion_exigir_sucesor_comprobante();
"""
            + GUARDA_COMPROBANTE.format(sustitucion="", factura_vigente="", sucesor="")
            + RESOLUCION_CON_RECTIFICACION,
        ),
    ]
