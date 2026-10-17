"""Fixtures y configuración de pruebas para el módulo de gastos."""

import secrets
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.middleware.csrf import _get_new_csrf_string, _mask_cipher_secret
from django.test import Client

from gastos.contracts import DocumentoVerificado, OpcionDocumental
from gastos.models import EstadoSolicitud, SolicitudGasto
from identidad.services import GROUP_CAPABILITIES, Actor
from tests.soporte_gastos import crear_gasto_sintetico

User = get_user_model()


@pytest.fixture(autouse=True)
def enable_demo_identity(settings: Any) -> None:
    """Habilita la identidad de demo por defecto para las pruebas de gastos."""
    settings.DEMO_IDENTITY_ENABLED = True


@pytest.fixture
def demo_groups(db: Any) -> dict[str, Group]:
    """Crea los grupos de identidad de demo."""
    return {
        name: Group.objects.get_or_create(name=name)[0]
        for name in ("demo_solicitante", "demo_operadora", "demo_lectura")
    }


@pytest.fixture
def demo_accounts(db: Any, demo_groups: dict[str, Group]) -> tuple[dict[str, Any], str]:
    """Crea las cuentas sintéticas A, B, O y L asociadas a sus respectivos grupos."""
    password = secrets.token_urlsafe(24)
    accounts = {}
    for username, group_name in {
        "demo_a": "demo_solicitante",
        "demo_b": "demo_solicitante",
        "demo_o": "demo_operadora",
        "demo_l": "demo_lectura",
    }.items():
        user = User.objects.create_user(username=username, password=password)
        user.groups.add(demo_groups[group_name])
        accounts[username] = user
    return accounts, password


def issue_csrf_credentials(client: Client) -> str:
    """Configura una cookie CSRF válida en el test client y retorna el token correspondiente."""
    secret = _get_new_csrf_string()
    client.cookies["csrftoken"] = secret
    return _mask_cipher_secret(secret)


@pytest.fixture
def create_actor(demo_groups: dict[str, Group]) -> Callable[[str, list[str]], tuple[Any, Actor]]:
    """Crea un usuario real asignado al grupo correspondiente según las capacidades requeridas."""

    def _factory(username: str, capabilities: list[str]) -> tuple[Any, Actor]:
        user, _ = User.objects.get_or_create(username=username)
        caps_set = frozenset(capabilities)
        if "gastos.presentar" in caps_set:
            user.groups.add(demo_groups["demo_solicitante"])
        elif "gastos.decidir" in caps_set:
            user.groups.add(demo_groups["demo_operadora"])
        elif "gastos.consultar_todas" in caps_set:
            user.groups.add(demo_groups["demo_lectura"])
        else:
            user.groups.clear()

        group_names = user.groups.values_list("name", flat=True)
        real_caps = frozenset().union(
            *(GROUP_CAPABILITIES[name] for name in group_names if name in GROUP_CAPABILITIES)
        )
        actor = Actor(subject_id=user.pk, capabilities=real_caps)
        return user, actor

    return _factory


@pytest.fixture
def auth_client() -> Callable[[Any, Any], Client]:
    """Crea un test client estándar con el usuario autenticado vía sesión real."""

    def _factory(user: Any, actor: Any = None) -> Client:
        client = Client()
        client.force_login(user)
        return client

    return _factory


@pytest.fixture
def csrf_auth_client() -> Callable[[Any, Any], tuple[Client, str]]:
    """Crea un test client con enforce_csrf_checks=True, sesión iniciada y token CSRF válido."""

    def _factory(user: Any, actor: Any = None) -> tuple[Client, str]:
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        token = issue_csrf_credentials(client)
        return client, token

    return _factory


