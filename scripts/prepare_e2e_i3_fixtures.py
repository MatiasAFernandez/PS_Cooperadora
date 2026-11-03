# ruff: noqa
"""Prepara fixtures sintéticas completas para la verificación E2E del Incremento I3."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
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

from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento
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


def run():
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
        )
    }

    accounts = {}
    for username, grp_list in [
        ("demo_a", ["demo_solicitante", "demo_documentos_aporte"]),
        ("demo_b", ["demo_solicitante", "demo_documentos_aporte"]),
        (
            "demo_o",
            [
                "demo_operadora",
                "demo_gastos_pago",
                "demo_documentos_revision",
                "demo_documentos_metadatos",
            ],
        ),
        ("demo_l", ["demo_lectura"]),
    ]:
        u, created = User.objects.get_or_create(username=username)
        u.set_password("demo1234")
        u.email = f"{username}@frre.utn.edu.ar"
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
        correo_comprobante="facturacion@techsolutions.com",
        centro_costo="Laboratorio de Inteligencia Artificial",
        actor=accounts["demo_a"],
    )
    presupuesto_doc = SimpleUploadedFile("presupuesto_gpu.pdf", b"%PDF-1.7 Demo Presupuesto\n%%EOF", "application/pdf")
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
        correo_comprobante="ventas@quimicadelnorte.com",
        centro_costo="Laboratorio de Química Aplicada",
        actor=accounts["demo_a"],
    )
    pago_doc = SimpleUploadedFile("factura_quimica.pdf", b"%PDF-1.7 Demo Factura\n%%EOF", "application/pdf")
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
        importe=Decimal("115800.00"),  # Neto
        fecha_pago=date.today(),
        referencia_externa="TRANSF-GAL-20261103-01",
        referencia_documental=str(doc_factura.referencia_version),
        monto_bruto=Decimal("120000.00"),
        monto_retencion_atp=Decimal("4200.00"),
        referencia_atp="CONST-ATP-2026-00892",
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
        archivo=SimpleUploadedFile("presup_red.pdf", b"%PDF-1.7 Presupuesto\n%%EOF", "application/pdf"),
        tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
        procedencia="SOLICITANTE",
    )
    registrar_pago_externo(
        solicitud_id=sol_gracia.pk,
        actor=actor_o,
        importe=Decimal("45000.00"),
        fecha_pago=date.today() - timedelta(days=5),
        referencia_externa="TRANSF-RED-20261029",
        referencia_documental=str(doc_gracia.referencia_version),
        monto_bruto=Decimal("45000.00"),
        monto_retencion_atp=Decimal("0.00"),
        document_provider=ProveedorDocumentalGastos(),
    )

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
            archivo=SimpleUploadedFile(f"presup_mora_{i}.pdf", b"%PDF-1.7 Presupuesto\n%%EOF", "application/pdf"),
            tipo=Documento.Tipo.PRESUPUESTO_PROFORMA,
            procedencia="SOLICITANTE",
        )
        registrar_pago_externo(
            solicitud_id=sol_mora.pk,
            actor=actor_o,
            importe=Decimal("30000.00"),
            fecha_pago=date.today() - timedelta(days=25),
            referencia_externa=f"TRANSF-MORA-{i}",
            referencia_documental=str(doc_mora.referencia_version),
            monto_bruto=Decimal("30000.00"),
            monto_retencion_atp=Decimal("0.00"),
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
        archivo=SimpleUploadedFile("factura_c1.pdf", b"%PDF-1.7 Factura C1\n%%EOF", "application/pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    pago_c1 = registrar_pago_externo(
        solicitud_id=sol_c1.pk,
        actor=actor_o,
        importe=Decimal("80000.00"),
        fecha_pago=date(2026, 3, 10),
        referencia_externa="TRANSF-C1-001",
        referencia_documental=str(doc_c1.referencia_version),
        monto_bruto=Decimal("80000.00"),
        monto_retencion_atp=Decimal("0.00"),
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
        archivo=SimpleUploadedFile("factura_c2.pdf", b"%PDF-1.7 Factura C2\n%%EOF", "application/pdf"),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    pago_c2 = registrar_pago_externo(
        solicitud_id=sol_c2.pk,
        actor=actor_o,
        importe=Decimal("193000.00"),
        fecha_pago=date(2026, 7, 15),
        referencia_externa="TRANSF-C2-001",
        referencia_documental=str(doc_c2.referencia_version),
        monto_bruto=Decimal("200000.00"),
        monto_retencion_atp=Decimal("7000.00"),
        referencia_atp="CONST-ATP-C2-0045",
        document_provider=ProveedorDocumentalGastos(),
    )
    SolicitudGasto.objects.filter(pk=sol_c2.pk).update(fecha_creacion=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc))

    print(f"--- Solicitud pendiente de pago creada con ID: {sol_pago.pk} ---")
    print(f"--- Solicitud pagada creada con ID: {sol_pagada.pk} ---")
    print("--- Todas las fixtures creadas exitosamente! ---")


if __name__ == "__main__":
    run()
