"""Motor de calculo (N3): evalua la formula de la ficha con `Decimal` a partir de la spec, sin cablear nada.

Dos funciones publicas:

- `planificar(spec_datos, tablas) -> Plan`: lee y **valida** todo lo que el calculo necesita de la spec y lo
  compila una vez. Es la unica puerta de validacion del bloque `calculo` y de las derivaciones: el Spec
  Registry (`engine/spec_registry.py`, `cargar_spec`) la invoca al cargar una ficha, de modo que una spec que
  el registro activa es, por construccion, calculable (dependencia `spec_registry → calculo`, hacia dentro).
  Toda incoherencia de la spec es `ErrorCalculo` aqui, nunca en `calcular`.
- `calcular(spec_datos, unidades, tablas, *, provisional, fecha, plan=None) -> ResultadoCalculo`: ejecuta el
  plan sobre las entradas consolidadas de cada unidad. Acepta un `Plan` ya construido; si no, lo construye.

Lo que `planificar` lee del YAML de la ficha (`docs/04` §7, regla de oro 4) y el criterio que aplica:

- `calculo.aritmetica`: obligatoria e igual a `decimal_exacta`; otra cosa es error (solo hay un motor).
- `calculo.motor` y `calculo.total`: obligatorios, con `salida` y `formula`. La formula por unidad compila en
  modo `formula` y sus identificadores son variables de la spec (entradas o derivadas); la del total compila y
  referencia exactamente la salida por unidad (se evalua sobre la lista de salidas).
- `variables.<nombre>` con `evidencia: derivado` y bloque `derivacion`; criterio unico (ADR-002 §3, QA-2):
  (a) `fuente` documental (no empieza por `tabla:`) → `metodo` es prosa y **nunca** se compila: la variable es
      entrada del consolidador (`entradas_requeridas`) y su `interpretacion` va a
      `interpretaciones_por_entrada`;
  (b) `fuente: tabla:<ID>` → `<ID>` debe estar en `tablas` y `clave` (variable de la spec) es obligatoria;
  (c) sin `fuente` → `metodo` debe compilar en modo `formula` y sus identificadores ser variables de la spec
      distintas de si misma. Ciclos entre derivadas → error. Se evaluan en orden topologico.
- `calculo.precondiciones[]`: modo `logica`. Una precondicion es **prosa** si no contiene ningun caracter de
  operador ni parentesis (`< > = ! + - * / ( ) [ ]`), es decir, solo palabras: entonces se delega a
  `reglas.py` (`precondiciones_delegadas`) con nota en la traza. Todo lo demas debe compilar y referenciar
  variables de la spec; una errata o funcion desconocida es error de planificacion, nunca una delegacion.
- `calculo.controles_fisicos[]`: `id` y `regla` (modo `logica`, identificadores = variables o salida por
  unidad); si alguno falla, el resultado de la unidad se **retira**.
- `calculo.redondeo_salida.<salida_total>_cae` + `interpretacion`: el codigo solo implementa "truncar"
  (hacia cero, a kWh entero). El criterio, normalizado (minusculas, sin tildes, espacios simples), debe ser
  exactamente `truncar a kwh entero` o empezar por la palabra `truncar`; otro criterio es error.

Reglas de implementacion que este modulo garantiza:

- `Decimal` de extremo a extremo con precision fija `PRECISION_DECIMAL` en un `localcontext`, independiente
  del contexto global. Ninguna entrada puede ser `float` ni texto (`ErrorCalculo`: contexto mal construido).
- Una variable derivable por la spec que llegue en `unidades` (p. ej. la fraccion de perdidas tomada de la
  ficha del variador) se **ignora** con aviso: el valor sale siempre de la derivacion declarada.
- Los errores de una unidad son de esa unidad: una entrada `None` (valor consumido nulo por conflicto o
  ausencia) o un error de evaluacion (division por cero) dejan `motivo_no_calculo` en la unidad y el total sin
  publicar; nunca una excepcion global.
- Nada de `eval`; toda cadena de la spec pasa por `engine.expresiones.compilar`. Ningun nombre de variable de
  la ficha aparece en este modulo: `ResultadoUnidad.fuentes[<variable>]` es la API de origen de cada derivada.
- No importa nada de agentes/, salida/, generator/ ni tests/.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal, localcontext

from engine.expresiones import (
    NO_EVALUABLE,
    ContextoDict,
    ErrorCargaExpresion,
    ErrorEvaluacionExpresion,
    Expresion,
    compilar,
)
from engine.tablas import ErrorTabla, Tabla

PRECISION_DECIMAL = 34
PREFIJO_TABLA = "tabla:"
EVIDENCIA_DERIVADA = "derivado"
ARITMETICA_SOPORTADA = "decimal_exacta"
SUFIJO_CAE = "_cae"
CRITERIO_TRUNCAR = "truncar"
CRITERIO_TRUNCAR_CANONICO = "truncar a kwh entero"
ORIGEN_DERIVADO = "derivado"
CARACTERES_EXPRESION = frozenset("<>=!+-*/()[]")


class ErrorCalculo(Exception):
    """Spec de calculo incompleta o no soportada, tabla ausente, entrada mal tipada o contexto mal formado."""


# ---------------------------------------------------------------------------
# Resultado (contrato ADR-002 §2.5)
# ---------------------------------------------------------------------------


@dataclass
class ResultadoUnidad:
    """Calculo de una unidad (motor). `salida` es `None` si no se calculo o se retiro (ver motivo)."""

    num_serie_motor: str
    entradas: dict[str, Decimal]
    derivadas: dict[str, Decimal]
    salida: Decimal | None
    controles: dict[str, object]  # id -> bool | NO_EVALUABLE
    precondiciones: dict[str, object]  # texto -> bool | NO_EVALUABLE
    interpretaciones: list[str]
    avisos: list[str]
    motivo_no_calculo: str | None
    fuentes: dict[str, str]  # variable derivada -> "tabla:<ID>" | "derivado" | "derivado(tabla:A,tabla:B)"


@dataclass
class ResultadoCalculo:
    """Resultado del calculo de una actuacion. `total` es `None` si alguna unidad no calcula o se retira."""

    por_unidad: list[ResultadoUnidad]
    total: Decimal | None
    total_cae: int | None
    traza: list[str]
    provisional: bool
    motivo_no_calculo: str | None
    interpretaciones: list[str]
    avisos: list[str]
    controles_ok: object  # bool | NO_EVALUABLE
    precondiciones_ok: object  # bool | NO_EVALUABLE
    precondiciones_delegadas: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan de calculo: lo que la spec declara, validado y compilado una vez
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Derivada:
    """Variable que este modulo deriva. `fuente` es `tabla:<ID>` (busqueda por `clave`) o `None` (formula)."""

    nombre: str
    fuente: str | None
    clave: str | None
    expresion: Expresion | None
    metodo: str
    dependencias: frozenset[str]
    origen: str  # trazabilidad para `fuentes`: "tabla:<ID>" | "derivado" | "derivado(tabla:A,tabla:B)"
    interpretacion: str | None
    si_no_existe_fila: str | None

    @property
    def es_tabla(self) -> bool:
        return self.fuente is not None


@dataclass(frozen=True)
class Control:
    id: str
    expresion: Expresion
    mensaje: str | None


@dataclass(frozen=True)
class Redondeo:
    clave: str  # "<salida_total>_cae"
    criterio: str  # texto original de la spec
    interpretacion: str | None


@dataclass(frozen=True)
class Plan:
    """Todo lo que `calcular` necesita, ya validado. Lo construye `planificar`; lo consume `calcular`.

    - `derivadas`: en orden topologico; cada una con su expresion (o tabla y clave), origen e interpretacion.
    - `entradas_requeridas`: variables que deben llegar del consolidador (las referencian la formula, las
      precondiciones, los controles o las derivadas y la spec no las deriva aqui).
    - `precondiciones`: compiladas (`Expresion.texto` conserva el texto); `precondiciones_delegadas`: prosa.
    - `controles`: id → `Control` (expresion compilada y mensaje).
    - `criterio_redondeo`: `None` si la spec no declara `redondeo_salida.<salida_total>_cae`.
    - `interpretaciones_estaticas`: las que aplica siempre que calcula (derivaciones por formula, redondeo).
    - `interpretaciones_por_entrada`: variable de entrada → INT de su `derivacion.interpretacion`; se aplican
      cuando la entrada se consume.
    """

    salida_unidad: str
    formula_unidad: Expresion
    salida_total: str
    formula_total: Expresion
    derivadas: tuple[Derivada, ...]
    entradas_requeridas: frozenset[str]
    precondiciones: tuple[Expresion, ...]
    precondiciones_delegadas: tuple[str, ...]
    controles: Mapping[str, Control]
    criterio_redondeo: Redondeo | None
    interpretaciones_estaticas: tuple[str, ...]
    interpretaciones_por_entrada: Mapping[str, str]
    subexpresiones: tuple[Expresion, ...]
    notas: tuple[str, ...]

    @property
    def derivables(self) -> frozenset[str]:
        return frozenset(d.nombre for d in self.derivadas)


def _leer(datos: object, ruta: str, contexto: str = "spec") -> object:
    actual = datos
    for parte in ruta.split("."):
        if not isinstance(actual, Mapping) or parte not in actual or actual[parte] is None:
            raise ErrorCalculo(f"{contexto}: falta `{ruta}`")
        actual = actual[parte]
    return actual


def _leer_texto(datos: object, ruta: str) -> str:
    valor = _leer(datos, ruta)
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorCalculo(f"spec: `{ruta}` debe ser una cadena no vacia")
    return valor


def _compilar(texto: str, modo: str, que: str) -> Expresion:
    try:
        return compilar(texto, modo=modo)
    except ErrorCargaExpresion as exc:
        raise ErrorCalculo(f"spec: {que} {texto!r} no compila ({exc})") from exc


def _exigir_identificadores(expresion: Expresion, permitidos: frozenset[str], que: str) -> None:
    ajenos = sorted(expresion.identificadores - permitidos)
    if ajenos:
        raise ErrorCalculo(
            f"spec: {que} {expresion.texto!r} referencia nombres que la spec no declara: {', '.join(ajenos)}"
        )


def es_prosa(texto: str) -> bool:
    """Precondicion de procedimiento: solo palabras, sin ningun caracter de operador ni parentesis."""
    return not any(c in CARACTERES_EXPRESION for c in texto)


def normalizar_criterio(criterio: str) -> str:
    """Minusculas, sin tildes, espacios simples: para comparar el criterio de redondeo de la spec."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", criterio) if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


