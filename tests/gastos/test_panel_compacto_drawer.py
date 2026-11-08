"""Pruebas de la bandeja de gastos y su vista rápida (Issue #92)."""

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
# 1. Tabla compacta
# ---------------------------------------------------------------------------


def test_solicitud_list_renderiza_cuatro_columnas(create_actor: Any) -> None:
    """El lector ve una tabla compacta y accesos directos al detalle."""
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

    assert content.count('<th scope="col">') == 4
    for label in ("Solicitud", "Importe estimado", "Estado", "Acción"):
        assert f'<th scope="col">{label}</th>' in content
    assert "$ 150.000,00" in content
    assert "Microscopio electrónico" in content
    assert "Ver detalle" in content
    assert "data-vista-rapida" not in content
    assert "Química" not in content


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

    assert "data-vista-rapida" not in html


def test_solicitud_list_vista_rapida_sin_datos_bancarios_para_tesoreria(create_actor: Any) -> None:
    """El perfil de pago recibe el resumen operativo sin datos bancarios."""
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

    assert cbu_publico not in html
    assert titular_publico not in html
    assert "Copiar CBU" not in html
    assert f'data-vista-rapida="resumen-{solicitud.pk}"' in html


def test_solicitud_list_sin_datos_bancarios_para_titular(create_actor: Any) -> None:
    """El titular tiene un enlace al detalle y no recibe datos bancarios en la lista."""
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
    assert cbu_propio not in html
    assert "Copiar CBU" not in html
    assert "data-vista-rapida" not in html
    assert reverse("gastos:detalle", kwargs={"pk": solicitud.pk}) in html


# ---------------------------------------------------------------------------
# 2. Atención operativa y filtros de pendientes
# ---------------------------------------------------------------------------


def test_total_atencion_cuenta_antes_de_filtros(create_actor: Any) -> None:
    """El contador refleja la atención visible y no la página ni los filtros GET."""
    operador, _ = create_actor("operador_total_atencion", ["gastos.decidir"])
    solicitante, _ = create_actor("solicitante_total_atencion", ["gastos.presentar"])
    ajena = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Presentada ajena",
        estado=EstadoSolicitud.PRESENTADA,
    )
    crear_gasto_sintetico(
        solicitante=operador,
        concepto="Presentada propia",
        estado=EstadoSolicitud.PRESENTADA,
    )
    aceptada = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada sin decisión",
        estado=EstadoSolicitud.ACEPTADA,
    )

    client = Client()
    client.force_login(operador)

    response = client.get(reverse("gastos:lista"))
    assert response.context["total_atencion"] == 1
    assert ajena in list(response.context["solicitudes"])

    filtrada = client.get(reverse("gastos:lista"), {"estado": "aceptada"})
    assert filtrada.context["total_atencion"] == 1
    assert list(filtrada.context["solicitudes"]) == [aceptada]


def test_total_atencion_no_agrega_consultas_por_fila(
    create_actor: Any, django_assert_num_queries: Any
) -> None:
    """El conteo de atención es una consulta fija, independiente de las filas."""
    operador, _ = create_actor("operador_atencion_queries", ["gastos.decidir"])
    solicitante, _ = create_actor("solicitante_atencion_queries", ["gastos.presentar"])
    for indice in range(12):
        crear_gasto_sintetico(
            solicitante=solicitante,
            concepto=f"Pendiente de decisión {indice}",
            estado=EstadoSolicitud.PRESENTADA,
        )

    client = Client()
    client.force_login(operador)

    with django_assert_num_queries(6):
        response = client.get(reverse("gastos:lista"))
    assert response.context["total_atencion"] == 12
    assert len(response.context["solicitudes"]) == 12


def test_filtro_pendiente_decision_y_opciones_ocultas(create_actor: Any) -> None:
    """Sólo se ofrecen los pendientes que el actor puede atender."""
    operador, _ = create_actor("operador_pendiente", ["gastos.decidir"])
    solicitante, _ = create_actor("solicitante_pendiente", ["gastos.presentar"])
    ajena = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Pendiente de decisión",
        estado=EstadoSolicitud.PRESENTADA,
    )
    crear_gasto_sintetico(
        solicitante=operador,
        concepto="Propia presentada",
        estado=EstadoSolicitud.PRESENTADA,
    )
    crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada",
        estado=EstadoSolicitud.ACEPTADA,
    )

    client = Client()
    client.force_login(operador)

    response = client.get(reverse("gastos:lista"))
    html = response.content.decode()
    assert '<option value="decision">Pendiente de decisión</option>' in html
    assert '<option value="pago">' not in html
    assert '<option value="atp">' not in html
    assert '<option value="deuda">' not in html

    filtrada = client.get(reverse("gastos:lista"), {"pendiente": "decision"})
    assert list(filtrada.context["solicitudes"]) == [ajena]

    rechazada = client.get(reverse("gastos:lista"), {"pendiente": "pago"})
    assert list(rechazada.context["solicitudes"]) == []
    assert "pendiente" in rechazada.context["filtro_form"].errors


