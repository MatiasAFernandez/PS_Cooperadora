"""Formularios para el módulo de gastos."""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from comunes.filtros import FiltroFechaForm
from documentos.models import Documento
from gastos.contracts import OpcionDocumental
from gastos.datos_transferencia import (
    CAMPOS_DATOS_TRANSFERENCIA,
    ETIQUETAS_DATOS_TRANSFERENCIA,
    LONGITUDES_DATOS_TRANSFERENCIA,
    MENSAJE_CBU_ALIAS_FRECUENTE,
    MENSAJE_CORREO_COMPROBANTE_INVALIDO,
    DatosTransferenciaInvalidInputError,
    es_cbu_alias_frecuente,
    validar_datos_transferencia,
)
from gastos.models import CentroCosto, EstadoSolicitud, SolicitudGasto, TipoFlujoGasto


class FiltroEstadoGastoForm(FiltroFechaForm):
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


class OptionalCentroCostoChoiceField(forms.ModelChoiceField):
    """Campo de centro de costo de catálogo que tolera valores textuales de transferencia."""

    def to_python(self, value: Any) -> Any:
        if value in self.empty_values:
            return None
        try:
            return super().to_python(value)
        except ValidationError:
            return None


class SolicitudGastoForm(forms.ModelForm):
    """Formulario para la presentación de una necesidad de gasto."""

    tipo_flujo = forms.ChoiceField(
        label="Modalidad de gasto",
        choices=TipoFlujoGasto.choices,
        initial=TipoFlujoGasto.COMPRA_DIRECTA,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text=(
            "Compra Directa (con presupuesto previo y factura posterior) o "
            "Reintegro (con factura previa ya abonada)."
        ),
    )
    centro_costo = OptionalCentroCostoChoiceField(
        label="Centro de costo institucional",
        queryset=CentroCosto.objects.filter(activo=True),
        required=False,
        empty_label="-- Seleccionar centro de costo (opcional) --",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Centro de costo institucional imputado. Se sincroniza con la transferencia.",
    )

    class Meta:
        model = SolicitudGasto
        fields = [
            "concepto",
            "monto_estimado",
            "unidad_requirente",
            "tipo_flujo",
            "centro_costo",
        ]
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["centro_costo"].queryset = CentroCosto.objects.filter(activo=True)

    def clean_tipo_flujo(self) -> str:
        flujo = self.cleaned_data.get("tipo_flujo")
        if not flujo:
            return TipoFlujoGasto.COMPRA_DIRECTA
        if flujo not in TipoFlujoGasto.values:
            raise ValidationError("Seleccione una modalidad de gasto válida.")
        return flujo

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


