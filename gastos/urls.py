"""Rutas URL del módulo de gastos."""

from django.urls import path

from gastos.views import (
    SolicitudGastoCreateView,
    SolicitudGastoDatosTransferenciaView,
    SolicitudGastoDecidirView,
    SolicitudGastoDetailView,
    SolicitudGastoDocumentosView,
    SolicitudGastoListView,
    SolicitudGastoPagoView,
)

app_name = "gastos"

urlpatterns = [
    path("", SolicitudGastoListView.as_view(), name="lista"),
    path("presentar/", SolicitudGastoCreateView.as_view(), name="presentar"),
    path(
        "<int:pk>/datos-transferencia/",
        SolicitudGastoDatosTransferenciaView.as_view(),
        name="datos-transferencia",
    ),
    path("<int:pk>/", SolicitudGastoDetailView.as_view(), name="detalle"),
    path(
        "<int:pk>/documentos/",
        SolicitudGastoDocumentosView.as_view(),
        name="documentos",
    ),
    path("<int:pk>/decidir/", SolicitudGastoDecidirView.as_view(), name="decidir"),
    path("<int:pk>/pagar/", SolicitudGastoPagoView.as_view(), name="pagar"),
]
