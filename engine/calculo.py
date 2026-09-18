"""Motor de calculo (N3): evalua la formula de la ficha con `Decimal` a partir de la spec, sin cablear nada.

Todo lo que se calcula se lee del YAML de la ficha (`docs/04` §7, regla de oro 4):

- `calculo.motor.formula` / `calculo.motor.salida`: la formula por unidad y el nombre de su salida.
- `calculo.total.formula` / `calculo.total.salida`: la formula del total sobre la lista de salidas por unidad.
- `variables.<nombre>.derivacion` de las variables `evidencia: derivado`: se derivan aqui las que salen de una
  tabla (`fuente: tabla:<ID>`, `clave`, `si_no_existe_fila`) y las cuyo `metodo` es una expresion del
  vocabulario cerrado cuyos identificadores son variables de la spec (`min(h_antes, h_despues)`,
  `perdidas_ref_kw / PM`). Las demas (`metodo` en prosa: registro de funcionamiento) las deriva el
  consolidador y llegan como entrada. Se evaluan en orden topologico de dependencias.
- `calculo.precondiciones`: cadenas en modo `logica`. Las que no compilan en el contexto de calculo (la que
  habla de reglas bloqueantes) se delegan a `reglas.py` con una nota en la traza. Una comparacion encadenada
  (`0 < h <= 8760`) se reescribe como conjuncion antes de compilar porque el parser no la admite.
- `calculo.controles_fisicos[]`: `id` y `regla`; si alguno falla, el resultado se **retira**.
- `calculo.redondeo_salida.<salida_total>_cae` + `interpretacion`: el codigo solo implementa "truncar" (hacia
  cero, a kWh entero); otro criterio es error de carga.

Reglas de implementacion que este modulo garantiza:

- `Decimal` de extremo a extremo con precision fija `PRECISION_DECIMAL` en un `localcontext`, independiente
  del contexto global. Ninguna entrada puede ser `float` (`ErrorCalculo`).
- Una variable derivable por la spec que llegue en `unidades` (p. ej. `p` tomada de la ficha del variador)
  se **ignora** con aviso: el valor sale siempre de la derivacion declarada (R-CAL-04).
- Nada de `eval`; toda cadena de la spec pasa por `engine.expresiones.compilar`.
- No importa nada de agentes/, salida/, generator/ ni tests/.
"""

from __future__ import annotations

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
ORIGEN_DERIVADO = "derivado"


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

    @property
    def p_fuente(self) -> str | None:
        """Origen de `p` para R-CAL-04 (`p.fuente == tabla:<ID>`). Azucar sobre `fuentes` (lo generico)."""
        return self.fuentes.get("p")


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
# Plan de calculo: lo que la spec declara, compilado una vez
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Derivacion:
    nombre: str
    tipo: str  # "tabla" | "expresion"
    dependencias: frozenset[str]
    origen: str
    id_tabla: str | None = None
    clave: str | None = None
    si_no_existe_fila: str | None = None
    expresion: Expresion | None = None
    texto: str | None = None
    interpretacion: str | None = None


@dataclass(frozen=True)
class _Control:
    id: str
    texto: str
    expresion: Expresion
    mensaje: str | None


@dataclass(frozen=True)
class _Redondeo:
    clave: str
    criterio: str
    interpretacion: str | None


@dataclass(frozen=True)
class _Plan:
    salida_unidad: str
    texto_formula_unidad: str
    formula_unidad: Expresion
    salida_total: str
    texto_formula_total: str
    formula_total: Expresion
    derivaciones: tuple[_Derivacion, ...]
    precondiciones: tuple[tuple[str, Expresion], ...]
    precondiciones_delegadas: tuple[str, ...]
    controles: tuple[_Control, ...]
    redondeo: _Redondeo | None
    subexpresiones: tuple[tuple[str, Expresion], ...]
    notas: tuple[str, ...]

    @property
    def derivables(self) -> frozenset[str]:
        return frozenset(d.nombre for d in self.derivaciones)


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
        raise ErrorCalculo(f"spec: {que} no compila ({exc})") from exc


