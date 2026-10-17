"""Migraciones reales de #53 sobre PostgreSQL y datos sintéticos."""

import hashlib
from pathlib import Path

import pytest
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor

GASTOS_ANTERIOR = ("gastos", "0003_pagoexterno_eventopagoexterno")
DOCUMENTOS_ANTERIOR = ("documentos", "0006_integridad_versiones")
COMUNES_ACTUAL = ("comunes", "0002_identidad_inmutable")
FACTURACION_ACTUAL = ("facturacion", "0005_integridad_respaldo")
PDF = b"%PDF-1.7\nDocumento sintetico #53\n%%EOF"

ESTADO_PREVIO = [
    GASTOS_ANTERIOR,
    DOCUMENTOS_ANTERIOR,
    COMUNES_ACTUAL,
    FACTURACION_ACTUAL,
]


def _estado_previo() -> tuple:
    """Deja el esquema en gastos 0003 con documentos ya endurecidos."""
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    executor.migrate(ESTADO_PREVIO)
    apps = executor.loader.project_state(ESTADO_PREVIO).apps
    return apps, finales


def _crear_gasto_historico(apps, pk: int, solicitante_id: int):
    return apps.get_model("gastos", "SolicitudGasto").objects.create(
        pk=pk,
        concepto=f"Gasto histórico {pk}",
        monto_estimado="1.00",
        unidad_requirente="Unidad que no es centro de costo",
        solicitante_id=solicitante_id,
    )


def _crear_cabecera(apps, numero: int, titular_id: int, *, circuito: str = "GASTO"):
    return apps.get_model("comunes", "TramiteBase").objects.create(
        circuito=circuito,
        numero_publico=numero,
        solicitante_actor_id=str(titular_id),
        centro_costo_codigo=None,
    )


def _crear_documento(apps, gasto, base, tmp_path: Path):
    archivo = f"documentos/legacy-{gasto.pk}.pdf"
    ruta = tmp_path / archivo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(PDF)
    return apps.get_model("documentos", "Documento").objects.create(
        solicitud_gasto_id=gasto.pk,
        tramite_base_id=base.pk,
        tipo="PRESUPUESTO_PROFORMA",
        procedencia="SOLICITANTE",
        archivo=archivo,
        nombre_original="legacy.pdf",
        formato="application/pdf",
        tamano=len(PDF),
        sha256=hashlib.sha256(PDF).hexdigest(),
        autor_id=gasto.solicitante_id,
    )


def _instantanea_documento(documento):
    return {
        "solicitud_gasto_id": documento.solicitud_gasto_id,
        "tramite_base_id": documento.tramite_base_id,
        "referencia_version": documento.referencia_version,
        "serie": documento.serie,
        "version": documento.version,
        "tipo": documento.tipo,
        "procedencia": documento.procedencia,
        "archivo": documento.archivo,
        "nombre_original": documento.nombre_original,
        "formato": documento.formato,
        "tamano": documento.tamano,
        "sha256": documento.sha256,
        "autor_id": documento.autor_id,
        "fecha_incorporacion": documento.fecha_incorporacion,
    }


@pytest.mark.django_db(transaction=True)
def test_backfill_reutiliza_cabecera_y_preserva_documentos(tmp_path: Path) -> None:
    """Reutiliza la cabecera existente y conserva filas, referencias y bytes."""
    apps, finales = _estado_previo()
    try:
        usuario = apps.get_model("auth", "User").objects.create(username="legacy_reuse")
        gasto = _crear_gasto_historico(apps, 700, usuario.pk)
        base = _crear_cabecera(apps, gasto.pk, usuario.pk)
        base.centro_costo_codigo = "CC-EXISTENTE"
        base.save(update_fields=["centro_costo_codigo"])
        documento = _crear_documento(apps, gasto, base, tmp_path)
        instantanea = _instantanea_documento(documento)

        executor = MigrationExecutor(connection)
        executor.migrate(finales)
        final = executor.loader.project_state(finales).apps

        gasto_final = final.get_model("gastos", "SolicitudGasto").objects.get(pk=gasto.pk)
        base_final = final.get_model("comunes", "TramiteBase").objects.get(pk=base.pk)
        documento_final = (
            final.get_model("documentos", "Documento").objects.get(pk=documento.pk)
        )

        assert gasto_final.tramite_base_id == base.pk
        assert base_final.numero_publico == gasto.pk
        assert base_final.solicitante_actor_id == str(usuario.pk)
        assert base_final.centro_costo_codigo == "CC-EXISTENTE"
        assert base_final.creado_en == base.creado_en
        assert (
            final.get_model("comunes", "TramiteBase")
            .objects.filter(circuito="GASTO")
            .count()
            == 1
        )
        assert _instantanea_documento(documento_final) == instantanea
        assert (tmp_path / documento_final.archivo).read_bytes() == PDF
        assert (
            hashlib.sha256((tmp_path / documento_final.archivo).read_bytes()).hexdigest()
            == documento_final.sha256
        )
    finally:
        MigrationExecutor(connection).migrate(finales)


