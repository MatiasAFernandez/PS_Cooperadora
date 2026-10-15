"""Formulario consumidor de pago externo (Issue #15, corte C03 + UI).

Cubre el orden de comprobaciones de la vista, el selector documental cargado
sólo desde servidor, la revalidación transaccional, el bypass idempotente sin
proveedor y el mapeo de errores. No usa identidad ni proveedor reales: sólo
actores y dobles sintéticos de prueba.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from gastos.contracts import DocumentVerificationError, OpcionDocumental
from gastos.models import EstadoSolicitud, EventoPagoExterno, PagoExterno
from gastos.payments import PaymentInvalidExpenseStateError, registrar_pago_externo

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
