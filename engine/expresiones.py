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
- ORIGEN: `prefijo:identificador` sin espacios (`tabla:REG1781_CUADRO6`) es un literal de origen que se
  compara como la cadena `"tabla:REG1781_CUADRO6"`. Los dos puntos de `for each x: ...` van seguidos de
  espacio y no se pegan.
- Palabras reservadas: `and or not in where for each true false` y las unidades de fecha.

Semantica:

- Tres valores: `True`, `False` y el centinela `NO_EVALUABLE`. `and`: algun `False` → `False`; todos
  `True` → `True`; si no → `NO_EVALUABLE`. `or`: algun `True` → `True`; todos `False` → `False`; si no
  → `NO_EVALUABLE`. `not NO_EVALUABLE` → `NO_EVALUABLE`. `a -> b` ≡ `not a or b` (ADR-001 C7).
- Un identificador ausente resuelve a `NO_EVALUABLE`, nunca a excepcion. Solo un contexto mal construido
  (`float`, tipos incomparables, escalar donde se esperaba coleccion) lanza `ErrorEvaluacionExpresion`.
- Literales simbolicos (enumerados sin comillas): un NOMBRE sin punto que el contexto no resuelve se toma
  como cadena con su propio nombre SOLO en el lado derecho de `==`/`!=` y SOLO si el lado izquierdo es una
  cadena (un enumerado se compara con texto; `kw_motor == PM` con `PM` ausente es `NO_EVALUABLE`). Dentro
  de una lista literal `[motor, bomba]` los nombres son siempre simbolicos (nunca se resuelven). En
  cualquier otra posicion un nombre ausente es `NO_EVALUABLE`.
- Regla de ligadura en `all(...)`, `exists(...)` y `count(...)`: si el argumento es un predicado (no un
  simple nombre ni un filtro), la variable ligada es el primer nombre del predicado, en orden de aparicion,
  que el contexto entrega como coleccion iterable (se prueba el nombre completo con puntos y despues su
  raiz). Cada elemento se evalua con un `ContextoElemento`: `raiz.atributo` se lee del elemento, `raiz`
  es el propio elemento, el resto de nombres se buscan primero en el elemento y despues en el contexto
  exterior. `coleccion where cond` y `for each coleccion: expr` ligan del mismo modo.
- Agregaciones trivaluadas: `exists` → algun `True` → `True`, si no algun `NO_EVALUABLE` → `NO_EVALUABLE`,
  si no `False` (vacio → `False`). `all` → algun `False` → `False`, si no algun `NO_EVALUABLE` →
  `NO_EVALUABLE`, si no `True` (vacio → `True`). `for each` igual que `all` pero coleccion vacia →
  `NO_EVALUABLE` (no hay unidad sobre la que evaluar). `count(pred)` → `NO_EVALUABLE` si algun elemento
  lo es; `count(coleccion)` → su tamaño; `count([])` → 0.
- `unique(x)`: `True` si todos los valores presentes (no `None`/`NO_EVALUABLE`) son iguales; un valor →
  `True`; escalar → `True`; sin valores → `NO_EVALUABLE`. Con un `dict` compara los valores (tipo_doc →
  valor). No aplica tolerancias ni normalizacion: eso lo hace el consolidador antes.
- Aritmetica solo con `Decimal` (los `int` del contexto se convierten). `date + duracion` suma años, meses
  o dias. Comparacion de `Decimal` con `NO_EVALUABLE` → `NO_EVALUABLE`.
- `sha256(x)`: `x` es `str` (UTF-8) o `bytes`; devuelve el hexdigest.
- `presente(doc)`: llama a la funcion `presente` del contexto sobre el elemento; si el contexto no la
  ofrece y el elemento tiene el atributo `presente`, se usa; si no, `NO_EVALUABLE`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
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
_COMPARADORES = frozenset({"==", "!=", "<", "<=", ">", ">="})


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
            else:
                tokens.append(_Token("PALABRA" if nombre in _PALABRAS else "NOMBRE", nombre, i))
        elif m.group("OP") is not None:
            tokens.append(_Token("OP", m.group("OP"), i))
        else:
            raise ErrorCargaExpresion(
                f"caracter no reconocido {m.group('ERROR')!r} en posicion {i}: {texto!r}"
            )
    tokens.append(_Token("FIN", "", len(texto)))
    return tokens