@pytest.mark.django_db(transaction=True)
def test_backfill_crea_cabecera_faltante_sin_derivar_centro_costo() -> None:
    """Un gasto sin cabecera recibe una sola cabecera con número y titular correctos."""
    apps, finales = _estado_previo()
    try:
        usuario = apps.get_model("auth", "User").objects.create(username="legacy_missing")
        gasto = _crear_gasto_historico(apps, 701, usuario.pk)

        executor = MigrationExecutor(connection)
        executor.migrate(finales)
        final = executor.loader.project_state(finales).apps
        gasto_final = final.get_model("gastos", "SolicitudGasto").objects.get(pk=gasto.pk)
        base_final = final.get_model("comunes", "TramiteBase").objects.get(
            circuito="GASTO", numero_publico=gasto.pk
        )

        assert gasto_final.tramite_base_id == base_final.pk
        assert base_final.solicitante_actor_id == str(usuario.pk)
        assert base_final.centro_costo_codigo is None
        assert (
            final.get_model("comunes", "TramiteBase")
            .objects.filter(circuito="GASTO")
            .count()
            == 1
        )
    finally:
        MigrationExecutor(connection).migrate(finales)


@pytest.mark.django_db(transaction=True)
def test_backfill_incompatible_revierte_todo_y_preserva_documentos(tmp_path: Path) -> None:
    """Una cabecera con otro titular aborta sin vínculos ni cabeceras nuevas."""
    apps, finales = _estado_previo()
    base_incorrecta = None
    try:
        titular = apps.get_model("auth", "User").objects.create(username="legacy_ok")
        ajeno = apps.get_model("auth", "User").objects.create(username="legacy_wrong")
        gasto_ok = _crear_gasto_historico(apps, 702, titular.pk)
        base_ok = _crear_cabecera(apps, gasto_ok.pk, titular.pk)
        documento = _crear_documento(apps, gasto_ok, base_ok, tmp_path)
        instantanea = _instantanea_documento(documento)

        gasto_incompatible = _crear_gasto_historico(apps, 703, titular.pk)
        base_incorrecta = _crear_cabecera(apps, gasto_incompatible.pk, ajeno.pk)

        before_bases = apps.get_model("comunes", "TramiteBase").objects.count()
        with pytest.raises(RuntimeError, match="Backfill #53"):
            MigrationExecutor(connection).migrate(finales)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tramite_base_id FROM gastos_solicitudgasto WHERE id = %s",
                [gasto_ok.pk],
            )
            assert cursor.fetchone()[0] is None
            cursor.execute(
                "SELECT tramite_base_id FROM gastos_solicitudgasto WHERE id = %s",
                [gasto_incompatible.pk],
            )
            assert cursor.fetchone()[0] is None
            cursor.execute(
                "SELECT count(*) FROM comunes_tramitebase WHERE circuito = 'GASTO'"
            )
            assert cursor.fetchone()[0] == before_bases
        documento_actual = apps.get_model("documentos", "Documento").objects.get(pk=documento.pk)
        assert _instantanea_documento(documento_actual) == instantanea
        assert (tmp_path / documento.archivo).read_bytes() == PDF
    finally:
        if base_incorrecta is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM comunes_tramitebase WHERE id = %s",
                    [base_incorrecta.pk],
                )
        MigrationExecutor(connection).migrate(finales)


