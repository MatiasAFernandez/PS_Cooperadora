"""Rutas HTTP protegidas para metadatos y contenido documental."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from identidad.services import has_capability, resolve_actor

from .forms import RevisionDocumentoForm
from .policy import ArchivoInvalido
from .revision import ConflictoRevision, consultar_revision, revisar, ultima_revision
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
            actor=_actor(request), documento_id=documento_id,
            capacidad="documentos.consultar_metadatos"
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
            actor=_actor(request), documento_id=documento_id,
            capacidad="documentos.recuperar_contenido"
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


@require_http_methods(["GET", "POST"])
def documento_revision(request, documento_id: int):
    actor = _actor(request)
    try:
        documento, revisiones = consultar_revision(actor=actor, documento_id=documento_id)
        actual = ultima_revision(documento)
        vigente = not documento.__class__.objects.filter(reemplaza=documento).exists()
        terminal = (
            documento.tramite_base.circuito == "FACTURACION"
            and documento.tramite_base.solicitud_facturacion.estado in {"CERRADA", "ANULADA"}
        )
        puede_revisar = has_capability(actor, "documentos.revisar") and vigente and not terminal
        form = RevisionDocumentoForm(initial={"revision_esperada": actual.pk if actual else 0})
        status = 200
        if request.method == "POST":
            if not has_capability(actor, "documentos.revisar"):
                raise PermissionDenied("No tenés permiso para revisar documentos.")
            form = RevisionDocumentoForm(request.POST)
            status = 400
            if form.is_valid():
                try:
                    revisar(actor=actor, documento_id=documento_id, **form.cleaned_data)
                except ValidationError as exc:
                    form.add_error(None, exc)
                except ConflictoRevision as exc:
                    form.add_error(None, str(exc))
                    status = 409
                else:
                    return redirect("documentos:revision", documento_id=documento_id)
        respuesta = render(request, "documentos/revision.html", {
            "actor": actor, "documento": documento, "actual": actual, "vigente": vigente,
            "puede_revisar": puede_revisar, "form": form,
            "puede_descargar": has_capability(actor, "documentos.recuperar_contenido"),
            "historial": [r.como_historial() for r in revisiones],
        }, status=status)
    except DocumentoNoVisible as exc:
        raise Http404(str(exc)) from exc
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta
