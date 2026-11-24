import math
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()

_DOS_DECIMALES = Decimal("0.01")
_CUIT_DIGITOS = re.compile(r"^\d{11}$")

_ESTADOS_HISTORIAL = {
    "PRESENTADA": "Presentada",
    "OBSERVADA": "Observada",
    "FACTURADA_PENDIENTE_COBRO": "Facturada pendiente de cobro",
    "COBRADA_EN_REVISION": "Cobrada en revisión",
    "CERRADA": "Cerrada",
    "ANULADA": "Anulada",
    "PENDIENTE": "Pendiente",
    "CONFIRMADO": "Confirmado",
    "RECHAZADO": "Rechazado",
    "RECTIFICADO": "Rectificado",
    "ACEPTADO": "Aceptado",
    "OBSERVADO": "Observado",
    "REGISTRADO": "Registrado",
    "CORREGIDO": "Corregido",
    "ACTUALIZADO": "Actualizado",
    "ENVIADO": "Enviado",
    "RECIBIDO": "Recibido",
    "VINCULO_ACTUALIZADO": "Vínculo actualizado",
}


def _parsear_decimal(valor):
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, Decimal):
        return valor if valor.is_finite() else None
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        if not math.isfinite(valor):
            return None
        return Decimal(str(valor))
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        try:
            numero = Decimal(texto)
        except InvalidOperation:
            if "," in texto and "." not in texto:
                texto = texto.replace(",", ".")
            elif "." in texto and "," in texto and texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                return None
            try:
                numero = Decimal(texto)
            except InvalidOperation:
                return None
        return numero if numero.is_finite() else None
    return None


@register.filter(name="ars")
def ars(valor):
    """Formatea un importe numérico o Decimal como moneda ARS (`$ 195.000,00`)."""
    numero = _parsear_decimal(valor)
    if numero is None:
        return "—"

    cuantizado = numero.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)
    if cuantizado == 0:
        return "$ 0,00"

    es_negativo = cuantizado < 0
    entero, decimales = f"{abs(cuantizado):.2f}".split(".")
    entero_con_miles = f"{int(entero):,}".replace(",", ".")
    importe = f"$ {entero_con_miles},{decimales}"
    return f"-{importe}" if es_negativo else importe


@register.filter(name="cuit")
def cuit(valor):
    """Formatea un CUIT/CUIL de 11 dígitos como `XX-XXXXXXXX-X`."""
    if valor is None or isinstance(valor, bool):
        return "—"
    texto = str(valor).strip()
    if not texto:
        return "—"
    digitos = texto.replace("-", "").replace(" ", "")
    if _CUIT_DIGITOS.fullmatch(digitos):
        return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"
    return texto


@register.filter(name="actor_visible")
def actor_visible(actor_id, mapa=None):
    """Resuelve el rótulo visible del actor desde un mapa opcional; cae en `actor #<id>`."""
    clave = str(actor_id)
    if isinstance(mapa, dict) and clave in mapa and mapa[clave]:
        return mapa[clave]
    return f"actor #{clave}"


@register.filter(name="estado_historial")
def estado_historial(valor):
    """Humaniza códigos técnicos de estado en eventos de historial."""
    if valor is None:
        return "—"
    texto = str(valor).strip()
    if not texto:
        return "—"
    return _ESTADOS_HISTORIAL.get(texto, texto)