def _desencadenar(texto: str) -> str | None:
    """`a < b <= c` → `(a < b) and (b <= c)`. Solo comparadores de orden en el nivel superior; si no hay
    al menos dos, devuelve `None`. Es una reescritura textual previa a `compilar`, no una evaluacion."""
    partes: list[str] = []
    ops: list[str] = []
    profundidad = 0
    comillas: str | None = None
    inicio = 0
    i = 0
    while i < len(texto):
        c = texto[i]
        if comillas is not None:
            if c == comillas:
                comillas = None
        elif c in "\"'":
            comillas = c
        elif c in "([":
            profundidad += 1
        elif c in ")]":
            profundidad -= 1
        elif profundidad == 0 and c in "<>" and not (c == ">" and i > 0 and texto[i - 1] == "-"):
            op = c + "=" if texto[i + 1 : i + 2] == "=" else c
            partes.append(texto[inicio:i])
            ops.append(op)
            i += len(op)
            inicio = i
            continue
        i += 1
    partes.append(texto[inicio:])
    if len(ops) < 2:
        return None
    limpias = [p.strip() for p in partes]
    if any(not p for p in limpias):
        return None
    return " and ".join(f"({a} {op} {b})" for a, op, b in zip(limpias, ops, limpias[1:], strict=False))


def _compilar_logica(texto: str, que: str) -> tuple[Expresion, str | None]:
    """Compila en modo logica; si falla por comparacion encadenada, la reescribe y devuelve la nota."""
    try:
        return compilar(texto, modo="logica"), None
    except ErrorCargaExpresion as exc:
        alternativa = _desencadenar(texto)
        if alternativa is None:
            raise ErrorCalculo(f"spec: {que} {texto!r} no compila ({exc})") from exc
        try:
            expresion = compilar(alternativa, modo="logica")
        except ErrorCargaExpresion as exc2:
            raise ErrorCalculo(f"spec: {que} {texto!r} no compila ({exc2})") from exc2
        nota = (
            f"{que} {texto!r} reescrita como {alternativa!r} (el parser no admite comparaciones encadenadas)"
        )
        return expresion, nota


def _derivaciones(variables: Mapping, tablas: Mapping[str, Tabla]) -> tuple[_Derivacion, ...]:
    """Variables `evidencia: derivado` que este modulo puede derivar, en orden topologico de dependencias."""
    nombres = frozenset(str(n) for n in variables)
    candidatas: dict[str, _Derivacion] = {}
    for nombre, declaracion in variables.items():
        nombre = str(nombre)
        if not isinstance(declaracion, Mapping) or declaracion.get("evidencia") != EVIDENCIA_DERIVADA:
            continue
        derivacion = declaracion.get("derivacion")
        if not isinstance(derivacion, Mapping):
            continue
        fuente = derivacion.get("fuente")
        if isinstance(fuente, str) and fuente.startswith(PREFIJO_TABLA):
            id_tabla = fuente[len(PREFIJO_TABLA) :]
            if id_tabla not in tablas:
                raise ErrorCalculo(
                    f"spec: variables.{nombre}.derivacion.fuente cita la tabla {id_tabla!r} y no esta cargada"
                )
            clave = derivacion.get("clave")
            if not isinstance(clave, str) or not clave:
                raise ErrorCalculo(f"spec: variables.{nombre}.derivacion.clave es obligatoria para una tabla")
            sin_fila = derivacion.get("si_no_existe_fila")
            candidatas[nombre] = _Derivacion(
                nombre=nombre,
                tipo="tabla",
                dependencias=frozenset({clave}),
                origen=fuente,
                id_tabla=id_tabla,
                clave=clave,
                si_no_existe_fila=str(sin_fila) if sin_fila else None,
                texto=str(derivacion.get("metodo") or ""),
            )
            continue
        metodo = derivacion.get("metodo")
        if not isinstance(metodo, str) or not metodo.strip():
            continue
        try:
            expresion = compilar(metodo, modo="formula")
        except ErrorCargaExpresion:
            continue  # metodo en prosa: lo deriva el consolidador y llega como entrada
        if not expresion.identificadores or not expresion.identificadores <= nombres:
            continue
        interpretacion = derivacion.get("interpretacion")
        candidatas[nombre] = _Derivacion(
            nombre=nombre,
            tipo="expresion",
            dependencias=expresion.identificadores,
            origen=ORIGEN_DERIVADO,
            expresion=expresion,
            texto=metodo,
            interpretacion=str(interpretacion) if interpretacion else None,
        )
    return _ordenar(candidatas)


