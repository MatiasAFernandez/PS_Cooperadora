"""Pruebas UX/UI de Avisos (Incremento 9A): pestañas A2, jerarquía de acciones y CSS limpio."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from avisos.models import Aviso, TipoAviso
from comunes.models import Circuito, TramiteBase
from gastos.models import SolicitudGasto
from identidad.models import CuentaLocal

pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()


def test_avisos_pestanas_a2_jerarquia_y_sin_boton_duplicado(settings):
    settings.LOCAL_IDENTITY_ENABLED = True
    user = User.objects.create_user(
        username="op_avisos_9a",
        email="op_avisos_9a@example.invalid",
        password="PasswordSintetica9A!",
        is_active=True,
    )
    grupo, _ = Group.objects.get_or_create(name="demo_operadora")
    user.groups.add(grupo)
    CuentaLocal.objects.create(
        user=user,
        email=user.email,
        nombre_completo="Operadora Avisos 9A",
        estado=CuentaLocal.Estado.APROBADA,
        email_verificado_en=timezone.now(),
    )
    solicitante = User.objects.create_user(
        username="sol_avisos_9a",
        email="sol_avisos_9a@example.invalid",
        password="PasswordSintetica9A!",
        is_active=True,
    )
    base = TramiteBase.objects.create(
        circuito=Circuito.GASTO,
        numero_publico=9001,
        solicitante_actor_id=str(solicitante.pk),
    )
    solicitud = SolicitudGasto.objects.create(
        id=9001,
        tramite_base=base,
        solicitante=solicitante,
        concepto="Compra sintética 9A",
        monto_estimado=Decimal("1500.00"),
        unidad_requirente="GISTAQ",
    )
    aviso = Aviso.objects.create(
        destinatario=user,
        solicitud_id=solicitud.pk,
        tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
    )

    cliente = Client()
    cliente.force_login(user)
    resp = cliente.get(reverse("avisos:lista"))
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "ui-tabs-segmented" in html
    assert "Ir al listado de gastos" not in html
    # A2 estricto: contador únicamente en No leídos, nunca en Todos.
    assert 'estado=todos"' in html
    todos_anchor = html.split("?estado=todos", 1)[1].split("</a>", 1)[0]
    assert "avisos-tab-count" not in todos_anchor
    assert '<span class="avisos-tab-count">1</span>' in html
    # Jerarquía invertida: Ver solicitud secundario limpio y Marcar como leído ghost.
    assert 'class="btn btn-secondary btn-row"' in html
    assert 'class="btn btn-ghost btn-row">Marcar como leído</button>' in html
    assert 'class="status-pill status-info">No leído</span>' in html

    # Marcar como leído quita el contador de No leídos y usa mensajes_flash.
    resp_leer = cliente.post(
        reverse("avisos:leer", args=[aviso.pk]),
        {"estado": "todos", "page": "1"},
        follow=True,
    )
    assert resp_leer.status_code == 200
    html_leido = resp_leer.content.decode()
    assert "avisos-tab-count" not in html_leido
    assert 'class="status-pill status-neutral">Leído</span>' in html_leido


def test_css_avisos_sin_important_ni_tokens_legacy():
    ruta = Path(settings.BASE_DIR) / "static" / "avisos" / "avisos.css"
    contenido = re.sub(r"/\*.*?\*/", "", ruta.read_text(encoding="utf-8"), flags=re.S)
    assert "!important" not in contenido
    assert "--ref-" not in contenido
