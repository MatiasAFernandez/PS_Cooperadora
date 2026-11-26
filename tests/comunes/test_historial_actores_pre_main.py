"""Pruebas de paridad de actores y estados legibles en historial común (pre-main)."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from comunes.actores import resolver_actores_visibles
from documentos.models import Documento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.models import DecisionGasto, EstadoSolicitud
from identidad.services import Actor
from tests.soporte_gastos import crear_gasto_sintetico

pytestmark = pytest.mark.django_db


def _asignar_grupos(user: Any, *nombres: str) -> None:
    for nombre in nombres:
        grupo, _ = Group.objects.get_or_create(name=nombre)
        user.groups.add(grupo)


def test_resolver_actores_visibles_internos_y_solicitante() -> None:
    user_model = get_user_model()
    con_nombre = user_model.objects.create_user(
        username="op_con_nombre",
        password="demo",
        first_name="Elena",
        last_name="Vargas",
    )
    sin_nombre = user_model.objects.create_user(username="sol_sin_nombre", password="demo")

    mapa_interno = resolver_actores_visibles(
        [con_nombre.pk, sin_nombre.pk, "999999", None, ""],
        puede_ver_internos=True,
        titular_actor_id=sin_nombre.pk,
    )
    assert mapa_interno == {
        str(con_nombre.pk): "Elena Vargas",
        str(sin_nombre.pk): "sol_sin_nombre",
    }

    mapa_solicitante = resolver_actores_visibles(
        [con_nombre.pk, sin_nombre.pk],
        puede_ver_internos=False,
        titular_actor_id=sin_nombre.pk,
    )
    assert mapa_solicitante == {
        str(con_nombre.pk): "Cooperadora",
        str(sin_nombre.pk): "Titular",
    }
    assert resolver_actores_visibles([], puede_ver_internos=True) == {}


def test_historial_detalle_gasto_muestra_nombres_internos_y_etiquetas_neutrales(
    settings: Any,
) -> None:
    settings.DEMO_IDENTITY_ENABLED = True
    user_model = get_user_model()
    solicitante = user_model.objects.create_user(
        username="sol_hist_gasto",
        password="demo",
        first_name="Lucía",
        last_name="Pérez",
    )
    operadora = user_model.objects.create_user(
        username="op_hist_gasto",
        password="demo",
        first_name="Elena",
        last_name="Vargas",
    )
    _asignar_grupos(solicitante, "demo_solicitante")
    _asignar_grupos(operadora, "demo_operadora")

    gasto = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Compra de sensores sintéticos",
        estado=EstadoSolicitud.ACEPTADA,
    )
    DecisionGasto.objects.create(
        solicitud=gasto,
        autor=operadora,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
        motivo="Aprobación sintética",
    )
    url = reverse("gastos:detalle", kwargs={"pk": gasto.pk})

    c_op = Client()
    c_op.force_login(operadora)
    resp_op = c_op.get(url)
    assert resp_op.status_code == 200
    html_op = resp_op.content.decode("utf-8")
    assert "Elena Vargas" in html_op
    assert f"actor #{operadora.pk}" not in html_op
    assert "estado del trámite: Aceptada" in html_op
    assert resp_op.context["cronologia"][0].actor_id == str(operadora.pk)

    c_sol = Client()
    c_sol.force_login(solicitante)
    resp_sol = c_sol.get(url)
    assert resp_sol.status_code == 200
    html_sol = resp_sol.content.decode("utf-8")
    assert "Cooperadora" in html_sol
    assert "Elena Vargas" not in html_sol
    assert f"actor #{operadora.pk}" not in html_sol
    assert "estado del trámite: Aceptada" in html_sol


def test_historial_revision_documental_muestra_nombres_internos_y_neutrales(
    settings: Any, tmp_path: Any
) -> None:
    settings.DEMO_IDENTITY_ENABLED = True
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "privado_hist"
    user_model = get_user_model()
    solicitante = user_model.objects.create_user(
        username="sol_hist_doc",
        password="demo",
        first_name="Lucía",
        last_name="Pérez",
    )
    revisora = user_model.objects.create_user(
        username="rev_hist_doc",
        password="demo",
        first_name="Marta",
        last_name="Benítez",
    )
    _asignar_grupos(
        solicitante,
        "demo_solicitante",
        "demo_documentos_metadatos",
    )
    _asignar_grupos(
        revisora,
        "demo_operadora",
        "demo_documentos_metadatos",
        "demo_documentos_revision",
    )

    gasto = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Respaldo documental sintético",
        estado=EstadoSolicitud.ACEPTADA,
    )
    actor_rev = Actor(
        subject_id=revisora.pk,
        capabilities=frozenset(
            {
                "gastos.consultar_todas",
                "documentos.incorporar",
                "documentos.consultar_metadatos",
                "documentos.revisar",
            }
        ),
    )
    doc = incorporar(
        actor=actor_rev,
        referencia=f"gastos:{gasto.pk}",
        archivo=SimpleUploadedFile(
            "factura-sintetica.pdf",
            b"%PDF-1.7\nContenido sintetico\n%%EOF",
            "application/pdf",
        ),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.INTERNO_COOPERADORA,
    )
    revisar(
        actor=actor_rev,
        documento_id=doc.pk,
        resultado="ACEPTADO",
        motivo="",
        revision_esperada=0,
    )
    url = reverse("documentos:revision", kwargs={"documento_id": doc.pk})

    c_rev = Client()
    c_rev.force_login(revisora)
    resp_rev = c_rev.get(url)
    assert resp_rev.status_code == 200
    html_rev = resp_rev.content.decode("utf-8")
    assert "Marta Benítez" in html_rev
    assert f"actor #{revisora.pk}" not in html_rev
    assert "resultado documental: Aceptado" in html_rev

    c_sol = Client()
    c_sol.force_login(solicitante)
    resp_sol = c_sol.get(url)
    assert resp_sol.status_code == 200
    html_sol = resp_sol.content.decode("utf-8")
    assert "Cooperadora" in html_sol
    assert "Marta Benítez" not in html_sol
    assert f"actor #{revisora.pk}" not in html_sol
    assert "resultado documental: Aceptado" in html_sol
