"""Registro del componente de facturación, propiedad de Matías."""

from django.apps import AppConfig


class FacturacionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "facturacion"