# ---------------------------------------------------------------------------
# Arbol sintactico y evaluacion
# ---------------------------------------------------------------------------


def _es_coleccion(valor: object) -> bool:
    return isinstance(valor, (list, tuple, set, frozenset))


def _numero(valor: object, que: str) -> Decimal:
    if isinstance(valor, bool):
        raise ErrorEvaluacionExpresion(f"{que}: se esperaba un numero y llego un booleano")
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        raise ErrorEvaluacionExpresion(f"{que}: float no permitido ({valor!r}); usa Decimal")
    raise ErrorEvaluacionExpresion(f"{que}: se esperaba un numero y llego {type(valor).__name__}")


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


def _coercionar(a: object, b: object) -> tuple[object, object]:
    """Iguala tipos comparables: int → Decimal; str numerica frente a Decimal → Decimal."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a, b
    if isinstance(a, float) or isinstance(b, float):
        raise ErrorEvaluacionExpresion("comparacion con float no permitida; usa Decimal")
    if isinstance(a, int):
        a = Decimal(a)
    if isinstance(b, int):
        b = Decimal(b)
    if isinstance(a, Decimal) and isinstance(b, str):
        b = _decimal_o_texto(b)
    elif isinstance(b, Decimal) and isinstance(a, str):
        a = _decimal_o_texto(a)
    return a, b


def _decimal_o_texto(texto: str) -> object:
    try:
        return Decimal(texto.strip())
    except (DecimalException, ValueError):
        return texto


def _comparar(op: str, a: object, b: object) -> bool:
    a, b = _coercionar(a, b)
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    misma_familia = (
        (isinstance(a, Decimal) and isinstance(b, Decimal))
        or (isinstance(a, date) and isinstance(b, date))
        or (isinstance(a, str) and isinstance(b, str))
    )
    if not misma_familia:
        raise ErrorEvaluacionExpresion(
            f"no se puede ordenar {type(a).__name__} {op} {type(b).__name__} ({a!r}, {b!r})"
        )
    if op == "<":
        return a < b  # type: ignore[operator]
    if op == "<=":
        return a <= b  # type: ignore[operator]
    if op == ">":
        return a > b  # type: ignore[operator]
    return a >= b  # type: ignore[operator]


@dataclass(frozen=True)
class _Duracion:
    cantidad: Decimal
    unidad: str  # "años" | "meses" | "dias"


def _sumar_fecha(fecha: date, duracion: _Duracion, signo: int) -> date:
    if duracion.cantidad != duracion.cantidad.to_integral_value():
        raise ErrorEvaluacionExpresion(f"duracion no entera: {duracion.cantidad} {duracion.unidad}")
    n = int(duracion.cantidad) * signo
    if duracion.unidad == "dias":
        return fecha + timedelta(days=n)
    meses_totales = fecha.month - 1 + (n * 12 if duracion.unidad == "años" else n)
    anio = fecha.year + meses_totales // 12
    mes = meses_totales % 12 + 1
    dia = min(fecha.day, _dias_del_mes(anio, mes))
    return fecha.replace(year=anio, month=mes, day=dia)


def _dias_del_mes(anio: int, mes: int) -> int:
    siguiente = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return (siguiente - date(anio, mes, 1)).days


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
    es_predicado = True

    def evaluar(self, ctx: Contexto) -> object:
        a = self.izq.evaluar(ctx)
        b = self.der.evaluar(ctx)
        if (
            b is NO_EVALUABLE
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
            raise ErrorEvaluacionExpresion(f"`in` sobre algo que no es coleccion: {type(col).__name__}")
        return any(_comparar("==", a, x) for x in col if x is not NO_EVALUABLE and x is not None)

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
    """Primer nombre del predicado (completo, luego su raiz) que el contexto entrega como coleccion."""
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
            raise ErrorEvaluacionExpresion(f"`where` sobre algo que no es coleccion: {type(col).__name__}")
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
            raise ErrorEvaluacionExpresion(f"`for each {self.coleccion}` sobre algo que no es coleccion")
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
            raise ErrorEvaluacionExpresion(f"{self.funcion}(): se esperaba una coleccion")
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
        return all(_comparar("==", primero, v) for v in presentes[1:])

    def _f_sum(self, ctx: Contexto) -> object:
        valor = self.args[0].evaluar(ctx)
        if valor is NO_EVALUABLE:
            return NO_EVALUABLE
        if isinstance(valor, Mapping):
            valor = list(valor.values())
        if not _es_coleccion(valor):
            raise ErrorEvaluacionExpresion("sum(): se esperaba una coleccion")
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
        if all(isinstance(v, date) for v in valores):
            return min(valores)  # type: ignore[type-var]
        return min(_numero(v, "min()") for v in valores)

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
            return _logico(_o_no_evaluable(funcion(elemento)), "presente()")
        return _logico(_o_no_evaluable(_buscar(elemento, "presente")), "presente()")


# ---------------------------------------------------------------------------
# Parser (descenso recursivo)
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, texto: str, modo: str) -> None:
        self.texto = texto
        self.modo = modo
        self.tokens = _tokenizar(texto)
        self.i = 0
        self.identificadores: set[str] = set()
        self.funciones: set[str] = set()

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
            nombre = self._esperar("NOMBRE").valor
            self.identificadores.add(nombre)
            self._esperar("OP", ":")
            return _ForEach(nombre, self.expresion())
        return self.implicacion()

    def implicacion(self) -> _Nodo:
        izq = self.disyuncion()
        if self._es("OP", "->"):
            self._avanzar()
            return _Implicacion(izq, self.implicacion())
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
            return _Not(self.negacion())
        return self.comparacion()

    def comparacion(self) -> _Nodo:
        izq = self.suma()
        if self._es("PALABRA", "in"):
            self._avanzar()
            return _Pertenencia(izq, self.suma())
        if self._es("OP") and self.actual.valor in _COMPARADORES:
            op = self._avanzar().valor
            return _Comparacion(op, izq, self.suma())
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
            return _Unario(op, self.unario())
        return self.potencia()

    def potencia(self) -> _Nodo:
        base = self.primario()
        if self._es("OP", "**"):
            if self.modo != "formula":
                raise self._error("`**` solo se admite en modo formula")
            self._avanzar()
            return _Binario("**", base, self.unario())
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
            nodo = self.expresion()
            self._esperar("OP", ")")
            return nodo
        if t.tipo == "NOMBRE":
            self._avanzar()
            if self._es("OP", "("):
                return self.llamada(t.valor)
            self.identificadores.add(t.valor)
            if self._es("PALABRA", "where"):
                self._avanzar()
                return _Filtro(_Nombre(t.valor), self.implicacion())
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
        if t.tipo in ("CADENA", "ORIGEN", "NOMBRE"):
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
        while not self._es("OP", ")"):
            if args:
                self._esperar("OP", ",")
            args.append(self.expresion())
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
    """Expresion compilada. `evaluar` da bool | NO_EVALUABLE (logica) o Decimal | NO_EVALUABLE (formula)."""

    texto: str
    modo: str
    identificadores: frozenset[str]
    funciones: frozenset[str]
    _arbol: _Nodo

    def evaluar(self, contexto: Contexto) -> object:
        resultado = self._arbol.evaluar(contexto)
        if resultado is NO_EVALUABLE:
            return NO_EVALUABLE
        if self.modo == "logica":
            return _logico(resultado, f"resultado de {self.texto!r}")
        if isinstance(resultado, (Decimal, date, bool)):
            return resultado
        if isinstance(resultado, int):
            return Decimal(resultado)
        return _numero(resultado, f"resultado de {self.texto!r}")


def compilar(texto: str, *, modo: str = "logica") -> Expresion:
    """Compila `logica` o `formula`. Vocabulario fuera de lista blanca → ErrorCargaExpresion."""
    if modo not in MODOS:
        raise ErrorCargaExpresion(f"modo desconocido {modo!r}; usa {MODOS}")
    if not isinstance(texto, str) or not texto.strip():
        raise ErrorCargaExpresion("expresion vacia")
    parser = _Parser(texto, modo)
    arbol = parser.parsear()
    return Expresion(
        texto=texto,
        modo=modo,
        identificadores=frozenset(parser.identificadores),
        funciones=frozenset(parser.funciones),
        _arbol=arbol,
    )


__all__ = [
    "FUNCIONES_PERMITIDAS",
    "MODOS",
    "NO_EVALUABLE",
    "Contexto",
    "ContextoDict",
    "ContextoElemento",
    "ErrorCargaExpresion",
    "ErrorEvaluacionExpresion",
    "Expresion",
    "compilar",
]
