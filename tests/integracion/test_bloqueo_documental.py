"""El bloqueo C01 se conserva hasta terminar la transacción del consumidor."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import OperationalError, close_old_connections, connection, transaction

from documentos.c01 import ProveedorDocumentalGastos
from documentos.models import Documento
from documentos.services import incorporar

from .helpers import archivo_pdf


@pytest.mark.django_db(transaction=True)
def test_verificacion_c01_bloquea_incluso_un_reemplazo_por_sql(escenario_comun):
    e = escenario_comun
    documento = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=archivo_pdf(),
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
    )
    valores = Documento.objects.filter(pk=documento.pk).values().get()
    for campo in ("id", "referencia_version", "fecha_incorporacion"):
        valores.pop(campo)
    valores.update(version=2, reemplaza_id=documento.pk, archivo="documentos/reemplazo-ficticio")

    def intentar_reemplazo():
        close_old_connections()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '250ms'")
                # Se salta el servicio de reemplazo: el trigger debe respetar el
                # mismo bloqueo raíz aunque se use directamente el ORM.
                return Documento.objects.create(**valores).pk
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as executor, transaction.atomic():
        ProveedorDocumentalGastos().verificar_y_bloquear_documento(
            actor=e.actor_staff,
            gasto=e.gasto,
            referencia_documental=str(documento.referencia_version),
        )
        with pytest.raises(OperationalError):
            executor.submit(intentar_reemplazo).result(timeout=10)
    assert not Documento.objects.filter(reemplaza=documento).exists()
    # Tras commit la misma escritura desde otra conexión debe poder continuar.
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(intentar_reemplazo).result(timeout=10) is not None
    assert Documento.objects.filter(reemplaza=documento, version=2).count() == 1
