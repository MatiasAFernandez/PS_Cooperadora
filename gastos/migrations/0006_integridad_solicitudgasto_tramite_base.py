"""Hace obligatorio el vínculo y lo protege también contra SQL directo."""

from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError

CIRCUITO_GASTO = "GASTO"

FUNCION_TRIGGER = """
CREATE OR REPLACE FUNCTION gastos_validar_tramite_base() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    base comunes_tramitebase%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.id IS DISTINCT FROM OLD.id
            OR NEW.tramite_base_id IS DISTINCT FROM OLD.tramite_base_id
            OR NEW.solicitante_id IS DISTINCT FROM OLD.solicitante_id THEN
            RAISE EXCEPTION
                'No se permite reasignar id, tramite_base ni solicitante de una SolicitudGasto.'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NEW.tramite_base_id IS NULL THEN
        RAISE EXCEPTION
            'La solicitud de gasto requiere una cabecera de trámite.'
            USING ERRCODE = '23502';
    END IF;
    SELECT * INTO base FROM comunes_tramitebase WHERE id = NEW.tramite_base_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'La cabecera de trámite de la solicitud no existe.'
            USING ERRCODE = '23503';
    END IF;
    IF base.circuito IS DISTINCT FROM 'GASTO'
        OR base.numero_publico IS DISTINCT FROM NEW.id
        OR base.solicitante_actor_id IS DISTINCT FROM NEW.solicitante_id::text THEN
        RAISE EXCEPTION
            'La cabecera de trámite es incompatible con la solicitud de gasto.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
"""


def instalar_trigger(apps, schema_editor) -> None:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(FUNCION_TRIGGER)
        cursor.execute(
            "DROP TRIGGER IF EXISTS gastos_validar_tramite_base ON gastos_solicitudgasto"
        )
        cursor.execute(
            "CREATE TRIGGER gastos_validar_tramite_base "
            "BEFORE INSERT OR UPDATE ON gastos_solicitudgasto "
            "FOR EACH ROW EXECUTE FUNCTION gastos_validar_tramite_base()"
        )


def _validar_reversa(apps, schema_editor) -> None:
    alias = schema_editor.connection.alias
    Gasto = apps.get_model("gastos", "SolicitudGasto")
    Base = apps.get_model("comunes", "TramiteBase")
    Documento = apps.get_model("documentos", "Documento")

    for gasto in Gasto.objects.using(alias).order_by("pk"):
        if gasto.tramite_base_id is None:
            raise IrreversibleError(
                f"No se puede revertir: el gasto #{gasto.pk} no tiene cabecera."
            )
        base = Base.objects.using(alias).filter(pk=gasto.tramite_base_id).first()
        if (
            base is None
            or base.circuito != CIRCUITO_GASTO
            or base.numero_publico != gasto.pk
            or base.solicitante_actor_id != str(gasto.solicitante_id)
        ):
            raise IrreversibleError(
                f"No se puede revertir: el gasto #{gasto.pk} tiene una cabecera incompatible."
            )
        if (
            Documento.objects.using(alias)
            .filter(solicitud_gasto_id=gasto.pk)
            .exclude(tramite_base_id=base.pk)
            .exists()
        ):
            raise IrreversibleError(
                f"No se puede revertir: los documentos del gasto #{gasto.pk} "
                "apuntan a otra cabecera."
            )


def desinstalar_trigger(apps, schema_editor) -> None:
    _validar_reversa(apps, schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP TRIGGER IF EXISTS gastos_validar_tramite_base ON gastos_solicitudgasto"
        )
        cursor.execute("DROP FUNCTION IF EXISTS gastos_validar_tramite_base()")


class Migration(migrations.Migration):
    dependencies = [
        ("gastos", "0005_backfill_solicitudgasto_tramite_base"),
    ]

    operations = [
        migrations.AlterField(
            model_name="solicitudgasto",
            name="tramite_base",
            field=models.OneToOneField(
                editable=False,
                help_text=(
                    "Cabecera común protegida; número y titular coinciden con la solicitud."
                ),
                on_delete=models.PROTECT,
                related_name="solicitud_gasto",
                to="comunes.tramitebase",
            ),
        ),
        migrations.RunPython(instalar_trigger, desinstalar_trigger),
    ]
