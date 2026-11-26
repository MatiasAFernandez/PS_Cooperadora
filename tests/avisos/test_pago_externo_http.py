"""Pruebas HTTP para avisos web de pago externo registrado (SPEC-031)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from avisos.models import Aviso, TipoAviso
from comunes.models import Circuito, TramiteBase
from gastos.models import (
    DecisionGasto,
    EstadoSolicitud,
    EventoPagoExterno,
    PagoExterno,
    SolicitudGasto,
)
from identidad.models import CuentaLocal

User = get_user_model()


def _crear_usuario(
    username: str,
    *,
    grupos: list[str] | None = None,
    con_cuenta_local: bool = True,
):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@sintetico.test",
        password="clave-sintetica-no-productiva",
        is_active=True,
    )
    for nombre_grupo in grupos or []:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)
    if con_cuenta_local:
        CuentaLocal.objects.create(
            user=user,
            email=f"{username}@sintetico.test",
            nombre_completo=f"Usuario {username}",
            estado=CuentaLocal.Estado.APROBADA,
            email_verificado_en=timezone.now(),
        )
    return user


def _crear_solicitud(
    solicitante, numero: int, *, estado: str = EstadoSolicitud.ACEPTADA
) -> SolicitudGasto:
    base = TramiteBase.objects.create(
        circuito=Circuito.GASTO,
        numero_publico=numero,
        solicitante_actor_id=str(solicitante.pk),
        centro_costo_codigo=None,
    )
    return SolicitudGasto.objects.create(
        pk=numero,
        tramite_base=base,
        concepto=f"Concepto confidencial #{numero}",
        monto_estimado=Decimal("45000.00"),
        unidad_requirente="Unidad sintética",
        solicitante=solicitante,
        estado=estado,
        version=1,
    )


def _crear_pago_y_evento(
    solicitud: SolicitudGasto,
    registrador,
    *,
    fecha_pago: date = date(2026, 11, 20),
    fecha_evento: datetime | None = None,
    monto_bruto: Decimal = Decimal("123456.78"),
    monto_retencion_atp: Decimal = Decimal("0.00"),
    referencia_atp: str = "",
    referencia_externa: str = "REF-CONFIDENCIAL-9988",
    referencia_documental: str | None = None,
    tipo_evento: str = "pago_externo_registrado",
) -> EventoPagoExterno:
    pago = PagoExterno.objects.create(
        solicitud=solicitud,
        importe=monto_bruto - monto_retencion_atp,
        monto_bruto=monto_bruto,
        monto_retencion_atp=monto_retencion_atp,
        referencia_atp=referencia_atp,
        moneda="ARS",
        fecha_pago=fecha_pago,
        referencia_externa=referencia_externa,
        referencia_documental=referencia_documental or f"doc-pago-{solicitud.pk}",
        version=1,
        huella_idempotencia=f"{solicitud.pk:064d}",
    )
    if fecha_evento is not None:
        with patch("django.utils.timezone.now", return_value=fecha_evento):
            return EventoPagoExterno.objects.create(
                pago=pago,
                tipo_evento=tipo_evento,
                actor=registrador,
            )
    return EventoPagoExterno.objects.create(
        pago=pago,
        tipo_evento=tipo_evento,
        actor=registrador,
    )


@pytest.mark.django_db
@override_settings(
    LOCAL_IDENTITY_ENABLED=True,
    DEMO_IDENTITY_ENABLED=True,
    TIME_ZONE="America/Argentina/Buenos_Aires",
)
def test_titular_ve_aviso_pago_historico_cuenta_y_marca_con_timestamp_estable():
    titular = _crear_usuario("tit_pago", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_pago", grupos=["demo_operadora"])
    solicitud = _crear_solicitud(titular, 2101, estado=EstadoSolicitud.ACEPTADA)

    fecha_evento = datetime(2026, 11, 14, 2, 15, tzinfo=UTC)
    evento = _crear_pago_y_evento(
        solicitud,
        operadora,
        fecha_pago=date(2025, 4, 17),
        fecha_evento=fecha_evento,
        monto_bruto=Decimal("98765.43"),
        monto_retencion_atp=Decimal("4321.10"),
        referencia_atp="ATP-RES-55",
        referencia_externa="OP-SECRETA-77",
        referencia_documental="doc-privado-2101",
    )
    aviso = Aviso.objects.create(
        destinatario=titular,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=solicitud.pk,
        evento_pago_id=evento.pk,
    )

    client = Client()
    client.force_login(titular)

    with timezone.override("America/Argentina/Buenos_Aires"):
        resp_lista = client.get(reverse("avisos:lista"))

    assert resp_lista.status_code == 200
    assert "no-store" in resp_lista.headers.get("Cache-Control", "")
    html = resp_lista.content.decode("utf-8")
    assert "Pago externo registrado (solicitud #2101)" in html
    texto_visible = " ".join(strip_tags(html).split())
    assert (
        "El 13/11/2026 23:15 se registró un pago externo para la solicitud #2101." in texto_visible
    )
    assert "17/04/2025" not in html
    for prohibido in (
        "Concepto confidencial #2101",
        "98765",
        "98.765",
        "94444",
        "94.444",
        "4321",
        "4.321",
        "ATP-RES-55",
        "OP-SECRETA-77",
        "doc-privado-2101",
        "Pagado",
        "ejecutada",
    ):
        assert prohibido not in html

    resp_contador = client.get(reverse("avisos:contador"))
    assert resp_contador.status_code == 200
    assert resp_contador.json() == {"no_leidos": 1}

    resp_mark = client.post(reverse("avisos:leer", kwargs={"pk": aviso.pk}))
    assert resp_mark.status_code == 302
    aviso.refresh_from_db()
    primer_ts = aviso.leida_en
    assert primer_ts is not None

    # Replay idempotente conserva timestamp original
    client.post(reverse("avisos:leer", kwargs={"pk": aviso.pk}))
    aviso.refresh_from_db()
    assert aviso.leida_en == primer_ts
    assert client.get(reverse("avisos:contador")).json() == {"no_leidos": 0}


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_otro_propietario_y_operador_no_titular_no_ven_ni_marcan_aviso_pago():
    titular = _crear_usuario("tit_own", grupos=["demo_solicitante"])
    otro_titular = _crear_usuario("tit_other", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_other", grupos=["demo_operadora"])
    solicitud = _crear_solicitud(titular, 2201, estado=EstadoSolicitud.ACEPTADA)
    evento = _crear_pago_y_evento(solicitud, operadora)
    aviso = Aviso.objects.create(
        destinatario=titular,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=solicitud.pk,
        evento_pago_id=evento.pk,
    )

    for usuario_ajeno in (otro_titular, operadora):
        c = Client()
        c.force_login(usuario_ajeno)
        resp_lista = c.get(reverse("avisos:lista"))
        assert resp_lista.status_code == 200
        assert "Pago externo registrado (solicitud #2201)" not in resp_lista.content.decode("utf-8")
        assert c.get(reverse("avisos:contador")).json() == {"no_leidos": 0}
        assert c.post(reverse("avisos:leer", kwargs={"pk": aviso.pk})).status_code == 404

    aviso.refresh_from_db()
    assert aviso.leida_en is None


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_revocar_consulta_csrf_get_no_muta_y_fuentes_cruzadas_o_desconocidas():
    titular = _crear_usuario("tit_sec", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_sec", grupos=["demo_operadora"])
    sol_propia = _crear_solicitud(titular, 2301, estado=EstadoSolicitud.ACEPTADA)
    sol_ajena = _crear_solicitud(operadora, 2302, estado=EstadoSolicitud.ACEPTADA)

    ev_propio = _crear_pago_y_evento(sol_propia, operadora)
    ev_ajeno = _crear_pago_y_evento(sol_ajena, operadora)

    aviso_valido = Aviso.objects.create(
        destinatario=titular,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=sol_propia.pk,
        evento_pago_id=ev_propio.pk,
    )
    aviso_cruzado = Aviso.objects.create(
        destinatario=titular,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=sol_propia.pk,
        evento_pago_id=ev_ajeno.pk,
    )
    aviso_desconocido = Aviso.objects.create(
        destinatario=titular,
        tipo="evento_desconocido",
        solicitud_id=sol_propia.pk,
    )

    c_csrf = Client(enforce_csrf_checks=True)
    c_csrf.force_login(titular)
    assert c_csrf.post(reverse("avisos:leer", kwargs={"pk": aviso_valido.pk})).status_code == 403

    c = Client()
    c.force_login(titular)
    assert c.get(reverse("avisos:leer", kwargs={"pk": aviso_valido.pk})).status_code == 405
    aviso_valido.refresh_from_db()
    assert aviso_valido.leida_en is None

    # Cruzados y tipos desconocidos no se exponen ni permiten marcado
    resp_lista = c.get(reverse("avisos:lista"))
    assert resp_lista.status_code == 200
    assert c.get(reverse("avisos:contador")).json() == {"no_leidos": 1}
    assert c.post(reverse("avisos:leer", kwargs={"pk": aviso_cruzado.pk})).status_code == 404
    assert c.post(reverse("avisos:leer", kwargs={"pk": aviso_desconocido.pk})).status_code == 404

    # Revocar consulta deja fuera
    titular.groups.remove(Group.objects.get(name="demo_solicitante"))
    assert c.get(reverse("avisos:lista")).status_code == 403
    assert c.get(reverse("avisos:contador")).status_code == 403
    assert c.post(reverse("avisos:leer", kwargs={"pk": aviso_valido.pk})).status_code == 403


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_bandeja_mezcla_tres_tipos_sin_n_mas_uno():
    usuario_mixto = _crear_usuario("mixto_user", grupos=["demo_solicitante", "demo_operadora"])
    otro = _crear_usuario("otro_mixto", grupos=["demo_solicitante"])

    sol_operativa = _crear_solicitud(otro, 2401, estado=EstadoSolicitud.PRESENTADA)
    Aviso.objects.create(
        destinatario=usuario_mixto,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=sol_operativa.pk,
    )

    sol_propia_1 = _crear_solicitud(usuario_mixto, 2402, estado=EstadoSolicitud.ACEPTADA)
    dec_1 = DecisionGasto.objects.create(
        solicitud=sol_propia_1,
        autor=otro,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
        motivo="Motivo reservado",
    )
    Aviso.objects.create(
        destinatario=usuario_mixto,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=sol_propia_1.pk,
        decision_id=dec_1.pk,
    )
    ev_1 = _crear_pago_y_evento(sol_propia_1, usuario_mixto)
    Aviso.objects.create(
        destinatario=usuario_mixto,
        tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
        solicitud_id=sol_propia_1.pk,
        evento_pago_id=ev_1.pk,
    )

    c = Client()
    c.force_login(usuario_mixto)

    with CaptureQueriesContext(connection) as ctx_base:
        resp_1 = c.get(reverse("avisos:lista"))
    assert resp_1.status_code == 200
    html_1 = resp_1.content.decode("utf-8")
    assert "Nueva solicitud de gasto #2401" in html_1
    assert "Decisión registrada: Aceptada (solicitud #2402)" in html_1
    assert "Pago externo registrado (solicitud #2402)" in html_1

    # Agregar 3 avisos de pago más en la misma página no debe sumar consultas (sin N+1)
    for idx, numero in enumerate((2403, 2404, 2405), start=1):
        sol_extra = _crear_solicitud(usuario_mixto, numero, estado=EstadoSolicitud.ACEPTADA)
        ev_extra = _crear_pago_y_evento(
            sol_extra,
            usuario_mixto,
            fecha_evento=timezone.now() - timedelta(minutes=idx),
        )
        Aviso.objects.create(
            destinatario=usuario_mixto,
            tipo=TipoAviso.PAGO_EXTERNO_REGISTRADO,
            solicitud_id=sol_extra.pk,
            evento_pago_id=ev_extra.pk,
        )

    with CaptureQueriesContext(connection) as ctx_multi:
        resp_2 = c.get(reverse("avisos:lista"))
    assert resp_2.status_code == 200
    assert len(ctx_multi) == len(ctx_base)
