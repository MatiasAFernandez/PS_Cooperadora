"""Pruebas unitarias e integración para el canal de correo de avisos de Gastos."""

from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections, transaction
from django.test import override_settings
from django.utils import timezone

from avisos.correo import (
    ConfiguracionCorreoInvalida,
    _lock_key_intencion,
    procesar_intencion_correo,
    validar_remitente_avisos,
    validar_url_base_avisos,
)
from avisos.models import Aviso, EstadoIntencionCorreo, IntencionCorreo, TipoAviso
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
    email: str | None = None,
    is_active: bool = True,
    con_cuenta_local: bool = False,
    estado_local: str = CuentaLocal.Estado.APROBADA,
    email_verificado: bool = True,
):
    correo = f"{username}@sintetico.test" if email is None else email
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


def _crear_solicitud_directa(solicitante, numero: int = 3001) -> SolicitudGasto:
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
        monto_estimado=Decimal("987.65"),
        unidad_requirente="Área sintética",
        solicitante=solicitante,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_canal_apagado_no_prepara_ni_envia_y_bloquea_reintento(
    django_capture_on_commit_callbacks,
):
    solicitante = _crear_usuario("sol_off", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_off", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    with django_capture_on_commit_callbacks(execute=True):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Compra sin correo",
            monto_estimado=Decimal("100.00"),
            unidad_requirente="Área sintética",
        )

    assert Aviso.objects.filter(destinatario=op, solicitud_id=solicitud.pk).count() == 1
    assert IntencionCorreo.objects.count() == 0
    assert len(mail.outbox) == 0

    with pytest.raises(CommandError, match="deshabilitado"):
        call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_rollback_externo_no_crea_intenciones_ni_envia(django_capture_on_commit_callbacks):
    solicitante = _crear_usuario("sol_rb_mail", grupos=["demo_solicitante"], con_cuenta_local=True)
    _crear_usuario("op_rb_mail", grupos=["demo_operadora"], con_cuenta_local=True)
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
                    monto_estimado=Decimal("200.00"),
                    unidad_requirente="Área sintética",
                )
                raise RuntimeError("Rollback simulado")
        except RuntimeError:
            pass

    assert SolicitudGasto.objects.count() == 0
    assert Aviso.objects.count() == 0
    assert IntencionCorreo.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000/",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_post_commit_envia_correo_minimo_y_respeta_aceptado(
    django_capture_on_commit_callbacks,
):
    solicitante = _crear_usuario(
        "sol_ok",
        grupos=["demo_solicitante", "demo_operadora"],
        con_cuenta_local=True,
    )
    op = _crear_usuario("op_ok", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    with django_capture_on_commit_callbacks(execute=True):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Dato sensible que no debe viajar",
            monto_estimado=Decimal("777.00"),
            unidad_requirente="Área sintética",
        )

    assert len(mail.outbox) == 1
    enviado = mail.outbox[0]
    assert enviado.to == ["op_ok@sintetico.test"]
    assert enviado.from_email == "cooperadora@sintetico.test"
    assert enviado.subject == f"[PS_Cooperadora] Nueva solicitud de gasto #{solicitud.pk}"
    assert f"http://127.0.0.1:8000/gastos/{solicitud.pk}/" in enviado.body
    assert "Dato sensible" not in enviado.body
    assert "777" not in enviado.body

    intencion = IntencionCorreo.objects.get(
        aviso__destinatario=op,
        aviso__solicitud_id=solicitud.pk,
    )
    assert intencion.estado == EstadoIntencionCorreo.ACEPTADO
    assert intencion.intentos == 1
    assert intencion.aceptado_en is not None
    assert intencion.direccion_ultimo_intento == "op_ok@sintetico.test"

    # Repetir generación o reintento no duplica envío aceptado
    assert generar_aviso_nueva_solicitud(solicitud.pk, preparar_correo=True) == 0
    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_sin_historico_ni_efectos_comando_web():
    autor = _crear_usuario("autor_hist", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_hist", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitud = _crear_solicitud_directa(autor, numero=3010)

    # Aviso previo existente sin IntencionCorreo
    Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )

    out = StringIO()
    call_command("reintentar_aviso_gasto", str(solicitud.pk), stdout=out)

    assert IntencionCorreo.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_error_open_queda_fallido_y_reintento_recupera(django_capture_on_commit_callbacks):
    solicitante = _crear_usuario("sol_open_err", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_open_err", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    conn_fallida = MagicMock()
    conn_fallida.open.side_effect = OSError("Conexión rechazada secreta")

    with (
        patch("avisos.correo.get_connection", return_value=conn_fallida),
        django_capture_on_commit_callbacks(execute=True),
    ):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Compra con error SMTP open",
            monto_estimado=Decimal("310.00"),
            unidad_requirente="Área sintética",
        )

    assert SolicitudGasto.objects.filter(pk=solicitud.pk).exists()
    intencion = IntencionCorreo.objects.get(
        aviso__destinatario=op,
        aviso__solicitud_id=solicitud.pk,
    )
    assert intencion.estado == EstadoIntencionCorreo.FALLIDO
    assert intencion.codigo_resultado == "smtp_conexion_error"
    assert "secreta" not in intencion.codigo_resultado

    # Reintento normal con backend locmem recupera
    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")
    intencion.refresh_from_db()
    assert intencion.estado == EstadoIntencionCorreo.ACEPTADO
    assert intencion.intentos == 2
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
)
def test_error_send_queda_incierto_y_error_close_no_degrada_aceptado(
    django_capture_on_commit_callbacks,
):
    solicitante = _crear_usuario("sol_send_err", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_send_err", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    conn_incierto = MagicMock()
    conn_incierto.open.return_value = True
    conn_incierto.send_messages.side_effect = TimeoutError("Timeout tras envío")

    with (
        patch("avisos.correo.get_connection", return_value=conn_incierto),
        django_capture_on_commit_callbacks(execute=True),
    ):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Compra incierta",
            monto_estimado=Decimal("410.00"),
            unidad_requirente="Área sintética",
        )

    intencion = IntencionCorreo.objects.get(
        aviso__destinatario=op,
        aviso__solicitud_id=solicitud.pk,
    )
    assert intencion.estado == EstadoIntencionCorreo.INCIERTO
    assert intencion.codigo_resultado == "smtp_envio_incierto"
    conn_incierto.close.assert_called_once()

    # Reintento normal no reenvía incierto
    with patch("avisos.correo.get_connection") as mock_get_conn:
        call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")
        mock_get_conn.assert_not_called()

    # Error en close() tras aceptación no degrada ACEPTADO
    aviso2 = Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk + 100,
    )
    _crear_solicitud_directa(solicitante, numero=solicitud.pk + 100)
    intencion2 = IntencionCorreo.objects.create(aviso=aviso2)

    conn_close_err = MagicMock()
    conn_close_err.open.return_value = True
    conn_close_err.send_messages.return_value = 1
    conn_close_err.close.side_effect = OSError("Error al cerrar")

    with patch("avisos.correo.get_connection", return_value=conn_close_err):
        res = procesar_intencion_correo(intencion2.pk)

    assert res.estado == EstadoIntencionCorreo.ACEPTADO
    intencion2.refresh_from_db()
    assert intencion2.estado == EstadoIntencionCorreo.ACEPTADO


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
)
def test_fallo_persistir_post_envio_conserva_en_proceso():
    autor = _crear_usuario("autor_db_err", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_db_err", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitud = _crear_solicitud_directa(autor, numero=3020)
    aviso = Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    intencion = IntencionCorreo.objects.create(aviso=aviso)

    conn_ok = MagicMock()
    conn_ok.open.return_value = True
    conn_ok.send_messages.return_value = 1

    with (
        patch("avisos.correo.get_connection", return_value=conn_ok),
        patch("avisos.correo._marcar_resultado_seguro", return_value=False),
    ):
        res = procesar_intencion_correo(intencion.pk)

    assert res.estado == EstadoIntencionCorreo.EN_PROCESO
    intencion.refresh_from_db()
    assert intencion.estado == EstadoIntencionCorreo.EN_PROCESO


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_revalida_permisos_y_correo_al_enviar():
    autor = _crear_usuario("autor_rev", grupos=["demo_solicitante"], con_cuenta_local=True)
    op_sin_perm = _crear_usuario("op_rev_perm", grupos=["demo_operadora"], con_cuenta_local=True)
    op_sin_mail = _crear_usuario(
        "op_rev_mail",
        grupos=["demo_operadora"],
        email="",
        con_cuenta_local=True,
    )
    solicitud = _crear_solicitud_directa(autor, numero=3030)

    aviso_perm = Aviso.objects.create(
        destinatario=op_sin_perm,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    int_perm = IntencionCorreo.objects.create(aviso=aviso_perm)

    aviso_mail = Aviso.objects.create(
        destinatario=op_sin_mail,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    int_mail = IntencionCorreo.objects.create(aviso=aviso_mail)

    # Revocar permisos antes del envío
    op_sin_perm.groups.clear()

    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")

    int_perm.refresh_from_db()
    int_mail.refresh_from_db()
    assert int_perm.estado == EstadoIntencionCorreo.OMITIDO
    assert int_perm.codigo_resultado == "sin_permisos"
    assert int_mail.estado == EstadoIntencionCorreo.FALLIDO
    assert int_mail.codigo_resultado == "correo_destinatario_invalido"
    assert len(mail.outbox) == 0

    # Corregir correo de CuentaLocal y reintentar
    op_sin_mail.cuenta_local.email = "corregido@sintetico.test"
    op_sin_mail.cuenta_local.save(update_fields=["email"])
    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")

    int_mail.refresh_from_db()
    assert int_mail.estado == EstadoIntencionCorreo.ACEPTADO
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["corregido@sintetico.test"]


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("https://cooperadora.example.org", "https://cooperadora.example.org"),
        ("https://cooperadora.example.org/", "https://cooperadora.example.org"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
        ("http://localhost:8000/", "http://localhost:8000"),
        ("http://[::1]:8000", "http://[::1]:8000"),
    ],
)
def test_url_base_valida(url: str, esperado: str):
    assert validar_url_base_avisos(url) == esperado


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "http://cooperadora.example.org",
        "https://user:pass@cooperadora.example.org",
        "https://cooperadora.example.org/gastos",
        "https://cooperadora.example.org?next=/",
        "https://cooperadora.example.org#sec",
        "http://localhost:99999",
        "http://localhost:0",
        "http://localhost:",
        "ftp://localhost:8000",
        "https://host con espacio",
        "https://cooperadora.example.org\n",
        "https://cooperadora.example.org\r\n",
        "https://cooperadora.example.org\t",
        "https://invalido..example.org",
        "https://-invalido.example.org",
        "https://solo-etiqueta",
    ],
)
def test_url_base_invalida(url: str):
    with pytest.raises(ConfiguracionCorreoInvalida):
        validar_url_base_avisos(url)


