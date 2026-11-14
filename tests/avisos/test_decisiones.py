"""Pruebas focales de backend para avisos de decisiones de Gastos (SPEC-030)."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone

from avisos.correo import _construir_mensaje, procesar_intencion_correo
from avisos.models import Aviso, EstadoIntencionCorreo, IntencionCorreo, TipoAviso
from avisos.permisos import avisos_autorizados_queryset
from avisos.services import generar_aviso_decision_gasto
from comunes.models import Circuito, TramiteBase
from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto
from gastos.services import (
    ConcurrencyConflictError,
    ExpenseNotFoundError,
    ExpensePermissionDeniedError,
    InvalidDecisionInputError,
    decide_expense,
)
from identidad.models import CuentaLocal
from identidad.services import Actor, actor_para_usuario

User = get_user_model()


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


def _crear_solicitud_directa(solicitante, numero: int = 7001) -> SolicitudGasto:
    base = TramiteBase.objects.create(
        circuito=Circuito.GASTO,
        numero_publico=numero,
        solicitante_actor_id=str(solicitante.pk),
        centro_costo_codigo=None,
    )
    return SolicitudGasto.objects.create(
        pk=numero,
        tramite_base=base,
        concepto="Concepto confidencial sintético",
        monto_estimado=Decimal("1234.56"),
        unidad_requirente="Laboratorio sintético",
        solicitante=solicitante,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )


def _actor_de(user) -> Actor:
    return actor_para_usuario(
        user,
        group_names=list(user.groups.values_list("name", flat=True)),
    )


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
@pytest.mark.parametrize(
    ("accion", "motivo", "estado_esperado"),
    [
        ("aceptar", "", EstadoSolicitud.ACEPTADA),
        ("postergar", "Motivo confidencial de postergación", EstadoSolicitud.POSTERGADA),
        ("rechazar", "Motivo confidencial de rechazo", EstadoSolicitud.RECHAZADA),
    ],
)
def test_decide_expense_genera_aviso_y_correo_por_resultado(
    django_capture_on_commit_callbacks,
    accion,
    motivo,
    estado_esperado,
):
    solicitante = _crear_usuario(
        f"sol_{accion}",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    operadora = _crear_usuario(
        f"op_{accion}",
        grupos=["demo_operadora"],
        con_cuenta_local=False,
    )
    solicitud = _crear_solicitud_directa(solicitante, numero=7100 + len(accion))

    with django_capture_on_commit_callbacks(execute=True):
        decide_expense(
            actor=_actor_de(operadora),
            solicitud_id=solicitud.pk,
            action=accion,
            expected_version=0,
            motivo=motivo,
        )

    decision = DecisionGasto.objects.get(solicitud=solicitud)
    assert decision.estado_resultante == estado_esperado

    aviso = Aviso.objects.get(
        destinatario=solicitante,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        decision_id=decision.pk,
    )
    assert aviso.solicitud_id == solicitud.pk
    assert aviso.intencion_correo.estado == EstadoIntencionCorreo.ACEPTADO

    assert len(mail.outbox) == 1
    enviado = mail.outbox[0]
    assert enviado.to == [solicitante.email]
    assert enviado.subject == f"[PS_Cooperadora] Decisión sobre solicitud de gasto #{solicitud.pk}"
    assert decision.get_estado_resultante_display() in enviado.body
    assert f"http://127.0.0.1:8000/gastos/{solicitud.pk}/" in enviado.body
    assert "Concepto confidencial sintético" not in enviado.body
    assert "1234.56" not in enviado.body
    if motivo:
        assert motivo not in enviado.body


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_secuencia_postergar_y_aceptar_genera_dos_avisos_e_idempotencia_no_reinicia_leido(
    django_capture_on_commit_callbacks,
):
    solicitante = _crear_usuario(
        "sol_seq",
        grupos=["demo_solicitante"],
        con_cuenta_local=False,
    )
    operadora = _crear_usuario(
        "op_seq",
        grupos=["demo_operadora"],
        con_cuenta_local=False,
    )
    solicitud = _crear_solicitud_directa(solicitante, numero=7201)

    with django_capture_on_commit_callbacks(execute=True):
        decide_expense(
            actor=_actor_de(operadora),
            solicitud_id=solicitud.pk,
            action="postergar",
            expected_version=0,
            motivo="Falta documentación",
        )
    decision_1 = DecisionGasto.objects.get(solicitud=solicitud)

    with django_capture_on_commit_callbacks(execute=True):
        decide_expense(
            actor=_actor_de(operadora),
            solicitud_id=solicitud.pk,
            action="aceptar",
            expected_version=1,
            motivo="",
        )
    decision_2 = DecisionGasto.objects.filter(solicitud=solicitud).order_by("pk").last()
    assert decision_1.pk != decision_2.pk

    avisos = list(
        Aviso.objects.filter(
            destinatario=solicitante,
            tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
            solicitud_id=solicitud.pk,
        ).order_by("pk")
    )
    assert [a.decision_id for a in avisos] == [decision_1.pk, decision_2.pk]
    assert len(mail.outbox) == 2

    # La fuente de estado/fecha del correo es DecisionGasto, no el estado actual de solicitud
    msg_postergada = _construir_mensaje(
        solicitud=solicitud,
        enlace=f"http://127.0.0.1:8000/gastos/{solicitud.pk}/",
        remitente="noreply@sintetico.test",
        destinatario_email=solicitante.email,
        aviso=avisos[0],
        decision=decision_1,
    )
    assert "Postergada" in msg_postergada.body
    assert "Aceptada" not in msg_postergada.body

    # Idempotencia: repetir mismo evento no duplica aviso ni correo ni reinicia leida_en
    leida_ts = timezone.now() - timedelta(minutes=5)
    Aviso.objects.filter(pk=avisos[0].pk).update(leida_en=leida_ts)
    creados = generar_aviso_decision_gasto(decision_1.pk, preparar_correo=True)
    assert creados == 0
    avisos[0].refresh_from_db()
    assert avisos[0].leida_en == leida_ts
    assert IntencionCorreo.objects.filter(aviso=avisos[0]).count() == 1


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_rollback_conflictos_y_errores_no_notifican_y_fallo_aviso_no_revierte_decision(
    django_capture_on_commit_callbacks,
):
    solicitante = _crear_usuario("sol_err", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_err", grupos=["demo_operadora"])
    solicitud = _crear_solicitud_directa(solicitante, numero=7301)

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(ConcurrencyConflictError):
            decide_expense(
                actor=_actor_de(operadora),
                solicitud_id=solicitud.pk,
                action="aceptar",
                expected_version=99,
                motivo="",
            )
        with pytest.raises(InvalidDecisionInputError):
            decide_expense(
                actor=_actor_de(operadora),
                solicitud_id=solicitud.pk,
                action="rechazar",
                expected_version=0,
                motivo="   ",
            )
        with pytest.raises(ExpensePermissionDeniedError):
            decide_expense(
                actor=_actor_de(solicitante),
                solicitud_id=solicitud.pk,
                action="aceptar",
                expected_version=0,
                motivo="",
            )
        with pytest.raises(ExpenseNotFoundError):
            decide_expense(
                actor=_actor_de(operadora),
                solicitud_id=999999,
                action="aceptar",
                expected_version=0,
                motivo="",
            )
        try:
            with transaction.atomic():
                decide_expense(
                    actor=_actor_de(operadora),
                    solicitud_id=solicitud.pk,
                    action="aceptar",
                    expected_version=0,
                    motivo="",
                )
                raise RuntimeError("Rollback externo simulado")
        except RuntimeError:
            pass

    assert DecisionGasto.objects.count() == 0
    assert Aviso.objects.count() == 0
    assert IntencionCorreo.objects.count() == 0
    assert len(mail.outbox) == 0

    # Fallo post-commit en avisos no revierte la decisión confirmada
    with patch(
        "avisos.services.generar_aviso_decision_gasto",
        side_effect=RuntimeError("Fallo simulado en avisos"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            decide_expense(
                actor=_actor_de(operadora),
                solicitud_id=solicitud.pk,
                action="aceptar",
                expected_version=0,
                motivo="",
            )

    solicitud.refresh_from_db()
    assert solicitud.estado == EstadoSolicitud.ACEPTADA
    assert DecisionGasto.objects.filter(solicitud=solicitud).count() == 1
    assert Aviso.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_permisos_matriz_titular_revocado_desconocidos_y_regresion_nueva_solicitud():
    sol_local = _crear_usuario(
        "sol_mat_local",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
    )
    sol_pendiente = _crear_usuario(
        "sol_mat_pend",
        grupos=["local_solicitante"],
        con_cuenta_local=True,
        estado_local=CuentaLocal.Estado.PENDIENTE,
    )
    operadora = _crear_usuario("op_mat", grupos=["demo_operadora"])
    lector = _crear_usuario("lec_mat", grupos=["demo_lectura"])

    s_ok = _crear_solicitud_directa(sol_local, numero=7401)
    s_pend = _crear_solicitud_directa(sol_pendiente, numero=7402)

    d_ok = DecisionGasto.objects.create(
        solicitud=s_ok,
        autor=operadora,
        motivo="",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )
    d_pend = DecisionGasto.objects.create(
        solicitud=s_pend,
        autor=operadora,
        motivo="",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )

    assert generar_aviso_decision_gasto(d_pend.pk, preparar_correo=True) == 0
    assert generar_aviso_decision_gasto(d_ok.pk, preparar_correo=True) == 1

    # Aviso de nueva solicitud para operadora + aviso desconocido en BD
    aviso_nueva = Aviso.objects.create(
        destinatario=operadora,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=s_ok.pk,
    )
    Aviso.objects.create(
        destinatario=sol_local,
        tipo="tipo_desconocido_futuro",
        solicitud_id=s_ok.pk,
    )
    # Aviso de decisión con solicitud_id cruzado (inconsistente)
    Aviso.objects.create(
        destinatario=sol_local,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=s_ok.pk,
        decision_id=d_pend.pk,
    )

    qs_sol = list(avisos_autorizados_queryset(_actor_de(sol_local)))
    assert len(qs_sol) == 1
    assert qs_sol[0].tipo == TipoAviso.DECISION_SOLICITUD_GASTO
    assert qs_sol[0].decision_id == d_ok.pk

    qs_op = list(avisos_autorizados_queryset(_actor_de(operadora)))
    assert [a.pk for a in qs_op] == [aviso_nueva.pk]

    assert avisos_autorizados_queryset(_actor_de(lector)).count() == 0

    # Si se revoca el acceso del titular antes del envío, el correo queda OMITIDO
    sol_local.groups.clear()
    intencion = IntencionCorreo.objects.get(aviso__decision_id=d_ok.pk)
    resultado = procesar_intencion_correo(intencion.pk)
    assert resultado.estado == EstadoIntencionCorreo.OMITIDO
    assert resultado.codigo == "sin_permisos"
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_constraints_y_comandos_cli_recuperacion_y_correo():
    solicitante = _crear_usuario("sol_cli", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_cli", grupos=["demo_operadora"])
    solicitud = _crear_solicitud_directa(solicitante, numero=7501)
    decision = DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=operadora,
        motivo="",
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )

    # Constraints de coherencia tipo / decision_id
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Aviso.objects.create(
                destinatario=operadora,
                tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
                solicitud_id=solicitud.pk,
                decision_id=decision.pk,
            )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Aviso.objects.create(
                destinatario=solicitante,
                tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
                solicitud_id=solicitud.pk,
                decision_id=None,
            )

    # Recuperación web por decision_id: crea aviso sin IntencionCorreo ni SMTP
    out_rec = StringIO()
    call_command("reintentar_aviso_decision_gasto", str(decision.pk), stdout=out_rec)
    assert "1 nuevos" in out_rec.getvalue()
    aviso_dec = Aviso.objects.get(
        destinatario=solicitante,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        decision_id=decision.pk,
    )
    assert IntencionCorreo.objects.count() == 0
    assert len(mail.outbox) == 0

    with pytest.raises(CommandError):
        call_command("reintentar_aviso_decision_gasto", "999999")

    # Comando correo_aviso_gasto distingue tipos en consulta y no reenvía aceptados/inciertos
    aviso_nueva = Aviso.objects.create(
        destinatario=operadora,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    int_aceptada = IntencionCorreo.objects.create(
        aviso=aviso_nueva,
        estado=EstadoIntencionCorreo.ACEPTADO,
    )
    int_fallida = IntencionCorreo.objects.create(
        aviso=aviso_dec,
        estado=EstadoIntencionCorreo.FALLIDO,
    )

    out_consulta = StringIO()
    call_command("correo_aviso_gasto", str(solicitud.pk), stdout=out_consulta)
    texto_consulta = out_consulta.getvalue()
    assert f"tipo={TipoAviso.NUEVA_SOLICITUD_GASTO}" in texto_consulta
    assert f"tipo={TipoAviso.DECISION_SOLICITUD_GASTO}" in texto_consulta

    out_reintento = StringIO()
    call_command(
        "correo_aviso_gasto",
        str(solicitud.pk),
        "--reintentar",
        stdout=out_reintento,
    )
    int_aceptada.refresh_from_db()
    int_fallida.refresh_from_db()
    assert int_aceptada.estado == EstadoIntencionCorreo.ACEPTADO
    assert int_aceptada.intentos == 0
    assert int_fallida.estado == EstadoIntencionCorreo.ACEPTADO
    assert len(mail.outbox) == 1
