"""Contratos y puertos de integración para el módulo de gastos.

Define los contratos exigidos por gastos hacia otros módulos o proveedores externos,
en particular el puerto consumidor de verificación y bloqueo documental según SPEC-011.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from gastos.models import SolicitudGasto

TIPOS_DOCUMENTO_ADMITIDOS_PAGO: tuple[str, ...] = (
    "factura",
    "presupuesto",
    "proforma",
)


class DocumentVerificationError(Exception):
    """Error emitido cuando el proveedor no puede validar o bloquear el documento."""


@dataclass(frozen=True, slots=True)
class DocumentoVerificado:
    """Evidencia de versión inmutable de documento bloqueada por el proveedor.

    Representa la confirmación de que el proveedor documental ha validado y
    bloqueado con éxito la versión inmutable dentro de la transacción activa.
    Incluye la referencia inequívoca a la solicitud de gasto a la que se validó
    (`solicitud_id`), la referencia opaca y el tipo de documento confirmado.
    No expone contenido binario, rutas de archivo ni metadatos sensibles.

    `gasto_id` se conserva como alias de sólo lectura de `solicitud_id` para no
    romper consumidores previos que usaban ese nombre.
    """

    solicitud_id: int
    referencia_documental: str
    tipo_documento: str

    @property
    def gasto_id(self) -> int:
        """Alias equivalente de `solicitud_id` (referencia inequívoca al gasto)."""
        return self.solicitud_id


@runtime_checkable
class DocumentVerificationPort(Protocol):
    """Puerto consumidor de verificación y bloqueo de versión documental.

    Responsabilidad de implementación: Proveedor de documentos (Matías, Issue #19).
    Este puerto vive del lado de gastos y define las garantías contractuales obligatorias
    que debe proveer cualquier adaptador documental dentro del circuito de pago:

    1. Transaccionalidad: La llamada se ejecuta DENTRO de la misma transacción atómica
       iniciada por el servicio de gastos (select_for_update sobre gasto precede a la versión).
    2. Existencia: El documento y su versión exacta deben existir y estar confirmados.
    3. Pertenencia (FK): El documento debe pertenecer de forma exclusiva y directa al trámite
       o solicitud de gasto indicada (no es reutilizable ni transferible entre gastos).
    4. Tipo admitido: Debe coincidir con los tipos documentalmente admitidos para el pago
       (p. ej. factura, presupuesto, proforma).
    5. Vigencia de versión: El método del proveedor retorna únicamente tras confirmar que
       la versión referenciada es la versión vigente del documento (si hubo reemplazos,
       el reemplazo genera una nueva versión inmutable preservando las anteriores; una versión
       histórica o reemplazada no es vigente para registrar un pago).
    6. Bloqueo hasta commit: El proveedor debe mantener un bloqueo pesimista a nivel BD
       sobre la fila de versión documental hasta el commit o rollback de esta transacción.
    7. Inmutabilidad y opacidad: Retorna una evidencia DocumentoVerificado con solicitud_id,
       referencia_documental y tipo_documento. No expone archivo físico, contenido binario
       ni metadatos adicionales al módulo de gastos.
    8. Revisión en demo: Un estado de revisión desconocido o ausente no impide este recorrido
       técnico, pero no se presenta como aprobación ni como cumplimiento de una factura
       definitiva pendiente. Las reglas institucionales de revisión siguen pendientes.

    NOTA DE ARQUITECTURA:
    No se proporciona ningún proveedor por defecto, stub productivo ni modelo duplicado.
    El servicio de registro de pago exige este puerto como argumento obligatorio.
    Los dobles de prueba sólo deben existir dentro de las suites de prueba.
    """

    def verificar_y_bloquear_documento(
        self,
        *,
        actor: Any,
        gasto: SolicitudGasto,
        referencia_documental: str,
        tipos_admitidos: Collection[str] = TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
    ) -> DocumentoVerificado:
        """Verifica pertenencia, tipo, vigencia y bloquea la versión del documento.

        Parámetros:
        - actor: Sujeto autenticado que realiza el registro.
        - gasto: Instancia bloqueada de SolicitudGasto a la que debe pertenecer el documento.
        - referencia_documental: Identificador opaco de la versión documental enviada.
        - tipos_admitidos: Colección de tipos de documento válidos para respaldar el pago.

        Retorna:
        - DocumentoVerificado con solicitud_id del gasto, referencia inmutable y tipo validado.

        Lanza:
        - DocumentVerificationError: si el documento no existe, no pertenece a este gasto,
          no es del tipo requerido, la versión no está vigente o no se pudo bloquear.
        """
        ...