def _derivadas(variables: Mapping, tablas: Mapping[str, Tabla]) -> tuple[Derivada, ...]:
    """Variables `evidencia: derivado` que este modulo deriva (criterio (b) y (c)), en orden topologico."""
    nombres = frozenset(str(n) for n in variables)
    candidatas: dict[str, Derivada] = {}
    for nombre, declaracion in variables.items():
        nombre = str(nombre)
        if not isinstance(declaracion, Mapping) or declaracion.get("evidencia") != EVIDENCIA_DERIVADA:
            continue
        ctx = f"spec: variables.{nombre}.derivacion"
        derivacion = declaracion.get("derivacion")
        if not isinstance(derivacion, Mapping):
            raise ErrorCalculo(f"{ctx}: una variable 'derivado' debe declarar `derivacion`")
        fuente = derivacion.get("fuente")
        if fuente is not None and not isinstance(fuente, str):
            raise ErrorCalculo(f"{ctx}.fuente: debe ser una cadena")
        metodo = derivacion.get("metodo")
        interpretacion = derivacion.get("interpretacion")
        if isinstance(fuente, str) and not fuente.startswith(PREFIJO_TABLA):
            continue  # (a) fuente documental: el metodo es prosa; la deriva el consolidador
        if isinstance(fuente, str):  # (b) tabla
            id_tabla = fuente[len(PREFIJO_TABLA) :]
            if id_tabla not in tablas:
                raise ErrorCalculo(f"{ctx}.fuente cita la tabla {id_tabla!r} y no esta cargada")
            clave = derivacion.get("clave")
            if not isinstance(clave, str) or not clave:
                raise ErrorCalculo(f"{ctx}.clave es obligatoria para una fuente de tabla")
            if clave not in nombres or clave == nombre:
                raise ErrorCalculo(f"{ctx}.clave {clave!r} no es otra variable de la spec")
            sin_fila = derivacion.get("si_no_existe_fila")
            candidatas[nombre] = Derivada(
                nombre=nombre,
                fuente=fuente,
                clave=clave,
                expresion=None,
                metodo=str(metodo or ""),
                dependencias=frozenset({clave}),
                origen=fuente,
                interpretacion=str(interpretacion) if interpretacion else None,
                si_no_existe_fila=str(sin_fila) if sin_fila else None,
            )
            continue
        # (c) sin fuente: el metodo es una formula sobre otras variables de la spec
        if not isinstance(metodo, str) or not metodo.strip():
            raise ErrorCalculo(f"{ctx}: sin `fuente` debe declarar `metodo` (formula)")
        expresion = _compilar(metodo, "formula", f"variables.{nombre}.derivacion.metodo")
        if nombre in expresion.identificadores:
            raise ErrorCalculo(f"{ctx}.metodo {metodo!r} es autorreferente")
        if not expresion.identificadores:
            raise ErrorCalculo(f"{ctx}.metodo {metodo!r} no depende de ninguna variable")
        _exigir_identificadores(expresion, nombres, f"variables.{nombre}.derivacion.metodo")
        candidatas[nombre] = Derivada(
            nombre=nombre,
            fuente=None,
            clave=None,
            expresion=expresion,
            metodo=metodo,
            dependencias=expresion.identificadores,
            origen=ORIGEN_DERIVADO,
            interpretacion=str(interpretacion) if interpretacion else None,
            si_no_existe_fila=None,
        )
    return _ordenar(candidatas)


