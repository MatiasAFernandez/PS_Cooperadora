"""Ficha PDF de datos de solicitud; no emite comprobantes fiscales."""

from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .forms import SolicitudFacturacionForm
from .views import FacturacionView


def generar_pdf(solicitud):
    salida = BytesIO()
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("Texto", parent=estilos["BodyText"], fontSize=10, leading=14)
    titulo = ParagraphStyle(
        "Titulo",
        parent=estilos["Heading1"],
        textColor=colors.HexColor("#212529"),
        fontSize=18,
        leading=22,
    )

    def texto(valor):
        return Paragraph(escape(str(valor)).replace("\n", "<br/>"), normal)

    filas = []
    for nombre, campo in SolicitudFacturacionForm.base_fields.items():
        if nombre in {"archivo_comprobante", "retirar_comprobante"}:
            continue
        valor = getattr(solicitud, nombre)
        if nombre == "presento_comprobante_pago":
            valor = "Sí" if valor else "No"
        elif nombre == "importe_factura":
            valor = f"{valor:.2f} ARS".replace(".", ",")
        elif hasattr(campo, "choices"):
            valor = dict(campo.choices).get(valor, valor)
        elif nombre == "fecha_operacion_declarada" and valor:
            valor = valor.strftime("%d/%m/%Y")
        filas.append(
            [texto(campo.label), texto(valor if valor not in (None, "") else "Sin declarar")]
        )
    filas.insert(1, [texto("Correo del solicitante"), texto(solicitud.correo_solicitante)])
    tabla = Table(filas, colWidths=[58 * mm, 116 * mm], hAlign="LEFT", splitInRow=1)
    tabla.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8f9fa")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dee2e6")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    ahora = timezone.localtime()
    contenido = [
        Paragraph("Solicitud para preparar facturación", titulo),
        texto("No es comprobante fiscal"),
        Spacer(1, 5 * mm),
        texto(f"Solicitud facturacion:{solicitud.pk} · Versión {solicitud.version_concurrencia}"),
        texto(f"Estado: {solicitud.get_estado_display()}"),
        texto(
            "Presentada: "
            + timezone.localtime(solicitud.fecha_presentacion).strftime("%d/%m/%Y %H:%M")
        ),
        texto("Exportada: " + ahora.strftime("%d/%m/%Y %H:%M %Z")),
        Spacer(1, 5 * mm),
        tabla,
        Spacer(1, 4 * mm),
        texto(
            "La declaración inicial de pago no acredita ingreso verificado. "
            "Los datos deben revisarse y completarse en el sistema de emisión externo."
        ),
    ]

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(
            A4[0] / 2,
            12 * mm,
            f"Solicitud {solicitud.pk} · No es comprobante fiscal · Página {doc.page}",
        )
        canvas.restoreState()

    SimpleDocTemplate(
        salida,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=f"Solicitud de facturación {solicitud.pk}",
    ).build(contenido, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()


class ExportarSolicitudPDFView(FacturacionView):
    def get(self, request, numero):
        solicitud = self.objeto(numero)
        respuesta = HttpResponse(generar_pdf(solicitud), content_type="application/pdf")
        respuesta["Content-Disposition"] = (
            f'attachment; filename="solicitud-facturacion-{numero}.pdf"'
        )
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
