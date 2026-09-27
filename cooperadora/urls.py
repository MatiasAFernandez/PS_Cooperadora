"""URL configuration for the Cooperadora project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("gastos/", include("gastos.urls")),
]