def _ordenar(candidatas: dict[str, Derivada]) -> tuple[Derivada, ...]:
    """Orden topologico (Kahn) con el orden de la spec como desempate; ciclo → error de planificacion."""
    pendientes = dict(candidatas)
    resueltas: dict[str, Derivada] = {}
    orden: list[Derivada] = []
    while pendientes:
        listas = [n for n, d in pendientes.items() if not any(dep in pendientes for dep in d.dependencias)]
        if not listas:
            raise ErrorCalculo(
                f"spec: dependencias circulares entre variables derivadas: {sorted(pendientes)}"
            )
        nombre = listas[0]
        derivada = pendientes.pop(nombre)
        if not derivada.es_tabla:
            tablas_origen: set[str] = set()
            for dep in derivada.dependencias:
                if dep in resueltas:
                    tablas_origen.update(_tablas_de(resueltas[dep].origen))
            if len(tablas_origen) == 1:
                origen = next(iter(tablas_origen))
            elif tablas_origen:
                origen = f"{ORIGEN_DERIVADO}({','.join(sorted(tablas_origen))})"
            else:
                origen = ORIGEN_DERIVADO
            derivada = Derivada(**{**_campos(derivada), "origen": origen})
        resueltas[nombre] = derivada
        orden.append(derivada)
    return tuple(orden)


def _tablas_de(origen: str) -> set[str]:
    if origen.startswith(PREFIJO_TABLA):
        return {origen}
    if origen.startswith(f"{ORIGEN_DERIVADO}(") and origen.endswith(")"):
        return set(origen[len(ORIGEN_DERIVADO) + 1 : -1].split(","))
    return set()


def _campos(instancia: object) -> dict[str, object]:
    return {f.name: getattr(instancia, f.name) for f in fields(instancia)}  # type: ignore[arg-type]


