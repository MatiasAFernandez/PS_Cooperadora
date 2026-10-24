"""Muestra sintética para ensayar respaldo y restauración; no ejecuta el respaldo."""

import hashlib
import json
from datetime import date
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import serializers
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from comunes.models import TramiteBase
from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento
from documentos.revision import revisar
from documentos.services import incorporar
from facturacion.cobros import registrar_cobro, verificar_cobro
from facturacion.comprobantes import registrar_comprobante
from facturacion.seguimiento import diagnostico, resolver_tramite
from facturacion.workflow import emitir_token, presentar_solicitud_facturacion
from gastos.payments import registrar_pago_externo
from gastos.services import crear_solicitud_gasto, decide_expense
from identidad.services import GROUP_CAPABILITIES, Actor


def pdf():
    return SimpleUploadedFile(
        "muestra.pdf", b"%PDF-1.7\nMuestra sintetica I2\n%%EOF", "application/pdf"
    )


def huella():
    modelos = {}
    for app in ("comunes", "gastos", "facturacion", "documentos"):
        for modelo in apps.get_app_config(app).get_models():
            datos = serializers.serialize("json", modelo.objects.order_by("pk"))
            modelos[modelo._meta.label_lower] = hashlib.sha256(datos.encode()).hexdigest()
    archivos = {
        str(d.pk): hashlib.sha256(
            (settings.DOCUMENT_STORAGE_ROOT / d.archivo).read_bytes()
        ).hexdigest()
        for d in Documento.objects.order_by("pk")
    }
    usuarios = [
        {
            "id": u.pk,
            "nombre": u.username,
            "grupos": sorted(u.groups.values_list("name", flat=True)),
        }
        for u in get_user_model().objects.order_by("pk")
    ]
    return {"modelos": modelos, "archivos": archivos, "usuarios": usuarios}


def crear():
    call_command(
        "preparar_identidad_demo",
        facturacion=True,
        revision_documental=True,
        verificacion_cobros=True,
        resolucion_facturacion=True,
        verbosity=0,
    )
    usuarios = {r: get_user_model().objects.get(username=f"demo_{r}") for r in ("a", "b", "o")}
    usuarios["o"].groups.add(Group.objects.get(name="demo_gastos_pago"))
    actores = {
        r: Actor(
            u.pk,
            frozenset().union(
                *(GROUP_CAPABILITIES[g] for g in u.groups.values_list("name", flat=True))
            ),
            u.email,
        )
        for r, u in usuarios.items()
    }
    a, b, o = (actores[r] for r in ("a", "b", "o"))
    gasto = crear_solicitud_gasto(
        actor=a,
        concepto="Insumos sintéticos I2",
        monto_estimado="100.25",
        unidad_requirente="Demo",
    )
    decide_expense(
        actor=o, solicitud_id=gasto.pk, action="aceptar", expected_version=0, motivo="Demo"
    )
    documento = incorporar(
        actor=a,
        referencia=f"gastos:{gasto.pk}",
        archivo=pdf(),
        tipo="FACTURA_PROVEEDOR",
        procedencia="SOLICITANTE",
    )
    revisar(
        actor=o, documento_id=documento.pk, resultado="ACEPTADO", motivo="", revision_esperada=0
    )
    registrar_pago_externo(
        actor=o,
        solicitud_id=gasto.pk,
        importe="100.25",
        fecha_pago=date(2026, 10, 24),
        referencia_externa="MUESTRA-I2-PAGO",
        referencia_documental=str(documento.referencia_version),
        document_provider=ProveedorDocumentalGastos(),
    )
    incorporar(
        actor=a,
        referencia=f"gastos:{gasto.pk}",
        archivo=pdf(),
        tipo="FACTURA_PROVEEDOR",
        procedencia="SOLICITANTE",
        reemplaza_id=documento.pk,
    )
    solicitud = presentar_solicitud_facturacion(
        actor=b,
        token_presentacion=emitir_token(b),
        datos={
            "presento_comprobante_pago": False,
            "nombre_solicitante": "Solicitante sintético",
            "cuit_receptor": "30712345671",
            "nombre_receptor": "Receptor sintético",
            "condicion_iva": "IVA_RESPONSABLE_INSCRIPTO",
            "email_envio_factura": "demo@example.invalid",
            "detalle_factura": "Servicio sintético",
            "importe_factura": "100.25",
            "producto_servicio": "ANALISIS",
            "centro_costo": "GISTAQ",
            "modalidad_cobro": "CUENTA_CORRIENTE",
            "observaciones": "Muestra de recuperación",
        },
    )
    factura = registrar_comprobante(
        actor=o,
        numero_publico=solicitud.pk,
        archivo_pdf=pdf(),
        datos={
            "tipo": "FACTURA",
            "cuit_emisor": "30712345671",
            "letra": "A",
            "punto_venta": "1",
            "numero": "29",
            "fecha_emision": "2026-10-24",
            "importe": "100.25",
        },
    )
    cobro = registrar_cobro(
        actor=b,
        numero=solicitud.pk,
        archivo=pdf(),
        datos={
            "medio": "BNA_COMUN",
            "numero_operacion": "MUESTRA-I2-COBRO",
            "fecha_operacion": "2026-10-24",
            "importe": "100.25",
        },
    )
    verificar_cobro(
        actor=o, numero=solicitud.pk, cobro_id=cobro.pk, datos={"resultado": "CONFIRMADO"}
    )
    for d in (factura.documento, cobro.documento):
        revisar(actor=o, documento_id=d.pk, resultado="ACEPTADO", motivo="", revision_esperada=0)
    resolver_tramite(
        actor=o,
        numero=solicitud.pk,
        accion="cerrar",
        motivo="Cierre sintético",
        revision_esperada=diagnostico(solicitud)["revision"],
    )


