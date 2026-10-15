"""Formularios para el módulo de gastos."""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from gastos.contracts import OpcionDocumental
from gastos.models import SolicitudGasto


class SolicitudGastoForm(forms.ModelForm):
    """Formulario para la presentación de una necesidad de gasto."""

    class Meta:
        model = SolicitudGasto
        fields = ["concepto", "monto_estimado", "unidad_requirente"]
        widgets = {
            "concepto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Insumos de laboratorio para cátedra",
                }
            ),
            "monto_estimado": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "0.00",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "unidad_requirente": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Laboratorio de Química",
                }
            ),
        }

    def clean_concepto(self) -> str:
        concepto = self.cleaned_data.get("concepto", "").strip()
        if not concepto:
            raise ValidationError("El concepto o justificación es obligatorio.")
        return concepto

    def clean_unidad_requirente(self) -> str:
        unidad = self.cleaned_data.get("unidad_requirente", "").strip()
        if not unidad:
            raise ValidationError("La unidad requirente es obligatoria.")
        return unidad

    def clean_monto_estimado(self) -> Decimal:
        monto = self.cleaned_data.get("monto_estimado")
        if monto is None or monto <= Decimal("0"):
            raise ValidationError("El importe estimado debe ser un monto positivo en ARS.")
        return monto


class DecisionGastoForm(forms.Form):
    """Formulario para la captura de una decisión humana sobre una solicitud de gasto."""

    action = forms.ChoiceField(
        choices=[
            ("aceptar", "Aceptar"),
            ("postergar", "Postergar"),
            ("rechazar", "Rechazar"),
        ],
        widget=forms.HiddenInput(),
    )
    version = forms.CharField(widget=forms.HiddenInput())
    motivo = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": (
                    "Ingrese el motivo de la decisión (obligatorio para postergar o rechazar)..."
                ),
            }
        ),
    )


class PagoExternoForm(forms.Form):
    """Captura del pago externo sin normalización previa.

    Los campos de importe, fecha y referencia externa se declaran como cadenas
    con `strip=False`: el formulario sólo comprueba presencia y pertenencia de la
    opción documental al listado vigente. La normalización autoritativa
    (importe, fecha y referencias) corresponde exclusivamente al servicio C03
    `gastos.payments.registrar_pago_externo`.

    El selector `referencia_documental` se construye a partir de las opciones
    seguras entregadas por el proveedor documental de servidor. El formulario no
    recibe, muestra ni deduce archivo, ruta, hash o revisión.
    """

    importe = forms.CharField(
        label="Importe pagado (ARS)",
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "0.00",
            }
        ),
        error_messages={"required": "El importe es obligatorio."},
    )
    fecha_pago = forms.CharField(
        label="Fecha del pago",
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "AAAA-MM-DD",
            }
        ),
        error_messages={"required": "La fecha de pago es obligatoria."},
    )
    referencia_externa = forms.CharField(
        label="Referencia externa",
        strip=False,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
        error_messages={"required": "La referencia externa es obligatoria."},
    )
    referencia_documental = forms.ChoiceField(
        label="Documento de respaldo",
        choices=(),
        widget=forms.Select(attrs={"class": "form-control"}),
        error_messages={
            "required": "Seleccione un documento de respaldo.",
            "invalid_choice": (
                "La opción documental seleccionada no está disponible para este gasto."
            ),
        },
    )

    def __init__(
        self,
        *args: Any,
        opciones_documentales: Iterable[OpcionDocumental] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["referencia_documental"].choices = [
            (opcion.referencia_documental, self._etiqueta_opcion(opcion))
            for opcion in (opciones_documentales or ())
        ]

    @staticmethod
    def _etiqueta_opcion(opcion: OpcionDocumental) -> str:
        """Etiqueta legible sin exponer más datos que los del DTO seguro."""
        etiqueta = (opcion.etiqueta or "").strip()
        if etiqueta:
            return etiqueta
        return f"Documento de respaldo ({opcion.tipo_documento})"