def _subexpresiones(texto: str) -> tuple[Expresion, ...]:
    """Grupos entre parentesis de la formula que compilan por si solos, para trazar valores intermedios."""
    pilas: list[int] = []
    grupos: list[tuple[int, str]] = []
    for i, c in enumerate(texto):
        if c == "(":
            pilas.append(i)
        elif c == ")" and pilas:
            inicio = pilas.pop()
            grupos.append((inicio, texto[inicio : i + 1]))
    resultado: list[Expresion] = []
    vistos: set[str] = set()
    for _, grupo in sorted(grupos):
        if grupo in vistos:
            continue
        vistos.add(grupo)
        try:
            resultado.append(compilar(grupo, modo="formula"))
        except ErrorCargaExpresion:
            continue
    return tuple(resultado)


def _interpretaciones_por_entrada(variables: Mapping) -> dict[str, str]:
    """Criterio (a): variable derivada por el consolidador (fuente documental) con `interpretacion`."""
    resultado: dict[str, str] = {}
    for nombre, declaracion in variables.items():
        if not isinstance(declaracion, Mapping) or declaracion.get("evidencia") != EVIDENCIA_DERIVADA:
            continue
        derivacion = declaracion.get("derivacion")
        if not isinstance(derivacion, Mapping):
            continue
        fuente = derivacion.get("fuente")
        interpretacion = derivacion.get("interpretacion")
        if isinstance(fuente, str) and not fuente.startswith(PREFIJO_TABLA) and interpretacion:
            resultado[str(nombre)] = str(interpretacion)
    return resultado


def _redondeo(calculo: Mapping, salida_total: str, notas: list[str]) -> Redondeo | None:
    bloque = calculo.get("redondeo_salida")
    clave_cae = f"{salida_total}{SUFIJO_CAE}"
    if bloque is None:
        notas.append(f"spec sin calculo.redondeo_salida.{clave_cae}: no se publica valor CAE entero")
        return None
    if not isinstance(bloque, Mapping):
        raise ErrorCalculo("spec: calculo.redondeo_salida debe ser un mapa")
    criterio = bloque.get(clave_cae)
    if criterio is None:
        notas.append(f"spec sin calculo.redondeo_salida.{clave_cae}: no se publica valor CAE entero")
        return None
    if not isinstance(criterio, str) or not criterio.strip():
        raise ErrorCalculo(f"spec: calculo.redondeo_salida.{clave_cae} debe ser una cadena no vacia")
    normalizado = normalizar_criterio(criterio)
    if normalizado != CRITERIO_TRUNCAR_CANONICO and not re.match(rf"{CRITERIO_TRUNCAR}\b", normalizado):
        raise ErrorCalculo(
            f"spec: calculo.redondeo_salida.{clave_cae} {criterio!r} no soportado "
            f"(solo {CRITERIO_TRUNCAR_CANONICO!r} o un criterio que empiece por {CRITERIO_TRUNCAR!r})"
        )
    interpretacion = bloque.get("interpretacion")
    return Redondeo(clave_cae, criterio, str(interpretacion) if interpretacion else None)


