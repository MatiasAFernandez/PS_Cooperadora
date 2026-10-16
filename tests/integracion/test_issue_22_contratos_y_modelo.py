"""Integridad real y contrato común del tramo de Matías en #22."""

import pytest
from django.db import IntegrityError, connection, transaction

from comunes.contracts import ReferenciaCruzadaError, TramiteNoDisponible, TramiteRef
from comunes.models import Circuito, TramiteBase
from comunes.services import registrar_cabecera_gasto, resolver_tramite_base
from documentos.models import Documento
from documentos.policy import ArchivoInvalido
from documentos.services import incorporar
from facturacion.models import EventoFacturacion, SolicitudFacturacion

from .helpers import archivo_pdf


def test_mismo_numero_en_dos_circuitos_y_consulta_sin_efectos(escenario_comun):
    e = escenario_comun
    gasto_base = registrar_cabecera_gasto(e.gasto)
    fact_base = e.factura.tramite_base
    assert gasto_base.numero_publico == fact_base.numero_publico
    assert gasto_base.pk != fact_base.pk
    assert gasto_base.solicitante_actor_id == str(e.a.pk)
    assert gasto_base.centro_costo_codigo is None
    cantidad = TramiteBase.objects.count()
    for base in (gasto_base, fact_base):
        assert resolver_tramite_base(TramiteRef.desde_texto(str(base.referencia))) == base
    assert TramiteBase.objects.count() == cantidad
    with pytest.raises(ReferenciaCruzadaError):
        resolver_tramite_base(fact_base.referencia, circuito_esperado=Circuito.GASTO)
    with pytest.raises(TramiteNoDisponible):
        resolver_tramite_base(TramiteRef(Circuito.FACTURACION, 2147483647))


def test_cabecera_inmutable_por_orm_queryset_y_sql(escenario_comun):
    base = escenario_comun.factura.tramite_base
    for campo, valor in (
        ("circuito", Circuito.GASTO),
        ("numero_publico", 1234567),
        ("solicitante_actor_id", str(escenario_comun.a.pk)),
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            TramiteBase.objects.filter(pk=base.pk).update(**{campo: valor})
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            # Los nombres de columna son constantes de la prueba, nunca entradas HTTP.
            cursor.execute(
                f"UPDATE comunes_tramitebase SET {campo} = %s WHERE id = %s", [valor, base.pk]
            )
    base.numero_publico += 1
    with pytest.raises(IntegrityError):
        base.save()


def test_hija_facturacion_rechaza_circuito_incorrecto_y_reasignacion(escenario_comun):
    e = escenario_comun
    gasto_base = registrar_cabecera_gasto(e.gasto)
    with pytest.raises(IntegrityError), transaction.atomic():
        SolicitudFacturacion.objects.create(pk=e.gasto.pk + 1000, tramite_base=gasto_base)
    with pytest.raises(IntegrityError), transaction.atomic():
        SolicitudFacturacion.objects.filter(pk=e.factura.pk).update(tramite_base=gasto_base)


def test_documento_cruzado_no_deja_registro_ni_archivo(escenario_comun):
    e = escenario_comun
    with pytest.raises(ArchivoInvalido):
        incorporar(
            actor=e.actor_staff,
            referencia=f"facturacion:{e.factura.pk}",
            archivo=archivo_pdf(),
            tipo=Documento.Tipo.FACTURA_PROVEEDOR,
            procedencia="INTERNO_COOPERADORA",
        )
    assert not Documento.objects.exists()
    assert not e.raiz.exists()


def test_integridad_documental_tambien_en_escrituras_directas(escenario_comun):
    e = escenario_comun
    base = registrar_cabecera_gasto(e.gasto)
    datos = dict(
        tramite_base=base,
        solicitud_gasto=e.gasto,
        tipo=Documento.Tipo.FACTURA_PROVEEDOR,
        procedencia="SOLICITANTE",
        archivo="no-se-escribe-en-storage",
        nombre_original="prueba.pdf",
        formato="application/pdf",
        tamano=10,
        sha256="0" * 64,
        autor=e.a,
    )
    for cambios in (
        {"tramite_base": e.factura.tramite_base},
        {"tipo": Documento.Tipo.COMPROBANTE_COBRO},
        {"tramite_base": None, "tramite_base_id": 2147483647},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            Documento.objects.create(**(datos | cambios))
    valido = Documento.objects.create(**datos)
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE documentos_documento SET tramite_base_id = %s WHERE id = %s",
            [e.factura.tramite_base_id, valido.pk],
        )
    assert Documento.objects.count() == 1


def test_eventos_facturacion_append_only_con_dto_cronologico(escenario_comun):
    e = escenario_comun
    eventos = [
        EventoFacturacion.objects.create(
            solicitud=e.factura,
            tipo_evento=tipo,
            actor=e.b,
            estado_resultante="EJEMPLO_CONTRATO",
            motivo_o_detalle="Ejemplo sintético",
        )
        for tipo in ("PRESENTACION", "OBSERVACION", "CORRECCION")
    ]
    historial = [evento.como_historial() for evento in e.factura.eventos.all()]
    assert [item.tipo_evento for item in historial] == [evento.tipo_evento for evento in eventos]
    assert all(item.tramite_ref == f"facturacion:{e.factura.pk}" for item in historial)
    assert all(item.fecha_hora.tzinfo is not None for item in historial)
    for sql in (
        "UPDATE facturacion_eventofacturacion SET tipo_evento = 'OTRO' WHERE id = %s",
        "DELETE FROM facturacion_eventofacturacion WHERE id = %s",
    ):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, [eventos[0].pk])
    with pytest.raises(IntegrityError):
        eventos[0].save()
    with pytest.raises(IntegrityError):
        eventos[0].delete()


def test_evento_y_cambio_se_revierten_juntos(escenario_comun):
    e = escenario_comun
    with pytest.raises(RuntimeError), transaction.atomic():
        # #23 ya restringe estados; cambiar versión prueba el mismo rollback
        # sin introducir un estado ajeno al catálogo operativo.
        SolicitudFacturacion.objects.filter(pk=e.factura.pk).update(version_concurrencia=2)
        EventoFacturacion.objects.create(
            solicitud=e.factura,
            tipo_evento="PRUEBA",
            actor=e.b,
            estado_resultante="BORRADOR_TECNICO",
        )
        raise RuntimeError("Fallo sintético posterior")
    e.factura.refresh_from_db()
    assert e.factura.estado == "BORRADOR_TECNICO"
    assert e.factura.version_concurrencia == 1
    assert not e.factura.eventos.exists()
