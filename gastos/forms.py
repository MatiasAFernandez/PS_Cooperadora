"""Formularios para el módulo de gastos."""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from documentos.models import Documento
from gastos.contracts import OpcionDocumental
from gastos.models import EstadoSolicitud, SolicitudGasto


class FiltroEstadoGastoForm(forms.Form):
    """Filtros de sólo lectura sobre las solicitudes visibles de la demo."""

    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=[("", "Todos los estados"), *EstadoSolicitud.choices],
        widget=forms.Select(attrs={"class": "form-control"}),
        error_messages={"invalid_choice": "Seleccione un estado válido."},
    )
    q = forms.CharField(
        label="Buscar en concepto",
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={"type": "search", "class": "form-control", "placeholder": "Texto del concepto"}
        ),
    )


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


class DocumentoGastoForm(forms.Form):
    """Formulario de aporte o reemplazo; los servicios documentales revalidan."""

    archivo = forms.FileField(
        label="Archivo de respaldo",
        error_messages={"required": "Seleccione un archivo de respaldo."},
        widget=forms.ClearableFileInput(
            attrs={"accept": ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"}
        ),
    )
    tipo = forms.ChoiceField(
        label="Tipo de documento",
        choices=(),
        error_messages={
            "required": "Seleccione un tipo de documento.",
            "invalid_choice": "Seleccione un tipo de documento válido para gastos.",
        },
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    procedencia = forms.ChoiceField(
        label="Procedencia",
        choices=(),
        error_messages={
            "required": "Seleccione la procedencia del documento.",
            "invalid_choice": "Seleccione una procedencia válida.",
        },
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    reemplaza_id = forms.ChoiceField(
        label="Versión a reemplazar",
        required=False,
        choices=(("", "Incorporar un documento nuevo"),),
        error_messages={
            "invalid_choice": (
                "Seleccione una versión vigente de este gasto o incorpore un documento nuevo."
            ),
        },
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(
        self,
        *args,
        combinaciones_documentales: dict[str, tuple[str, ...]],
        versiones_reemplazables=(),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        etiquetas_tipo = dict(Documento.Tipo.choices)
        etiquetas_procedencia = dict(Documento.Procedencia.choices)
        tipos = tuple(combinaciones_documentales)
        procedencias = tuple(
            dict.fromkeys(
                procedencia
                for opciones in combinaciones_documentales.values()
                for procedencia in opciones
            )
        )
        self.combinaciones_documentales = {
            tipo: frozenset(opciones)
            for tipo, opciones in combinaciones_documentales.items()
        }
        self.versiones_reemplazables = {
            str(version.documento_id): version for version in versiones_reemplazables
        }
        self.fields["tipo"].choices = [
            ("", "Seleccione un tipo"),
            *((tipo, etiquetas_tipo[tipo]) for tipo in tipos),
        ]
        self.fields["procedencia"].choices = [
            ("", "Seleccione una procedencia"),
            *((codigo, etiquetas_procedencia[codigo]) for codigo in procedencias),
        ]
        self.fields["reemplaza_id"].choices = [
            ("", "Incorporar un documento nuevo"),
            *(
                (
                    documento_id,
                    f"{version.tipo_mostrado} — {version.nombre} — versión {version.version}",
                )
                for documento_id, version in self.versiones_reemplazables.items()
            ),
        ]

    def clean(self):
        datos = super().clean()
        tipo = datos.get("tipo")
        procedencia = datos.get("procedencia")
        if tipo and procedencia and procedencia not in self.combinaciones_documentales.get(
            tipo, frozenset()
        ):
            self.add_error(
                "procedencia",
                "La combinación de tipo y procedencia no está disponible para este gasto.",
            )

        reemplaza_id = datos.get("reemplaza_id")
        version = self.versiones_reemplazables.get(reemplaza_id)
        if version is not None and tipo and version.tipo != tipo:
            self.add_error("tipo", "Al reemplazar, conserve el tipo de la versión seleccionada.")
        return datos


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
