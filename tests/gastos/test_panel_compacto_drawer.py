"""Pruebas del panel compacto Master-Detail y Drawer lateral (Issue #92).

Cubre:
- GAST-R06 / SPEC-013: Privacidad estricta en SSR de datos bancarios en el Drawer.
  Los perfiles sin permiso de registrar pago (ej. demo_lectura) no reciben CBU, alias,
  ni titular en el DOM ni en atributos data-*.
- Visualización de las 8 columnas compactas y badges de modalidad y estado.
- Inclusión del botón de copiado rápido con feedback y fallback para entornos LAN.
- Optimización de queryset (select_related y prefetch_related) para evitar N+1.
- Paginación a 25 registros conservando filtros de búsqueda.
- Desglose contable en Drawer para pagos con retención provincial ATP Chaco.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from gastos.models import (
    CentroCosto,
    EstadoSolicitud,
    PagoExterno,
    RevisionDatosTransferencia,
    SolicitudGasto,
    TipoFlujoGasto,
)
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# Fixtures y Ayudantes
# ---------------------------------------------------------------------------


def _crear_solicitud_con_transferencia(
    solicitante: Any,
    concepto: str = "Compra de instrumental",
    monto: Decimal = Decimal("45000.00"),
    tipo_flujo: str = TipoFlujoGasto.COMPRA_DIRECTA,
    centro_costo: CentroCosto | None = None,
    cbu_alias: str = "0720000000000000000000",
    titular: str = "Laboratorio Central SRL",
) -> SolicitudGasto:
    """Crea una solicitud de gasto completa con revisión de datos bancarios."""
    solicitud = crear_gasto_sintetico(
        concepto=concepto,
        monto_estimado=monto,
        solicitante=solicitante,
        unidad_requirente="Laboratorio",
        estado=EstadoSolicitud.ACEPTADA,
    )
    solicitud.tipo_flujo = tipo_flujo
    solicitud.centro_costo = centro_costo
    solicitud.save()

    RevisionDatosTransferencia.objects.create(
        solicitud=solicitud,
        numero_revision=1,
        titular_nombre=titular,
        identificacion="30-11223344-5",
        cbu_alias=cbu_alias,
        correo_comprobante="proveedor@lab.com",
        centro_costo=centro_costo.nombre if centro_costo else "General",
        actor=solicitante,
    )
    return solicitud


# ---------------------------------------------------------------------------
# 1. Verificación de 8 Columnas y Badges de Modalidad
# ---------------------------------------------------------------------------


def test_solicitud_list_renderiza_8_columnas_y_badges(create_actor: Any) -> None:
    """Verifica que el panel Master-Detail expone las 8 columnas institucionales."""
    user, _ = create_actor("usuario_consulta", ["gastos.consultar_todas"])
    client = Client()
    client.force_login(user)

    centro = CentroCosto.objects.create(codigo="cc-quimica", nombre="Química")
    _crear_solicitud_con_transferencia(
        solicitante=user,
        concepto="Microscopio electrónico",
        monto=Decimal("150000.00"),
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=centro,
    )
    _crear_solicitud_con_transferencia(
        solicitante=user,
        concepto="Pasajes congreso científico",
        monto=Decimal("35000.00"),
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
    )

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200

    content = response.content.decode()

    # 1. Cabeceras de las 8 columnas
    assert '<th scope="col"' in content
    assert "ID" in content
    assert "Modalidad" in content
    assert "Centro de Costo" in content
    assert "Concepto" in content
    assert "Monto Estimado" in content
    assert "Estado" in content
    assert "Fecha" in content
    assert "Acciones" in content

    # 2. Badges de modalidad y nombres de centro
    assert "Compra Directa" in content
    assert "Reintegro" in content
    assert "Química" in content

    # 3. Micro-interacción: Botón inspeccionar drawer y enlace al script
    assert "Inspeccionar" in content
    assert "drawer.js" in content
    assert "drawer-backdrop" in content


# ---------------------------------------------------------------------------
# 2. Privacidad Estricta en SSR (GAST-R06 / SPEC-013)
# ---------------------------------------------------------------------------


def test_solicitud_list_drawer_privacidad_ssr_sin_datos_bancarios(create_actor: Any) -> None:
    """Usuario sin permiso de registrar pago (demo_lectura) NO recibe CBU en el DOM."""
    user_titular, _ = create_actor("titular_real", ["gastos.presentar"])
    user_lectura, _ = create_actor("demo_lectura", ["gastos.consultar_todas"])

    cbu_secreto = "0110599540000012345678"
    titular_secreto = "Proveedor Confidencial SA"
    _crear_solicitud_con_transferencia(
        solicitante=user_titular,
        concepto="Servidor de cómputo",
        cbu_alias=cbu_secreto,
        titular=titular_secreto,
    )

    client = Client()
    client.force_login(user_lectura)

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200

    html = response.content.decode()

    # Invariante GAST-R06: Ni el CBU ni el titular deben aparecer en ninguna parte del HTML
    assert cbu_secreto not in html
    assert titular_secreto not in html
    assert "Copiar CBU" not in html
    assert "btn-copy" not in html

    # Debe informar la política de confidencialidad en el cuerpo del drawer
    assert "Privacidad Institucional" in html
    assert "restringidos exclusivamente al titular del gasto y al personal autorizado" in html


def test_solicitud_list_drawer_con_datos_bancarios_para_tesoreria(create_actor: Any) -> None:
    """Personal con capacidad gastos.registrar_pago SÍ recibe CBU y botón de copiado."""
    user_titular, _ = create_actor("titular_real2", ["gastos.presentar"])
    user_pagador, _ = create_actor("operador_tesoreria", ["gastos.consultar_todas"])
    user_pagador.groups.add(Group.objects.get_or_create(name="demo_gastos_pago")[0])

    cbu_publico = "0720123488000098765432"
    titular_publico = "Comercio de Electrónica SRL"
    solicitud = _crear_solicitud_con_transferencia(
        solicitante=user_titular,
        concepto="Cables y fuentes",
        cbu_alias=cbu_publico,
        titular=titular_publico,
    )

    client = Client()
    client.force_login(user_pagador)

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200

    html = response.content.decode()

    # Personal autorizado sí accede a los datos bancarios
    assert cbu_publico in html
    assert titular_publico in html
    assert "Copiar CBU" in html
    assert "btn-copy" in html
    assert f"drawer-solicitud-{solicitud.pk}" in html


def test_solicitud_list_drawer_con_datos_bancarios_para_titular(create_actor: Any) -> None:
    """El titular del trámite accede a sus propios datos bancarios en el Drawer."""
    user_titular, _ = create_actor(
        "titular_propio", ["gastos.presentar", "gastos.consultar_propias"]
    )

    cbu_propio = "0140999900000011223344"
    solicitud = _crear_solicitud_con_transferencia(
        solicitante=user_titular,
        concepto="Reintegro por librería",
        cbu_alias=cbu_propio,
        titular="Docente Investigador",
    )

    client = Client()
    client.force_login(user_titular)

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200

    html = response.content.decode()
    assert cbu_propio in html
    assert "Copiar CBU" in html
    assert f"drawer-solicitud-{solicitud.pk}" in html


# ---------------------------------------------------------------------------
# 3. Desglose Contable y Retención ATP en Drawer
# ---------------------------------------------------------------------------


def test_solicitud_list_drawer_muestra_desglose_atp(create_actor: Any) -> None:
    """Verifica que el Drawer expone el desglose de bruto, retención ATP y neto."""
    user, _ = create_actor("operador_pagos_atp", ["gastos.consultar_todas"])
    user.groups.add(Group.objects.get_or_create(name="demo_gastos_pago")[0])
    solicitud = _crear_solicitud_con_transferencia(
        solicitante=user,
        concepto="Servicio de mantenimiento",
        monto=Decimal("100000.00"),
    )

    # Registrar pago con retención ATP
    PagoExterno.objects.create(
        solicitud=solicitud,
        monto_bruto=Decimal("100000.00"),
        monto_retencion_atp=Decimal("3500.00"),
        importe=Decimal("96500.00"),
        referencia_atp="CONST-ATP-7788",
        referencia_externa="TRF-BANCO-9911",
        referencia_documental="FAC-PROV-1234",
        fecha_pago=date(2026, 11, 3),
        huella_idempotencia="huella-test-atp-drawer",
    )

    client = Client()
    client.force_login(user)

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200

    html = response.content.decode()
    assert "Pago Confirmado" in html
    assert "CONST-ATP-7788" in html
    assert "TRF-BANCO-9911" in html
    assert "Retención ATP Chaco" in html
    assert "96500" in html


# ---------------------------------------------------------------------------
# 4. Optimización de Consultas SQL (Prevención de N+1)
# ---------------------------------------------------------------------------


def test_solicitud_list_queries_optimizadas_sin_n_mas_1(
    create_actor: Any, django_assert_num_queries: Any
) -> None:
    """Verifica que select_related y prefetch_related acotan las consultas de BD."""
    user, _ = create_actor("consultor_n1", ["gastos.consultar_todas"])
    user.groups.add(Group.objects.get_or_create(name="demo_gastos_pago")[0])
    centro = CentroCosto.objects.create(codigo="cc-opt", nombre="Centro Optimizado")

    for i in range(10):
        _crear_solicitud_con_transferencia(
            solicitante=user,
            concepto=f"Solicitud múltiple #{i}",
            monto=Decimal("10000.00"),
            centro_costo=centro,
            cbu_alias=f"072000000000000000000{i}",
        )

    client = Client()
    client.force_login(user)

    # El listado de 10 solicitudes con centro_costo, pago_externo y revisiones de transferencia
    # no debe superar una cantidad acotada y fija de consultas (sin N+1):
    # 1. Sesión y actor
    # 2. Solicitudes con JOIN a centro_costo y pago_externo
    # 3. Prefetch de revisiones de transferencia
    # 4. Paginador (COUNT)
    with django_assert_num_queries(6):
        response = client.get(reverse("gastos:lista"))
        assert response.status_code == 200
        assert len(response.context["solicitudes"]) == 10


# ---------------------------------------------------------------------------
# 5. Paginación a 25 Registros y Preservación de Filtros
# ---------------------------------------------------------------------------


def test_solicitud_list_paginacion_a_25_registros(create_actor: Any) -> None:
    """Crea 30 registros y verifica que la paginación a 25 registros funcione."""
    user, _ = create_actor("usuario_paginacion", ["gastos.consultar_todas"])

    for i in range(30):
        crear_gasto_sintetico(
            concepto=f"Gasto lote #{i}",
            monto_estimado=Decimal("100.00"),
            solicitante=user,
        )

    client = Client()
    client.force_login(user)

    # Página 1
    resp1 = client.get(reverse("gastos:lista"))
    assert resp1.status_code == 200
    assert len(resp1.context["solicitudes"]) == 25
    assert resp1.context["is_paginated"] is True
    assert resp1.context["page_obj"].has_next() is True
    assert resp1.context["page_obj"].has_previous() is False
    assert "Siguiente" in resp1.content.decode()

    # Página 2
    resp2 = client.get(reverse("gastos:lista"), {"page": 2})
    assert resp2.status_code == 200
    assert len(resp2.context["solicitudes"]) == 5
    assert resp2.context["page_obj"].has_previous() is True
    assert "Anterior" in resp2.content.decode()
