# ruff: noqa
"""Prepara fixtures sintéticas completas para la verificación E2E del Incremento I3."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cooperadora.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from reportlab.pdfgen.canvas import Canvas

from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento
from documentos.revision import revisar
from documentos.services import incorporar
from gastos.models import (
    CentroCosto,
    PagoExterno,
    ParametroOperativo,
    RevisionDatosTransferencia,
    SolicitudGasto,
    TipoFlujoGasto,
)
from gastos.services import (
    crear_solicitud_gasto,
    decide_expense,
    CLAVE_PARAMETRO_ATP_BASE,
    CLAVE_PARAMETRO_ATP_ALICUOTA,
)
from gastos.payments import registrar_pago_externo
from identidad.services import GROUP_CAPABILITIES, Actor

User = get_user_model()


def run(*, visual=False):
    if "--reset" in sys.argv:
        print("--- Reiniciando base de datos (--reset) ---")
        from django.core.management import call_command
        call_command("flush", interactive=False)

    print("--- 1. Preparando Grupos y Usuarios Demo ---")
    groups = {
        name: Group.objects.get_or_create(name=name)[0]
        for name in (
            "demo_solicitante",
            "demo_operadora",
            "demo_lectura",
            "demo_gastos_pago",
            "demo_documentos_aporte",
            "demo_documentos_revision",
            "demo_documentos_metadatos",
            *(("demo_documentos_descarga",) if visual else ()),
        )
    }

    grupos_solicitante_visual = (
        ["demo_documentos_metadatos", "demo_documentos_descarga"] if visual else []
    )
    accounts = {}
    for username, grp_list in [
        ("demo_a", ["demo_solicitante", "demo_documentos_aporte", *grupos_solicitante_visual]),
        ("demo_b", ["demo_solicitante", "demo_documentos_aporte", *grupos_solicitante_visual]),
        (
            "demo_o",
            [
                "demo_operadora",
                "demo_gastos_pago",
                "demo_documentos_aporte",
                "demo_documentos_revision",
                "demo_documentos_metadatos",
                *(["demo_documentos_descarga"] if visual else []),
            ],
        ),
        ("demo_l", ["demo_lectura"]),
    ]:
        u, created = User.objects.get_or_create(username=username)
        u.set_password("demo1234")
        u.email = f"{username}@example.invalid" if visual else f"{username}@frre.utn.edu.ar"
        if visual:
            u.first_name, u.last_name = {
                "demo_a": ("Lucía", "Ejemplo"),
                "demo_b": ("Tomás", "Muestra"),
                "demo_o": ("Cooperadora", "Demo"),
                "demo_l": ("Consulta", "Demo"),
            }[username]
        u.is_active = True
        u.save()
        u.groups.clear()
        for g_name in grp_list:
            u.groups.add(groups[g_name])
        accounts[username] = u
        print(f"  Usuario {username} configurado.")

    actor_a = Actor(
        accounts["demo_a"].pk,
        frozenset().union(
            GROUP_CAPABILITIES["demo_solicitante"],
            GROUP_CAPABILITIES["demo_documentos_aporte"],
        ),
    )
    actor_b = Actor(
        accounts["demo_b"].pk,
        frozenset().union(
            GROUP_CAPABILITIES["demo_solicitante"],
            GROUP_CAPABILITIES["demo_documentos_aporte"],
        ),
    )
    actor_o = Actor(
        accounts["demo_o"].pk,
        frozenset().union(
            GROUP_CAPABILITIES["demo_operadora"],
            GROUP_CAPABILITIES["demo_gastos_pago"],
            GROUP_CAPABILITIES["demo_documentos_aporte"],
            GROUP_CAPABILITIES["demo_documentos_revision"],
            GROUP_CAPABILITIES["demo_documentos_metadatos"],
        ),
    )

    print("--- 2. Centros de Costo y Parámetros Operativos ---")
    c_ia, _ = CentroCosto.objects.update_or_create(
        codigo="lab-ia",
        defaults={"nombre": "Laboratorio de Inteligencia Artificial", "activo": True},
    )
    c_quim, _ = CentroCosto.objects.update_or_create(
        codigo="lab-quimica",
        defaults={"nombre": "Laboratorio de Química Aplicada", "activo": True},
    )
    c_inactivo, _ = CentroCosto.objects.update_or_create(
        codigo="proyecto-cerrado",
        defaults={"nombre": "Proyecto Cerrado 2024", "activo": False},
    )

    ParametroOperativo.objects.update_or_create(
        clave=CLAVE_PARAMETRO_ATP_BASE,
        defaults={"valor_decimal": Decimal("90000.00"), "descripcion": "Base imponible ATP"},
    )
    ParametroOperativo.objects.update_or_create(
        clave=CLAVE_PARAMETRO_ATP_ALICUOTA,
        defaults={"valor_decimal": Decimal("0.035"), "descripcion": "Alícuota general ATP"},
    )

    print("--- 3. Creando Solicitudes Representativas ---")

    if SolicitudGasto.objects.filter(concepto="Adquisición Insumos GPU NVIDIA").exists():
        sol_pago = SolicitudGasto.objects.filter(concepto="Adquisición Insumos GPU NVIDIA").first()
        sol_pagada = SolicitudGasto.objects.filter(concepto="Reactivos de Laboratorio y Cristalería").first()
        print("--- Las fixtures de prueba ya se encuentran inicializadas en la base de datos! ---")
        if sol_pago:
            print(f"--- Solicitud pendiente de pago disponible con ID: {sol_pago.pk} ---")
        if sol_pagada:
            print(f"--- Solicitud pagada disponible con ID: {sol_pagada.pk} ---")
        print("--- Para reiniciar desde cero, podés ejecutar: python scripts/prepare_e2e_i3_fixtures.py --reset ---")
        return

    # 3.1. Solicitud 1: Pendiente de pago para Issue #91 (Compra directa aceptada)
    sol_pago = crear_solicitud_gasto(
        actor=actor_a,
        concepto="Adquisición Insumos GPU NVIDIA",
        monto_estimado=Decimal("150000.00"),
        unidad_requirente="Laboratorio de Inteligencia Artificial",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_ia,
    )
    decide_expense(
        actor=actor_o,
        solicitud_id=sol_pago.pk,
        action="aceptar",
        expected_version=0,
        motivo="Aprobado en reunión de consejo",
    )
    RevisionDatosTransferencia.objects.create(
        solicitud=sol_pago,
        numero_revision=1,
        titular_nombre="Tech Solutions SA",
        identificacion="30-71234567-8",
        cbu_alias="0110599520000001234567",
        correo_comprobante="facturacion@example.invalid",
        centro_costo="Laboratorio de Inteligencia Artificial",
        actor=accounts["demo_a"],
    )
    presupuesto_doc = _pdf_demo("presupuesto_gpu.pdf")
    incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_pago.pk}",
        archivo=presupuesto_doc,
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia="SOLICITANTE",
    )

    # 3.2. Solicitud 2: Ya pagada con retención ATP para probar Drawer y detalle
    sol_pagada = crear_solicitud_gasto(
        actor=actor_a,
        concepto="Reactivos de Laboratorio y Cristalería",
        monto_estimado=Decimal("120000.00"),
        unidad_requirente="Laboratorio de Química Aplicada",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_quim,
    )
    decide_expense(
        actor=actor_o,
        solicitud_id=sol_pagada.pk,
        action="aceptar",
        expected_version=0,
        motivo="Aprobado por partida docente",
    )
    RevisionDatosTransferencia.objects.create(
        solicitud=sol_pagada,
        numero_revision=1,
        titular_nombre="Química del Norte SRL",
        identificacion="30-65432109-1",
        cbu_alias="0070123450000009876543",
        correo_comprobante="ventas@example.invalid",
        centro_costo="Laboratorio de Química Aplicada",
        actor=accounts["demo_a"],
    )
    pago_doc = _pdf_demo("factura_quimica.pdf")
    doc_factura = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_pagada.pk}",
        archivo=pago_doc,
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    registrar_pago_externo(
        solicitud_id=sol_pagada.pk,
        actor=actor_o,
        fecha_pago=date.today(),
        referencia_externa="TRANSF-GAL-20261103-01",
        referencia_documental=str(doc_factura.referencia_version),
        monto_bruto=Decimal("120000.00"),
        monto_retencion_atp=Decimal("4200.00"),
        referencia_atp="CONST-ATP-2026-00892",
        comprobante_bancario=_pdf_demo("comprobante_quimica.pdf"),
        constancia_atp=_pdf_demo("constancia_atp_quimica.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )

    # 3.3. Solicitud 3: Compra directa pagada con presupuesto hace 5 días (Periodo de gracia, demo_a)
    sol_gracia = crear_solicitud_gasto(
        actor=actor_a,
        concepto="Cables de Red y Patch Panels",
        monto_estimado=Decimal("45000.00"),
        unidad_requirente="Laboratorio de Inteligencia Artificial",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_ia,
    )
    decide_expense(
        actor=actor_o,
        solicitud_id=sol_gracia.pk,
        action="aceptar",
        expected_version=0,
        motivo="Aprobado",
    )
    doc_gracia = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_gracia.pk}",
        archivo=_pdf_demo("presup_red.pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia="SOLICITANTE",
    )
    registrar_pago_externo(
        solicitud_id=sol_gracia.pk,
        actor=actor_o,
        fecha_pago=date.today() - timedelta(days=5),
        referencia_externa="TRANSF-RED-20261029",
        referencia_documental=str(doc_gracia.referencia_version),
        monto_bruto=Decimal("45000.00"),
        monto_retencion_atp=Decimal("0.00"),
        comprobante_bancario=_pdf_demo("comprobante_red.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )

    if visual:
        _crear_casos_visuales(actor_a, actor_b, actor_o, c_ia, c_quim)

    # 3.4. Solicitudes 4, 5, 6: 3 compras directas pagadas hace 25 días para demo_b (Mora > 2 trámites, Bloqueo)
    for i in range(1, 4):
        sol_mora = crear_solicitud_gasto(
            actor=actor_b,
            concepto=f"Material Bibliográfico Lote #{i}",
            monto_estimado=Decimal("30000.00"),
            unidad_requirente="Departamento de Investigación",
            tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
            centro_costo=None,  # Para que además sume a 'Sin centro asignado'
        )
        decide_expense(
            actor=actor_o,
            solicitud_id=sol_mora.pk,
            action="aceptar",
            expected_version=0,
            motivo=f"Aprobado Lote {i}",
        )
        doc_mora = incorporar(
            actor=actor_b,
            referencia=f"gastos:{sol_mora.pk}",
            archivo=_pdf_demo(f"presup_mora_{i}.pdf"),
            tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
            procedencia="SOLICITANTE",
        )
        registrar_pago_externo(
            solicitud_id=sol_mora.pk,
            actor=actor_o,
            fecha_pago=date.today() - timedelta(days=25),
            referencia_externa=f"TRANSF-MORA-{i}",
            referencia_documental=str(doc_mora.referencia_version),
            monto_bruto=Decimal("30000.00"),
            monto_retencion_atp=Decimal("0.00"),
            comprobante_bancario=_pdf_demo(f"comprobante_mora_{i}.pdf"),
            document_provider=ProveedorDocumentalGastos(),
        )

    # 3.5. Movimientos Históricos en C1 y C2 para enriquecer el Reporte Cuatrimestral (Issue #94)
    # Movimiento C1 (Marzo 2026)
    sol_c1 = crear_solicitud_gasto(
        actor=actor_a,
        concepto="Microscopios Ópticos de Precisión",
        monto_estimado=Decimal("80000.00"),
        unidad_requirente="Laboratorio de Química Aplicada",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_quim,
    )
    decide_expense(actor=actor_o, solicitud_id=sol_c1.pk, action="aceptar", expected_version=0, motivo="Aprobado C1")
    doc_c1 = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_c1.pk}",
        archivo=_pdf_demo("factura_c1.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    pago_c1 = registrar_pago_externo(
        solicitud_id=sol_c1.pk,
        actor=actor_o,
        fecha_pago=date(2026, 3, 10),
        referencia_externa="TRANSF-C1-001",
        referencia_documental=str(doc_c1.referencia_version),
        monto_bruto=Decimal("80000.00"),
        monto_retencion_atp=Decimal("0.00"),
        comprobante_bancario=_pdf_demo("comprobante_c1.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )
    # Ajustar fecha de creación de la solicitud a C1
    SolicitudGasto.objects.filter(pk=sol_c1.pk).update(fecha_creacion=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc))

    # Movimiento C2 (Julio 2026)
    sol_c2 = crear_solicitud_gasto(
        actor=actor_a,
        concepto="Cluster de Cómputo Paralelo",
        monto_estimado=Decimal("200000.00"),
        unidad_requirente="Laboratorio de Inteligencia Artificial",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_ia,
    )
    decide_expense(actor=actor_o, solicitud_id=sol_c2.pk, action="aceptar", expected_version=0, motivo="Aprobado C2")
    doc_c2 = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_c2.pk}",
        archivo=_pdf_demo("factura_c2.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    pago_c2 = registrar_pago_externo(
        solicitud_id=sol_c2.pk,
        actor=actor_o,
        fecha_pago=date(2026, 7, 15),
        referencia_externa="TRANSF-C2-001",
        referencia_documental=str(doc_c2.referencia_version),
        monto_bruto=Decimal("200000.00"),
        monto_retencion_atp=Decimal("7000.00"),
        referencia_atp="CONST-ATP-C2-0045",
        comprobante_bancario=_pdf_demo("comprobante_c2.pdf"),
        constancia_atp=_pdf_demo("constancia_atp_c2.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )
    SolicitudGasto.objects.filter(pk=sol_c2.pk).update(fecha_creacion=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc))

    print(f"--- Solicitud pendiente de pago creada con ID: {sol_pago.pk} ---")
    print(f"--- Solicitud pagada creada con ID: {sol_pagada.pk} ---")

    if visual:
        # Al final para no desplazar los IDs de los casos anteriores.
        _crear_casos_i3_demo_a(accounts, actor_a, actor_o, c_ia)

    print("--- Todas las fixtures creadas exitosamente! ---")


def _crear_casos_i3_demo_a(accounts, actor_a, actor_o, c_ia):
    """Agrega cuatro expedientes I3 para demo_a sin desplazar los IDs previos."""
    cliente = Client(HTTP_HOST="localhost")
    cliente.force_login(accounts["demo_a"])

    # Caso 1: alta real con respaldo (POST /gastos/presentar/).
    concepto_alta = "I3-01 Alta real con respaldo - Sensores de robótica"
    respuesta_alta = cliente.post(
        reverse("gastos:presentar"),
        {
            "concepto": concepto_alta,
            "monto_estimado": "98765.43",
            "unidad_requirente": "Laboratorio de Inteligencia Artificial",
            "tipo_flujo": TipoFlujoGasto.COMPRA_DIRECTA,
            "centro_costo": str(c_ia.pk),
            "respaldo_archivo": _pdf_demo("respaldo_alta_real_i3.pdf"),
        },
    )
    if respuesta_alta.status_code != 302:
        raise RuntimeError(
            "El alta real con respaldo no respondió 302: "
            f"{respuesta_alta.status_code}."
        )
    sol_alta = SolicitudGasto.objects.get(concepto=concepto_alta)
    doc_alta = Documento.objects.get(
        solicitud_gasto=sol_alta,
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
    )

    # Caso 2: respaldo observado, descargable y reemplazable por su titular.
    concepto_observado = "I3-02 Respaldo observado - Notebook de taller"
    sol_observado = crear_solicitud_gasto(
        actor=actor_a,
        concepto=concepto_observado,
        monto_estimado=Decimal("78000.00"),
        unidad_requirente="Laboratorio de Inteligencia Artificial",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_ia,
    )
    doc_observado = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_observado.pk}",
        archivo=_pdf_demo("factura_notebook_observada.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    revisar(
        actor=actor_o,
        documento_id=doc_observado.pk,
        resultado="OBSERVADO",
        motivo="El importe no coincide con el presupuesto.",
        revision_esperada=0,
    )

    # Caso 3: respaldo observado y reemplazado; versión nueva pendiente y vieja conservada.
    concepto_reemplazo = "I3-03 Respaldo reemplazado - Proyector de aula"
    sol_reemplazo = crear_solicitud_gasto(
        actor=actor_a,
        concepto=concepto_reemplazo,
        monto_estimado=Decimal("64000.00"),
        unidad_requirente="Laboratorio de Inteligencia Artificial",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_ia,
    )
    doc_anterior = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_reemplazo.pk}",
        archivo=_pdf_demo("presupuesto_proyector.pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    revisar(
        actor=actor_o,
        documento_id=doc_anterior.pk,
        resultado="OBSERVADO",
        motivo="Falta el detalle del proveedor.",
        revision_esperada=0,
    )
    doc_nuevo = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_reemplazo.pk}",
        archivo=_pdf_demo("presupuesto_proyector_v2.pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia=Documento.Procedencia.SOLICITANTE,
        reemplaza_id=doc_anterior.pk,
    )
    if (
        doc_nuevo.version != 2
        or doc_nuevo.revisiones.exists()
        or not Documento.objects.filter(pk=doc_anterior.pk).exists()
    ):
        raise RuntimeError(
            "El reemplazo I3-03 no conservó la versión anterior ni dejó pendiente la nueva."
        )

    # Caso 4: compra directa con factura aceptada y pago con retención cero.
    concepto_al_dia = "I3-04 Compra directa al día - Factura y pago"
    sol_al_dia = crear_solicitud_gasto(
        actor=actor_a,
        concepto=concepto_al_dia,
        monto_estimado=Decimal("88000.00"),
        unidad_requirente="Laboratorio de Inteligencia Artificial",
        tipo_flujo=TipoFlujoGasto.COMPRA_DIRECTA,
        centro_costo=c_ia,
    )
    decide_expense(
        actor=actor_o,
        solicitud_id=sol_al_dia.pk,
        action="aceptar",
        expected_version=0,
        motivo="Compra directa aprobada para el recorrido I3.",
    )
    doc_factura = incorporar(
        actor=actor_a,
        referencia=f"gastos:{sol_al_dia.pk}",
        archivo=_pdf_demo("factura_compra_directa_i3.pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia=Documento.Procedencia.SOLICITANTE,
    )
    revisar(
        actor=actor_o,
        documento_id=doc_factura.pk,
        resultado="ACEPTADO",
        motivo="Factura conforme.",
        revision_esperada=0,
    )
    registrar_pago_externo(
        solicitud_id=sol_al_dia.pk,
        actor=actor_o,
        fecha_pago=date.today(),
        referencia_externa="TRANSF-I3-AL-DIA-01",
        referencia_documental=str(doc_factura.referencia_version),
        monto_bruto=Decimal("88000.00"),
        monto_retencion_atp=Decimal("0.00"),
        comprobante_bancario=_pdf_demo("comprobante_compra_directa_i3.pdf"),
        document_provider=ProveedorDocumentalGastos(),
    )
    respuesta_detalle = cliente.get(
        reverse("gastos:detalle", kwargs={"pk": sol_al_dia.pk})
    )
    if (
        respuesta_detalle.status_code != 200
        or "Trámite al día" not in respuesta_detalle.content.decode("utf-8")
    ):
        raise RuntimeError(
            "El expediente I3-04 no quedó apto para el chip 'Trámite al día'."
        )

    print("--- Casos I3 de demo_a (sólo con --visual) ---")
    print(
        f"  [I3-01] Alta real con respaldo (302 verificado): solicitud #{sol_alta.pk}, "
        f"documento #{doc_alta.pk}"
    )
    print(
        f"  [I3-02] Respaldo observado: solicitud #{sol_observado.pk}, "
        f"documento #{doc_observado.pk}"
    )
    print(
        f"  [I3-03] Respaldo reemplazado: solicitud #{sol_reemplazo.pk}, "
        f"versiones #{doc_anterior.pk} -> #{doc_nuevo.pk}"
    )
    print(
        f"  [I3-04] Compra directa al día (chip verificado): solicitud #{sol_al_dia.pk}, "
        f"factura #{doc_factura.pk}"
    )


def _crear_casos_visuales(actor_a, actor_b, actor_o, c_ia, c_quim):
    casos = (
        (actor_a, "Sensores y baterías recargables para los kits de robótica del turno tarde", "presentar", ""),
        (actor_a, "Reparación del proyector del aula 12", "postergar", "Revisar disponibilidad de la partida el próximo mes."),
        (actor_b, "Impresión de cartelería para la feria de ciencias", "rechazar", "El mismo gasto ya fue incluido en el pedido general de la feria."),
        (actor_a, "Insumos de limpieza para el laboratorio", "aceptar", "Adjuntar presupuesto antes de registrar el pago."),
        (actor_a, "Reintegro por instrumental para prácticas de química", "aceptar", "Se verificó el gasto presentado."),
    )
    for actor, concepto, accion, motivo in casos:
        reintegro = concepto.startswith("Reintegro")
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto=concepto,
            monto_estimado=Decimal("145800.00") if reintegro else Decimal("56750.50"),
            unidad_requirente="Laboratorios",
            tipo_flujo=TipoFlujoGasto.REINTEGRO if reintegro else TipoFlujoGasto.COMPRA_DIRECTA,
            centro_costo=c_quim if reintegro else c_ia,
        )
        if accion != "presentar":
            decide_expense(
                actor=actor_o,
                solicitud_id=solicitud.pk,
                action=accion,
                expected_version=0,
                motivo=motivo,
            )
        if reintegro:
            factura = incorporar(
                actor=actor,
                referencia=f"gastos:{solicitud.pk}",
                archivo=_pdf_demo("factura_reintegro.pdf"),
                tipo=Documento.Tipo.FACTURA_PROVEEDOR,
                procedencia="SOLICITANTE",
            )
            registrar_pago_externo(
                solicitud_id=solicitud.pk,
                actor=actor_o,
                fecha_pago=date.today(),
                referencia_externa="DEMO-REINTEGRO-01",
                referencia_documental=str(factura.referencia_version),
                monto_bruto=Decimal("145800.00"),
                monto_retencion_atp=Decimal("5103.00"),
                incorporar_atp_despues=True,
                comprobante_bancario=_pdf_demo("comprobante_reintegro.pdf"),
                document_provider=ProveedorDocumentalGastos(),
            )


def _pdf_demo(nombre):
    archivo = BytesIO()
    pdf = Canvas(archivo, pagesize=(595, 160), invariant=True)
    pdf.setTitle(nombre)
    pdf.setFont("Helvetica", 18)
    pdf.drawString(40, 90, "DOCUMENTO SINTÉTICO DE DEMOSTRACIÓN")
    pdf.drawString(40, 60, nombre)
    pdf.save()
    return SimpleUploadedFile(nombre, archivo.getvalue(), "application/pdf")


if __name__ == "__main__":
    run(visual="--visual" in sys.argv)