def test_filtro_pendiente_pago_y_atp_segun_capacidades(create_actor: Any) -> None:
    """Tesorería ve y usa los pendientes de pago y constancia ATP."""
    pagador, _ = create_actor("operador_pago_pendiente", ["gastos.consultar_todas"])
    for grupo in ("demo_gastos_pago", "demo_documentos_aporte", "demo_documentos_metadatos"):
        pagador.groups.add(Group.objects.get_or_create(name=grupo)[0])
    solicitante, _ = create_actor("solicitante_pago_pendiente", ["gastos.presentar"])

    sin_pago = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada sin pago",
        estado=EstadoSolicitud.ACEPTADA,
        monto_estimado=Decimal("100.00"),
    )
    con_atp = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada con ATP pendiente",
        estado=EstadoSolicitud.ACEPTADA,
        monto_estimado=Decimal("100.00"),
    )
    PagoExterno.objects.create(
        solicitud=con_atp,
        monto_bruto=Decimal("100.00"),
        monto_retencion_atp=Decimal("3.50"),
        importe=Decimal("96.50"),
        referencia_documental="FAC-PENDIENTE-ATP",
        fecha_pago=date(2026, 11, 3),
        huella_idempotencia="huella-pendiente-atp-filtro",
    )

    client = Client()
    client.force_login(pagador)

    response = client.get(reverse("gastos:lista"))
    html = response.content.decode()
    assert '<option value="pago">Sin pago registrado</option>' in html
    assert '<option value="atp">Constancia ATP pendiente</option>' in html
    assert '<option value="decision">' not in html
    assert '<option value="deuda">' not in html
    assert response.context["total_atencion"] == 2

    assert list(
        client.get(reverse("gastos:lista"), {"pendiente": "pago"}).context["solicitudes"]
    ) == [sin_pago]
    assert list(
        client.get(reverse("gastos:lista"), {"pendiente": "atp"}).context["solicitudes"]
    ) == [con_atp]


def test_filtro_deuda_propia_visible_para_quien_presenta(create_actor: Any) -> None:
    """El solicitante puede filtrar su propia deuda sin ver deuda ajena."""
    solicitante, _ = create_actor("solicitante_deuda", ["gastos.presentar"])
    solicitud = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Compra directa propia",
        estado=EstadoSolicitud.ACEPTADA,
        monto_estimado=Decimal("100.00"),
    )
    PagoExterno.objects.create(
        solicitud=solicitud,
        monto_bruto=Decimal("100.00"),
        importe=Decimal("100.00"),
        referencia_documental="FAC-DEUDA-PROPIA",
        fecha_pago=date(2020, 1, 1),
        huella_idempotencia="huella-deuda-propia-filtro",
    )

    client = Client()
    client.force_login(solicitante)

    response = client.get(reverse("gastos:lista"))
    assert '<option value="deuda">Falta factura definitiva</option>' in response.content.decode()
    filtrada = client.get(reverse("gastos:lista"), {"pendiente": "deuda"})
    assert list(filtrada.context["solicitudes"]) == [solicitud]


# ---------------------------------------------------------------------------
# 3. Privacidad de referencias del pago
# ---------------------------------------------------------------------------


def test_solicitud_list_no_expone_desglose_atp(create_actor: Any) -> None:
    """El desglose y las referencias quedan en el detalle."""
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
    assert "CONST-ATP-7788" not in html
    assert "TRF-BANCO-9911" not in html
    assert "Retención ATP Chaco" not in html
    assert "96500" not in html


# ---------------------------------------------------------------------------
# 4. Optimización de Consultas SQL (Prevención de N+1)
# ---------------------------------------------------------------------------


def test_solicitud_list_queries_optimizadas_sin_n_mas_1(
    create_actor: Any, django_assert_num_queries: Any
) -> None:
    """La consulta del listado evita N+1."""
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

    with django_assert_num_queries(5):
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


# ---------------------------------------------------------------------------
# 6. Etiqueta derivada Pagada y filtro de cualquier pendiente
# ---------------------------------------------------------------------------


