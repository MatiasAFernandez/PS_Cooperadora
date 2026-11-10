"""URL configuration for the Cooperadora project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("gestion/", include("gestion.urls")),
    path("facturacion/", include("facturacion.urls")),
    path("admin/", admin.site.urls),
    path("gastos/", include("gastos.urls")),
    path("documentos/", include("documentos.urls")),
    path("demo/", include("identidad.urls")),
]