class FakeDocumentVerificationPort:
    """Doble de prueba local del puerto documental (nunca fuera de tests).

    Registra cada invocación, comprueba que se ejecuta dentro de la transacción
    atómica del servicio y devuelve una evidencia `DocumentoVerificado` coherente
    por defecto o el resultado/error explícito recibido. También implementa el
    listado provisional de opciones para el selector del formulario.
    """

    def __init__(
        self,
        *,
        resultado: DocumentoVerificado | None = None,
        error: Exception | None = None,
        tipo_documento: str = "factura",
        opciones: Any = None,
        error_listado: Exception | None = None,
    ) -> None:
        self.resultado = resultado
        self.error = error
        self.tipo_documento = tipo_documento
        self.opciones = list(opciones) if opciones is not None else []
        self.error_listado = error_listado
        self.llamadas: list[dict[str, Any]] = []
        self.llamadas_listado: list[dict[str, Any]] = []
        self.llamado_en_atomic: bool | None = None

    def verificar_y_bloquear_documento(
        self,
        *,
        actor: Any,
        gasto: SolicitudGasto,
        referencia_documental: str,
        tipos_admitidos: Any = ("factura", "presupuesto", "proforma"),
    ) -> DocumentoVerificado:
        from django.db import transaction

        self.llamado_en_atomic = transaction.get_connection().in_atomic_block
        self.llamadas.append(
            {
                "actor_id": actor.subject_id,
                "gasto_id": gasto.pk,
                "referencia_documental": referencia_documental,
                "tipos_admitidos": tuple(tipos_admitidos),
            }
        )
        if self.error is not None:
            raise self.error
        if self.resultado is not None:
            return self.resultado
        return DocumentoVerificado(
            solicitud_id=gasto.pk,
            referencia_documental=referencia_documental,
            tipo_documento=self.tipo_documento,
        )

    def listar_opciones_para_pago(
        self,
        *,
        actor: Any,
        gasto: SolicitudGasto,
        tipos_admitidos: Any = ("factura", "presupuesto", "proforma"),
    ) -> list[OpcionDocumental]:
        self.llamadas_listado.append(
            {
                "actor_id": actor.subject_id,
                "gasto_id": gasto.pk,
                "tipos_admitidos": tuple(tipos_admitidos),
            }
        )
        if self.error_listado is not None:
            raise self.error_listado
        return list(self.opciones)


@pytest.fixture
def fake_document_provider() -> Callable[..., FakeDocumentVerificationPort]:
    """Fábrica del doble de prueba del puerto documental."""

    def _factory(**kwargs: Any) -> FakeDocumentVerificationPort:
        return FakeDocumentVerificationPort(**kwargs)

    return _factory


@pytest.fixture
def solicitud_factory(db: Any) -> Callable[..., SolicitudGasto]:
    """Crea solicitudes sintéticas con solicitante propio y estado configurable."""

    def _factory(
        *,
        estado: str = EstadoSolicitud.ACEPTADA,
        solicitante: Any = None,
        monto: str = "1000.00",
    ) -> SolicitudGasto:
        if solicitante is None:
            solicitante = User.objects.create_user(username=f"sol_{secrets.token_hex(4)}")
        return crear_gasto_sintetico(
            concepto="Gasto sintético para pago externo",
            monto_estimado=Decimal(monto),
            unidad_requirente="Unidad sintética",
            solicitante=solicitante,
            estado=estado,
        )

    return _factory


@pytest.fixture
def actor_factory(db: Any) -> Callable[..., tuple[Any, Actor]]:
    """Crea usuarios reales y su Actor con el conjunto exacto de capacidades indicado."""

    def _factory(capabilities: Any = ()) -> tuple[Any, Actor]:
        user = User.objects.create_user(username=f"actor_{secrets.token_hex(4)}")
        actor = Actor(subject_id=user.pk, capabilities=frozenset(capabilities))
        return user, actor

    return _factory


@pytest.fixture
def capacidad_registrar_pago(monkeypatch: Any) -> None:
    """Simula las capacidades del circuito de pago sin alterar el módulo identidad.

    La extensión de identidad (#21/#28) aún no conoce los códigos
    `gastos.registrar_pago` ni `documentos.ver_metadatos`; tanto el servicio de
    pagos como las vistas los verifican y aquí se sustituyen por la comprobación
    directa sobre el Actor. Se parchean ambos módulos para que la vista y el
    servicio compartan el mismo doble.
    """

    def _tiene_capacidad(actor: Any, code: str) -> bool:
        return code in getattr(actor, "capabilities", frozenset())

    monkeypatch.setattr("gastos.payments.has_capability", _tiene_capacidad)
    monkeypatch.setattr("gastos.views.has_capability", _tiene_capacidad)
