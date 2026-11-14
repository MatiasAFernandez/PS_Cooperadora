"""Comando para reintentar idempotentemente el aviso web de una decisión de gasto."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from avisos.services import generar_aviso_decision_gasto
from gastos.models import DecisionGasto


class Command(BaseCommand):
    """Reintenta la generación del aviso web para una decisión de gasto sin enviar correo."""

    help = "Reintenta idempotentemente la generación del aviso web para una decisión de gasto."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "decision_id",
            type=int,
            help="Número identificador de la decisión de gasto.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        decision_id: int = options["decision_id"]
        if decision_id <= 0:
            raise CommandError("El identificador de decisión debe ser un entero positivo.")

        try:
            creados = generar_aviso_decision_gasto(decision_id)
        except DecisionGasto.DoesNotExist as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(
                f"Error al generar el aviso para la decisión #{decision_id}."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Aviso procesado para decisión #{decision_id}: {creados} nuevos."
            )
        )
