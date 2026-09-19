"""JSON canonico, codificacion tipada y hash encadenado del log (docs/03 §6.1, ADR-004 C2).

Tres piezas, en este orden de dependencia:

1. **`json_canonico(obj)`** — la unica forma en que este paquete convierte datos en texto: claves ordenadas,
   UTF-8 (`ensure_ascii=False`), sin espacios, `Decimal` y `date`/`datetime` como cadena. Dos objetos
   equivalentes dan la misma cadena y un cambio de orden de claves no la cambia: sin eso el hash no es
   reproducible y el log no demuestra nada.
2. **`codificar` / `decodificar`** — el payload de un evento viaja a JSONL y vuelve. JSON no tiene `Decimal`
   ni `date`, asi que lo que entra en un payload se guarda **etiquetado** (`{"$decimal": "305829.6"}`,
   `{"$fecha": "2026-03-02"}`, `{"$instante": "2026-09-19T08:00:00Z"}`). Es lo que permite que el replay
   trabaje con el log y solo con el log: un `Decimal` que sale del log sigue siendo `Decimal`.
3. **`calcular_hash(evento_sin_hash, hash_previo)`** = `sha256(hash_previo + json_canonico(evento))`.

Decisiones de este modulo:

- **`float` no entra**. Ni en un payload ni en el hash: una magnitud es `Decimal` y la telemetria no es
  materia de log (`CLAUDE.md` §2). Un `float` es `ErrorEvento`, no una conversion silenciosa.
- **Instantes en UTC con `Z`**. `ocurrido_en` se normaliza a `timezone.utc` y se escribe
  `2026-09-19T08:00:00+00:00` como `2026-09-19T08:00:00Z` (el formato del ejemplo de `docs/03` §6.1). Se lee
  cualquiera de los dos. Un `datetime` sin zona es `ErrorEvento`: nunca `datetime.now()` a secas
  (`ADR-004` C2, `ADR-003` H-08).
- **`Decimal` sin normalizar**: `format(valor, "f")`, sin exponente y conservando la escala, para que
  `decodificar(codificar(d))` devuelva exactamente `d`.
- Un tipo que no sepamos serializar es un error ruidoso, no un `str(...)` de cortesia.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum

#: Etiquetas de los tipos que JSON no tiene. Un dict con **exactamente** una de estas claves es un valor
#: tipado; cualquier otro dict es un dict.
CLAVE_DECIMAL = "$decimal"
CLAVE_FECHA = "$fecha"
CLAVE_INSTANTE = "$instante"
CLAVES_TIPADAS = (CLAVE_DECIMAL, CLAVE_FECHA, CLAVE_INSTANTE)

#: Sufijo de UTC en el texto de un instante (decision de este modulo; se lee tambien `+00:00`).
SUFIJO_UTC = "Z"


class ErrorEvento(Exception):
    """Evento mal construido, payload no serializable o cadena de hash rota."""


# ---------------------------------------------------------------------------
# Instantes
# ---------------------------------------------------------------------------


def normalizar_instante(valor: object) -> datetime:
    """El instante en UTC. Un `datetime` naive (sin zona) es un defecto, no un instante (`ADR-004` C2)."""
    if not isinstance(valor, datetime):
        raise ErrorEvento(f"`ocurrido_en` debe ser un datetime con zona, no {type(valor).__name__}")
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErrorEvento(
            "`ocurrido_en` sin zona horaria: el log exige UTC explicito (datetime.now(timezone.utc))"
        )
    return valor.astimezone(UTC)


def ahora_utc() -> datetime:
    """El instante actual en UTC. El unico sitio del paquete que mira el reloj."""
    return datetime.now(UTC)


def texto_instante(valor: datetime) -> str:
    """Instante UTC en ISO-8601 con `Z` (ver cabecera)."""
    return normalizar_instante(valor).isoformat().replace("+00:00", SUFIJO_UTC)


def instante_desde_texto(texto: object) -> datetime:
    """Inverso de `texto_instante`; acepta `Z` y `+00:00`."""
    if not isinstance(texto, str) or not texto.strip():
        raise ErrorEvento(f"instante no textual: {texto!r}")
    crudo = texto.strip()
    if crudo.endswith(SUFIJO_UTC):
        crudo = crudo[:-1] + "+00:00"
    try:
        leido = datetime.fromisoformat(crudo)
    except ValueError as exc:
        raise ErrorEvento(f"instante ilegible {texto!r}: {exc}") from exc
    return normalizar_instante(leido)


def texto_decimal(valor: Decimal) -> str:
    """`Decimal` como cadena sin exponente y conservando la escala (ver cabecera)."""
    if not valor.is_finite():
        raise ErrorEvento(f"el log no serializa un Decimal no finito ({valor})")
    return format(valor, "f")


# ---------------------------------------------------------------------------
# JSON canonico
# ---------------------------------------------------------------------------


def _plano(valor: object, ruta: str = "$") -> object:
    """Estructura JSON pura: `Decimal` y fechas como cadena, sin `float`, sin objetos opacos."""
    if valor is None or isinstance(valor, bool | str):
        return valor
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        raise ErrorEvento(
            f"{ruta}: el log no serializa float (una magnitud es Decimal; la telemetria no es log)"
        )
    if isinstance(valor, Decimal):
        return texto_decimal(valor)
    if isinstance(valor, datetime):
        return texto_instante(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return _plano(valor.value, ruta)
    if isinstance(valor, Mapping):
        return {str(clave): _plano(v, f"{ruta}.{clave}") for clave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_plano(v, f"{ruta}[{i}]") for i, v in enumerate(valor)]
    if isinstance(valor, set | frozenset):
        # Un conjunto no tiene orden: se ordena por su propia forma canonica para que el hash no dependa
        # del orden de iteracion de Python.
        return sorted((_plano(v, f"{ruta}{{}}") for v in valor), key=lambda v: json.dumps(v, sort_keys=True))
    raise ErrorEvento(f"{ruta}: tipo no serializable en el log: {type(valor).__name__}")


def json_canonico(obj: object) -> str:
    """Forma canonica de `obj`: claves ordenadas, UTF-8, sin espacios (ver cabecera)."""
    return json.dumps(_plano(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Codificacion tipada de payloads
# ---------------------------------------------------------------------------


def codificar(valor: object, ruta: str = "$") -> object:
    """Valor JSON con etiquetas de tipo (ver cabecera). Es lo que se guarda en `Evento.payload`."""
    if valor is None or isinstance(valor, bool | str):
        return valor
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        raise ErrorEvento(
            f"{ruta}: el log no serializa float (una magnitud es Decimal; la telemetria no es log)"
        )
    if isinstance(valor, Decimal):
        return {CLAVE_DECIMAL: texto_decimal(valor)}
    if isinstance(valor, datetime):
        return {CLAVE_INSTANTE: texto_instante(valor)}
    if isinstance(valor, date):
        return {CLAVE_FECHA: valor.isoformat()}
    if isinstance(valor, Enum):
        return codificar(valor.value, ruta)
    if isinstance(valor, Mapping):
        return {str(clave): codificar(v, f"{ruta}.{clave}") for clave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [codificar(v, f"{ruta}[{i}]") for i, v in enumerate(valor)]
    raise ErrorEvento(f"{ruta}: tipo no codificable en un payload: {type(valor).__name__}")


def _etiqueta(valor: Mapping) -> str | None:
    if len(valor) != 1:
        return None
    clave = next(iter(valor))
    return clave if clave in CLAVES_TIPADAS else None


def decodificar(valor: object) -> object:
    """Inverso de `codificar`: devuelve `Decimal`, `date` y `datetime` donde habia etiquetas."""
    if isinstance(valor, Mapping):
        etiqueta = _etiqueta(valor)
        if etiqueta == CLAVE_DECIMAL:
            return Decimal(str(valor[etiqueta]))
        if etiqueta == CLAVE_FECHA:
            return date.fromisoformat(str(valor[etiqueta]))
        if etiqueta == CLAVE_INSTANTE:
            return instante_desde_texto(valor[etiqueta])
        return {str(clave): decodificar(v) for clave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [decodificar(v) for v in valor]
    return valor


# ---------------------------------------------------------------------------
# Hash encadenado
# ---------------------------------------------------------------------------


def calcular_hash(evento_sin_hash: Mapping[str, object], hash_previo: str) -> str:
    """`sha256(hash_previo + json_canonico(evento sin su hash))` en hexadecimal (`docs/03` §6.1).

    `hash_previo` del primer evento es la cadena vacia. La clave `hash` se ignora si viene en el sobre.
    """
    if not isinstance(evento_sin_hash, Mapping):
        raise ErrorEvento(f"el sobre de un evento es un Mapping, no {type(evento_sin_hash).__name__}")
    if not isinstance(hash_previo, str):
        raise ErrorEvento(f"`hash_previo` debe ser texto, no {type(hash_previo).__name__}")
    cuerpo = {clave: valor for clave, valor in evento_sin_hash.items() if clave != "hash"}
    return hashlib.sha256((hash_previo + json_canonico(cuerpo)).encode("utf-8")).hexdigest()


__all__ = [
    "CLAVES_TIPADAS",
    "CLAVE_DECIMAL",
    "CLAVE_FECHA",
    "CLAVE_INSTANTE",
    "SUFIJO_UTC",
    "ErrorEvento",
    "ahora_utc",
    "calcular_hash",
    "codificar",
    "decodificar",
    "instante_desde_texto",
    "json_canonico",
    "normalizar_instante",
    "texto_decimal",
    "texto_instante",
]
