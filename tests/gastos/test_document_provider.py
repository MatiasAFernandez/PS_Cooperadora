"""Carga fail-closed del proveedor documental desde configuración de servidor."""

from typing import Any

from gastos.document_provider import cargar_proveedor_documental


class ProveedorConfigurado:
    """Implementación mínima para probar la carga de una clase configurada."""

    def listar_opciones_para_pago(self, **kwargs: Any) -> list[Any]:
        return []

    def verificar_y_bloquear_documento(self, **kwargs: Any) -> Any:
        return None


def test_clase_configurada_se_instancia_antes_de_validar_el_puerto(settings: Any) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = ProveedorConfigurado

    proveedor = cargar_proveedor_documental()

    assert isinstance(proveedor, ProveedorConfigurado)


def test_ruta_punteada_de_clase_configurada_se_instancia(settings: Any) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = (
        f"{ProveedorConfigurado.__module__}.{ProveedorConfigurado.__qualname__}"
    )

    proveedor = cargar_proveedor_documental()

    assert isinstance(proveedor, ProveedorConfigurado)


def test_proveedor_malformado_falla_cerrado(settings: Any) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = "ruta.inexistente.Proveedor"

    assert cargar_proveedor_documental() is None
