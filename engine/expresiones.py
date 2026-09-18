"""Lenguaje de expresiones de la spec: parser de lista blanca y evaluador trivaluado.

Interpreta las cadenas `logica` (reglas) y `formula` (calculo) de `spec/*.yaml` sin `eval`, sin
`exec` y sin el modulo `ast`. Vocabulario cerrado de `docs/04` §6: una funcion o construccion que no
este aqui es `ErrorCargaExpresion` al compilar, nunca un fallo en tiempo de evaluacion.

Gramatica (BNF breve; la precedencia crece hacia abajo):

    expresion    := "for" "each" NOMBRE ":" expresion | implicacion
    implicacion  := disyuncion ( "->" implicacion )?              # asociativa a la derecha
    disyuncion   := conjuncion ( "or" conjuncion )*
    conjuncion   := negacion ( "and" negacion )*
    negacion     := "not" negacion | comparacion
    comparacion  := suma ( ( "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" ) suma )?
    suma         := producto ( ( "+" | "-" ) producto )*
    producto     := unario ( ( "*" | "/" ) unario )*
    unario       := ( "-" | "+" ) unario | potencia
    potencia     := primario ( "**" unario )?                     # solo en modo "formula"
    primario     := NUMERO ( UNIDAD_FECHA )? | CADENA | "true" | "false" | ORIGEN
                  | "[" ( literal ( "," literal )* )? "]"
                  | NOMBRE "(" ( expresion ( "," expresion )* )? ")"
                  | NOMBRE "where" implicacion
                  | NOMBRE
                  | "(" expresion ")"
    literal      := NUMERO | CADENA | "true" | "false" | NOMBRE      # NOMBRE en lista = literal simbolico

Lexico:

- NUMERO: `\\d+(\\.\\d+)?` → `Decimal`. Nunca `float`. Seguido de `años`/`año`/`anos`/`ano`/`meses`/`mes`/
  `dias`/`días`/`dia`/`día` es una duracion (`fecha + 3 años`).
- CADENA: entre comillas dobles o simples.
- NOMBRE: identificador con puntos (`PM.valores_por_fuente`, `registro.dias`). Un codigo en mayusculas con
  guion y segmento final numerico (`FIS-01`, `R-CON-01`, `DOC-05B`) es un unico identificador si no hay
  espacios alrededor del guion; `a - b` con espacios, o con operandos en minuscula o numericos, es resta.
  `True`, `False`, `None`, `null` y sus variantes de mayusculas NO son nombres: el vocabulario booleano es
  solo `true`/`false` en minusculas y no existe el literal nulo (la ausencia es `NO_EVALUABLE`).
- ORIGEN: `prefijo:identificador` sin espacios (`tabla:REG1781_CUADRO6`) es un literal de origen que se
  compara como la cadena `"tabla:REG1781_CUADRO6"`. Los dos puntos de `for each x: ...` van seguidos de
  espacio y no se pegan.
- Palabras reservadas: `and or not in where for each true false` y las unidades de fecha.
- Profundidad de anidamiento (parentesis, argumentos, `not`, signo unario, `->`, `**`, `where`, `for each`)
  acotada a `PROFUNDIDAD_MAXIMA`; superarla es `ErrorCargaExpresion`, nunca `RecursionError`.

Tipado del contexto (ADR-002 §2.4): el contexto entrega **valores tipados**:

- `Decimal` para magnitudes (un `int` se acepta y se convierte; un `float` es error de contexto).
- `datetime.date` para fechas (`datetime.datetime` es error de contexto).
- `bool` para predicados (`factura.campos_minimos_presentes`, `doc.obligatorio`).
- `str` solo para enumerados e identificadores (`regimen_previo`, `N2.evidencia`, `p.fuente`, numeros
  de serie, valores canonicos de `valores_por_fuente`).
- `list`/`tuple` para colecciones. `motor` es la **lista** de unidades de la actuacion, no el `dict` de
  `ActuacionConsolidada.unidades`. `for each`, `where` y la ligadura de `all/exists/count` iteran solo
  sobre `list`/`tuple`; un `set` o un `dict` en esa posicion es error de contexto (los `dict` se admiten
  en `unique`, `count`, `sum` y `exists` sin predicado, donde se toman sus valores, y en `in`, donde se
  toman sus claves).

El parser **no coerciona texto**: `"35"` no es `35`, `"true"` no es `true`, `"2026-01-01"` no es una
fecha. Una comparacion `==`/`!=` entre familias distintas (`str`/`bool`/`Decimal`/`date`/`bytes`) es
`ErrorEvaluacionExpresion`, nunca `False` ni `True` silencioso; `<`/`<=`/`>`/`>=` solo ordenan numeros
con numeros y fechas con fechas. Un `Decimal` no finito (`NaN`, `Infinity`) que llegue del contexto es
error de contexto en aritmetica y en comparacion.

Semantica:

- Tres valores: `True`, `False` y el centinela `NO_EVALUABLE`. `and`: algun `False` → `False`; todos
  `True` → `True`; si no → `NO_EVALUABLE`. `or`: algun `True` → `True`; todos `False` → `False`; si no
  → `NO_EVALUABLE`. `not NO_EVALUABLE` → `NO_EVALUABLE`. `a -> b` ≡ `not a or b` (ADR-001 C7).
- Un identificador ausente (o `None`) resuelve a `NO_EVALUABLE`, nunca a excepcion. Solo un contexto mal
  construido (`float`, `datetime`, no finito, tipos incomparables, escalar o `set` donde se esperaba
  lista, `presente` que lanza) produce `ErrorEvaluacionExpresion`.
- Literales simbolicos (enumerados sin comillas). Dos regimenes, elegidos al compilar:
  * Con `compilar(..., enumerados=conjunto)`: un NOMBRE sin punto que este en el conjunto es SIEMPRE una
    cadena con su propio nombre, en cualquier posicion de expresion, y no entra en `identificadores`;
    un NOMBRE que no este en el conjunto es siempre identificador (sin heuristica en evaluacion). Las
    posiciones de ligadura `for each NOMBRE:` y `NOMBRE where ...` son colecciones por gramatica aunque
    el nombre figure en el conjunto (`motor` es categoria de linea de factura y coleccion de unidades).
    Dentro de `[...]` un NOMBRE que no este en el conjunto es `ErrorCargaExpresion` (errata en la spec).
  * Sin `enumerados` (`None`): heuristica de F0.1. Un NOMBRE sin punto que el contexto no resuelve se toma
    como cadena SOLO en el lado derecho de `==`/`!=` y SOLO si el lado izquierdo es `str`. Dentro de
    `[...]` los nombres son siempre simbolicos.
  `Expresion.literales_simbolicos` recoge los nombres resueltos como literal al compilar (los de `[...]`
  y, con `enumerados`, los del conjunto). `Expresion.colecciones_ligadas` recoge los nombres en posicion
  `for each` / `where`; estos si estan en `identificadores`.
- Regla de ligadura en `all(...)`, `exists(...)` y `count(...)`: si el argumento es un predicado (no un
  simple nombre ni un filtro), la variable ligada es el primer nombre del predicado, en orden de aparicion,
  que el contexto entrega como lista o tupla (se prueba el nombre completo con puntos y despues su raiz).
  Cada elemento se evalua con un `ContextoElemento`: `raiz.atributo` se lee del elemento, `raiz` es el
  propio elemento, el resto de nombres se buscan primero en el elemento y despues en el contexto exterior.
  `coleccion where cond` y `for each coleccion: expr` ligan del mismo modo.
- Agregaciones trivaluadas: `exists` → algun `True` → `True`, si no algun `NO_EVALUABLE` → `NO_EVALUABLE`,
  si no `False` (vacio → `False`). `all` → algun `False` → `False`, si no algun `NO_EVALUABLE` →
  `NO_EVALUABLE`, si no `True` (vacio → `True`). `for each` igual que `all` pero coleccion vacia →
  `NO_EVALUABLE` (no hay unidad sobre la que evaluar). `count(pred)` → `NO_EVALUABLE` si algun elemento
  lo es; `count(coleccion)` → su tamaño; `count([])` → 0.
- `unique(x)`: `True` si todos los valores presentes (no `None`/`NO_EVALUABLE`) son iguales; un valor →
  `True`; escalar → `True`; sin valores → `NO_EVALUABLE`. Con un `dict` compara los valores (tipo_doc →
  valor). Compara con la igualdad del tipo de los elementos: los `valores_por_fuente` son cadenas
  canonicas y se comparan como cadenas (`"110"` ≠ `"110.0"`); un `dict` de `Decimal` se compara como
  `Decimal`; mezclar familias es error de contexto. No aplica tolerancias ni normalizacion: eso lo hace
  el consolidador antes.
- `in`: `str` frente a literales simbolicos y cadenas; `Decimal` frente a numeros. Mezclar familias
  dentro de la lista es error de contexto (se comparan todos los elementos, sin cortocircuito).
- Aritmetica solo con `Decimal` (los `int` del contexto se convierten). `date + duracion` suma años, meses
  o dias; salir del rango de `date` es error de contexto. Comparacion con `NO_EVALUABLE` → `NO_EVALUABLE`.
- `sha256(x)`: `x` es `str` (UTF-8) o `bytes`; devuelve el hexdigest.
- `presente(doc)`: llama a la funcion `presente` del contexto sobre el elemento; si el contexto no la
  ofrece y el elemento tiene el atributo `presente`, se usa; si no, `NO_EVALUABLE`. Si la funcion lanza,
  el error se envuelve en `ErrorEvaluacionExpresion` con el mensaje original.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, DecimalException
from typing import Protocol, runtime_checkable


class ErrorCargaExpresion(Exception):
    """Sintaxis invalida, funcion o construccion fuera del vocabulario. Se lanza al compilar."""


class ErrorEvaluacionExpresion(Exception):
    """Contexto mal construido: float, tipos incomparables, escalar donde se esperaba coleccion."""


class _NoEvaluable:
    """Centinela unico. No es `None`, ni `True`, ni `False`; no admite contexto booleano."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NO_EVALUABLE"

    def __bool__(self) -> bool:
        raise TypeError("NO_EVALUABLE no tiene valor de verdad; compara con `is NO_EVALUABLE`")

    def __reduce__(self) -> str:
        return "NO_EVALUABLE"


