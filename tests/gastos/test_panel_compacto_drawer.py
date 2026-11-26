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
    """El lector ve la tabla compacta, el resumen y los enlaces al detalle."""
    user, _ = create_actor("usuario_consulta", ["gastos.consultar_todas"])
    client = Client()
    client.force_login(user)

    centro = CentroCosto.objects.create(codigo="cc-quimica", nombre="Química")
    solicitud = _crear_solicitud_con_transferencia(
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
    assert f'data-vista-rapida="resumen-{solicitud.pk}"' in content
    assert "<dt>Centro de costo</dt><dd>Química</dd>" in content
    panel = content.split(f'id="resumen-{solicitud.pk}"', 1)[1].split("</dialog>", 1)[0]
    assert '<a class="btn btn-primary"' in panel
    assert panel.count(">Ver detalle</a>") == 1
    assert 'class="btn btn-secondary"' not in panel


def test_solicitud_list_drawer_privacidad_ssr_sin_datos_bancarios(create_actor: Any) -> None:
    """Usuario sin permiso de registrar pago (demo_lectura) NO recibe CBU en el DOM."""
    user_titular, _ = create_actor("titular_real", ["gastos.presentar"])
    user_lectura, _ = create_actor("demo_lectura", ["gastos.consultar_todas"])

    cbu_secreto = "0110599540000012345678"
    titular_secreto = "Proveedor Confidencial SA"
    solicitud = _crear_solicitud_con_transferencia(
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

    assert f'data-vista-rapida="resumen-{solicitud.pk}"' in html


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
    """El titular recibe la vista rápida de sus gastos, sin datos bancarios."""
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
    otro_titular, _ = create_actor("otro_titular", ["gastos.presentar"])
    ajena = crear_gasto_sintetico(solicitante=otro_titular, concepto="Solicitud ajena")

    client = Client()
    client.force_login(user_titular)

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200

    html = response.content.decode()
    assert cbu_propio not in html
    assert "Copiar CBU" not in html
    assert f'data-vista-rapida="resumen-{solicitud.pk}"' in html
    assert f'id="resumen-{ajena.pk}"' not in html
    assert "Solicitud ajena" not in html
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

    # 6 consultas del listado + 1 consulta fija de CuentaLocal para resolver la
    # identidad en esta petición (el contrato exige comprobar la base cada vez,
    # sin caché entre peticiones). El usuario y su cuenta se reutilizan al renderizar.
    with django_assert_num_queries(7):
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

    # 5 consultas del listado + 1 consulta fija de CuentaLocal para resolver la
    # identidad en esta petición (el contrato exige comprobar la base cada vez,
    # sin caché entre peticiones). El usuario y su cuenta se reutilizan al renderizar.
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
    assert '<span class="status-pill status-success">Pagada</span>' in detalle.content.decode()


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


# ---------------------------------------------------------------------------
# 7. Orden de filtros, preservación entre pestañas y limpieza contextual
# ---------------------------------------------------------------------------


def test_buscador_aparece_primero_en_el_dom_de_filtros(create_actor: Any) -> None:
    """El orden del DOM y tabulación ubica el buscador antes del selector de estado."""
    operador, _ = create_actor("operador_orden_filtros", ["gastos.decidir"])
    client = Client()
    client.force_login(operador)

    response = client.get(reverse("gastos:lista"))
    assert response.status_code == 200
    assert list(response.context["filtro_form"].fields)[:4] == [
        "q",
        "estado",
        "pendiente",
        "periodo",
    ]
    html = response.content.decode()
    assert html.index('id="id_q"') < html.index('id="id_estado"')


def test_pestanas_conservan_filtros_compatibles_y_vuelven_a_primera_pagina(
    create_actor: Any,
) -> None:
    """Al cambiar de pestaña conserva búsqueda y filtros compatibles, sin paginación."""
    operador, _ = create_actor("operador_tabs_filtros", ["gastos.decidir"])
    for grupo in ("demo_gastos_pago", "demo_documentos_aporte", "demo_documentos_metadatos"):
        operador.groups.add(Group.objects.get_or_create(name=grupo)[0])
    client = Client()
    client.force_login(operador)

    # Desde Todas con criterio compatible y página 2 -> Requieren atención conserva todo sin page
    r_compatible = client.get(
        reverse("gastos:lista"),
        {"q": "QA 134", "estado": "aceptada", "periodo": "anio", "anio": "2026", "page": "2"},
    )
    assert (
        r_compatible.context["url_tab_atencion"]
        == "/gastos/?atencion=1&q=QA+134&estado=aceptada&periodo=anio&anio=2026"
    )
    assert (
        r_compatible.context["url_tab_todas"]
        == "/gastos/?q=QA+134&estado=aceptada&periodo=anio&anio=2026"
    )

    # Estado incompatible (rechazada) se descarta al ir a Requieren atención, manteniendo q
    r_incompatible = client.get(
        reverse("gastos:lista"),
        {"q": "QA 134", "estado": "rechazada", "page": "3"},
    )
    assert r_incompatible.context["url_tab_atencion"] == "/gastos/?atencion=1&q=QA+134"
    assert r_incompatible.context["url_tab_todas"] == "/gastos/?q=QA+134&estado=rechazada"

    # Desde Requieren atención hacia Todas conserva criterios y vuelve a página 1
    r_desde_atencion = client.get(
        reverse("gastos:lista"),
        {"atencion": "1", "q": "QA 134", "pendiente": "pago", "pagina": "2"},
    )
    assert r_desde_atencion.context["url_tab_todas"] == "/gastos/?q=QA+134&pendiente=pago"
    assert (
        r_desde_atencion.context["url_tab_atencion"]
        == "/gastos/?atencion=1&q=QA+134&pendiente=pago"
    )


def test_quitar_filtros_solo_visible_con_criterios_y_limpia_en_pestana_actual(
    create_actor: Any,
) -> None:
    """Quitar filtros se oculta sin criterios y limpia dentro de la pestaña activa."""
    operador, _ = create_actor("operador_limpiar_filtros", ["gastos.decidir"])
    client = Client()
    client.force_login(operador)

    sin_filtros_todas = client.get(reverse("gastos:lista"))
    assert sin_filtros_todas.context["tiene_filtros_activos"] is False
    assert (
        'data-bandeja-limpiar hidden href="/gastos/">Quitar filtros</a>'
        in sin_filtros_todas.content.decode()
    )

    sin_filtros_atencion = client.get(reverse("gastos:lista"), {"atencion": "1"})
    assert sin_filtros_atencion.context["tiene_filtros_activos"] is False
    assert sin_filtros_atencion.context["limpiar_filtros_url"] == "/gastos/?atencion=1"
    assert (
        'data-bandeja-limpiar hidden href="/gastos/?atencion=1">Quitar filtros</a>'
        in sin_filtros_atencion.content.decode()
    )
    assert sin_filtros_atencion.context["url_tab_todas"] == "/gastos/"

    con_filtros_atencion = client.get(
        reverse("gastos:lista"), {"atencion": "1", "q": "insumos"}
    )
    assert con_filtros_atencion.context["tiene_filtros_activos"] is True
    assert con_filtros_atencion.context["limpiar_filtros_url"] == "/gastos/?atencion=1"
    assert (
        'data-bandeja-limpiar href="/gastos/?atencion=1">Quitar filtros</a>'
        in con_filtros_atencion.content.decode()
    )
    assert con_filtros_atencion.context["url_tab_todas"] == "/gastos/?q=insumos"


# ---------------------------------------------------------------------------
# 8. Requieren atención para Solicitantes (Incremento 8A / D-4 + A2)
# ---------------------------------------------------------------------------


def test_solicitante_ve_pestana_atencion_observada_y_deuda_con_cta_adjuntar(
    create_actor: Any, django_assert_num_queries: Any
) -> None:
    """Solicitante agrupa OBSERVADA + deuda en O(1) con contador solo en Atención."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from documentos.models import Documento
    from documentos.revision import revisar
    from documentos.services import incorporar
    from gastos.models import CierreGasto
    from identidad.services import Actor

    solicitante, _ = create_actor("solicitante_inc8a_tabs", ["gastos.presentar"])
    for grupo in ("demo_documentos_aporte", "demo_documentos_metadatos"):
        solicitante.groups.add(Group.objects.get_or_create(name=grupo)[0])
    otro, _ = create_actor("otro_inc8a_tabs", ["gastos.presentar"])
    operador, _ = create_actor("operador_inc8a_cierre", ["gastos.decidir"])

    observada = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Gasto observado propio",
        estado=EstadoSolicitud.OBSERVADA,
    )
    deuda = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Compra directa con factura pendiente",
        estado=EstadoSolicitud.ACEPTADA,
    )
    deuda.tipo_flujo = TipoFlujoGasto.COMPRA_DIRECTA
    deuda.save()
    PagoExterno.objects.create(
        solicitud=deuda,
        monto_bruto=Decimal("500.00"),
        importe=Decimal("500.00"),
        referencia_documental="PRESUP-INC8A-1",
        fecha_pago=date(2026, 11, 20),
        huella_idempotencia="huella-inc8a-deuda-1",
    )
    # Presentada normal y compra directa ya cerrada NO deben entrar en Requieren atención
    crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Presentada sin acción propia",
        estado=EstadoSolicitud.PRESENTADA,
    )
    cerrada = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Compra directa cerrada",
        estado=EstadoSolicitud.ACEPTADA,
    )
    cerrada.tipo_flujo = TipoFlujoGasto.COMPRA_DIRECTA
    cerrada.save()
    actor_full = Actor(
        subject_id=operador.pk,
        capabilities=frozenset(
            {
                "gastos.consultar_todas",
                "documentos.incorporar",
                "documentos.consultar_metadatos",
                "documentos.revisar",
            }
        ),
    )
    pdf = lambda nombre: SimpleUploadedFile(  # noqa: E731
        nombre, b"%PDF-1.7\nContenido test\n%%EOF", "application/pdf"
    )
    doc_f = incorporar(
        actor=actor_full,
        referencia=f"gastos:{cerrada.pk}",
        archivo=pdf("fac-cerrada.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.INTERNO_COOPERADORA,
    )
    rev_f = revisar(
        actor=actor_full,
        documento_id=doc_f.pk,
        resultado="ACEPTADO",
        motivo="",
        revision_esperada=0,
    )
    doc_p = incorporar(
        actor=actor_full,
        referencia=f"gastos:{cerrada.pk}",
        archivo=pdf("comp-cerrada.pdf"),
        tipo=Documento.Tipo.COMPROBANTE_PAGO,
        procedencia=Documento.Procedencia.EXTERNO_BANCO,
    )
    rev_p = revisar(
        actor=actor_full,
        documento_id=doc_p.pk,
        resultado="ACEPTADO",
        motivo="",
        revision_esperada=0,
    )
    PagoExterno.objects.create(
        solicitud=cerrada,
        monto_bruto=Decimal("300.00"),
        importe=Decimal("300.00"),
        referencia_documental=str(doc_f.referencia_version),
        comprobante_bancario=doc_p,
        fecha_pago=date(2026, 11, 18),
        huella_idempotencia="huella-inc8a-deuda-2",
    )
    CierreGasto.objects.create(
        solicitud=cerrada,
        actor=operador,
        observacion="Cerrada en test",
        pago_version=1,
        documento_fiscal=doc_f,
        revision_fiscal=rev_f,
        documento_comprobante_pago=doc_p,
        revision_comprobante_pago=rev_p,
    )
    # Observada ajena no visible para el solicitante
    crear_gasto_sintetico(
        solicitante=otro,
        concepto="Observada de otro usuario",
        estado=EstadoSolicitud.OBSERVADA,
    )

    client = Client()
    client.force_login(solicitante)

    # Cantidad fija de consultas independientemente del número de filas
    with django_assert_num_queries(9):
        resp_todas = client.get(reverse("gastos:lista"))
    assert resp_todas.status_code == 200
    assert resp_todas.context["ofrece_atencion"] is True
    assert resp_todas.context["total_atencion"] == 2
    html_todas = resp_todas.content.decode()
    assert "Requieren atención" in html_todas
    assert 'data-bandeja-tab="atencion" class="bandeja-tab-con-pendientes"' in html_todas
    assert '<span class="bandeja-tab-count">2</span>' in html_todas
    # A2: solo en Requieren atención (clase base + modificador --attn)
    assert html_todas.count('class="bandeja-tab-count"') == 1

    resp_atencion = client.get(reverse("gastos:lista"), {"atencion": "1"})
    assert resp_atencion.status_code == 200
    assert {s.pk for s in resp_atencion.context["solicitudes"]} == {observada.pk, deuda.pk}
    html_atencion = resp_atencion.content.decode()
    assert f'href="/gastos/{deuda.pk}/?bandeja=atencion%3D1#cargar-respaldo"' in html_atencion
    assert "Adjuntar factura" in html_atencion
    href_obs = f'href="/gastos/{observada.pk}/?bandeja=atencion%3D1#observacion-solicitud"'
    assert href_obs in html_atencion
    assert "Corregir solicitud" in html_atencion
    panel = html_atencion.split(f'id="resumen-{observada.pk}"', 1)[1].split("</dialog>", 1)[0]
    assert (
        f'<a class="btn btn-secondary" href="/gastos/{observada.pk}/?bandeja=atencion%3D1">'
        "Ver detalle</a>" in panel
    )
    assert f'<a class="btn btn-primary" {href_obs}>Corregir solicitud</a>' in panel

    # Filtros compatibles vs incompatibles al cambiar de pestaña
    r_obs = client.get(reverse("gastos:lista"), {"estado": "observada", "q": "propio"})
    assert r_obs.context["url_tab_atencion"] == "/gastos/?atencion=1&q=propio&estado=observada"
    r_rech = client.get(reverse("gastos:lista"), {"estado": "rechazada", "q": "propio"})
    assert r_rech.context["url_tab_atencion"] == "/gastos/?atencion=1&q=propio"

    # Sin permiso documentos.incorporar, el CTA de deuda cae en Ver detalle (#seguimiento-factura)
    solicitante.groups.remove(Group.objects.get(name="demo_documentos_aporte"))
    html_sin_aporte = client.get(reverse("gastos:lista"), {"atencion": "1"}).content.decode()
    assert "Adjuntar factura" not in html_sin_aporte
    assert f'href="/gastos/{deuda.pk}/?bandeja=atencion%3D1#seguimiento-factura"' in html_sin_aporte


def test_atencion_vacia_para_solicitante_y_lectura(create_actor: Any) -> None:
    """Las cuentas sin pendientes tienen un contador neutro y una vista vacía."""
    solicitante, _ = create_actor("solicitante_sin_pendientes", ["gastos.presentar"])
    crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Presentada sin deuda",
        estado=EstadoSolicitud.PRESENTADA,
    )
    client = Client()
    client.force_login(solicitante)
    resp = client.get(reverse("gastos:lista"), {"atencion": "1"})
    assert resp.status_code == 200
    assert resp.context["total_atencion"] == 0
    assert list(resp.context["solicitudes"]) == []
    assert "No tenés solicitudes que requieran atención en este momento." in resp.content.decode()

    lector, _ = create_actor("lector_sin_pendientes", ["gastos.consultar_todas"])
    client.force_login(lector)
    lista_url = reverse("gastos:lista")
    resp_lector = client.get(lista_url)
    assert resp_lector.status_code == 200
    assert resp_lector.context["ofrece_atencion"] is False
    assert len(resp_lector.context["solicitudes"]) == 1
    html_lector = resp_lector.content.decode()
    assert 'Requieren atención <span class="bandeja-tab-count">0</span>' in html_lector
    assert "bandeja-tab-con-pendientes" not in html_lector
    pendientes_lector = client.get(lista_url, {"atencion": "1"})
    assert list(pendientes_lector.context["solicitudes"]) == []
