"""Migración desde #22 con varias solicitudes técnicas y un evento previo."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_uuid_individual_preserva_cabeceras_y_eventos_previos():
    executor = MigrationExecutor(connection)
    finales = executor.loader.graph.leaf_nodes()
    previo = [("facturacion", "0002_integridad_y_eventos")]
    try:
        executor.migrate(previo)
        apps = executor.loader.project_state(previo).apps
        user = apps.get_model("auth", "User").objects.create(username="previo-facturacion")
        Base = apps.get_model("comunes", "TramiteBase")
        Solicitud = apps.get_model("facturacion", "SolicitudFacturacion")
        Evento = apps.get_model("facturacion", "EventoFacturacion")
        for numero in (710, 711):
            base = Base.objects.create(
                circuito="FACTURACION",
                numero_publico=numero,
                solicitante_actor_id=str(user.pk),
            )
            solicitud = Solicitud.objects.create(
                pk=numero,
                tramite_base_id=base.pk,
                estado="BORRADOR_TECNICO",
            )
            Evento.objects.create(
                solicitud_id=solicitud.pk,
                actor_id=user.pk,
                tipo_evento="PRUEBA_PREVIA",
                estado_resultante="BORRADOR_TECNICO",
            )
        ids = list(Evento.objects.values_list("pk", flat=True))
        MigrationExecutor(connection).migrate(finales)
        apps = MigrationExecutor(connection).loader.project_state(finales).apps
        Solicitud = apps.get_model("facturacion", "SolicitudFacturacion")
        Evento = apps.get_model("facturacion", "EventoFacturacion")
        filas = list(Solicitud.objects.order_by("pk"))
        assert [x.pk for x in filas] == [710, 711]
        assert len({x.clave_idempotencia for x in filas}) == 2
        assert all(x.estado == "BORRADOR_TECNICO" and not x.correo_solicitante for x in filas)
        assert list(Evento.objects.values_list("pk", flat=True)) == ids
        assert all(x.snapshot_datos == {} for x in Evento.objects.all())
    finally:
        MigrationExecutor(connection).migrate(finales)
