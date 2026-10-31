"""Datos operativos de transferencia del gasto (Issue #74 / SPEC-013).

Cubre captura inicial opcional y completa, validación del bloque, correcciones
versionadas, historial inmutable, autorización de lectura y escritura,
denegaciones, bloqueo posterior al pago y presentación separada en el detalle.
Las pruebas usan únicamente actores y valores sintéticos.
"""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.urls import reverse

from gastos.datos_transferencia import (
    CAMPOS_DATOS_TRANSFERENCIA,
    MENSAJE_CBU_ALIAS_FRECUENTE,
    MENSAJE_CORREO_COMPROBANTE_INVALIDO,
    DatosTransferenciaBloqueadaError,
    DatosTransferenciaInvalidInputError,
    DatosTransferenciaNotFoundError,
    DatosTransferenciaPermissionDeniedError,
    consultar_revisiones_datos_transferencia,
    datos_de_revision,
    puede_consultar_datos_transferencia,
    registrar_revision_datos_transferencia,
)
from gastos.models import (
    EstadoSolicitud,
    PagoExterno,
    RevisionDatosTransferencia,
    SolicitudGasto,
)
from gastos.payments import registrar_pago_externo
from gastos.services import crear_solicitud_gasto
from identidad.services import Actor
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()

DATOS_COMPLETOS = {
    "titular_nombre": "Titular Sintetico Unico",
    "identificacion": "ID-SINT-741",
    "cbu_alias": "ALIAS.SINT.741",
    "correo_comprobante": "correo.sintetico.741@example.test",
    "centro_costo": "CC-SINT-741",
}

DATOS_NUEVOS = {
    "titular_nombre": "Titular Sintetico Corregido",
    "identificacion": "ID-SINT-742",
    "cbu_alias": "ALIAS.SINT.742",
    "correo_comprobante": "correo.sintetico.742@example.test",
    "centro_costo": "CC-SINT-742",
}


def _crear_gasto(
    user: Any,
    *,
    estado: str = EstadoSolicitud.ACEPTADA,
    concepto: str = "Gasto sintético con datos de transferencia",
):
    return crear_gasto_sintetico(
        concepto=concepto,
        monto_estimado=Decimal("2500.00"),
        unidad_requirente="Unidad sintética de transferencia",
        solicitante=user,
        estado=estado,
    )


def _registrar_datos(actor: Actor, gasto: Any, datos: dict[str, str]):
    return registrar_revision_datos_transferencia(
        actor=actor, solicitud_id=gasto.pk, datos=datos
    )


def _registrar_pago(actor: Actor, gasto: Any, fake_document_provider: Any) -> PagoExterno:
    return registrar_pago_externo(
        actor=actor,
        solicitud_id=gasto.pk,
        importe="1234.56",
        fecha_pago="2026-10-27",
        referencia_externa="TRF-74-SINTETICA",
        referencia_documental="doc-sintetico-74",
        document_provider=fake_document_provider(),
    )


# --------------------------------------------------------------------------- #
# Captura inicial: vacía, completa y parcial
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_formulario_inicial_sin_datos_crea_gasto_sin_revision(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_inicial_vacio", ["gastos.presentar", "gastos.consultar_propias"]
    )
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:presentar"),
        {
            "concepto": "Insumos sin datos de transferencia",
            "monto_estimado": "1500.00",
            "unidad_requirente": "Unidad sintética",
        },
    )

    assert response.status_code == 302
    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_formulario_inicial_completo_crea_solicitud_y_primera_revision(
    create_actor: Any, csrf_auth_client: Any
) -> None:
    user, _actor = create_actor(
        "titular_inicial_completo", ["gastos.presentar", "gastos.consultar_propias"]
    )
    client, token = csrf_auth_client(user, _actor)

    response = client.post(
        reverse("gastos:presentar"),
        {
            "csrfmiddlewaretoken": token,
            "concepto": "Insumos con datos de transferencia",
            "monto_estimado": "2500.00",
            "unidad_requirente": "Unidad sintética",
            **DATOS_COMPLETOS,
        },
    )

    assert response.status_code == 302
    gasto = SolicitudGasto.objects.get()
    revision = RevisionDatosTransferencia.objects.get()
    assert revision.solicitud_id == gasto.pk
    assert revision.numero_revision == 1
    assert revision.actor_id == user.pk
    assert revision.fecha_hora is not None
    assert datos_de_revision(revision) == DATOS_COMPLETOS
    assert gasto.tramite_base.centro_costo_codigo is None
    assert response.url == reverse("gastos:detalle", kwargs={"pk": gasto.pk})


