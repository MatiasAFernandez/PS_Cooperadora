"""Comando para reintentar idempotentemente el aviso web de un evento de pago externo."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from avisos.services import generar_aviso_pago_externo
from gastos.models import EventoPagoExterno


class Command(BaseCommand):
    """Reintenta la generación del aviso web para un evento de pago externo sin enviar correo."""

    help = "Reintenta idempotentemente la generación del aviso web para un evento de pago externo."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "evento_pago_id",
            type=int,
            help="Número identificador del evento de pago externo.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        evento_pago_id: int = options["evento_pago_id"]
        if evento_pago_id <= 0:
            raise CommandError("El identificador de evento de pago debe ser un entero positivo.")

        try:
            creados = generar_aviso_pago_externo(evento_pago_id)
        except EventoPagoExterno.DoesNotExist as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(
                f"Error al generar el aviso para el evento de pago #{evento_pago_id}."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Aviso procesado para evento de pago #{evento_pago_id}: {creados} nuevos."
            )
        )
