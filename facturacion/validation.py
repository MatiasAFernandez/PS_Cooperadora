"""Validadores reutilizados en formularios, modelos y servicios de facturación."""

import re

from django.core.exceptions import ValidationError


def validar_cuit(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{11}", value):
        raise ValidationError("Ingresá los 11 dígitos del CUIT, sin separadores.")
    suma = sum(int(n) * p for n, p in zip(value[:10], (5, 4, 3, 2, 7, 6, 5, 4, 3, 2), strict=True))
    digito = 11 - suma % 11
    digito = 0 if digito == 11 else 9 if digito == 10 else digito
    if int(value[-1]) != digito:
        raise ValidationError("El dígito verificador del CUIT no es válido.")
