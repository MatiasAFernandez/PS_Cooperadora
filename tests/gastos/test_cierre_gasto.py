"""Pruebas focalizadas para seguimiento documental y cierre explícito de gasto (#136)."""

from datetime import date
from decimal import Decimal
from threading import Barrier, Thread
from typing import Any

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connections
from django.test import Client
from django.urls import reverse

from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento, RevisionDocumento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.models import CierreGasto, EstadoSolicitud, TipoFlujoGasto
from gastos.payments import (
    PaymentConflictError,
    incorporar_constancia_atp_posterior,
    rectificar_pago_externo,
    registrar_pago_externo,
)
from gastos.reports import obtener_pendientes_actuales_gastos
from gastos.services import (
    ConcurrencyConflictError,
    ExpenseNotFoundError,
    ExpensePermissionDeniedError,
    InvalidTransitionError,
    cerrar_solicitud_gasto,
    decide_expense,
    evaluar_requisitos_cierre,
    puede_cerrar_solicitud,
    verificar_deuda_documental_solicitante,
)
from identidad.services import Actor
from tests.soporte_gastos import crear_gasto_sintetico

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _pdf(nombre: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(nombre, PDF_BYTES, content_type="application/pdf")


def _actor(user: Any, caps: set[str]) -> Actor:
    return Actor(subject_id=user.pk, capabilities=frozenset(caps))


def _client_como(user: Any, caps: list[str] | set[str]) -> Client:
    from identidad.services import GROUP_CAPABILITIES

    cap_set = set(caps)
    for group_name, group_caps in GROUP_CAPABILITIES.items():
        if group_caps <= cap_set and not group_name.startswith("local_"):
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)
    client = Client()
    client.force_login(user)
    return client


def _actor_doc_full(user: Any) -> Actor:
    return _actor(
        user,
        {
            "gastos.consultar_todas",
            "gastos.decidir",
            "gastos.registrar_pago",
            "gastos.cerrar",
            "documentos.incorporar",
            "documentos.consultar_metadatos",
            "documentos.ver_metadatos",
            "documentos.revisar",
        },
    )


