"""Rutas de solicitudes de facturación."""

from django.urls import path

from . import views
from .exportacion import ExportarSolicitudPDFView
from .views_cobros import RegistrarCobroView, VerificarCobroView
from .views_comprobantes import RegistrarComprobanteView
from .views_seguimiento import ActualizarRespaldoView, ResolverTramiteView

app_name = "facturacion"
urlpatterns = [
    path("<int:numero>/exportar.pdf", ExportarSolicitudPDFView.as_view(), name="exportar_pdf"),
    path("<int:numero>/resolver/", ResolverTramiteView.as_view(), name="resolver"),
    path("<int:numero>/respaldos/<str:clase>/<int:objeto_id>/", ActualizarRespaldoView.as_view(),
         name="actualizar_respaldo"),
    path("<int:numero>/cobros/nuevo/", RegistrarCobroView.as_view(), name="registrar_cobro"),
    path("<int:numero>/cobros/<int:cobro_id>/verificar/", VerificarCobroView.as_view(),
         name="verificar_cobro"),
    path("", views.ListaSolicitudesView.as_view(), name="lista"),
    path("nueva/", views.PresentarSolicitudView.as_view(), name="presentar"),
    path("<int:numero>/", views.DetalleSolicitudView.as_view(), name="detalle"),
    path("<int:numero>/observar/", views.ObservarSolicitudView.as_view(), name="observar"),
    path("<int:numero>/corregir/", views.CorregirSolicitudView.as_view(), name="corregir"),
    path("<int:numero>/comprobantes/nuevo/", RegistrarComprobanteView.as_view(),
         name="registrar_comprobante"),
]
