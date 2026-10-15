"""Formulario consumidor de pago externo (Issue #15, corte C03 + UI).

Cubre el orden de comprobaciones de la vista, el selector documental cargado
sólo desde servidor, la revalidación transaccional, el bypass idempotente sin
proveedor y el mapeo de errores. No usa identidad ni proveedor reales: sólo
actores y dobles sintéticos de prueba.
"""

from datetime import date
from decimal import Decimal
from threading import Event, Thread
from typing import Any

import pytest
from django.db import connections
from django.test import Client
from django.urls import reverse

from gastos import views as gastos_views
from gastos.contracts import DocumentVerificationError, OpcionDocumental
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno
from gastos.payments import (
    PaymentConflictError,
    PaymentInvalidExpenseStateError,
    registrar_pago_externo,
)
from identidad.services import Actor

CAPS_PAGO_UI = (
    "gastos.consultar_todas",
    "gastos.registrar_pago",
    "documentos.ver_metadatos",
)


@pytest.fixture
def actor_pago(actor_factory: Any, monkeypatch: Any) -> Any:
    """Actor sintético con visibilidad total, registro de pago y metadatos."""
    user, actor = actor_factory(CAPS_PAGO_UI)
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    return user, actor


@pytest.fixture
def opcion_pago() -> OpcionDocumental:
    """Opción documental sintética sin archivo, ruta, hash ni revisión."""
    return OpcionDocumental(
        referencia_documental="doc-opaco-1",
        tipo_documento="factura",
        etiqueta="Factura sintética 1",
    )


@pytest.fixture
def provider_pago(
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
) -> Any:
    """Configura el proveedor documental sólo desde settings de servidor."""
    proveedor = fake_document_provider(opciones=[opcion_pago])
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = proveedor
    return proveedor


def _url_pagar(solicitud: Any) -> str:
    return reverse("gastos:pagar", kwargs={"pk": solicitud.pk})


def _url_detalle(solicitud: Any) -> str:
    return reverse("gastos:detalle", kwargs={"pk": solicitud.pk})


def _payload_pago(referencia_documental: str = "doc-opaco-1") -> dict[str, str]:
    return {
        "importe": "825.40",
        "fecha_pago": "2026-10-14",
        "referencia_externa": "ref-sintetica-001",
        "referencia_documental": referencia_documental,
    }


# --------------------------------------------------------------------------- #
# GET: formulario, permisos, ausencia de proveedor
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_get_formulario_muestra_selector_de_opciones(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_pagar(solicitud))

    assert response.status_code == 200
    assert response.context["form"].fields["referencia_documental"].choices == [
        ("doc-opaco-1", "Factura sintética 1")
    ]
    contenido = response.content
    assert b"Registrar Pago Externo" in contenido
    assert b'value="doc-opaco-1"' in contenido
    assert b"AAAA-MM-DD" in contenido
    assert provider_pago.llamadas_listado[0]["gasto_id"] == solicitud.pk
    assert provider_pago.llamadas_listado[0]["tipos_admitidos"] == (
        "factura",
        "presupuesto",
        "proforma",
    )


@pytest.mark.django_db
def test_get_sin_permiso_registrar_pago_retorna_403(
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_factory(("gastos.consultar_todas", "documentos.ver_metadatos"))
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_pagar(solicitud))

    assert response.status_code == 403
    assert provider_pago.llamadas_listado == []


@pytest.mark.django_db
def test_get_sin_permiso_metadatos_retorna_403_antes_del_proveedor(
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_factory(("gastos.consultar_todas", "gastos.registrar_pago"))
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_pagar(solicitud))

    assert response.status_code == 403
    # La capacidad documental se exige antes de invocar al proveedor o su listado.
    assert provider_pago.llamadas_listado == []


