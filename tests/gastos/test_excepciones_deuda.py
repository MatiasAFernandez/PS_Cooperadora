from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import connections
from django.urls import reverse
from django.utils import timezone

from gastos.excepciones_deuda import (
    excepcion_deuda_vigente,
    otorgar_excepcion_deuda,
    revocar_excepcion_deuda,
)
from gastos.models import ExcepcionDeudaDocumental, SolicitudGasto, TipoFlujoGasto
from gastos.services import verificar_deuda_documental_solicitante
from identidad.models import CuentaLocal
from identidad.services import actor_para_usuario, has_capability
from tests.gastos.test_alertas_deuda_documental import (
    _adjuntar_factura,
    _crear_compra_directa_pagada,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def instante(monkeypatch):
    fecha = datetime(2026, 11, 27, 14, 20, tzinfo=UTC)
    monkeypatch.setattr(timezone, "now", lambda: fecha)
    return fecha


@pytest.fixture
def administrador(create_actor):
    usuario, _ = create_actor("admin_excepciones_demo", ["gastos.consultar_todas"])
    grupo, _ = Group.objects.get_or_create(name="demo_gastos_excepciones")
    usuario.groups.add(grupo)
    return usuario, actor_para_usuario(usuario)


@pytest.fixture
def titular(create_actor):
    usuario, actor = create_actor("titular_excepcion_demo", ["gastos.presentar"])
    usuario.first_name = "Lucía"
    usuario.last_name = "Herrera Demo"
    usuario.email = "lucia.herrera@example.invalid"
    usuario.save(update_fields=["first_name", "last_name", "email"])
    return usuario, actor


def _otorgar_formulario(vence_en, motivo="Compra urgente para el laboratorio"):
    return {
        "accion": "otorgar",
        "motivo": motivo,
        "vence_en": timezone.localtime(vence_en).strftime("%Y-%m-%dT%H:%M"),
    }


def test_otorgamiento_y_revocacion_por_cuenta(administrador, titular, auth_client, instante):
    usuario, _ = titular
    cliente = auth_client(administrador[0])
    ruta_busqueda = reverse("gastos:excepciones_urgencia")
    ruta_titular = reverse("gastos:excepcion_titular", args=[usuario.pk])
    vencimiento = instante + timedelta(days=2)

    rendiciones = cliente.get(reverse("gastos:deuda_documental"))
    assert ruta_busqueda in rendiciones.content.decode()
    for consulta in ("Lucía Herrera", "lucia.herrera@example.invalid"):
        respuesta = cliente.get(ruta_busqueda, {"q": consulta})
        assert ruta_titular in respuesta.content.decode()

    respuesta = cliente.get(ruta_titular)
    assert respuesta.context["form"]["vence_en"].initial == instante + timedelta(days=7)
    assert 'value="2026-12-04T11:20"' in respuesta.content.decode()
    assert cliente.post(ruta_titular, _otorgar_formulario(vencimiento, "  ")).status_code == 400
    assert cliente.post(ruta_titular, _otorgar_formulario(instante)).status_code == 400
    assert not ExcepcionDeudaDocumental.objects.exists()

    concedida = cliente.post(ruta_titular, _otorgar_formulario(vencimiento), follow=True)
    excepcion = ExcepcionDeudaDocumental.objects.get(titular=usuario)
    assert excepcion.vence_en == vencimiento
    assert excepcion.otorgada_por == administrador[0]
    assert excepcion.otorgada_en == instante
    assert "Otorgaste la excepción por urgencia." in concedida.content.decode()

    revocacion = {"accion": "revocar", "excepcion_id": excepcion.pk, "motivo": "  "}
    assert cliente.post(ruta_titular, revocacion).status_code == 400
    assert excepcion_deuda_vigente(usuario.pk) == excepcion
    revocacion["motivo"] = "La compra pudo esperar"
    revocada = cliente.post(ruta_titular, revocacion, follow=True)
    excepcion.refresh_from_db()
    assert excepcion.revocada_por == administrador[0]
    assert excepcion.revocada_en == instante
    assert excepcion.motivo_revocacion == revocacion["motivo"]
    for texto in (excepcion.motivo, excepcion.motivo_revocacion, "Revocaste la excepción"):
        assert texto in revocada.content.decode()
    assert excepcion_deuda_vigente(usuario.pk) is None

    # Una cuenta con historial permanece consultable si se la suspende.
    usuario.is_active = False
    usuario.save(update_fields=["is_active"])
    assert ruta_titular in cliente.get(ruta_busqueda, {"q": usuario.email}).content.decode()
    assert cliente.get(ruta_titular).context["form"] is None


@pytest.mark.parametrize(
    ("local_habilitado", "estado", "correo_verificado", "grupos", "elegible"),
    [
        (False, CuentaLocal.Estado.APROBADA, True, ("local_solicitante",), False),
        (True, CuentaLocal.Estado.PENDIENTE, True, ("demo_solicitante",), False),
        (True, CuentaLocal.Estado.RECHAZADA, True, ("demo_solicitante",), False),
        (True, CuentaLocal.Estado.APROBADA, False, ("demo_solicitante",), False),
        (True, None, False, ("local_solicitante",), False),
        (True, CuentaLocal.Estado.APROBADA, True, ("local_solicitante", "demo_solicitante"), True),
        (False, None, False, ("demo_solicitante",), True),
    ],
    ids=[
        "adaptador-local-apagado",
        "local-pendiente",
        "local-rechazada",
        "local-sin-verificar",
        "demo-con-grupo-local",
        "local-habilitada",
        "demo-habilitada",
    ],
)
def test_busqueda_respeta_elegibilidad_y_mantiene_historial(
    local_habilitado,
    estado,
    correo_verificado,
    grupos,
    elegible,
    administrador,
    auth_client,
    settings,
    instante,
):
    settings.LOCAL_IDENTITY_ENABLED = local_habilitado
    correo = "elegibilidad@example.invalid"
    usuario = get_user_model().objects.create_user(username="elegibilidad_demo", email=correo)
    usuario.groups.add(*(Group.objects.get_or_create(name=nombre)[0] for nombre in grupos))
    if estado is not None:
        CuentaLocal.objects.create(
            user=usuario,
            email=correo,
            nombre_completo="Cuenta sintética de elegibilidad",
            estado=estado,
            email_verificado_en=instante if correo_verificado else None,
        )
    assert has_capability(actor_para_usuario(usuario), "gastos.presentar") is elegible

    cliente = auth_client(administrador[0])
    busqueda = reverse("gastos:excepciones_urgencia")
    ficha = reverse("gastos:excepcion_titular", args=[usuario.pk])
    resultado = cliente.get(busqueda, {"q": correo})
    assert [cuenta.pk for cuenta in resultado.context["pagina"]] == (
        [usuario.pk] if elegible else []
    )
    assert cliente.get(ficha).status_code == (200 if elegible else 404)
    if elegible:
        return

    anterior = ExcepcionDeudaDocumental.objects.create(
        titular=usuario,
        otorgada_por=administrador[0],
        otorgada_en=instante - timedelta(days=9),
        vence_en=instante - timedelta(days=2),
        motivo="Excepción histórica de la cuenta",
    )
    resultado_con_historial = cliente.get(busqueda, {"q": correo})
    assert [cuenta.pk for cuenta in resultado_con_historial.context["pagina"]] == [usuario.pk]
    respuesta = cliente.get(ficha)
    assert respuesta.status_code == 200
    assert list(respuesta.context["historial"]) == [anterior]
    assert respuesta.context["form"] is None


@pytest.mark.parametrize("accion", ["otorgar", "revocar"])
def test_guardar_regresa_a_la_primera_pagina_con_la_busqueda(
    accion, administrador, titular, auth_client, instante
):
    usuario, _ = titular
    ExcepcionDeudaDocumental.objects.bulk_create(
        [
            ExcepcionDeudaDocumental(
                titular=usuario,
                otorgada_por=administrador[0],
                otorgada_en=instante - timedelta(days=2 * dias),
                vence_en=instante - timedelta(days=2 * dias - 1),
                motivo=f"Motivo histórico {dias}",
            )
            for dias in range(1, 12)
        ]
    )
    vence_en = instante + timedelta(days=1)
    if accion == "otorgar":
        datos = _otorgar_formulario(vence_en)
    else:
        vigente = otorgar_excepcion_deuda(
            actor=administrador[1], titular_id=usuario.pk, motivo="Urgencia", vence_en=vence_en
        )
        datos = {"accion": "revocar", "excepcion_id": vigente.pk, "motivo": "Urgencia resuelta"}

    cliente = auth_client(administrador[0])
    consulta = "Lucía Herrera / Laboratorio"
    origen = reverse(
        "gastos:excepcion_titular", args=[usuario.pk], query={"page": 2, "q": consulta}
    )
    invalida = cliente.post(origen, datos | {"motivo": "   "})
    assert invalida.status_code == 400
    assert invalida.context["historial"].number == 2
    assert invalida.context["consulta"] == consulta
    assert "motivo" in invalida.context["form"].errors

    guardada = cliente.post(origen, datos, follow=True)
    destino = reverse("gastos:excepcion_titular", args=[usuario.pk], query={"q": consulta})
    assert guardada.redirect_chain == [(destino, 302)]
    assert guardada.context["historial"].number == 1
    reciente = guardada.context["historial"][0]
    motivo = reciente.motivo if accion == "otorgar" else reciente.motivo_revocacion
    assert motivo == datos["motivo"]


@pytest.mark.parametrize(
    ("grupos", "staff"),
    [
        (("demo_solicitante",), False),
        (("demo_lectura",), False),
        (("demo_administracion", "demo_operadora"), False),
        (("demo_gastos_excepciones",), False),
        (("demo_lectura",), True),
    ],
)
def test_gestion_requiere_capacidad_explicita(grupos, staff, titular, auth_client, instante):
    usuario = get_user_model().objects.create_user(
        username="sin_autoridad", is_staff=staff, is_superuser=staff
    )
    usuario.groups.add(*(Group.objects.get_or_create(name=nombre)[0] for nombre in grupos))
    cliente = auth_client(usuario)
    ruta_titular = reverse("gastos:excepcion_titular", args=[titular[0].pk])
    assert cliente.get(reverse("gastos:excepciones_urgencia")).status_code == 403
    assert cliente.get(ruta_titular).status_code == 403
    assert (
        cliente.post(ruta_titular, _otorgar_formulario(instante + timedelta(days=1))).status_code
        == 403
    )
    assert cliente.post(ruta_titular, {"accion": "revocar", "excepcion_id": 1}).status_code == 403
    assert not ExcepcionDeudaDocumental.objects.exists()


def test_post_de_gestion_exige_csrf(administrador, titular, csrf_auth_client, instante):
    cliente, _ = csrf_auth_client(administrador[0])
    ruta = reverse("gastos:excepcion_titular", args=[titular[0].pk])
    respuesta = cliente.post(ruta, _otorgar_formulario(instante + timedelta(days=1)))
    assert respuesta.status_code == 403
    assert not ExcepcionDeudaDocumental.objects.exists()


@pytest.mark.parametrize("fin", ["vencimiento", "revocacion", "demo_desactivada"])
def test_la_excepcion_solo_levanta_el_bloqueo_mientras_corresponde(
    fin, administrador, titular, create_actor, auth_client, settings, instante, monkeypatch
):
    usuario, actor = titular
    _, administrador_actor = administrador
    pago = timezone.localdate() - timedelta(days=45)
    deudas = [
        _crear_compra_directa_pagada(usuario, f"Rendición vencida {i}", pago) for i in range(3)
    ]
    otro, otro_actor = create_actor("otro_titular_demo", ["gastos.presentar"])
    for i in range(3):
        _crear_compra_directa_pagada(otro, f"Rendición de otra cuenta {i}", pago)

    cliente = auth_client(usuario)
    presentar = reverse("gastos:presentar")
    solicitud = {
        "concepto": "Compra de insumos con excepción",
        "monto_estimado": "10000.00",
        "unidad_requirente": "Laboratorio",
        "tipo_flujo": TipoFlujoGasto.COMPRA_DIRECTA,
    }
    assert cliente.post(presentar, solicitud).status_code == 400
    vence_en = instante + timedelta(days=1)
    excepcion = otorgar_excepcion_deuda(
        actor=administrador_actor, titular_id=usuario.pk, motivo="Urgencia", vence_en=vence_en
    )
    assert excepcion_deuda_vigente(usuario.pk, instante=vence_en - timedelta(microseconds=1))
    assert excepcion_deuda_vigente(usuario.pk, instante=vence_en) is None
    assert verificar_deuda_documental_solicitante(otro_actor).tiene_bloqueo

    alta = cliente.get(presentar)
    assert "Excepción por urgencia vigente" in alta.content.decode()
    assert cliente.post(presentar, solicitud).status_code == 302
    resumen = verificar_deuda_documental_solicitante(actor)
    assert resumen.total_en_mora == 3
    assert not resumen.tiene_bloqueo

    if fin == "vencimiento":
        monkeypatch.setattr(timezone, "now", lambda: vence_en)
    elif fin == "revocacion":
        revocar_excepcion_deuda(
            actor=administrador_actor,
            titular_id=usuario.pk,
            excepcion_id=excepcion.pk,
            motivo="Se regularizó la urgencia",
        )
    else:
        settings.DEMO_IDENTITY_ENABLED = False
        assert verificar_deuda_documental_solicitante(actor).tiene_bloqueo
        return

    assert cliente.post(presentar, solicitud).status_code == 400
    assert (
        SolicitudGasto.objects.filter(solicitante=usuario, concepto=solicitud["concepto"]).count()
        == 1
    )
    _adjuntar_factura(deudas[0], usuario)
    assert cliente.post(presentar, solicitud).status_code == 302


def test_revocacion_atrasada_no_afecta_una_nueva_excepcion(administrador, titular, instante):
    _, actor = administrador
    usuario, _ = titular
    datos = {"actor": actor, "titular_id": usuario.pk, "motivo": "Urgencia"}
    vence_en = instante + timedelta(days=1)
    anterior = otorgar_excepcion_deuda(**datos, vence_en=vence_en)
    revocar_excepcion_deuda(**datos, excepcion_id=anterior.pk)
    nueva = otorgar_excepcion_deuda(**datos, vence_en=vence_en)

    with pytest.raises(ValidationError, match="seleccionada ya no está vigente"):
        revocar_excepcion_deuda(**datos, excepcion_id=anterior.pk)
    assert excepcion_deuda_vigente(usuario.pk) == nueva


@pytest.mark.django_db(transaction=True)
def test_dos_concesiones_concurrentes_crean_una_sola_excepcion(administrador, titular, instante):
    _, actor = administrador
    usuario, _ = titular
    barrera = Barrier(2)

    def otorgar(indice):
        try:
            barrera.wait(timeout=10)
            otorgar_excepcion_deuda(
                actor=actor,
                titular_id=usuario.pk,
                motivo=f"Urgencia {indice}",
                vence_en=instante + timedelta(days=1),
            )
        except ValidationError as error:
            assert error.messages == ["Ya hay una excepción vigente para este titular."]
            return False
        finally:
            connections.close_all()
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(otorgar, [1, 2], timeout=20))

    assert sorted(resultados) == [False, True]
    assert ExcepcionDeudaDocumental.objects.filter(titular=usuario).count() == 1
