"""Pruebas UX/UI de Cuentas y Usuarios locales (Incremento 9A)."""

import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from identidad.models import CuentaLocal

pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()


def _crear_cuenta(
    username: str,
    nombre: str,
    *,
    estado: str = CuentaLocal.Estado.APROBADA,
    verificado: bool = True,
    activo: bool = True,
    grupos: list[str] | None = None,
    cuit_cuil: str = "",
) -> CuentaLocal:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.invalid",
        password="PasswordSintetica9A!",
        is_active=activo,
    )
    for nombre_grupo in grupos or []:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user.groups.add(grupo)
    return CuentaLocal.objects.create(
        user=user,
        email=user.email,
        nombre_completo=nombre,
        estado=estado,
        email_verificado_en=timezone.now() if verificado else None,
        cuit_cuil=cuit_cuil,
    )


def test_listado_usuarios_tabla_densa_banner_condicional_y_vacio(settings):
    settings.LOCAL_IDENTITY_ENABLED = True
    admin = _crear_cuenta(
        "admin_u9a",
        "Admin Local 9A",
        grupos=["local_administracion"],
    )
    cliente = Client()
    cliente.force_login(admin.user)
    url = reverse("cuentas:usuarios")

    # Sin pendientes: no aparece banner condicional ni botón duplicado en cabecera.
    resp_sin_pend = cliente.get(url)
    assert resp_sin_pend.status_code == 200
    html0 = resp_sin_pend.content.decode()
    assert '<table class="usuarios-table">' in html0
    assert "usuarios-altas-banner" not in html0
    assert "Quitar filtros" not in html0
    assert "Página 1 de 1" not in html0
    assert ">Aprobada<" in html0
    assert ">APROBADA<" not in html0

    # Al existir una solicitud pendiente: aparece banner condicional con contador.
    pendiente = _crear_cuenta(
        "pend_u9a",
        "Solicitante Pendiente 9A",
        estado=CuentaLocal.Estado.PENDIENTE,
        verificado=False,
        cuit_cuil="30712345671",
    )
    html1 = cliente.get(url).content.decode()
    assert "usuarios-altas-banner" in html1
    assert '<span class="usuarios-altas-count">1</span>' in html1
    assert ">Pendiente<" in html1
    assert ">Sin verificar<" in html1

    # Filtro sin resultados muestra estado vacío claro + botón Quitar filtros.
    html_vacio = cliente.get(url, {"q": "sin-coincidencias-9a"}).content.decode()
    assert "No hay cuentas para mostrar" in html_vacio
    assert "Quitar filtros" in html_vacio

    # Ficha formatea CUIT y actividad no expone jerga técnica User.is_active.
    url_ficha = reverse("cuentas:usuario_detalle", args=[pendiente.pk])
    html_ficha = cliente.get(url_ficha).content.decode()
    assert "30-71234567-1" in html_ficha
    assert 'class="page-back page-back--arrow"' in html_ficha

    pendiente.user.is_active = False
    pendiente.user.save(update_fields=["is_active"])
    html_act = cliente.get(
        reverse("cuentas:usuario_actividad", args=[pendiente.pk])
    ).content.decode()
    assert "User.is_active" not in html_act
    assert "habilitará nuevamente el acceso de la cuenta al sistema" in html_act


def test_voseo_en_vistas_locales_y_css_cuentas_usuarios_limpios(settings):
    settings.LOCAL_IDENTITY_ENABLED = True
    cliente = Client()
    html_rec = cliente.get(reverse("cuentas:recuperar")).content.decode()
    assert "Ingresá tu correo electrónico" in html_rec
    assert "Ingrese su correo" not in html_rec

    html_reenv = cliente.get(reverse("cuentas:reenviar")).content.decode()
    assert "Ingresá tu correo electrónico" in html_reenv

    for rel in ("identidad/cuentas.css", "identidad/usuarios.css", "identidad/inicio.css"):
        ruta = Path(settings.BASE_DIR) / "static" / rel
        contenido = re.sub(r"/\*.*?\*/", "", ruta.read_text(encoding="utf-8"), flags=re.S)
        assert "!important" not in contenido, rel
        assert "--ref-" not in contenido, rel
