"""Pruebas HTTP y de interfaz de servidor para la bandeja de avisos de Gastos."""

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
from gastos.models import EstadoSolicitud, SolicitudGasto
from identidad.models import CuentaLocal

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


def _crear_solicitud(solicitante, numero: int) -> SolicitudGasto:
    base = TramiteBase.objects.create(
        circuito=Circuito.GASTO,
        numero_publico=numero,
        solicitante_actor_id=str(solicitante.pk),
        centro_costo_codigo=None,
    )
    return SolicitudGasto.objects.create(
        pk=numero,
        tramite_base=base,
        concepto=f"Concepto privado confidencial #{numero}",
        monto_estimado=Decimal("98765.43"),
        unidad_requirente="Unidad secreta sintética",
        solicitante=solicitante,
        estado=EstadoSolicitud.PRESENTADA,
        version=0,
    )


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_autorizacion_y_exclusiones_en_lista_contador_y_marcado():
    op_valido = _crear_usuario(
        "op_valido",
        grupos=["demo_operadora"],
        con_cuenta_local=True,
    )
    aviso = Aviso.objects.create(
        destinatario=op_valido,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=501,
    )

    no_autorizados = [
        None,
        _crear_usuario(
            "local_pendiente",
            grupos=["demo_operadora"],
            con_cuenta_local=True,
            estado_local=CuentaLocal.Estado.PENDIENTE,
        ),
        _crear_usuario(
            "solo_lectura",
            grupos=["demo_lectura"],
            con_cuenta_local=True,
        ),
        _crear_usuario(
            "local_admin",
            grupos=["local_administracion"],
            con_cuenta_local=True,
        ),
        _crear_usuario(
            "staff_sin_cap",
            grupos=[],
            is_staff=True,
            is_superuser=True,
            con_cuenta_local=False,
        ),
    ]

    for usuario in no_autorizados:
        client = Client()
        if usuario is not None:
            client.force_login(usuario)

        resp_lista = client.get(reverse("avisos:lista"))
        assert resp_lista.status_code == 403

        resp_contador = client.get(reverse("avisos:contador"))
        assert resp_contador.status_code == 403

        resp_leer = client.post(reverse("avisos:leer", kwargs={"pk": aviso.pk}))
        assert resp_leer.status_code == 403

    aviso.refresh_from_db()
    assert aviso.leida_en is None


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=False, DEMO_IDENTITY_ENABLED=False)
def test_flags_identidad_deshabilitados_deniegan_acceso():
    op = _crear_usuario(
        "op_flags_off",
        grupos=["demo_operadora"],
        con_cuenta_local=True,
    )
    client = Client()
    client.force_login(op)

    assert client.get(reverse("avisos:lista")).status_code == 403
    assert client.get(reverse("avisos:contador")).status_code == 403


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_revocar_grupo_despues_de_iniciar_sesion_deja_sin_acceso():
    op = _crear_usuario(
        "op_revocable",
        grupos=["demo_operadora"],
        con_cuenta_local=True,
    )
    aviso = Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=502,
    )

    client = Client()
    client.force_login(op)
    assert client.get(reverse("avisos:lista")).status_code == 200
    assert client.get(reverse("avisos:contador")).status_code == 200

    grupo = Group.objects.get(name="demo_operadora")
    op.groups.remove(grupo)

    assert client.get(reverse("avisos:lista")).status_code == 403
    assert client.get(reverse("avisos:contador")).status_code == 403
    assert client.post(reverse("avisos:leer", kwargs={"pk": aviso.pk})).status_code == 403


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_aislamiento_entre_destinatarios_e_id_ajeno_404():
    op_a = _crear_usuario("op_a", grupos=["demo_operadora"], con_cuenta_local=True)
    op_b = _crear_usuario("op_b", grupos=["demo_operadora"], con_cuenta_local=False)

    aviso_a = Aviso.objects.create(
        destinatario=op_a,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=601,
    )
    aviso_b = Aviso.objects.create(
        destinatario=op_b,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=602,
    )

    client_a = Client()
    client_a.force_login(op_a)

    resp_lista = client_a.get(reverse("avisos:lista"))
    assert resp_lista.status_code == 200
    assert "no-store" in resp_lista.headers.get("Cache-Control", "")
    html = resp_lista.content.decode("utf-8")
    assert "Nueva solicitud de gasto #601" in html
    assert "Nueva solicitud de gasto #602" not in html

    resp_contador = client_a.get(reverse("avisos:contador"))
    assert resp_contador.status_code == 200
    assert "no-store" in resp_contador.headers.get("Cache-Control", "")
    assert resp_contador.json() == {"no_leidos": 1}

    resp_ajeno = client_a.post(reverse("avisos:leer", kwargs={"pk": aviso_b.pk}))
    assert resp_ajeno.status_code == 404

    aviso_b.refresh_from_db()
    assert aviso_b.leida_en is None
    assert aviso_a.leida_en is None


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_get_no_muta_csrf_403_y_marcado_doble_preserva_timestamp():
    op = _crear_usuario("op_mark", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitud = _crear_solicitud(_crear_usuario("autor_gasto", grupos=["demo_solicitante"]), 701)
    aviso = Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=solicitud.pk,
    )

    client_csrf = Client(enforce_csrf_checks=True)
    client_csrf.force_login(op)
    resp_sin_csrf = client_csrf.post(reverse("avisos:leer", kwargs={"pk": aviso.pk}))
    assert resp_sin_csrf.status_code == 403

    client = Client()
    client.force_login(op)

    # GET a bandeja y GET a /leer/ no mutan
    resp_lista = client.get(reverse("avisos:lista"))
    assert resp_lista.status_code == 200
    html_lista = resp_lista.content.decode("utf-8")
    assert "Concepto privado confidencial" not in html_lista
    assert "98765" not in html_lista
    assert "Unidad secreta" not in html_lista

    resp_get_leer = client.get(reverse("avisos:leer", kwargs={"pk": aviso.pk}))
    assert resp_get_leer.status_code == 405
    assert "no-store" in resp_get_leer.headers.get("Cache-Control", "")

    aviso.refresh_from_db()
    assert aviso.leida_en is None

    # Primer POST marca y redirige reconstruyendo estado/page sin aceptar next arbitrario
    resp_mark_1 = client.post(
        reverse("avisos:leer", kwargs={"pk": aviso.pk}),
        data={"estado": "no_leidos", "page": "2", "next": "https://evil.example/"},
    )
    assert resp_mark_1.status_code == 302
    assert "no-store" in resp_mark_1.headers.get("Cache-Control", "")
    assert resp_mark_1.headers["Location"] == f"{reverse('avisos:lista')}?estado=no_leidos&page=2"

    aviso.refresh_from_db()
    primer_timestamp = aviso.leida_en
    assert primer_timestamp is not None

    # Segundo POST es idempotente y preserva el timestamp original
    resp_mark_2 = client.post(
        reverse("avisos:leer", kwargs={"pk": aviso.pk}),
        data={"estado": "todos", "page": "²"},
        follow=True,
    )
    assert resp_mark_2.status_code == 200
    aviso.refresh_from_db()
    assert aviso.leida_en == primer_timestamp
    assert "ya estaba marcado como leído" in resp_mark_2.content.decode("utf-8")


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_filtro_invalido_400_y_paginacion_con_filtro():
    op = _crear_usuario("op_pag", grupos=["demo_operadora"], con_cuenta_local=True)
    base_time = timezone.now()
    for i in range(1, 29):
        aviso = Aviso.objects.create(
            destinatario=op,
            tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
            solicitud_id=800 + i,
            leida_en=base_time if i == 28 else None,
        )
        Aviso.objects.filter(pk=aviso.pk).update(creada_en=base_time + timedelta(minutes=i))

    client = Client()
    client.force_login(op)

    resp_invalido = client.get(reverse("avisos:lista"), {"estado": "cualquiera"})
    assert resp_invalido.status_code == 400
    assert "no-store" in resp_invalido.headers.get("Cache-Control", "")
    assert "Nueva solicitud de gasto #" not in resp_invalido.content.decode("utf-8")

    # 27 no leídos -> página 1 tiene 25, página 2 tiene 2; #828 (leído) queda excluido
    resp_p1 = client.get(reverse("avisos:lista"), {"estado": "no_leidos"})
    assert resp_p1.status_code == 200
    html_p1 = resp_p1.content.decode("utf-8")
    assert "Nueva solicitud de gasto #827" in html_p1
    assert "Nueva solicitud de gasto #828" not in html_p1
    assert "estado=no_leidos&amp;page=2" in html_p1

    resp_p2 = client.get(reverse("avisos:lista"), {"estado": "no_leidos", "page": "2"})
    assert resp_p2.status_code == 200
    html_p2 = resp_p2.content.decode("utf-8")
    assert "Nueva solicitud de gasto #802" in html_p2
    assert "Nueva solicitud de gasto #801" in html_p2
    assert "Página 2 de 2" in html_p2


