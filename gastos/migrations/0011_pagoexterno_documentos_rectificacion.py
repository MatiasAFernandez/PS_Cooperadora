"""Comprobante bancario, constancia ATP, versión efectiva e historial de rectificaciones.

La migración conserva los pagos históricos sin inventar PDFs: crea una
representación original marcada como legado y deja nulos los vínculos
documentales que no existían.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def crear_representaciones_originales(apps, schema_editor):
    PagoExterno = apps.get_model("gastos", "PagoExterno")
    Original = apps.get_model("gastos", "PagoExternoOriginal")
    for pago in PagoExterno.objects.all().iterator():
        Original.objects.get_or_create(
            pago_id=pago.pk,
            defaults={
                "importe": pago.importe,
                "monto_bruto": pago.monto_bruto,
                "monto_retencion_atp": pago.monto_retencion_atp,
                "moneda": pago.moneda,
                "fecha_pago": pago.fecha_pago,
                "referencia_externa": pago.referencia_externa,
                "referencia_documental": pago.referencia_documental,
                "referencia_atp": pago.referencia_atp,
                "comprobante_bancario_id": pago.comprobante_bancario_id,
                "constancia_atp_id": pago.constancia_atp_id,
                "comprobante_sha256": "",
                "constancia_sha256": "",
                "es_legado": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0010_alter_documento_procedencia_alter_documento_tipo"),
        ("gastos", "0010_pagoexterno_monto_bruto_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="pagoexterno",
            name="referencia_externa",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Número de operación o referencia bancaria informada. Puede quedar "
                    "vacío: no se inventa un número."
                ),
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="pagoexterno",
            name="comprobante_bancario",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Documento PDF del comprobante bancario. Nulo sólo en registros "
                    "históricos anteriores a la regla de PDF obligatorio."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pagos_como_comprobante_bancario",
                to="documentos.documento",
            ),
        ),
        migrations.AddField(
            model_name="pagoexterno",
            name="constancia_atp",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Constancia ATP vigente del pago. Puede incorporarse después del "
                    "registro; nunca se fabrica ni se infiere."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pagos_como_constancia_atp",
                to="documentos.documento",
            ),
        ),
        migrations.AddField(
            model_name="pagoexterno",
            name="version",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Versión efectiva del pago. Cada rectificación o aporte posterior la "
                    "incrementa."
                ),
            ),
        ),
        migrations.CreateModel(
            name="PagoExternoOriginal",
            fields=[
                (
                    "pago",
                    models.OneToOneField(
                        help_text="Pago cuyo alta original se conserva.",
                        on_delete=django.db.models.deletion.PROTECT,
                        primary_key=True,
                        related_name="original",
                        serialize=False,
                        to="gastos.pagoexterno",
                    ),
                ),
                ("importe", models.DecimalField(decimal_places=2, max_digits=12)),
                ("monto_bruto", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "monto_retencion_atp",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                ("moneda", models.CharField(default="ARS", max_length=3)),
                ("fecha_pago", models.DateField()),
                (
                    "referencia_externa",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("referencia_documental", models.CharField(max_length=255)),
                (
                    "referencia_atp",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                (
                    "comprobante_sha256",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "constancia_sha256",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "es_legado",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Alta anterior a la regla de comprobante PDF obligatorio."
                        ),
                    ),
                ),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                (
                    "comprobante_bancario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pagos_originales_como_comprobante",
                        to="documentos.documento",
                    ),
                ),
                (
                    "constancia_atp",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pagos_originales_como_constancia",
                        to="documentos.documento",
                    ),
                ),
            ],
            options={
                "verbose_name": "Representación original del pago",
                "verbose_name_plural": "Representaciones originales de pagos",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            importe=models.F("monto_bruto")
                            - models.F("monto_retencion_atp")
                        ),
                        name="pago_original_identidad_neto_atp",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(moneda="ARS"),
                        name="pago_original_moneda_ars",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PagoExternoCambio",
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
                    "numero_version",
                    models.PositiveIntegerField(
                        help_text="Versión efectiva resultante después del cambio."
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("rectificacion", "Rectificación de datos"),
                            (
                                "comprobante_reemplazado",
                                "Comprobante bancario reemplazado",
                            ),
                            (
                                "comprobante_incorporado",
                                "Comprobante bancario incorporado",
                            ),
                            ("atp_incorporada", "Constancia ATP incorporada"),
                            ("atp_retirada", "Constancia ATP desvinculada"),
                        ],
                        max_length=40,
                    ),
                ),
                ("motivo", models.TextField(max_length=500)),
                ("fecha_hora", models.DateTimeField(auto_now_add=True)),
                ("datos_antes", models.JSONField()),
                ("datos_despues", models.JSONField()),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cambios_pago_externo",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "documento_anterior",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cambios_pago_documento_anterior",
                        to="documentos.documento",
                    ),
                ),
                (
                    "documento_nuevo",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cambios_pago_documento_nuevo",
                        to="documentos.documento",
                    ),
                ),
                (
                    "pago",
                    models.ForeignKey(
                        help_text="Pago efectivo al que se aplicó el cambio.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cambios",
                        to="gastos.pagoexterno",
                    ),
                ),
            ],
            options={
                "verbose_name": "Cambio de pago externo",
                "verbose_name_plural": "Cambios de pagos externos",
                "ordering": ["pago_id", "numero_version"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("pago", "numero_version"),
                        name="uq_pago_externo_cambio_version",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("numero_version__gt", 0)),
                        name="pago_externo_cambio_version_positiva",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("motivo", ""), _negated=True),
                        name="pago_externo_cambio_motivo_obligatorio",
                    ),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="pagoexterno",
            constraint=models.CheckConstraint(
                condition=models.Q(("version__gt", 0)),
                name="pago_externo_version_positiva",
            ),
        ),
        migrations.RunPython(
            crear_representaciones_originales,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION prevent_pago_externo_original_change()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'La representación original del pago es inmutable.'
                    USING ERRCODE = '23514';
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS
                trg_pago_externo_original_inmutable ON gastos_pagoexternooriginal;
            CREATE TRIGGER trg_pago_externo_original_inmutable
            BEFORE UPDATE OR DELETE ON gastos_pagoexternooriginal
            FOR EACH ROW
            EXECUTE FUNCTION prevent_pago_externo_original_change();

            CREATE OR REPLACE FUNCTION prevent_pago_externo_cambio_change()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'El historial de cambios del pago es append-only.'
                    USING ERRCODE = '23514';
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS
                trg_pago_externo_cambio_inmutable ON gastos_pagoexternocambio;
            CREATE TRIGGER trg_pago_externo_cambio_inmutable
            BEFORE UPDATE OR DELETE ON gastos_pagoexternocambio
            FOR EACH ROW
            EXECUTE FUNCTION prevent_pago_externo_cambio_change();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS
                trg_pago_externo_original_inmutable ON gastos_pagoexternooriginal;
            DROP FUNCTION IF EXISTS prevent_pago_externo_original_change();
            DROP TRIGGER IF EXISTS
                trg_pago_externo_cambio_inmutable ON gastos_pagoexternocambio;
            DROP FUNCTION IF EXISTS prevent_pago_externo_cambio_change();
            """,
        ),
    ]
