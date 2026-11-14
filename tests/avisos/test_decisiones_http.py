"""Pruebas HTTP para avisos web de decisiones de Gastos (SPEC-030)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from avisos.models import Aviso, TipoAviso
from comunes.models import Circuito, TramiteBase
from gastos.models import DecisionGasto, EstadoSolicitud, SolicitudGasto
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


def _crear_decision(
    solicitud: SolicitudGasto,
    autor,
    *,
    estado_anterior: str,
    estado_resultante: str,
    motivo: str = "Motivo confidencial de prueba",
) -> DecisionGasto:
    return DecisionGasto.objects.create(
        solicitud=solicitud,
        autor=autor,
        estado_anterior=estado_anterior,
        estado_resultante=estado_resultante,
        motivo=motivo,
    )


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_solicitante_ve_decision_historica_cuenta_y_marca_con_timestamp_estable():
    solicitante = _crear_usuario("sol_dec", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_dec", grupos=["demo_operadora"])
    solicitud = _crear_solicitud(solicitante, 1101, estado=EstadoSolicitud.ACEPTADA)

    dec_post = _crear_decision(
        solicitud,
        operadora,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.POSTERGADA,
        motivo="Motivo reservado postergacion",
    )
    dec_acep = _crear_decision(
        solicitud,
        operadora,
        estado_anterior=EstadoSolicitud.POSTERGADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
        motivo="Motivo reservado aceptacion",
    )
    aviso_post = Aviso.objects.create(
        destinatario=solicitante,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
        decision_id=dec_post.pk,
    )
    aviso_acep = Aviso.objects.create(
        destinatario=solicitante,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
        decision_id=dec_acep.pk,
    )
    # Aviso operativo ajeno en la DB: no debe contar ni mostrarse al solicitante
    Aviso.objects.create(
        destinatario=solicitante,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=1102,
    )

    client = Client()
    client.force_login(solicitante)

    resp_lista = client.get(reverse("avisos:lista"))
    assert resp_lista.status_code == 200
    assert "no-store" in resp_lista.headers.get("Cache-Control", "")
    html = resp_lista.content.decode("utf-8")
    assert "Decisión registrada: Postergada" in html
    assert "Decisión registrada: Aceptada" in html
    assert "se registró la decisión Postergada sobre la solicitud #1101" in html
    assert "Motivo reservado" not in html
    assert "Nueva solicitud de gasto #1102" not in html

    resp_contador = client.get(reverse("avisos:contador"))
    assert resp_contador.status_code == 200
    assert resp_contador.json() == {"no_leidos": 2}

    resp_mark = client.post(reverse("avisos:leer", kwargs={"pk": aviso_post.pk}))
    assert resp_mark.status_code == 302
    aviso_post.refresh_from_db()
    primer_ts = aviso_post.leida_en
    assert primer_ts is not None

    # Repetición preserva timestamp y no altera el otro aviso
    client.post(reverse("avisos:leer", kwargs={"pk": aviso_post.pk}))
    aviso_post.refresh_from_db()
    aviso_acep.refresh_from_db()
    assert aviso_post.leida_en == primer_ts
    assert aviso_acep.leida_en is None
    assert client.get(reverse("avisos:contador")).json() == {"no_leidos": 1}


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_autorizacion_lector_admin_anonimo_y_tipos_ajenos_en_decisiones():
    solicitante = _crear_usuario("sol_auth", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_auth", grupos=["demo_operadora"])
    lector = _crear_usuario("lec_auth", grupos=["demo_lectura"])
    admin_cuentas = _crear_usuario("adm_auth", grupos=["local_administracion"])

    solicitud = _crear_solicitud(solicitante, 1201, estado=EstadoSolicitud.RECHAZADA)
    decision = _crear_decision(
        solicitud,
        operadora,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.RECHAZADA,
    )
    aviso_dec = Aviso.objects.create(
        destinatario=solicitante,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
        decision_id=decision.pk,
    )
    aviso_op = Aviso.objects.create(
        destinatario=operadora,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )

    # Anónimo y admin cuentas sin consulta -> 403
    for user in (None, admin_cuentas):
        c = Client()
        if user is not None:
            c.force_login(user)
        assert c.get(reverse("avisos:lista")).status_code == 403
        assert c.get(reverse("avisos:contador")).status_code == 403
        assert c.post(reverse("avisos:leer", kwargs={"pk": aviso_dec.pk})).status_code == 403

    # Lector -> 200 vacío, contador 0, 404 al intentar marcar aviso ajeno u operativo
    c_lec = Client()
    c_lec.force_login(lector)
    resp_lec = c_lec.get(reverse("avisos:lista"))
    assert resp_lec.status_code == 200
    assert "Decisión registrada:" not in resp_lec.content.decode("utf-8")
    assert c_lec.get(reverse("avisos:contador")).json() == {"no_leidos": 0}
    assert c_lec.post(reverse("avisos:leer", kwargs={"pk": aviso_dec.pk})).status_code == 404
    assert c_lec.post(reverse("avisos:leer", kwargs={"pk": aviso_op.pk})).status_code == 404

    # Solicitante no puede marcar aviso operativo de otra persona ni propio sin permiso
    c_sol = Client()
    c_sol.force_login(solicitante)
    assert c_sol.post(reverse("avisos:leer", kwargs={"pk": aviso_op.pk})).status_code == 404


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_csrf_get_no_muta_y_perdida_de_acceso_en_decisiones():
    solicitante = _crear_usuario("sol_csrf", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_csrf", grupos=["demo_operadora"])
    solicitud = _crear_solicitud(solicitante, 1301, estado=EstadoSolicitud.ACEPTADA)
    decision = _crear_decision(
        solicitud,
        operadora,
        estado_anterior=EstadoSolicitud.PRESENTADA,
        estado_resultante=EstadoSolicitud.ACEPTADA,
    )
    aviso = Aviso.objects.create(
        destinatario=solicitante,
        tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
        decision_id=decision.pk,
    )

    c_csrf = Client(enforce_csrf_checks=True)
    c_csrf.force_login(solicitante)
    assert c_csrf.post(reverse("avisos:leer", kwargs={"pk": aviso.pk})).status_code == 403

    c = Client()
    c.force_login(solicitante)
    assert c.get(reverse("avisos:leer", kwargs={"pk": aviso.pk})).status_code == 405
    aviso.refresh_from_db()
    assert aviso.leida_en is None

    # Pérdida de grupo revoca acceso inmediatamente
    solicitante.groups.remove(Group.objects.get(name="demo_solicitante"))
    assert c.get(reverse("avisos:lista")).status_code == 403
    assert c.get(reverse("avisos:contador")).status_code == 403
    assert c.post(reverse("avisos:leer", kwargs={"pk": aviso.pk})).status_code == 403


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_paginacion_y_filtros_en_decisiones():
    solicitante = _crear_usuario("sol_pag", grupos=["demo_solicitante"])
    operadora = _crear_usuario("op_pag_dec", grupos=["demo_operadora"])
    base_time = timezone.now()

    for i in range(1, 28):
        sol = _crear_solicitud(solicitante, 1400 + i, estado=EstadoSolicitud.ACEPTADA)
        dec = _crear_decision(
            sol,
            operadora,
            estado_anterior=EstadoSolicitud.PRESENTADA,
            estado_resultante=EstadoSolicitud.ACEPTADA,
        )
        aviso = Aviso.objects.create(
            destinatario=solicitante,
            tipo=TipoAviso.DECISION_SOLICITUD_GASTO,
            solicitud_id=sol.pk,
            decision_id=dec.pk,
            leida_en=base_time if i == 27 else None,
        )
        Aviso.objects.filter(pk=aviso.pk).update(creada_en=base_time + timedelta(minutes=i))

    c = Client()
    c.force_login(solicitante)
    resp_p1 = c.get(reverse("avisos:lista"), {"estado": "no_leidos"})
    assert resp_p1.status_code == 200
    assert "Página 1 de 2" in resp_p1.content.decode("utf-8")

    resp_p2 = c.get(reverse("avisos:lista"), {"estado": "no_leidos", "page": "2"})
    assert resp_p2.status_code == 200
    html_p2 = resp_p2.content.decode("utf-8")
    assert "solicitud #1401" in html_p2
    assert "Página 2 de 2" in html_p2