@pytest.mark.django_db
@pytest.mark.parametrize("campo_faltante", CAMPOS_DATOS_TRANSFERENCIA)
def test_formulario_inicial_parcial_no_crea_solicitud_ni_revision(
    campo_faltante: str,
    create_actor: Any,
    auth_client: Any,
) -> None:
    user, actor = create_actor(
        f"titular_inicial_parcial_{campo_faltante}",
        ["gastos.presentar", "gastos.consultar_propias"],
    )
    client = auth_client(user, actor)
    datos = {campo: valor for campo, valor in DATOS_COMPLETOS.items() if campo != campo_faltante}

    response = client.post(
        reverse("gastos:presentar"),
        {
            "concepto": "Insumos con bloque parcial",
            "monto_estimado": "2500.00",
            "unidad_requirente": "Unidad sintética",
            **datos,
        },
    )

    assert response.status_code == 200
    assert SolicitudGasto.objects.count() == 0
    assert RevisionDatosTransferencia.objects.count() == 0
    assert campo_faltante in response.context["datos_form"].errors


@pytest.mark.django_db
def test_formulario_inicial_rechaza_correo_de_destino_invalido(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_inicial_correo_invalido",
        ["gastos.presentar", "gastos.consultar_propias"],
    )
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:presentar"),
        {
            "concepto": "Insumos con correo de destino inválido",
            "monto_estimado": "1500.00",
            "unidad_requirente": "Unidad sintética",
            **{**DATOS_COMPLETOS, "correo_comprobante": "destino-sin-arroba"},
        },
    )

    assert response.status_code == 200
    assert SolicitudGasto.objects.count() == 0
    assert RevisionDatosTransferencia.objects.count() == 0
    assert "correo_comprobante" in response.context["datos_form"].errors
    assert MENSAJE_CORREO_COMPROBANTE_INVALIDO in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("cbu_alias", ["frecuente", "  FrEcUeNtE  "])
def test_formulario_inicial_rechaza_literal_frecuente_como_cbu_alias(
    cbu_alias: str,
    create_actor: Any,
    auth_client: Any,
) -> None:
    user, actor = create_actor(
        "titular_inicial_frecuente",
        ["gastos.presentar", "gastos.consultar_propias"],
    )
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:presentar"),
        {
            "concepto": "Insumos con CBU o alias inválido",
            "monto_estimado": "1500.00",
            "unidad_requirente": "Unidad sintética",
            **{**DATOS_COMPLETOS, "cbu_alias": cbu_alias},
        },
    )

    assert response.status_code == 200
    assert SolicitudGasto.objects.count() == 0
    assert RevisionDatosTransferencia.objects.count() == 0
    assert "cbu_alias" in response.context["datos_form"].errors
    assert MENSAJE_CBU_ALIAS_FRECUENTE in response.content.decode()


