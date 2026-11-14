"""Comando para reintentar idempotentemente el aviso de una solicitud de gasto."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from avisos.services import generar_aviso_nueva_solicitud
from gastos.models import SolicitudGasto


class Command(BaseCommand):
    """Reintenta la generación de avisos web para una solicitud de gasto."""

    help = "Reintenta idempotentemente la generación de avisos para una solicitud de gasto."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "solicitud_id",
            type=int,
            help="Número identificador de la solicitud de gasto.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        solicitud_id: int = options["solicitud_id"]
        if solicitud_id <= 0:
            raise CommandError("El identificador de solicitud debe ser un entero positivo.")

        try:
            creados = generar_aviso_nueva_solicitud(solicitud_id)
        except SolicitudGasto.DoesNotExist as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(
                f"Error al generar avisos para la solicitud #{solicitud_id}."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Avisos procesados para solicitud #{solicitud_id}: {creados} nuevos."
            )
        )
