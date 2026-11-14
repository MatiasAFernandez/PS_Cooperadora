"""Comando operativo para consultar, reintentar y conciliar correos de avisos de Gastos."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from avisos.correo import (
    ConciliacionError,
    conciliar_intencion_correo,
    enviar_correos_nueva_solicitud,
)
from avisos.models import IntencionCorreo, TipoAviso
from gastos.models import SolicitudGasto


class Command(BaseCommand):
    """Consulta, reintenta o concilia intenciones de correo para una solicitud de gasto."""

    help = (
        "Consulta, reintenta pendientes/fallidos o concilia intenciones de correo "
        "para una solicitud de gasto."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "solicitud_id",
            type=int,
            help="Número identificador de la solicitud de gasto.",
        )
        parser.add_argument(
            "--reintentar",
            action="store_true",
            help="Reintenta únicamente intenciones en estado pendiente o fallido.",
        )
        parser.add_argument(
            "--conciliar-envio",
            type=int,
            dest="conciliar_intencion_id",
            help="ID de la intención incierta o en proceso a conciliar.",
        )
        parser.add_argument(
            "--resultado",
            choices=["aceptado", "reintentar"],
            help="Resultado de conciliación: 'aceptado' o 'reintentar'.",
        )
        parser.add_argument(
            "--confirmar-riesgo-duplicado",
            action="store_true",
            help=(
                "Confirma explícitamente el riesgo de duplicado al conciliar como "
                "'reintentar'."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        solicitud_id: int = options["solicitud_id"]
        if solicitud_id <= 0:
            raise CommandError("El identificador de solicitud debe ser un entero positivo.")

        if not SolicitudGasto.objects.filter(pk=solicitud_id).exists():
            raise CommandError(f"No existe la solicitud de gasto #{solicitud_id}.")

        reintentar: bool = options["reintentar"]
        conciliar_id: int | None = options["conciliar_intencion_id"]
        resultado: str | None = options["resultado"]
        confirmar_riesgo: bool = options["confirmar_riesgo_duplicado"]

        if reintentar and conciliar_id is not None:
            raise CommandError(
                "No se pueden combinar --reintentar y --conciliar-envio en la misma ejecución."
            )

        if conciliar_id is not None:
            if not resultado:
                raise CommandError(
                    "Debe indicar --resultado aceptado|reintentar al usar --conciliar-envio."
                )
            try:
                intencion = conciliar_intencion_correo(
                    solicitud_id,
                    conciliar_id,
                    resultado=resultado,
                    confirmar_riesgo_duplicado=confirmar_riesgo,
                )
            except ConciliacionError as exc:
                raise CommandError(str(exc)) from exc

            self.stdout.write(
                self.style.SUCCESS(
                    f"Intención #{intencion.pk} conciliada: estado={intencion.estado} "
                    f"codigo={intencion.codigo_resultado}"
                )
            )
            return

        if resultado is not None or confirmar_riesgo:
            raise CommandError(
                "--resultado y --confirmar-riesgo-duplicado requieren --conciliar-envio."
            )

        if reintentar:
            if not getattr(settings, "AVISOS_EMAIL_ENABLED", False):
                raise CommandError(
                    "El canal de correo de avisos está deshabilitado (AVISOS_EMAIL_ENABLED=False)."
                )
            resultados = enviar_correos_nueva_solicitud(
                solicitud_id,
                incluir_fallidos=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reintentos ejecutados para solicitud #{solicitud_id}: "
                    f"{len(resultados)} procesados."
                )
            )
            for item in resultados:
                self.stdout.write(
                    f"  intencion={item.intencion_id} estado={item.estado} codigo={item.codigo}"
                )
            return

        # Consulta por defecto (solo lectura, sin direcciones ni envíos)
        intenciones = list(
            IntencionCorreo.objects.filter(
                aviso__solicitud_id=solicitud_id,
                aviso__tipo=TipoAviso.NUEVA_SOLICITUD_GASTO,
            )
            .select_related("aviso")
            .order_by("pk")
        )
        if not intenciones:
            self.stdout.write(
                f"Solicitud #{solicitud_id}: sin intenciones de correo registradas."
            )
            return

        self.stdout.write(
            f"Intenciones de correo para solicitud #{solicitud_id} ({len(intenciones)}):"
        )
        for intencion in intenciones:
            self.stdout.write(
                f"  intencion={intencion.pk} aviso={intencion.aviso_id} "
                f"destinatario={intencion.aviso.destinatario_id} "
                f"estado={intencion.estado} intentos={intencion.intentos} "
                f"codigo={intencion.codigo_resultado or '-'}"
            )