@pytest.mark.django_db
def test_formulario_inicial_conserva_el_correo_de_destino_normalizado(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_correo_destino",
        ["gastos.presentar", "gastos.consultar_propias"],
    )
    user.email = "correo.sesion@example.test"
    user.save(update_fields=["email"])
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:presentar"),
        {
            "concepto": "Insumos con correo de destino",
            "monto_estimado": "1500.00",
            "unidad_requirente": "Unidad sintética",
            **{
                **DATOS_COMPLETOS,
                "correo_comprobante": "  Destino.Sintetico@Example.Test  ",
            },
        },
    )

    assert response.status_code == 302
    revision = RevisionDatosTransferencia.objects.get()
    assert revision.correo_comprobante == "Destino.Sintetico@Example.Test"
    assert revision.correo_comprobante != user.email


@pytest.mark.django_db
def test_servicio_de_alta_rechaza_bloque_parcial_sin_reservar_numero(
    actor_factory: Any,
) -> None:
    _, actor = actor_factory(("gastos.presentar",))
    datos = dict(DATOS_COMPLETOS)
    del datos["cbu_alias"]

    with pytest.raises(DatosTransferenciaInvalidInputError):
        crear_solicitud_gasto(
            actor=actor,
            concepto="Alta parcial inválida",
            monto_estimado=Decimal("100.00"),
            unidad_requirente="Unidad sintética",
            datos_transferencia=datos,
        )

    assert SolicitudGasto.objects.count() == 0
    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_servicio_de_alta_crea_primera_revision_con_actor_del_servidor(
    actor_factory: Any,
) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))

    gasto = crear_solicitud_gasto(
        actor=actor,
        concepto="Alta con transferencia",
        monto_estimado=Decimal("100.00"),
        unidad_requirente="Unidad sintética",
        datos_transferencia=DATOS_COMPLETOS,
    )

    revision = RevisionDatosTransferencia.objects.get(solicitud_id=gasto.pk)
    assert revision.numero_revision == 1
    assert revision.actor_id == user.pk
    assert revision.fecha_hora is not None
    assert datos_de_revision(revision) == DATOS_COMPLETOS


# --------------------------------------------------------------------------- #
# Correcciones, historial e inmutabilidad
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_correccion_crea_revision_nueva_y_conserva_la_anterior(
    actor_factory: Any,
) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)

    primera = _registrar_datos(actor, gasto, DATOS_COMPLETOS)
    segunda = _registrar_datos(actor, gasto, DATOS_NUEVOS)

    primera.refresh_from_db()
    segunda.refresh_from_db()
    assert primera.numero_revision == 1
    assert segunda.numero_revision == 2
    assert datos_de_revision(primera) == DATOS_COMPLETOS
    assert datos_de_revision(segunda) == DATOS_NUEVOS
    assert primera.actor_id == segunda.actor_id == user.pk
    assert primera.fecha_hora is not None
    assert segunda.fecha_hora is not None

    revisiones = consultar_revisiones_datos_transferencia(actor, gasto.pk)
    assert revisiones is not None
    assert [revision.numero_revision for revision in revisiones] == [1, 2]
    assert revisiones[-1].pk == segunda.pk


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("cbu_alias", "A" * 129),
        ("correo_comprobante", "a" * 255),
        ("titular_nombre", "Titular con NUL \x00"),
    ],
)
def test_validacion_rechaza_valores_fuera_de_contrato(
    campo: str, valor: str, actor_factory: Any
) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    datos = {**DATOS_COMPLETOS, campo: valor}

    with pytest.raises(DatosTransferenciaInvalidInputError):
        _registrar_datos(actor, gasto, datos)

    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_servicio_rechaza_correo_de_destino_invalido(actor_factory: Any) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    datos = {**DATOS_COMPLETOS, "correo_comprobante": "destino-sin-arroba"}

    with pytest.raises(DatosTransferenciaInvalidInputError) as exc_info:
        _registrar_datos(actor, gasto, datos)

    assert str(exc_info.value) == MENSAJE_CORREO_COMPROBANTE_INVALIDO
    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("cbu_alias", ["frecuente", "  FrEcUeNtE  "])