def test_bandeja_distingue_aceptada_de_pagada_y_filtra_estado_pagada(
    create_actor: Any,
) -> None:
    """Pagada deriva del pago registrado y estado=pagada no cambia el estado guardado."""
    lector, _ = create_actor("lector_pagada", ["gastos.consultar_todas"])
    solicitante, _ = create_actor("solicitante_pagada", ["gastos.presentar"])
    sin_pago = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada sin pago",
        estado=EstadoSolicitud.ACEPTADA,
    )
    pagada = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada pagada",
        estado=EstadoSolicitud.ACEPTADA,
    )
    PagoExterno.objects.create(
        solicitud=pagada,
        monto_bruto=Decimal("100.00"),
        importe=Decimal("100.00"),
        referencia_documental="FAC-PAGADA-ETIQUETA",
        fecha_pago=date(2026, 11, 3),
        huella_idempotencia="huella-pagada-etiqueta",
    )

    client = Client()
    client.force_login(lector)

    response = client.get(reverse("gastos:lista"))
    html = response.content.decode()
    assert '<option value="pagada">Pagada</option>' in html
    assert '<select name="pendiente"' not in html
    assert '<input type="hidden" name="pendiente"' in html
    assert '<span class="bandeja-chip bandeja-chip-pagada">Pagada</span>' in html
    assert '<span class="bandeja-chip bandeja-chip-aceptada">Aceptada</span>' in html

    todas_aceptadas = client.get(reverse("gastos:lista"), {"estado": "aceptada"})
    assert {s.pk for s in todas_aceptadas.context["solicitudes"]} == {
        sin_pago.pk,
        pagada.pk,
    }

    solo_pagadas = client.get(reverse("gastos:lista"), {"estado": "pagada"})
    assert [s.pk for s in solo_pagadas.context["solicitudes"]] == [pagada.pk]

    detalle = client.get(reverse("gastos:detalle", kwargs={"pk": pagada.pk}))
    assert '<span class="sd-pill sd-pill-success">Pagada</span>' in detalle.content.decode()


def test_cualquier_pendiente_reune_condiciones_del_actor(create_actor: Any) -> None:
    """Cualquier pendiente aplica OR sobre decisión, pago y ATP disponibles."""
    operador, _ = create_actor("operador_mixto_pendiente", ["gastos.decidir"])
    for grupo in ("demo_gastos_pago", "demo_documentos_aporte", "demo_documentos_metadatos"):
        operador.groups.add(Group.objects.get_or_create(name=grupo)[0])
    solicitante, _ = create_actor("solicitante_mixto_pendiente", ["gastos.presentar"])

    por_decidir = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Presentada ajena",
        estado=EstadoSolicitud.PRESENTADA,
    )
    crear_gasto_sintetico(
        solicitante=operador,
        concepto="Presentada propia",
        estado=EstadoSolicitud.PRESENTADA,
    )
    sin_pago = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada sin pago",
        estado=EstadoSolicitud.ACEPTADA,
    )
    con_atp = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada con ATP pendiente",
        estado=EstadoSolicitud.ACEPTADA,
    )
    PagoExterno.objects.create(
        solicitud=con_atp,
        monto_bruto=Decimal("100.00"),
        monto_retencion_atp=Decimal("3.50"),
        importe=Decimal("96.50"),
        referencia_documental="FAC-ATP-MIXTA",
        fecha_pago=date(2026, 11, 3),
        huella_idempotencia="huella-atp-mixta",
    )
    pagada_sin_pendientes = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Aceptada pagada sin pendientes",
        estado=EstadoSolicitud.ACEPTADA,
    )
    PagoExterno.objects.create(
        solicitud=pagada_sin_pendientes,
        monto_bruto=Decimal("50.00"),
        importe=Decimal("50.00"),
        referencia_documental="FAC-PAGADA-MIXTA",
        fecha_pago=date(2026, 11, 4),
        huella_idempotencia="huella-pagada-mixta",
    )

    client = Client()
    client.force_login(operador)

    response = client.get(reverse("gastos:lista"))
    html = response.content.decode()
    assert '<option value="cualquiera">Cualquier pendiente</option>' in html
    assert '<option value="decision">Pendiente de decisión</option>' in html
    assert '<option value="pago">Sin pago registrado</option>' in html
    assert '<option value="atp">Constancia ATP pendiente</option>' in html

    filtrada = client.get(reverse("gastos:lista"), {"pendiente": "cualquiera"})
    assert {s.pk for s in filtrada.context["solicitudes"]} == {
        por_decidir.pk,
        sin_pago.pk,
        con_atp.pk,
    }
