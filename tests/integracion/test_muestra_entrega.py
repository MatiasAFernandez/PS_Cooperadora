"""Reproducibilidad y límites del comando sintético de entrega."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from comunes.models import TramiteBase
from documentos.models import Documento
from facturacion.models import SolicitudFacturacion
from gastos.models import PagoExterno

pytestmark = pytest.mark.django_db(transaction=True)


def test_muestra_verifica_hechos_y_detecta_bytes_alterados(settings, tmp_path):
    settings.DEMO_IDENTITY_ENABLED = True
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "archivos"
    manifiesto = tmp_path / "manifiesto.json"
    call_command("muestra_entrega", "crear", manifiesto=manifiesto)
    assert TramiteBase.objects.count() == 2
    assert Documento.objects.count() == 4
    assert SolicitudFacturacion.objects.get().estado == "CERRADA"
    assert PagoExterno.objects.count() == 1
    call_command("muestra_entrega", "verificar", manifiesto=manifiesto)
    documento = Documento.objects.first()
    (settings.DOCUMENT_STORAGE_ROOT / documento.archivo).write_bytes(b"bytes alterados")
    with pytest.raises(CommandError, match="difiere"):
        call_command("muestra_entrega", "verificar", manifiesto=manifiesto)
    with pytest.raises(CommandError, match="vacía"):
        call_command("muestra_entrega", "crear", manifiesto=manifiesto)
    assert TramiteBase.objects.count() == 2 and Documento.objects.count() == 4


def test_muestra_no_crea_en_demo_deshabilitada(settings, tmp_path):
    settings.DEMO_IDENTITY_ENABLED = False
    with pytest.raises(CommandError, match="demo"):
        call_command("muestra_entrega", "crear", manifiesto=tmp_path / "manifiesto.json")
    assert not get_user_model().objects.exists()


def test_muestra_no_agrega_datos_a_base_con_usuarios(settings, tmp_path):
    settings.DEMO_IDENTITY_ENABLED = True
    get_user_model().objects.create_user(username="cuenta_previa")
    with pytest.raises(CommandError, match="vacía"):
        call_command("muestra_entrega", "crear", manifiesto=tmp_path / "manifiesto.json")
    assert get_user_model().objects.count() == 1
    assert not TramiteBase.objects.exists()