def planificar(spec_datos: Mapping, tablas: Mapping[str, Tabla]) -> Plan:
    """Valida el bloque `calculo` y las derivaciones de la spec y compila todo una vez.

    Es la unica puerta de validacion del calculo: `spec_registry.cargar_spec` la invoca al cargar una ficha
    (dependencia hacia dentro `spec_registry → calculo`) y envuelve `ErrorCalculo` como error de carga; asi
    una spec activa es calculable por construccion y `calcular` no valida nada de la spec. Criterios en la
    cabecera del modulo.
    """
    if not isinstance(spec_datos, Mapping):
        raise ErrorCalculo("spec_datos debe ser el mapping de la spec cargada")
    if not isinstance(tablas, Mapping):
        raise ErrorCalculo("tablas debe ser un mapping id -> Tabla")
    calculo = _leer(spec_datos, "calculo")
    if not isinstance(calculo, Mapping):
        raise ErrorCalculo("spec: `calculo` debe ser un mapa")
    aritmetica = calculo.get("aritmetica")
    if aritmetica != ARITMETICA_SOPORTADA:
        raise ErrorCalculo(
            f"spec: calculo.aritmetica {aritmetica!r} no soportada (debe ser {ARITMETICA_SOPORTADA!r})"
        )
    variables = _leer(spec_datos, "variables")
    if not isinstance(variables, Mapping):
        raise ErrorCalculo("spec: `variables` debe ser un mapa")
    nombres = frozenset(str(n) for n in variables)

    salida_unidad = _leer_texto(spec_datos, "calculo.motor.salida")
    salida_total = _leer_texto(spec_datos, "calculo.total.salida")
    if salida_unidad == salida_total or salida_unidad in nombres or salida_total in nombres:
        raise ErrorCalculo(
            "spec: las salidas de calculo.motor y calculo.total deben ser nombres nuevos y distintos"
        )
    formula_unidad = _compilar(
        _leer_texto(spec_datos, "calculo.motor.formula"), "formula", "calculo.motor.formula"
    )
    _exigir_identificadores(formula_unidad, nombres, "calculo.motor.formula")
    formula_total = _compilar(
        _leer_texto(spec_datos, "calculo.total.formula"), "formula", "calculo.total.formula"
    )
    if salida_unidad not in formula_total.identificadores:
        raise ErrorCalculo(
            f"spec: calculo.total.formula {formula_total.texto!r} no usa la salida "
            f"por unidad {salida_unidad!r}"
        )
    _exigir_identificadores(formula_total, frozenset({salida_unidad}), "calculo.total.formula")

    derivadas = _derivadas(variables, tablas)
    notas: list[str] = []

    precondiciones: list[Expresion] = []
    delegadas: list[str] = []
    lista_precondiciones = calculo.get("precondiciones") or []
    if not isinstance(lista_precondiciones, list):
        raise ErrorCalculo("spec: calculo.precondiciones debe ser una lista de cadenas")
    for texto in lista_precondiciones:
        if not isinstance(texto, str) or not texto.strip():
            raise ErrorCalculo("spec: cada calculo.precondiciones[] debe ser una cadena no vacia")
        if es_prosa(texto):
            delegadas.append(texto)
            notas.append(
                f"precondicion {texto!r} es prosa (sin operadores): no se evalua en el calculo; "
                "la aplica reglas.py"
            )
            continue
        expresion = _compilar(texto, "logica", "precondicion")
        _exigir_identificadores(expresion, nombres, "precondicion")
        precondiciones.append(expresion)

    controles: dict[str, Control] = {}
    lista_controles = calculo.get("controles_fisicos") or []
    if not isinstance(lista_controles, list):
        raise ErrorCalculo("spec: calculo.controles_fisicos debe ser una lista")
    for control in lista_controles:
        if not isinstance(control, Mapping) or not control.get("id") or not control.get("regla"):
            raise ErrorCalculo("spec: cada calculo.controles_fisicos[] necesita `id` y `regla`")
        id_control = str(control["id"])
        if id_control in controles or id_control in nombres:
            raise ErrorCalculo(f"spec: control fisico {id_control!r} repetido o con nombre de variable")
        expresion = _compilar(str(control["regla"]), "logica", f"control {id_control}")
        _exigir_identificadores(expresion, nombres | {salida_unidad}, f"control {id_control}")
        mensaje = control.get("mensaje")
        controles[id_control] = Control(id_control, expresion, str(mensaje) if mensaje else None)

    redondeo = _redondeo(calculo, salida_total, notas)

    derivables = frozenset(d.nombre for d in derivadas)
    referenciadas: set[str] = set(formula_unidad.identificadores)
    for expresion in precondiciones:
        referenciadas.update(expresion.identificadores)
    for control in controles.values():
        referenciadas.update(control.expresion.identificadores)
    for d in derivadas:
        referenciadas.update(d.dependencias)
    entradas_requeridas = frozenset(referenciadas - derivables - {salida_unidad})

    estaticas: list[str] = []
    for d in derivadas:
        if d.interpretacion:
            _unir_unicos(estaticas, [d.interpretacion])
    if redondeo is not None and redondeo.interpretacion:
        _unir_unicos(estaticas, [redondeo.interpretacion])

    return Plan(
        salida_unidad=salida_unidad,
        formula_unidad=formula_unidad,
        salida_total=salida_total,
        formula_total=formula_total,
        derivadas=derivadas,
        entradas_requeridas=entradas_requeridas,
        precondiciones=tuple(precondiciones),
        precondiciones_delegadas=tuple(delegadas),
        controles=controles,
        criterio_redondeo=redondeo,
        interpretaciones_estaticas=tuple(estaticas),
        interpretaciones_por_entrada=_interpretaciones_por_entrada(variables),
        subexpresiones=_subexpresiones(formula_unidad.texto),
        notas=tuple(notas),
    )


# ---------------------------------------------------------------------------
# Calculo
# ---------------------------------------------------------------------------


def _texto(valor: object) -> str:
    """`Decimal` como cadena sin ceros de cola ni exponente; el resto, `str`. Independiente del contexto."""
    if isinstance(valor, Decimal):
        with localcontext() as ctx:
            ctx.prec = PRECISION_DECIMAL
            return format(valor.normalize(), "f")
    return str(valor)


def _decimal_entrada(valor: object, que: str) -> Decimal:
    if isinstance(valor, bool):
        raise ErrorCalculo(f"{que}: se esperaba Decimal y llego un booleano")
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ErrorCalculo(f"{que}: valor no finito {valor!r}")
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        raise ErrorCalculo(f"{que}: float no permitido ({valor!r}); usa Decimal")
    raise ErrorCalculo(f"{que}: se esperaba Decimal y llego {type(valor).__name__}")


def _decimal_resultado(valor: object, que: str) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    raise ErrorCalculo(f"{que}: la expresion no produce un numero ({type(valor).__name__})")


def _evaluar(expresion: Expresion, contexto: ContextoDict, que: str) -> object:
    """Evaluacion fuera de una unidad (total): un error de evaluacion es un defecto del plan."""
    try:
        return expresion.evaluar(contexto)
    except ErrorEvaluacionExpresion as exc:
        raise ErrorCalculo(f"{que}: {exc}") from exc


_ERROR = object()


def _evaluar_unidad(
    expresion: Expresion, contexto: ContextoDict, que: str, unidad: ResultadoUnidad, traza: list[str]
) -> object:
    """Evaluacion dentro de una unidad: un error de evaluacion (division por cero, tipos) es motivo de esa
    unidad y devuelve `_ERROR`; nunca una excepcion global."""
    try:
        return expresion.evaluar(contexto)
    except ErrorEvaluacionExpresion as exc:
        mensaje = f"{que}: error de evaluacion ({exc})"
        traza.append(f"unidad {unidad.num_serie_motor}: {mensaje}")
        unidad.avisos.append(f"unidad {unidad.num_serie_motor}: {mensaje}")
        if unidad.motivo_no_calculo is None:
            unidad.motivo_no_calculo = mensaje
        return _ERROR


