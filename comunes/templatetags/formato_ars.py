import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()

_DOS_DECIMALES = Decimal("0.01")


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