def test_servicio_rechaza_literal_frecuente_como_cbu_alias(
    cbu_alias: str, actor_factory: Any
) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    datos = {**DATOS_COMPLETOS, "cbu_alias": cbu_alias}

    with pytest.raises(DatosTransferenciaInvalidInputError) as exc_info:
        _registrar_datos(actor, gasto, datos)

    assert str(exc_info.value) == MENSAJE_CBU_ALIAS_FRECUENTE
    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_correccion_vacia_no_escribe(actor_factory: Any) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)

    with pytest.raises(DatosTransferenciaInvalidInputError):
        _registrar_datos(actor, gasto, {})

    assert RevisionDatosTransferencia.objects.filter(solicitud_id=gasto.pk).count() == 1


@pytest.mark.django_db
def test_revision_no_admite_modificacion_ni_borrado(actor_factory: Any) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    revision = _registrar_datos(actor, gasto, DATOS_COMPLETOS)

    revision.titular_nombre = "Otro titular"
    with pytest.raises(IntegrityError):
        revision.save()
    with pytest.raises(IntegrityError):
        RevisionDatosTransferencia.objects.filter(pk=revision.pk).update(
            titular_nombre="Otro titular"
        )
    with pytest.raises(IntegrityError):
        revision.delete()

    actual = RevisionDatosTransferencia.objects.get(pk=revision.pk)
    assert actual.titular_nombre == DATOS_COMPLETOS["titular_nombre"]


@pytest.mark.django_db
def test_trigger_postgresql_bloquea_update_directo_por_sql(actor_factory: Any) -> None:
    """El trigger de la migración protege aunque se omita la guarda del ORM."""
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    revision = _registrar_datos(actor, gasto, DATOS_COMPLETOS)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE gastos_revisiondatostransferencia "
                    "SET titular_nombre = %s WHERE id = %s",
                    ["Titular alterado por SQL directo", revision.pk],
                )

    actual = RevisionDatosTransferencia.objects.get(pk=revision.pk)
    assert actual.titular_nombre == DATOS_COMPLETOS["titular_nombre"]


@pytest.mark.django_db
def test_numero_de_revision_es_unico_por_gasto(actor_factory: Any) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RevisionDatosTransferencia.objects.create(
                solicitud=gasto,
                numero_revision=1,
                actor_id=user.pk,
                **DATOS_NUEVOS,
            )


# --------------------------------------------------------------------------- #
# Autorización de escritura
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_solo_el_titular_con_presentar_puede_corregir(actor_factory: Any) -> None:
    owner, owner_actor = actor_factory(
        ("gastos.presentar", "gastos.consultar_propias")
    )
    _, otro_actor = actor_factory(
        ("gastos.presentar", "gastos.consultar_todas")
    )
    titular_sin_presentar = Actor(
        subject_id=owner_actor.subject_id,
        capabilities=frozenset({"gastos.consultar_propias"}),
    )
    gasto = _crear_gasto(owner)

    with pytest.raises(DatosTransferenciaPermissionDeniedError):
        _registrar_datos(otro_actor, gasto, DATOS_COMPLETOS)
    with pytest.raises(DatosTransferenciaPermissionDeniedError):
        _registrar_datos(titular_sin_presentar, gasto, DATOS_COMPLETOS)

    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_actor_sin_visibilidad_recibe_404_sin_escribir(actor_factory: Any) -> None:
    owner, _ = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    _, ajeno = actor_factory(("gastos.presentar",))
    gasto = _crear_gasto(owner)

    with pytest.raises(DatosTransferenciaNotFoundError):
        _registrar_datos(ajeno, gasto, DATOS_COMPLETOS)

    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_correccion_bloqueada_por_solicitud_rechazada(actor_factory: Any) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user, estado=EstadoSolicitud.RECHAZADA)

    with pytest.raises(DatosTransferenciaBloqueadaError):
        _registrar_datos(actor, gasto, DATOS_COMPLETOS)

    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_correccion_bloqueada_si_el_pago_ya_fue_registrado(
    actor_factory: Any, fake_document_provider: Any
) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    _, payment_actor = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)
    _registrar_pago(payment_actor, gasto, fake_document_provider)

    with pytest.raises(DatosTransferenciaBloqueadaError):
        _registrar_datos(actor, gasto, DATOS_NUEVOS)

    assert RevisionDatosTransferencia.objects.filter(solicitud_id=gasto.pk).count() == 1
    assert PagoExterno.objects.filter(solicitud_id=gasto.pk).count() == 1
    actual = RevisionDatosTransferencia.objects.get(solicitud_id=gasto.pk)
    assert datos_de_revision(actual) == DATOS_COMPLETOS