@pytest.mark.django_db
@override_settings(LOCAL_IDENTITY_ENABLED=True, DEMO_IDENTITY_ENABLED=True)
def test_navegacion_y_script_condicional_en_plantillas():
    op = _crear_usuario("op_nav", grupos=["demo_operadora"], con_cuenta_local=True)
    solicitante = _crear_usuario("sol_nav", grupos=["demo_solicitante"], con_cuenta_local=True)
    Aviso.objects.create(
        destinatario=op,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
        solicitud_id=901,
    )

    client_op = Client()
    client_op.force_login(op)
    resp_op = client_op.get(reverse("avisos:lista"))
    assert resp_op.status_code == 200
    html_op = resp_op.content.decode("utf-8")
    assert reverse("avisos:lista") in html_op
    assert f'data-avisos-contador-url="{reverse("avisos:contador")}"' in html_op
    assert 'aria-current="page"' in html_op
    assert "avisos/contador.js" in html_op
    assert reverse("gastos:detalle", kwargs={"pk": 901}) in html_op
    assert reverse("gastos:lista") in html_op

    client_sol = Client()
    client_sol.force_login(solicitante)
    resp_sol = client_sol.get(reverse("gastos:lista"))
    assert resp_sol.status_code == 200
    html_sol = resp_sol.content.decode("utf-8")
    assert reverse("avisos:lista") not in html_sol
    assert "data-avisos-contador-url" not in html_sol
    assert "avisos/contador.js" not in html_sol
