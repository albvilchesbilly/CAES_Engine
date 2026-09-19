"""Serializacion del modelo canonico a JSON puro: lo que `json.dumps` acepta **sin** `default=`.

Reglas (C1 de `ADR-004`, §6.1 de `docs/03`):

- `Decimal` y `date` viajan **como cadena**, siempre. Es lo que hace reproducible el hash del log (S3.1,
  C2) y lo que evita que un consumidor reintroduzca coma flotante en el ahorro.
- Orden estable: los campos de una dataclass salen en su orden de declaracion; las claves de un diccionario,
  ordenadas. Dos ejecuciones del mismo dato producen exactamente el mismo `dict`.
- Un `float` es un defecto, no un valor a convertir: se rechaza con `ErrorModelo`. Lo mismo cualquier tipo
  que no sepamos serializar; nada se convierte "a lo bruto" con `str()`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext

from engine.modelo.entidades import ErrorModelo

#: Precision con la que se normaliza un `Decimal` a texto (la misma que `engine.calculo`).
PRECISION_DECIMAL = 34


def decimal_a_texto(valor: Decimal) -> str:
    """Texto canonico de un `Decimal`: sin ceros de cola ni exponente. Un no finito sale tal cual.

    `NaN` e `Infinity` no se "arreglan" aqui: se dejan pasar como texto para que el validador los rechace
    con la ruta del campo (formato `decimal-string`), en vez de morir en la serializacion sin decir donde.
    """
    if not valor.is_finite():
        return str(valor)
    if valor == 0:
        return "0"
    with localcontext() as ctx:
        ctx.prec = PRECISION_DECIMAL
        return format(valor.normalize(), "f")


def _valor(valor: object, ruta: str) -> object:
    if valor is None:
        return None
    if isinstance(valor, bool | str):
        return valor
    if isinstance(valor, Decimal):
        return decimal_a_texto(valor)
    if isinstance(valor, float):
        raise ErrorModelo(f"{ruta}: el modelo canonico no admite coma flotante (usa Decimal)")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if is_dataclass(valor) and not isinstance(valor, type):
        return {
            campo.name: _valor(getattr(valor, campo.name), f"{ruta}.{campo.name}" if ruta else campo.name)
            for campo in fields(valor)
        }
    if isinstance(valor, Mapping):
        return {
            str(clave): _valor(valor[clave], f"{ruta}.{clave}" if ruta else str(clave))
            for clave in sorted(valor, key=str)
        }
    if isinstance(valor, list | tuple | set | frozenset):
        elementos = sorted(valor, key=str) if isinstance(valor, set | frozenset) else valor
        return [_valor(v, f"{ruta}[{i}]") for i, v in enumerate(elementos)]
    raise ErrorModelo(f"{ruta}: tipo no serializable en el modelo canonico ({type(valor).__name__})")


def a_dict(obj: object) -> dict[str, object]:
    """Entidad del modelo canonico como `dict` JSON-compatible (ver cabecera del modulo)."""
    if not (is_dataclass(obj) and not isinstance(obj, type)):
        raise ErrorModelo(f"a_dict espera una entidad del modelo canonico, no {type(obj).__name__}")
    salida = _valor(obj, "")
    if not isinstance(salida, dict):  # pragma: no cover - una dataclass siempre serializa a dict
        raise ErrorModelo("la serializacion de una entidad debe producir un objeto")
    return salida


__all__ = ["PRECISION_DECIMAL", "a_dict", "decimal_a_texto"]
