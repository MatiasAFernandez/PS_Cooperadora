"""Formularios para el módulo de gastos."""

import re
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
from gestion.formularios import FormularioConfigurableMixin


class FiltroEstadoGastoForm(FiltroFechaForm):
    """Filtros de sólo lectura sobre las solicitudes visibles de la demo."""

    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=[
            ("", "Todos los estados"),
            *EstadoSolicitud.choices,
            ("pagada", "Pagada"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
        error_messages={"invalid_choice": "Seleccione un estado válido."},
    )
    q = forms.CharField(
        label="Buscar por concepto o número",
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "class": "form-control",
                "placeholder": "Buscar por concepto o número",
            }
        ),
    )
    pendiente = forms.ChoiceField(
        label="Tipo de pendiente",
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-control"}),
        error_messages={"invalid_choice": "Seleccione un pendiente válido."},
    )

    def __init__(
        self,
        *args: Any,
        pendientes: Iterable[tuple[str, str]] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        opciones = list(pendientes)
        if opciones:
            self.fields["pendiente"].choices = [
                ("", "Todos los trámites"),
                ("cualquiera", "Cualquier pendiente"),
                *opciones,
            ]
        else:
            # Sin pendientes propios del actor no se ofrece un selector vacío;
            # el campo oculto sigue validando los valores recibidos por GET.
            self.fields["pendiente"].choices = [("", "")]
            self.fields["pendiente"].widget = forms.HiddenInput()
            self.fields["pendiente"].label = ""
        self.order_fields(["estado", "q", "pendiente", "periodo", "dia", "mes", "anio"])


class OptionalCentroCostoChoiceField(forms.ModelChoiceField):
    """Campo de centro de costo de catálogo que tolera valores textuales de transferencia."""

    def to_python(self, value: Any) -> Any:
        if value in self.empty_values:
            return None
        try:
            return super().to_python(value)
        except ValidationError:
            return None


class MontoMonetarioField(forms.DecimalField):
    def to_python(self, value: Any) -> Decimal | None:
        if value in self.empty_values:
            return None
        if isinstance(value, str):
            value = normalizar_importe_monetario(value)
            if value == "":
                return None
            if not _RE_ASCII_SIN_SEPARADORES.fullmatch(value):
                raise ValidationError(
                    self.error_messages["invalid"], code="invalid"
                )
        return super().to_python(value)


class SolicitudGastoForm(FormularioConfigurableMixin, forms.ModelForm):
    """Formulario para la presentación de una necesidad de gasto."""

    tipo_flujo = forms.ChoiceField(
        label="Modalidad de gasto",
        choices=TipoFlujoGasto.choices,
        initial=TipoFlujoGasto.COMPRA_DIRECTA,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    centro_costo = OptionalCentroCostoChoiceField(
        label="Centro de costo",
        queryset=CentroCosto.objects.filter(activo=True),
        required=False,
        empty_label="-- Seleccionar centro de costo --",
        widget=forms.Select(attrs={"class": "form-control"}),
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
        labels = {
            "concepto": "Concepto / justificación", "monto_estimado": "Importe estimado · ARS",
        }
        help_texts = {"unidad_requirente": "Área o unidad que solicita el gasto."}
        field_classes = {"monto_estimado": MontoMonetarioField}
        widgets = {
            "concepto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Insumos de laboratorio para cátedra",
                }
            ),
            "monto_estimado": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "inputmode": "decimal",
                    "placeholder": "0,00",
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
        self.configurar("GASTO")

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


class RespaldoSolicitudForm(FormularioConfigurableMixin, forms.Form):
    """Adjunto opcional del alta; la vista aplica la política del archivo."""

    respaldo_archivo = forms.FileField(
        label="Respaldo comercial",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"accept": ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"}
        ),
    )


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar("GASTO", solo_base=True)


class DatosTransferenciaForm(FormularioConfigurableMixin, forms.Form):
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
    )
    identificacion = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["identificacion"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["identificacion"],
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
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
    )
    correo_comprobante = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["correo_comprobante"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["correo_comprobante"],
        widget=forms.TextInput(
            attrs={"class": "form-control", "autocomplete": "off", "inputmode": "email"}
        ),
    )
    centro_costo = forms.CharField(
        label=ETIQUETAS_DATOS_TRANSFERENCIA["centro_costo"],
        required=False,
        max_length=LONGITUDES_DATOS_TRANSFERENCIA["centro_costo"],
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )

    def __init__(self, *args: Any, centro_costo_default: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.centro_costo_default = centro_costo_default
        self.datos_transferencia: dict[str, str] | None = None
        self.configurar("GASTO", solo_base=True, solo_textos=True)

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
        label="Reemplazar documento",
        required=False,
        choices=(("", "Cargar como documento nuevo"),),
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
        if len(procedencias) == 1:
            self.procedencia_unica: str | None = procedencias[0]
            campo_procedencia = self.fields["procedencia"]
            campo_procedencia.widget = forms.HiddenInput()
            campo_procedencia.required = False
            campo_procedencia.initial = self.procedencia_unica
            campo_procedencia.choices = [
                (
                    self.procedencia_unica,
                    etiquetas_procedencia.get(self.procedencia_unica, self.procedencia_unica),
                ),
            ]
            campo_procedencia.bound_data = lambda data, initial: data or initial
        else:
            self.procedencia_unica = None
            self.fields["procedencia"].choices = [
                ("", "Seleccione una procedencia"),
                *((codigo, etiquetas_procedencia[codigo]) for codigo in procedencias),
            ]
        self.fields["reemplaza_id"].choices = [
            ("", "Cargar como documento nuevo"),
            *(
                (
                    documento_id,
                    f"{version.tipo_mostrado} — {version.nombre} — versión {version.version}",
                )
                for documento_id, version in self.versiones_reemplazables.items()
            ),
        ]
        if not self.versiones_reemplazables:
            # Sin versiones reemplazables el selector sólo tendría la opción
            # "documento nuevo": se conserva el campo como hidden para el POST.
            campo_reemplazo = self.fields["reemplaza_id"]
            campo_reemplazo.widget = forms.HiddenInput()
            campo_reemplazo.required = False
            campo_reemplazo.choices = [("", "")]

    def clean_procedencia(self) -> str:
        procedencia = (self.cleaned_data.get("procedencia") or "").strip()
        if self.procedencia_unica:
            if not procedencia:
                return self.procedencia_unica
            if procedencia != self.procedencia_unica:
                raise ValidationError(
                    self.fields["procedencia"].error_messages["invalid_choice"],
                    code="invalid_choice",
                )
            return self.procedencia_unica
        return self.cleaned_data.get("procedencia", "")

    def clean(self):
        datos = super().clean()
        if self.procedencia_unica:
            if "procedencia" not in self.errors:
                if not datos.get("procedencia"):
                    datos["procedencia"] = self.procedencia_unica
                    self.cleaned_data["procedencia"] = self.procedencia_unica
                elif datos.get("procedencia") != self.procedencia_unica:
                    self.add_error(
                        "procedencia",
                        self.fields["procedencia"].error_messages["invalid_choice"],
                    )
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


_RE_ASCII_SIN_SEPARADORES = re.compile(r"^[+-]?\d+(?:\.\d{1,2})?$")
_RE_ASCII_CON_MILES = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+\.\d{1,2}$")
_RE_ASCII_SOLO_MILES = re.compile(r"^[+-]?\d{1,3}(?:,\d{3}){2,}$")
_RE_ES_AR_SIN_MILES = re.compile(r"^[+-]?\d+,\d{1,2}$")
_RE_ES_AR_CON_MILES = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3})+,\d{1,2}$")
_RE_ES_AR_SOLO_MILES = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3}){2,}$")