# --------------------------------------------------------------------------- #
# Lectura autorizada y denegada
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_lectura_reservada_a_titular_y_actor_de_pago_con_visibilidad(
    actor_factory: Any,
) -> None:
    user, owner_actor = actor_factory(
        ("gastos.presentar", "gastos.consultar_propias")
    )
    _, payment_actor = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )
    _, lector_global = actor_factory(("gastos.consultar_todas",))
    _, solo_pago = actor_factory(("gastos.registrar_pago",))
    _, sin_capacidades = actor_factory(())
    gasto = _crear_gasto(user)
    _registrar_datos(owner_actor, gasto, DATOS_COMPLETOS)

    assert consultar_revisiones_datos_transferencia(owner_actor, gasto.pk) is not None
    assert consultar_revisiones_datos_transferencia(payment_actor, gasto.pk) is not None
    assert consultar_revisiones_datos_transferencia(lector_global, gasto.pk) is None
    assert consultar_revisiones_datos_transferencia(solo_pago, gasto.pk) is None
    assert consultar_revisiones_datos_transferencia(sin_capacidades, gasto.pk) is None

    assert puede_consultar_datos_transferencia(owner_actor, gasto) is True
    assert puede_consultar_datos_transferencia(payment_actor, gasto) is True
    assert puede_consultar_datos_transferencia(lector_global, gasto) is False
    assert puede_consultar_datos_transferencia(solo_pago, gasto) is False


@pytest.mark.django_db
def test_detalle_no_expone_datos_a_lector_global(
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
) -> None:
    user, owner_actor = actor_factory(
        ("gastos.presentar", "gastos.consultar_propias")
    )
    lector_user, lector_actor = actor_factory(("gastos.consultar_todas",))
    gasto = _crear_gasto(user)
    _registrar_datos(owner_actor, gasto, DATOS_COMPLETOS)
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: lector_actor)

    response = auth_client(lector_user, lector_actor).get(
        reverse("gastos:detalle", kwargs={"pk": gasto.pk})
    )

    assert response.status_code == 200
    assert response.context["datos_transferencia"] is None
    assert response.context["datos_transferencia_autorizado"] is False
    contenido = response.content.decode()
    for valor in DATOS_COMPLETOS.values():
        assert valor not in contenido
    assert "No disponibles para esta cuenta" in contenido


@pytest.mark.django_db
def test_detalle_muestra_datos_a_titular_y_actor_de_pago(
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
) -> None:
    titular, titular_actor = actor_factory(
        ("gastos.presentar", "gastos.consultar_propias")
    )
    pago_user, pago_actor = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )
    gasto = _crear_gasto(titular)
    _registrar_datos(titular_actor, gasto, DATOS_COMPLETOS)

    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: titular_actor)
    respuesta_titular = auth_client(titular, titular_actor).get(
        reverse("gastos:detalle", kwargs={"pk": gasto.pk})
    )
    assert respuesta_titular.status_code == 200
    assert len(respuesta_titular.context["datos_transferencia"]) == 1
    assert "Corregir datos de transferencia" in respuesta_titular.content.decode()
    for valor in DATOS_COMPLETOS.values():
        assert valor in respuesta_titular.content.decode()

    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: pago_actor)
    respuesta_pago = auth_client(pago_user, pago_actor).get(
        reverse("gastos:detalle", kwargs={"pk": gasto.pk})
    )
    assert respuesta_pago.status_code == 200
    assert len(respuesta_pago.context["datos_transferencia"]) == 1
    for valor in DATOS_COMPLETOS.values():
        assert valor in respuesta_pago.content.decode()
    assert "Corregir datos de transferencia" not in respuesta_pago.content.decode()


