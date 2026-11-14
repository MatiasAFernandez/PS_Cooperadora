"""Pruebas focales de backend para avisos de pago externo registrado (SPEC-031)."""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection
from django.test import override_settings
from django.utils import timezone

from avisos.correo import procesar_intencion_correo
from avisos.models import Aviso, EstadoIntencionCorreo, IntencionCorreo, TipoAviso
from avisos.permisos import avisos_autorizados_queryset, evaluar_autorizacion_aviso
from avisos.services import generar_aviso_pago_externo
from gastos.contracts import DocumentoVerificado
from gastos.models import (
    DecisionGasto,
    EstadoSolicitud,
    EventoPagoExterno,
    PagoExterno,
    PagoExternoOriginal,
)
from gastos.payments import (
    PaymentConflictError,
    PaymentPermissionDeniedError,
    incorporar_constancia_atp_posterior,
    rectificar_pago_externo,
    registrar_pago_externo,
)
from identidad.models import CuentaLocal
from identidad.services import Actor, actor_para_usuario
from tests.soporte_gastos import crear_gasto_sintetico
from tests.soporte_pagos import pdf_comprobante, pdf_constancia

pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()

CAPS_PAGO = frozenset(
    {
        "gastos.registrar_pago",
        "gastos.consultar_todas",
        "documentos.incorporar",
        "documentos.ver_metadatos",
    }
)


class _FakeDocumentProvider:
    def verificar_y_bloquear_documento(
        self,
        *,
        actor: Actor,
        gasto,
        referencia_documental: str,
        tipos_admitidos,
    ) -> DocumentoVerificado:
        tipo = next(iter(tipos_admitidos))
        return DocumentoVerificado(
            solicitud_id=gasto.pk,
            referencia_documental=referencia_documental,
            tipo_documento=tipo,
        )


@pytest.fixture(autouse=True)
def _storage_y_capacidades(settings, tmp_path, monkeypatch):
    settings.DOCUMENT_STORAGE_ROOT = tmp_path / "documentos_privados"
    settings.DEMO_IDENTITY_ENABLED = True
    settings.LOCAL_IDENTITY_ENABLED = True

    def _tiene_capacidad(actor: Actor, code: str) -> bool:
        return code in getattr(actor, "capabilities", frozenset())

    monkeypatch.setattr("gastos.payments.has_capability", _tiene_capacidad)


def _crear_usuario(
    username: str,
    *,
    grupos: list[str] | None = None,
    is_active: bool = True,
    con_cuenta_local: bool = False,
    estado_local: str = CuentaLocal.Estado.APROBADA,
    email_verificado: bool = True,
):
    correo = f"{username}@sintetico.test"
    user = User.objects.create_user(
        username=username,
        email=correo,
        password="clave-sintetica-no-productiva",
        is_active=is_active,
    )
    for nombre_grupo in grupos or []:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)
    if con_cuenta_local:
        CuentaLocal.objects.create(
            user=user,
            email=correo,
            nombre_completo=f"Usuario {username}",
            estado=estado_local,
            email_verificado_en=timezone.now() if email_verificado else None,
        )
    return user


def _actor_de(user) -> Actor:
    return actor_para_usuario(
        user,
        group_names=list(user.groups.values_list("name", flat=True)),
    )


def _crear_solicitud(solicitante, *, estado: str = EstadoSolicitud.ACEPTADA):
    return crear_gasto_sintetico(
        concepto="Concepto confidencial sintético",
        monto_estimado=Decimal("1000.00"),
        unidad_requirente="Unidad sintética",
        solicitante=solicitante,
        estado=estado,
    )


def _payload_alta(**overrides):
    base = {
        "monto_bruto": Decimal("1000.00"),
        "monto_retencion_atp": Decimal("0.00"),
        "fecha_pago": date(2026, 3, 10),
        "referencia_externa": "TRF-CONFIDENCIAL-1",
        "referencia_documental": "doc-version-1",
        "comprobante_bancario": pdf_comprobante(),
    }
    base.update(overrides)
    return base


def _manifiestos_inciertos(storage_root: Path) -> list[Path]:
    carpeta = storage_root / ".operaciones"
    if not carpeta.exists():
        return []
    return [p for p in carpeta.glob("*.json") if "incierta" in p.read_text(encoding="utf-8")]


