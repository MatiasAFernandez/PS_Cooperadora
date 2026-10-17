"""Rutas de solicitudes de facturación."""

from django.urls import path

from . import views

app_name = "facturacion"
urlpatterns = [
    path("", views.ListaSolicitudesView.as_view(), name="lista"),
    path("nueva/", views.PresentarSolicitudView.as_view(), name="presentar"),
    path("<int:numero>/", views.DetalleSolicitudView.as_view(), name="detalle"),
    path("<int:numero>/observar/", views.ObservarSolicitudView.as_view(), name="observar"),
    path("<int:numero>/corregir/", views.CorregirSolicitudView.as_view(), name="corregir"),
]
