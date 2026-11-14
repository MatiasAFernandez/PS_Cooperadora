"""Rutas HTTP para la bandeja de avisos web internos."""

from django.urls import path

from avisos import views

app_name = "avisos"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("contador/", views.contador, name="contador"),
    path("<int:pk>/leer/", views.leer, name="leer"),
]
