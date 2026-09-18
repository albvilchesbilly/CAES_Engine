"""Rules Engine (N2): evalua las reglas de la spec sobre la actuacion consolidada y emite el veredicto.

Funcion pura (docs/04 §1): misma actuacion + misma spec + misma fecha = mismo resultado. No lee documentos,
no llama a ningun modelo, no tiene estado. No conoce ninguna ficha: todo identificador de la `logica` se
resuelve contra la spec, la actuacion consolidada, las tablas y el resultado del calculo (regla de oro 4).
El unico vocabulario ajeno al marco esta en `ALIAS_CONTEXTO`, declarado y acotado mas abajo.

Que hace `evaluar_actuacion`, en este orden (docs/04 §5.1):

1. `cabecera` → 2. `ambito` → 3. `consistencia` → 4. calculo (N3) → 5. `post_calculo` → 6. `resto`.

Paradas:

- Si falla una regla **bloqueante** de `ambito`, se evaluan todas las de esa fase y se **detiene**: las fases
  siguientes no se evaluan y sus reglas salen `NO_EVALUABLE` con motivo `fase no evaluada: detenido en
  ambito` (caso D: un ahorro declarado en ficha o convenio no se calcula ni se contrasta).
- Si falla una regla bloqueante de `cabecera` o de `consistencia`, se evaluan todas las de esa fase, se
  saltan el calculo y `post_calculo`, y **si** se evalua `resto`, para que el informe liste de una vez todas
  las carencias documentales (caso C).
- Un conflicto consolidado (`ActuacionConsolidada.conflictos`, regla de oro 6) bloquea por si mismo: el
  veredicto es al menos `BLOQUEADO`, no se calcula y `bloqueo_por_conflicto` nombra las variables, aunque la
  regla que las cruza quede `NO_EVALUABLE` (docs/04 §4.2, ADR-002 §3 fila F0.8 → F0.9).

Orden interno frente a orden del informe: `resto` se **evalua** antes del calculo (sus reglas no pueden
referenciar salidas del calculo, porque el Spec Registry manda a `post_calculo` toda regla que las use) para
poder decidir si procede un calculo provisional; `Evaluacion.resultados` se entrega siempre en orden de fase.

Calculo provisional (docs/04 §4.1 y §4.2, caso B): si el veredicto que arrojan las reglas ya evaluadas es
`SUBSANABLE` y a una unidad le falta **una** entrada del plan que participa en una derivada junto a otra
entrada presente (la derivacion del menor de dos valores), se sustituye la ausente por la presente, se marca
el resultado `provisional` y se deja el aviso `<ausente> ausente: calculo provisional con <derivada> =
<sustituta>`. Nunca se hace para un veredicto `PREVALIDADO`: un ahorro sin el dato que lo sostiene no se
publica como acreditado. La derivada y las entradas salen del `Plan`, no de una lista en codigo.

Veredicto por prioridad `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO` (`VEREDICTO_POR_SEVERIDAD`
sobre las reglas que **fallan**). `NO_EVALUABLE` nunca cambia el veredicto y `AVISO` tampoco: un `AVISO` que
falla va a `Evaluacion.avisos`.

Contexto de evaluacion (ADR-002 §2.4; `construir_contexto` es publica y testeable). Cada dato consolidado
expone una familia de nombres, con `X` el nombre de la variable o del hecho documental:

| Nombre | Valor |
|---|---|
| `X` | `DatoConsolidado.valor_consumido` (tipado; `None` → `NO_EVALUABLE`) |
| `X.valores_por_fuente`, `X_por_fuente` | `dict` tipo de documento → valor canonico (cadenas) |
| `X.demostrado`, `X.declarado`, `X.derivado` | `valores_tipados_por_tipo_evidencia` |
| `X.evidencia` | `tipo_evidencia` consumido |
| `X.fuente` | origen del valor: el de la derivacion del `Plan` si la spec la deriva, el del calculo si ya
  se ha calculado, y si no la `fuente_primaria` del dato |

Ademas: las listas de `ambito` y de cualquier bloque de constantes de la spec; cada tabla por su `id` como
lista de filas; `doc` (coleccion de `documentacion` con `obligatorio` ya resuelto a `bool`) y la funcion
`presente`; la coleccion de unidades bajo el nombre que la spec usa para el nivel de unidad; las salidas del
calculo (por unidad y total, con y sin el sufijo del valor truncado), las derivadas y los controles fisicos
por su `id`.

Limitaciones conocidas (deuda declarada, ver el informe de F0.9 y ADR-002 §3):

- `unique(NOMBRE)` sin sufijo (consistencia de numeros de serie o de titular entre documentos) tiene que
  comparar los valores **por fuente**, no el escalar ya consolidado: sobre el escalar siempre seria cierto.
  Como `Expresion` no expone el arbol, los argumentos directos de `unique(` se detectan con
  `argumentos_unique()` sobre el texto de la `logica` y se sustituyen en el contexto de esa regla. Lo limpio
  es que el parser los publique (`Expresion.argumentos_unique`) o que la spec escriba el sufijo.
- `ALIAS_CONTEXTO` y las dos reglas de alias genericas (`_alias_plural`, `_alias_requisitos`) resuelven los
  nombres de la `logica` que no son variables ni hechos consolidados. Es vocabulario de ficha en el nucleo:
  su sitio es un bloque `contexto:` de la spec (v1.2), que lo declararia junto a la ficha.

Nada de `eval`, `exec` ni `compile`: toda cadena de la spec pasa por `engine.expresiones.compilar`. No
importa nada de agentes/, salida/, generator/ ni tests/.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from engine.calculo import SUFIJO_CAE, Plan, ResultadoCalculo, ResultadoUnidad, calcular
from engine.evidencias import ActuacionConsolidada, DatoConsolidado
from engine.expresiones import (
    NO_EVALUABLE,
    Contexto,
    ContextoDict,
    ContextoElemento,
    ErrorCargaExpresion,
    ErrorEvaluacionExpresion,
    compilar,
)
from engine.spec_registry import (
    NIVEL_UNIDAD,
    NIVELES_VARIABLE_UNIDAD,
    OBLIGATORIO_CONDICIONAL,
    SEVERIDAD_AMBITO,
    SEVERIDAD_DATOS,
    SEVERIDAD_SUBSANABLE,
    SEVERIDADES_BLOQUEANTES,
    TIPOS_EVIDENCIA,
    Regla,
    Spec,
    raiz_de,
)

# --- Veredicto (docs/04 §4.1) ------------------------------------------------------------------------
VEREDICTO_NO_ELEGIBLE = "NO_ELEGIBLE"
VEREDICTO_BLOQUEADO = "BLOQUEADO"
VEREDICTO_SUBSANABLE = "SUBSANABLE"
VEREDICTO_PREVALIDADO = "PREVALIDADO"
ORDEN_VEREDICTO = (VEREDICTO_NO_ELEGIBLE, VEREDICTO_BLOQUEADO, VEREDICTO_SUBSANABLE, VEREDICTO_PREVALIDADO)
VEREDICTO_POR_SEVERIDAD: Mapping[str, str] = {
    SEVERIDAD_AMBITO: VEREDICTO_NO_ELEGIBLE,
    SEVERIDAD_DATOS: VEREDICTO_BLOQUEADO,
    SEVERIDAD_SUBSANABLE: VEREDICTO_SUBSANABLE,
}

# --- Fases (docs/04 §5.1). `calculo` no es una fase de reglas: es el paso de N3 entre 3 y 5. -----------
FASE_CABECERA = "cabecera"
FASE_AMBITO = "ambito"
FASE_CONSISTENCIA = "consistencia"
FASE_CALCULO = "calculo"
FASE_POST_CALCULO = "post_calculo"
FASE_RESTO = "resto"
ORDEN_FASES = (
    FASE_CABECERA,
    FASE_AMBITO,
    FASE_CONSISTENCIA,
    FASE_CALCULO,
    FASE_POST_CALCULO,
    FASE_RESTO,
)
FASES_PREVIAS = (FASE_CABECERA, FASE_AMBITO, FASE_CONSISTENCIA)

# --- Sufijos de la familia de nombres de un dato consolidado (ADR-002 §2.4) ---------------------------
SUFIJO_VALORES_POR_FUENTE = ".valores_por_fuente"
SUFIJO_POR_FUENTE = "_por_fuente"
SUFIJO_EVIDENCIA = ".evidencia"
SUFIJO_FUENTE = ".fuente"
SUFIJOS_CONSOLIDACION = (
    SUFIJO_VALORES_POR_FUENTE,
    SUFIJO_POR_FUENTE,
    SUFIJO_EVIDENCIA,
    SUFIJO_FUENTE,
) + tuple(f".{tipo}" for tipo in sorted(TIPOS_EVIDENCIA))

NOMBRE_COLECCION_DOCUMENTOS = "doc"
NOMBRE_FUNCION_PRESENTE = "presente"
SUFIJOS_PLURAL = ("s", "es")

MOTIVO_DETENIDO = "fase no evaluada: detenido en {fase}"
MOTIVO_SIN_CALCULO = "fase no evaluada: sin calculo ({motivo})"
MOTIVO_SIN_UNIDADES = "sin unidades sobre las que evaluar"
MOTIVO_ERROR_CONTEXTO = "error de contexto: {detalle}"
MOTIVO_DATOS_AUSENTES = "datos ausentes: {nombres}"
MOTIVO_NO_VIGENTE = "regla no vigente el {fecha}"

# Patrones como texto, sin precompilar: el fuente del nucleo no contiene la llamada `compile` (ADR-002 §3).
PATRON_UNIQUE = r"\bunique\s*\(\s*([A-Za-z_][A-Za-z_0-9.]*)\s*\)"
PATRON_PERTENENCIA = r"\b([A-Za-z_][A-Za-z_0-9]*)\s+in\s+([A-Za-z_][A-Za-z_0-9]*)\b"

#: Nombres de la `logica` que no son variables de la spec ni hechos que produzca el consolidador y que este
#: modulo resuelve por si mismo. **Es deuda**: su sitio es un bloque `contexto:` de la spec (propuesta para
#: v1.2), que declararia junto a la ficha de donde sale cada nombre. Mientras tanto se declaran aqui, uno a
#: uno, con su origen y su interpretacion, para que ninguna resolucion quede implicita en el codigo.
#: Las demas resoluciones son genericas y estan en `_alias_plural` (singular de un hecho de tipo lista) y
#: `_alias_requisitos` (`<x> in <tipo de documento>` con `requisitos` declarados en la spec).
ALIAS_CONTEXTO: Mapping[str, Mapping[str, str]] = {
    "solicitud.fecha": {
        "origen": "fecha_evaluacion",
        "interpretacion": "INT-10",
        "nota": (
            "en prevalidacion no hay solicitud presentada: se toma la fecha de evaluacion "
            "(ADR-002 §2.3 y §6.3, INT-10 propuesto, pendiente de Billy)"
        ),
    },
}
ORIGEN_FECHA_EVALUACION = "fecha_evaluacion"


class ErrorReglas(Exception):
    """Entrada mal construida para el motor de reglas (no una carencia de la actuacion)."""


class Resultado(Enum):
    """Los tres resultados de una regla (docs/04 §4.2, docs/03 §14.b)."""

    CUMPLE = "CUMPLE"
    FALLA = "FALLA"
    NO_EVALUABLE = "NO_EVALUABLE"


@dataclass(frozen=True)
class ResultadoRegla:
    """Resultado de una regla sobre una actuacion, con su ficha de identidad de la spec."""

    id: str
    resultado: Resultado
    severidad: str
    fase: str
    nivel: str
    descripcion: str
    referencia: str | None = None
    interpretacion: str | None = None
    por_unidad: Mapping[str, Resultado] = field(default_factory=dict)
    motivo: str | None = None
    subsanacion: Mapping[str, object] = field(default_factory=dict)

    @property
    def falla(self) -> bool:
        return self.resultado is Resultado.FALLA

    @property
    def bloqueante(self) -> bool:
        return self.severidad in SEVERIDADES_BLOQUEANTES

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "resultado": self.resultado.value,
            "severidad": self.severidad,
            "fase": self.fase,
            "nivel": self.nivel,
            "descripcion": self.descripcion,
            "referencia": self.referencia,
            "interpretacion": self.interpretacion,
            "por_unidad": {k: v.value for k, v in self.por_unidad.items()},
            "motivo": self.motivo,
        }


@dataclass
class Evaluacion:
    """Veredicto de una actuacion con la traza completa de como se llego a el."""

    resultados: list[ResultadoRegla]
    veredicto: str
    hash_reglas: str
    fases_evaluadas: tuple[str, ...]
    fases_saltadas: tuple[str, ...]
    calculo: ResultadoCalculo | None
    interpretaciones_aplicadas: list[str]
    carencias: list[Mapping[str, object]]
    avisos: list[str]
    bloqueo_por_conflicto: tuple[str, ...] = ()

    def resultado(self, id_regla: str) -> ResultadoRegla:
        for resultado in self.resultados:
            if resultado.id == id_regla:
                return resultado
        raise KeyError(f"la evaluacion no contiene la regla {id_regla!r}")

    def por_resultado(self, resultado: Resultado) -> list[ResultadoRegla]:
        return [r for r in self.resultados if r.resultado is resultado]

    @property
    def falladas(self) -> list[str]:
        return [r.id for r in self.resultados if r.falla]

    @property
    def no_evaluables(self) -> list[str]:
        return [r.id for r in self.resultados if r.resultado is Resultado.NO_EVALUABLE]

    def a_dict(self) -> dict[str, object]:
        return {
            "veredicto": self.veredicto,
            "hash_reglas": self.hash_reglas,
            "fases_evaluadas": list(self.fases_evaluadas),
            "fases_saltadas": list(self.fases_saltadas),
            "resultados": [r.a_dict() for r in self.resultados],
            "interpretaciones_aplicadas": list(self.interpretaciones_aplicadas),
            "carencias": [dict(c) for c in self.carencias],
            "avisos": list(self.avisos),
            "bloqueo_por_conflicto": list(self.bloqueo_por_conflicto),
        }


# ---------------------------------------------------------------------------
# Contexto de evaluacion
# ---------------------------------------------------------------------------


@dataclass
class ContextoEvaluacion:
    """Espacio de nombres de una evaluacion (cumple `engine.expresiones.Contexto`).

    `datos` resuelve los nombres de nivel actuacion (mas las constantes de la spec, las tablas, la coleccion
    de documentos y las salidas totales del calculo); `unidades` guarda, por unidad, el mapa de nombres de
    nivel unidad. Una regla de nivel unidad se evalua con un `ContextoElemento` sobre el mapa de su unidad,
    que delega en `datos` lo que no encuentra.
    """

    datos: dict[str, object]
    unidades: dict[str, dict[str, object]]
    avisos: list[str] = field(default_factory=list)
    interpretaciones: list[str] = field(default_factory=list)

    def resolver(self, nombre: str) -> object:
        return ContextoDict(self.datos).resolver(nombre)

    def contexto_actuacion(self, sustituciones: Mapping[str, object] | None = None) -> Contexto:
        if not sustituciones:
            return ContextoDict(self.datos)
        return ContextoDict({**self.datos, **sustituciones})

    def contexto_unidad(self, serie: str, sustituciones: Mapping[str, object] | None = None) -> Contexto:
        unidad = self.unidades.get(serie, {})
        if sustituciones:
            unidad = {**unidad, **sustituciones}
        return ContextoElemento(unidad, None, self.contexto_actuacion(sustituciones))


def _valores_por_fuente(dato: DatoConsolidado) -> dict[str, str]:
    return dict(dato.valores_por_fuente)


def _familia_dato(nombre: str, dato: DatoConsolidado) -> dict[str, object]:
    """Los nombres que un dato consolidado expone al lenguaje de expresiones (ADR-002 §2.4)."""
    familia: dict[str, object] = {nombre: dato.valor_consumido}
    valores = _valores_por_fuente(dato)
    familia[f"{nombre}{SUFIJO_VALORES_POR_FUENTE}"] = valores
    familia[f"{nombre}{SUFIJO_POR_FUENTE}"] = valores
    familia[f"{nombre}{SUFIJO_EVIDENCIA}"] = dato.tipo_evidencia
    familia[f"{nombre}{SUFIJO_FUENTE}"] = dato.fuente_primaria
    for tipo, valor in dato.valores_tipados_por_tipo_evidencia.items():
        familia[f"{nombre}.{tipo}"] = valor
    return familia


def _constantes_spec(spec: Spec) -> dict[str, object]:
    """Listas de constantes de la spec (`ambito.<lista>`) y tablas de referencia por su `id`."""
    datos: dict[str, object] = {}
    if isinstance(spec.ambito, Mapping):
        listas = {
            clave: list(valor)
            for clave, valor in spec.ambito.items()
            if isinstance(valor, list) and all(isinstance(v, str) for v in valor)
        }
        if listas:
            datos["ambito"] = listas
    for id_tabla, tabla in spec.tablas.items():
        datos[id_tabla] = tabla.como_coleccion()
    return datos


def _funcion_presente(actuacion: ActuacionConsolidada) -> Callable[[object], object]:
    """`presente(doc)`: hay al menos un documento de ese tipo en la actuacion (docs/04 §6.4)."""
    tipos = {str(t) for t in actuacion.documentos_por_tipo}

    def presente(elemento: object) -> object:
        tipo: object = None
        if isinstance(elemento, Mapping):
            tipo = elemento.get("tipo")
        elif isinstance(elemento, str):
            tipo = elemento
        if not isinstance(tipo, str) or not tipo:
            return NO_EVALUABLE
        return tipo in tipos

    return presente


def _obligatorio(decl: Mapping[str, object], contexto: Contexto, spec: Spec, avisos: list[str]) -> bool:
    """Resuelve `obligatorio` a `bool`; `condicional` evalua su `condicion` con el parser (ADR-002 §3 QA-1).

    Una condicion que no se puede evaluar (dato ausente, errata) deja el documento como **no obligatorio** y
    un aviso: mantenerla `NO_EVALUABLE` convertiria la regla de presencia documental en `NO_EVALUABLE` para
    siempre y ocultaria las carencias de los demas documentos obligatorios.
    """
    valor = decl.get("obligatorio")
    if isinstance(valor, bool):
        return valor
    identificacion = decl.get("id") or decl.get("tipo") or "documento"
    if str(valor) != OBLIGATORIO_CONDICIONAL:
        avisos.append(
            f"documentacion {identificacion}: `obligatorio` {valor!r} no es booleano ni condicional"
        )
        return False
    condicion = decl.get("condicion")
    detalle = ""
    if isinstance(condicion, str) and condicion.strip():
        try:
            expresion = compilar(condicion, enumerados=spec.enumerados)
            resultado = expresion.evaluar(contexto)
        except (ErrorCargaExpresion, ErrorEvaluacionExpresion) as exc:
            detalle = f" ({exc})"
        else:
            if isinstance(resultado, bool):
                return resultado
    avisos.append(
        f"documentacion {identificacion}: obligatoriedad condicional no evaluable "
        f"({condicion!r}){detalle}; se evalua como no obligatorio"
    )
    return False


def _coleccion_documentos(
    actuacion: ActuacionConsolidada, spec: Spec, contexto: Contexto, avisos: list[str]
) -> list[dict[str, object]]:
    presente = _funcion_presente(actuacion)
    coleccion: list[dict[str, object]] = []
    for decl in spec.documentacion:
        tipo = str(decl.get("tipo") or "")
        entrada: dict[str, object] = {
            "id": decl.get("id"),
            "tipo": tipo,
            "nombre": decl.get("nombre"),
            "obligatorio": _obligatorio(decl, contexto, spec, avisos),
            "requisitos": list(decl.get("requisitos") or []),
            "interpretacion": decl.get("interpretacion"),
            "presente": presente(tipo),
        }
        coleccion.append(entrada)
    return coleccion


def _nombres_coleccion_unidades(spec: Spec) -> tuple[str, ...]:
    """Nombre(s) que la spec da al nivel de unidad (`variables.*.nivel`); ahi va la lista de unidades."""
    nombres = {
        str(decl.get("nivel"))
        for decl in spec.variables.values()
        if decl.get("nivel") in NIVELES_VARIABLE_UNIDAD
    }
    return tuple(sorted(nombres)) or (NIVEL_UNIDAD,)


def _datos_unidad(
    datos_unidad: Mapping[str, DatoConsolidado], plan: Plan, resultado: ResultadoUnidad | None
) -> dict[str, object]:
    """Nombres de nivel unidad: datos consolidados, origen de cada derivada, derivadas, salida y controles."""
    unidad: dict[str, object] = {}
    for nombre, dato in datos_unidad.items():
        unidad.update(_familia_dato(nombre, dato))
    for derivada in plan.derivadas:
        # El origen de una variable que la spec deriva lo fija el plan y esta disponible antes de calcular
        # (por eso la regla que vigila el origen puede ir en la fase de consistencia). Si ademas llega un
        # valor homonimo de un documento, gana el del documento: el calculo lo ignorara, pero la regla tiene
        # que poder decir de donde salio (es lo que distingue la tabla de referencia de la ficha del
        # fabricante).
        unidad.setdefault(f"{derivada.nombre}{SUFIJO_FUENTE}", derivada.origen)
    if resultado is not None:
        for nombre, valor in resultado.derivadas.items():
            unidad[nombre] = valor
        for nombre, origen in resultado.fuentes.items():
            unidad[f"{nombre}{SUFIJO_FUENTE}"] = origen
        for id_control, valor in resultado.controles.items():
            unidad[id_control] = valor
        if resultado.salida is not None:
            unidad[plan.salida_unidad] = resultado.salida
    return unidad


def construir_contexto(
    actuacion: ActuacionConsolidada,
    spec: Spec,
    *,
    calculo: ResultadoCalculo | None = None,
    fecha_evaluacion: date,
) -> ContextoEvaluacion:
    """Espacio de nombres de la evaluacion. Ningun nombre de la ficha esta cableado (ver la cabecera)."""
    if not isinstance(fecha_evaluacion, date) or isinstance(fecha_evaluacion, datetime):
        raise ErrorReglas("fecha_evaluacion debe ser un datetime.date (no datetime)")
    avisos: list[str] = []
    interpretaciones: list[str] = []
    datos: dict[str, object] = _constantes_spec(spec)

    for nombre, dato in actuacion.variables.items():
        datos.update(_familia_dato(nombre, dato))

    for nombre, alias in ALIAS_CONTEXTO.items():
        if alias.get("origen") == ORIGEN_FECHA_EVALUACION:
            datos[nombre] = fecha_evaluacion

    datos[NOMBRE_COLECCION_DOCUMENTOS] = _coleccion_documentos(
        actuacion, spec, ContextoDict(dict(datos)), avisos
    )
    datos[NOMBRE_FUNCION_PRESENTE] = _funcion_presente(actuacion)

    por_unidad: Mapping[str, ResultadoUnidad] = (
        {u.num_serie_motor: u for u in calculo.por_unidad} if calculo is not None else {}
    )
    unidades: dict[str, dict[str, object]] = {
        serie: _datos_unidad(datos_unidad, spec.plan, por_unidad.get(serie))
        for serie, datos_unidad in actuacion.unidades.items()
    }
    lista_unidades = list(unidades.values())
    for nombre in _nombres_coleccion_unidades(spec):
        datos[nombre] = lista_unidades

    if calculo is not None:
        if calculo.total is not None:
            datos[spec.plan.salida_total] = calculo.total
        if calculo.total_cae is not None:
            datos[f"{spec.plan.salida_total}{SUFIJO_CAE}"] = Decimal(calculo.total_cae)

    return ContextoEvaluacion(
        datos=datos, unidades=unidades, avisos=avisos, interpretaciones=interpretaciones
    )


# ---------------------------------------------------------------------------
# Alias: nombres de la logica que no son variables ni hechos consolidados
# ---------------------------------------------------------------------------


def argumentos_unique(logica: str) -> tuple[str, ...]:
    """Nombres que son argumento directo de `unique(...)` y no llevan sufijo de consolidacion.

    Deuda: lo natural es que `Expresion` publique `argumentos_unique` al compilar (propuesta para el parser);
    mientras tanto se leen del texto de la `logica`, que es la fuente de verdad de la regla.
    """
    nombres: list[str] = []
    for nombre in re.findall(PATRON_UNIQUE, logica):
        if any(nombre.endswith(sufijo) for sufijo in SUFIJOS_CONSOLIDACION):
            continue
        if nombre not in nombres:
            nombres.append(nombre)
    return tuple(nombres)


def _alias_plural(nombre: str, actuacion: ActuacionConsolidada, serie: str | None) -> object:
    """Alias generico: el singular de un hecho consolidado de tipo lista resuelve a esa lista."""
    for sufijo in SUFIJOS_PLURAL:
        dato = actuacion.dato(nombre + sufijo, serie) or actuacion.dato(nombre + sufijo)
        if dato is not None and isinstance(dato.valor_consumido, list):
            return list(dato.valor_consumido)
    return None


def _es_prefijo(raiz: str, tipo: str) -> bool:
    return tipo == raiz or tipo.startswith(raiz + "_")


def _lista_bajo_raiz(actuacion: ActuacionConsolidada, tipo_documento: str) -> list | None:
    """Unico hecho consolidado de tipo lista cuya raiz es prefijo del tipo de documento (`T.*` para `T_x`)."""
    candidatos = sorted(
        (nombre, dato)
        for nombre, dato in actuacion.variables.items()
        if isinstance(dato.valor_consumido, list) and _es_prefijo(raiz_de(nombre), tipo_documento)
    )
    return list(candidatos[0][1].valor_consumido) if candidatos else None


def _alias_requisitos(logica: str, actuacion: ActuacionConsolidada, spec: Spec) -> dict[str, object]:
    """Alias generico `<x> in <tipo de documento>`: los `requisitos` que la spec exige a ese documento.

    El nombre de la izquierda (el elemento ligado) resuelve a la lista **declarada** en `documentacion` y el
    de la derecha a la lista **hallada** en la actuacion. Sin ninguno de los dos, la regla queda
    `NO_EVALUABLE`.
    """
    sustituciones: dict[str, object] = {}
    tipos = {
        str(decl.get("tipo")): list(decl.get("requisitos") or [])
        for decl in spec.documentacion
        if decl.get("requisitos")
    }
    for izquierda, derecha in re.findall(PATRON_PERTENENCIA, logica):
        declarados = tipos.get(derecha)
        if not declarados:
            continue
        hallados = _lista_bajo_raiz(actuacion, derecha)
        sustituciones[izquierda] = declarados
        if hallados is not None:
            sustituciones[derecha] = hallados
    return sustituciones


def _sustituciones(
    regla: Regla, actuacion: ActuacionConsolidada, spec: Spec, serie: str | None
) -> dict[str, object]:
    """Nombres que esta regla resuelve de forma distinta a la general (ver la cabecera del modulo)."""
    sustituciones: dict[str, object] = {}
    for nombre in argumentos_unique(regla.logica):
        dato = actuacion.dato(nombre, serie) or actuacion.dato(nombre)
        if dato is not None:
            sustituciones[nombre] = _valores_por_fuente(dato)
    sustituciones.update(_alias_requisitos(regla.logica, actuacion, spec))
    for nombre in sorted(regla.expresion.identificadores):
        if nombre in sustituciones:
            continue
        if actuacion.dato(nombre, serie) is not None or actuacion.dato(nombre) is not None:
            continue
        plural = _alias_plural(nombre, actuacion, serie)
        if plural is not None:
            sustituciones[nombre] = plural
    return sustituciones


# ---------------------------------------------------------------------------
# Evaluacion de una regla
# ---------------------------------------------------------------------------


def _a_resultado(valor: object) -> Resultado:
    if valor is NO_EVALUABLE:
        return Resultado.NO_EVALUABLE
    return Resultado.CUMPLE if valor is True else Resultado.FALLA


def _agregar_unidades(resultados: Mapping[str, Resultado]) -> Resultado:
    """CUMPLE si cumple en todas; FALLA si falla en alguna; NO_EVALUABLE si no hay unidades (ADR-002 §2.4)."""
    if not resultados:
        return Resultado.NO_EVALUABLE
    if any(r is Resultado.FALLA for r in resultados.values()):
        return Resultado.FALLA
    if any(r is Resultado.NO_EVALUABLE for r in resultados.values()):
        return Resultado.NO_EVALUABLE
    return Resultado.CUMPLE


def _ausentes(regla: Regla, contexto: Contexto) -> list[str]:
    nombres = regla.expresion.identificadores - regla.expresion.colecciones_ligadas
    return sorted(n for n in nombres if contexto.resolver(n) is NO_EVALUABLE)


def _evaluar_en(regla: Regla, contexto: Contexto) -> tuple[Resultado, str | None, str | None]:
    """(resultado, motivo, aviso) de una regla sobre un contexto concreto."""
    try:
        valor = regla.expresion.evaluar(contexto)
    except ErrorEvaluacionExpresion as exc:
        motivo = MOTIVO_ERROR_CONTEXTO.format(detalle=exc)
        return Resultado.NO_EVALUABLE, motivo, f"{regla.id}: {motivo}"
    resultado = _a_resultado(valor)
    if resultado is not Resultado.NO_EVALUABLE:
        return resultado, None, None
    ausentes = _ausentes(regla, contexto)
    motivo = MOTIVO_DATOS_AUSENTES.format(nombres=", ".join(ausentes)) if ausentes else None
    return resultado, motivo, None


def _resultado_regla(
    regla: Regla,
    resultado: Resultado,
    *,
    por_unidad: Mapping[str, Resultado] | None = None,
    motivo: str | None = None,
) -> ResultadoRegla:
    return ResultadoRegla(
        id=regla.id,
        resultado=resultado,
        severidad=regla.severidad,
        fase=regla.fase,
        nivel=regla.nivel,
        descripcion=regla.descripcion,
        referencia=regla.referencia,
        interpretacion=regla.interpretacion,
        por_unidad=dict(por_unidad or {}),
        motivo=motivo,
        subsanacion=dict(regla.subsanacion),
    )


def evaluar_regla(
    regla: Regla,
    actuacion: ActuacionConsolidada,
    spec: Spec,
    contexto: ContextoEvaluacion,
    avisos: list[str] | None = None,
    *,
    fecha_evaluacion: date,
) -> ResultadoRegla:
    """Evalua una regla (por unidad si su `nivel` lo es) y nunca deja escapar una excepcion de evaluacion.

    `avisos` recoge, si se pasa, los avisos que genere la evaluacion (contexto mal construido).
    """
    avisos = [] if avisos is None else avisos
    if not regla.vigencia.contiene(fecha_evaluacion):
        return _resultado_regla(
            regla, Resultado.NO_EVALUABLE, motivo=MOTIVO_NO_VIGENTE.format(fecha=fecha_evaluacion.isoformat())
        )
    if regla.nivel == NIVEL_UNIDAD:
        por_unidad: dict[str, Resultado] = {}
        motivos: list[str] = []
        for serie in contexto.unidades:
            sustituciones = _sustituciones(regla, actuacion, spec, serie)
            resultado, motivo, aviso = _evaluar_en(regla, contexto.contexto_unidad(serie, sustituciones))
            por_unidad[serie] = resultado
            if motivo:
                motivos.append(f"{serie}: {motivo}")
            if aviso:
                avisos.append(aviso)
        agregado = _agregar_unidades(por_unidad)
        motivo_final = None
        if agregado is Resultado.NO_EVALUABLE:
            motivo_final = "; ".join(motivos) if motivos else MOTIVO_SIN_UNIDADES
        return _resultado_regla(regla, agregado, por_unidad=por_unidad, motivo=motivo_final)

    sustituciones = _sustituciones(regla, actuacion, spec, None)
    resultado, motivo, aviso = _evaluar_en(regla, contexto.contexto_actuacion(sustituciones))
    if aviso:
        avisos.append(aviso)
    return _resultado_regla(regla, resultado, motivo=motivo)


# ---------------------------------------------------------------------------
# Veredicto, carencias e interpretaciones
# ---------------------------------------------------------------------------


def _peor(veredictos: Iterable[str]) -> str:
    peor = VEREDICTO_PREVALIDADO
    for veredicto in veredictos:
        if ORDEN_VEREDICTO.index(veredicto) < ORDEN_VEREDICTO.index(peor):
            peor = veredicto
    return peor


def veredicto_de(resultados: Iterable[ResultadoRegla], *, conflicto: bool = False) -> str:
    """Veredicto por prioridad a partir de las reglas que **fallan** (docs/04 §4.1); `AVISO` no cuenta."""
    veredictos = [
        VEREDICTO_POR_SEVERIDAD[r.severidad]
        for r in resultados
        if r.falla and r.severidad in VEREDICTO_POR_SEVERIDAD
    ]
    if conflicto:
        veredictos.append(VEREDICTO_BLOQUEADO)
    return _peor(veredictos)


def _documentos_de_carencia(
    regla: Regla, spec: Spec, documentos: Sequence[Mapping[str, object]]
) -> list[str]:
    """Documentos que subsanan la regla: los que declara la spec o, si no, los que citan sus variables."""
    declarados = [str(d) for d in (regla.subsanacion.get("documentos") or [])]
    if declarados:
        return declarados
    tipos: list[str] = []
    for raiz in sorted(regla.raices):
        decl = spec.variables.get(raiz)
        if isinstance(decl, Mapping):
            for fuente in decl.get("fuentes") or []:
                if str(fuente) not in tipos:
                    tipos.append(str(fuente))
            derivacion = decl.get("derivacion")
            if isinstance(derivacion, Mapping):
                fuente = derivacion.get("fuente")
                if isinstance(fuente, str) and ":" not in fuente and fuente not in tipos:
                    tipos.append(fuente)
        for entrada in spec.documentacion:
            tipo = str(entrada.get("tipo") or "")
            if tipo and _es_prefijo(raiz, tipo) and tipo not in tipos:
                tipos.append(tipo)
    if NOMBRE_FUNCION_PRESENTE in regla.expresion.funciones:
        for entrada in documentos:
            if entrada.get("obligatorio") is True and entrada.get("presente") is not True:
                tipo = str(entrada.get("tipo") or "")
                if tipo and tipo not in tipos:
                    tipos.append(tipo)
    return tipos


def _carencias(
    resultados: Iterable[ResultadoRegla], spec: Spec, documentos: Sequence[Mapping[str, object]]
) -> list[Mapping[str, object]]:
    carencias: list[Mapping[str, object]] = []
    for resultado in resultados:
        if not resultado.falla:
            continue
        regla = spec.regla(resultado.id)
        mensaje = str(regla.subsanacion.get("mensaje") or regla.descripcion)
        carencias.append(
            {
                "id": regla.id,
                "severidad": regla.severidad,
                "mensaje": mensaje,
                "documentos": _documentos_de_carencia(regla, spec, documentos),
            }
        )
    return carencias


def _interpretaciones(
    resultados: Iterable[ResultadoRegla],
    actuacion: ActuacionConsolidada,
    calculo: ResultadoCalculo | None,
    alias_consumidos: Iterable[str],
) -> list[str]:
    aplicadas: set[str] = set()
    for resultado in resultados:
        if resultado.resultado is not Resultado.NO_EVALUABLE and resultado.interpretacion:
            aplicadas.add(str(resultado.interpretacion))
    if calculo is not None:
        aplicadas.update(str(i) for i in calculo.interpretaciones)
    datos: list[DatoConsolidado] = list(actuacion.variables.values())
    for unidad in actuacion.unidades.values():
        datos.extend(unidad.values())
    for dato in datos:
        if dato.interpretacion and dato.valor_consumido is not None:
            aplicadas.add(str(dato.interpretacion))
    for nombre in alias_consumidos:
        interpretacion = ALIAS_CONTEXTO.get(nombre, {}).get("interpretacion")
        if interpretacion:
            aplicadas.add(str(interpretacion))
    return sorted(aplicadas)


# ---------------------------------------------------------------------------
# Calculo
# ---------------------------------------------------------------------------


def _entradas_unidad(datos_unidad: Mapping[str, DatoConsolidado], plan: Plan) -> dict[str, Decimal | None]:
    entradas: dict[str, Decimal | None] = {}
    for nombre in sorted(plan.entradas_requeridas):
        dato = datos_unidad.get(nombre)
        valor = dato.valor_consumido if dato is not None else None
        entradas[nombre] = valor if isinstance(valor, Decimal) else None
    return entradas


def _sustituir_entrada_ausente(
    plan: Plan, entradas: Mapping[str, Decimal | None]
) -> tuple[dict[str, Decimal | None], list[str]]:
    """Calculo provisional del caso B: la unica entrada ausente toma el valor de su hermana en la derivada.

    Solo se aplica si la derivada combina exactamente esas dos entradas (`min(a, b)` y equivalentes): el
    resultado es entonces el de la entrada presente, que es el criterio conservador de la ficha.
    """
    ausentes = [n for n, v in entradas.items() if v is None]
    if len(ausentes) != 1:
        return dict(entradas), []
    ausente = ausentes[0]
    for derivada in plan.derivadas:
        if derivada.expresion is None or ausente not in derivada.expresion.identificadores:
            continue
        hermanas = [
            n for n in sorted(derivada.expresion.identificadores - {ausente}) if entradas.get(n) is not None
        ]
        if len(hermanas) != 1:
            continue
        nuevas = dict(entradas)
        nuevas[ausente] = entradas[hermanas[0]]
        aviso = f"{ausente} ausente: calculo provisional con {derivada.nombre} = {hermanas[0]}"
        return nuevas, [aviso]
    return dict(entradas), []


# ---------------------------------------------------------------------------
# evaluar_actuacion
# ---------------------------------------------------------------------------


def _alias_consumidos(reglas: Iterable[Regla]) -> list[str]:
    nombres: set[str] = set()
    for regla in reglas:
        nombres |= {n for n in regla.expresion.identificadores if n in ALIAS_CONTEXTO}
    return sorted(nombres)


def evaluar_actuacion(
    actuacion: ActuacionConsolidada,
    spec: Spec,
    *,
    fecha_evaluacion: date,
    calcular_fn: Callable[..., ResultadoCalculo] = calcular,
) -> Evaluacion:
    """Evalua las 26 reglas de la spec por fases, calcula si procede y emite el veredicto. Ver la cabecera."""
    if not isinstance(actuacion, ActuacionConsolidada):
        raise ErrorReglas("actuacion debe ser una ActuacionConsolidada")
    if not isinstance(fecha_evaluacion, date) or isinstance(fecha_evaluacion, datetime):
        raise ErrorReglas("fecha_evaluacion debe ser un datetime.date (no datetime)")

    avisos: list[str] = list(actuacion.avisos)
    orden_spec = spec.estados.get("orden_evaluacion") if isinstance(spec.estados, Mapping) else None
    if isinstance(orden_spec, list) and tuple(str(v) for v in orden_spec) != ORDEN_VEREDICTO:
        avisos.append(
            f"la spec declara otro orden de veredictos {orden_spec}; "
            f"se aplica el del marco {list(ORDEN_VEREDICTO)}"
        )

    contexto = construir_contexto(actuacion, spec, calculo=None, fecha_evaluacion=fecha_evaluacion)
    avisos.extend(contexto.avisos)
    documentos = contexto.datos.get(NOMBRE_COLECCION_DOCUMENTOS) or []
    por_fase = spec.reglas_por_fase()
    resultados: dict[str, ResultadoRegla] = {}
    evaluadas: list[str] = []
    saltadas: list[str] = []

    def evaluar_fase(fase: str) -> list[ResultadoRegla]:
        de_la_fase = [
            evaluar_regla(regla, actuacion, spec, contexto, avisos, fecha_evaluacion=fecha_evaluacion)
            for regla in por_fase.get(fase, [])
        ]
        for resultado in de_la_fase:
            resultados[resultado.id] = resultado
        evaluadas.append(fase)
        return de_la_fase

    def saltar_fase(fase: str, motivo: str) -> None:
        for regla in por_fase.get(fase, []):
            resultados[regla.id] = _resultado_regla(regla, Resultado.NO_EVALUABLE, motivo=motivo)
        saltadas.append(fase)

    def hay_bloqueo(de_la_fase: Iterable[ResultadoRegla]) -> bool:
        return any(r.falla and r.bloqueante for r in de_la_fase)

    bloqueo_por_conflicto = tuple(
        sorted({dato.variable for dato in actuacion.conflictos if isinstance(dato, DatoConsolidado)})
    )
    if bloqueo_por_conflicto:
        avisos.append(
            f"conflicto entre fuentes fiables en {', '.join(bloqueo_por_conflicto)}: no se calcula y el "
            f"veredicto es al menos {VEREDICTO_BLOQUEADO} (regla de oro 6)"
        )

    detenido_en: str | None = None
    bloqueo_previo = False
    for fase in FASES_PREVIAS:
        de_la_fase = evaluar_fase(fase)
        if hay_bloqueo(de_la_fase):
            bloqueo_previo = True
            if fase == FASE_AMBITO:
                detenido_en = FASE_AMBITO
                break

    if detenido_en is not None:
        motivo = MOTIVO_DETENIDO.format(fase=detenido_en)
        for fase in (FASE_CONSISTENCIA, FASE_CALCULO, FASE_POST_CALCULO, FASE_RESTO):
            saltar_fase(fase, motivo)
        return _componer(
            spec,
            actuacion,
            resultados,
            por_fase,
            veredicto_de(resultados.values(), conflicto=bool(bloqueo_por_conflicto)),
            None,
            evaluadas,
            saltadas,
            avisos,
            documentos,
            bloqueo_por_conflicto,
        )

    evaluar_fase(FASE_RESTO)
    veredicto_parcial = veredicto_de(resultados.values(), conflicto=bool(bloqueo_por_conflicto))

    calculo: ResultadoCalculo | None = None
    motivo_sin_calculo: str | None = None
    if bloqueo_por_conflicto:
        motivo_sin_calculo = f"conflicto en {', '.join(bloqueo_por_conflicto)}"
    elif bloqueo_previo:
        falladas = ", ".join(r.id for r in resultados.values() if r.falla and r.bloqueante)
        motivo_sin_calculo = f"reglas bloqueantes falladas: {falladas}"
    if motivo_sin_calculo is None:
        provisional = veredicto_parcial == VEREDICTO_SUBSANABLE
        unidades: dict[str, dict[str, Decimal | None]] = {}
        for serie, datos_unidad in actuacion.unidades.items():
            entradas = _entradas_unidad(datos_unidad, spec.plan)
            if provisional:
                entradas, avisos_sustitucion = _sustituir_entrada_ausente(spec.plan, entradas)
                avisos.extend(avisos_sustitucion)
            unidades[serie] = entradas
        for nota in spec.plan.precondiciones_delegadas:
            avisos.append(
                f"precondicion delegada del calculo comprobada por el motor de reglas: {nota} "
                f"(ninguna bloqueante fallida antes del calculo)"
            )
        try:
            calculo = calcular_fn(
                spec.datos,
                unidades,
                spec.tablas,
                provisional=provisional,
                fecha=fecha_evaluacion,
                plan=spec.plan,
            )
        except Exception as exc:  # noqa: BLE001 - el calculo nunca tumba la evaluacion
            motivo_sin_calculo = f"error de calculo: {exc}"
            avisos.append(motivo_sin_calculo)
            calculo = None
        else:
            avisos.extend(calculo.avisos)
    if calculo is not None:
        contexto = construir_contexto(actuacion, spec, calculo=calculo, fecha_evaluacion=fecha_evaluacion)
        evaluadas.append(FASE_CALCULO)
        evaluar_fase(FASE_POST_CALCULO)
    else:
        saltadas.append(FASE_CALCULO)
        saltar_fase(FASE_POST_CALCULO, MOTIVO_SIN_CALCULO.format(motivo=motivo_sin_calculo or "sin calculo"))

    veredicto = veredicto_de(resultados.values(), conflicto=bool(bloqueo_por_conflicto))
    if calculo is not None and veredicto == VEREDICTO_SUBSANABLE and not calculo.provisional:
        calculo.provisional = True
        calculo.traza.append("calculo provisional: estimacion no acreditada (veredicto SUBSANABLE)")
    for resultado in resultados.values():
        if resultado.falla and resultado.severidad not in VEREDICTO_POR_SEVERIDAD:
            aviso = f"aviso {resultado.id}: {resultado.descripcion}"
            if aviso not in avisos:
                avisos.append(aviso)

    return _componer(
        spec,
        actuacion,
        resultados,
        por_fase,
        veredicto,
        calculo,
        evaluadas,
        saltadas,
        avisos,
        documentos,
        bloqueo_por_conflicto,
    )


def _componer(
    spec: Spec,
    actuacion: ActuacionConsolidada,
    resultados: Mapping[str, ResultadoRegla],
    por_fase: Mapping[str, list[Regla]],
    veredicto: str,
    calculo: ResultadoCalculo | None,
    evaluadas: Sequence[str],
    saltadas: Sequence[str],
    avisos: Sequence[str],
    documentos: Sequence[Mapping[str, object]],
    bloqueo_por_conflicto: tuple[str, ...] = (),
) -> Evaluacion:
    ordenados: list[ResultadoRegla] = []
    for fase in ORDEN_FASES:
        for regla in por_fase.get(fase, []):
            resultado = resultados.get(regla.id)
            if resultado is not None:
                ordenados.append(resultado)
    evaluados = {r.id for r in ordenados if r.resultado is not Resultado.NO_EVALUABLE}
    alias_consumidos = _alias_consumidos(
        regla for fase in por_fase.values() for regla in fase if regla.id in evaluados
    )
    return Evaluacion(
        resultados=ordenados,
        veredicto=veredicto,
        hash_reglas=spec.hash_reglas,
        fases_evaluadas=tuple(f for f in ORDEN_FASES if f in set(evaluadas)),
        fases_saltadas=tuple(f for f in ORDEN_FASES if f in set(saltadas)),
        calculo=calculo,
        interpretaciones_aplicadas=_interpretaciones(ordenados, actuacion, calculo, alias_consumidos),
        carencias=_carencias(ordenados, spec, documentos),
        avisos=list(dict.fromkeys(avisos)),
        bloqueo_por_conflicto=bloqueo_por_conflicto,
    )


__all__ = [
    "ALIAS_CONTEXTO",
    "ORDEN_FASES",
    "ORDEN_VEREDICTO",
    "VEREDICTO_BLOQUEADO",
    "VEREDICTO_NO_ELEGIBLE",
    "VEREDICTO_POR_SEVERIDAD",
    "VEREDICTO_PREVALIDADO",
    "VEREDICTO_SUBSANABLE",
    "ContextoEvaluacion",
    "ErrorReglas",
    "Evaluacion",
    "Resultado",
    "ResultadoRegla",
    "argumentos_unique",
    "construir_contexto",
    "evaluar_actuacion",
    "evaluar_regla",
    "veredicto_de",
]