NO_EVALUABLE = _NoEvaluable()

FUNCIONES_PERMITIDAS: frozenset[str] = frozenset(
    {"unique", "exists", "all", "count", "sum", "min", "abs", "sha256", "presente"}
)
_ARIDAD: dict[str, tuple[int, int | None]] = {
    "unique": (1, 1),
    "exists": (1, 1),
    "all": (1, 1),
    "count": (1, 1),
    "sum": (1, 1),
    "min": (2, None),
    "abs": (1, 1),
    "sha256": (1, 1),
    "presente": (1, 1),
}
MODOS = ("logica", "formula")
PROFUNDIDAD_MAXIMA = 64

_UNIDADES_FECHA: dict[str, str] = {
    "años": "años",
    "año": "años",
    "anos": "años",
    "ano": "años",
    "meses": "meses",
    "mes": "meses",
    "dias": "dias",
    "días": "dias",
    "dia": "dias",
    "día": "dias",
}
_PALABRAS = frozenset({"and", "or", "not", "in", "where", "for", "each", "true", "false"}) | frozenset(
    _UNIDADES_FECHA
)
# Nombres que parecen literales de otros lenguajes; se rechazan al compilar (comparados en minusculas).
_NOMBRES_PROHIBIDOS = frozenset({"true", "false", "none", "null"})
_COMPARADORES = frozenset({"==", "!=", "<", "<=", ">", ">="})
_ORDENABLES = frozenset({"numero", "fecha"})


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------


@runtime_checkable
class Contexto(Protocol):
    """Espacio de nombres de una evaluacion. `resolver` devuelve el valor o `NO_EVALUABLE` si falta."""

    def resolver(self, nombre: str) -> object: ...


_AUSENTE = object()
_ESCALARES = (str, bytes, bool, int, Decimal, date, float, _NoEvaluable, type(None))


