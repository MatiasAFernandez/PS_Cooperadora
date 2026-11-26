"""Pruebas del micro-PR de cierre UX final (campos dinámicos, 403/404/500, fallbacks y emails)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.template import Context, Engine
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from comunes.error_views import error_403, error_404, error_500
from comunes.filtros import FiltroFechaForm
from comunes.models import Circuito, TramiteBase
from facturacion.workflow import emitir_token, presentar_solicitud_facturacion
from gestion.models import ConfiguracionFormulario, RespuestaFormulario
from identidad.datos_usuarios import _limpiar_y_validar_datos
from identidad.models import CuentaLocal
from identidad.services import actor_para_usuario
from tests.soporte_gastos import crear_gasto_sintetico

pytestmark = pytest.mark.django_db(transaction=True)


def _asignar_grupos(user: Any, *nombres: str) -> None:
    for nombre in nombres:
        grupo, _ = Group.objects.get_or_create(name=nombre)
        user.groups.add(grupo)


def _campos_dinamicos_demo() -> list[dict[str, Any]]:
    return [
        {
            "clave": "sec_proyecto",
            "etiqueta": "Datos del proyecto",
            "ayuda": "Completá esta sección solo si corresponde a un proyecto financiado.",
            "tipo": "seccion",
            "requerido": False,
            "activo": True,
            "orden": 900,
            "opciones": [],
        },
        {
            "clave": "codigo_proyecto",
            "etiqueta": "Código de proyecto",
            "ayuda": "Ej.: PID-2026-04",
            "tipo": "texto",
            "requerido": False,
            "activo": True,
            "orden": 901,
            "opciones": [],
        },
        {
            "clave": "prioridad_area",
            "etiqueta": "Prioridad del área",
            "ayuda": "Indicá la urgencia operativa.",
            "tipo": "seleccion",
            "requerido": True,
            "activo": True,
            "orden": 902,
            "opciones": [["NORMAL", "Normal"], ["ALTA", "Alta"]],
        },
    ]


def test_campos_adicionales_y_respuestas_en_gastos_y_facturacion(settings: Any) -> None:
    settings.DEMO_IDENTITY_ENABLED = True
    user_model = get_user_model()
    solicitante = user_model.objects.create_user(
        username="sol_dinamico",
        password="demo",
        email="sol.dinamico@example.invalid",
        first_name="Sofía",
        last_name="Méndez",
    )
    _asignar_grupos(solicitante, "demo_solicitante", "demo_facturacion_solicitante")

    ConfiguracionFormulario.objects.update_or_create(
        circuito="GASTO", defaults={"revision": 3, "campos": _campos_dinamicos_demo()}
    )
    ConfiguracionFormulario.objects.update_or_create(
        circuito="FACTURACION", defaults={"revision": 2, "campos": _campos_dinamicos_demo()}
    )

    client = Client()
    client.force_login(solicitante)

    # 1. Formularios con campos adicionales reales en ambos circuitos
    for url in (reverse("gastos:presentar"), reverse("facturacion:presentar")):
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        assert 'class="gestion-extra-card"' in html
        assert "Datos del proyecto" in html
        assert "Código de proyecto" in html
        assert "(Opcional)" in html
        assert "Prioridad del área" in html
        assert "Código de proyecto:" not in html
        assert 'class="ns-section"' not in html or url == reverse("gastos:presentar")

    # 2. Respuestas guardadas en detalle de Gasto
    gasto = crear_gasto_sintetico(solicitante=solicitante, concepto="Gasto con campo dinámico")
    base_gasto, _ = TramiteBase.objects.get_or_create(
        circuito=Circuito.GASTO,
        numero_publico=gasto.pk,
        defaults={"solicitante_actor_id": str(solicitante.pk)},
    )
    RespuestaFormulario.objects.create(
        tramite=base_gasto,
        actor=solicitante,
        revision=3,
        campos=_campos_dinamicos_demo(),
        datos={
            "codigo_proyecto": {
                "etiqueta": "Código de proyecto",
                "tipo": "texto",
                "valor": "PID-2026-04",
            },
            "prioridad_area": {
                "etiqueta": "Prioridad del área",
                "tipo": "seleccion",
                "valor": "Alta",
            },
        },
    )
    resp_g = client.get(reverse("gastos:detalle", kwargs={"pk": gasto.pk}))
    assert resp_g.status_code == 200
    html_g = resp_g.content.decode("utf-8")
    assert "gestion-respuestas" in html_g
    assert "gestion-respuestas-chevron" in html_g
    assert "PID-2026-04" in html_g
    assert "gestion-card" not in html_g

    # 3. Respuestas guardadas en detalle de Facturación
    actor_sol = actor_para_usuario(solicitante)
    assert actor_sol is not None
    fac = presentar_solicitud_facturacion(
        actor=actor_sol,
        datos={
            "presento_comprobante_pago": False,
            "nombre_solicitante": "Sofía Méndez",
            "cuit_receptor": "30712345671",
            "nombre_receptor": "Empresa Sintética SRL",
            "condicion_iva": "IVA_RESPONSABLE_INSCRIPTO",
            "email_envio_factura": "factura.qa@example.invalid",
            "detalle_factura": "Servicio sintético de prueba",
            "importe_factura": "150000.00",
            "producto_servicio": "ANALISIS",
            "centro_costo": "GISTAQ",
            "modalidad_cobro": "CUENTA_CORRIENTE",
            "observaciones": "",
            "configuracion_revision": "2",
            "codigo_proyecto": "PID-FAC-09",
            "prioridad_area": "ALTA",
        },
        token_presentacion=emitir_token(actor_sol),
    )
    resp_f = client.get(reverse("facturacion:detalle", args=[fac.pk]))
    assert resp_f.status_code == 200
    html_f = resp_f.content.decode("utf-8")
    assert "gestion-respuestas" in html_f
    assert "gestion-respuestas-chevron" in html_f
    assert "PID-FAC-09" in html_f
    assert "gestion-card" not in html_f


def test_paginas_error_403_404_autenticado_y_anonimo_y_500_autosuficiente(settings: Any) -> None:
    settings.DEMO_IDENTITY_ENABLED = True
    settings.LOCAL_IDENTITY_ENABLED = True
    rf = RequestFactory()
    user_model = get_user_model()
    user = user_model.objects.create_user(username="err_user", password="demo")
    _asignar_grupos(user, "demo_solicitante")

    # 1. 403 y 404 sin sesión
    req_anon = rf.get("/ruta-inexistente/")
    req_anon.user = type("Anon", (), {"is_authenticated": False})()
    for view_fn, status_esperado, titulo in (
        (error_403, 403, "No tenés permisos para ver esta pantalla"),
        (error_404, 404, "No encontramos la página que buscás"),
    ):
        resp = view_fn(req_anon)
        assert resp.status_code == status_esperado
        assert "no-store" in resp.headers.get("Cache-Control", "")
        html = resp.content.decode("utf-8")
        assert titulo in html
        assert "Iniciar sesión" in html
        assert 'id="app-nav"' not in html

    # 2. 403 y 404 con sesión iniciada (con sidebar) — HTTP real con DEBUG=False
    CuentaLocal.objects.create(
        user=user,
        email="err.user@example.invalid",
        nombre_completo="Usuario Error",
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=datetime(2026, 11, 20, tzinfo=UTC),
    )
    with override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"]):
        client_auth = Client()
        client_auth.force_login(user)

        resp_403_auth = client_auth.get(reverse("gestion:configuracion", args=["GASTO"]))
        assert resp_403_auth.status_code == 403
        html_403 = resp_403_auth.content.decode("utf-8")
        assert "No tenés permisos para ver esta pantalla" in html_403
        assert "Volver al inicio" in html_403
        assert 'id="app-nav"' in html_403

        resp_404_auth = client_auth.get("/esta-ruta-no-existe-autenticado/")
        assert resp_404_auth.status_code == 404
        html_404 = resp_404_auth.content.decode("utf-8")
        assert "No encontramos la página que buscás" in html_404
        assert "Volver al inicio" in html_404
        assert 'id="app-nav"' in html_404

        # 3. 404 real sin sesión con DEBUG=False
        client_anon = Client()
        resp_404_anon = client_anon.get("/esta-ruta-no-existe-jamas/")
        assert resp_404_anon.status_code == 404
        html_404_anon = resp_404_anon.content.decode("utf-8")
        assert "No encontramos la página que buscás" in html_404_anon
        assert "Iniciar sesión" in html_404_anon
        assert 'id="app-nav"' not in html_404_anon

    # 4. 500 autosuficiente (sin context processors, sin bibliotecas, sin DB)
    engine = Engine(dirs=settings.TEMPLATES[0]["DIRS"], libraries={})
    html_500 = engine.get_template("500.html").render(Context({}))
    assert "Ocurrió un error inesperado" in html_500
    assert "#162f52" in html_500
    assert "#1e4273" in html_500
    resp_500 = error_500(req_anon)
    assert resp_500.status_code == 500
    assert "Ocurrió un error inesperado" in resp_500.content.decode("utf-8")


def test_campos_filtro_sin_dos_puntos_en_labels() -> None:
    html = render_to_string(
        "comunes/campos_filtro.html",
        {"form": FiltroFechaForm()},
    )
    assert "<label for=" in html
    assert ":</label>" not in html


def test_fallback_nombre_completo_en_subpaginas_usuarios(settings: Any) -> None:
    settings.LOCAL_IDENTITY_ENABLED = True
    user_model = get_user_model()
    admin = user_model.objects.create_user(
        username="admin_fb", email="admin.fb@example.invalid", password="demo"
    )
    _asignar_grupos(admin, "local_administracion")
    CuentaLocal.objects.create(
        user=admin,
        email="admin.fb@example.invalid",
        nombre_completo="Admin Prueba",
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=datetime(2026, 11, 20, tzinfo=UTC),
    )
    target_user = user_model.objects.create_user(
        username="sin_nombre_fb", email="sinnombre.fb@example.invalid", password="demo"
    )
    cuenta = CuentaLocal.objects.create(
        user=target_user,
        email="sinnombre.fb@example.invalid",
        nombre_completo="",
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=datetime(2026, 11, 20, tzinfo=UTC),
    )

    client = Client()
    client.force_login(admin)
    for url_name in (
        "cuentas:usuario_detalle",
        "cuentas:usuario_editar",
        "cuentas:usuario_perfiles",
        "cuentas:usuario_actividad",
    ):
        resp = client.get(reverse(url_name, args=[cuenta.pk]))
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        assert "sinnombre.fb@example.invalid" in html
        assert '<h1 class="cuentas-title"></h1>' not in html


def test_correos_avisos_sin_colores_legacy_y_voseo_identidad() -> None:
    base = Path(__file__).resolve().parents[2]
    for nombre in (
        "nueva_solicitud.html",
        "decision_solicitud.html",
        "pago_externo_registrado.html",
    ):
        contenido = (base / "templates" / "avisos" / "email" / nombre).read_text(encoding="utf-8")
        assert "#090979" not in contenido
        assert "#084298" not in contenido
        assert "#162f52" in contenido
        assert "#1e4273" in contenido

    with pytest.raises(Exception) as exc_info:
        _limpiar_y_validar_datos({"nombre_completo": 123})
    assert "Ingresá un texto válido." in str(exc_info.value)