def _agregar(valores: list[object]) -> object:
    if any(v is False for v in valores):
        return False
    if valores and all(v is True for v in valores):
        return True
    return NO_EVALUABLE


def _unir_unicos(destino: list[str], nuevos: list[str] | tuple[str, ...]) -> None:
    for n in nuevos:
        if n not in destino:
            destino.append(n)


def _entradas(plan: Plan, valores: Mapping, unidad: ResultadoUnidad, traza: list[str]) -> dict[str, Decimal]:
    num_serie = unidad.num_serie_motor
    if not isinstance(valores, Mapping):
        raise ErrorCalculo(f"unidad {num_serie}: las variables deben ser un mapping nombre -> Decimal")
    entradas: dict[str, Decimal] = {}
    nulas: list[str] = []
    for nombre, valor in valores.items():
        nombre = str(nombre)
        if nombre in plan.derivables:
            unidad.avisos.append(
                f"unidad {num_serie}: valor de {nombre} suministrado externamente ignorado; "
                f"se deriva segun la spec"
            )
            continue
        if valor is None:
            nulas.append(nombre)
            continue
        entradas[nombre] = _decimal_entrada(valor, f"unidad {num_serie}: {nombre}")
    traza.append(
        f"unidad {num_serie}: entradas "
        + (" ".join(f"{k}={_texto(v)}" for k, v in entradas.items()) or "(ninguna)")
    )
    if nulas:
        plural = "s" if len(nulas) > 1 else ""
        unidad.motivo_no_calculo = (
            f"entrada{plural} {', '.join(nulas)} sin valor consumido (conflicto o ausente)"
        )
        traza.append(f"unidad {num_serie}: {unidad.motivo_no_calculo}")
    consumidas = [
        f"{nombre} ({interpretacion})"
        for nombre, interpretacion in plan.interpretaciones_por_entrada.items()
        if nombre in entradas and nombre in plan.entradas_requeridas
    ]
    if consumidas:
        _unir_unicos(
            unidad.interpretaciones,
            [
                interpretacion
                for nombre, interpretacion in plan.interpretaciones_por_entrada.items()
                if nombre in entradas and nombre in plan.entradas_requeridas
            ],
        )
        traza.append(f"unidad {num_serie}: entradas con interpretacion: {', '.join(consumidas)}")
    return entradas


def _derivar_tabla(
    d: Derivada,
    datos: dict[str, Decimal],
    tablas: Mapping[str, Tabla],
    fecha: date | None,
    unidad: ResultadoUnidad,
    traza: list[str],
) -> None:
    prefijo = f"unidad {unidad.num_serie_motor}"
    valor_clave = datos.get(d.clave or "")
    if valor_clave is None:
        traza.append(f"{prefijo}: {d.nombre} no derivable: falta {d.clave}")
        return
    tabla = tablas[(d.fuente or "")[len(PREFIJO_TABLA) :]]
    if fecha is not None and not tabla.vigente(fecha):
        unidad.avisos.append(
            f"{prefijo}: tabla {tabla.id} no vigente en {fecha.isoformat()} "
            f"(vigencia {tabla.vigencia_desde} a {tabla.vigencia_hasta}); revision humana"
        )
    try:
        busqueda = tabla.buscar(valor_clave)
    except ErrorTabla as exc:
        mensaje = f"{d.nombre}: {exc}"
        unidad.avisos.append(f"{prefijo}: {mensaje}")
        unidad.motivo_no_calculo = unidad.motivo_no_calculo or mensaje
        traza.append(f"{prefijo}: {mensaje}")
        return
    if busqueda.aviso:
        unidad.avisos.append(f"{prefijo}: {d.nombre}: {busqueda.aviso}")
    if busqueda.valor is None:
        unidad.motivo_no_calculo = unidad.motivo_no_calculo or (
            f"{d.nombre}: {tabla.clave} = {_texto(valor_clave)} fuera del rango de la tabla {tabla.id}; "
            "no se calcula"
        )
        traza.append(f"{prefijo}: {d.nombre} sin valor en {d.origen} ({tabla.clave} = {_texto(valor_clave)})")
        return
    if busqueda.exacta and busqueda.fila is not None:
        detalle = f"fila exacta {tabla.clave} = {_texto(busqueda.fila.clave)}"
    else:
        etiqueta = d.si_no_existe_fila or busqueda.interpretacion or "interpolacion"
        adyacentes = busqueda.filas_adyacentes
        entre = (
            f" entre {tabla.clave} = {_texto(adyacentes[0].clave)} y {_texto(adyacentes[1].clave)}"
            if adyacentes
            else ""
        )
        detalle = f"sin fila exacta, {tabla.valor} interpolado{entre} ({etiqueta})"
        _unir_unicos(unidad.interpretaciones, [etiqueta])
    if d.interpretacion:
        _unir_unicos(unidad.interpretaciones, [d.interpretacion])
    unidad.derivadas[d.nombre] = busqueda.valor
    unidad.fuentes[d.nombre] = d.origen
    datos[d.nombre] = busqueda.valor
    traza.append(f"{prefijo}: {d.nombre} = {_texto(busqueda.valor)} ({d.origen}, {detalle})")


