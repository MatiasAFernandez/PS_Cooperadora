"""Archivos ficticios para probar el almacenamiento sin datos institucionales."""

from django.core.files.uploadedfile import SimpleUploadedFile


def archivo_pdf():
    return SimpleUploadedFile(
        "ejemplo.pdf", b"%PDF-1.7\nEjemplo ficticio\n%%EOF", "application/pdf"
    )