@pytest.mark.django_db
def test_get_ajena_o_inexistente_retorna_404(
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_factory(
        ("gastos.consultar_propias", "gastos.registrar_pago", "documentos.ver_metadatos")
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    solicitud_ajena = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)

    client = auth_client(user, actor)
    assert client.get(_url_pagar(solicitud_ajena)).status_code == 404
    assert client.get(reverse("gastos:pagar", kwargs={"pk": 999999})).status_code == 404


@pytest.mark.django_db
def test_get_sin_proveedor_configurado_retorna_503(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    capacidad_registrar_pago: Any,
) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_pagar(solicitud))

    assert response.status_code == 503


@pytest.mark.django_db
def test_get_con_listado_con_error_retorna_503_generico(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(
        error_listado=RuntimeError("detalle interno del listado")
    )
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_pagar(solicitud))

    assert response.status_code == 503
    assert b"detalle interno del listado" not in response.content


@pytest.mark.django_db
def test_get_en_estado_no_aceptado_o_con_pago_redirige_al_detalle(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud_presentada = solicitud_factory(
        estado=EstadoSolicitud.PRESENTADA, solicitante=user
    )
    client = auth_client(user, actor)

    response = client.get(_url_pagar(solicitud_presentada))
    assert response.status_code == 302
    assert response.url == _url_detalle(solicitud_presentada)


# --------------------------------------------------------------------------- #
# POST: alta nueva, normalización C03 y mapeo de errores
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_post_valido_registra_pago_y_redirige(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 302
    assert response.url == _url_detalle(solicitud)
    pago = PagoExterno.objects.get()
    assert pago.solicitud_id == solicitud.pk
    assert pago.importe == Decimal("825.40")
    assert pago.fecha_pago == date(2026, 10, 14)
    assert pago.referencia_externa == "ref-sintetica-001"
    assert pago.referencia_documental == "doc-opaco-1"
    assert EventoPagoExterno.objects.count() == 1
    assert len(provider_pago.llamadas) == 1
    assert provider_pago.llamado_en_atomic is True


@pytest.mark.django_db
def test_post_entrega_valores_originales_a_c03_sin_strip_previo(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """El formulario no normaliza: C03 recibe y normaliza los valores originales."""
    opcion = OpcionDocumental(
        referencia_documental="  doc-opaco-con-espacios  ",
        tipo_documento="presupuesto",
        etiqueta="Presupuesto sintético",
    )
    proveedor = fake_document_provider(opciones=[opcion])
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = proveedor

    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {
            "importe": " 825.40 ",
            "fecha_pago": " 2026-10-14 ",
            "referencia_externa": "  ref-sintetica-001  ",
            "referencia_documental": "  doc-opaco-con-espacios  ",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    pago = PagoExterno.objects.get()
    assert pago.importe == Decimal("825.40")
    assert pago.fecha_pago == date(2026, 10, 14)
    assert pago.referencia_externa == "ref-sintetica-001"
    assert pago.referencia_documental == "  doc-opaco-con-espacios  "
    assert proveedor.llamadas[0]["referencia_documental"] == "  doc-opaco-con-espacios  "


@pytest.mark.django_db
def test_post_entrada_invalida_retorna_400_con_contexto(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "importe": "no-es-un-importe", "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 400
    assert response.context["solicitud"].pk == solicitud.pk
    assert response.context["form"].non_field_errors()
    assert PagoExterno.objects.count() == 0
    assert provider_pago.llamadas == []


@pytest.mark.django_db
def test_post_opcion_fuera_del_listado_retorna_400(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago("doc-no-listado"), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 400
    assert "referencia_documental" in response.context["form"].errors
    assert PagoExterno.objects.count() == 0
    assert provider_pago.llamadas == []


@pytest.mark.django_db
def test_post_estado_no_aceptado_retorna_409(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.PRESENTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 409
    assert response.context["form"]["importe"].value() == "825.40"
    assert response.context["formulario_habilitado"] is False
    assert 'type="submit" class="btn" disabled' in response.content.decode()
    assert provider_pago.llamadas_listado == []
    assert PagoExterno.objects.count() == 0
    assert provider_pago.llamadas == []


@pytest.mark.django_db
def test_post_cambio_de_estado_conserva_datos_y_deshabilita_reintento(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    def pago_rechazado_por_estado(**kwargs: Any) -> None:
        raise PaymentInvalidExpenseStateError("estado actualizado concurrentemente")

    monkeypatch.setattr("gastos.views.registrar_pago_externo", pago_rechazado_por_estado)
    client, token = csrf_auth_client(user, actor)
    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 409
    assert response.context["form"]["importe"].value() == "825.40"
    assert response.context["formulario_habilitado"] is False
    assert 'type="submit" class="btn" disabled' in response.content.decode()


@pytest.mark.django_db
def test_post_error_documental_retorna_409_generico_sin_detalle(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(
        opciones=[opcion_pago],
        error=DocumentVerificationError("detalle-interno-confidencial"),
    )
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 409
    assert b"detalle-interno-confidencial" not in response.content
    assert response.context["form"]["importe"].value() == "825.40"
    assert response.context["form"]["referencia_externa"].value() == "ref-sintetica-001"
    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0


@pytest.mark.django_db
def test_post_documento_reemplazado_refresca_opciones_y_conserva_campos(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    opcion_vigente = OpcionDocumental(
        referencia_documental="doc-opaco-2",
        tipo_documento="factura",
        etiqueta="Factura sintética vigente",
    )
    provider = fake_document_provider(
        opciones=[opcion_pago],
        error=DocumentVerificationError("versión reemplazada; detalle confidencial"),
    )
    listados = iter(([opcion_pago], [opcion_vigente]))
    provider.listar_opciones_para_pago = lambda **kwargs: next(listados)
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = provider

    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)
    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 409
    assert response.context["form"]["importe"].value() == "825.40"
    assert response.context["form"]["referencia_externa"].value() == "ref-sintetica-001"
    assert response.context["form"].fields["referencia_documental"].choices == [
        ("doc-opaco-2", "Factura sintética vigente")
    ]
    assert "versión reemplazada".encode() not in response.content
    assert b'doc-opaco-2' in response.content
    assert PagoExterno.objects.count() == 0


@pytest.mark.django_db
def test_post_con_provider_en_el_payload_no_se_deriva_del_cliente(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    """Aun enviando un provider por POST, el servidor falla cerrado sin settings."""
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None
    intruso = fake_document_provider(opciones=[opcion_pago])
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {
            **_payload_pago(),
            "document_provider": "gastos.document_provider.cargar_proveedor_documental",
            "GASTOS_PAYMENT_DOCUMENT_PROVIDER": "intruso",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 503
    assert intruso.llamadas_listado == []
    assert PagoExterno.objects.count() == 0


# --------------------------------------------------------------------------- #
# POST: idempotencia sobre un pago existente (bypass sin proveedor)
# --------------------------------------------------------------------------- #


def _registrar_pago_previo(actor: Any, solicitud: Any, proveedor: Any) -> PagoExterno:
    return registrar_pago_externo(
        actor=actor,
        solicitud_id=solicitud.pk,
        importe="825.40",
        fecha_pago="2026-10-14",
        referencia_externa="ref-sintetica-001",
        referencia_documental="doc-opaco-1",
        document_provider=proveedor,
    )


@pytest.mark.django_db
def test_post_reenvio_identico_redirige_sin_listar_ni_usar_proveedor(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    _registrar_pago_previo(actor, solicitud, fake_document_provider(opciones=[opcion_pago]))

    # Proveedor configurado pero que fallaría si la vista intentara listar o validar.
    espia = fake_document_provider(
        opciones=[opcion_pago],
        error_listado=RuntimeError("no debe listarse"),
        error=DocumentVerificationError("no debe verificarse"),
    )
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = espia

    client, token = csrf_auth_client(user, actor)
    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 302
    assert response.url == _url_detalle(solicitud)
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert espia.llamadas_listado == []
    assert espia.llamadas == []


@pytest.mark.django_db
def test_post_reenvio_identico_funciona_sin_proveedor_disponible(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    _registrar_pago_previo(actor, solicitud, fake_document_provider(opciones=[opcion_pago]))

    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None
    client, token = csrf_auth_client(user, actor)
    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 302
    assert response.url == _url_detalle(solicitud)
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1


@pytest.mark.django_db
def test_post_reenvio_con_contenido_distinto_retorna_409(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    _registrar_pago_previo(actor, solicitud, fake_document_provider(opciones=[opcion_pago]))
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None

    client, token = csrf_auth_client(user, actor)
    response = client.post(
        _url_pagar(solicitud),
        {
            **_payload_pago(),
            "importe": "50.00",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 409
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    pago = PagoExterno.objects.get()
    assert pago.importe == Decimal("825.40")


@pytest.mark.django_db
def test_post_reenvio_entrada_invalida_retorna_400_con_detalle(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    _registrar_pago_previo(actor, solicitud, fake_document_provider(opciones=[opcion_pago]))
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None

    client, token = csrf_auth_client(user, actor)
    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "importe": "", "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 400
    assert response.context["solicitud"].pk == solicitud.pk
    assert response.context["error_pago"]
    assert PagoExterno.objects.count() == 1


# --------------------------------------------------------------------------- #
# CSRF y detalle
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_post_sin_csrf_es_rechazado_sin_escrituras(
    actor_pago: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.post(_url_pagar(solicitud), _payload_pago())

    assert response.status_code == 403
    assert PagoExterno.objects.count() == 0


@pytest.mark.django_db
def test_detalle_ofrece_accion_solo_con_ambos_permisos_y_provider(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_detalle(solicitud))

    assert response.status_code == 200
    assert response.context["puede_registrar_pago"] is True
    assert response.context["pago_provider_configurado"] is True
    assert b"Registrar pago externo" in response.content
    assert _url_pagar(solicitud).encode() in response.content


@pytest.mark.django_db
def test_detalle_deshabilita_accion_sin_provider_configurado(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    capacidad_registrar_pago: Any,
) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_detalle(solicitud))

    assert response.status_code == 200
    assert response.context["puede_registrar_pago"] is True
    assert response.context["pago_provider_configurado"] is False
    assert "Registrar pago externo (no disponible)" in response.content.decode()
    assert _url_pagar(solicitud).encode() not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("capacidades", "mensaje"),
    [
        (
            ("gastos.consultar_todas", "documentos.ver_metadatos"),
            "falta el permiso para registrar pagos",
        ),
        (
            ("gastos.consultar_todas", "gastos.registrar_pago"),
            "falta el permiso para consultar metadatos documentales",
        ),
    ],
)
def test_detalle_explica_permiso_faltante_sin_consultar_documentos(
    capacidades: tuple[str, ...],
    mensaje: str,
    actor_factory: Any,
    monkeypatch: Any,
    auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_factory(capacidades)
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_detalle(solicitud))

    assert response.status_code == 200
    assert mensaje in response.content.decode()
    assert provider_pago.llamadas_listado == []


@pytest.mark.django_db
def test_get_sin_opciones_documentales_deshabilita_envio(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(opciones=[])
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)

    response = auth_client(user, actor).get(_url_pagar(solicitud))

    assert response.status_code == 200
    assert "No hay opciones documentales disponibles" in response.content.decode()
    assert 'type="submit" class="btn" disabled' in response.content.decode()


@pytest.mark.django_db
def test_detalle_no_ofrece_accion_si_ya_existe_pago(
    actor_pago: Any,
    auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    _registrar_pago_previo(actor, solicitud, fake_document_provider(opciones=[opcion_pago]))
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = None

    response = auth_client(user, actor).get(_url_detalle(solicitud))

    assert response.status_code == 200
    assert response.context["puede_registrar_pago"] is False
    assert _url_pagar(solicitud).encode() not in response.content


# --------------------------------------------------------------------------- #
# B1: permisos, visibilidad y entrada malformada afectados por el reenvío
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_post_ajena_o_inexistente_retorna_404_sin_invocar_proveedor(
    actor_factory: Any,
    monkeypatch: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_factory(
        ("gastos.consultar_propias", "gastos.registrar_pago", "documentos.ver_metadatos")
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    solicitud_ajena = solicitud_factory(estado=EstadoSolicitud.ACEPTADA)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud_ajena),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 404
    assert provider_pago.llamadas_listado == []
    assert provider_pago.llamadas == []
    assert PagoExterno.objects.count() == 0


@pytest.mark.django_db
def test_post_sin_permiso_registrar_pago_precede_al_pago_ya_existente(
    actor_factory: Any,
    monkeypatch: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    """La capacidad independiente de pago no se sustituye por detectar el pago."""
    user, actor_completo = actor_factory(CAPS_PAGO_UI)
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    _registrar_pago_previo(
        actor_completo, solicitud, fake_document_provider(opciones=[opcion_pago])
    )
    espia = fake_document_provider(
        opciones=[opcion_pago],
        error_listado=RuntimeError("no debe listarse"),
    )
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = espia
    actor_sin_pago = Actor(
        subject_id=user.pk,
        capabilities=frozenset(("gastos.consultar_todas", "documentos.ver_metadatos")),
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor_sin_pago)
    client, token = csrf_auth_client(user, actor_sin_pago)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 403
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert espia.llamadas_listado == []
    assert espia.llamadas == []


@pytest.mark.django_db
def test_post_sin_permiso_metadatos_retorna_403_para_alta_nueva(
    actor_factory: Any,
    monkeypatch: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    provider_pago: Any,
    capacidad_registrar_pago: Any,
) -> None:
    user, actor = actor_factory(("gastos.consultar_todas", "gastos.registrar_pago"))
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor)
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 403
    assert provider_pago.llamadas_listado == []
    assert PagoExterno.objects.count() == 0


@pytest.mark.django_db
def test_post_reenvio_de_pago_existente_no_exige_metadatos(
    actor_factory: Any,
    monkeypatch: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    fake_document_provider: Any,
    opcion_pago: OpcionDocumental,
    capacidad_registrar_pago: Any,
) -> None:
    """Un reenvío ya persistido sólo reautoriza `gastos.registrar_pago`."""
    user, actor_completo = actor_factory(CAPS_PAGO_UI)
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    _registrar_pago_previo(
        actor_completo, solicitud, fake_document_provider(opciones=[opcion_pago])
    )
    actor_replay = Actor(
        subject_id=user.pk,
        capabilities=frozenset(("gastos.consultar_todas", "gastos.registrar_pago")),
    )
    monkeypatch.setattr("gastos.views.resolve_actor", lambda request: actor_replay)
    client, token = csrf_auth_client(user, actor_replay)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 302
    assert response.url == _url_detalle(solicitud)
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1


@pytest.mark.django_db
def test_post_sin_pago_previo_y_listado_con_error_conserva_503_sin_alta(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
) -> None:
    """Sin pago confirmado, el fallo del listado no habilita ningún alta nueva."""
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = fake_document_provider(
        error_listado=RuntimeError("listado sintético no disponible")
    )
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    client, token = csrf_auth_client(user, actor)

    response = client.post(
        _url_pagar(solicitud),
        {**_payload_pago(), "csrfmiddlewaretoken": token},
    )

    assert response.status_code == 503
    assert PagoExterno.objects.count() == 0
    assert EventoPagoExterno.objects.count() == 0


# --------------------------------------------------------------------------- #
# B1: ventana real A/B con C03 en otra conexión PostgreSQL
# --------------------------------------------------------------------------- #

_TIMEOUT_VENTANA = 15.0


class _ProveedorListadoEnVentana:
    """Doble documental que sincroniza la ventana de reenvío concurrente.

    La vista de B sólo invoca el listado después de comprobar ausencia de pago.
    El doble registra esa ausencia, libera al hilo de A y espera su commit con un
    timeout acotado antes de comprobar que el pago ya es visible para B. Recién
    entonces falla el listado o devuelve un catálogo sin la versión enviada.
    """

    def __init__(
        self,
        *,
        b_en_listado: Event,
        a_commit: Event,
        modo: str,
        opciones: list[OpcionDocumental],
        registro: dict[str, Any],
        timeout: float,
    ) -> None:
        self._b_en_listado = b_en_listado
        self._a_commit = a_commit
        self._modo = modo
        self._opciones = opciones
        self._registro = registro
        self._timeout = timeout
        self.llamadas_listado: list[dict[str, Any]] = []
        self.llamadas: list[dict[str, Any]] = []

    def listar_opciones_para_pago(
        self, *, actor: Any, gasto: Any, tipos_admitidos: Any = None
    ) -> list[OpcionDocumental]:
        self.llamadas_listado.append(
            {
                "actor_id": actor.subject_id,
                "gasto_id": gasto.pk,
                "tipos_admitidos": tuple(tipos_admitidos or ()),
            }
        )
        self._registro["b_ausencia_inicial"] = not PagoExterno.objects.filter(
            solicitud_id=gasto.pk
        ).exists()
        self._b_en_listado.set()
        self._registro["a_commit_visto_por_b"] = self._a_commit.wait(timeout=self._timeout)
        self._registro["pago_visible_para_b"] = PagoExterno.objects.filter(
            solicitud_id=gasto.pk
        ).exists()
        if self._modo == "falla":
            raise RuntimeError("listado documental sintético no disponible")
        return list(self._opciones)

    def verificar_y_bloquear_documento(self, **kwargs: Any) -> Any:
        self.llamadas.append(kwargs)
        raise AssertionError("Un reenvío no debe verificar ni bloquear el documento.")


def _ejecutar_ventana_reenvio(
    *,
    modo: str,
    payload: dict[str, str],
    solicitud: Any,
    actor: Any,
    user: Any,
    csrf_auth_client: Any,
    fake_document_provider: Any,
    monkeypatch: Any,
    settings: Any,
) -> tuple[Any, dict[str, Any], _ProveedorListadoEnVentana]:
    """Ejecuta A en otra conexión y B por HTTP real, detenida tras la consulta.

    A usa el servicio C03 real con su propio proveedor sintético. B recorre la
    vista con CSRF válido; su listado queda bloqueado hasta que A confirmó. El
    registro devuelto conserva la evidencia de ausencia inicial, del commit
    visible y de las decisiones reales alcanzadas por B.
    """
    registro: dict[str, Any] = {}
    b_en_listado = Event()
    a_commit = Event()
    proveedor_b = _ProveedorListadoEnVentana(
        b_en_listado=b_en_listado,
        a_commit=a_commit,
        modo=modo,
        opciones=[
            OpcionDocumental(
                referencia_documental="doc-opaco-9",
                tipo_documento="factura",
                etiqueta="Factura sintética posterior",
            )
        ],
        registro=registro,
        timeout=_TIMEOUT_VENTANA,
    )
    settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER = proveedor_b
    proveedor_a = fake_document_provider(
        opciones=[
            OpcionDocumental(
                referencia_documental="doc-opaco-1",
                tipo_documento="factura",
                etiqueta="Factura sintética 1",
            )
        ]
    )

    decisiones_helper: list[bool] = []
    helper_real = gastos_views._pago_externo_registrado

    def _helper_instrumentado(solicitud_consultada: Any) -> bool:
        resultado = helper_real(solicitud_consultada)
        decisiones_helper.append(resultado)
        return resultado

    monkeypatch.setattr("gastos.views._pago_externo_registrado", _helper_instrumentado)

    llamadas_c03: list[dict[str, Any]] = []
    servicio_real = gastos_views.registrar_pago_externo

    def _servicio_instrumentado(**kwargs: Any) -> Any:
        try:
            resultado = servicio_real(**kwargs)
        except Exception as exc:
            llamadas_c03.append(
                {
                    "resultado": "error",
                    "tipo": type(exc).__name__,
                    "sin_proveedor": kwargs.get("document_provider") is None,
                }
            )
            raise
        llamadas_c03.append(
            {
                "resultado": "ok",
                "pago_pk": resultado.pk,
                "sin_proveedor": kwargs.get("document_provider") is None,
            }
        )
        return resultado

    monkeypatch.setattr("gastos.views.registrar_pago_externo", _servicio_instrumentado)

    def _hilo_a() -> None:
        connections.close_all()
        try:
            if not b_en_listado.wait(timeout=_TIMEOUT_VENTANA):
                raise AssertionError("B no alcanzó el listado dentro del timeout.")
            registro["a_ausencia_inicial"] = not PagoExterno.objects.filter(
                solicitud_id=solicitud.pk
            ).exists()
            pago = registrar_pago_externo(
                actor=actor,
                solicitud_id=solicitud.pk,
                importe="825.40",
                fecha_pago="2026-10-14",
                referencia_externa="ref-sintetica-001",
                referencia_documental="doc-opaco-1",
                document_provider=proveedor_a,
            )
            registro["a_pago_pk"] = pago.pk
        except Exception as exc:
            registro["a_error"] = exc
        finally:
            a_commit.set()
            connections.close_all()

    hilo_a = Thread(target=_hilo_a, daemon=True)
    hilo_a.start()

    client, token = csrf_auth_client(user, actor)
    try:
        response = client.post(
            _url_pagar(solicitud),
            {**payload, "csrfmiddlewaretoken": token},
        )
    finally:
        # Red de seguridad para no dejar el hilo de A esperando ante un fallo de B.
        b_en_listado.set()
        a_commit.set()
        hilo_a.join(timeout=_TIMEOUT_VENTANA)

    assert not hilo_a.is_alive(), "El hilo de A quedó bloqueado."
    registro["decisiones_helper"] = decisiones_helper
    registro["llamadas_c03"] = llamadas_c03
    return response, registro, proveedor_b


def _asegurar_evidencia_ventana(
    registro: dict[str, Any], proveedor_b: _ProveedorListadoEnVentana
) -> None:
    """Comprueba la evidencia común exigida a la ventana concurrente."""
    assert "a_error" not in registro, registro.get("a_error")
    assert registro["a_ausencia_inicial"] is True
    assert registro["b_ausencia_inicial"] is True
    assert registro["a_commit_visto_por_b"] is True
    assert registro["pago_visible_para_b"] is True
    assert registro["decisiones_helper"] == [False, True]
    assert len(proveedor_b.llamadas_listado) == 1
    assert proveedor_b.llamadas == []


@pytest.mark.django_db(transaction=True)
def test_ventana_listado_falla_identico_redirige_al_pago_confirmado_por_a(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    response, registro, proveedor_b = _ejecutar_ventana_reenvio(
        modo="falla",
        payload=_payload_pago(),
        solicitud=solicitud,
        actor=actor,
        user=user,
        csrf_auth_client=csrf_auth_client,
        fake_document_provider=fake_document_provider,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    _asegurar_evidencia_ventana(registro, proveedor_b)
    assert registro["llamadas_c03"] == [
        {
            "resultado": "ok",
            "pago_pk": registro["a_pago_pk"],
            "sin_proveedor": True,
        }
    ]
    assert response.status_code == 302
    assert response.url == _url_detalle(solicitud)
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert PagoExterno.objects.get().pk == registro["a_pago_pk"]


@pytest.mark.django_db(transaction=True)
def test_ventana_listado_falla_distinto_retorna_409_sin_escrituras(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    response, registro, proveedor_b = _ejecutar_ventana_reenvio(
        modo="falla",
        payload={**_payload_pago(), "importe": "826.40"},
        solicitud=solicitud,
        actor=actor,
        user=user,
        csrf_auth_client=csrf_auth_client,
        fake_document_provider=fake_document_provider,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    _asegurar_evidencia_ventana(registro, proveedor_b)
    assert registro["llamadas_c03"] == [
        {
            "resultado": "error",
            "tipo": PaymentConflictError.__name__,
            "sin_proveedor": True,
        }
    ]
    assert response.status_code == 409
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert PagoExterno.objects.get().importe == Decimal("825.40")


@pytest.mark.django_db(transaction=True)
def test_ventana_version_ausente_identico_redirige_al_pago_confirmado_por_a(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    response, registro, proveedor_b = _ejecutar_ventana_reenvio(
        modo="sin_version",
        payload=_payload_pago(),
        solicitud=solicitud,
        actor=actor,
        user=user,
        csrf_auth_client=csrf_auth_client,
        fake_document_provider=fake_document_provider,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    _asegurar_evidencia_ventana(registro, proveedor_b)
    assert registro["llamadas_c03"] == [
        {
            "resultado": "ok",
            "pago_pk": registro["a_pago_pk"],
            "sin_proveedor": True,
        }
    ]
    assert response.status_code == 302
    assert response.url == _url_detalle(solicitud)
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert PagoExterno.objects.get().pk == registro["a_pago_pk"]


@pytest.mark.django_db(transaction=True)
def test_ventana_version_ausente_distinto_retorna_409_sin_escrituras(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    response, registro, proveedor_b = _ejecutar_ventana_reenvio(
        modo="sin_version",
        payload={**_payload_pago(), "importe": "826.40"},
        solicitud=solicitud,
        actor=actor,
        user=user,
        csrf_auth_client=csrf_auth_client,
        fake_document_provider=fake_document_provider,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    _asegurar_evidencia_ventana(registro, proveedor_b)
    assert registro["llamadas_c03"] == [
        {
            "resultado": "error",
            "tipo": PaymentConflictError.__name__,
            "sin_proveedor": True,
        }
    ]
    assert response.status_code == 409
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
    assert PagoExterno.objects.get().importe == Decimal("825.40")


@pytest.mark.django_db(transaction=True)
def test_ventana_payload_malformado_no_crea_ni_duplica_escrituras(
    actor_pago: Any,
    csrf_auth_client: Any,
    solicitud_factory: Any,
    settings: Any,
    fake_document_provider: Any,
    capacidad_registrar_pago: Any,
    monkeypatch: Any,
) -> None:
    """La existencia habilita C03, pero un payload inválido sigue siendo 400."""
    user, actor = actor_pago
    solicitud = solicitud_factory(estado=EstadoSolicitud.ACEPTADA, solicitante=user)
    response, registro, proveedor_b = _ejecutar_ventana_reenvio(
        modo="falla",
        payload={**_payload_pago(), "importe": "no-es-un-importe"},
        solicitud=solicitud,
        actor=actor,
        user=user,
        csrf_auth_client=csrf_auth_client,
        fake_document_provider=fake_document_provider,
        monkeypatch=monkeypatch,
        settings=settings,
    )

    _asegurar_evidencia_ventana(registro, proveedor_b)
    assert registro["llamadas_c03"] == [
        {
            "resultado": "error",
            "tipo": "PaymentInvalidInputError",
            "sin_proveedor": True,
        }
    ]
    assert response.status_code == 400
    assert response.context["error_pago"]
    assert PagoExterno.objects.count() == 1
    assert EventoPagoExterno.objects.count() == 1