def verificar_acceso():
    for documento in Documento.objects.select_related("tramite_base"):
        cliente = Client()
        cliente.force_login(
            get_user_model().objects.get(pk=documento.tramite_base.solicitante_actor_id)
        )
        url = reverse("documentos:archivo", args=[documento.pk])
        respuesta = cliente.get(url, HTTP_HOST="localhost")
        if respuesta.status_code != 200:
            raise CommandError("La descarga del titular no funciona tras restaurar.")
        contenido = b"".join(respuesta.streaming_content)
        if (
            hashlib.sha256(contenido).hexdigest()
            != hashlib.sha256(
                (settings.DOCUMENT_STORAGE_ROOT / documento.archivo).read_bytes()
            ).hexdigest()
        ):
            raise CommandError("La descarga no coincide con el archivo restaurado.")
        ajeno = "demo_b" if documento.tramite_base.circuito == "GASTO" else "demo_a"
        cliente.force_login(get_user_model().objects.get(username=ajeno))
        if cliente.get(url, HTTP_HOST="localhost").status_code != 404:
            raise CommandError("La descarga ajena no fue denegada.")


class Command(BaseCommand):
    help = "Crea o verifica una muestra sintética en una base aislada para ensayar recuperación."

    def add_arguments(self, parser):
        parser.add_argument("accion", choices=("crear", "verificar"))
        parser.add_argument("--manifiesto", required=True, type=Path)

    def handle(self, *args, **options):
        if not settings.DEMO_IDENTITY_ENABLED:
            raise CommandError("Sólo se admite el entorno de demo explícitamente habilitado.")
        manifiesto = options["manifiesto"]
        if options["accion"] == "crear":
            if get_user_model().objects.exists() or TramiteBase.objects.exists():
                raise CommandError("Crear exige una base migrada vacía, sin usuarios ni trámites.")
            if manifiesto.exists() or (
                settings.DOCUMENT_STORAGE_ROOT.exists()
                and any(settings.DOCUMENT_STORAGE_ROOT.iterdir())
            ):
                raise CommandError(
                    "El manifiesto y el almacenamiento de destino deben estar vacíos."
                )
            crear()
            manifiesto.write_text(json.dumps(huella(), indent=2), encoding="utf-8")
        else:
            esperado = json.loads(manifiesto.read_text(encoding="utf-8"))
            if huella() != esperado:
                raise CommandError(
                    "La muestra restaurada difiere de la original (filas, grupos o bytes)."
                )
            verificar_acceso()
        self.stdout.write(self.style.SUCCESS(f"Muestra {options['accion']}: correcta."))