def _buscar(objeto: object, ruta: str) -> object:
    """Busca `ruta` (con puntos) en un dict anidado o en atributos de un objeto. `_AUSENTE` si no esta."""
    if isinstance(objeto, Mapping):
        if ruta in objeto:
            return objeto[ruta]
        cabeza, sep, resto = ruta.partition(".")
        if sep and cabeza in objeto:
            return _buscar(objeto[cabeza], resto)
        return _AUSENTE
    if isinstance(objeto, _ESCALARES) or isinstance(objeto, (list, tuple, set, frozenset)):
        return _AUSENTE
    cabeza, sep, resto = ruta.partition(".")
    if cabeza.startswith("_") or not hasattr(objeto, cabeza):
        return _AUSENTE
    valor = getattr(objeto, cabeza)
    return _buscar(valor, resto) if sep else valor


def _o_no_evaluable(valor: object) -> object:
    return NO_EVALUABLE if valor is _AUSENTE or valor is None else valor


class ContextoDict:
    """Contexto sobre un dict anidado. Acepta claves planas con punto (`"registro.dias"`) o anidadas."""

    def __init__(self, datos: Mapping[str, object] | None = None) -> None:
        self._datos: Mapping[str, object] = datos or {}

    def resolver(self, nombre: str) -> object:
        return _o_no_evaluable(_buscar(self._datos, nombre))


class ContextoElemento:
    """Contexto de un elemento ligado a `ligado` dentro de una coleccion; delega en el exterior."""

    def __init__(self, elemento: object, ligado: str | None, exterior: Contexto) -> None:
        self._elemento = elemento
        self._ligado = ligado
        self._exterior = exterior

    def resolver(self, nombre: str) -> object:
        ligado = self._ligado
        if ligado is not None:
            if nombre == ligado:
                return _o_no_evaluable(self._elemento)
            if nombre.startswith(ligado + "."):
                return _o_no_evaluable(_buscar(self._elemento, nombre[len(ligado) + 1 :]))
        valor = _buscar(self._elemento, nombre)
        if valor is not _AUSENTE:
            return _o_no_evaluable(valor)
        return self._exterior.resolver(nombre)


# ---------------------------------------------------------------------------
# Lexico
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Token:
    tipo: str  # NUMERO CADENA NOMBRE ORIGEN PALABRA OP FIN
    valor: str
    pos: int


_OPS = ("->", "**", "==", "!=", "<=", ">=", "+", "-", "*", "/", "<", ">", "(", ")", "[", "]", ",", ":")
# Un unico lexico en alternacion ordenada; el ultimo grupo captura cualquier caracter no reconocido.
_LEXICO = (
    r"(?P<ESPACIO>\s+)"
    r"|(?P<NUMERO>\d+(?:\.\d+)?(?![\w.]))"
    r"|\"(?P<CADENA2>[^\"]*)\"|'(?P<CADENA1>[^']*)'"
    r"|(?P<CODIGO>[A-Z][A-Z0-9]*(?:-[A-Z]+)*-\d+[A-Z]?(?![\w-]))"
    r"|(?P<NOMBRE>[^\W\d]\w*(?:\.[^\W\d]\w*)*)(?P<ORIGEN>:[^\W\d][\w.]*)?"
    r"|(?P<OP>" + "|".join(re.escape(op) for op in _OPS) + ")"
    r"|(?P<ERROR>.)"
)


def _tokenizar(texto: str) -> list[_Token]:
    tokens: list[_Token] = []
    for m in re.finditer(_LEXICO, texto):
        i = m.start()
        if m.group("ESPACIO") is not None:
            continue
        if m.group("NUMERO") is not None:
            tokens.append(_Token("NUMERO", m.group("NUMERO"), i))
        elif m.group("CADENA2") is not None or m.group("CADENA1") is not None:
            cadena = m.group("CADENA2") if m.group("CADENA2") is not None else m.group("CADENA1")
            tokens.append(_Token("CADENA", cadena, i))
        elif m.group("CODIGO") is not None:
            tokens.append(_Token("NOMBRE", m.group("CODIGO"), i))
        elif m.group("NOMBRE") is not None:
            nombre = m.group("NOMBRE")
            if m.group("ORIGEN") is not None:
                tokens.append(_Token("ORIGEN", nombre + m.group("ORIGEN"), i))
            elif nombre in _PALABRAS:
                tokens.append(_Token("PALABRA", nombre, i))
            elif nombre.lower() in _NOMBRES_PROHIBIDOS:
                raise ErrorCargaExpresion(
                    f"{nombre!r} no es un nombre valido en posicion {i}: los booleanos son `true`/`false` "
                    f"en minusculas y no existe literal nulo (la ausencia es NO_EVALUABLE): {texto!r}"
                )
            else:
                tokens.append(_Token("NOMBRE", nombre, i))
        elif m.group("OP") is not None:
            tokens.append(_Token("OP", m.group("OP"), i))
        else:
            raise ErrorCargaExpresion(
                f"caracter no reconocido {m.group('ERROR')!r} en posicion {i}: {texto!r}"
            )
    tokens.append(_Token("FIN", "", len(texto)))
    return tokens


# ---------------------------------------------------------------------------
# Tipos: familias, normalizacion y comparacion
# ---------------------------------------------------------------------------


def _es_coleccion(valor: object) -> bool:
    """Coleccion iterable del lenguaje: solo `list` y `tuple` (orden determinista)."""
    return isinstance(valor, (list, tuple))


def _numero(valor: object, que: str) -> Decimal:
    if isinstance(valor, bool):
        raise ErrorEvaluacionExpresion(f"{que}: se esperaba un numero y llego un booleano")
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ErrorEvaluacionExpresion(f"{que}: valor no finito ({valor!r}) en el contexto")
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        raise ErrorEvaluacionExpresion(f"{que}: float no permitido ({valor!r}); usa Decimal")
    raise ErrorEvaluacionExpresion(f"{que}: se esperaba un numero y llego {type(valor).__name__}")