@pytest.mark.django_db(transaction=True)
def test_backfill_no_cruza_numero_compartido_con_facturacion() -> None:
    """La cabecera de facturación con igual número permanece intacta."""
    apps, finales = _estado_previo()
    try:
        usuario = apps.get_model("auth", "User").objects.create(username="legacy_overlap")
        gasto = _crear_gasto_historico(apps, 704, usuario.pk)
        base_facturacion = _crear_cabecera(
            apps, gasto.pk, usuario.pk, circuito="FACTURACION"
        )
        solicitud_facturacion = apps.get_model(
            "facturacion", "SolicitudFacturacion"
        ).objects.create(
            pk=gasto.pk,
            tramite_base_id=base_facturacion.pk,
            estado="BORRADOR_TECNICO",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(finales)
        final = executor.loader.project_state(finales).apps
        gasto_final = final.get_model("gastos", "SolicitudGasto").objects.get(pk=gasto.pk)
        base_gasto = final.get_model("comunes", "TramiteBase").objects.get(
            circuito="GASTO", numero_publico=gasto.pk
        )
        factura_final = (
            final.get_model("facturacion", "SolicitudFacturacion")
            .objects.get(pk=solicitud_facturacion.pk)
        )

        assert base_gasto.pk != base_facturacion.pk
        assert gasto_final.tramite_base_id == base_gasto.pk
        assert factura_final.tramite_base_id == base_facturacion.pk
        assert (
            final.get_model("comunes", "TramiteBase")
            .objects.filter(numero_publico=gasto.pk)
            .count()
            == 2
        )
    finally:
        MigrationExecutor(connection).migrate(finales)


@pytest.mark.django_db(transaction=True)
def test_reversa_exitosa_conserva_gastos_cabeceras_y_documentos(tmp_path: Path) -> None:
    """Revertir quita la columna propia sin borrar datos comunes ni documentos."""
    apps, finales = _estado_previo()
    try:
        usuario = apps.get_model("auth", "User").objects.create(username="legacy_reverse")
        gasto = _crear_gasto_historico(apps, 705, usuario.pk)
        base = _crear_cabecera(apps, gasto.pk, usuario.pk)
        documento = _crear_documento(apps, gasto, base, tmp_path)
        instantanea = _instantanea_documento(documento)
        MigrationExecutor(connection).migrate(finales)

        objetivo = ESTADO_PREVIO
        MigrationExecutor(connection).migrate(objetivo)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'gastos_solicitudgasto'
                  AND column_name = 'tramite_base_id'
                """
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT count(*) FROM gastos_solicitudgasto WHERE id = %s", [gasto.pk])
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT count(*) FROM comunes_tramitebase WHERE id = %s", [base.pk])
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT count(*) FROM documentos_documento WHERE id = %s",
                [documento.pk],
            )
            assert cursor.fetchone()[0] == 1

        reverso = MigrationExecutor(connection).loader.project_state(objetivo).apps
        documento_reverso = (
            reverso.get_model("documentos", "Documento").objects.get(pk=documento.pk)
        )
        assert _instantanea_documento(documento_reverso) == instantanea
        assert (tmp_path / documento_reverso.archivo).read_bytes() == PDF
        assert reverso.get_model("comunes", "TramiteBase").objects.filter(pk=base.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(finales)


@pytest.mark.django_db(transaction=True)
def test_reversa_con_vinculo_incoherente_se_bloquea_y_conserva_el_esquema(
    tmp_path: Path,
) -> None:
    """Una inconsistencia introducida a mano impide revertir y no pierde el trigger."""
    apps, finales = _estado_previo()
    gasto = None
    base = None
    base_ajena = None
    try:
        usuario = apps.get_model("auth", "User").objects.create(username="legacy_bad_reverse")
        gasto = _crear_gasto_historico(apps, 706, usuario.pk)
        base = _crear_cabecera(apps, gasto.pk, usuario.pk)
        _crear_documento(apps, gasto, base, tmp_path)
        MigrationExecutor(connection).migrate(finales)

        base_ajena = _crear_cabecera(apps, 707, usuario.pk)
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE gastos_solicitudgasto "
                "DISABLE TRIGGER gastos_validar_tramite_base"
            )
            cursor.execute(
                "UPDATE gastos_solicitudgasto SET tramite_base_id = %s WHERE id = %s",
                [base_ajena.pk, gasto.pk],
            )
            cursor.execute(
                "ALTER TABLE gastos_solicitudgasto "
                "ENABLE TRIGGER gastos_validar_tramite_base"
            )

        objetivo = ESTADO_PREVIO
        with pytest.raises(IrreversibleError, match="No se puede revertir"):
            MigrationExecutor(connection).migrate(objetivo)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'gastos_solicitudgasto'
                  AND column_name = 'tramite_base_id'
                """
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT tgenabled FROM pg_trigger "
                "WHERE tgname = 'gastos_validar_tramite_base'"
            )
            assert cursor.fetchone()[0] == "O"
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE gastos_solicitudgasto "
                "DISABLE TRIGGER gastos_validar_tramite_base"
            )
            if base is not None and gasto is not None:
                cursor.execute(
                    "UPDATE gastos_solicitudgasto SET tramite_base_id = %s WHERE id = %s",
                    [base.pk, gasto.pk],
                )
            cursor.execute(
                "ALTER TABLE gastos_solicitudgasto "
                "ENABLE TRIGGER gastos_validar_tramite_base"
            )
            if base_ajena is not None:
                cursor.execute(
                    "DELETE FROM comunes_tramitebase WHERE id = %s", [base_ajena.pk]
                )
        MigrationExecutor(connection).migrate(finales)
