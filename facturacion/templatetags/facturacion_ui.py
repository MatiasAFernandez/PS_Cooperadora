"""Filtros de presentación exclusivos de Facturación."""

import re
from decimal import Decimal

from django import template

from comunes.templatetags.formato_ars import ars, cuit
from facturacion.choices import ModalidadCobro

register = template.Library()

_RE_EMISOR_CUIT = re.compile(r"\bEmisor:\s*(\d{11})\b")
_RE_IMPORTE_ARS = re.compile(r"(?<!\d)(\d+\.\d{2})\s+ARS\b")
_MEDIOS = dict(ModalidadCobro.choices)
_RE_MEDIO = re.compile(
    r"\b(" + "|".join(re.escape(codigo) for codigo in _MEDIOS) + r")(?=:)"
)


@register.filter(name="detalle_historial")
def detalle_historial(texto: object) -> str:
    """Formatea CUIT, montos ARS y códigos de medio al presentar el historial de Facturación."""
    if not texto:
        return ""
    resultado = str(texto)
    resultado = _RE_EMISOR_CUIT.sub(lambda m: f"Emisor: {cuit(m.group(1))}", resultado)
    resultado = _RE_IMPORTE_ARS.sub(lambda m: ars(Decimal(m.group(1))), resultado)
    resultado = _RE_MEDIO.sub(lambda m: _MEDIOS[m.group(1)], resultado)
    return resultado
