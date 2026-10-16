"""Política mínima D05 para archivos sintéticos del incremento 2."""

import hashlib
from dataclasses import dataclass
from pathlib import PurePath

from django.conf import settings


class ArchivoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class ArchivoValidado:
    contenido: bytes
    formato: str
    nombre: str
    sha256: str


def _formato(contenido: bytes) -> str | None:
    if contenido.startswith(b"%PDF-"):
        return "application/pdf"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def validar_archivo(archivo: object) -> ArchivoValidado:
    maximo = settings.DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES
    if not isinstance(maximo, int) or maximo < 1:
        raise ValueError("DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES debe ser positivo.")
    nombre = str(getattr(archivo, "name", "")).replace("\\", "/")
    nombre = PurePath(nombre).name
    if not nombre or len(nombre) > 255 or any(ord(c) < 32 for c in nombre):
        raise ArchivoInvalido("Nombre de archivo inválido.")

    # Leer un byte adicional detecta el límite sin confiar en un Content-Length.
    contenido = archivo.read(maximo + 1)
    if not isinstance(contenido, bytes) or not contenido or len(contenido) > maximo:
        raise ArchivoInvalido("Archivo vacío o demasiado grande.")
    formato = _formato(contenido)
    extension = PurePath(nombre).suffix.lower()
    extensiones = {
        "application/pdf": {".pdf"},
        "image/jpeg": {".jpg", ".jpeg"},
        "image/png": {".png"},
    }
    if formato is None or extension not in extensiones[formato]:
        raise ArchivoInvalido("Tipo o extensión no permitidos.")
    declarado = getattr(archivo, "content_type", None)
    if declarado != formato:
        raise ArchivoInvalido("El tipo MIME declarado no coincide con el contenido.")
    return ArchivoValidado(contenido, formato, nombre, hashlib.sha256(contenido).hexdigest())
