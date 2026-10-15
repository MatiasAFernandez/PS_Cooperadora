from django.urls import path

from .views import documento_archivo, documento_detalle, documentos_tramite

app_name = "documentos"

urlpatterns = [
    path("<str:modulo>/<int:tramite_id>/", documentos_tramite, name="tramite"),
    path("<int:documento_id>/", documento_detalle, name="detalle"),
    path("<int:documento_id>/archivo/", documento_archivo, name="archivo"),
]