# --------------------------------------------------------------------------- #
# Commit real, aislamiento poscommit e idempotencia
# --------------------------------------------------------------------------- #


@override_settings(
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_alta_pago_genera_aviso_y_envia_correo_fuera_de_atomic(settings) -> None:
    titular = _crear_usuario(
        "titular_ok",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    operadora = _crear_usuario("operadora_ok", grupos=["demo_operadora"])
    actor_op = Actor(subject_id=operadora.pk, capabilities=CAPS_PAGO)
    solicitud = _crear_solicitud(titular)

    estados_atomic_smtp: list[bool] = []
    from django.core.mail.backends.locmem import EmailBackend

    original_send = EmailBackend.send_messages

    def _spy_send(self, email_messages):
        estados_atomic_smtp.append(connection.in_atomic_block)
        pago_guardado = PagoExterno.objects.get(solicitud_id=solicitud.pk)
        assert EventoPagoExterno.objects.filter(pago=pago_guardado).exists()
        assert PagoExternoOriginal.objects.filter(pago=pago_guardado).exists()
        assert (
            Path(settings.DOCUMENT_STORAGE_ROOT) / pago_guardado.comprobante_bancario.archivo
        ).is_file()
        return original_send(self, email_messages)

    with patch.object(EmailBackend, "send_messages", _spy_send):
        pago = registrar_pago_externo(
            actor=actor_op,
            solicitud_id=solicitud.pk,
            document_provider=_FakeDocumentProvider(),
            **_payload_alta(),
        )

    assert PagoExterno.objects.filter(pk=pago.pk).exists()
    evento = EventoPagoExterno.objects.get(pago=pago)
    assert PagoExternoOriginal.objects.filter(pago=pago).exists()
    assert estados_atomic_smtp == [False]

    aviso = Aviso.objects.get(
        destinatario=titular,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        evento_pago_id=evento.pk,
    )
    assert aviso.solicitud_id == solicitud.pk
    assert aviso.decision_id is None
    assert aviso.intencion_correo.estado == EstadoIntencionCorreo.ACEPTADO

    assert len(mail.outbox) == 1
    enviado = mail.outbox[0]
    assert enviado.to == [titular.email]
    assert enviado.subject == (
        f"[PS_Cooperadora] Registro de pago externo de solicitud de gasto #{solicitud.pk}"
    )
    assert "TRF-CONFIDENCIAL-1" not in enviado.body
    assert "1000" not in enviado.body
    assert "Concepto confidencial" not in enviado.body
    assert _manifiestos_inciertos(settings.DOCUMENT_STORAGE_ROOT) == []


@override_settings(
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
@pytest.mark.parametrize(
    "target",
    [
        "avisos.services.generar_aviso_pago_externo",
        "avisos.correo.enviar_correos_pago_externo",
    ],
)
def test_fallo_callback_poscommit_no_revierte_pago_ni_marca_manifiesto_incierto(
    settings, monkeypatch, target
) -> None:
    titular = _crear_usuario(
        "titular_fallo_cb",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    operadora = _crear_usuario("operadora_fallo_cb", grupos=["demo_operadora"])
    actor_op = Actor(subject_id=operadora.pk, capabilities=CAPS_PAGO)
    solicitud = _crear_solicitud(titular)

    def _boom(*args, **kwargs):
        raise RuntimeError("Fallo simulado en callback poscommit")

    monkeypatch.setattr(target, _boom)

    pago = registrar_pago_externo(
        actor=actor_op,
        solicitud_id=solicitud.pk,
        document_provider=_FakeDocumentProvider(),
        **_payload_alta(),
    )

    assert PagoExterno.objects.filter(pk=pago.pk).exists()
    assert EventoPagoExterno.objects.filter(pago=pago).exists()
    assert PagoExternoOriginal.objects.filter(pago=pago).exists()
    assert pago.comprobante_bancario_id is not None
    assert (
        Path(settings.DOCUMENT_STORAGE_ROOT) / pago.comprobante_bancario.archivo
    ).is_file()
    assert _manifiestos_inciertos(settings.DOCUMENT_STORAGE_ROOT) == []


@override_settings(
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_replay_identico_no_duplica_y_rectificacion_y_atp_no_avisan() -> None:
    titular = _crear_usuario(
        "titular_replay",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    operadora = _crear_usuario("operadora_replay", grupos=["demo_operadora"])
    actor_op = Actor(subject_id=operadora.pk, capabilities=CAPS_PAGO)
    solicitud = _crear_solicitud(titular)

    pago = registrar_pago_externo(
        actor=actor_op,
        solicitud_id=solicitud.pk,
        document_provider=_FakeDocumentProvider(),
        **_payload_alta(
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("100.00"),
            incorporar_atp_despues=True,
        ),
    )
    assert Aviso.objects.filter(tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO).count() == 1
    assert IntencionCorreo.objects.count() == 1

    # Replay idéntico antes de rectificar
    pago_replay = registrar_pago_externo(
        actor=actor_op,
        solicitud_id=solicitud.pk,
        document_provider=_FakeDocumentProvider(),
        **_payload_alta(
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("100.00"),
            comprobante_bancario=None,
        ),
    )
    assert pago_replay.pk == pago.pk
    assert Aviso.objects.filter(tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO).count() == 1

    # Incorporación de constancia ATP posterior no genera nuevo aviso
    incorporar_constancia_atp_posterior(
        actor=actor_op,
        solicitud_id=solicitud.pk,
        version_esperada=pago.version,
        constancia_atp=pdf_constancia(),
        motivo="Constancia ATP posterior sintética",
    )
    assert Aviso.objects.filter(tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO).count() == 1

    # Rectificación posterior no genera nuevo aviso
    pago.refresh_from_db()
    rectificar_pago_externo(
        actor=actor_op,
        solicitud_id=solicitud.pk,
        version_esperada=pago.version,
        motivo="Corrección de fecha sintética",
        fecha_pago=date(2026, 3, 12),
        monto_bruto=Decimal("1000.00"),
        monto_retencion_atp=Decimal("100.00"),
    )
    assert Aviso.objects.filter(tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO).count() == 1

    # Replay idéntico al alta ORIGINAL tras rectificar tampoco avisa ni duplica
    pago_replay_post = registrar_pago_externo(
        actor=actor_op,
        solicitud_id=solicitud.pk,
        document_provider=_FakeDocumentProvider(),
        **_payload_alta(
            monto_bruto=Decimal("1000.00"),
            monto_retencion_atp=Decimal("100.00"),
            comprobante_bancario=None,
        ),
    )
    assert pago_replay_post.pk == pago.pk
    assert Aviso.objects.filter(tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO).count() == 1
    assert IntencionCorreo.objects.count() == 1


@override_settings(
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_conflicto_denegacion_y_fallo_storage_o_sql_no_avisan(monkeypatch) -> None:
    titular = _crear_usuario(
        "titular_err",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    operadora = _crear_usuario("operadora_err", grupos=["demo_operadora"])
    actor_op = Actor(subject_id=operadora.pk, capabilities=CAPS_PAGO)
    actor_sin_permiso = Actor(
        subject_id=operadora.pk, capabilities=frozenset({"gastos.consultar_todas"})
    )

    solicitud_denegada = _crear_solicitud(titular)
    with pytest.raises(PaymentPermissionDeniedError):
        registrar_pago_externo(
            actor=actor_sin_permiso,
            solicitud_id=solicitud_denegada.pk,
            document_provider=_FakeDocumentProvider(),
            **_payload_alta(),
        )
    assert Aviso.objects.count() == 0

    # Fallo al crear PagoExternoOriginal (rollback SQL + compensación)
    def _fallo_original(*args, **kwargs):
        raise RuntimeError("Fallo SQL simulado")

    monkeypatch.setattr(PagoExternoOriginal.objects, "create", _fallo_original)
    with pytest.raises(RuntimeError, match="Fallo SQL simulado"):
        registrar_pago_externo(
            actor=actor_op,
            solicitud_id=solicitud_denegada.pk,
            document_provider=_FakeDocumentProvider(),
            **_payload_alta(),
        )
    monkeypatch.undo()
    assert Aviso.objects.count() == 0
    assert IntencionCorreo.objects.count() == 0

    # Alta válida y luego conflicto
    registrar_pago_externo(
        actor=actor_op,
        solicitud_id=solicitud_denegada.pk,
        document_provider=_FakeDocumentProvider(),
        **_payload_alta(),
    )
    assert Aviso.objects.count() == 1
    with pytest.raises(PaymentConflictError):
        registrar_pago_externo(
            actor=actor_op,
            solicitud_id=solicitud_denegada.pk,
            document_provider=_FakeDocumentProvider(),
            **_payload_alta(referencia_externa="OTRA-REF"),
        )
    assert Aviso.objects.count() == 1


# --------------------------------------------------------------------------- #
# Permisos, fail-closed, canal apagado, CLI y recuperación web
# --------------------------------------------------------------------------- #


@override_settings(AVISOS_EMAIL_ENABLED=False)
def test_titular_consultar_propias_registrador_igual_titular_y_lectura_ajena() -> None:
    titular = _crear_usuario(
        "titular_propio",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    lectura = _crear_usuario("lectura_global", grupos=["demo_lectura"])
    solicitud = _crear_solicitud(titular)

    # Titular también actúa como registrador del pago
    actor_registrador = Actor(
        subject_id=titular.pk,
        capabilities=CAPS_PAGO | {"gastos.consultar_propias"},
    )
    pago = registrar_pago_externo(
        actor=actor_registrador,
        solicitud_id=solicitud.pk,
        document_provider=_FakeDocumentProvider(),
        **_payload_alta(),
    )
    evento = EventoPagoExterno.objects.get(pago=pago)

    # Canal apagado: crea aviso web pero no crea intención de correo
    aviso = Aviso.objects.get(
        destinatario=titular,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        evento_pago_id=evento.pk,
    )
    assert IntencionCorreo.objects.count() == 0

    # Titular con gastos.consultar_propias ve su aviso; lectura global ajena no
    assert list(avisos_autorizados_queryset(_actor_de(titular))) == [aviso]
    assert list(avisos_autorizados_queryset(_actor_de(lectura))) == []


def test_fail_closed_permisos_perdidos_inactivo_ids_cruzados_y_unknown() -> None:
    titular = _crear_usuario(
        "titular_fc",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    otro = _crear_usuario(
        "otro_fc",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    operadora = _crear_usuario("operadora_fc", grupos=["demo_operadora"])
    actor_op = Actor(subject_id=operadora.pk, capabilities=CAPS_PAGO)

    sol1 = _crear_solicitud(titular)
    sol2 = _crear_solicitud(otro)

    with override_settings(AVISOS_EMAIL_ENABLED=False):
        pago1 = registrar_pago_externo(
            actor=actor_op,
            solicitud_id=sol1.pk,
            document_provider=_FakeDocumentProvider(),
            **_payload_alta(),
        )
        pago2 = registrar_pago_externo(
            actor=actor_op,
            solicitud_id=sol2.pk,
            document_provider=_FakeDocumentProvider(),
            **_payload_alta(referencia_externa="TRF-2"),
        )

    ev1 = EventoPagoExterno.objects.get(pago=pago1)
    ev2 = EventoPagoExterno.objects.get(pago=pago2)

    # Evento de otra solicitud -> fail-closed
    ok, codigo = evaluar_autorizacion_aviso(
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        actor=_actor_de(titular),
        destinatario_id=titular.pk,
        solicitud=sol1,
        evento_pago=ev2,
    )
    assert not ok
    assert codigo == "evento_pago_inconsistente"

    # Tipo desconocido -> fail-closed
    ok_unk, cod_unk = evaluar_autorizacion_aviso(
        tipo="tipo_inexistente_futuro",
        actor=_actor_de(titular),
        destinatario_id=titular.pk,
        solicitud=sol1,
        evento_pago=ev1,
    )
    assert not ok_unk
    assert cod_unk == "tipo_desconocido"

    # Usuario inactivo -> omitido al procesar correo y excluido del queryset
    aviso1 = Aviso.objects.get(evento_pago_id=ev1.pk)
    intencion = IntencionCorreo.objects.create(
        aviso=aviso1,
        estado=EstadoIntencionCorreo.PENDIENTE,
    )
    titular.is_active = False
    titular.save(update_fields=["is_active"])
    assert list(avisos_autorizados_queryset(_actor_de(titular))) == []

    with override_settings(
        AVISOS_EMAIL_ENABLED=True,
        AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    ):
        res = procesar_intencion_correo(intencion.pk)
    assert res.estado == EstadoIntencionCorreo.OMITIDO


@override_settings(
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_retry_smtp_cli_comun_tres_tipos_y_recuperacion_web_sin_smtp() -> None:
    titular = _crear_usuario(
        "titular_cli",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    operadora = _crear_usuario("operadora_cli", grupos=["demo_operadora"])
    actor_op = Actor(subject_id=operadora.pk, capabilities=CAPS_PAGO)
    solicitud = _crear_solicitud(titular)

    # Deshabilitar correo durante el registro para probar recuperación web sin SMTP
    with override_settings(AVISOS_EMAIL_ENABLED=False):
        pago = registrar_pago_externo(
            actor=actor_op,
            solicitud_id=solicitud.pk,
            document_provider=_FakeDocumentProvider(),
            **_payload_alta(),
        )
    evento = EventoPagoExterno.objects.get(pago=pago)
    aviso = Aviso.objects.get(evento_pago_id=evento.pk)

    # Conservar leida_en ante reintento idempotente
    marca = timezone.now() - timedelta(hours=1)
    aviso.leida_en = marca
    aviso.save(update_fields=["leida_en"])
    assert generar_aviso_pago_externo(evento.pk, preparar_correo=True) == 0
    aviso.refresh_from_db()
    assert aviso.leida_en == marca

    # Eliminar aviso y recuperar con comando web sin crear intención ni enviar SMTP
    aviso.delete()
    out_web = StringIO()
    call_command("reintentar_aviso_pago_externo", str(evento.pk), stdout=out_web)
    assert "1 nuevos" in out_web.getvalue()
    aviso_rec = Aviso.objects.get(evento_pago_id=evento.pk)
    assert IntencionCorreo.objects.count() == 0
    assert len(mail.outbox) == 0

    # Crear intenciones para los 3 tipos y verificar consulta + reintento CLI común
    decision = DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=operadora,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
        motivo="",
    )
    aviso_nueva = Aviso.objects.create(
        destinatario=operadora,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    aviso_dec = Aviso.objects.create(
        destinatario=titular,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
        decision_id=decision.pk,
    )
    IntencionCorreo.objects.create(aviso=aviso_nueva, estado=EstadoIntencionCorreo.FALLIDO)
    IntencionCorreo.objects.create(aviso=aviso_dec, estado=EstadoIntencionCorreo.FALLIDO)
    IntencionCorreo.objects.create(aviso=aviso_rec, estado=EstadoIntencionCorreo.FALLIDO)

    out_consulta = StringIO()
    call_command("correo_aviso_gasto", str(solicitud.pk), stdout=out_consulta)
    texto_consulta = out_consulta.getvalue()
    assert f"evento_pago={evento.pk}" in texto_consulta
    assert f"decision={decision.pk}" in texto_consulta

    out_reintento = StringIO()
    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar", stdout=out_reintento)
    assert "3 procesados" in out_reintento.getvalue()
    assert (
        IntencionCorreo.objects.get(aviso=aviso_rec).estado
        == EstadoIntencionCorreo.ACEPTADO
    )
    assert len(mail.outbox) >= 1

    with pytest.raises(CommandError):
        call_command("reintentar_aviso_pago_externo", "0")


def test_constraints_aviso_coherencia_y_unicidad() -> None:
    titular = _crear_usuario("titular_const", grupos=["local_solicitante"])

    with pytest.raises(IntegrityError):
        Aviso.objects.create(
            destinatario=titular,
            tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
            solicitud_id=1,
            decision_id=10,
            evento_pago_id=20,
        )

    Aviso.objects.create(
        destinatario=titular,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=1,
        evento_pago_id=20,
    )
    with pytest.raises(IntegrityError):
        Aviso.objects.create(
            destinatario=titular,
            tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
            solicitud_id=1,
            evento_pago_id=20,
        )
