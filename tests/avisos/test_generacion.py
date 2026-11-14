"""Pruebas de generación, idempotencia, transaccionalidad y reintento de avisos."""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from avisos.models import Aviso, TipoAviso
from avisos.services import generar_aviso_nueva_solicitud
from comunes.models import Circuito, TramiteBase
from gastos.models import EstadoSolicitud, SolicitudGasto
from gastos.services import crear_solicitud_gasto
from identidad.models import CuentaLocal
from identidad.services import Actor

User = get_user_model()


def _crear_usuario(
    username: str,
    *,
    grupos: list[str] | None = None,
    is_active: bool = True,
    is_staff: bool = False,
    is_superuser: bool = False,
    con_cuenta_local: bool = False,
    estado_local: str = CuentaLocal.Estado.APROBADA,
    email_verificado: bool = True,
):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@sintetico.test",
        password="clave-sintetica-no-productiva",
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    for nombre_grupo in grupos or []:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)
    if con_cuenta_local:
        CuentaLocal.objects.create(
            user=user,
            email=f"{username}@sintetico.test",
            nombre_completo=f"Usuario {username}",
            estado=estado_local,
            email_verificado_en=timezone.now() if email_verificado else None,
        )
    return user


def _crear_solicitud_directa(solicitante, numero: int = 1001) -> SolicitudGasto:
    base = TramiteBase.objects.create(
        circuito=Circuito.GASTO,
        numero_publico=numero,
        solicitante_actor_id=str(solicitante.pk),
        centro_costo_codigo=None,
    )
    return SolicitudGasto.objects.create(
        pk=numero,
        tramite_base=base,
        concepto="Insumo sintético",
        monto_estimado=Decimal("150.00"),
        unidad_requirente="Laboratorio sintético",
        solicitante=solicitante,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_destinatarios_locales_demo_y_exclusiones():
    autor = _crear_usuario(
        "autor_op",
        grupos=["demo_operadora", "demo_solicitante"],
        con_cuenta_local=True,
    )
    op_local_valido = _crear_usuario(
        "op_local_ok",
        grupos=["demo_operadora"],
        con_cuenta_local=True,
        estado_local=CuentaLocal.Estado.APROBADA,
        email_verificado=True,
    )
    op_demo_valido = _crear_usuario(
        "op_demo_ok",
        grupos=["demo_operadora"],
        con_cuenta_local=False,
    )
    # Exclusiones
    _crear_usuario("solo_lectura", grupos=["demo_lectura"], con_cuenta_local=False)
    _crear_usuario(
        "staff_sin_cap",
        grupos=[],
        is_staff=True,
        is_superuser=True,
        con_cuenta_local=False,
    )
    _crear_usuario(
        "local_admin",
        grupos=["local_administracion"],
        con_cuenta_local=True,
    )
    _crear_usuario(
        "sin_permisos",
        grupos=["demo_solicitante"],
        con_cuenta_local=True,
    )
    _crear_usuario(
        "local_pendiente",
        grupos=["demo_operadora"],
        con_cuenta_local=True,
        estado_local=CuentaLocal.Estado.PENDIENTE,
        email_verificado=True,
    )
    _crear_usuario(
        "local_sin_verificar",
        grupos=["demo_operadora"],
        con_cuenta_local=True,
        estado_local=CuentaLocal.Estado.APROBADA,
        email_verificado=False,
    )
    _crear_usuario(
        "inactivo",
        grupos=["demo_operadora"],
        is_active=False,
        con_cuenta_local=True,
    )

    solicitud = _crear_solicitud_directa(autor, numero=2001)
    creados = generar_aviso_nueva_solicitud(solicitud.pk)

    assert creados == 2
    destinatarios = set(
        Aviso.objects.filter(solicitud_id=solicitud.pk).values_list("destinatario_id", flat=True)
    )
    assert destinatarios == {op_local_valido.pk, op_demo_valido.pk}

    aviso = Aviso.objects.get(destinatario=op_local_valido, solicitud_id=solicitud.pk)
    assert aviso.tipo == TipoAviso.NUEVA_SOLICITUD_GASTO
    assert aviso.get_absolute_url() == reverse("gastos:detalle", kwargs={"pk": solicitud.pk})


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=False)
def test_respeta_flags_identidad_demo_deshabilitado():
    autor = _crear_usuario("autor_f", grupos=["demo_solicitante"], con_cuenta_local=True)
    op_local = _crear_usuario("op_local_f", grupos=["demo_operadora"], con_cuenta_local=True)
    _crear_usuario("op_demo_f", grupos=["demo_operadora"], con_cuenta_local=False)

    solicitud = _crear_solicitud_directa(autor, numero=2002)
    creados = generar_aviso_nueva_solicitud(solicitud.pk)

    assert creados == 1
    assert list(Aviso.objects.values_list("destinatario_id", flat=True)) == [op_local.pk]


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=False, DEMO_IDENTITY_ENABLED=True)
def test_respeta_flags_identidad_local_deshabilitado_sin_fallback():
    autor = _crear_usuario("autor_l", grupos=["demo_solicitante"], con_cuenta_local=False)
    _crear_usuario("op_local_l", grupos=["demo_operadora"], con_cuenta_local=True)
    op_demo = _crear_usuario("op_demo_l", grupos=["demo_operadora"], con_cuenta_local=False)

    solicitud = _crear_solicitud_directa(autor, numero=2003)
    creados = generar_aviso_nueva_solicitud(solicitud.pk)

    assert creados == 1
    assert list(Aviso.objects.values_list("destinatario_id", flat=True)) == [op_demo.pk]


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_idempotencia_preserva_fecha_leida():
    autor = _crear_usuario("autor_i", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_i", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitud = _crear_solicitud_directa(autor, numero=2004)

    assert generar_aviso_nueva_solicitud(solicitud.pk) == 1
    aviso = Aviso.objects.get(destinatario=op, solicitud_id=solicitud.pk)
    marca_leida = timezone.now()
    aviso.leida_en = marca_leida
    aviso.save(update_fields=["leida_en"])

    assert generar_aviso_nueva_solicitud(solicitud.pk) == 0
    assert Aviso.objects.filter(destinatario=op, solicitud_id=solicitud.pk).count() == 1
    aviso.refresh_from_db()
    assert aviso.leida_en == marca_leida


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_creacion_real_dispara_callback_on_commit(django_capture_on_commit_callbacks):
    solicitante = _crear_usuario("sol_real", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_real", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    with django_capture_on_commit_callbacks(execute=True):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Compra sintética real",
            monto_estimado=Decimal("320.00"),
            unidad_requirente="Área sintética",
        )

    assert solicitud.estado == EstadoSolicitud.PRESENTADA
    assert Aviso.objects.filter(destinatario=op, solicitud_id=solicitud.pk).count() == 1


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_outer_rollback_no_crea_avisos(django_capture_on_commit_callbacks):
    solicitante = _crear_usuario("sol_rb", grupos=["demo_solicitante"], con_cuenta_local=True)
    _crear_usuario("op_rb", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                crear_solicitud_gasto(
                    actor=actor,
                    concepto="Compra revertida",
                    monto_estimado=Decimal("100.00"),
                    unidad_requirente="Área sintética",
                )
                raise RuntimeError("Fallo simulado para revertir")
        except RuntimeError:
            pass

    assert SolicitudGasto.objects.count() == 0
    assert Aviso.objects.count() == 0


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_fallo_callback_no_pierde_solicitud_y_reintento_recupera(
    django_capture_on_commit_callbacks,
    caplog,
):
    solicitante = _crear_usuario("sol_err", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_err", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    with (
        patch(
            "avisos.services.generar_aviso_nueva_solicitud",
            side_effect=RuntimeError("Fallo transitorio simulado"),
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Compra con fallo de aviso",
            monto_estimado=Decimal("450.00"),
            unidad_requirente="Área sintética",
        )

    assert SolicitudGasto.objects.filter(pk=solicitud.pk).exists()
    assert Aviso.objects.count() == 0
    assert str(solicitud.pk) in caplog.text

    out = StringIO()
    call_command("reintentar_aviso_gasto", str(solicitud.pk), stdout=out)
    assert Aviso.objects.filter(destinatario=op, solicitud_id=solicitud.pk).count() == 1
    assert "1 nuevos" in out.getvalue()

    # Segundo reintento idempotente
    out_rep = StringIO()
    call_command("reintentar_aviso_gasto", str(solicitud.pk), stdout=out_rep)
    assert Aviso.objects.filter(destinatario=op, solicitud_id=solicitud.pk).count() == 1
    assert "0 nuevos" in out_rep.getvalue()


@pytest.mark.django_db
def test_reintento_solicitud_inexistente_falla_visible():
    with pytest.raises(SolicitudGasto.DoesNotExist):
        generar_aviso_nueva_solicitud(999999)

    with pytest.raises(CommandError, match="999999"):
        call_command("reintentar_aviso_gasto", "999999")
