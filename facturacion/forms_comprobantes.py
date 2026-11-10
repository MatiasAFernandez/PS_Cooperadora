"""Datos declarados de un comprobante externo; no emite ni valida fiscalmente."""

from decimal import Decimal

from django import forms

from documentos.models import Documento

from .envios import EnvioForm
from .models import ComprobanteExterno
from .validation import validar_cuit

DATOS_COMPROBANTE = (
    "cuit_emisor", "letra", "punto_venta", "numero", "fecha_emision", "importe",
    "procedencia", "origen_aclaracion",
)


class ComprobanteExternoForm(EnvioForm):
    field_order = (
        "tipo", *DATOS_COMPROBANTE, "archivo_pdf", "aceptar_respaldo",
        "enviado", "destinatario", "fecha_envio",
    )
    tipo = forms.ChoiceField(choices=[("", "Seleccioná…"), *ComprobanteExterno.Tipo.choices])
    cuit_emisor = forms.CharField(
        label="CUIT de quien emite el comprobante",
        validators=[validar_cuit],
        max_length=11,
        help_text=(
            "Copialo del comprobante emitido. Si factura Cooperadora, corresponde su CUIT; "
            "el CUIT del receptor de la solicitud identifica a quien recibe la factura."
        ),
    )
    letra = forms.RegexField(
        regex=r"^[A-Z]$",
        label="Letra del comprobante (A, B, C…)",
        max_length=1,
        help_text=(
            "Copiala del comprobante emitido, en mayúscula. "
            "El campo Tipo distingue factura, nota de crédito o nota de débito."
        ),
    )
    punto_venta = forms.IntegerField(label="Punto de venta", min_value=1, max_value=99999)
    numero = forms.IntegerField(label="Número", min_value=1, max_value=99999999)
    fecha_emision = forms.DateField(
        label="Fecha de emisión",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    importe = forms.DecimalField(
        label="Importe del comprobante",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    archivo_pdf = forms.FileField(
        label="PDF del comprobante (opcional para Xubio)", required=False,
        help_text="Si ya está en Xubio, registrá sus datos sin volver a cargar el PDF. "
        "Para Otro origen, el archivo es obligatorio.",
    )

    procedencia = forms.ChoiceField(
        label="Origen",
        required=False,
        choices=[("EXTERNO_XUBIO", "Xubio"), ("EXTERNO_OTRO", "Otro")],
        initial="EXTERNO_XUBIO",
    )
    origen_aclaracion = forms.CharField(
        label="Aclaración del otro origen",
        required=False,
        max_length=200,
        help_text="Obligatoria si seleccionás Otro.",
    )
    aceptar_respaldo = forms.BooleanField(
        label="Revisé el PDF y doy conformidad al documento de respaldo",
        required=False,
        initial=True,
        help_text="Guarda la conformidad documental a tu nombre junto con el comprobante.",
    )

    def __init__(self, *args, puede_aceptar=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not puede_aceptar:
            del self.fields["aceptar_respaldo"]

    def clean(self):
        datos = super().clean()
        origen = datos.get("procedencia") or "EXTERNO_XUBIO"
        datos["procedencia"] = origen
        if origen == "EXTERNO_OTRO" and not datos.get("origen_aclaracion"):
            self.add_error("origen_aclaracion", "Indicá el sistema o procedencia del comprobante.")
        if origen == "EXTERNO_XUBIO":
            datos["origen_aclaracion"] = ""
        if origen == "EXTERNO_OTRO" and not datos.get("archivo_pdf") and not getattr(
            self, "conserva_archivo", False
        ):
            self.add_error("archivo_pdf", "Para Otro origen, adjuntá el PDF del comprobante.")
        return datos


class ModificarComprobanteForm(ComprobanteExternoForm):
    nuevo = forms.ModelChoiceField(
        label="Versión sucesora vigente existente",
        queryset=Documento.objects.none(),
        required=False,
        empty_label="Conservar el PDF vinculado",
        help_text="Elegí una versión ya cargada del mismo comprobante o adjuntá un PDF nuevo.",
    )
    motivo = forms.CharField(label="Motivo del cambio", max_length=2000, widget=forms.Textarea)
    revision = forms.CharField(widget=forms.HiddenInput)
    field_order = ("tipo", *DATOS_COMPROBANTE, "nuevo", "archivo_pdf", "motivo")

    def __init__(self, *args, comprobante, revision, puede_corregir, puede_adjuntar, opciones=None):
        self.conserva_archivo = comprobante.documento_id is not None
        super().__init__(
            *args,
            initial={
                campo: getattr(comprobante, campo) for campo in ("tipo", *DATOS_COMPROBANTE)
            } | {"revision": revision},
        )
        for campo in ("enviado", "destinatario", "fecha_envio"):
            del self.fields[campo]
        self.fields["tipo"].disabled = True
        for campo in DATOS_COMPROBANTE:
            self.fields[campo].disabled = not puede_corregir
        self.fields["fecha_emision"].widget.format = "%Y-%m-%d"
        if puede_adjuntar:
            self.fields["archivo_pdf"].required = False
            self.fields["archivo_pdf"].label = "Nuevo PDF del comprobante"
        else:
            del self.fields["archivo_pdf"]
        if opciones is None:
            del self.fields["nuevo"]
        else:
            self.fields["nuevo"].queryset = opciones
            self.fields["nuevo"].label_from_instance = lambda documento: (
                f"{documento.nombre_original} — versión {documento.version}"
            )

    def clean(self):
        datos = super().clean()
        if datos.get("nuevo") and datos.get("archivo_pdf"):
            raise forms.ValidationError("Elegí una versión existente o adjuntá un PDF nuevo.")
        return datos
