from django.urls import path

from gastos.views import ReporteCuatrimestralGastosView

from .views import CampoView, ConfiguracionView, ReporteFacturacionView

app_name = "gestion"
urlpatterns = [
    path("configuracion/<str:circuito>/", ConfiguracionView.as_view(), name="configuracion"),
    path("configuracion/<str:circuito>/nuevo/", CampoView.as_view(), name="campo_nuevo"),
    path("configuracion/<str:circuito>/campos/<str:clave>/", CampoView.as_view(), name="campo"),
    path("reportes/gastos/", ReporteCuatrimestralGastosView.as_view(), name="reporte_gastos"),
    path("reportes/facturacion/", ReporteFacturacionView.as_view(), name="reporte_facturacion"),
]
