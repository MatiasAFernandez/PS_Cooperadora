"""Rutas URL del módulo de gastos."""

from django.urls import path

from gastos.views import (
    CentroCostoToggleActivoView,
    GestionCatalogosView,
    ReporteCuatrimestralGastosView,
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
        "reportes/cuatrimestral/",
        ReporteCuatrimestralGastosView.as_view(),
        name="reporte_cuatrimestral",
    ),
    path(
        "catalogos/",
        GestionCatalogosView.as_view(),
    ),
    path(
        "administracion/catalogos/",
        GestionCatalogosView.as_view(),
        name="gestion_catalogos",
    ),
    path(
        "administracion/centros-costo/<int:pk>/toggle/",
        CentroCostoToggleActivoView.as_view(),
        name="centro_costo_toggle",
    ),
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
