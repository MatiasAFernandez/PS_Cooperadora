"""Referencias y eventos de lectura; cada circuito conserva sus transiciones."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

MODULOS = {"GASTO": "gastos", "FACTURACION": "facturacion"}


class ReferenciaCruzadaError(LookupError):
    """Una referencia no pertenece al circuito esperado por el consumidor."""


class TramiteNoDisponible(LookupError):
    """No existe una cabecera válida con su solicitud concreta y titular."""


@dataclass(frozen=True, slots=True)
class TramiteRef:
    circuito: str
    numero_publico: int

    def __post_init__(self):
        if self.circuito not in MODULOS:
            raise ValueError("Circuito desconocido.")
        if type(self.numero_publico) is not int or not 0 < self.numero_publico <= 2147483647:
            raise ValueError("Número público inválido.")

    def __str__(self) -> str:
        return f"{MODULOS[self.circuito]}:{self.numero_publico}"

    @classmethod
    def desde_texto(cls, texto: str) -> "TramiteRef":
        if not isinstance(texto, str) or not re.fullmatch(
            r"(gastos|facturacion):[1-9][0-9]{0,9}", texto
        ):
            raise ValueError("Referencia inválida.")
        modulo, numero = texto.split(":")
        circuito = next(c for c, m in MODULOS.items() if m == modulo)
        return cls(circuito, int(numero))


class EventoHistorialProtocol(Protocol):
    """Superficie que pueden consumir las futuras vistas comunes de Franco."""

    evento_id: int
    tramite_ref: str
    tipo_evento: str
    actor_id: str
    fecha_hora: datetime
    estado_resultante: str
    motivo_o_detalle: str


@dataclass(frozen=True, slots=True)
class EventoHistorialDTO:
    evento_id: int
    tramite_ref: str
    tipo_evento: str
    actor_id: str
    fecha_hora: datetime
    estado_resultante: str
    motivo_o_detalle: str
