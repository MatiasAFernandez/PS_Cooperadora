"""Protege la pertenencia del respaldo y la reversión que perdería negocio."""

from django.db import migrations


def impedir_perdida(apps, schema_editor):
    from django.db.migrations.exceptions import IrreversibleError
    solicitud = apps.get_model("facturacion", "SolicitudFacturacion")
    if solicitud.objects.using(schema_editor.connection.alias).exclude(
        estado="BORRADOR_TECNICO"
    ).exists():
        raise IrreversibleError("No revertir negocio; preparar migración correctiva.")


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0004_solicitudfacturacion_ck_fac_datos_operativos_and_more"),
    ]
    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION facturacion_validar_respaldo() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.documento_comprobante_inicial_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM documentos_documento
                        WHERE id = NEW.documento_comprobante_inicial_id
                        AND tramite_base_id = NEW.tramite_base_id
                        AND tipo = 'COMPROBANTE_COBRO'
                    ) THEN
                        RAISE EXCEPTION 'Respaldo incompatible' USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END; $$;
                CREATE TRIGGER facturacion_respaldo
                BEFORE INSERT OR UPDATE ON facturacion_solicitudfacturacion
                FOR EACH ROW EXECUTE FUNCTION facturacion_validar_respaldo();
            """,
            reverse_sql="""
                DROP TRIGGER facturacion_respaldo ON facturacion_solicitudfacturacion;
                DROP FUNCTION facturacion_validar_respaldo();
            """,
        ),
        migrations.RunPython(migrations.RunPython.noop, impedir_perdida),
    ]
