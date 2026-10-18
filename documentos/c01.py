"""Proveedor de Matías para el puerto C01 existente, sin reglas de pago o cierre.

El consumidor de Franco conserva su transacción e idempotencia. Este adaptador
autoriza la consulta, traduce tipos y bloquea una versión vigente hasta commit.
La referencia UUID identifica una versión exacta sin exponer rutas o contenido.
La revisión ausente sólo permite el recorrido técnico: esta evidencia no
acredita conformidad documental ni contable y no resuelve deuda o cierre.
"""

from collections.abc import Collection
from uuid import UUID

from django.db import connection
from django.db.models import OuterRef, Q, Subquery

from gastos.contracts import (
    TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
    DocumentoVerificado,
    DocumentVerificationError,
    OpcionDocumental,
)
from gastos.models import SolicitudGasto
from gastos.queries import visible_expenses
from identidad.services import Actor, has_capability

from .acceso import documentos_visibles
from .models import Documento, RevisionDocumento
from .services import bloquear_serie

# Presupuesto/proforma tiene un único tipo persistido. Se representa como
# 'presupuesto' en C01, que admite ambas clases; no se inventa una distinción.
TIPOS_C01 = {
    Documento.Tipo.FACTURA_PROVEEDOR: "factura",
    Documento.Tipo.PRESUPUESTO_PROFORMA: "presupuesto",
}


class ProveedorDocumentalGastos:
    """Implementación real optativa del puerto consumidor de gastos."""

    @staticmethod
    def _autorizar(actor: Actor | None, gasto: SolicitudGasto, *, pago: bool = False) -> None:
        metadatos = has_capability(actor, "documentos.consultar_metadatos") or has_capability(
            actor, "documentos.ver_metadatos"
        )
        if not metadatos or not visible_expenses(actor).filter(pk=gasto.pk).exists():
            raise DocumentVerificationError("Respaldo documental no disponible.")
        if pago and not has_capability(actor, "gastos.registrar_pago"):
            raise DocumentVerificationError("Respaldo documental no disponible.")

    @staticmethod
    def _tipos(tipos_admitidos: Collection[str]) -> list[str]:
        # El llamador sólo puede reducir el catálogo que admite el contrato.
        permitidos = set(tipos_admitidos) & set(TIPOS_DOCUMENTO_ADMITIDOS_PAGO)
        return [tipo for tipo, codigo in TIPOS_C01.items() if codigo in permitidos]

    def listar_opciones_para_pago(
        self,
        *,
        actor: Actor | None,
        gasto: SolicitudGasto,
        tipos_admitidos: Collection[str] = TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
    ) -> list[OpcionDocumental]:
        self._autorizar(actor, gasto)
        documentos = (
            documentos_visibles(actor)
            .annotate(ultima_revision=Subquery(
                RevisionDocumento.objects.filter(documento_id=OuterRef("pk"))
                .order_by("-id").values("resultado")[:1]
            ))
            .filter(
                solicitud_gasto=gasto,
                sucesor__isnull=True,
                tipo__in=self._tipos(tipos_admitidos),
            )
            .filter(Q(ultima_revision__isnull=True) | Q(ultima_revision="ACEPTADO"))
            .order_by("id")
        )
        return [
            OpcionDocumental(
                referencia_documental=str(doc.referencia_version),
                tipo_documento=TIPOS_C01[doc.tipo],
                etiqueta=doc.get_tipo_display(),
            )
            for doc in documentos
        ]

    def verificar_y_bloquear_documento(
        self,
        *,
        actor: Actor | None,
        gasto: SolicitudGasto,
        referencia_documental: str,
        tipos_admitidos: Collection[str] = TIPOS_DOCUMENTO_ADMITIDOS_PAGO,
    ) -> DocumentoVerificado:
        if not connection.in_atomic_block:
            raise DocumentVerificationError("La verificación requiere una transacción activa.")
        # Reafirma el orden gasto -> raíz documental aun si el llamador olvidó
        # tomar el primer bloqueo. La transacción exterior conserva ambos.
        gasto_bloqueado = visible_expenses(actor).select_for_update().filter(pk=gasto.pk).first()
        if gasto_bloqueado is None:
            raise DocumentVerificationError("Respaldo documental no disponible.")
        self._autorizar(actor, gasto_bloqueado, pago=True)
        try:
            referencia = UUID(referencia_documental)
        except (ValueError, TypeError, AttributeError) as exc:
            raise DocumentVerificationError("Respaldo documental no disponible.") from exc
        documento = (
            documentos_visibles(actor)
            .filter(
                referencia_version=referencia,
                solicitud_gasto=gasto_bloqueado,
                tipo__in=self._tipos(tipos_admitidos),
            )
            .first()
        )
        if documento is None:
            raise DocumentVerificationError("Respaldo documental no disponible.")
        bloquear_serie(documento)
        if Documento.objects.filter(reemplaza=documento).exists():
            raise DocumentVerificationError("Respaldo documental no disponible.")
        revision = documento.revisiones.order_by("-id").first()
        if revision and revision.resultado != RevisionDocumento.Resultado.ACEPTADO:
            raise DocumentVerificationError("Respaldo documental no disponible.")
        # La fila raíz serializa también los reemplazos: ningún sucesor puede
        # aparecer entre esta comprobación y el commit del pago exterior.
        Documento.objects.select_for_update().get(pk=documento.pk)
        return DocumentoVerificado(
            solicitud_id=gasto_bloqueado.pk,
            referencia_documental=str(documento.referencia_version),
            tipo_documento=TIPOS_C01[documento.tipo],
        )
