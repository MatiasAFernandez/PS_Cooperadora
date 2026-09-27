"""Rutas URL del módulo de gastos."""

from django.urls import path

from gastos.views import (
    SolicitudGastoCreateView,
    SolicitudGastoDecidirView,
    SolicitudGastoDetailView,
    SolicitudGastoListView,
)

app_name = "gastos"

urlpatterns = [
    path("", SolicitudGastoListView.as_view(), name="lista"),
    path("presentar/", SolicitudGastoCreateView.as_view(), name="presentar"),
    path("<int:pk>/", SolicitudGastoDetailView.as_view(), name="detalle"),
    path("<int:pk>/decidir/", SolicitudGastoDecidirView.as_view(), name="decidir"),
]
