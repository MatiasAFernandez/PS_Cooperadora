"""Cuentas y solicitudes enteramente sintéticas del recorrido #21/#23."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from identidad.services import GROUP_CAPABILITIES, Actor


@pytest.fixture
def escenario(settings, tmp_path):
    settings.DEMO_IDENTITY_ENABLED = True
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "privado"
    call_command("preparar_identidad_demo", facturacion=True, verbosity=0)
    usuarios, actores = {}, {}
    for sufijo in ("a", "b", "o", "l"):
        user = get_user_model().objects.get(username=f"demo_{sufijo}")
        capacidades = frozenset().union(
            *(GROUP_CAPABILITIES[g] for g in user.groups.values_list("name", flat=True))
        )
        usuarios[sufijo] = user
        actores[sufijo] = Actor(user.pk, capacidades, user.email)
    return SimpleNamespace(
        usuarios=usuarios,
        actores=actores,
        raiz=settings.DOCUMENT_STORAGE_ROOT,
    )


@pytest.fixture
def datos():
    return dict(
        presento_comprobante_pago=False,
        nombre_solicitante="Solicitante ficticio",
        cuit_receptor="30712345671",
        nombre_receptor="Receptor ficticio",
        condicion_iva="IVA_RESPONSABLE_INSCRIPTO",
        email_envio_factura="destino@example.invalid",
        detalle_factura="Servicio ficticio",
        importe_factura="100.25",
        producto_servicio="ANALISIS",
        centro_costo="GISTAQ",
        modalidad_cobro="CUENTA_CORRIENTE",
        observaciones="Observaciones de prueba",
    )