def _ordenar(candidatas: dict[str, _Derivacion]) -> tuple[_Derivacion, ...]:
    """Orden topologico (Kahn) con el orden de la spec como desempate; ciclo → error de carga."""
    pendientes = dict(candidatas)
    resueltas: dict[str, _Derivacion] = {}
    orden: list[_Derivacion] = []
    while pendientes:
        listas = [
            n
            for n, d in pendientes.items()
            if not any(dep in pendientes for dep in d.dependencias if dep != n)
        ]
        if not listas or any(n in candidatas[n].dependencias for n in listas):
            raise ErrorCalculo(
                f"spec: dependencias circulares entre variables derivadas: {sorted(pendientes)}"
            )
        nombre = listas[0]
        derivacion = pendientes.pop(nombre)
        tablas_origen: set[str] = set()
        if derivacion.tipo == "tabla":
            tablas_origen.add(derivacion.origen)
        else:
            for dep in derivacion.dependencias:
                if dep in resueltas:
                    tablas_origen.update(_tablas_de(resueltas[dep].origen))
            if len(tablas_origen) == 1:
                origen = next(iter(tablas_origen))
            elif tablas_origen:
                origen = f"{ORIGEN_DERIVADO}({','.join(sorted(tablas_origen))})"
            else:
                origen = ORIGEN_DERIVADO
            derivacion = _Derivacion(**{**_campos(derivacion), "origen": origen})
        resueltas[nombre] = derivacion
        orden.append(derivacion)
    return tuple(orden)


def _tablas_de(origen: str) -> set[str]:
    if origen.startswith(PREFIJO_TABLA):
        return {origen}
    if origen.startswith(f"{ORIGEN_DERIVADO}(") and origen.endswith(")"):
        return set(origen[len(ORIGEN_DERIVADO) + 1 : -1].split(","))
    return set()


def _campos(instancia: object) -> dict[str, object]:
    return {f.name: getattr(instancia, f.name) for f in fields(instancia)}  # type: ignore[arg-type]


def _subexpresiones(texto: str) -> tuple[tuple[str, Expresion], ...]:
    """Grupos entre parentesis de la formula que compilan por si solos, para trazar valores intermedios."""
    pilas: list[int] = []
    grupos: list[tuple[int, str]] = []
    for i, c in enumerate(texto):
        if c == "(":
            pilas.append(i)
        elif c == ")" and pilas:
            inicio = pilas.pop()
            grupos.append((inicio, texto[inicio : i + 1]))
    resultado: list[tuple[str, Expresion]] = []
    vistos: set[str] = set()
    for _, grupo in sorted(grupos):
        if grupo in vistos:
            continue
        vistos.add(grupo)
        try:
            resultado.append((grupo, compilar(grupo, modo="formula")))
        except ErrorCargaExpresion:
            continue
    return tuple(resultado)


