"""Vincula cada gasto histórico con su cabecera o crea la faltante.

La validación se completa antes de escribir. Cualquier discrepancia de circuito,
número, titular o referencia documental aborta la migración y PostgreSQL revierte
las cabeceras y vínculos creados. Los documentos no se modifican.
"""

from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError

CIRCUITO_GASTO = "GASTO"


def _abortar(mensaje: str) -> None:
    raise RuntimeError(f"Backfill #53 de gastos: {mensaje}")


def _base_por_numero(Base, alias: str) -> dict:
    return {
        base.numero_publico: base
        for base in Base.objects.using(alias).filter(circuito=CIRCUITO_GASTO).order_by("pk")
    }


def _documentos_por_gasto(Documento, alias: str) -> dict:
    documentos: dict[int, list] = {}
    for documento in (
        Documento.objects.using(alias)
        .filter(solicitud_gasto_id__isnull=False)
        .order_by("pk")
    ):
        documentos.setdefault(documento.solicitud_gasto_id, []).append(documento)
    return documentos


def _validar_cabecera(base, gasto) -> None:
    if base is None:
        _abortar(f"El gasto #{gasto.pk} no tiene cabecera disponible.")
    if base.circuito != CIRCUITO_GASTO:
        _abortar(f"El gasto #{gasto.pk} referencia una cabecera de otro circuito.")
    if base.numero_publico != gasto.pk:
        _abortar(
            f"El gasto #{gasto.pk} referencia la cabecera #{base.pk} "
            f"con número público {base.numero_publico}."
        )
    if base.solicitante_actor_id != str(gasto.solicitante_id):
        _abortar(
            f"El gasto #{gasto.pk} no coincide con el titular de la cabecera #{base.pk}."
        )


def _validar_documento(documento, gasto, base, Base, alias: str) -> None:
    if documento.tramite_base_id != base.pk:
        _abortar(
            f"El documento #{documento.pk} del gasto #{gasto.pk} apunta a otra cabecera."
        )
    base_documento = (
        Base.objects.using(alias)
        .filter(pk=documento.tramite_base_id)
        .values("circuito", "numero_publico", "solicitante_actor_id")
        .first()
    )
    if base_documento is None:
        _abortar(f"El documento #{documento.pk} no tiene cabecera existente.")
    if (
        base_documento["circuito"] != CIRCUITO_GASTO
        or base_documento["numero_publico"] != gasto.pk
        or base_documento["solicitante_actor_id"] != str(gasto.solicitante_id)
    ):
        _abortar(f"El documento #{documento.pk} es incompatible con el gasto #{gasto.pk}.")


def backfill(apps, schema_editor) -> None:
    alias = schema_editor.connection.alias
    Gasto = apps.get_model("gastos", "SolicitudGasto")
    Base = apps.get_model("comunes", "TramiteBase")
    Documento = apps.get_model("documentos", "Documento")

    # Las altas/actualizaciones de gastos quedan bloqueadas hasta terminar. Las
    # lecturas y las escrituras de documentos permitidas por su propio trigger
    # no se ven afectadas. El orden gastos -> cabeceras evita un deadlock con
    # el alta documental que bloquea primero el gasto.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("LOCK TABLE gastos_solicitudgasto IN SHARE ROW EXCLUSIVE MODE")
        cursor.execute("LOCK TABLE comunes_tramitebase IN SHARE ROW EXCLUSIVE MODE")

    gastos = list(Gasto.objects.using(alias).select_for_update().order_by("pk"))
    bases = _base_por_numero(Base, alias)
    documentos = _documentos_por_gasto(Documento, alias)

    # Preflight sin escrituras: toda la coherencia se valida antes de crear o
    # vincular. Así un error no deja cabeceras parciales.
    plan = []
    for gasto in gastos:
        base = bases.get(gasto.pk)
        if base is not None:
            _validar_cabecera(base, gasto)
        for documento in documentos.get(gasto.pk, ()):
            if base is None:
                _abortar(
                    f"El gasto #{gasto.pk} tiene el documento #{documento.pk} "
                    "pero no tiene cabecera."
                )
            _validar_documento(documento, gasto, base, Base, alias)
        plan.append((gasto, base))

    for gasto, base in plan:
        if base is None:
            base = Base.objects.using(alias).create(
                circuito=CIRCUITO_GASTO,
                numero_publico=gasto.pk,
                solicitante_actor_id=str(gasto.solicitante_id),
                centro_costo_codigo=None,
            )
            bases[gasto.pk] = base
        Gasto.objects.using(alias).filter(pk=gasto.pk).update(tramite_base_id=base.pk)

    # Postvalidación sobre lo persistido, sin aceptar vínculos nulos o cruzados.
    for gasto in Gasto.objects.using(alias).select_for_update().order_by("pk"):
        base = bases.get(gasto.pk)
        if gasto.tramite_base_id is None:
            _abortar(f"El gasto #{gasto.pk} quedó sin cabecera.")
        if base is None or gasto.tramite_base_id != base.pk:
            _abortar(f"El gasto #{gasto.pk} quedó vinculado a una cabecera inesperada.")
        _validar_cabecera(base, gasto)
        for documento in (
            Documento.objects.using(alias)
            .filter(solicitud_gasto_id=gasto.pk)
            .order_by("pk")
        ):
            _validar_documento(documento, gasto, base, Base, alias)


def validar_reversa(apps, schema_editor) -> None:
    """Impide revertir si los vínculos o documentos ya son incoherentes.

    No borra cabeceras ni documentos: la columna de gastos se elimina después con
    la reversa de 0004 y las filas comunes permanecen.
    """
    alias = schema_editor.connection.alias
    Gasto = apps.get_model("gastos", "SolicitudGasto")
    Base = apps.get_model("comunes", "TramiteBase")
    Documento = apps.get_model("documentos", "Documento")

    bases = _base_por_numero(Base, alias)
    for gasto in Gasto.objects.using(alias).order_by("pk"):
        if gasto.tramite_base_id is None:
            raise IrreversibleError(
                f"No se puede revertir: el gasto #{gasto.pk} no tiene cabecera."
            )
        base = bases.get(gasto.pk)
        try:
            _validar_cabecera(base, gasto)
        except RuntimeError as exc:
            raise IrreversibleError(str(exc)) from exc
        if gasto.tramite_base_id != base.pk:
            raise IrreversibleError(
                f"No se puede revertir: el gasto #{gasto.pk} apunta a otra cabecera."
            )
        try:
            for documento in (
                Documento.objects.using(alias)
                .filter(solicitud_gasto_id=gasto.pk)
                .order_by("pk")
            ):
                _validar_documento(documento, gasto, base, Base, alias)
        except RuntimeError as exc:
            raise IrreversibleError(str(exc)) from exc


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0006_integridad_versiones"),
        ("gastos", "0004_solicitudgasto_tramite_base"),
    ]

    operations = [
        migrations.RunPython(backfill, validar_reversa),
    ]