@pytest.mark.parametrize(
    "remitente",
    [
        "",
        "   ",
        "sin-arroba",
        "coop@sintetico.test\r\nBcc: otro@sintetico.test",
        "Cooperadora <coop@sintetico.test>\n",
        "coop@sintetico.test\r",
    ],
)
def test_remitente_invalido_rechaza_crlf_y_header_injection(remitente: str):
    with pytest.raises(ConfiguracionCorreoInvalida):
        validar_remitente_avisos(remitente)


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_independencia_dos_destinatarios():
    autor = _crear_usuario("autor_ind", grupos=["demo_solicitante"], con_cuenta_local=True)
    op1 = _crear_usuario("op_ind_1", grupos=["demo_operadora"], email="", con_cuenta_local=True)
    op2 = _crear_usuario("op_ind_2", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitud = _crear_solicitud_directa(autor, numero=3040)

    av1 = Aviso.objects.create(
        destinatario=op1,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    av2 = Aviso.objects.create(
        destinatario=op2,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    int1 = IntencionCorreo.objects.create(aviso=av1)
    int2 = IntencionCorreo.objects.create(aviso=av2)

    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")

    int1.refresh_from_db()
    int2.refresh_from_db()
    assert int1.estado == EstadoIntencionCorreo.FALLIDO
    assert int2.estado == EstadoIntencionCorreo.ACEPTADO
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["op_ind_2@sintetico.test"]


@pytest.mark.django_db(transaction=True)
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
)
def test_exclusion_advisory_lock_segunda_conexion_no_roba_envio_ni_concilia():
    conn = connections["default"]
    if conn.vendor != "postgresql":
        pytest.skip("Prueba de advisory lock exclusiva de PostgreSQL")

    autor = _crear_usuario("autor_lock", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_lock", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitud = _crear_solicitud_directa(autor, numero=3050)
    aviso = Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    intencion = IntencionCorreo.objects.create(
        aviso=aviso,
        estado=EstadoIntencionCorreo.EN_PROCESO,
    )

    # Segunda conexión independiente a PostgreSQL toma el advisory lock
    import psycopg

    params = conn.get_connection_params()
    key = _lock_key_intencion(intencion.pk)
    with psycopg.connect(**params) as segunda_conn:
        with segunda_conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [key])
            assert cur.fetchone()[0] is True

        res = procesar_intencion_correo(intencion.pk)
        assert res.ejecutado is False
        assert res.codigo == "emisor_activo"

        with pytest.raises(CommandError, match="emisor activo"):
            call_command(
                "correo_aviso_gasto",
                str(solicitud.pk),
                "--conciliar-envio",
                str(intencion.pk),
                "--resultado",
                "aceptado",
            )


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_comando_consulta_y_conciliacion_flags():
    autor = _crear_usuario("autor_cli", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_cli", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitud = _crear_solicitud_directa(autor, numero=3060)
    aviso = Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )
    intencion = IntencionCorreo.objects.create(
        aviso=aviso,
        estado=EstadoIntencionCorreo.INCIERTO,
        direccion_ultimo_intento="op_cli@sintetico.test",
    )

    # Consulta por defecto no muestra direcciones ni envía
    out_consulta = StringIO()
    call_command("correo_aviso_gasto", str(solicitud.pk), stdout=out_consulta)
    salida = out_consulta.getvalue()
    assert f"intencion={intencion.pk}" in salida
    assert "estado=incierto" in salida
    assert "op_cli@sintetico.test" not in salida
    assert len(mail.outbox) == 0

    # Reintentar por conciliación sin confirmar riesgo falla
    with pytest.raises(CommandError, match="riesgo"):
        call_command(
            "correo_aviso_gasto",
            str(solicitud.pk),
            "--conciliar-envio",
            str(intencion.pk),
            "--resultado",
            "reintentar",
        )

    # Con confirmación explícita pasa a FALLIDO y luego --reintentar lo envía
    call_command(
        "correo_aviso_gasto",
        str(solicitud.pk),
        "--conciliar-envio",
        str(intencion.pk),
        "--resultado",
        "reintentar",
        "--confirmar-riesgo-duplicado",
    )
    intencion.refresh_from_db()
    assert intencion.estado == EstadoIntencionCorreo.FALLIDO

    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")
    intencion.refresh_from_db()
    assert intencion.estado == EstadoIntencionCorreo.ACEPTADO
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_error_constructor_backend_queda_fallido_sin_filtrar_secreto_y_reintenta(
    django_capture_on_commit_callbacks,
    caplog,
):
    solicitante = _crear_usuario("sol_ctor_err", grupos=["demo_solicitante"], con_cuenta_local=True)
    op1 = _crear_usuario("op_ctor_err_1", grupos=["demo_operadora"], con_cuenta_local=True)
    op2 = _crear_usuario("op_ctor_err_2", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    caplog.set_level("INFO")
    with (
        patch(
            "avisos.correo.get_connection",
            side_effect=RuntimeError("SECRETO_BACKEND_SENUELO_123"),
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Compra con error en constructor backend",
            monto_estimado=Decimal("320.00"),
            unidad_requirente="Área sintética",
        )

    assert Aviso.objects.filter(solicitud_id=solicitud.pk).count() == 2
    intenciones = list(
        IntencionCorreo.objects.filter(aviso__solicitud_id=solicitud.pk).order_by("pk")
    )
    assert len(intenciones) == 2
    for intencion in intenciones:
        assert intencion.estado == EstadoIntencionCorreo.FALLIDO
        assert intencion.codigo_resultado == "error_preparacion_correo"
        assert "SECRETO_BACKEND_SENUELO_123" not in intencion.codigo_resultado

    assert "SECRETO_BACKEND_SENUELO_123" not in caplog.text
    assert len(mail.outbox) == 0

    # Al corregir la configuración, el reintento normal recupera ambos envíos
    call_command("correo_aviso_gasto", str(solicitud.pk), "--reintentar")
    for intencion in intenciones:
        intencion.refresh_from_db()
        assert intencion.estado == EstadoIntencionCorreo.ACEPTADO
        assert intencion.intentos == 2
    assert len(mail.outbox) == 2
    assert {m.to[0] for m in mail.outbox} == {op1.email, op2.email}


@pytest.mark.django_db(transaction=True)
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    AVISOS_EMAIL_ENABLED=True,
    AVISOS_PUBLIC_BASE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="cooperadora@sintetico.test",
)
def test_commit_real_ejecuta_smtp_fuera_de_atomic_con_aviso_e_intencion_persistidos():
    solicitante = _crear_usuario("sol_tx_real", grupos=["demo_solicitante"], con_cuenta_local=True)
    op = _crear_usuario("op_tx_real", grupos=["demo_operadora"], con_cuenta_local=True)
    actor = Actor(
        subject_id=solicitante.pk,
        capabilities=frozenset({"gastos.presentar", "gastos.consultar_propias"}),
    )

    observado: dict[str, object] = {
        "open_called": False,
        "send_called": False,
    }

    class FakeConnection:
        def open(self) -> bool:
            observado["open_called"] = True
            observado["in_atomic_open"] = connection.in_atomic_block
            observado["aviso_en_open"] = Aviso.objects.filter(destinatario=op).exists()
            observado["intencion_en_open"] = IntencionCorreo.objects.filter(
                aviso__destinatario=op
            ).exists()
            return True

        def send_messages(self, messages) -> int:
            observado["send_called"] = True
            observado["in_atomic_send"] = connection.in_atomic_block
            observado["aviso_en_send"] = Aviso.objects.filter(destinatario=op).exists()
            observado["intencion_en_send"] = IntencionCorreo.objects.filter(
                aviso__destinatario=op
            ).exists()
            return len(messages)

        def close(self) -> None:
            return None

    with patch("avisos.correo.get_connection", return_value=FakeConnection()):
        solicitud = crear_solicitud_gasto(
            actor=actor,
            concepto="Compra con commit real",
            monto_estimado=Decimal("550.00"),
            unidad_requirente="Área sintética",
        )

    assert observado["open_called"] is True
    assert observado["send_called"] is True
    assert observado["in_atomic_open"] is False
    assert observado["in_atomic_send"] is False
    assert observado["aviso_en_open"] is True
    assert observado["intencion_en_open"] is True
    assert observado["aviso_en_send"] is True
    assert observado["intencion_en_send"] is True

    intencion = IntencionCorreo.objects.get(
        aviso__destinatario=op,
        aviso__solicitud_id=solicitud.pk,
    )
    assert intencion.estado == EstadoIntencionCorreo.ACEPTADO