def _derivar_expresion(
    d: Derivada, datos: dict[str, Decimal], unidad: ResultadoUnidad, traza: list[str]
) -> None:
    prefijo = f"unidad {unidad.num_serie_motor}"
    expresion = d.expresion
    if expresion is None:
        raise ErrorCalculo(f"{prefijo}: la derivada {d.nombre} no tiene expresion (plan mal construido)")
    valor = _evaluar_unidad(expresion, ContextoDict(datos), f"derivacion de {d.nombre}", unidad, traza)
    if valor is _ERROR:
        return
    if valor is NO_EVALUABLE:
        faltan = sorted(n for n in d.dependencias if n not in datos)
        traza.append(f"{prefijo}: {d.nombre} no derivable: faltan {', '.join(faltan) or 'datos'}")
        return
    numero = _decimal_resultado(valor, f"{prefijo}: derivacion de {d.nombre}")
    unidad.derivadas[d.nombre] = numero
    unidad.fuentes[d.nombre] = d.origen
    datos[d.nombre] = numero
    etiqueta = f" ({d.interpretacion})" if d.interpretacion else ""
    if d.interpretacion:
        _unir_unicos(unidad.interpretaciones, [d.interpretacion])
    traza.append(f"{prefijo}: {d.nombre} = {d.metodo} = {_texto(numero)}{etiqueta}")


def _calcular_unidad(
    plan: Plan,
    num_serie: str,
    valores: Mapping,
    tablas: Mapping[str, Tabla],
    fecha: date | None,
    traza: list[str],
) -> ResultadoUnidad:
    unidad = ResultadoUnidad(
        num_serie_motor=num_serie,
        entradas={},
        derivadas={},
        salida=None,
        controles={},
        precondiciones={},
        interpretaciones=[],
        avisos=[],
        motivo_no_calculo=None,
        fuentes={},
    )
    prefijo = f"unidad {num_serie}"
    unidad.entradas = _entradas(plan, valores, unidad, traza)
    datos: dict[str, Decimal] = dict(unidad.entradas)

    for d in plan.derivadas:
        if d.es_tabla:
            _derivar_tabla(d, datos, tablas, fecha, unidad, traza)
        else:
            _derivar_expresion(d, datos, unidad, traza)

    contexto = ContextoDict(datos)
    for expresion in plan.precondiciones:
        texto = expresion.texto
        resultado = _evaluar_unidad(expresion, contexto, f"precondicion {texto!r}", unidad, traza)
        if resultado is _ERROR:
            resultado = NO_EVALUABLE
        unidad.precondiciones[texto] = resultado
        traza.append(f"{prefijo}: precondicion {texto!r} = {resultado}")
        if resultado is False and unidad.motivo_no_calculo is None:
            unidad.motivo_no_calculo = f"precondicion {texto!r} no se cumple"

    if unidad.motivo_no_calculo is None:
        for expresion in plan.subexpresiones:
            parcial = _evaluar_unidad(expresion, contexto, expresion.texto, unidad, traza)
            if isinstance(parcial, Decimal):
                traza.append(f"{prefijo}: {expresion.texto} = {_texto(parcial)}")
    if unidad.motivo_no_calculo is None:
        valor = _evaluar_unidad(plan.formula_unidad, contexto, "formula", unidad, traza)
        if valor is NO_EVALUABLE:
            faltan = sorted(n for n in plan.formula_unidad.identificadores if n not in datos)
            unidad.motivo_no_calculo = f"faltan variables para la formula: {', '.join(faltan)}"
            traza.append(f"{prefijo}: {plan.salida_unidad} no calculable ({unidad.motivo_no_calculo})")
        elif valor is not _ERROR:
            unidad.salida = _decimal_resultado(valor, f"{prefijo}: formula")
            traza.append(
                f"{prefijo}: {plan.salida_unidad} = {plan.formula_unidad.texto} = {_texto(unidad.salida)}"
            )
    if unidad.salida is None:
        traza.append(f"{prefijo}: no se calcula ({unidad.motivo_no_calculo})")

    datos_control: dict[str, object] = dict(datos)
    if unidad.salida is not None:
        datos_control[plan.salida_unidad] = unidad.salida
    contexto_control = ContextoDict(datos_control)
    fallidos: list[Control] = []
    for control in plan.controles.values():
        resultado = _evaluar_unidad(
            control.expresion, contexto_control, f"control {control.id}", unidad, traza
        )
        if resultado is _ERROR:
            resultado = NO_EVALUABLE
        unidad.controles[control.id] = resultado
        sufijo = f" ({control.mensaje})" if resultado is False and control.mensaje else ""
        traza.append(f"{prefijo}: control {control.id} {control.expresion.texto!r} = {resultado}{sufijo}")
        if resultado is False:
            fallidos.append(control)
    if fallidos:
        ids = ", ".join(c.id for c in fallidos)
        mensajes = "; ".join(c.mensaje for c in fallidos if c.mensaje)
        motivo = f"retirado: control fisico {ids} fallido" + (f" ({mensajes})" if mensajes else "")
        if unidad.salida is not None:
            traza.append(f"{prefijo}: {plan.salida_unidad} = {_texto(unidad.salida)} retirado por {ids}")
            unidad.salida = None
        unidad.motivo_no_calculo = unidad.motivo_no_calculo or motivo
    return unidad