def _comparable(valor: object, que: str) -> object:
    """Normaliza un operando de comparacion: int → Decimal; rechaza float, datetime, no finito y ajeno."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, Decimal, float)):
        return _numero(valor, que)
    if isinstance(valor, datetime):
        raise ErrorEvaluacionExpresion(f"{que}: datetime no permitido ({valor!r}); usa datetime.date")
    if isinstance(valor, (str, date, bytes)):
        return valor
    raise ErrorEvaluacionExpresion(f"{que}: tipo no comparable {type(valor).__name__} ({valor!r})")


def _familia(valor: object) -> str:
    if isinstance(valor, bool):
        return "booleano"
    if isinstance(valor, Decimal):
        return "numero"
    if isinstance(valor, str):
        return "texto"
    if isinstance(valor, date):
        return "fecha"
    return "bytes"


def _comparar(op: str, a: object, b: object) -> bool:
    """Igualdad y orden entre valores de la misma familia; familias distintas → error de contexto."""
    a = _comparable(a, f"operando izquierdo de {op}")
    b = _comparable(b, f"operando derecho de {op}")
    fa, fb = _familia(a), _familia(b)
    if fa != fb:
        raise ErrorEvaluacionExpresion(f"no se puede comparar {fa} {op} {fb} ({a!r}, {b!r})")
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if fa not in _ORDENABLES:
        raise ErrorEvaluacionExpresion(f"no se puede ordenar {fa} {op} {fb} ({a!r}, {b!r})")
    if op == "<":
        return a < b  # type: ignore[operator]
    if op == "<=":
        return a <= b  # type: ignore[operator]
    if op == ">":
        return a > b  # type: ignore[operator]
    return a >= b  # type: ignore[operator]


def _logico(valor: object, que: str) -> object:
    if valor is NO_EVALUABLE or isinstance(valor, bool):
        return valor
    raise ErrorEvaluacionExpresion(f"{que}: se esperaba un booleano y llego {type(valor).__name__}")


def _y(valores: list[object]) -> object:
    if any(v is False for v in valores):
        return False
    if all(v is True for v in valores):
        return True
    return NO_EVALUABLE


def _o(valores: list[object]) -> object:
    if any(v is True for v in valores):
        return True
    if all(v is False for v in valores):
        return False
    return NO_EVALUABLE


@dataclass(frozen=True)
class _Duracion:
    cantidad: Decimal
    unidad: str  # "años" | "meses" | "dias"


def _sumar_fecha(fecha: date, duracion: _Duracion, signo: int) -> date:
    if isinstance(fecha, datetime):
        raise ErrorEvaluacionExpresion(f"datetime no permitido ({fecha!r}); usa datetime.date")
    if duracion.cantidad != duracion.cantidad.to_integral_value():
        raise ErrorEvaluacionExpresion(f"duracion no entera: {duracion.cantidad} {duracion.unidad}")
    n = int(duracion.cantidad) * signo
    try:
        if duracion.unidad == "dias":
            return fecha + timedelta(days=n)
        meses_totales = fecha.month - 1 + (n * 12 if duracion.unidad == "años" else n)
        anio = fecha.year + meses_totales // 12
        mes = meses_totales % 12 + 1
        dia = min(fecha.day, _dias_del_mes(anio, mes))
        return fecha.replace(year=anio, month=mes, day=dia)
    except (OverflowError, ValueError) as exc:
        raise ErrorEvaluacionExpresion(
            f"fecha fuera de rango: {fecha.isoformat()} {'+' if signo > 0 else '-'} "
            f"{duracion.cantidad} {duracion.unidad} ({exc})"
        ) from exc


def _dias_del_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]  # ValueError fuera de [1, 9999]: lo captura _sumar_fecha


# ---------------------------------------------------------------------------
# Arbol sintactico y evaluacion
# ---------------------------------------------------------------------------


class _Nodo:
    def evaluar(self, ctx: Contexto) -> object:
        raise NotImplementedError

    def nombres(self) -> list[str]:
        """Nombres referenciados en orden de aparicion (con repeticiones)."""
        return []

    es_predicado = False


@dataclass(frozen=True)
class _Literal(_Nodo):
    valor: object

    def evaluar(self, ctx: Contexto) -> object:
        return self.valor


@dataclass(frozen=True)
class _Nombre(_Nodo):
    nombre: str

    def evaluar(self, ctx: Contexto) -> object:
        return ctx.resolver(self.nombre)

    def nombres(self) -> list[str]:
        return [self.nombre]


@dataclass(frozen=True)
class _Lista(_Nodo):
    elementos: tuple[_Nodo, ...]

    def evaluar(self, ctx: Contexto) -> object:
        return [e.evaluar(ctx) for e in self.elementos]


@dataclass(frozen=True)
class _DuracionNodo(_Nodo):
    duracion: _Duracion

    def evaluar(self, ctx: Contexto) -> object:
        return self.duracion


@dataclass(frozen=True)
class _Unario(_Nodo):
    op: str
    operando: _Nodo

    def evaluar(self, ctx: Contexto) -> object:
        v = self.operando.evaluar(ctx)
        if v is NO_EVALUABLE:
            return NO_EVALUABLE
        n = _numero(v, f"{self.op}x")
        return -n if self.op == "-" else n

    def nombres(self) -> list[str]:
        return self.operando.nombres()


@dataclass(frozen=True)
class _Binario(_Nodo):
    op: str
    izq: _Nodo
    der: _Nodo

    def evaluar(self, ctx: Contexto) -> object:
        a = self.izq.evaluar(ctx)
        b = self.der.evaluar(ctx)
        if a is NO_EVALUABLE or b is NO_EVALUABLE:
            return NO_EVALUABLE
        if isinstance(a, date) and isinstance(b, _Duracion) and self.op in ("+", "-"):
            return _sumar_fecha(a, b, 1 if self.op == "+" else -1)
        x = _numero(a, f"operando izquierdo de {self.op}")
        y = _numero(b, f"operando derecho de {self.op}")
        try:
            if self.op == "+":
                return x + y
            if self.op == "-":
                return x - y
            if self.op == "*":
                return x * y
            if self.op == "/":
                return x / y
            return x**y
        except DecimalException as exc:
            raise ErrorEvaluacionExpresion(f"error aritmetico en {x} {self.op} {y}: {exc!r}") from exc

    def nombres(self) -> list[str]:
        return self.izq.nombres() + self.der.nombres()


@dataclass(frozen=True)
class _Comparacion(_Nodo):
    op: str
    izq: _Nodo
    der: _Nodo
    heuristica: bool  # True sin `enumerados`: nombre ausente a la derecha de ==/!= con izquierdo str
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        a = self.izq.evaluar(ctx)
        b = self.der.evaluar(ctx)
        if (
            self.heuristica
            and b is NO_EVALUABLE
            and isinstance(a, str)
            and self.op in ("==", "!=")
            and isinstance(self.der, _Nombre)
            and "." not in self.der.nombre
        ):
            b = self.der.nombre  # literal simbolico (enumerado sin comillas)
        if a is NO_EVALUABLE or b is NO_EVALUABLE:
            return NO_EVALUABLE
        return _comparar(self.op, a, b)

    def nombres(self) -> list[str]:
        return self.izq.nombres() + self.der.nombres()


@dataclass(frozen=True)
class _Pertenencia(_Nodo):
    elemento: _Nodo
    coleccion: _Nodo
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        a = self.elemento.evaluar(ctx)
        col = self.coleccion.evaluar(ctx)
        if a is NO_EVALUABLE or col is NO_EVALUABLE:
            return NO_EVALUABLE
        if isinstance(col, Mapping):
            col = list(col.keys())
        if not _es_coleccion(col):
            raise ErrorEvaluacionExpresion(f"`in` sobre algo que no es lista: {type(col).__name__}")
        # sin cortocircuito: una familia ajena en la lista es error aunque otro elemento coincida
        coincidencias = [_comparar("==", a, x) for x in col if x is not NO_EVALUABLE and x is not None]
        return any(coincidencias)

    def nombres(self) -> list[str]:
        return self.elemento.nombres() + self.coleccion.nombres()


@dataclass(frozen=True)
class _Not(_Nodo):
    operando: _Nodo
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        v = _logico(self.operando.evaluar(ctx), "not")
        return NO_EVALUABLE if v is NO_EVALUABLE else not v

    def nombres(self) -> list[str]:
        return self.operando.nombres()


@dataclass(frozen=True)
class _And(_Nodo):
    operandos: tuple[_Nodo, ...]
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        return _y([_logico(o.evaluar(ctx), "and") for o in self.operandos])

    def nombres(self) -> list[str]:
        return [n for o in self.operandos for n in o.nombres()]


@dataclass(frozen=True)
class _Or(_Nodo):
    operandos: tuple[_Nodo, ...]
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        return _o([_logico(o.evaluar(ctx), "or") for o in self.operandos])

    def nombres(self) -> list[str]:
        return [n for o in self.operandos for n in o.nombres()]


@dataclass(frozen=True)
class _Implicacion(_Nodo):
    antecedente: _Nodo
    consecuente: _Nodo
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        a = _logico(self.antecedente.evaluar(ctx), "->")
        b = _logico(self.consecuente.evaluar(ctx), "->")
        no_a = NO_EVALUABLE if a is NO_EVALUABLE else not a
        return _o([no_a, b])

    def nombres(self) -> list[str]:
        return self.antecedente.nombres() + self.consecuente.nombres()


def _ligar(pred: _Nodo, ctx: Contexto) -> tuple[str, list[object]] | None:
    """Primer nombre del predicado (completo, luego su raiz) que el contexto entrega como lista o tupla."""
    vistos: set[str] = set()
    for nombre in pred.nombres():
        raiz = nombre.split(".", 1)[0]
        for candidato in (nombre, raiz):
            if candidato in vistos:
                continue
            vistos.add(candidato)
            valor = ctx.resolver(candidato)
            if _es_coleccion(valor):
                return candidato, list(valor)  # type: ignore[arg-type]
    return None


def _iterar(pred: _Nodo, ligado: str, elementos: list[object], ctx: Contexto) -> list[object]:
    return [_logico(pred.evaluar(ContextoElemento(e, ligado, ctx)), "predicado") for e in elementos]


@dataclass(frozen=True)
class _Filtro(_Nodo):
    coleccion: _Nodo
    condicion: _Nodo

    def resultados(self, ctx: Contexto) -> object:
        """Lista de (elemento, resultado trivaluado) o NO_EVALUABLE si la coleccion falta."""
        col = self.coleccion.evaluar(ctx)
        if col is NO_EVALUABLE:
            return NO_EVALUABLE
        if not _es_coleccion(col):
            raise ErrorEvaluacionExpresion(
                f"`where` sobre algo que no es lista ni tupla: {type(col).__name__}"
            )
        ligado = self.coleccion.nombre if isinstance(self.coleccion, _Nombre) else None
        return [(e, _logico(self.condicion.evaluar(ContextoElemento(e, ligado, ctx)), "where")) for e in col]

    def evaluar(self, ctx: Contexto) -> object:
        pares = self.resultados(ctx)
        if pares is NO_EVALUABLE:
            return NO_EVALUABLE
        if any(r is NO_EVALUABLE for _, r in pares):
            return NO_EVALUABLE
        return [e for e, r in pares if r is True]

    def nombres(self) -> list[str]:
        return self.coleccion.nombres() + self.condicion.nombres()


@dataclass(frozen=True)
class _ForEach(_Nodo):
    coleccion: str
    cuerpo: _Nodo
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        col = ctx.resolver(self.coleccion)
        if col is NO_EVALUABLE:
            return NO_EVALUABLE
        if not _es_coleccion(col):
            raise ErrorEvaluacionExpresion(
                f"`for each {self.coleccion}` sobre algo que no es lista ni tupla: {type(col).__name__}"
            )
        if not col:
            return NO_EVALUABLE
        return _y(_iterar(self.cuerpo, self.coleccion, list(col), ctx))  # type: ignore[arg-type]

    def nombres(self) -> list[str]:
        return [self.coleccion] + self.cuerpo.nombres()


@dataclass(frozen=True)
class _Llamada(_Nodo):
    funcion: str
    args: tuple[_Nodo, ...]

    @property
    def es_predicado(self) -> bool:  # type: ignore[override]
        return self.funcion == "presente"

    def nombres(self) -> list[str]:
        return [n for a in self.args for n in a.nombres()]

    def evaluar(self, ctx: Contexto) -> object:
        return getattr(self, "_f_" + self.funcion)(ctx)

    # --- valores trivaluados de un argumento cuantificado ---------------------
    def _resultados(self, ctx: Contexto) -> object:
        """Para all/exists/count: lista trivaluada por elemento, o NO_EVALUABLE."""
        arg = self.args[0]
        if isinstance(arg, _Filtro):
            pares = arg.resultados(ctx)
            return pares if pares is NO_EVALUABLE else [r for _, r in pares]
        if arg.es_predicado:
            ligadura = _ligar(arg, ctx)
            if ligadura is None:
                return NO_EVALUABLE
            ligado, elementos = ligadura
            return _iterar(arg, ligado, elementos, ctx)
        valor = arg.evaluar(ctx)
        if valor is NO_EVALUABLE:
            return NO_EVALUABLE
        if isinstance(valor, Mapping):
            valor = list(valor.values())
        if not _es_coleccion(valor):
            raise ErrorEvaluacionExpresion(f"{self.funcion}(): se esperaba una lista")
        return list(valor)

    def _f_exists(self, ctx: Contexto) -> object:
        res = self._resultados(ctx)
        if res is NO_EVALUABLE:
            return NO_EVALUABLE
        if self.args[0].es_predicado or isinstance(self.args[0], _Filtro):
            return _o(res) if res else False  # type: ignore[arg-type]
        return len(res) > 0  # type: ignore[arg-type]

    def _f_all(self, ctx: Contexto) -> object:
        res = self._resultados(ctx)
        if res is NO_EVALUABLE:
            return NO_EVALUABLE
        return _y([_logico(r, "all") for r in res])  # type: ignore[union-attr]

    def _f_count(self, ctx: Contexto) -> object:
        res = self._resultados(ctx)
        if res is NO_EVALUABLE:
            return NO_EVALUABLE
        if self.args[0].es_predicado or isinstance(self.args[0], _Filtro):
            if any(r is NO_EVALUABLE for r in res):  # type: ignore[union-attr]
                return NO_EVALUABLE
            return sum(1 for r in res if r is True)  # type: ignore[union-attr]
        return len(res)  # type: ignore[arg-type]

    def _f_unique(self, ctx: Contexto) -> object:
        valor = self.args[0].evaluar(ctx)
        if valor is NO_EVALUABLE:
            return NO_EVALUABLE
        if isinstance(valor, Mapping):
            valores = list(valor.values())
        elif _es_coleccion(valor):
            valores = list(valor)  # type: ignore[arg-type]
        else:
            return True
        presentes = [v for v in valores if v is not None and v is not NO_EVALUABLE]
        if not presentes:
            return NO_EVALUABLE
        primero = presentes[0]
        # igualdad del tipo de los elementos (cadenas canonicas como cadenas); sin cortocircuito
        iguales = [_comparar("==", primero, v) for v in presentes[1:]]
        return all(iguales)

    def _f_sum(self, ctx: Contexto) -> object:
        valor = self.args[0].evaluar(ctx)
        if valor is NO_EVALUABLE:
            return NO_EVALUABLE
        if isinstance(valor, Mapping):
            valor = list(valor.values())
        if not _es_coleccion(valor):
            raise ErrorEvaluacionExpresion("sum(): se esperaba una lista")
        total = Decimal(0)
        for v in valor:  # type: ignore[union-attr]
            if v is NO_EVALUABLE or v is None:
                return NO_EVALUABLE
            total += _numero(v, "sum()")
        return total

    def _f_min(self, ctx: Contexto) -> object:
        valores = [a.evaluar(ctx) for a in self.args]
        if any(v is NO_EVALUABLE for v in valores):
            return NO_EVALUABLE
        normalizados = [_comparable(v, "min()") for v in valores]
        if all(_familia(v) == "fecha" for v in normalizados):
            return min(normalizados)  # type: ignore[type-var]
        return min(_numero(v, "min()") for v in normalizados)

    def _f_abs(self, ctx: Contexto) -> object:
        v = self.args[0].evaluar(ctx)
        return NO_EVALUABLE if v is NO_EVALUABLE else abs(_numero(v, "abs()"))

    def _f_sha256(self, ctx: Contexto) -> object:
        v = self.args[0].evaluar(ctx)
        if v is NO_EVALUABLE:
            return NO_EVALUABLE
        if isinstance(v, str):
            v = v.encode("utf-8")
        if not isinstance(v, (bytes, bytearray)):
            raise ErrorEvaluacionExpresion("sha256(): se esperaba str o bytes")
        return hashlib.sha256(v).hexdigest()

    def _f_presente(self, ctx: Contexto) -> object:
        elemento = self.args[0].evaluar(ctx)
        if elemento is NO_EVALUABLE:
            return NO_EVALUABLE
        funcion = ctx.resolver("presente")
        if isinstance(funcion, Callable):  # type: ignore[arg-type]
            try:
                resultado = funcion(elemento)
            except ErrorEvaluacionExpresion:
                raise
            except Exception as exc:
                raise ErrorEvaluacionExpresion(f"presente() lanzo {type(exc).__name__}: {exc}") from exc
            return _logico(_o_no_evaluable(resultado), "presente()")
        return _logico(_o_no_evaluable(_buscar(elemento, "presente")), "presente()")


# ---------------------------------------------------------------------------
# Parser (descenso recursivo)
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, texto: str, modo: str, enumerados: frozenset[str] | None) -> None:
        self.texto = texto
        self.modo = modo
        self.enumerados = enumerados
        self.tokens = _tokenizar(texto)
        self.i = 0
        self.profundidad = 0
        self.identificadores: set[str] = set()
        self.funciones: set[str] = set()
        self.literales_simbolicos: set[str] = set()
        self.colecciones_ligadas: set[str] = set()

    # --- utilidades ------------------------------------------------------------
    @property
    def actual(self) -> _Token:
        return self.tokens[self.i]

    def _es(self, tipo: str, valor: str | None = None) -> bool:
        t = self.actual
        return t.tipo == tipo and (valor is None or t.valor == valor)

    def _avanzar(self) -> _Token:
        t = self.actual
        self.i += 1
        return t

    def _esperar(self, tipo: str, valor: str | None = None) -> _Token:
        if not self._es(tipo, valor):
            esperado = valor or tipo
            raise self._error(f"se esperaba {esperado!r}")
        return self._avanzar()

    def _error(self, mensaje: str) -> ErrorCargaExpresion:
        t = self.actual
        donde = f"posicion {t.pos}" + (f" ({t.valor!r})" if t.valor else " (fin)")
        return ErrorCargaExpresion(f"{mensaje} en {donde}: {self.texto!r}")

    def _entrar(self) -> None:
        self.profundidad += 1
        if self.profundidad > PROFUNDIDAD_MAXIMA:
            raise self._error(f"anidamiento superior a {PROFUNDIDAD_MAXIMA} niveles")

    def _salir(self) -> None:
        self.profundidad -= 1

    def _es_enumerado(self, nombre: str) -> bool:
        return self.enumerados is not None and "." not in nombre and nombre in self.enumerados

    # --- gramatica -------------------------------------------------------------
    def parsear(self) -> _Nodo:
        nodo = self.expresion()
        if not self._es("FIN"):
            raise self._error("tokens sobrantes")
        return nodo

    def expresion(self) -> _Nodo:
        if self._es("PALABRA", "for"):
            self._avanzar()
            self._esperar("PALABRA", "each")
            nombre = self._esperar("NOMBRE").valor  # posicion de ligadura: siempre coleccion
            self.identificadores.add(nombre)
            self.colecciones_ligadas.add(nombre)
            self._esperar("OP", ":")
            self._entrar()
            try:
                return _ForEach(nombre, self.expresion())
            finally:
                self._salir()
        return self.implicacion()

    def implicacion(self) -> _Nodo:
        izq = self.disyuncion()
        if self._es("OP", "->"):
            self._avanzar()
            self._entrar()
            try:
                return _Implicacion(izq, self.implicacion())
            finally:
                self._salir()
        return izq

    def disyuncion(self) -> _Nodo:
        partes = [self.conjuncion()]
        while self._es("PALABRA", "or"):
            self._avanzar()
            partes.append(self.conjuncion())
        return partes[0] if len(partes) == 1 else _Or(tuple(partes))

    def conjuncion(self) -> _Nodo:
        partes = [self.negacion()]
        while self._es("PALABRA", "and"):
            self._avanzar()
            partes.append(self.negacion())
        return partes[0] if len(partes) == 1 else _And(tuple(partes))

    def negacion(self) -> _Nodo:
        if self._es("PALABRA", "not"):
            self._avanzar()
            self._entrar()
            try:
                return _Not(self.negacion())
            finally:
                self._salir()
        return self.comparacion()

    def comparacion(self) -> _Nodo:
        izq = self.suma()
        if self._es("PALABRA", "in"):
            self._avanzar()
            return _Pertenencia(izq, self.suma())
        if self._es("OP") and self.actual.valor in _COMPARADORES:
            op = self._avanzar().valor
            return _Comparacion(op, izq, self.suma(), heuristica=self.enumerados is None)
        return izq

    def suma(self) -> _Nodo:
        izq = self.producto()
        while self._es("OP") and self.actual.valor in ("+", "-"):
            op = self._avanzar().valor
            izq = _Binario(op, izq, self.producto())
        return izq

    def producto(self) -> _Nodo:
        izq = self.unario()
        while self._es("OP") and self.actual.valor in ("*", "/"):
            op = self._avanzar().valor
            izq = _Binario(op, izq, self.unario())
        return izq

    def unario(self) -> _Nodo:
        if self._es("OP") and self.actual.valor in ("-", "+"):
            op = self._avanzar().valor
            self._entrar()
            try:
                return _Unario(op, self.unario())
            finally:
                self._salir()
        return self.potencia()

    def potencia(self) -> _Nodo:
        base = self.primario()
        if self._es("OP", "**"):
            if self.modo != "formula":
                raise self._error("`**` solo se admite en modo formula")
            self._avanzar()
            self._entrar()
            try:
                return _Binario("**", base, self.unario())
            finally:
                self._salir()
        return base

    def primario(self) -> _Nodo:
        t = self.actual
        if t.tipo == "NUMERO":
            self._avanzar()
            numero = Decimal(t.valor)
            if self._es("PALABRA") and self.actual.valor in _UNIDADES_FECHA:
                unidad = _UNIDADES_FECHA[self._avanzar().valor]
                return _DuracionNodo(_Duracion(numero, unidad))
            return _Literal(numero)
        if t.tipo == "CADENA":
            self._avanzar()
            return _Literal(t.valor)
        if t.tipo == "ORIGEN":
            self._avanzar()
            return _Literal(t.valor)
        if t.tipo == "PALABRA" and t.valor in ("true", "false"):
            self._avanzar()
            return _Literal(t.valor == "true")
        if t.tipo == "OP" and t.valor == "[":
            return self.lista()
        if t.tipo == "OP" and t.valor == "(":
            self._avanzar()
            self._entrar()
            try:
                nodo = self.expresion()
            finally:
                self._salir()
            self._esperar("OP", ")")
            return nodo
        if t.tipo == "NOMBRE":
            self._avanzar()
            if self._es("OP", "("):
                return self.llamada(t.valor)
            if self._es("PALABRA", "where"):  # posicion de ligadura: siempre coleccion
                self._avanzar()
                self.identificadores.add(t.valor)
                self.colecciones_ligadas.add(t.valor)
                self._entrar()
                try:
                    return _Filtro(_Nombre(t.valor), self.implicacion())
                finally:
                    self._salir()
            if self._es_enumerado(t.valor):
                self.literales_simbolicos.add(t.valor)
                return _Literal(t.valor)
            self.identificadores.add(t.valor)
            return _Nombre(t.valor)
        if t.tipo == "PALABRA":
            raise self._error(f"palabra reservada {t.valor!r} fuera de lugar")
        raise self._error("expresion incompleta" if t.tipo == "FIN" else "token inesperado")

    def lista(self) -> _Nodo:
        self._esperar("OP", "[")
        elementos: list[_Nodo] = []
        while not self._es("OP", "]"):
            if elementos:
                self._esperar("OP", ",")
            elementos.append(self.literal_de_lista())
        self._avanzar()
        return _Lista(tuple(elementos))

    def literal_de_lista(self) -> _Nodo:
        t = self._avanzar()
        if t.tipo == "NUMERO":
            return _Literal(Decimal(t.valor))
        if t.tipo in ("CADENA", "ORIGEN"):
            return _Literal(t.valor)
        if t.tipo == "NOMBRE":
            if self.enumerados is not None and not self._es_enumerado(t.valor):
                self.i -= 1
                raise self._error(f"{t.valor!r} no es un enumerado declarado por la spec")
            self.literales_simbolicos.add(t.valor)
            return _Literal(t.valor)
        if t.tipo == "PALABRA" and t.valor in ("true", "false"):
            return _Literal(t.valor == "true")
        self.i -= 1
        raise self._error("elemento de lista no valido (numero, cadena, true/false o literal simbolico)")

    def llamada(self, nombre: str) -> _Nodo:
        if nombre not in FUNCIONES_PERMITIDAS:
            raise self._error(f"funcion desconocida {nombre!r}; permitidas: {sorted(FUNCIONES_PERMITIDAS)}")
        self._esperar("OP", "(")
        args: list[_Nodo] = []
        self._entrar()
        try:
            while not self._es("OP", ")"):
                if args:
                    self._esperar("OP", ",")
                args.append(self.expresion())
        finally:
            self._salir()
        self._avanzar()
        minimo, maximo = _ARIDAD[nombre]
        if len(args) < minimo or (maximo is not None and len(args) > maximo):
            raise self._error(
                f"{nombre}() recibe {minimo if maximo == minimo else f'{minimo}+'} argumento(s)"
            )
        self.funciones.add(nombre)
        return _Llamada(nombre, tuple(args))


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expresion:
    """Expresion compilada. `evaluar` da bool | NO_EVALUABLE (logica) o Decimal | NO_EVALUABLE (formula).

    - `identificadores`: nombres que el contexto debe resolver (incluye las `colecciones_ligadas`).
    - `literales_simbolicos`: nombres resueltos como cadena al compilar (los de `[...]` y, con
      `enumerados`, los del conjunto). Nunca se resuelven en el contexto.
    - `colecciones_ligadas`: nombres en posicion `for each NOMBRE:` / `NOMBRE where`.
    - `enumerados`: el conjunto con el que se compilo, o `None` (heuristica de F0.1).
    """

    texto: str
    modo: str
    identificadores: frozenset[str]
    funciones: frozenset[str]
    literales_simbolicos: frozenset[str]
    colecciones_ligadas: frozenset[str]
    enumerados: frozenset[str] | None
    _arbol: _Nodo

    def evaluar(self, contexto: Contexto) -> object:
        resultado = self._arbol.evaluar(contexto)
        if resultado is NO_EVALUABLE:
            return NO_EVALUABLE
        if self.modo == "logica":
            return _logico(resultado, f"resultado de {self.texto!r}")
        if isinstance(resultado, bool) or (
            isinstance(resultado, date) and not isinstance(resultado, datetime)
        ):
            return resultado
        return _numero(resultado, f"resultado de {self.texto!r}")


def compilar(texto: str, *, modo: str = "logica", enumerados: Iterable[str] | None = None) -> Expresion:
    """Compila `logica` o `formula`. Vocabulario fuera de lista blanca → ErrorCargaExpresion.

    `enumerados`: valores simbolicos que la spec declara (`variables.*.valores`, `ambito.tipos_equipo_*`,
    tipos de evidencia, categorias de linea). Si se pasa, un nombre del conjunto es siempre literal y uno
    ajeno siempre identificador; si es `None`, se aplica la heuristica de F0.1 en evaluacion.
    """
    if modo not in MODOS:
        raise ErrorCargaExpresion(f"modo desconocido {modo!r}; usa {MODOS}")
    if not isinstance(texto, str) or not texto.strip():
        raise ErrorCargaExpresion("expresion vacia")
    conjunto: frozenset[str] | None = None
    if enumerados is not None:
        if isinstance(enumerados, (str, bytes)):
            raise ErrorCargaExpresion("`enumerados` debe ser un conjunto de cadenas, no una cadena")
        conjunto = frozenset(enumerados)
        for e in conjunto:
            if not isinstance(e, str) or not e:
                raise ErrorCargaExpresion(f"enumerado no valido {e!r}: se esperaba una cadena no vacia")
            if e in _PALABRAS or e.lower() in _NOMBRES_PROHIBIDOS:
                raise ErrorCargaExpresion(f"enumerado {e!r} choca con una palabra reservada del lenguaje")
    parser = _Parser(texto, modo, conjunto)
    try:
        arbol = parser.parsear()
    except RecursionError as exc:  # red de seguridad; la guarda de profundidad actua antes
        raise ErrorCargaExpresion(f"expresion demasiado anidada: {texto[:80]!r}") from exc
    return Expresion(
        texto=texto,
        modo=modo,
        identificadores=frozenset(parser.identificadores),
        funciones=frozenset(parser.funciones),
        literales_simbolicos=frozenset(parser.literales_simbolicos),
        colecciones_ligadas=frozenset(parser.colecciones_ligadas),
        enumerados=conjunto,
        _arbol=arbol,
    )


__all__ = [
    "FUNCIONES_PERMITIDAS",
    "MODOS",
    "NO_EVALUABLE",
    "PROFUNDIDAD_MAXIMA",
    "Contexto",
    "ContextoDict",
    "ContextoElemento",
    "ErrorCargaExpresion",
    "ErrorEvaluacionExpresion",
    "Expresion",
    "compilar",
]
