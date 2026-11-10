"""Datos de entrada compartidos por HTTP y servicios; no confían en ModelForm.save."""

from decimal import Decimal

from django import forms

from comunes.filtros import FiltroFechaForm
from gestion.formularios import FormularioConfigurableMixin

from .choices import CentroCosto, CondicionIVA, ModalidadCobro, ProductoServicio
from .validation import validar_cuit


class SolicitudFacturacionForm(FormularioConfigurableMixin, forms.Form):
    presento_comprobante_pago = forms.TypedChoiceField(
        label="¿Presentaste comprobante de pago?",
        choices=[("", "Seleccioná…"), ("True", "Sí"), ("False", "No")],
        coerce=lambda val: val == "True",
        empty_value=None,
        help_text=(
            "Si elegís Sí, completá la fecha y el número de operación y adjuntá el comprobante."
        ),
    )
    nombre_solicitante = forms.CharField(label="Nombre del solicitante", max_length=200)
    cuit_receptor = forms.CharField(
        label="CUIT del receptor", validators=[validar_cuit], max_length=11
    )
    nombre_receptor = forms.CharField(label="Nombre o razón social del receptor", max_length=255)
    condicion_iva = forms.ChoiceField(label="Condición ante el IVA", choices=CondicionIVA.choices)
    email_envio_factura = forms.EmailField(
        label="Correo para enviar la factura",
        max_length=254,
        help_text="Cooperadora enviará la factura a esta dirección.",
    )
    detalle_factura = forms.CharField(label="Detalle de la factura", widget=forms.Textarea)
    importe_factura = forms.DecimalField(
        label="Importe solicitado",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    producto_servicio = forms.ChoiceField(
        label="Producto o servicio", choices=ProductoServicio.choices
    )
    centro_costo = forms.ChoiceField(label="Centro de costo", choices=CentroCosto.choices)
    modalidad_cobro = forms.ChoiceField(label="Medio o cuenta", choices=ModalidadCobro.choices)
    observaciones = forms.CharField(
        label="Observaciones (opcional)", widget=forms.Textarea, required=False
    )
    fecha_operacion_declarada = forms.DateField(
        label="Fecha de operación declarada",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    numero_operacion_declarado = forms.CharField(
        label="Número de operación declarada",
        max_length=100,
        required=False,
    )
    archivo_comprobante = forms.FileField(
        label="Comprobante de pago declarado",
        required=False,
        help_text="PDF, JPEG o PNG de hasta 10 MiB. El archivo anterior queda en el historial.",
    )
    retirar_comprobante = forms.BooleanField(
        label="Retirar el documento de respaldo vigente (se conserva en el historial)",
        required=False,
    )

    def __init__(self, *args, documento_actual=False, tramite_config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.documento_actual = documento_actual
        self.fields["centro_costo"].choices = [
            (valor, etiqueta) for valor, etiqueta in CentroCosto.choices
            if valor != "OPCION_35"
        ]
        orden = list(self.fields)
        orden.remove("presento_comprobante_pago")
        orden.insert(orden.index("fecha_operacion_declarada"), "presento_comprobante_pago")
        self.order_fields(orden)
        self.configurar("FACTURACION", tramite=tramite_config)

    def clean(self):
        data = super().clean()
        if data.get("retirar_comprobante") and data.get("archivo_comprobante"):
            self.add_error("retirar_comprobante", "Elegí retirar o reemplazar, no ambas acciones.")
        if data.get("presento_comprobante_pago"):
            for field in ("fecha_operacion_declarada", "numero_operacion_declarado"):
                if not data.get(field) and not self.has_error(field):
                    self.add_error(field, "Este dato es obligatorio al declarar un pago.")
            conserva = self.documento_actual and not data.get("retirar_comprobante")
            if not data.get("archivo_comprobante") and not conserva and not self.has_error(
                "archivo_comprobante"
            ):
                self.add_error("archivo_comprobante", "Adjuntá el comprobante del pago declarado.")
        return data


class FiltroFacturacionForm(FiltroFechaForm):
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=[
            ("", "Todos los estados"),
            ("PRESENTADA", "Presentada"),
            ("OBSERVADA", "Observada"),
            ("FACTURADA_PENDIENTE_COBRO", "Facturada pendiente de cobro"),
            ("COBRADA_EN_REVISION", "Cobrada en revisión"),
            ("CERRADA", "Cerrada"),
            ("ANULADA", "Anulada"),
        ],
    )
    q = forms.CharField(
        label="Buscar solicitud, solicitante, receptor, CUIT o detalle",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"type": "search"}),
    )
