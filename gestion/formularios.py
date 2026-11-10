"""Configuración declarativa: textos y respuestas, sin código ejecutable."""

import copy
import uuid
from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from documentos.policy import ArchivoInvalido, validar_archivo

from .models import ConfiguracionFormulario, RespuestaFormulario, VersionFormulario

CIRCUITOS = (("GASTO", "Gastos"), ("FACTURACION", "Facturación"))
TIPOS = (
    ("texto", "Texto breve"),
    ("parrafo", "Cuadro de texto"),
    ("seleccion", "Lista de opciones"),
    ("multiple", "Selección múltiple"),
    ("radio", "Botones de opción"),
    ("casilla", "Casilla de confirmación"),
    ("documento", "Sección para adjuntar documento"),
    ("seccion", "Título y leyenda"),
)
OPCIONES_LIBRES = {"producto_servicio", "centro_costo", "condicion_iva"}
NO_EDITABLES = {"retirar_comprobante", "configuracion_revision"}


def clase_formulario(circuito):
    if circuito == "GASTO":
        from gastos.forms import SolicitudGastoForm

        return SolicitudGastoForm
    from facturacion.forms import SolicitudFacturacionForm

    return SolicitudFacturacionForm


def campos_base(circuito):
    campos = {
        k: v for k, v in clase_formulario(circuito).base_fields.items() if k not in NO_EDITABLES
    }
    if circuito == "GASTO":
        from gastos.forms import DatosTransferenciaForm, RespaldoSolicitudForm

        for origen in (DatosTransferenciaForm, RespaldoSolicitudForm):
            for clave, campo in origen.base_fields.items():
                campos.setdefault(clave, campo)
    else:
        campos["centro_costo"] = copy.deepcopy(campos["centro_costo"])
        campos["centro_costo"].choices = [
            (k, v) for k, v in campos["centro_costo"].choices if k != "OPCION_35"
        ]
    return campos


def protegido(circuito, clave):
    return clave in campos_base(circuito) and clave not in {
        "observaciones",
        "centro_costo",
        "respaldo_archivo",
    }


def configuracion(circuito):
    registro = ConfiguracionFormulario.objects.filter(circuito=circuito).first()
    return (registro.revision, copy.deepcopy(registro.campos)) if registro else (0, [])


def opciones_campo(campo):
    if isinstance(campo, forms.ModelChoiceField):
        return []
    return [[str(k), str(v)] for k, v in getattr(campo, "choices", []) if k]


def esquema_editor(circuito):
    revision, guardados = configuracion(circuito)
    por_clave = {c["clave"]: c for c in guardados}
    resultado = []
    for clave, campo in campos_base(circuito).items():
        valor = dict(
            clave=clave,
            etiqueta=str(campo.label or clave),
            ayuda=str(campo.help_text),
            requerido=campo.required,
            activo=True,
            tipo="base",
            opciones=opciones_campo(campo),
            orden=len(resultado),
        )
        valor.update(por_clave.pop(clave, {}))
        valor["protegido"] = protegido(circuito, clave)
        valor["opciones_editables"] = bool(valor["opciones"])
        resultado.append(valor)
    resultado.extend(
        dict(c, protegido=False, opciones_editables=c["tipo"] in {"seleccion", "multiple", "radio"})
        for c in por_clave.values()
    )
    return revision, sorted(resultado, key=lambda c: c["orden"])


