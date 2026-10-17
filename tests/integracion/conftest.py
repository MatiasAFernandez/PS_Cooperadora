"""Datos sintéticos para contratos comunes; sin modificar el recorrido de Franco."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from facturacion.services import crear_solicitud_tecnica
from identidad.services import GROUP_CAPABILITIES, Actor
from tests.soporte_gastos import crear_gasto_sintetico


@pytest.fixture
def escenario_comun(db, settings, tmp_path):
    settings.DEMO_IDENTITY_ENABLED = True
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "privado"

    def usuario(nombre, grupos):
        user = get_user_model().objects.create_user(username=nombre, password="demo")
        for grupo in grupos:
            user.groups.add(Group.objects.get_or_create(name=grupo)[0])
        capacidades = frozenset().union(*(GROUP_CAPABILITIES[g] for g in grupos))
        return user, Actor(user.pk, capacidades)

    docs = ["demo_documentos_aporte", "demo_documentos_metadatos", "demo_documentos_descarga"]
    a, actor_a = usuario("a_comun", ["demo_solicitante", "demo_facturacion_solicitante", *docs])
    b, actor_b = usuario("b_comun", ["demo_solicitante", "demo_facturacion_solicitante", *docs])
    staff, actor_staff = usuario(
        "operadora_comun",
        ["demo_operadora", "demo_facturacion_operadora", "demo_gastos_pago", *docs],
    )
    factura = crear_solicitud_tecnica(actor=actor_b)
    # Forzar la colisión pública demuestra que los circuitos permanecen distintos.
    gasto = crear_gasto_sintetico(
        pk=factura.pk,
        concepto="Prueba",
        monto_estimado="1.00",
        unidad_requirente="Unidad ficticia",
        solicitante=a,
        estado="aceptada",
    )
    return SimpleNamespace(
        a=a,
        b=b,
        staff=staff,
        actor_a=actor_a,
        actor_b=actor_b,
        actor_staff=actor_staff,
        gasto=gasto,
        factura=factura,
        raiz=settings.DOCUMENT_STORAGE_ROOT,
    )
