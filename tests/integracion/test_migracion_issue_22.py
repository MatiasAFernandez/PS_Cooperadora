"""Upgrade real desde la PR #48, con archivos y referencias históricas intactos."""

import hashlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_upgrade_preserva_archivos_ids_y_valores_no_clasificados(tmp_path):
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    previos = [
        ("documentos", "0003_alter_documento_procedencia_alter_documento_tipo"),
        ("comunes", None),
        ("facturacion", None),
    ]
    try:
        executor.migrate(previos)
        anteriores = executor.loader.project_state(
            [
                ("documentos", "0003_alter_documento_procedencia_alter_documento_tipo"),
                ("gastos", "0003_pagoexterno_eventopagoexterno"),
            ]
        ).apps
        usuario = anteriores.get_model("auth", "User").objects.create(username="previo")
        gasto = anteriores.get_model("gastos", "SolicitudGasto").objects.create(
            solicitante_id=usuario.pk,
            concepto="Previo",
            monto_estimado="1.00",
            unidad_requirente="No es centro de costo",
        )
        contenido = b"%PDF-1.7\nArchivo anterior sintetico\n%%EOF"
        antiguos = []
        for i, tipo in enumerate(("PRESUPUESTO", "respaldo")):
            ruta = tmp_path / f"documentos/historico-{i}"
            ruta.parent.mkdir(exist_ok=True)
            ruta.write_bytes(contenido)
            antiguos.append(
                anteriores.get_model("documentos", "Documento").objects.create(
                    solicitud_gasto_id=gasto.pk,
                    tipo=tipo,
                    procedencia="SOLICITANTE",
                    archivo=f"documentos/historico-{i}",
                    nombre_original="anterior.pdf",
                    formato="application/pdf",
                    tamano=len(contenido),
                    sha256=hashlib.sha256(contenido).hexdigest(),
                    autor_id=usuario.pk,
                )
            )
        executor = MigrationExecutor(connection)
        executor.migrate(finales)
        actuales = executor.loader.project_state(finales).apps
        docs = list(actuales.get_model("documentos", "Documento").objects.order_by("id"))
        assert [doc.pk for doc in docs] == [doc.pk for doc in antiguos]
        assert [doc.archivo for doc in docs] == [doc.archivo for doc in antiguos]
        assert [doc.tipo for doc in docs] == ["PRESUPUESTO_PROFORMA", "respaldo"]
        assert docs[0].referencia_version != docs[1].referencia_version
        assert docs[0].serie != docs[1].serie
        assert docs[0].tramite_base_id == docs[1].tramite_base_id
        base = actuales.get_model("comunes", "TramiteBase").objects.get(pk=docs[0].tramite_base_id)
        assert base.numero_publico == gasto.pk
        assert base.solicitante_actor_id == str(usuario.pk)
        assert base.centro_costo_codigo is None
        for doc in docs:
            assert (tmp_path / doc.archivo).read_bytes() == contenido
            assert doc.sha256 == hashlib.sha256((tmp_path / doc.archivo).read_bytes()).hexdigest()
    finally:
        # Restaurar el esquema también si falla una aserción, para no contaminar
        # el resto de la suite que usa modelos actuales.
        MigrationExecutor(connection).migrate(finales)