@pytest.mark.django_db(transaction=True)
def test_precondiciones_cierre_negativos_presupuesto_ticket_revisiones_y_atp(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_full = _actor_doc_full(user_o)
    actor_a = _actor(
        user_a,
        {"gastos.presentar", "gastos.consultar_propias", "documentos.incorporar"},
    )

    gasto = crear_gasto_sintetico(
        concepto="Insumos de laboratorio",
        monto_estimado=Decimal("5000.00"),
        unidad_requirente="Química",
        solicitante=user_a,
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
    )
    decide_expense(
        actor=actor_full,
        solicitud_id=gasto.pk,
        action="aceptar",
        expected_version=0,
        motivo="",
    )
    gasto.refresh_from_db()

    # 1. Sin pago registrado
    ev = evaluar_requisitos_cierre(gasto)
    assert ev.puede_cerrar is False
    assert "pago_faltante" in [p.codigo for p in ev.pendientes]
    with pytest.raises(InvalidTransitionError):
        cerrar_solicitud_gasto(
            actor=actor_full,
            solicitud_id=gasto.pk,
            expected_version=gasto.version,
        )

    # 2. Presupuesto proforma (incluso ACEPTADO) + pago registrado -> nunca habilita cierre
    presupuesto = incorporar(
        actor=actor_a,
        referencia=f"gastos:{gasto.pk}",
        archivo=_pdf("presupuesto.pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    revisar(
        actor=actor_full,
        documento_id=presupuesto.pk,
        resultado=RevisionDocumento.Resultado.ACEPTADO,
        motivo="",
        revision_esperada=0,
    )
    pago = registrar_pago_externo(
        actor=actor_full,
        solicitud_id=gasto.pk,
        monto_bruto=Decimal("5000.00"),
        monto_retencion_atp=Decimal("100.00"),
        fecha_pago=date(2026, 11, 15),
        referencia_externa="OP-100",
        referencia_documental=str(presupuesto.referencia_version),
        comprobante_bancario=_pdf("banco.pdf"),
        incorporar_atp_despues=True,
        document_provider=ProveedorDocumentalGastos(),
    )

    # Ticket no fiscal tampoco satisface factura definitiva
    ticket = incorporar(
        actor=actor_a,
        referencia=f"gastos:{gasto.pk}",
        archivo=_pdf("ticket.pdf"),
        tipo=Documento.Tipo.TICKET_NO_FISCAL,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    revisar(
        actor=actor_full,
        documento_id=ticket.pk,
        resultado=RevisionDocumento.Resultado.ACEPTADO,
        motivo="",
        revision_esperada=0,
    )

    ev = evaluar_requisitos_cierre(gasto)
    codigos = {p.codigo for p in ev.pendientes}
    assert ev.puede_cerrar is False
    assert "factura_faltante" in codigos
    assert "comprobante_banco_sin_revision" in codigos
    assert "constancia_atp_faltante" in codigos

    # 3. Factura definitiva incorporada pero pendiente / observada / rechazada
    factura = incorporar(
        actor=actor_a,
        referencia=f"gastos:{gasto.pk}",
        archivo=_pdf("factura.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    assert "factura_sin_revision" in {p.codigo for p in evaluar_requisitos_cierre(gasto).pendientes}

    rev_obs = revisar(
        actor=actor_full,
        documento_id=factura.pk,
        resultado=RevisionDocumento.Resultado.OBSERVADO,
        motivo="Falta CUIT legible",
        revision_esperada=0,
    )
    assert "factura_observada" in {p.codigo for p in evaluar_requisitos_cierre(gasto).pendientes}

    revisar(
        actor=actor_full,
        documento_id=factura.pk,
        resultado=RevisionDocumento.Resultado.RECHAZADO,
        motivo="Comprobante inválido",
        revision_esperada=rev_obs.pk,
    )
    assert "factura_rechazada" in {p.codigo for p in evaluar_requisitos_cierre(gasto).pendientes}

    # Constancia ATP posterior sin revisar tampoco habilita
    incorporar_constancia_atp_posterior(
        actor=actor_full,
        solicitud_id=gasto.pk,
        version_esperada=pago.version,
        motivo="Adjunto retención",
        constancia_atp=_pdf("atp.pdf"),
    )
    assert "constancia_atp_sin_revision" in {
        p.codigo for p in evaluar_requisitos_cierre(gasto).pendientes
    }


@pytest.mark.django_db(transaction=True)
def test_cierre_conforme_ambos_flujos_inmutabilidad_mora_y_reportes(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_full = _actor_doc_full(user_o)
    actor_a = _actor(
        user_a,
        {"gastos.presentar", "gastos.consultar_propias", "documentos.incorporar"},
    )

    # Flujo 1: Compra directa con presupuesto inicial + factura definitiva + retención 0
    gasto_cd = crear_gasto_sintetico(
        concepto="Compra directa mobiliario",
        monto_estimado=Decimal("15000.00"),
        unidad_requirente="Biblioteca",
        solicitante=user_a,
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
    )
    decide_expense(
        actor=actor_full,
        solicitud_id=gasto_cd.pk,
        action="aceptar",
        expected_version=0,
        motivo="",
    )
    presupuesto = incorporar(
        actor=actor_a,
        referencia=f"gastos:{gasto_cd.pk}",
        archivo=_pdf("presup_cd.pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    pago_cd = registrar_pago_externo(
        actor=actor_full,
        solicitud_id=gasto_cd.pk,
        monto_bruto=Decimal("15000.00"),
        monto_retencion_atp=Decimal("0.00"),
        fecha_pago=date(2026, 10, 1),
        referencia_externa="OP-CD-1",
        referencia_documental=str(presupuesto.referencia_version),
        comprobante_bancario=_pdf("banco_cd.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )
    # Antes de factura definitiva, figura en deuda y en pendientes globales
    assert verificar_deuda_documental_solicitante(
        actor_a, fecha_referencia=date(2026, 11, 15)
    ).total_pendientes == 1
    assert obtener_pendientes_actuales_gastos()["sin_factura"]["cantidad"] >= 1

    factura_cd = incorporar(
        actor=actor_a,
        referencia=f"gastos:{gasto_cd.pk}",
        archivo=_pdf("factura_cd.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    revisar(
        actor=actor_full,
        documento_id=factura_cd.pk,
        resultado=RevisionDocumento.Resultado.ACEPTADO,
        motivo="",
        revision_esperada=0,
    )
    revisar(
        actor=actor_full,
        documento_id=pago_cd.comprobante_bancario_id,
        resultado=RevisionDocumento.Resultado.ACEPTADO,
        motivo="",
        revision_esperada=0,
    )

    gasto_cd.refresh_from_db()
    ev_cd = evaluar_requisitos_cierre(gasto_cd)
    assert ev_cd.puede_cerrar is True
    cierre_cd = cerrar_solicitud_gasto(
        actor=actor_full,
        solicitud_id=gasto_cd.pk,
        expected_version=gasto_cd.version,
        huella_cierre=ev_cd.huella_cierre,
        observacion="Cierre compra directa verificado",
    )
    gasto_cd.refresh_from_db()
    assert gasto_cd.estado == EstadoSolicitud.ACEPTADA
    assert gasto_cd.version == 2
    assert cierre_cd.documento_fiscal_id == factura_cd.pk
    assert cierre_cd.documento_constancia_atp is None

    # Excluido de deuda documental
    assert (
        verificar_deuda_documental_solicitante(
            actor_a, fecha_referencia=date(2026, 11, 15)
        ).total_pendientes
        == 0
    )

    # Inmutabilidad de CierreGasto
    with pytest.raises(IntegrityError):
        cierre_cd.observacion = "Alterado"
        cierre_cd.save()
    with pytest.raises(IntegrityError):
        cierre_cd.delete()
    with pytest.raises(IntegrityError):
        CierreGasto.objects.filter(pk=cierre_cd.pk).update(observacion="Bulk")
    with pytest.raises(IntegrityError):
        CierreGasto.objects.filter(pk=cierre_cd.pk).delete()

    # Flujo 2: Reintegro con retención ATP > 0
    gasto_re = crear_gasto_sintetico(
        concepto="Reintegro insumos",
        monto_estimado=Decimal("8000.00"),
        unidad_requirente="Taller",
        solicitante=user_a,
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
    )
    decide_expense(
        actor=actor_full,
        solicitud_id=gasto_re.pk,
        action="aceptar",
        expected_version=0,
        motivo="",
    )
    factura_re = incorporar(
        actor=actor_a,
        referencia=f"gastos:{gasto_re.pk}",
        archivo=_pdf("factura_re.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    pago_re = registrar_pago_externo(
        actor=actor_full,
        solicitud_id=gasto_re.pk,
        monto_bruto=Decimal("8000.00"),
        monto_retencion_atp=Decimal("240.00"),
        fecha_pago=date(2026, 11, 15),
        referencia_externa="OP-RE-1",
        referencia_documental=str(factura_re.referencia_version),
        comprobante_bancario=_pdf("banco_re.pdf"),
        constancia_atp=_pdf("atp_re.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )
    for doc_id in (factura_re.pk, pago_re.comprobante_bancario_id, pago_re.constancia_atp_id):
        revisar(
            actor=actor_full,
            documento_id=doc_id,
            resultado=RevisionDocumento.Resultado.ACEPTADO,
            motivo="",
            revision_esperada=0,
        )
    gasto_re.refresh_from_db()
    cierre_re = cerrar_solicitud_gasto(
        actor=actor_full,
        solicitud_id=gasto_re.pk,
        expected_version=gasto_re.version,
    )
    assert cierre_re.documento_constancia_atp_id == pago_re.constancia_atp_id


@pytest.mark.django_db(transaction=True)
def test_permisos_metadatos_vistas_historial_privado_y_mutaciones_posteriores(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_b = accounts["demo_b"]
    user_o = accounts["demo_o"]
    actor_full = _actor_doc_full(user_o)
    actor_a = _actor(
        user_a,
        {"gastos.presentar", "gastos.consultar_propias", "documentos.incorporar"},
    )

    gasto = crear_gasto_sintetico(
        concepto="Equipamiento red",
        monto_estimado=Decimal("12000.00"),
        unidad_requirente="Redes",
        solicitante=user_a,
        tipo_flujo=TipoFlujoGasto.REINTEGRO,
    )
    decide_expense(
        actor=actor_full,
        solicitud_id=gasto.pk,
        action="aceptar",
        expected_version=0,
        motivo="",
    )
    factura = incorporar(
        actor=actor_a,
        referencia=f"gastos:{gasto.pk}",
        archivo=_pdf("factura_red.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    pago = registrar_pago_externo(
        actor=actor_full,
        solicitud_id=gasto.pk,
        monto_bruto=Decimal("12000.00"),
        monto_retencion_atp=Decimal("0.00"),
        fecha_pago=date(2026, 11, 15),
        referencia_externa="OP-RED-1",
        referencia_documental=str(factura.referencia_version),
        comprobante_bancario=_pdf("banco_red.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )

    # Con pendientes, GET /cerrar/ redirige a detalle
    client_o_full = _client_como(
        user_o,
        [
            "gastos.consultar_todas",
            "gastos.cerrar",
            "documentos.consultar_metadatos",
            "documentos.ver_metadatos",
        ],
    )
    resp_get_pend = client_o_full.get(reverse("gastos:cerrar", kwargs={"pk": gasto.pk}))
    assert resp_get_pend.status_code == 302

    # Aceptar ambos documentos
    revisar(
        actor=actor_full,
        documento_id=factura.pk,
        resultado=RevisionDocumento.Resultado.ACEPTADO,
        motivo="",
        revision_esperada=0,
    )
    revisar(
        actor=actor_full,
        documento_id=pago.comprobante_bancario_id,
        resultado=RevisionDocumento.Resultado.ACEPTADO,
        motivo="",
        revision_esperada=0,
    )
    gasto.refresh_from_db()

    # 404 usuario sin visibilidad, 403 si falta gastos.cerrar o metadatos
    with pytest.raises(ExpenseNotFoundError):
        cerrar_solicitud_gasto(
            actor=_actor(user_b, {"gastos.cerrar", "documentos.consultar_metadatos"}),
            solicitud_id=gasto.pk,
            expected_version=gasto.version,
        )
    with pytest.raises(ExpensePermissionDeniedError):
        cerrar_solicitud_gasto(
            actor=_actor(user_o, {"gastos.consultar_todas", "gastos.cerrar"}),
            solicitud_id=gasto.pk,
            expected_version=gasto.version,
        )
    with pytest.raises(ExpensePermissionDeniedError):
        cerrar_solicitud_gasto(
            actor=_actor(user_o, {"gastos.consultar_todas", "documentos.consultar_metadatos"}),
            solicitud_id=gasto.pk,
            expected_version=gasto.version,
        )
    assert puede_cerrar_solicitud(
        _actor(user_o, {"gastos.consultar_todas", "gastos.cerrar"}), gasto
    ) is False

    # GET elegible devuelve 200 con clases scoped efectivas e importes es-AR
    resp_get_ok = client_o_full.get(reverse("gastos:cerrar", kwargs={"pk": gasto.pk}))
    assert resp_get_ok.status_code == 200
    html_get_ok = resp_get_ok.content.decode("utf-8")
    assert 'class="solicitud-detalle nueva-solicitud"' in html_get_ok
    assert "Bruto $ 12.000,00 · Retención ATP $ 0,00 · Neto $ 12.000,00" in html_get_ok

    # POST sin huella_cierre devuelve 400 con mensaje visible y observación conservada
    resp_sin_huella = client_o_full.post(
        reverse("gastos:cerrar", kwargs={"pk": gasto.pk}),
        data={
            "version": str(gasto.version),
            "huella_cierre": "",
            "observacion": "Nota sin huella conservada",
        },
    )
    assert resp_sin_huella.status_code == 400
    html_sin_huella = resp_sin_huella.content.decode("utf-8")
    assert "Falta la huella de verificación del cierre" in html_sin_huella
    assert "Nota sin huella conservada" in html_sin_huella
    assert not CierreGasto.objects.filter(solicitud=gasto).exists()

    # POST con huella obsoleta devuelve 409 conservando observación
    resp_409 = client_o_full.post(
        reverse("gastos:cerrar", kwargs={"pk": gasto.pk}),
        data={
            "version": str(gasto.version),
            "huella_cierre": "huella-invalida",
            "observacion": "Nota que no debe perderse",
        },
    )
    assert resp_409.status_code == 409
    assert "Nota que no debe perderse" in resp_409.content.decode("utf-8")

    # POST válido cierra
    ev = evaluar_requisitos_cierre(gasto)
    resp_ok = client_o_full.post(
        reverse("gastos:cerrar", kwargs={"pk": gasto.pk}),
        data={
            "version": str(gasto.version),
            "huella_cierre": ev.huella_cierre,
            "observacion": "Conforme para archivo",
        },
    )
    assert resp_ok.status_code == 302

    # El solicitante conserva el resumen del cierre.
    client_a = _client_como(user_a, ["gastos.consultar_propias", "gastos.presentar"])
    resp_det_a = client_a.get(reverse("gastos:detalle", kwargs={"pk": gasto.pk}))
    html_det_a = resp_det_a.content.decode("utf-8")
    assert "Cerrada" in html_det_a
    assert "Cierre del trámite" in html_det_a
    assert "Documentación obligatoria verificada y aceptada." in html_det_a
    assert "banco_red.pdf" not in html_det_a

    user_l = accounts["demo_l"]
    client_l = _client_como(user_l, ["gastos.consultar_todas", "gastos.consultar_adjuntos"])
    resp_det_l = client_l.get(reverse("gastos:detalle", kwargs={"pk": gasto.pk}))
    html_det_l = resp_det_l.content.decode("utf-8")
    assert "Cerrada" in html_det_l
    assert "Cierre del trámite" in html_det_l
    assert "banco_red.pdf" not in html_det_l
    assert "factura_red.pdf" in html_det_l
    assert reverse("documentos:archivo", args=[factura.pk]) in html_det_l
    assert "/revision/" not in html_det_l

    # Bandeja y panel de vista rápida muestran Pagada + Cerrada
    resp_lista_a = client_a.get(reverse("gastos:lista"))
    html_lista_a = resp_lista_a.content.decode("utf-8")
    assert "Pagada" in html_lista_a
    assert "Cerrada" in html_lista_a

    client_o_panel = _client_como(
        user_o,
        ["gastos.consultar_todas", "gastos.decidir", "gastos.registrar_pago"],
    )
    resp_lista_o = client_o_panel.get(reverse("gastos:lista"))
    html_lista_o = resp_lista_o.content.decode("utf-8")
    assert "Pagada" in html_lista_o
    assert "Cerrada" in html_lista_o

    gasto.refresh_from_db()
    resp_reversion = client_o_panel.post(
        reverse("gastos:decidir", args=[gasto.pk]),
        data={
            "action": "revertir",
            "version": gasto.version,
            "motivo": "Motivo conservado tras el cierre",
        },
    )
    assert resp_reversion.status_code == 409
    contenido_reversion = resp_reversion.content.decode()
    assert "El trámite está cerrado" in contenido_reversion
    assert "Motivo conservado tras el cierre" in contenido_reversion
    assert "Confirmar reversión" not in contenido_reversion

    # Mutaciones posteriores bloqueadas en Gastos y en rutas directas de documentos
    with pytest.raises(PaymentConflictError):
        rectificar_pago_externo(
            actor=actor_full,
            solicitud_id=gasto.pk,
            version_esperada=pago.version,
            motivo="Cambio tardío",
            fecha_pago=date(2026, 11, 15),
            monto_bruto=Decimal("12000.00"),
            monto_retencion_atp=Decimal("0.00"),
        )
    with pytest.raises(PaymentConflictError):
        incorporar_constancia_atp_posterior(
            actor=actor_full,
            solicitud_id=gasto.pk,
            version_esperada=pago.version,
            motivo="ATP tardía",
            constancia_atp=_pdf("atp_tardia.pdf"),
        )

    client_docs = _client_como(
        user_o,
        [
            "gastos.consultar_todas",
            "documentos.incorporar",
            "documentos.consultar_metadatos",
            "documentos.ver_metadatos",
            "documentos.revisar",
        ],
    )
    assert client_docs.get(reverse("gastos:documentos", kwargs={"pk": gasto.pk})).status_code == 302
    assert (
        client_docs.post(
            reverse("gastos:documentos", kwargs={"pk": gasto.pk}),
            data={},
        ).status_code
        == 409
    )

    with pytest.raises(PermissionDenied):
        incorporar(
            actor=actor_a,
            referencia=f"gastos:{gasto.pk}",
            archivo=_pdf("tardio.pdf"),
            tipo=Documento.Tipo.FACTURA_PROVEEDOR,
            procedencia=Documento.Procedencia.SOLICITANTE,
        )
    with pytest.raises(PermissionDenied):
        revisar(
            actor=actor_full,
            documento_id=factura.pk,
            resultado=RevisionDocumento.Resultado.OBSERVADO,
            motivo="Revisión tardía",
            revision_esperada=RevisionDocumento.objects.filter(documento=factura).order_by("-id").first().pk,
        )
    assert (
        client_docs.post(
            reverse("documentos:revision", kwargs={"documento_id": factura.pk}),
            data={"resultado": "OBSERVADO", "motivo": "Tardío", "revision_esperada": "1"},
        ).status_code
        == 403
    )


@pytest.mark.django_db(transaction=True)
def test_concurrencia_real_dos_cierres_y_cierre_vs_revision_postgresql(
    demo_accounts: tuple[dict[str, Any], str],
) -> None:
    accounts, _ = demo_accounts
    user_a = accounts["demo_a"]
    user_o = accounts["demo_o"]
    actor_full = _actor_doc_full(user_o)
    actor_a = _actor(
        user_a,
        {"gastos.presentar", "gastos.consultar_propias", "documentos.incorporar"},
    )

    def _preparar_gasto_listo(sufijo: str) -> tuple[Any, Documento, RevisionDocumento, str]:
        gasto = crear_gasto_sintetico(
            concepto=f"Concurrencia cierre {sufijo}",
            monto_estimado=Decimal("9000.00"),
            unidad_requirente="Laboratorio",
            solicitante=user_a,
            tipo_flujo=TipoFlujoGasto.REINTEGRO,
        )
        decide_expense(
            actor=actor_full,
            solicitud_id=gasto.pk,
            action="aceptar",
            expected_version=0,
            motivo="",
        )
        factura = incorporar(
            actor=actor_a,
            referencia=f"gastos:{gasto.pk}",
            archivo=_pdf(f"f_{sufijo}.pdf"),
            tipo=Documento.Tipo.FACTURA_PROVEEDOR,
            procedencia=Documento.Procedencia.SOLICITANTE,
        )
        pago = registrar_pago_externo(
            actor=actor_full,
            solicitud_id=gasto.pk,
            monto_bruto=Decimal("9000.00"),
            monto_retencion_atp=Decimal("0.00"),
            fecha_pago=date(2026, 11, 15),
            referencia_externa=f"OP-{sufijo}",
            referencia_documental=str(factura.referencia_version),
            comprobante_bancario=_pdf(f"b_{sufijo}.pdf"),
            document_provider=ProveedorDocumentalGastos(),
        )
        rev_f = revisar(
            actor=actor_full,
            documento_id=factura.pk,
            resultado=RevisionDocumento.Resultado.ACEPTADO,
            motivo="",
            revision_esperada=0,
        )
        revisar(
            actor=actor_full,
            documento_id=pago.comprobante_bancario_id,
            resultado=RevisionDocumento.Resultado.ACEPTADO,
            motivo="",
            revision_esperada=0,
        )
        gasto.refresh_from_db()
        ev = evaluar_requisitos_cierre(gasto)
        assert ev.puede_cerrar is True
        return gasto, factura, rev_f, ev.huella_cierre

    # Escenario 1: dos cierres y una reversión simultáneos sobre un gasto pagado.
    gasto_1, _, _, huella_1 = _preparar_gasto_listo("c1")
    _client_como(
        user_o,
        [
            "gastos.consultar_todas",
            "gastos.cerrar",
            "documentos.consultar_metadatos",
            "documentos.ver_metadatos",
        ],
    )
    url_cerrar = reverse("gastos:cerrar", args=[gasto_1.pk])
    url_decidir = reverse("gastos:decidir", args=[gasto_1.pk])
    datos_cierre = {"version": gasto_1.version, "huella_cierre": huella_1}
    datos_reversion = {
        "action": "revertir",
        "version": gasto_1.version,
        "motivo": "Corrección concurrente",
    }
    solicitudes_http = (
        (url_cerrar, datos_cierre),
        (url_cerrar, datos_cierre),
        (url_decidir, datos_reversion),
    )
    barrier_1 = Barrier(len(solicitudes_http))
    results_1: list[int | Exception | None] = [None] * len(solicitudes_http)

    def worker_post(idx: int, url: str, datos: dict[str, Any]) -> None:
        connections.close_all()
        try:
            client = Client()
            client.force_login(user_o)
            barrier_1.wait(timeout=10)
            resp = client.post(url, datos)
            results_1[idx] = resp.status_code
        except Exception as exc:
            results_1[idx] = exc
        finally:
            connections.close_all()

    hilos = [
        Thread(target=worker_post, args=(indice, url, datos))
        for indice, (url, datos) in enumerate(solicitudes_http)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=15)
        assert not hilo.is_alive()
    assert sorted(r for r in results_1[:2] if isinstance(r, int)) == [302, 409], results_1
    assert results_1[2] == 409, results_1
    gasto_1.refresh_from_db()
    assert gasto_1.version == 2
    assert gasto_1.estado == EstadoSolicitud.ACEPTADA
    assert gasto_1.decisiones.count() == 1
    assert CierreGasto.objects.filter(solicitud=gasto_1).count() == 1

    # Escenario 2: cierre vs revisión concurrente sobre la factura
    gasto_2, factura_2, rev_f2, huella_2 = _preparar_gasto_listo("c2")
    barrier_2 = Barrier(2)
    res_cierre: list[str] = []
    res_rev: list[str] = []

    def worker_close_srv() -> None:
        connections.close_all()
        try:
            barrier_2.wait(timeout=10)
            cerrar_solicitud_gasto(
                actor=actor_full,
                solicitud_id=gasto_2.pk,
                expected_version=gasto_2.version,
                huella_cierre=huella_2,
            )
            res_cierre.append("ok")
        except (ConcurrencyConflictError, InvalidTransitionError):
            res_cierre.append("conflict")
        finally:
            connections.close_all()

    def worker_rev_srv() -> None:
        connections.close_all()
        try:
            barrier_2.wait(timeout=10)
            revisar(
                actor=actor_full,
                documento_id=factura_2.pk,
                resultado=RevisionDocumento.Resultado.OBSERVADO,
                motivo="Observación concurrente",
                revision_esperada=rev_f2.pk,
            )
            res_rev.append("ok")
        except PermissionDenied:
            res_rev.append("blocked")
        finally:
            connections.close_all()

    tc = Thread(target=worker_close_srv)
    tr = Thread(target=worker_rev_srv)
    tc.start()
    tr.start()
    tc.join(timeout=15)
    tr.join(timeout=15)

    assert len(res_cierre) == 1 and len(res_rev) == 1
    assert (res_cierre[0] == "ok" and res_rev[0] == "blocked") or (
        res_cierre[0] == "conflict" and res_rev[0] == "ok"
    )
