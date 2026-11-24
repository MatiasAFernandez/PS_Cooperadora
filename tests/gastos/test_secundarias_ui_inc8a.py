"""Pruebas de modernización y coherencia de vistas secundarias de Gastos (Incremento 8A)."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from documentos.models import Documento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.models import (
    CierreGasto,
    EstadoSolicitud,
    PagoExterno,
    TipoFlujoGasto,
)
from identidad.services import Actor, actor_para_usuario
from tests.soporte_gastos import crear_gasto_sintetico

pytestmark = pytest.mark.django_db


def _pdf_sintetico(nombre: str = "respaldo-inc8a.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"%PDF-1.7\nDocumento sintetico Inc 8A\n%%EOF",
        "application/pdf",
    )


def _preparar_gasto_listo_para_cierre(
    *, solicitante: Any, operador: Any, concepto: str, huella: str
) -> tuple[Any, Documento, Any, Documento, Any]:
    """Crea un gasto aceptado con pago y documentos obligatorios aceptados."""
    gasto = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto=concepto,
        estado=EstadoSolicitud.ACEPTADA,
    )
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
    doc_f = incorporar(
        actor=actor_full,
        referencia=f"gastos:{gasto.pk}",
        archivo=_pdf_sintetico(f"fac-{huella}.pdf"),
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
        referencia=f"gastos:{gasto.pk}",
        archivo=_pdf_sintetico(f"comp-{huella}.pdf"),
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
        solicitud=gasto,
        monto_bruto=Decimal("1200.00"),
        importe=Decimal("1200.00"),
        referencia_documental=str(doc_f.referencia_version),
        comprobante_bancario=doc_p,
        fecha_pago=date(2026, 11, 10),
        huella_idempotencia=huella,
    )
    return gasto, doc_f, rev_f, doc_p, rev_p


def test_detalle_gasto_respuestas_dentro_estado_cerrada_neutro_y_sin_legado(
    create_actor: Any,
) -> None:
    """Detalle incluye respuestas en main, Cerrada gris neutro y sin legado."""
    from gestion.models import RespuestaFormulario

    solicitante, _ = create_actor("sol_det_inc8a", ["gastos.presentar"])
    operador, _ = create_actor("op_det_inc8a", ["gastos.decidir"])
    gasto, doc_f, rev_f, doc_p, rev_p = _preparar_gasto_listo_para_cierre(
        solicitante=solicitante,
        operador=operador,
        concepto="Compra de insumos cerrada",
        huella="huella-inc8a-cerrada",
    )
    RespuestaFormulario.objects.create(
        tramite=gasto.tramite_base,
        actor=solicitante,
        revision=1,
        datos={"nota": {"etiqueta": "Nota adicional", "tipo": "texto", "valor": "Valor sintético"}},
    )
    CierreGasto.objects.create(
        solicitud=gasto,
        actor=operador,
        observacion="Cerrada para prueba visual",
        pago_version=1,
        documento_fiscal=doc_f,
        revision_fiscal=rev_f,
        documento_comprobante_pago=doc_p,
        revision_comprobante_pago=rev_p,
    )

    client = Client()
    client.force_login(operador)
    resp = client.get(reverse("gastos:detalle", kwargs={"pk": gasto.pk}))
    assert resp.status_code == 200
    html = resp.content.decode()

    assert '<span class="status-pill status-neutral">Cerrada</span>' in html
    assert "sd-pill-purple" not in html
    assert "drawer.js" not in html
    assert "Montserrat" not in html
    assert "gastos.presentar" not in html
    assert html.count("Volver al listado") == 1
    assert 'class="page-back' in html

    idx_detalle = html.index('class="solicitud-detalle"')
    idx_respuestas = html.index("Datos del formulario configurable e historial")
    idx_aside = html.index('<aside class="sd-side">')
    assert idx_detalle < idx_respuestas < idx_aside


def test_detalle_gasto_visor_documentos_y_privacidad_titular(create_actor: Any) -> None:
    """Documentos en detalle ofrece Ver archivo solo con documentos.recuperar_contenido."""
    solicitante, _ = create_actor("sol_visor_inc8a", ["gastos.presentar"])
    for grupo in ("demo_documentos_aporte", "demo_documentos_metadatos"):
        solicitante.groups.add(Group.objects.get_or_create(name=grupo)[0])
    operador, _ = create_actor("op_visor_inc8a", ["gastos.decidir"])
    for grupo in ("demo_documentos_metadatos", "demo_documentos_descarga"):
        operador.groups.add(Group.objects.get_or_create(name=grupo)[0])

    gasto = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Gasto sin pago con documento",
        estado=EstadoSolicitud.PRESENTADA,
    )
    actor_sol = actor_para_usuario(solicitante)
    assert actor_sol is not None
    incorporar(
        actor=actor_sol,
        referencia=f"gastos:{gasto.pk}",
        archivo=_pdf_sintetico("presupuesto-inc8a.pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )

    client = Client()
    client.force_login(operador)
    html_op = client.get(reverse("gastos:detalle", kwargs={"pk": gasto.pk})).content.decode()
    assert "data-visor-doc-trigger" in html_op
    assert 'id="visor-documento-dialogo"' in html_op
    assert "visor_documentos.js" in html_op

    client.force_login(solicitante)
    html_sol = client.get(reverse("gastos:detalle", kwargs={"pk": gasto.pk})).content.decode()
    assert "data-visor-doc-trigger" not in html_sol
    assert 'id="visor-documento-dialogo"' not in html_sol


def test_corregir_y_cerrar_conservan_navegacion_sidebar(create_actor: Any) -> None:
    """Regresión Inc 8A: /corregir/ y /cerrar/ pasan actor y renderizan la barra lateral."""
    solicitante, _ = create_actor("sol_nav_inc8a", ["gastos.presentar"])
    operador, _ = create_actor("op_nav_inc8a", ["gastos.decidir"])
    for grupo in ("demo_gastos_cierre", "demo_documentos_metadatos"):
        operador.groups.add(Group.objects.get_or_create(name=grupo)[0])

    observada = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Observada para corregir",
        estado=EstadoSolicitud.OBSERVADA,
    )
    client = Client()
    client.force_login(solicitante)
    resp_corregir = client.get(reverse("gastos:corregir", kwargs={"pk": observada.pk}))
    assert resp_corregir.status_code == 200
    assert resp_corregir.context["actor"] is not None
    html_corregir = resp_corregir.content.decode()
    assert 'id="app-nav"' in html_corregir
    assert 'class="page-back' in html_corregir
    assert "(Opcional)" in html_corregir

    pagada, *_ = _preparar_gasto_listo_para_cierre(
        solicitante=solicitante,
        operador=operador,
        concepto="Pagada para cerrar",
        huella="huella-inc8a-cerrar",
    )
    client.force_login(operador)
    resp_cerrar = client.get(reverse("gastos:cerrar", kwargs={"pk": pagada.pk}))
    assert resp_cerrar.status_code == 200
    assert resp_cerrar.context["actor"] is not None
    html_cerrar = resp_cerrar.content.decode()
    assert 'id="app-nav"' in html_cerrar
    assert 'class="page-back' in html_cerrar
    assert "(Opcional)" in html_cerrar


def test_presentar_errores_enfocables_opcional_y_sentence_case(create_actor: Any) -> None:
    """GET y POST inválido en /gastos/presentar/ usan (Opcional), foco y sentence case."""
    solicitante, _ = create_actor("sol_pres_inc8a", ["gastos.presentar"])
    client = Client()
    client.force_login(solicitante)

    resp_get = client.get(reverse("gastos:presentar"))
    assert resp_get.status_code == 200
    html_get = resp_get.content.decode()
    assert 'class="page-back' in html_get
    assert "(Opcional)" in html_get
    assert "Enviar solicitud" in html_get
    assert "Enviar Solicitud" not in html_get
    assert "ns-req" not in html_get

    resp_post = client.post(
        reverse("gastos:presentar"), {"tipo_flujo": TipoFlujoGasto.COMPRA_DIRECTA}
    )
    assert resp_post.status_code == 200
    html_post = resp_post.content.decode()
    assert 'id="ns-error-summary"' in html_post
    assert "data-auto-focus-error" in html_post
    assert 'tabindex="-1"' in html_post
    assert "foco_errores.js" in html_post


def test_datos_transferencia_atp_y_documento_form_limpios(create_actor: Any) -> None:
    """Auxiliares usan h1, .page-back, <dl> válido en ATP y sin jerga C03 ni help_text duplicado."""
    solicitante, _ = create_actor("sol_aux_inc8a", ["gastos.presentar"])
    solicitante.groups.add(Group.objects.get_or_create(name="demo_documentos_aporte")[0])
    operador, _ = create_actor("op_aux_inc8a", ["gastos.decidir"])
    for grupo in ("demo_gastos_pago", "demo_documentos_aporte", "demo_documentos_metadatos"):
        operador.groups.add(Group.objects.get_or_create(name=grupo)[0])

    gasto_sin_pago = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Auxiliares Inc 8A sin pago",
        estado=EstadoSolicitud.PRESENTADA,
    )
    gasto = crear_gasto_sintetico(
        solicitante=solicitante,
        concepto="Auxiliares Inc 8A",
        estado=EstadoSolicitud.ACEPTADA,
    )
    PagoExterno.objects.create(
        solicitud=gasto,
        monto_bruto=Decimal("1000.00"),
        monto_retencion_atp=Decimal("35.00"),
        importe=Decimal("965.00"),
        referencia_documental="FAC-INC8A-ATP",
        fecha_pago=date(2026, 11, 15),
        huella_idempotencia="huella-inc8a-atp",
    )

    client = Client()
    client.force_login(solicitante)
    url_tr = reverse("gastos:datos-transferencia", kwargs={"pk": gasto_sin_pago.pk})
    html_tr = client.get(url_tr).content.decode()
    assert "<h1>" in html_tr
    assert 'class="page-back' in html_tr
    assert "C03" not in html_tr
    assert "ns-req" not in html_tr

    html_doc = client.get(
        reverse("gastos:documentos", kwargs={"pk": gasto_sin_pago.pk})
    ).content.decode()
    assert "— PS Cooperadora" in html_doc
    assert "<h1>" in html_doc
    assert 'class="page-back' in html_doc
    assert html_doc.count("PDF, JPG o PNG") == 1
    assert html_doc.count('class="sd-field-help"') <= 1

    client.force_login(operador)
    html_atp = client.get(reverse("gastos:pago_atp", kwargs={"pk": gasto.pk})).content.decode()
    assert '<dl class="kv-list rp-summary-list">' in html_atp
    assert "$ 1.000,00" in html_atp
    assert "$ 35,00" in html_atp
    assert 'class="page-back' in html_atp