def _planificar(spec_datos: Mapping, tablas: Mapping[str, Tabla]) -> _Plan:
    if not isinstance(spec_datos, Mapping):
        raise ErrorCalculo("spec_datos debe ser el mapping de la spec cargada")
    if not isinstance(tablas, Mapping):
        raise ErrorCalculo("tablas debe ser un mapping id -> Tabla")
    calculo = _leer(spec_datos, "calculo")
    aritmetica = calculo.get("aritmetica") if isinstance(calculo, Mapping) else None  # type: ignore[union-attr]
    if aritmetica is not None and aritmetica != ARITMETICA_SOPORTADA:
        raise ErrorCalculo(
            f"spec: calculo.aritmetica {aritmetica!r} no soportada (solo {ARITMETICA_SOPORTADA!r})"
        )
    variables = _leer(spec_datos, "variables")
    if not isinstance(variables, Mapping):
        raise ErrorCalculo("spec: `variables` debe ser un mapa")

    salida_unidad = _leer_texto(spec_datos, "calculo.motor.salida")
    texto_unidad = _leer_texto(spec_datos, "calculo.motor.formula")
    formula_unidad = _compilar(texto_unidad, "formula", "calculo.motor.formula")
    salida_total = _leer_texto(spec_datos, "calculo.total.salida")
    texto_total = _leer_texto(spec_datos, "calculo.total.formula")
    formula_total = _compilar(texto_total, "formula", "calculo.total.formula")
    if salida_unidad not in formula_total.identificadores:
        raise ErrorCalculo(
            f"spec: calculo.total.formula {texto_total!r} no usa la salida por unidad {salida_unidad!r}"
        )

    notas: list[str] = []
    precondiciones: list[tuple[str, Expresion]] = []
    delegadas: list[str] = []
    for texto in calculo.get("precondiciones") or []:  # type: ignore[union-attr]
        texto = str(texto)
        try:
            expresion, nota = _compilar_logica(texto, "precondicion")
        except ErrorCalculo:
            delegadas.append(texto)
            notas.append(
                f"precondicion {texto!r} no evaluable en el contexto de calculo; la aplica reglas.py"
            )
            continue
        if nota:
            notas.append(nota)
        precondiciones.append((texto, expresion))

    controles: list[_Control] = []
    for control in calculo.get("controles_fisicos") or []:  # type: ignore[union-attr]
        if not isinstance(control, Mapping) or not control.get("id") or not control.get("regla"):
            raise ErrorCalculo("spec: cada calculo.controles_fisicos[] necesita `id` y `regla`")
        texto = str(control["regla"])
        expresion, nota = _compilar_logica(texto, f"control {control['id']}")
        if nota:
            notas.append(nota)
        mensaje = control.get("mensaje")
        controles.append(_Control(str(control["id"]), texto, expresion, str(mensaje) if mensaje else None))

    redondeo: _Redondeo | None = None
    bloque = calculo.get("redondeo_salida") or {}  # type: ignore[union-attr]
    clave_cae = f"{salida_total}{SUFIJO_CAE}"
    if isinstance(bloque, Mapping) and bloque.get(clave_cae):
        criterio = str(bloque[clave_cae])
        if CRITERIO_TRUNCAR not in criterio.lower():
            raise ErrorCalculo(
                f"spec: calculo.redondeo_salida.{clave_cae} {criterio!r} no soportado (solo truncar)"
            )
        interpretacion = bloque.get("interpretacion")
        redondeo = _Redondeo(clave_cae, criterio, str(interpretacion) if interpretacion else None)
    else:
        notas.append(f"spec sin calculo.redondeo_salida.{clave_cae}: no se publica valor CAE entero")

    return _Plan(
        salida_unidad=salida_unidad,
        texto_formula_unidad=texto_unidad,
        formula_unidad=formula_unidad,
        salida_total=salida_total,
        texto_formula_total=texto_total,
        formula_total=formula_total,
        derivaciones=_derivaciones(variables, tablas),
        precondiciones=tuple(precondiciones),
        precondiciones_delegadas=tuple(delegadas),
        controles=tuple(controles),
        redondeo=redondeo,
        subexpresiones=_subexpresiones(texto_unidad),
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
    try:
        return expresion.evaluar(contexto)
    except ErrorEvaluacionExpresion as exc:
        raise ErrorCalculo(f"{que}: {exc}") from exc


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


def _entradas(
    plan: _Plan, num_serie: str, valores: Mapping, avisos: list[str], traza: list[str]
) -> dict[str, Decimal]:
    if not isinstance(valores, Mapping):
        raise ErrorCalculo(f"unidad {num_serie}: las variables deben ser un mapping nombre -> Decimal")
    entradas: dict[str, Decimal] = {}
    for nombre, valor in valores.items():
        nombre = str(nombre)
        if nombre in plan.derivables:
            avisos.append(
                f"unidad {num_serie}: valor de {nombre} suministrado externamente ignorado; "
                f"se deriva segun la spec"
            )
            continue
        entradas[nombre] = _decimal_entrada(valor, f"unidad {num_serie}: {nombre}")
    traza.append(
        f"unidad {num_serie}: entradas "
        + (" ".join(f"{k}={_texto(v)}" for k, v in entradas.items()) or "(ninguna)")
    )
    return entradas


def _derivar_tabla(
    d: _Derivacion,
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
    tabla = tablas[d.id_tabla or ""]
    if fecha is not None and not tabla.vigente(fecha):
        unidad.avisos.append(
            f"{prefijo}: tabla {tabla.id} no vigente en {fecha.isoformat()} "
            f"(vigencia {tabla.vigencia_desde} a {tabla.vigencia_hasta}); revision humana"
        )
    try:
        busqueda = tabla.buscar(valor_clave)
    except ErrorTabla as exc:
        raise ErrorCalculo(f"{prefijo}: {exc}") from exc
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
    unidad.derivadas[d.nombre] = busqueda.valor
    unidad.fuentes[d.nombre] = d.origen
    datos[d.nombre] = busqueda.valor
    traza.append(f"{prefijo}: {d.nombre} = {_texto(busqueda.valor)} ({d.origen}, {detalle})")


def _derivar_expresion(
    d: _Derivacion, datos: dict[str, Decimal], unidad: ResultadoUnidad, traza: list[str]
) -> None:
    prefijo = f"unidad {unidad.num_serie_motor}"
    valor = _evaluar(d.expresion, ContextoDict(datos), f"{prefijo}: derivacion de {d.nombre}")  # type: ignore[arg-type]
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
    traza.append(f"{prefijo}: {d.nombre} = {d.texto} = {_texto(numero)}{etiqueta}")


def _calcular_unidad(
    plan: _Plan,
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
    unidad.entradas = _entradas(plan, num_serie, valores, unidad.avisos, traza)
    datos: dict[str, Decimal] = dict(unidad.entradas)

    for d in plan.derivaciones:
        if d.tipo == "tabla":
            _derivar_tabla(d, datos, tablas, fecha, unidad, traza)
        else:
            _derivar_expresion(d, datos, unidad, traza)

    contexto = ContextoDict(datos)
    for texto, expresion in plan.precondiciones:
        resultado = _evaluar(expresion, contexto, f"{prefijo}: precondicion {texto!r}")
        unidad.precondiciones[texto] = resultado
        traza.append(f"{prefijo}: precondicion {texto!r} = {resultado}")
        if resultado is False and unidad.motivo_no_calculo is None:
            unidad.motivo_no_calculo = f"precondicion {texto!r} no se cumple"

    if unidad.motivo_no_calculo is None:
        for texto, expresion in plan.subexpresiones:
            parcial = _evaluar(expresion, contexto, f"{prefijo}: {texto}")
            if isinstance(parcial, Decimal):
                traza.append(f"{prefijo}: {texto} = {_texto(parcial)}")
        valor = _evaluar(plan.formula_unidad, contexto, f"{prefijo}: formula")
        if valor is NO_EVALUABLE:
            faltan = sorted(n for n in plan.formula_unidad.identificadores if n not in datos)
            unidad.motivo_no_calculo = f"faltan variables para la formula: {', '.join(faltan)}"
            traza.append(f"{prefijo}: {plan.salida_unidad} no calculable ({unidad.motivo_no_calculo})")
        else:
            unidad.salida = _decimal_resultado(valor, f"{prefijo}: formula")
            traza.append(
                f"{prefijo}: {plan.salida_unidad} = {plan.texto_formula_unidad} = {_texto(unidad.salida)}"
            )
    else:
        traza.append(f"{prefijo}: no se calcula ({unidad.motivo_no_calculo})")

    datos_control: dict[str, object] = dict(datos)
    if unidad.salida is not None:
        datos_control[plan.salida_unidad] = unidad.salida
    contexto_control = ContextoDict(datos_control)
    fallidos: list[_Control] = []
    for control in plan.controles:
        resultado = _evaluar(control.expresion, contexto_control, f"{prefijo}: control {control.id}")
        unidad.controles[control.id] = resultado
        sufijo = f" ({control.mensaje})" if resultado is False and control.mensaje else ""
        traza.append(f"{prefijo}: control {control.id} {control.texto!r} = {resultado}{sufijo}")
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
    unidades: Mapping[str, Mapping[str, Decimal]],
    tablas: Mapping[str, Tabla],
    *,
    provisional: bool = False,
    fecha: date | None = None,
) -> ResultadoCalculo:
    """Calcula la salida por unidad y el total segun la spec. Ver la cabecera del modulo.

    `unidades`: `num_serie_motor -> {variable: Decimal}` con las variables de entrada consolidadas. Un `float`
    es `ErrorCalculo`. Las variables que la spec deriva se ignoran si llegan aqui (aviso).
    `fecha`: fecha de evaluacion para comprobar la vigencia de las tablas (solo aviso).
    """
    if not isinstance(unidades, Mapping):
        raise ErrorCalculo("unidades debe ser un mapping num_serie_motor -> {variable: Decimal}")
    with localcontext() as ctx:
        ctx.prec = PRECISION_DECIMAL
        plan = _planificar(spec_datos, tablas)
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
                    f"total: {plan.salida_total} = {plan.texto_formula_total} = {sumandos}{_texto(total)}"
                )
                if plan.redondeo is not None:
                    total_cae = int(total.to_integral_value(rounding=ROUND_DOWN))
                    etiqueta = f"; {plan.redondeo.interpretacion}" if plan.redondeo.interpretacion else ""
                    traza.append(
                        f"total: {plan.redondeo.clave} = {total_cae} ({plan.redondeo.criterio}{etiqueta})"
                    )
                    if plan.redondeo.interpretacion:
                        _unir_unicos(interpretaciones, [plan.redondeo.interpretacion])
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
        datos = {f.name: _serializar(getattr(valor, f.name)) for f in fields(valor)}
        if isinstance(valor, ResultadoUnidad):
            datos["p_fuente"] = valor.p_fuente
        return datos
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