def normalizar_importe_monetario(valor: Any, nombre_campo: str = "importe") -> str:
    """Normaliza un importe escrito/pegado en es-AR o estándar a formato ASCII '0.00'.

    Acepta formato estándar ASCII (punto decimal, coma de miles opcional bien agrupada)
    o formato es-AR (coma decimal, punto de miles opcional bien agrupado).
    Los formatos ambiguos (como '1.234' o '1,234') o malformados (como '1.2.3')
    se preservan sin alterar para que la validación autoritativa del servicio C03
    los rechace conforme a su contrato riguroso.
    """
    if valor in (None, ""):
        return ""
    texto = str(valor).strip()
    if not texto:
        return ""
    sin_prefijo = texto
    if sin_prefijo.startswith("$"):
        sin_prefijo = sin_prefijo[1:].strip()

    if _RE_ASCII_SIN_SEPARADORES.fullmatch(sin_prefijo):
        return sin_prefijo
    if _RE_ASCII_CON_MILES.fullmatch(sin_prefijo) or _RE_ASCII_SOLO_MILES.fullmatch(sin_prefijo):
        return sin_prefijo.replace(",", "")
    if _RE_ES_AR_SIN_MILES.fullmatch(sin_prefijo):
        return sin_prefijo.replace(",", ".")
    if _RE_ES_AR_CON_MILES.fullmatch(sin_prefijo) or _RE_ES_AR_SOLO_MILES.fullmatch(sin_prefijo):
        return sin_prefijo.replace(".", "").replace(",", ".")

    return texto