@pytest.mark.django_db
def test_detalle_distingue_revision_actual_e_historial(
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)
    _registrar_datos(actor, gasto, DATOS_NUEVOS)
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)

    response = auth_client(user, actor).get(
        reverse("gastos:detalle", kwargs={"pk": gasto.pk})
    )

    assert response.status_code == 200
    assert response.context["datos_transferencia_actual"].numero_revision == 2
    historial = response.context["datos_transferencia_historial"]
    assert [revision.numero_revision for revision in historial] == [1]
    contenido = response.content.decode()
    assert "Ver revisiones anteriores (1)" in contenido
    assert DATOS_COMPLETOS["titular_nombre"] in contenido
    assert DATOS_NUEVOS["titular_nombre"] in contenido


@pytest.mark.django_db
def test_detalle_titular_ofrece_agregar_datos_si_no_existen(
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
) -> None:
    user, actor = actor_factory(("gastos.presentar", "gastos.consultar_propias"))
    gasto = _crear_gasto(user)
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)

    response = auth_client(user, actor).get(
        reverse("gastos:detalle", kwargs={"pk": gasto.pk})
    )

    assert response.status_code == 200
    assert response.context["datos_transferencia"] == ()
    contenido = response.content.decode()
    assert "No hay datos de transferencia informados" in contenido
    assert "Agregar datos de transferencia" in contenido


# --------------------------------------------------------------------------- #
# Vistas de corrección
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_post_correccion_ignora_actor_y_fecha_inyectados(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_inyeccion", ["gastos.presentar", "gastos.consultar_propias"]
    )
    otro = User.objects.create_user(username="otro_actor_inyectado")
    gasto = _crear_gasto(user)
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk}),
        {
            **DATOS_COMPLETOS,
            "actor": str(otro.pk),
            "actor_id": str(otro.pk),
            "fecha_hora": "2000-01-01 00:00:00",
        },
    )

    assert response.status_code == 302
    revision = RevisionDatosTransferencia.objects.get(solicitud_id=gasto.pk)
    assert revision.actor_id == user.pk
    assert revision.fecha_hora.year != 2000


@pytest.mark.django_db
def test_get_correccion_inicializa_la_revision_actual(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_get_correccion", ["gastos.presentar", "gastos.consultar_propias"]
    )
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)

    response = auth_client(user, actor).get(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk})
    )

    assert response.status_code == 200
    assert response.context["revision_actual"].numero_revision == 1
    assert response.context["form"].initial == DATOS_COMPLETOS


@pytest.mark.django_db
def test_post_correccion_crea_revision_y_redirige(
    create_actor: Any, csrf_auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_post_correccion", ["gastos.presentar", "gastos.consultar_propias"]
    )
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk}),
        {**DATOS_NUEVOS, "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 302
    assert response.url == reverse("gastos:detalle", kwargs={"pk": gasto.pk})
    revisiones = RevisionDatosTransferencia.objects.filter(
        solicitud_id=gasto.pk
    ).order_by("numero_revision")
    assert [revision.numero_revision for revision in revisiones] == [1, 2]
    assert datos_de_revision(revisiones[1]) == DATOS_NUEVOS


@pytest.mark.django_db
def test_post_correccion_sin_datos_previos_crea_primera_revision(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_post_sin_datos", ["gastos.presentar", "gastos.consultar_propias"]
    )
    gasto = _crear_gasto(user)
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk}),
        DATOS_COMPLETOS,
    )

    assert response.status_code == 302
    revision = RevisionDatosTransferencia.objects.get(solicitud_id=gasto.pk)
    assert revision.numero_revision == 1
    assert revision.actor_id == user.pk
    assert datos_de_revision(revision) == DATOS_COMPLETOS


