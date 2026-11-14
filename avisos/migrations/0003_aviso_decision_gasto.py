# Generated manually for avisos.Aviso decision_id (additive, sin backfill)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("avisos", "0002_intencioncorreo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aviso",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("nueva_solicitud_gasto", "Nueva solicitud de gasto"),
                    ("decision_solicitud_gasto", "Decisión sobre solicitud de gasto"),
                ],
                default="nueva_solicitud_gasto",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="aviso",
            name="decision_id",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name="aviso",
            name="unique_aviso_destinatario_tipo_solicitud",
        ),
        migrations.AddConstraint(
            model_name="aviso",
            constraint=models.UniqueConstraint(
                condition=models.Q(("decision_id__isnull", True)),
                fields=("destinatario", "tipo", "solicitud_id"),
                name="unique_aviso_destinatario_tipo_solicitud",
            ),
        ),
        migrations.AddConstraint(
            model_name="aviso",
            constraint=models.UniqueConstraint(
                condition=models.Q(("decision_id__isnull", False)),
                fields=("destinatario", "tipo", "decision_id"),
                name="unique_aviso_destinatario_tipo_decision",
            ),
        ),
        migrations.AddConstraint(
            model_name="aviso",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(decision_id__isnull=True, tipo="nueva_solicitud_gasto")
                    | models.Q(decision_id__isnull=False, tipo="decision_solicitud_gasto")
                    | ~models.Q(
                        ("tipo__in", ["nueva_solicitud_gasto", "decision_solicitud_gasto"])
                    )
                ),
                name="check_aviso_tipo_decision_coherente",
            ),
        ),
    ]
