"""Pruebas exhaustivas para el Reporte Directivo Cuatrimestral (Issue #94 / GAST-R08).

Cubre:
- GAST-R08: Control de acceso estricto mediante la capacidad 'gastos.consultar_todas'.
  - Usuario anónimo redirige a login / demo (HTTP 302).
  - Solicitante común (demo_a con 'gastos.presentar') recibe HTTP 403 PermissionDenied.
  - Usuario con 'gastos.consultar_todas' (demo_l / directivo) accede con HTTP 200.
  - Visibilidad condicional del botón de acceso en solicitud_list.html.
- Partición cuatrimestral canónica:
  - C1: Enero a Abril (meses 1 a 4).
  - C2: Mayo a Agosto (meses 5 a 8).
  - C3: Septiembre a Diciembre (meses 9 a 12).
- Exactitud contable de agregaciones (sin duplicación por JOIN):
  - Coalesce(Sum(...), Decimal("0.00")) en períodos vacíos o sin movimientos.
  - Identidad contable: Neto = Bruto - Retención ATP.
  - Reconciliación: Suma(C1, C2, C3) == Total Anual.
- Desglose por Centro de Costo institucional:
  - Agrupación por cada centro y fila especial para "Sin centro de costo asignado / Histórico".
  - Reconciliación: Suma(Centros + Sin Centro) == Total Anual.
- Filtrado por año y selector de ejercicios:
  - Aislamiento entre años (2025 vs 2026).
  - Fallback defensivo ante parámetros de año inválidos o no numéricos.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gastos.models import CentroCosto, EstadoSolicitud, PagoExterno, SolicitudGasto
from gastos.reports import (
    obtener_anios_disponibles_gastos,
    obtener_reporte_cuatrimestral_gastos,
)
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


# ---------------------------------------------------------------------------
# Helpers para configuración de escenarios sintéticos de reporte
# ---------------------------------------------------------------------------


def _crear_solicitud_con_fecha(
    solicitante: Any,
    concepto: str,
    monto_estimado: Decimal,
    fecha: date,
    centro_costo: CentroCosto | None = None,
) -> SolicitudGasto:
    """Crea una SolicitudGasto y fija su fecha_creacion mediante .update()."""
    solicitud = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto=concepto,
        monto_estimado=monto_estimado,
        estado=EstadoSolicitud.ACEPTADA,
        centro_costo=centro_costo,
    )
    dt = datetime(fecha.year, fecha.month, fecha.day, 12, 0, tzinfo=UTC)
    SolicitudGasto.objects.filter(pk=solicitud.pk).update(fecha_creacion=dt)
    solicitud.refresh_from_db()
    return solicitud


def _crear_pago_con_fecha(
    solicitud: SolicitudGasto,
    fecha_pago: date,
    monto_bruto: Decimal,
    monto_retencion_atp: Decimal = Decimal("0.00"),
) -> PagoExterno:
    """Registra un PagoExterno con fecha específica e importes bruto/ATP/neto."""
    neto = monto_bruto - monto_retencion_atp
    pago = PagoExterno.objects.create(
        solicitud=solicitud,
        importe=neto,
        moneda="ARS",
        fecha_pago=fecha_pago,
        referencia_externa=f"TRF-{uuid.uuid4().hex[:6].upper()}",
        referencia_documental=f"doc-{uuid.uuid4().hex[:8]}",
        huella_idempotencia=uuid.uuid4().hex,
        monto_bruto=monto_bruto,
        monto_retencion_atp=monto_retencion_atp,
        referencia_atp="RET-ATP-CHACO" if monto_retencion_atp > 0 else "",
    )
    return pago


# ---------------------------------------------------------------------------
# 1. Control de Acceso y Permisos (GAST-R08)
# ---------------------------------------------------------------------------


def test_acceso_anonimo_redirige_a_login(client: Any) -> None:
    """Un usuario anónimo no autenticado es redirigido a login al intentar ver el reporte."""
    url = reverse("gastos:reporte_cuatrimestral")
    response = client.get(url)
    assert response.status_code == 302
    assert reverse("identidad:login") in response.url


def test_solicitante_sin_capacidad_recibe_403(create_actor: Any, auth_client: Any) -> None:
    """Un solicitante común ('gastos.presentar') no puede acceder al reporte directivo."""
    user, _ = create_actor("solic_sin_reporte", ["gastos.presentar"])
    client = auth_client(user)

    url = reverse("gastos:reporte_cuatrimestral")
    response = client.get(url)
    assert response.status_code == 403


def test_usuario_con_consultar_todas_accede_con_200(
    create_actor: Any, auth_client: Any
) -> None:
    """Un usuario con 'gastos.consultar_todas' (auditor/directivo) accede exitosamente."""
    user, _ = create_actor("directivo_autorizado", ["gastos.consultar_todas"])
    client = auth_client(user)

    url = reverse("gastos:reporte_cuatrimestral")
    response = client.get(url)
    assert response.status_code == 200
    assert "Reporte Directivo de Gastos" in response.content.decode()


def test_visibilidad_boton_reporte_en_panel_segun_permisos(
    create_actor: Any, auth_client: Any
) -> None:
    """El botón 'Reporte Cuatrimestral' en solicitud_list.html sólo se muestra a autorizados."""
    solicitante, _ = create_actor("solic_panel", ["gastos.presentar"])
    directivo, _ = create_actor("dir_panel", ["gastos.consultar_todas"])

    client_solic = auth_client(solicitante)
    res_solic = client_solic.get(reverse("gastos:lista"))
    assert res_solic.status_code == 200
    enlace_reporte = f'href="{reverse("gastos:reporte_cuatrimestral")}"'
    assert enlace_reporte not in res_solic.content.decode()

    client_dir = auth_client(directivo)
    res_dir = client_dir.get(reverse("gastos:lista"))
    assert res_dir.status_code == 200
    assert enlace_reporte in res_dir.content.decode()
    assert reverse("gastos:reporte_cuatrimestral") in res_dir.content.decode()


# ---------------------------------------------------------------------------
# 2. Partición Cuatrimestral y Exactitud de Agregaciones (C1, C2, C3)
# ---------------------------------------------------------------------------


def test_reporte_base_vacia_devuelve_ceros_sin_none() -> None:
    """Sobre una base vacía, todos los campos decimales son Decimal('0.00') y conteos 0."""
    reporte = obtener_reporte_cuatrimestral_gastos(2026)

    assert reporte.anio == 2026
    assert len(reporte.cuatrimestres) == 3
    for c in reporte.cuatrimestres:
        assert c.cantidad_solicitudes == 0
        assert c.monto_solicitado == Decimal("0.00")
        assert c.cantidad_pagos == 0
        assert c.monto_erogado_bruto == Decimal("0.00")
        assert c.monto_retencion_atp == Decimal("0.00")
        assert c.monto_neto_transferido == Decimal("0.00")

    assert reporte.totales.cantidad_solicitudes == 0
    assert reporte.totales.monto_solicitado == Decimal("0.00")
    assert reporte.totales.monto_erogado_bruto == Decimal("0.00")
    assert reporte.totales.monto_retencion_atp == Decimal("0.00")
    assert reporte.totales.monto_neto_transferido == Decimal("0.00")


def test_agregacion_cuatrimestral_distribucion_exacta(create_actor: Any) -> None:
    """Verifica que cada cuatrimestre registre con precisión sus solicitudes y erogaciones."""
    user, _ = create_actor("solic_cuatri", ["gastos.presentar"])

    # 1. Trámite en C1 (marzo 2026): solicitada $10.000, pagada $10.000 (sin retención ATP)
    s_c1 = _crear_solicitud_con_fecha(user, "Gasto C1", Decimal("10000.00"), date(2026, 3, 10))
    _crear_pago_con_fecha(s_c1, date(2026, 3, 15), Decimal("10000.00"))

    # Solicitud adicional en C1 sin pagar (abril 2026): $5.000
    _crear_solicitud_con_fecha(user, "Gasto C1 pendiente", Decimal("5000.00"), date(2026, 4, 25))

    # 2. Trámite en C2 (junio 2026): solicitada $100.000, pagada con retención ATP ($3.500)
    s_c2 = _crear_solicitud_con_fecha(user, "Gasto C2", Decimal("100000.00"), date(2026, 6, 5))
    _crear_pago_con_fecha(
        s_c2, date(2026, 6, 20), Decimal("100000.00"), monto_retencion_atp=Decimal("3500.00")
    )

    # 3. Trámite en C3 (octubre 2026): solicitada $50.000, pagada $50.000 (sin retención)
    s_c3 = _crear_solicitud_con_fecha(user, "Gasto C3", Decimal("50000.00"), date(2026, 10, 1))
    _crear_pago_con_fecha(s_c3, date(2026, 10, 15), Decimal("50000.00"))

    reporte = obtener_reporte_cuatrimestral_gastos(2026)

    # Inspección de C1 (Ene–Abr)
    c1 = reporte.cuatrimestres[0]
    assert c1.cuatrimestre == 1
    assert c1.cantidad_solicitudes == 2
    assert c1.monto_solicitado == Decimal("15000.00")
    assert c1.cantidad_pagos == 1
    assert c1.monto_erogado_bruto == Decimal("10000.00")
    assert c1.monto_retencion_atp == Decimal("0.00")
    assert c1.monto_neto_transferido == Decimal("10000.00")

    # Inspección de C2 (May–Ago)
    c2 = reporte.cuatrimestres[1]
    assert c2.cuatrimestre == 2
    assert c2.cantidad_solicitudes == 1
    assert c2.monto_solicitado == Decimal("100000.00")
    assert c2.cantidad_pagos == 1
    assert c2.monto_erogado_bruto == Decimal("100000.00")
    assert c2.monto_retencion_atp == Decimal("3500.00")
    assert c2.monto_neto_transferido == Decimal("96500.00")
    assert c2.monto_neto_transferido == c2.monto_erogado_bruto - c2.monto_retencion_atp

    # Inspección de C3 (Sep–Dic)
    c3 = reporte.cuatrimestres[2]
    assert c3.cuatrimestre == 3
    assert c3.cantidad_solicitudes == 1
    assert c3.monto_solicitado == Decimal("50000.00")
    assert c3.cantidad_pagos == 1
    assert c3.monto_erogado_bruto == Decimal("50000.00")
    assert c3.monto_retencion_atp == Decimal("0.00")
    assert c3.monto_neto_transferido == Decimal("50000.00")

    # Reconciliación total anual
    assert reporte.totales.cantidad_solicitudes == 4
    assert reporte.totales.monto_solicitado == Decimal("165000.00")
    assert reporte.totales.cantidad_pagos == 3
    assert reporte.totales.monto_erogado_bruto == Decimal("160000.00")
    assert reporte.totales.monto_retencion_atp == Decimal("3500.00")
    assert reporte.totales.monto_neto_transferido == Decimal("156500.00")
    assert (
        reporte.totales.monto_neto_transferido
        == reporte.totales.monto_erogado_bruto - reporte.totales.monto_retencion_atp
    )


# ---------------------------------------------------------------------------
# 3. Desglose por Centro de Costo (con fila 'Sin centro asignado')
# ---------------------------------------------------------------------------


def test_agregacion_por_centro_de_costo_reconcilia_con_totales(create_actor: Any) -> None:
    """Verifica que las erogaciones se desglosen por centro de costo y reconcilien el 100%."""
    user, _ = create_actor("solic_cc", ["gastos.presentar"])

    cc_quimica = CentroCosto.objects.create(codigo="LAB-QUI", nombre="Laboratorio de Química")
    cc_sistemas = CentroCosto.objects.create(codigo="DEP-SIS", nombre="Departamento de Sistemas")

    # 1. Trámite asignado a LAB-QUI
    s1 = _crear_solicitud_con_fecha(
        user, "Reactivos", Decimal("20000.00"), date(2026, 2, 1), centro_costo=cc_quimica
    )
    _crear_pago_con_fecha(s1, date(2026, 2, 10), Decimal("20000.00"))

    # 2. Trámite asignado a DEP-SIS con retención ATP
    s2 = _crear_solicitud_con_fecha(
        user, "Licencias", Decimal("120000.00"), date(2026, 5, 10), centro_costo=cc_sistemas
    )
    _crear_pago_con_fecha(
        s2, date(2026, 5, 20), Decimal("120000.00"), monto_retencion_atp=Decimal("4200.00")
    )

    # 3. Trámite sin centro de costo asignado (None / Histórico)
    s3 = _crear_solicitud_con_fecha(
        user, "Respaldo histórico", Decimal("15000.00"), date(2026, 9, 1), centro_costo=None
    )
    _crear_pago_con_fecha(s3, date(2026, 9, 15), Decimal("15000.00"))

    reporte = obtener_reporte_cuatrimestral_gastos(2026)

    centros_dict = {c.codigo: c for c in reporte.centros_costo}

    # Centro LAB-QUI
    qui = centros_dict["LAB-QUI"]
    assert qui.nombre == "Laboratorio de Química"
    assert qui.cantidad_solicitudes == 1
    assert qui.monto_solicitado == Decimal("20000.00")
    assert qui.cantidad_pagos == 1
    assert qui.monto_erogado_bruto == Decimal("20000.00")
    assert qui.monto_retencion_atp == Decimal("0.00")
    assert qui.monto_neto_transferido == Decimal("20000.00")

    # Centro DEP-SIS
    sis = centros_dict["DEP-SIS"]
    assert sis.nombre == "Departamento de Sistemas"
    assert sis.cantidad_solicitudes == 1
    assert sis.monto_solicitado == Decimal("120000.00")
    assert sis.cantidad_pagos == 1
    assert sis.monto_erogado_bruto == Decimal("120000.00")
    assert sis.monto_retencion_atp == Decimal("4200.00")
    assert sis.monto_neto_transferido == Decimal("115800.00")

    # Fila Sin Centro de Costo Asignado
    sin_cc = centros_dict["-"]
    assert "Sin centro de costo asignado" in sin_cc.nombre
    assert sin_cc.cantidad_solicitudes == 1
    assert sin_cc.monto_solicitado == Decimal("15000.00")
    assert sin_cc.cantidad_pagos == 1
    assert sin_cc.monto_erogado_bruto == Decimal("15000.00")
    assert sin_cc.monto_retencion_atp == Decimal("0.00")
    assert sin_cc.monto_neto_transferido == Decimal("15000.00")

    # Reconciliación: la suma de todos los centros equivale a los totales globales
    suma_solic = sum(c.cantidad_solicitudes for c in reporte.centros_costo)
    suma_monto_solic = sum(c.monto_solicitado for c in reporte.centros_costo)
    suma_pagos = sum(c.cantidad_pagos for c in reporte.centros_costo)
    suma_bruto = sum(c.monto_erogado_bruto for c in reporte.centros_costo)
    suma_atp = sum(c.monto_retencion_atp for c in reporte.centros_costo)
    suma_neto = sum(c.monto_neto_transferido for c in reporte.centros_costo)

    assert suma_solic == reporte.totales.cantidad_solicitudes == 3
    assert suma_monto_solic == reporte.totales.monto_solicitado == Decimal("155000.00")
    assert suma_pagos == reporte.totales.cantidad_pagos == 3
    assert suma_bruto == reporte.totales.monto_erogado_bruto == Decimal("155000.00")
    assert suma_atp == reporte.totales.monto_retencion_atp == Decimal("4200.00")
    assert suma_neto == reporte.totales.monto_neto_transferido == Decimal("150800.00")


# ---------------------------------------------------------------------------
# 4. Aislamiento Temporal y Selector de Años
# ---------------------------------------------------------------------------


def test_aislamiento_entre_anios_calendario(create_actor: Any) -> None:
    """Verifica que los registros de 2025 no se mezclen con los de 2026."""
    user, _ = create_actor("solic_anios", ["gastos.presentar"])

    # Actividad en 2025
    s_2025 = _crear_solicitud_con_fecha(user, "Gasto 2025", Decimal("8000.00"), date(2025, 6, 1))
    _crear_pago_con_fecha(s_2025, date(2025, 6, 10), Decimal("8000.00"))

    # Actividad en 2026
    s_2026 = _crear_solicitud_con_fecha(user, "Gasto 2026", Decimal("16000.00"), date(2026, 6, 1))
    _crear_pago_con_fecha(s_2026, date(2026, 6, 10), Decimal("16000.00"))

    anios = obtener_anios_disponibles_gastos()
    assert 2025 in anios
    assert 2026 in anios

    reporte_2025 = obtener_reporte_cuatrimestral_gastos(2025)
    assert reporte_2025.anio == 2025
    assert reporte_2025.totales.cantidad_solicitudes == 1
    assert reporte_2025.totales.monto_solicitado == Decimal("8000.00")
    assert reporte_2025.totales.monto_erogado_bruto == Decimal("8000.00")

    reporte_2026 = obtener_reporte_cuatrimestral_gastos(2026)
    assert reporte_2026.anio == 2026
    assert reporte_2026.totales.cantidad_solicitudes == 1
    assert reporte_2026.totales.monto_solicitado == Decimal("16000.00")
    assert reporte_2026.totales.monto_erogado_bruto == Decimal("16000.00")


def test_vista_reporte_renderiza_kpis_y_tablas(create_actor: Any, auth_client: Any) -> None:
    """GET /gastos/reportes/cuatrimestral/ renderiza KPIs, tablas con .font-tabular y combo."""
    user, _ = create_actor("directivo_html", ["gastos.consultar_todas"])
    client = auth_client(user)

    s = _crear_solicitud_con_fecha(
        user, "Gasto Auditoría UX", Decimal("95000.00"), date(2026, 2, 10)
    )
    _crear_pago_con_fecha(
        s, date(2026, 2, 15), Decimal("95000.00"), monto_retencion_atp=Decimal("3325.00")
    )

    response = client.get(reverse("gastos:reporte_cuatrimestral"), {"anio": "2026"})
    assert response.status_code == 200
    html = response.content.decode()

    # Verificación de elementos del template Calidad 2026
    assert "Reporte Directivo de Gastos" in html
    assert 'id="kpiBruto">$ 95.000,00' in html
    assert 'id="kpiAtp">$ 3.325,00' in html
    assert 'id="kpiNeto">$ 91.675,00' in html
    assert 'id="ch1SrTable"' in html
    assert "Sin centro de costo asignado" in html
    assert "font-tabular" in html


def test_vista_reporte_fallback_anio_invalido(create_actor: Any, auth_client: Any) -> None:
    """GET con parámetro 'anio' malformado o fuera de rango hace fallback seguro sin error 500."""
    user, _ = create_actor("directivo_fallback", ["gastos.consultar_todas"])
    client = auth_client(user)

    # Año de texto no numérico
    res_texto = client.get(reverse("gastos:reporte_cuatrimestral"), {"anio": "abc"})
    assert res_texto.status_code == 200

    # Año absurdo
    res_absurdo = client.get(reverse("gastos:reporte_cuatrimestral"), {"anio": "1800"})
    assert res_absurdo.status_code == 200


def test_ranking_y_filtros_por_centro(create_actor: Any, auth_client: Any) -> None:
    user, _ = create_actor("directivo_ranking", ["gastos.consultar_todas"])
    client = auth_client(user)
    url = reverse("gastos:reporte_cuatrimestral")
    centros = [
        CentroCosto.objects.create(codigo=f"AREA-{i:02}", nombre=f"Área {i}")
        for i in range(35)
    ]
    fecha = date(2026, 2, 1)
    for i, centro in enumerate(centros[27:], start=1):
        monto = Decimal(i * 1000)
        solicitud = _crear_solicitud_con_fecha(user, centro.nombre, monto, fecha, centro)
        _crear_pago_con_fecha(solicitud, fecha, monto)
    _crear_solicitud_con_fecha(user, "Compra sin pagar", Decimal("500"), fecha, centros[26])

    general = client.get(url, {"anio": 2026, "corte": "C1"})
    assert general.status_code == 200
    assert [row.codigo for row in general.context["centros_costo_top"]] == [
        centro.codigo for centro in reversed(centros[-6:])
    ]
    assert len(general.context["centros_costo_tabla"]) == 9
    todos = client.get(url, {"anio": 2026, "corte": "C1", "sin_actividad": "1"})
    assert {row.codigo for row in todos.context["centros_costo_tabla"]} >= {
        centro.codigo for centro in centros
    }

    filtrado = client.get(url, {"anio": 2026, "corte": "C1", "centro_costo": centros[-1].pk})
    assert filtrado.status_code == 200
    reporte = filtrado.context["reporte"]
    assert reporte.totales.cantidad_solicitudes == 1
    assert reporte.totales.monto_erogado_bruto == Decimal("8000")
    assert reporte.cuatrimestres[0].monto_erogado_bruto == Decimal("8000")
    assert filtrado.context["pendientes_actuales"] == general.context["pendientes_actuales"]

    invalido = client.get(url, {"anio": 2026, "corte": "C1", "centro_costo": "9" * 25})
    assert invalido.status_code == 200
    assert invalido.context["reporte"].totales == general.context["reporte"].totales
