"""Configuración del componente de identidad de demostración y acceso local."""

from django.apps import AppConfig


class IdentidadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "identidad"

    def ready(self) -> None:
        """Conecta manejadores de señales para revocación estricta de tokens."""
        import identidad.tokens_local  # noqa: F401
