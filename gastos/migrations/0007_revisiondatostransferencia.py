# Migración aditiva de datos operativos de transferencia (Issue #74 / SPEC-013).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gastos", "0006_integridad_solicitudgasto_tramite_base"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RevisionDatosTransferencia",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "numero_revision",
                    models.PositiveIntegerField(
                        help_text=(
                            "Número secuencial de la revisión dentro del gasto (inicial: 1)."
                        )
                    ),
                ),
                (
                    "titular_nombre",
                    models.CharField(
                        help_text=(
                            "Titular o beneficiario de la cuenta, tal como fue informado."
                        ),
                        max_length=200,
                    ),
                ),
                (
                    "identificacion",
                    models.CharField(
                        help_text=(
                            "Identificación informada del titular; no se valida contra un "
                            "padrón."
                        ),
                        max_length=100,
                    ),
                ),
                (
                    "cbu_alias",
                    models.CharField(
                        help_text=(
                            "CBU o alias informado como dato textual; no se valida contra "
                            "un padrón bancario."
                        ),
                        max_length=128,
                    ),
                ),
                (
                    "correo_comprobante",
                    models.CharField(
                        help_text=(
                            "Correo informado para remitir el comprobante; no se envía "
                            "automáticamente."
                        ),
                        max_length=254,
                    ),
                ),
                (
                    "centro_costo",
                    models.CharField(
                        help_text=(
                            "Centro de costo informado; no se confunde con la unidad "
                            "requirente."
                        ),
                        max_length=100,
                    ),
                ),
                (
                    "fecha_hora",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text=(
                            "Fecha y hora fijadas por el servidor al registrar la revisión."
                        ),
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        help_text="Actor del servidor que registró la revisión.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revisiones_datos_transferencia_gasto",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "solicitud",
                    models.ForeignKey(
                        help_text=(
                            "Gasto al que pertenece la revisión; el historial no se "
                            "reasigna."
                        ),
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revisiones_datos_transferencia",
                        to="gastos.solicitudgasto",
                    ),
                ),
            ],
            options={
                "verbose_name": "Revisión de datos de transferencia",
                "verbose_name_plural": "Revisiones de datos de transferencia",
                "ordering": ["solicitud", "numero_revision"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("solicitud", "numero_revision"),
                        name="uq_revision_datos_transferencia_numero",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("numero_revision__gt", 0)),
                        name="revision_datos_transferencia_numero_positivo",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION gastos_proteger_revision_datos_transferencia()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP <> 'INSERT' THEN
                    RAISE EXCEPTION
                        'La revisión de datos de transferencia es inmutable.'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_revision_datos_transferencia_inmutable
                ON gastos_revisiondatostransferencia;

            CREATE TRIGGER trg_revision_datos_transferencia_inmutable
            BEFORE INSERT OR UPDATE OR DELETE ON gastos_revisiondatostransferencia
            FOR EACH ROW
            EXECUTE FUNCTION gastos_proteger_revision_datos_transferencia();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_revision_datos_transferencia_inmutable
                ON gastos_revisiondatostransferencia;
            DROP FUNCTION IF EXISTS gastos_proteger_revision_datos_transferencia();
            """,
        ),
    ]
