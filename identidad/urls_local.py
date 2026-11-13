"""Configuración de rutas HTTP para el espacio de nombres 'cuentas'."""

from django.urls import path

from identidad import views_local, views_usuarios

app_name = "cuentas"

urlpatterns = [
    # Rutas estáticas antes de dinámicas para evitar colisiones
    path("", views_local.InicioView.as_view(), name="inicio"),
    path("acceso/", views_local.LocalLoginView.as_view(), name="login"),
    path("salida/", views_local.LocalLogoutView.as_view(), name="logout"),
    path("registro/", views_local.RegistroView.as_view(), name="registro"),
    path("registro/recibido/", views_local.RecibidoView.as_view(), name="recibido"),
    path("verificar/", views_local.VerificarView.as_view(), name="verificar"),
    path("reenviar/", views_local.ReenviarView.as_view(), name="reenviar"),
    path("estado/", views_local.EstadoView.as_view(), name="estado"),
    path("administracion/altas/", views_local.AltasView.as_view(), name="altas"),
    path(
        "administracion/usuarios/",
        views_usuarios.UsuariosView.as_view(),
        name="usuarios",
    ),
    path(
        "administracion/usuarios/<int:pk>/",
        views_usuarios.UsuarioDetalleView.as_view(),
        name="usuario_detalle",
    ),
    path(
        "administracion/usuarios/<int:pk>/editar/",
        views_usuarios.UsuarioEditarView.as_view(),
        name="usuario_editar",
    ),
    path(
        "administracion/usuarios/<int:pk>/actividad/",
        views_usuarios.UsuarioActividadView.as_view(),
        name="usuario_actividad",
    ),
    path(
        "administracion/usuarios/<int:pk>/perfiles/",
        views_usuarios.UsuarioPerfilesView.as_view(),
        name="usuario_perfiles",
    ),
    path("recuperar/", views_local.LocalPasswordResetView.as_view(), name="recuperar"),
    path(
        "recuperar/enviado/",
        views_local.RecuperarEnviadoView.as_view(),
        name="recuperar_enviado",
    ),
    path(
        "recuperar/completa/",
        views_local.ResetCompletoView.as_view(),
        name="reset_completo",
    ),
    path(
        "recuperar/<uidb64>/<token>/",
        views_local.LocalPasswordResetConfirmView.as_view(),
        name="reset_confirm",
    ),
    path("clave/", views_local.LocalPasswordChangeView.as_view(), name="cambiar_clave"),
    path(
        "clave/cambiada/",
        views_local.ClaveCambiadaView.as_view(),
        name="clave_cambiada",
    ),
]