class DatosTransferenciaForm(forms.Form):
    """Bloque opcional y completo de datos operativos para una transferencia.

    El formulario no crea filas por sí mismo: la vista entrega el resultado al
    servicio, que revalida y serializa la escritura. Valida la sintaxis del
    correo de destino y rechaza el literal «frecuente» como CBU/alias; tampoco
    copia el correo de la sesión ni relaciona estos datos con la unidad
    requirente.
    """

    titular_nombre = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["titular_nombre"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["titular_nombre"],
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "Persona titular o beneficiaria de la cuenta",
            }
        ),
        help_text="Se guarda como fue informado; no se presume que sea quien solicita.",
    )
    identificacion = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["identificacion"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["identificacion"],
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
        help_text="No se valida contra un padrón todavía inexistente.",
    )
    cbu_alias = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["cbu_alias"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["cbu_alias"],
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "CBU o alias real informado",
            }
        ),
        help_text=(
            "Dato textual; no se acepta «frecuente» como cuenta ni se verifica "
            "con el banco."
        ),
    )
    correo_comprobante = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["correo_comprobante"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["correo_comprobante"],
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off", "inputmode": "email"}
        ),
        help_text=(
            "Correo de destino; se guarda el texto ingresado normalizado, sin "
            "copiarlo de la sesión y sin enviar mensajes."
        ),
    )
    centro_costo = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["centro_costo"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["centro_costo"],
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
        help_text="Se informa como texto y es independiente de la unidad requirente.",
    )

    def __init__(self, *args: Any, centro_costo_default: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.centro_costo_default = centro_costo_default
        self.datos_transferencia: dict[str, str] | None = None

    def clean_cbu_alias(self) -> str:
        cbu_alias = self.cleaned_data.get("cbu_alias", "").strip()
        if cbu_alias and es_cbu_alias_frecuente(cbu_alias):
            raise ValidationError(MENSAJE_CBU_ALIAS_FRECUENTE, code="invalid")
        return cbu_alias

    def clean_correo_comprobante(self) -> str:
        correo = self.cleaned_data.get("correo_comprobante", "").strip()
        if not correo:
            return correo
        try:
            validate_email(correo)
        except ValidationError as exc:
            raise ValidationError(
                MENSAJE_CORREO_COMPROBANTE_INVALIDO, code="invalid"
            ) from exc
        return correo

    def clean(self) -> dict[str, Any]:
        datos = super().clean()
        if not (datos.get("centro_costo") or "").strip() and self.centro_costo_default:
            datos["centro_costo"] = self.centro_costo_default
            self.cleaned_data["centro_costo"] = self.centro_costo_default

        if not any(datos.get(campo) for campo in CAMPOS_DATOS_TRANSFERENCIA):
            self.datos_transferencia = None
            return datos

        # Un error de campo (correo inválido, «frecuente» o longitud excedida)
        # ya explica el problema; no se duplica como dato faltante del bloque.
        if self.errors:
            self.datos_transferencia = None
            return datos

        try:
            self.datos_transferencia = validar_datos_transferencia(datos)
        except DatosTransferenciaInvalidInputError as exc:
            for campo in exc.campos_faltantes:
                self.add_error(
                    campo,
                    "Este dato es obligatorio si completa el bloque de transferencia.",
                )
            self.add_error(None, str(exc))
            self.datos_transferencia = None
        return datos


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
        label="Documento de respaldo",
        error_messages={"required": "Seleccione un documento de respaldo."},
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
    monto_bruto = forms.CharField(
        label="Monto bruto de la operación (ARS)",
        required=False,
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "0.00",
            }
        ),
        help_text="Importe bruto antes de retención ATP. Si no aplica retención, déjelo vacío.",
    )
    monto_retencion_atp = forms.CharField(
        label="Monto retención ATP (ARS)",
        required=False,
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "0.00",
            }
        ),
        help_text="Importe a retener por alícuota provincial de ATP Chaco.",
    )
    referencia_atp = forms.CharField(
        label="Certificado o referencia ATP",
        required=False,
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "ej: CERT-ATP-2026-001",
            }
        ),
        help_text="Número o referencia del certificado de retención impositiva.",
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
        if opcion.tipo_documento == "factura":
            return "Factura o Ticket-Factura de proveedor"
        return f"Documento de respaldo ({opcion.tipo_documento})"


class CentroCostoForm(forms.ModelForm):
    """Formulario para la administración de centros de costo."""

    codigo = forms.SlugField(
        max_length=64,
        strip=True,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "ej: lab-quimica"}
        ),
        help_text="Identificador único en minúsculas, números y guiones.",
    )

    class Meta:
        model = CentroCosto
        fields = ["codigo", "nombre", "activo"]
        widgets = {
            "nombre": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "ej: Laboratorio de Química"}
            ),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_codigo(self) -> str:
        codigo = self.cleaned_data.get("codigo", "").strip().lower()
        if not codigo:
            raise ValidationError("El código del centro de costo es obligatorio.")
        return codigo

    def clean_nombre(self) -> str:
        nombre = self.cleaned_data.get("nombre", "").strip()
        if not nombre:
            raise ValidationError("El nombre del centro de costo es obligatorio.")
        return nombre


class ParametrosATPForm(forms.Form):
    """Formulario para la configuración de la retención de ATP."""

    base_imponible_atp = forms.DecimalField(
        label="Base imponible de retención ATP (ARS)",
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "90000.00"}
        ),
        help_text="Monto a partir del cual aplica retención impositiva.",
    )
    alicuota_atp = forms.DecimalField(
        label="Alícuota sugerida ATP (%)",
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "3.50"}
        ),
        help_text="Porcentaje de retención provincial aplicado por defecto.",
    )

