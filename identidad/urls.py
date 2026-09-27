"""Rutas de acceso de la identidad sintética."""

from django.urls import path

from identidad.views import DemoHomeView, DemoLoginView, DemoLogoutView

app_name = "identidad"

urlpatterns = [
    path("", DemoHomeView.as_view(), name="inicio"),
    path("acceso/", DemoLoginView.as_view(), name="login"),
    path("salida/", DemoLogoutView.as_view(), name="logout"),
]
