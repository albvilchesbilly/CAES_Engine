"""Validador del modelo canonico contra los JSON Schema del paquete (`ADR-004` C1, opcion 1).

Por que un validador propio y no `jsonschema` ni `pydantic`: el nucleo no gana dependencias para algo que
hacemos una vez, y `pydantic` ademas coacciona tipos, justo lo que el contrato de la Fase 0 prohibe
(`ADR-002` §2.4). El esquema esta escrito en JSON Schema estandar, asi que delegar en un validador completo
el dia que haga falta es cambiar este modulo y nada mas.

Subconjunto de draft 2020-12 implementado (`PALABRAS`): `type` (con union de tipos), `required`,
`properties`, `additionalProperties` (`false` o un esquema), `items`, `minItems`, `enum`, `minimum`,
`minLength`, `$ref` **local** (`#/$defs/<nombre>`) y dos formatos propios:

- `decimal-string`: cadena que `Decimal` acepta y que es **finita** (`NaN` e `Infinity` fallan).
- `date`: cadena ISO `AAAA-MM-DD` exacta.

Cualquier otra palabra en un esquema es un **error de carga** (`ErrorModelo`), no un silencio: un esquema
que declara una restriccion que el validador ignoraria daria una falsa sensacion de validacion. Es el mismo
criterio que `engine.expresiones` con una funcion desconocida.

Los esquemas se leen del propio paquete (`esquemas/*.json`) y se cachean. No hay red, ni descargas, ni
resolucion de `$id` remotos: `validar` es determinista y funciona sin conexion.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path

from engine.modelo.entidades import (
    ActuacionCanonica,
    ErrorModelo,
    Expediente,
    GrupoActuaciones,
)
from engine.modelo.serializacion import a_dict

#: Carpeta con los esquemas versionados. Se leen de aqui y solo de aqui.
CARPETA_ESQUEMAS = Path(__file__).resolve().parent / "esquemas"

#: Nombre logico de esquema → fichero. El sufijo es la version del modelo (`MODELO_VERSION`).
ESQUEMAS: Mapping[str, str] = {
    "actuacion": "actuacion-1.0.json",
    "grupo": "grupo-1.0.json",
    "expediente": "expediente-1.0.json",
}

#: Entidad → esquema con el que se valida.
ESQUEMA_POR_ENTIDAD: Mapping[type, str] = {
    ActuacionCanonica: "actuacion",
    GrupoActuaciones: "grupo",
    Expediente: "expediente",
}

#: Palabras de JSON Schema que este validador entiende. Otra cosa en un esquema es un error de carga.
PALABRAS = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "enum",
        "minimum",
        "minLength",
        "format",
    }
)

#: Formatos propios soportados (§C1 de `ADR-004`).
FORMATOS = ("decimal-string", "date")

#: Fecha ISO estricta. Se guarda como texto y se usa con `re.fullmatch`: el nucleo no usa `compile`.
PATRON_FECHA = r"\d{4}-\d{2}-\d{2}"
RAIZ = "(raiz)"


def _ruta(ruta: str) -> str:
    return ruta or RAIZ


def _tipo_json(valor: object) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, int):
        return "integer"
    if isinstance(valor, str):
        return "string"
    if isinstance(valor, Mapping):
        return "object"
    if isinstance(valor, list):
        return "array"
    return type(valor).__name__


def _comprobar_palabras(esquema: object, donde: str) -> None:
    """Recorre el esquema al cargarlo y falla si usa una palabra que este validador no implementa."""
    if isinstance(esquema, Mapping):
        for clave, valor in esquema.items():
            if clave not in PALABRAS:
                raise ErrorModelo(f"{donde}: el esquema usa la palabra no soportada {clave!r}")
            if clave == "format" and valor not in FORMATOS:
                raise ErrorModelo(f"{donde}: formato no soportado {valor!r}")
            if clave in ("properties", "$defs") and isinstance(valor, Mapping):
                for nombre, sub in valor.items():
                    _comprobar_palabras(sub, f"{donde}.{clave}.{nombre}")
            elif clave in ("items", "additionalProperties"):
                _comprobar_palabras(valor, f"{donde}.{clave}")


@cache
def esquema(nombre: str) -> Mapping[str, object]:
    """Esquema del paquete, cargado y comprobado. Sin red: se lee del fichero que acompaña al codigo."""
    if nombre not in ESQUEMAS:
        raise ErrorModelo(f"no existe el esquema {nombre!r}; hay {sorted(ESQUEMAS)}")
    ruta = CARPETA_ESQUEMAS / ESQUEMAS[nombre]
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - solo si el paquete esta roto
        raise ErrorModelo(f"no se puede leer el esquema {nombre!r} en {ruta}: {exc}") from exc
    if not isinstance(datos, dict):  # pragma: no cover
        raise ErrorModelo(f"el esquema {nombre!r} no es un objeto JSON")
    _comprobar_palabras(datos, nombre)
    return datos


def _resolver(sub: Mapping[str, object], raiz: Mapping[str, object]) -> Mapping[str, object]:
    """Resuelve un `$ref` local (`#/$defs/<nombre>`). No se resuelven referencias remotas."""
    ref = sub.get("$ref")
    if ref is None:
        return sub
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise ErrorModelo(f"referencia no soportada {ref!r} (solo #/$defs/<nombre>)")
    nombre = ref[len("#/$defs/") :]
    defs = raiz.get("$defs")
    if not isinstance(defs, Mapping) or nombre not in defs:
        raise ErrorModelo(f"el esquema no define {ref!r}")
    destino = defs[nombre]
    if not isinstance(destino, Mapping):  # pragma: no cover
        raise ErrorModelo(f"la definicion {ref!r} no es un esquema")
    return destino


def _validar_formato(valor: str, formato: str, ruta: str) -> None:
    if formato == "decimal-string":
        try:
            numero = Decimal(valor)
        except InvalidOperation:
            raise ErrorModelo(f"{_ruta(ruta)}: {valor!r} no es un decimal") from None
        if not numero.is_finite():
            raise ErrorModelo(f"{_ruta(ruta)}: {valor!r} no es un decimal finito")
    elif formato == "date":
        if not re.fullmatch(PATRON_FECHA, valor):
            raise ErrorModelo(f"{_ruta(ruta)}: {valor!r} no es una fecha ISO AAAA-MM-DD")
        anio, mes, dia = (int(parte) for parte in valor.split("-"))
        try:
            date(anio, mes, dia)
        except ValueError:
            raise ErrorModelo(f"{_ruta(ruta)}: {valor!r} no es una fecha valida") from None


def _validar_nodo(valor: object, sub: Mapping[str, object], raiz: Mapping[str, object], ruta: str) -> None:
    sub = _resolver(sub, raiz)

    tipos = sub.get("type")
    if tipos is not None:
        esperados = tuple(tipos) if isinstance(tipos, list) else (tipos,)
        real = _tipo_json(valor)
        # Un booleano no es un entero en JSON Schema; `_tipo_json` ya los separa.
        if real not in esperados:
            raise ErrorModelo(f"{_ruta(ruta)}: se esperaba {'|'.join(esperados)} y llego {real}")

    if "enum" in sub:
        permitidos = sub["enum"]
        if isinstance(permitidos, list) and not any(
            valor is permitido or valor == permitido for permitido in permitidos
        ):
            raise ErrorModelo(f"{_ruta(ruta)}: {valor!r} no esta en el enumerado {permitidos}")

    if isinstance(valor, str):
        minimo = sub.get("minLength")
        if isinstance(minimo, int) and len(valor) < minimo:
            raise ErrorModelo(f"{_ruta(ruta)}: cadena mas corta que el minimo ({minimo})")
        formato = sub.get("format")
        if isinstance(formato, str):
            _validar_formato(valor, formato, ruta)

    if isinstance(valor, int) and not isinstance(valor, bool):
        minimo = sub.get("minimum")
        if isinstance(minimo, int) and valor < minimo:
            raise ErrorModelo(f"{_ruta(ruta)}: {valor} es menor que el minimo ({minimo})")

    if isinstance(valor, Mapping):
        _validar_objeto(valor, sub, raiz, ruta)
    elif isinstance(valor, list):
        _validar_lista(valor, sub, raiz, ruta)


def _validar_objeto(
    valor: Mapping[str, object], sub: Mapping[str, object], raiz: Mapping[str, object], ruta: str
) -> None:
    requeridos = sub.get("required")
    if isinstance(requeridos, Sequence):
        for campo in requeridos:
            if campo not in valor:
                raise ErrorModelo(f"{_ruta(ruta)}: falta el campo requerido {campo!r}")

    propiedades = sub.get("properties")
    propiedades = propiedades if isinstance(propiedades, Mapping) else {}
    adicionales = sub.get("additionalProperties", True)

    for clave, contenido in valor.items():
        hijo = f"{ruta}.{clave}" if ruta else str(clave)
        declarada = propiedades.get(clave)
        if isinstance(declarada, Mapping):
            _validar_nodo(contenido, declarada, raiz, hijo)
        elif adicionales is False:
            raise ErrorModelo(f"{_ruta(ruta)}: campo no permitido {clave!r}")
        elif isinstance(adicionales, Mapping):
            _validar_nodo(contenido, adicionales, raiz, hijo)


def _validar_lista(valor: list, sub: Mapping[str, object], raiz: Mapping[str, object], ruta: str) -> None:
    minimo = sub.get("minItems")
    if isinstance(minimo, int) and len(valor) < minimo:
        raise ErrorModelo(f"{_ruta(ruta)}: se esperaban al menos {minimo} elementos y hay {len(valor)}")
    elementos = sub.get("items")
    if isinstance(elementos, Mapping):
        for i, elemento in enumerate(valor):
            _validar_nodo(elemento, elementos, raiz, f"{ruta}[{i}]")


def validar_documento(datos: Mapping[str, object], nombre_esquema: str = "actuacion") -> None:
    """Valida un `dict` ya serializado contra el esquema indicado. `ErrorModelo` con la ruta del campo."""
    if not isinstance(datos, Mapping):
        raise ErrorModelo(f"{RAIZ}: se esperaba un objeto y llego {_tipo_json(datos)}")
    raiz = esquema(nombre_esquema)
    _validar_nodo(datos, raiz, raiz, "")


def validar(obj: object) -> None:
    """Valida una entidad del modelo canonico contra su JSON Schema (ver cabecera del modulo)."""
    if isinstance(obj, Mapping):
        raise ErrorModelo(
            "validar espera una entidad del modelo canonico; para un dict, validar_documento(datos, esquema)"
        )
    if not (is_dataclass(obj) and not isinstance(obj, type)):
        raise ErrorModelo(f"validar espera una entidad del modelo canonico, no {type(obj).__name__}")
    nombre = ESQUEMA_POR_ENTIDAD.get(type(obj))
    if nombre is None:
        raise ErrorModelo(f"{type(obj).__name__} no tiene esquema propio; valida la entidad que la contiene")
    validar_documento(a_dict(obj), nombre)


__all__ = [
    "CARPETA_ESQUEMAS",
    "ESQUEMAS",
    "ESQUEMA_POR_ENTIDAD",
    "FORMATOS",
    "PALABRAS",
    "esquema",
    "validar",
    "validar_documento",
]
