"""Carga fail-closed del proveedor documental configurado en el servidor.

El módulo de gastos nunca construye, elige ni acepta un proveedor documental a
partir de datos enviados por el cliente (POST, query string, cabeceras o
sesión). La única fuente admitida es la configuración de servidor
`settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER`, que por defecto está ausente.

Cualquier ausencia, ruta inválida, error de importación, objeto que no cumpla el
puerto o fallo al instanciar se resuelve devolviendo `None` (fail-closed): la
capa de vista responde 503 y no se ofrece ni registra el pago.
"""

from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from gastos.contracts import DocumentVerificationPort

# Métodos obligatorios del puerto documental consumidos por gastos.
_METODOS_REQUERIDOS = (
    "verificar_y_bloquear_documento",
    "listar_opciones_para_pago",
)


def _cumple_puerto(candidato: Any) -> bool:
    """Comprueba que el candidato exponga los métodos obligatorios del puerto."""
    if candidato is None:
        return False
    return all(callable(getattr(candidato, metodo, None)) for metodo in _METODOS_REQUERIDOS)


def _resolver_configuracion(configuracion: Any) -> Any:
    """Resuelve una configuración de servidor a una instancia del puerto.

    Acepta una ruta punteada a clase, instancia o fábrica, o directamente un
    objeto ya construido. No interpreta ningún valor de origen cliente.
    """
    if isinstance(configuracion, str):
        objetivo = import_string(configuracion.strip())
    else:
        objetivo = configuracion

    # Una clase también expone sus métodos como atributos callables, pero aún no
    # es una instancia utilizable por la vista. Instanciarla antes de validarla.
    if not isinstance(objetivo, type) and _cumple_puerto(objetivo):
        return objetivo

    if isinstance(objetivo, type):
        return objetivo()

    if callable(objetivo):
        return objetivo()

    return None


def cargar_proveedor_documental() -> DocumentVerificationPort | None:
    """Devuelve el proveedor documental de servidor o `None` si no es utilizable.

    Garantías:
    - Sólo lee `settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER` (ausente por defecto).
    - Nunca deriva el proveedor de datos de la petición.
    - Falla cerrado ante cualquier error: devuelve `None` en lugar de propagar
      una excepción o aceptar un objeto incompleto.
    """
    configuracion = getattr(settings, "GASTOS_PAYMENT_DOCUMENT_PROVIDER", None)
    if configuracion is None:
        return None

    if isinstance(configuracion, str) and not configuracion.strip():
        return None

    try:
        proveedor = _resolver_configuracion(configuracion)
    except Exception:
        # Ruta inexistente, import que falla, constructor que lanza: fail-closed.
        return None

    if not _cumple_puerto(proveedor):
        return None

    return proveedor