class PagoExternoForm(forms.Form):
    """Captura del pago externo documentado.

    El formulario sólo comprueba presencia y pertenencia de la opción documental
    al listado vigente. La normalización autoritativa de importes, fecha,
    referencias, neto derivado y archivos PDF corresponde al servicio C03
    ``gastos.payments.registrar_pago_externo``. El neto no se envía como
    autoridad: se muestra calculado y el servidor lo deriva.
    """

    monto_bruto = forms.CharField(
        label="Monto bruto · ARS",
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "0,00",
                "data-campo": "bruto",
            }
        ),
        help_text=(
            "Monto real de la operación. Viene precargado desde el estimado "
            "y podés editarlo."
        ),
    )
    monto_retencion_atp = forms.CharField(
        label="Retención registrada · ARS",
        initial="0,00",
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "0,00",
                "data-campo": "retencion",
            }
        ),
        help_text="Importe informado por ATP. No se aplica una alícuota automáticamente.",
    )
    fecha_pago = forms.CharField(
        label="Fecha del pago",
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "type": "date",
                "autocomplete": "off",
            }
        ),
        error_messages={"required": "La fecha de pago es obligatoria."},
    )
    referencia_externa = forms.CharField(
        label="Número de operación / referencia bancaria",
        required=False,
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "Si figura en el comprobante",
            }
        ),
        help_text="Opcional. Si figura en el comprobante.",
    )
    referencia_atp = forms.CharField(
        label="Referencia de la constancia ATP",
        required=False,
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "Si figura en la constancia",
            }
        ),
    )
    referencia_documental = forms.ChoiceField(
        label="Comprobante comercial (factura o proforma)",
        choices=(),
        widget=forms.Select(attrs={"class": "form-control", "data-campo": "respaldo"}),
        help_text=(
            "Factura, presupuesto o proforma vigente del gasto. "
            "No es el comprobante bancario."
        ),
        error_messages={
            "required": "Seleccione un documento de respaldo.",
            "invalid_choice": (
                "La opción documental seleccionada no está disponible para este gasto."
            ),
        },
    )
    comprobante_bancario = forms.FileField(
        label="Comprobante bancario",
        required=True,
        widget=forms.FileInput(
            attrs={
                "accept": "application/pdf,.pdf,image/jpeg,.jpg,.jpeg,image/png,.png",
                "class": "rp-file-input",
                "data-doc": "banco",
            }
        ),
        help_text=(
            "Comprobante de la transferencia ya realizada (PDF o imagen). "
            "Es obligatorio para registrar el pago."
        ),
        error_messages={"required": "Seleccioná el comprobante bancario (PDF o imagen)."},
    )
    constancia_atp = forms.FileField(
        label="Constancia de retención ATP",
        required=False,
        widget=forms.FileInput(
            attrs={
                "accept": "application/pdf,.pdf",
                "class": "rp-file-input",
                "data-doc": "atp",
            }
        ),
    )
    atp_decision = forms.ChoiceField(
        label="Constancia ATP",
        required=False,
        initial="ahora",
        choices=(
            ("ahora", "Adjuntarla ahora"),
            ("despues", "La incorporaré después"),
        ),
        widget=forms.RadioSelect(attrs={"class": "rp-radio"}),
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

    def clean_monto_bruto(self) -> str:
        bruto_raw = self.cleaned_data.get("monto_bruto", "")
        return normalizar_importe_monetario(bruto_raw, "monto_bruto")

    def clean_monto_retencion_atp(self) -> str:
        retencion_raw = self.cleaned_data.get("monto_retencion_atp", "")
        if retencion_raw in (None, ""):
            return "0.00"
        return normalizar_importe_monetario(retencion_raw, "monto_retencion_atp")

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        bruto_str = cleaned_data.get("monto_bruto")
        retencion_str = cleaned_data.get("monto_retencion_atp")
        if bruto_str and retencion_str:
            try:
                bruto = Decimal(bruto_str)
                retencion = Decimal(retencion_str)
                if retencion >= bruto:
                    self.add_error(
                        "monto_retencion_atp",
                        "La retención debe ser menor que el monto bruto.",
                    )
            except Exception:
                pass

        atp_decision = cleaned_data.get("atp_decision")
        constancia_atp = cleaned_data.get("constancia_atp")
        referencia_atp = (cleaned_data.get("referencia_atp") or "").strip()

        if atp_decision == "despues":
            if constancia_atp:
                self.add_error(
                    "constancia_atp",
                    "Al diferir la constancia ATP no se debe adjuntar un archivo.",
                )
            if referencia_atp:
                self.add_error(
                    "referencia_atp",
                    "Al diferir la constancia ATP no se debe informar una referencia.",
                )
        elif retencion_str:
            try:
                retencion = Decimal(retencion_str)
                if retencion == Decimal("0.00"):
                    if constancia_atp:
                        self.add_error(
                            "constancia_atp",
                            "Con retención cero no corresponde incorporar una constancia ATP.",
                        )
            except Exception:
                pass
        return cleaned_data


class RectificacionPagoForm(forms.Form):
    """Rectificación de datos efectivos y del comprobante bancario."""

    version_esperada = forms.IntegerField(widget=forms.HiddenInput)
    motivo = forms.CharField(
        label="Motivo de la rectificación",
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Explicá qué corregís y por qué.",
            }
        ),
        error_messages={"required": "El motivo de la rectificación es obligatorio."},
    )
    fecha_pago = forms.CharField(
        label="Fecha del pago",
        strip=False,
        widget=forms.TextInput(attrs={"class": "form-control", "type": "date"}),
    )
    monto_bruto = forms.CharField(
        label="Monto bruto · ARS",
        strip=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal", "data-campo": "bruto"}
        ),
    )
    monto_retencion_atp = forms.CharField(
        label="Retención registrada · ARS",
        strip=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "data-campo": "retencion",
            }
        ),
    )
    referencia_externa = forms.CharField(
        label="Número de operación / referencia bancaria",
        required=False,
        strip=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    referencia_atp = forms.CharField(
        label="Referencia de la constancia ATP",
        required=False,
        strip=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    comprobante_bancario = forms.FileField(
        label="Reemplazar comprobante bancario",
        required=False,
        widget=forms.FileInput(
            attrs={
                "accept": "application/pdf,.pdf,image/jpeg,.jpg,.jpeg,image/png,.png",
                "class": "rp-file-input",
                "data-doc": "banco",
            }
        ),
        help_text="Opcional. Si lo reemplazás, la versión anterior se conserva.",
    )

    def clean_monto_bruto(self) -> str:
        bruto_raw = self.cleaned_data.get("monto_bruto", "")
        return normalizar_importe_monetario(bruto_raw, "monto_bruto")

    def clean_monto_retencion_atp(self) -> str:
        retencion_raw = self.cleaned_data.get("monto_retencion_atp", "")
        if retencion_raw in (None, ""):
            return "0.00"
        return normalizar_importe_monetario(retencion_raw, "monto_retencion_atp")

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        bruto_str = cleaned_data.get("monto_bruto")
        retencion_str = cleaned_data.get("monto_retencion_atp")
        if bruto_str and retencion_str:
            try:
                bruto = Decimal(bruto_str)
                retencion = Decimal(retencion_str)
                if retencion >= bruto:
                    self.add_error(
                        "monto_retencion_atp",
                        "La retención debe ser menor que el monto bruto.",
                    )
            except Exception:
                pass
        return cleaned_data


class ConstanciaATPForm(forms.Form):
    """Aporte posterior de la constancia ATP con motivo y versión esperada."""

    version_esperada = forms.IntegerField(widget=forms.HiddenInput)
    motivo = forms.CharField(
        label="Motivo del aporte",
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Explicá por qué incorporás la constancia ahora.",
            }
        ),
        error_messages={"required": "El motivo del aporte es obligatorio."},
    )
    constancia_atp = forms.FileField(
        label="Constancia de retención ATP",
        required=True,
        widget=forms.FileInput(
            attrs={
                "accept": "application/pdf,.pdf",
                "class": "rp-file-input",
                "data-doc": "atp",
            }
        ),
        error_messages={"required": "Seleccioná el PDF de la constancia ATP."},
    )


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

