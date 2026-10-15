"""Rutas HTTP protegidas para metadatos y contenido documental."""

from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_http_methods

from identidad.services import resolve_actor

from .policy import ArchivoInvalido
from .services import (
    AlmacenamientoNoDisponible,
    DocumentoNoVisible,
    almacenamiento,
    incorporar,
    listar,
    metadatos,
    obtener,
)


def _actor(request):
    actor = resolve_actor(request)
    if actor is None:
        raise PermissionDenied("Identidad no disponible.")
    return actor


@require_http_methods(["GET", "POST"])
def documentos_tramite(request, modulo: str, tramite_id: int):
    actor = _actor(request)
    referencia = f"{modulo}:{tramite_id}"
    try:
        if request.method == "GET":
            documentos = [metadatos(d) for d in listar(actor=actor, referencia=referencia)]
            respuesta = JsonResponse({"documentos": documentos})
        else:
            archivo = request.FILES.get("archivo")
            if archivo is None:
                return JsonResponse({"error": "Archivo requerido."}, status=400)
            documento = incorporar(
                actor=actor,
                referencia=referencia,
                archivo=archivo,
                tipo=request.POST.get("tipo"),
                procedencia=request.POST.get("procedencia"),
            )
            respuesta = JsonResponse(metadatos(documento), status=201)
    except DocumentoNoVisible as exc:
        raise Http404(str(exc)) from exc
    except ArchivoInvalido as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except AlmacenamientoNoDisponible:
        return JsonResponse({"error": "Almacenamiento no disponible."}, status=503)
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


@require_http_methods(["GET"])
def documento_detalle(request, documento_id: int):
    try:
        documento = obtener(
            actor=_actor(request), documento_id=documento_id, capacidad="documentos.ver_metadatos"
        )
    except DocumentoNoVisible as exc:
        raise Http404(str(exc)) from exc
    respuesta = JsonResponse(metadatos(documento))
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


@require_http_methods(["GET"])
def documento_archivo(request, documento_id: int):
    try:
        documento = obtener(
            actor=_actor(request), documento_id=documento_id, capacidad="documentos.descargar"
        )
    except DocumentoNoVisible as exc:
        raise Http404(str(exc)) from exc
    try:
        archivo = almacenamiento().open(documento.archivo, "rb")
    except OSError:
        return JsonResponse({"error": "Archivo no disponible."}, status=503)
    respuesta = FileResponse(
        archivo, as_attachment=True, filename=documento.nombre_original,
        content_type=documento.formato,
    )
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta
