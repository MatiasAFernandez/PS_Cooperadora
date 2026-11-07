from decimal import Decimal

from django import forms

from documentos.models import Documento

from .choices import MEDIOS_PAGO_EFECTIVOS, ModalidadCobro
from .models import VerificacionCobro

DATOS_COBRO = ("medio", "numero_operacion", "fecha_operacion", "importe")


class CobroForm(forms.Form):
    medio = forms.ChoiceField(
        label="Medio / cuenta de destino",
        choices=[
            ("", "Seleccioná…"),
            *((k, v) for k, v in ModalidadCobro.choices if k in MEDIOS_PAGO_EFECTIVOS),
        ],
    )
    numero_operacion = forms.CharField(label="Número de operación", max_length=100)
    fecha_operacion = forms.DateField(
        label="Fecha de operación", widget=forms.DateInput(attrs={"type": "date"})
    )
    importe = forms.DecimalField(
        label="Importe recibido (ARS)", max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    documento = forms.ModelChoiceField(
        label="Documento de respaldo existente",
        queryset=Documento.objects.none(),
        required=False,
        empty_label="Seleccioná un documento de respaldo o adjuntá uno nuevo",
        help_text=(
            "Acá aparecen los comprobantes de esta solicitud que todavía no están vinculados "
            "a un cobro, como el archivo adjuntado al presentar la solicitud. "
            "Si la lista está vacía, adjuntá el comprobante en Nuevo documento de respaldo."
        ),
    )
    archivo = forms.FileField(
        label="Nuevo documento de respaldo",
        required=False,
        help_text="PDF, JPEG o PNG de hasta 10 MiB.",
    )
    confirmar_al_registrar = forms.BooleanField(
        label="Cotejé el ingreso externo y doy conformidad al documento de respaldo",
        required=False,
        initial=True,
        help_text=(
            "Confirma el ingreso y registra tu conformidad documental en esta misma carga. "
            "No constituye una revisión por otra persona. Sin marcar, el cobro queda pendiente."
        ),
    )

    def __init__(self, *args, documentos, puede_confirmar=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not puede_confirmar:
            del self.fields["confirmar_al_registrar"]
        self.fields["documento"].queryset = documentos
        self.fields["documento"].label_from_instance = lambda d: (
            f"{d.nombre_original} — versión {d.version}"
        )

    def clean(self):
        datos = super().clean()
        if bool(datos.get("documento")) == bool(datos.get("archivo")):
            raise forms.ValidationError(
                "Elegí un documento de respaldo existente o adjuntá uno nuevo. Usá una sola opción."
            )
        return datos


class CorreccionCobroForm(forms.Form):
    medio = CobroForm.base_fields["medio"]
    numero_operacion = CobroForm.base_fields["numero_operacion"]
    fecha_operacion = forms.DateField(
        label="Fecha de operación",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    importe = CobroForm.base_fields["importe"]
    archivo = forms.FileField(
        label="Nuevo documento de respaldo (opcional)",
        required=False,
        help_text=(
            "PDF, JPEG o PNG de hasta 10 MiB. Si lo omitís, se crea una versión "
            "del documento de respaldo actual."
        ),
    )
    motivo = forms.CharField(
        label="Motivo de la corrección", max_length=2000, widget=forms.Textarea
    )


class ModificarCobroForm(CorreccionCobroForm):
    nuevo_id = forms.ModelChoiceField(
        label="Versión sucesora vigente existente",
        queryset=Documento.objects.none(),
        required=False,
        empty_label="Conservar el documento vinculado",
        help_text=(
            "Si ya se cargó una versión nueva para este cobro, podés seleccionarla acá. "
            "También podés adjuntar otro archivo."
        ),
    )
    resultado_esperado = forms.CharField(widget=forms.HiddenInput)
    revision = forms.CharField(widget=forms.HiddenInput)
    field_order = (*DATOS_COBRO, "nuevo_id", "archivo", "motivo")

    def __init__(self, *args, cobro, revision, puede_corregir, puede_adjuntar, opciones=None):
        super().__init__(
            *args,
            initial={
                **{campo: getattr(cobro, campo) for campo in DATOS_COBRO},
                "resultado_esperado": cobro.resultado,
                "revision": revision,
            },
        )
        for campo in DATOS_COBRO:
            self.fields[campo].disabled = not puede_corregir
            self.fields[campo].widget.attrs["data-valor-original"] = str(self.initial[campo])
        self.fields["motivo"].label = "Motivo del cambio"
        if puede_adjuntar:
            self.fields["archivo"].help_text = "PDF, JPEG o PNG de hasta 10 MiB."
        else:
            del self.fields["archivo"]
        if opciones is None:
            del self.fields["nuevo_id"]
        else:
            self.fields["nuevo_id"].queryset = opciones
            self.fields["nuevo_id"].label_from_instance = lambda documento: (
                f"{documento.nombre_original} — versión {documento.version}"
            )

    def clean(self):
        datos = super().clean()
        if datos.get("archivo") and datos.get("nuevo_id"):
            raise forms.ValidationError("Elegí una versión existente o adjuntá un archivo nuevo.")
        return datos


class VerificacionCobroForm(forms.Form):
    resultado = forms.ChoiceField(
        choices=[("", "Seleccioná…"), *VerificacionCobro.Resultado.choices]
    )
    motivo = forms.CharField(required=False, max_length=2000, widget=forms.Textarea)

    def clean(self):
        datos = super().clean()
        if datos.get("resultado") == "RECHAZADO" and not datos.get("motivo"):
            self.add_error("motivo", "Indicá el motivo del rechazo.")
        return datos