@pytest.mark.django_db
def test_post_correccion_parcial_conserva_valores_y_no_escribe(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_post_parcial", ["gastos.presentar", "gastos.consultar_propias"]
    )
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk}),
        {
            "titular_nombre": "Titular Parcial Conservado",
            "identificacion": "",
            "cbu_alias": "",
            "correo_comprobante": "",
            "centro_costo": "",
        },
    )

    assert response.status_code == 400
    assert "Titular Parcial Conservado" in response.content.decode()
    assert response.context["form"].errors
    assert RevisionDatosTransferencia.objects.filter(solicitud_id=gasto.pk).count() == 1


@pytest.mark.django_db
def test_get_correccion_de_gasto_ajeno_retorna_403(
    create_actor: Any, auth_client: Any
) -> None:
    titular, _ = create_actor(
        "titular_ajeno_correccion", ["gastos.presentar", "gastos.consultar_propias"]
    )
    lector_user, lector_actor = create_actor(
        "lector_ajeno_correccion", ["gastos.consultar_todas"]
    )
    gasto = _crear_gasto(titular)

    response = auth_client(lector_user, lector_actor).get(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk})
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_get_correccion_despues_de_pago_redirige_con_explicacion(
    create_actor: Any,
    actor_factory: Any,
    auth_client: Any,
    fake_document_provider: Any,
) -> None:
    user, actor = create_actor(
        "titular_pago_get", ["gastos.presentar", "gastos.consultar_propias"]
    )
    _, payment_actor = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )
    gasto = _crear_gasto(user)
    _registrar_pago(payment_actor, gasto, fake_document_provider)

    response = auth_client(user, actor).get(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk}), follow=True
    )

    assert response.status_code == 200
    assert "ya tiene un pago registrado" in response.content.decode()
    assert RevisionDatosTransferencia.objects.count() == 0


@pytest.mark.django_db
def test_post_correccion_despues_de_pago_retorna_409_sin_escribir(
    create_actor: Any,
    actor_factory: Any,
    auth_client: Any,
    fake_document_provider: Any,
) -> None:
    user, actor = create_actor(
        "titular_pago_post", ["gastos.presentar", "gastos.consultar_propias"]
    )
    _, payment_actor = actor_factory(
        ("gastos.registrar_pago", "gastos.consultar_todas")
    )
    gasto = _crear_gasto(user)
    _registrar_datos(actor, gasto, DATOS_COMPLETOS)
    _registrar_pago(payment_actor, gasto, fake_document_provider)
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk}),
        DATOS_NUEVOS,
    )

    assert response.status_code == 409
    assert "ya tiene un pago registrado" in response.content.decode()
    assert RevisionDatosTransferencia.objects.filter(solicitud_id=gasto.pk).count() == 1


@pytest.mark.django_db
def test_post_correccion_rechazada_retorna_409_sin_escribir(
    create_actor: Any, auth_client: Any
) -> None:
    user, actor = create_actor(
        "titular_rechazada", ["gastos.presentar", "gastos.consultar_propias"]
    )
    gasto = _crear_gasto(user, estado=EstadoSolicitud.RECHAZADA)
    client = auth_client(user, actor)

    response = client.post(
        reverse("gastos:datos-transferencia", kwargs={"pk": gasto.pk}),
        DATOS_COMPLETOS,
    )

    assert response.status_code == 409
    assert "rechazada" in response.content.decode()
    assert RevisionDatosTransferencia.objects.count() == 0