def calcular(
    spec_datos: Mapping,
    unidades: Mapping[str, Mapping[str, Decimal | None]],
    tablas: Mapping[str, Tabla],
    *,
    provisional: bool = False,
    fecha: date | None = None,
    plan: Plan | None = None,
) -> ResultadoCalculo:
    """Calcula la salida por unidad y el total segun el plan de la spec. Ver la cabecera del modulo.

    `unidades`: `num_serie_motor -> {variable: Decimal | None}` con las variables de entrada consolidadas.
    `None` es un valor consumido nulo (conflicto o ausencia): esa unidad no calcula. Un `float` o un texto es
    `ErrorCalculo` (contexto mal construido). Las variables que la spec deriva se ignoran si llegan (aviso).
    `fecha`: fecha de evaluacion para comprobar la vigencia de las tablas (solo aviso).
    `plan`: `Plan` de `planificar`; si falta se construye aqui (misma validacion).
    """
    if not isinstance(unidades, Mapping):
        raise ErrorCalculo("unidades debe ser un mapping num_serie_motor -> {variable: Decimal}")
    if plan is None:
        plan = planificar(spec_datos, tablas)
    elif not isinstance(plan, Plan):
        raise ErrorCalculo("plan debe ser el Plan devuelto por planificar")
    with localcontext() as ctx:
        ctx.prec = PRECISION_DECIMAL
        traza: list[str] = list(plan.notas)
        avisos: list[str] = []
        interpretaciones: list[str] = []
        por_unidad: list[ResultadoUnidad] = []
        for num_serie, valores in unidades.items():
            unidad = _calcular_unidad(plan, str(num_serie), valores, tablas, fecha, traza)
            por_unidad.append(unidad)
            avisos.extend(unidad.avisos)
            _unir_unicos(interpretaciones, unidad.interpretaciones)

        total: Decimal | None = None
        total_cae: int | None = None
        motivo: str | None = None
        if not por_unidad:
            motivo = "sin unidades que calcular"
        else:
            sin_salida = [u for u in por_unidad if u.salida is None]
            if sin_salida:
                motivo = "; ".join(f"unidad {u.num_serie_motor}: {u.motivo_no_calculo}" for u in sin_salida)
            else:
                salidas = [u.salida for u in por_unidad]
                valor = _evaluar(plan.formula_total, ContextoDict({plan.salida_unidad: salidas}), "total")
                total = _decimal_resultado(valor, "total")
                sumandos = f"{' + '.join(_texto(s) for s in salidas)} = " if len(salidas) > 1 else ""
                traza.append(
                    f"total: {plan.salida_total} = {plan.formula_total.texto} = {sumandos}{_texto(total)}"
                )
                redondeo = plan.criterio_redondeo
                if redondeo is not None:
                    total_cae = int(total.to_integral_value(rounding=ROUND_DOWN))
                    etiqueta = f"; {redondeo.interpretacion}" if redondeo.interpretacion else ""
                    traza.append(f"total: {redondeo.clave} = {total_cae} ({redondeo.criterio}{etiqueta})")
                    if redondeo.interpretacion:
                        _unir_unicos(interpretaciones, [redondeo.interpretacion])
        if motivo is not None:
            traza.append(f"total: no se publica ({motivo})")

        controles_ok = _agregar([r for u in por_unidad for r in u.controles.values()])
        precondiciones_ok = _agregar([r for u in por_unidad for r in u.precondiciones.values()])
        traza.append(f"controles fisicos: {controles_ok}; precondiciones: {precondiciones_ok}")
        traza.append("interpretaciones aplicadas: " + (", ".join(interpretaciones) or "ninguna"))
        if provisional:
            traza.append("calculo provisional: estimacion no acreditada (veredicto SUBSANABLE)")
        return ResultadoCalculo(
            por_unidad=por_unidad,
            total=total,
            total_cae=total_cae,
            traza=traza,
            provisional=provisional,
            motivo_no_calculo=motivo,
            interpretaciones=interpretaciones,
            avisos=avisos,
            controles_ok=controles_ok,
            precondiciones_ok=precondiciones_ok,
            precondiciones_delegadas=list(plan.precondiciones_delegadas),
        )


# ---------------------------------------------------------------------------
# Serializacion para el informe JSON
# ---------------------------------------------------------------------------


def _serializar(valor: object) -> object:
    if valor is NO_EVALUABLE:
        return "NO_EVALUABLE"
    if isinstance(valor, Decimal):
        return _texto(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if is_dataclass(valor) and not isinstance(valor, type):
        return {f.name: _serializar(getattr(valor, f.name)) for f in fields(valor)}
    if isinstance(valor, Mapping):
        return {str(k): _serializar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, frozenset, set)):
        return [_serializar(v) for v in valor]
    return valor


def a_dict(resultado: ResultadoCalculo) -> dict:
    """`ResultadoCalculo` como dict serializable en JSON: `Decimal` como cadena, `NO_EVALUABLE` como texto."""
    salida = _serializar(resultado)
    if not isinstance(salida, dict):
        raise ErrorCalculo("a_dict espera un ResultadoCalculo")
    return salida


__all__ = [
    "ARITMETICA_SOPORTADA",
    "CARACTERES_EXPRESION",
    "CRITERIO_TRUNCAR",
    "CRITERIO_TRUNCAR_CANONICO",
    "PRECISION_DECIMAL",
    "PREFIJO_TABLA",
    "Control",
    "Derivada",
    "ErrorCalculo",
    "Plan",
    "Redondeo",
    "ResultadoCalculo",
    "ResultadoUnidad",
    "a_dict",
    "calcular",
    "es_prosa",
    "normalizar_criterio",
    "planificar",
]
