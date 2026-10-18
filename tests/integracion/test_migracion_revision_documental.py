"""Upgrade/reversa sin datos perdidos y bloqueo de reversa con historial real."""

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from documentos.models import Documento, RevisionDocumento
from documentos.services import incorporar

from .helpers import archivo_pdf


@pytest.mark.django_db(transaction=True)
def test_reversa_vacia_y_upgrade_preservan_documento(escenario_comun):
    e = escenario_comun
    documento = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=archivo_pdf(),
        tipo="FACTURA_PROVEEDOR",
        procedencia="SOLICITANTE",
    )
    contenido = (e.raiz / documento.archivo).read_bytes()
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("documentos", "0006_integridad_versiones")])
        assert "documentos_revisiondocumento" not in connection.introspection.table_names()
        MigrationExecutor(connection).migrate(finales)
        actual = Documento.objects.get(pk=documento.pk)
        assert actual.referencia_version == documento.referencia_version
        assert actual.archivo == documento.archivo and actual.sha256 == documento.sha256
        assert (e.raiz / actual.archivo).read_bytes() == contenido
        assert not RevisionDocumento.objects.exists()
    finally:
        MigrationExecutor(connection).migrate(finales)


@pytest.mark.django_db(transaction=True)
def test_reversa_con_historial_no_retira_guarda(escenario_comun):
    e = escenario_comun
    documento = incorporar(
        actor=e.actor_a,
        referencia=f"gastos:{e.gasto.pk}",
        archivo=archivo_pdf(),
        tipo="FACTURA_PROVEEDOR",
        procedencia="SOLICITANTE",
    )
    revision = RevisionDocumento.objects.create(
        documento=documento,
        resultado="ACEPTADO",
        actor=e.staff,
    )
    with pytest.raises(DatabaseError, match="Hay revisiones"):
        MigrationExecutor(connection).migrate([("documentos", "0007_revision_documental")])
    with pytest.raises(IntegrityError), transaction.atomic():
        RevisionDocumento.objects.filter(pk=revision.pk).update(resultado="OBSERVADO")
    assert RevisionDocumento.objects.get(pk=revision.pk).resultado == "ACEPTADO"