class CampoEdicionForm(forms.Form):
    etiqueta = forms.CharField(label="Nombre del campo o sección", max_length=200)
    ayuda = forms.CharField(
        label="Leyenda o texto explicativo",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    tipo = forms.ChoiceField(label="Tipo de campo", choices=TIPOS)
    requerido = forms.BooleanField(label="Obligatorio", required=False)
    activo = forms.BooleanField(label="Visible en nuevas solicitudes", required=False, initial=True)
    orden = forms.IntegerField(label="Posición", min_value=0, max_value=1000, initial=100)
    opciones = forms.CharField(
        label="Opciones: una por línea, con formato código | texto",
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text="Retirar opciones conserva las respuestas históricas.",
    )
    revision = forms.IntegerField(widget=forms.HiddenInput, min_value=0)

    def __init__(self, *args, circuito, clave=None, **kwargs):
        self.circuito, self.clave = circuito, clave
        self.original = campos_base(circuito).get(clave)
        self.opciones_visibles = bool(self.original and opciones_campo(self.original))
        revision, campos = esquema_editor(circuito)
        campo = next((c for c in campos if c["clave"] == clave), None)
        if campo:
            initial = dict(campo, opciones="\n".join(f"{k} | {v}" for k, v in campo["opciones"]))
        else:
            initial = dict(tipo="texto", activo=True, orden=len(campos))
        initial["revision"] = revision
        super().__init__(*args, initial=initial, **kwargs)
        if self.original:
            self.fields["tipo"].choices = [("base", "Campo del circuito")]
            self.fields["tipo"].disabled = True
            self.fields["orden"].disabled = True
            self.fields["orden"].help_text = "Los campos del circuito conservan su posición."
            if protegido(circuito, clave):
                self.fields["requerido"].disabled = True
                self.fields["activo"].disabled = True
                self.fields["requerido"].help_text = "Requisito protegido del circuito."
            if isinstance(self.original, forms.ModelChoiceField):
                self.fields["opciones"].disabled = True
                self.fields[
                    "opciones"
                ].help_text = "Administrá estas opciones en Catálogos y parámetros."

    def clean_opciones(self):
        texto = self.cleaned_data["opciones"]
        resultado = []
        for linea in texto.splitlines():
            if not linea.strip():
                continue
            partes = [p.strip() for p in linea.split("|", 1)]
            limite = 30 if self.clave == "condicion_iva" else 50
            if len(partes) != 2 or not all(partes) or len(partes[0]) > limite:
                raise ValidationError(f"Usá código | texto; código de hasta {limite} caracteres.")
            if partes[0] in {p[0] for p in resultado}:
                raise ValidationError("No se admiten códigos repetidos.")
            resultado.append(partes)
        if self.original and self.clave not in OPCIONES_LIBRES:
            validos = {c[0] for c in opciones_campo(self.original)}
            if any(c[0] not in validos for c in resultado):
                raise ValidationError("Campo esencial: conservá sus códigos.")
            if validos and {c[0] for c in resultado} != validos:
                raise ValidationError("Renombrá las opciones esenciales sin retirarlas.")
        return resultado

    def clean(self):
        datos = super().clean()
        tipo = datos.get("tipo")
        necesita = tipo in {"seleccion", "multiple", "radio"} or (
            self.original is not None and bool(opciones_campo(self.original))
        )
        if necesita and not datos.get("opciones"):
            self.add_error("opciones", "Definí al menos una opción.")
        if tipo == "seccion":
            datos["requerido"] = False
        if not necesita:
            datos["opciones"] = []
        return datos


@transaction.atomic
def guardar_campo(actor, circuito, clave, datos):
    from django.core.exceptions import PermissionDenied

    from identidad.services import has_capability

    if not has_capability(actor, "gestion.configurar"):
        raise PermissionDenied
    if circuito not in dict(CIRCUITOS):
        raise ValidationError("Circuito inválido.")
    config, _ = ConfiguracionFormulario.objects.get_or_create(circuito=circuito)
    config = ConfiguracionFormulario.objects.select_for_update().get(pk=config.pk)
    form = CampoEdicionForm(datos, circuito=circuito, clave=clave)
    if not form.is_valid():
        raise ValidationError(dict(form.errors))
    if form.cleaned_data["revision"] != config.revision:
        raise ValidationError("La configuración cambió. Recargá la pantalla antes de guardar.")
    clave = clave or f"extra_{uuid.uuid4().hex[:12]}"
    if not any(c["clave"] == clave for c in esquema_editor(circuito)[1]) and not clave.startswith(
        "extra_"
    ):
        raise ValidationError("Campo inexistente.")
    valor = {k: v for k, v in form.cleaned_data.items() if k != "revision"}
    valor["clave"] = clave
    campos = [c for c in config.campos if c["clave"] != clave] + [valor]
    config.campos = campos
    config.revision += 1
    config.save(update_fields=["campos", "revision"])
    VersionFormulario.objects.create(
        configuracion=config, revision=config.revision, campos=campos, actor_id=actor.subject_id
    )
    return clave


class AdjuntoConfigurable(forms.FileField):
    def clean(self, data, initial=None):
        archivo = super().clean(data, initial)
        if archivo:
            try:
                validar_archivo(archivo)
            except ArchivoInvalido as exc:
                raise ValidationError(str(exc)) from exc
            archivo.seek(0)
        return archivo


class FormularioConfigurableMixin:
    def configurar(self, circuito, tramite=None, solo_base=False, solo_textos=False):
        self.circuito_config = circuito
        self.config_solo_base = solo_base
        self.config_revision, self.config_campos = configuracion(circuito)
        self.campos_adicionales = []
        anterior = tramite.respuestas_formulario.order_by("-pk").first() if tramite else None
        self.respuestas_previas = anterior.datos if anterior else {}
        for c in sorted(self.config_campos, key=lambda c: c["orden"]):
            clave = c["clave"]
            if c["tipo"] == "base":
                campo = self.fields.get(clave)
                if campo is None:
                    continue
                campo.label, campo.help_text = c["etiqueta"], c["ayuda"]
                if not solo_textos and not protegido(circuito, clave):
                    campo.required = c["requerido"]
                    if not c["activo"]:
                        campo.disabled, campo.required = True, False
                        campo.widget = forms.HiddenInput()
                if (
                    not solo_textos
                    and c["opciones"]
                    and not isinstance(campo, forms.ModelChoiceField)
                ):
                    campo.choices = [("", "Seleccioná…"), *c["opciones"]]
                continue
            if solo_base or not c["activo"]:
                continue
            kwargs = dict(label=c["etiqueta"], help_text=c["ayuda"], required=c["requerido"])
            tipo = c["tipo"]
            if tipo == "documento":
                from django.conf import settings

                mib = settings.DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
                kwargs["help_text"] += f" PDF, JPEG o PNG; hasta {mib:g} MiB."
                campo = AdjuntoConfigurable(**kwargs)
            elif tipo == "multiple":
                campo = forms.MultipleChoiceField(choices=c["opciones"], **kwargs)
            elif tipo in {"seleccion", "radio"}:
                campo = forms.ChoiceField(choices=[("", "Seleccioná…"), *c["opciones"]], **kwargs)
                if tipo == "radio":
                    campo.widget = forms.RadioSelect(choices=campo.choices)
            elif tipo == "casilla":
                campo = forms.BooleanField(**kwargs)
            else:
                campo = forms.CharField(max_length=4000, **kwargs)
                if tipo == "parrafo":
                    campo.widget = forms.Textarea(attrs={"rows": 3})
                if tipo == "seccion":
                    campo.disabled, campo.required = True, False
                    campo.widget = forms.HiddenInput()
            if clave in self.respuestas_previas:
                previo = self.respuestas_previas[clave]
                self.initial.setdefault(clave, previo.get("entrada"))
                if tipo == "documento" and previo.get("documento_id"):
                    campo.required = False
                    campo.help_text += " Se conserva el adjunto anterior si no lo reemplazás."
            campo.es_seccion = tipo == "seccion"
            self.fields[clave] = campo
            self.campos_adicionales.append(clave)
        if solo_base:
            return
        self.fields["configuracion_revision"] = forms.IntegerField(
            initial=self.config_revision, required=False, widget=forms.HiddenInput()
        )

    def clean(self):
        datos = super().clean()
        if self.config_solo_base:
            return datos
        if datos.get("configuracion_revision", 0) not in {self.config_revision, None} or (
            self.config_revision and datos.get("configuracion_revision") is None
        ):
            raise ValidationError("El formulario cambió. Volvé a abrirlo.")
        return datos


def guardar_respuesta(*, actor, tramite, form, escrituras=None):
    config, _ = ConfiguracionFormulario.objects.get_or_create(circuito=form.circuito_config)
    config = ConfiguracionFormulario.objects.select_for_update().get(pk=config.pk)
    if config.revision != form.config_revision:
        raise ValidationError("El formulario cambió durante el envío. Volvé a abrirlo.")
    if not form.config_campos:
        return
    from documentos.services import incorporar

    datos = {}
    base_editados = [
        c["clave"]
        for c in form.config_campos
        if c["tipo"] == "base"
        and c["activo"]
        and c["clave"] in form.fields
        and not isinstance(form.fields[c["clave"]], forms.FileField)
    ]
    for clave in [*base_editados, *form.campos_adicionales]:
        campo = form.fields[clave]
        if getattr(campo, "es_seccion", False):
            continue
        valor = form.cleaned_data.get(clave)
        item = dict(etiqueta=campo.label, valor=valor, entrada=valor, tipo="texto")
        if isinstance(campo, forms.FileField):
            item["tipo"] = "documento"
            item["entrada"] = None
            if not valor:
                previo = form.respuestas_previas.get(clave, {})
                if previo.get("documento_id"):
                    item.update(
                        valor=previo["valor"], documento_id=previo["documento_id"], tipo="documento"
                    )
                else:
                    item["valor"] = "Sin adjunto"
            else:
                if escrituras is None:
                    raise ValidationError("El adjunto requiere una operación documental completa.")
                documento = incorporar(
                    actor=actor,
                    referencia=str(tramite.referencia),
                    archivo=valor,
                    tipo="ANEXO_SOLICITUD",
                    procedencia="SOLICITANTE",
                    _escrituras=escrituras,
                )
                item.update(
                    valor=documento.nombre_original, documento_id=documento.pk, tipo="documento"
                )
        elif isinstance(campo, forms.ModelChoiceField):
            item["entrada"] = str(valor.pk) if valor is not None else ""
            item["valor"] = str(valor) if valor is not None else ""
        elif isinstance(valor, date | Decimal):
            item["entrada"] = str(valor)
            item["valor"] = str(valor)
        elif isinstance(campo, forms.MultipleChoiceField):
            etiquetas = dict(campo.choices)
            item["valor"] = ", ".join(etiquetas[v] for v in valor)
        elif isinstance(valor, bool):
            item["valor"] = "Sí" if valor else "No"
        elif isinstance(campo, forms.ChoiceField):
            item["valor"] = dict(campo.choices).get(valor, valor)
        datos[clave] = item
    RespuestaFormulario.objects.create(
        tramite=tramite,
        actor_id=actor.subject_id,
        revision=config.revision,
        campos=form.config_campos,
        datos=datos,
    )
