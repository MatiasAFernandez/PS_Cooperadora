from django.db import migrations


def preparar(apps, schema_editor):
    Configuracion = apps.get_model("gestion", "ConfiguracionFormulario")
    for circuito in ("GASTO", "FACTURACION"):
        Configuracion.objects.get_or_create(circuito=circuito)


class Migration(migrations.Migration):
    dependencies = [("gestion", "0002_historial_inmutable")]
    operations = [migrations.RunPython(preparar, migrations.RunPython.noop)]
