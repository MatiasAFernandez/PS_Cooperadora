"""Archivos y cargas sintéticas para las pruebas de pago documentado."""

from django.core.files.uploadedfile import SimpleUploadedFile


def pdf_comprobante(nombre: str = "comprobante-bancario-sintetico.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"%PDF-1.7\nComprobante bancario sintetico\n%%EOF",
        "application/pdf",
    )


def pdf_constancia(nombre: str = "constancia-atp-sintetica.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"%PDF-1.7\nConstancia ATP sintetica\n%%EOF",
        "application/pdf",
    )


def pdf_falso(nombre: str = "comprobante-falso.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"no soy un pdf",
        "application/pdf",
    )


def jpg_comprobante(nombre: str = "comprobante-bancario.jpg") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"\xff\xd8\xff\xe0" + b"\x00" * 30,
        "image/jpeg",
    )


def png_comprobante(nombre: str = "comprobante-bancario.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 30,
        "image/png",
    )


def webp_invalido(nombre: str = "comprobante-bancario.webp") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        nombre,
        b"RIFF\x20\x00\x00\x00WEBPVP8 " + b"\x00" * 20,
        "image/webp",
    )
