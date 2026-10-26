from decimal import Decimal

from django import forms

from documentos.models import Documento

from .choices import MEDIOS_PAGO_EFECTIVOS, ModalidadCobro
from .models import VerificacionCobro


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
        label="Respaldo existente",
        queryset=Documento.objects.none(),
        required=False,
        empty_label="Seleccioná un respaldo o adjuntá uno nuevo",
    )
    archivo = forms.FileField(label="Nuevo respaldo PDF/JPEG/PNG (hasta 10 MiB)", required=False)
    confirmar_al_registrar = forms.BooleanField(
        label="Cotejé el ingreso externo y doy conformidad al respaldo",
        required=False,
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
            raise forms.ValidationError("Elegí un respaldo existente o un archivo nuevo, sólo uno.")
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
