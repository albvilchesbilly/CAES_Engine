"""Spec Registry (N1): carga, valida y versiona las specs de ficha (`spec/*.yaml`).

No conoce ninguna ficha concreta (regla de oro 4): todo lo que decide sale de la propia spec. Un test lee
este fuente y comprueba que no contiene identificadores de ficha, de tabla ni de regla.

Que hace `cargar_spec` (docs/04 §2), en este orden:

1. Rechaza cualquier ruta bajo `propuestas/` (docs/04 §2.2; regla de oro 9) y exige que el nombre del
   fichero sea `<CODIGO>_v<version_ficha>.yaml` y coincida con `spec.id` y `spec.version_ficha`.
2. Valida bloques y campos: `spec.id`, `version_ficha` (cadena), `version_spec` (semver); bloques
   `variables`, `calculo`, `documentacion`, `reglas`, `estados`; cada regla con `id` unico,
   `descripcion`, `logica` y `severidad` del catalogo (docs/04 §4.1). Toda referencia `INT-xx` en
   cualquier punto de la spec debe existir en `interpretaciones[].id`.
3. Carga las tablas del bloque `tablas` con `engine.tablas.cargar_tablas` (garantia 4 de docs/04 §2.5);
   `ErrorTabla` se envuelve en `ErrorCargaSpec`.
4. Calcula los **enumerados** del parser: toda lista de cadenas bajo `ambito`, `variables.*.valores`, los
   tres tipos de evidencia (`demostrado`, `declarado`, `derivado`) y los literales simbolicos que aparecen
   dentro de `[...]` en alguna `logica` (se obtienen compilando primero sin enumerados, que es el modo en el
   que el parser toma como literal todo nombre dentro de una lista). Un enumerado que coincida con el nombre
   de una variable es error de carga: esa variable nunca podria resolverse.
5. Compila con esos enumerados cada `logica` (modo `logica`), `calculo.motor.formula` y
   `calculo.total.formula` (modo `formula`), `calculo.controles_fisicos[].regla` (modo `logica`),
   `calculo.precondiciones[]` (modo `logica`; la que no compila es una precondicion de procedimiento, se
   guarda como texto en `Spec.precondiciones_texto` y deja aviso) y `variables.*.derivacion.metodo` cuando
   la derivacion no declara `fuente` (una derivacion sin fuente es una expresion sobre otras variables; con
   fuente, `metodo` describe la extraccion y no se compila). `ErrorCargaExpresion` → `ErrorCargaSpec`.
6. Aplica los valores por defecto de la anatomia de regla (docs/04 §3.2) y deriva `fase` y `nivel` cuando
   la spec no los declara (ver abajo).
7. Comprueba la garantia "toda regla bloqueante que pueda quedar `NO_EVALUABLE` tiene una `SUBSANABLE`
   que recoge la carencia" (docs/04 §2.5.3; ver abajo).
8. Calcula `hash_reglas` (SHA-256 del bloque `reglas` tal y como esta en el YAML, canonizado como JSON
   con claves ordenadas, sin espacios, UTF-8) y `hash_spec` (SHA-256 de los bytes del fichero).

**Derivacion de `fase`** (docs/04 §5.2 y docs/03 §14.c; sin lista de ids en codigo). Si la regla declara
`fase`, se respeta. Si no, en este orden:

- severidad `BLOQUEANTE_AMBITO` → `ambito`;
- la logica referencia una salida del calculo (`calculo.motor.salida`, `calculo.total.salida`, con o sin el
  sufijo `_cae` del valor truncado) o un `calculo.controles_fisicos[].id` → `post_calculo`;
- severidad `BLOQUEANTE_DATOS`, o la logica referencia el id de una tabla del bloque `tablas` →
  `consistencia`;
- en otro caso → `resto`.

**Derivacion de `nivel`**: `unidad` si la logica usa `for each` o si alguno de sus identificadores es de
nivel unidad; `actuacion` en caso contrario. Un identificador es de nivel unidad segun su raiz: una
variable con `nivel` de unidad (`motor` en el vocabulario de la spec); la salida de `calculo.motor` (por
construccion es por unidad); un control fisico cuya `regla` referencia algo de nivel unidad; o un hecho
documental (`raiz.atributo` cuya raiz es prefijo de uno o varios tipos de `documentacion`) cuando todas
las variables que citan esos documentos en `fuentes` o `derivacion.fuente` son de nivel unidad.

**Garantia NO_EVALUABLE → SUBSANABLE** (comprobacion estatica al cargar). Para cada regla `BLOQUEANTE_*`
se toman sus `identificadores` (el parser ya excluye los literales) menos las `colecciones_ligadas`, y
cada uno se reduce a su **raiz**: se quitan los sufijos de consolidacion (`.valores_por_fuente`,
`.declarado`, `.derivado`, `.evidencia`, `.fuente`, `_por_fuente`) y, en un nombre con punto, la raiz es lo
anterior al punto. Una raiz esta **cubierta** si:

  (a) alguna regla `SUBSANABLE` referencia la misma raiz; o
  (b) es una variable de la spec y alguna de sus `fuentes` (o su `derivacion.fuente`) es un
      `documentacion[].tipo` con `obligatorio: true`, y existe una regla `SUBSANABLE` que usa la funcion
      `presente` (regla de presencia documental); o
  (c) es prefijo de un tipo de documento obligatorio (`tipo == raiz` o `tipo` empieza por `raiz + "_"`),
      con la misma condicion de regla de presencia; o
  (d) es una variable derivada de tabla (`derivacion.fuente` empieza por `tabla:`) cuya `clave`, si la
      declara, esta cubierta; o derivada por `metodo` (expresion) cuyos identificadores estan todos
      cubiertos (recursivo); o
  (e) es una salida del calculo o un control fisico, y los identificadores de su formula/regla estan todos
      cubiertos (recursivo); o
  (f) es una constante de la propia spec (`ambito.<lista>` y similares: la raiz es un bloque de la spec).

Una raiz mapeable a la spec y no cubierta en una regla bloqueante → `ErrorCargaSpec` con regla y raiz. Una
raiz que no se puede mapear a nada de la spec (un hecho que solo produce el consolidador) no es error: deja
un aviso en `Spec.avisos_carga` ("garantia no verificable estaticamente para <regla>: <raiz>").

**Versiones** (docs/04 §2.4): `SpecRegistry.obtener(codigo, version_ficha=None, fecha=None)`. Con una
version, la devuelve. Con varias y `version_ficha`, esa. Con varias y solo `fecha`, aplica el criterio que
las specs declaren en `spec.vigencia` (`desde`/`hasta`); si no todas lo declaran, devuelve la version mas
alta y deja el aviso "criterio de vigencia no decidido (docs/04 §2.4)". El criterio no se inventa aqui.

No importa nada de agentes/, salida/, generator/ ni tests/. Sin `eval`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from engine.calculo import ErrorCalculo, Plan, planificar
from engine.expresiones import ErrorCargaExpresion, Expresion, compilar
from engine.tablas import ErrorTabla, Tabla, cargar_tablas

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_SPEC = "spec"
CARPETA_PROPUESTAS = "propuestas"
EXTENSION_SPEC = ".yaml"
PATRON_NOMBRE_FICHERO = r"^(?P<codigo>[A-Za-z0-9]+)_v(?P<version>[0-9][0-9A-Za-z.]*)\.yaml$"
PATRON_SEMVER = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$"
PATRON_INTERPRETACION = r"^INT-\d{2,}$"
PATRON_FOR_EACH = r"\bfor\s+each\b"

SEVERIDADES = ("BLOQUEANTE_AMBITO", "BLOQUEANTE_DATOS", "SUBSANABLE", "AVISO")
SEVERIDAD_AMBITO = "BLOQUEANTE_AMBITO"
SEVERIDAD_DATOS = "BLOQUEANTE_DATOS"
SEVERIDAD_SUBSANABLE = "SUBSANABLE"
SEVERIDADES_BLOQUEANTES = frozenset({SEVERIDAD_AMBITO, SEVERIDAD_DATOS})
FASES = ("cabecera", "ambito", "consistencia", "post_calculo", "resto")
NIVELES_REGLA = ("unidad", "actuacion", "grupo", "expediente")
NIVEL_UNIDAD = "unidad"
NIVEL_ACTUACION = "actuacion"
# Vocabulario de `variables.*.nivel` en la spec: `motor` (por unidad) y `expediente` (por actuacion).
NIVELES_VARIABLE_UNIDAD = frozenset({"motor", NIVEL_UNIDAD})
NIVELES_VARIABLE_ACTUACION = frozenset({"expediente", NIVEL_ACTUACION})
TIPOS_EVIDENCIA = frozenset({"demostrado", "declarado", "derivado"})
OBLIGATORIO_CONDICIONAL = "condicional"
CALCULO_POR_UNIDAD = "motor"  # bloque `calculo.motor`: formula por unidad
CALCULO_TOTAL = "total"  # bloque `calculo.total`: agregado de la actuacion
SUFIJO_CAE = "_cae"  # valor truncado a kWh entero de una salida (INT-06)
SUFIJO_POR_FUENTE = "_por_fuente"
SUFIJOS_CONSOLIDACION = (".valores_por_fuente", ".declarado", ".derivado", ".evidencia", ".fuente")
PREFIJO_TABLA = "tabla:"
FUNCION_PRESENCIA = "presente"
BLOQUES_OBLIGATORIOS = ("spec", "variables", "calculo", "documentacion", "reglas", "estados")
CAMPOS_REGLA_OBLIGATORIOS = ("id", "descripcion", "logica", "severidad")
ORIGEN_SUBSANACION_DEFECTO = ("interno",)
AVISO_VIGENCIA_NO_DECIDIDA = "criterio de vigencia no decidido (docs/04 §2.4)"


class ErrorCargaSpec(Exception):
    """La spec no se activa: fichero, campos, expresiones, tablas o garantias invalidos."""


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Vigencia:
    """Intervalo cerrado de fechas; `None` en un extremo significa sin limite."""

    desde: date | None = None
    hasta: date | None = None

    def contiene(self, fecha: date) -> bool:
        if not isinstance(fecha, date) or isinstance(fecha, datetime):
            raise ErrorCargaSpec(f"vigencia.contiene() espera una fecha (date), no {type(fecha).__name__}")
        if self.desde is not None and fecha < self.desde:
            return False
        return not (self.hasta is not None and fecha > self.hasta)


@dataclass(frozen=True)
class Regla:
    """Una regla de la spec con los valores por defecto de docs/04 §3.2 ya aplicados."""

    id: str
    descripcion: str
    logica: str
    severidad: str
    referencia: str | None
    interpretacion: str | None
    fase: str
    nivel: str
    diferencial: bool
    equivalente_plataforma: str | None
    origen_subsanacion: tuple[str, ...]
    subsanacion: Mapping[str, object]  # {"mensaje": str, "documentos": list[str]}
    vigencia: Vigencia
    expresion: Expresion
    fase_declarada: bool = False  # True si `fase` venia en el YAML; False si se derivo
    nivel_declarado: bool = False

    @property
    def es_bloqueante(self) -> bool:
        return self.severidad in SEVERIDADES_BLOQUEANTES

    @property
    def raices(self) -> frozenset[str]:
        """Raices de los identificadores de la logica (sin colecciones ligadas)."""
        return frozenset(
            raiz_de(nombre) for nombre in self.expresion.identificadores - self.expresion.colecciones_ligadas
        )


@dataclass
class Spec:
    """Una spec de ficha cargada y validada. `datos` es el mapping crudo del YAML."""

    codigo: str
    version_ficha: str
    version_spec: str
    ruta: Path
    datos: Mapping[str, object]
    reglas: list[Regla]
    variables: Mapping[str, Mapping[str, object]]
    documentacion: list[Mapping[str, object]]
    calculo: Mapping[str, object]
    ambito: Mapping[str, object]
    estados: Mapping[str, object]
    interpretaciones: list[Mapping[str, object]]
    tablas: dict[str, Tabla]
    enumerados: frozenset[str]
    expresiones_calculo: dict[str, Expresion]
    precondiciones_texto: list[str]
    plan: Plan
    vigencia: Vigencia | None
    hash_reglas: str
    hash_spec: str
    avisos_carga: list[str] = field(default_factory=list)

    def regla(self, id: str) -> Regla:
        for regla in self.reglas:
            if regla.id == id:
                return regla
        raise KeyError(f"la spec {self.codigo} v{self.version_ficha} no tiene la regla {id!r}")

    def reglas_por_fase(self) -> dict[str, list[Regla]]:
        """Reglas agrupadas por fase en el orden de evaluacion (docs/04 §5.1); toda fase tiene clave."""
        por_fase: dict[str, list[Regla]] = {fase: [] for fase in FASES}
        for regla in self.reglas:
            por_fase[regla.fase].append(regla)
        return por_fase

    def variables_nivel(self, nivel: str) -> dict[str, Mapping[str, object]]:
        """Variables cuyo `nivel` es `nivel` o su equivalente.

        `unidad` equivale a `motor` y `actuacion` a `expediente` (vocabulario de la spec).
        """
        if nivel in NIVELES_VARIABLE_UNIDAD:
            equivalentes: frozenset[str] = NIVELES_VARIABLE_UNIDAD
        elif nivel in NIVELES_VARIABLE_ACTUACION:
            equivalentes = NIVELES_VARIABLE_ACTUACION
        else:
            equivalentes = frozenset({nivel})
        return {n: v for n, v in self.variables.items() if v.get("nivel") in equivalentes}

    def documentos_obligatorios(self) -> list[Mapping[str, object]]:
        """Entradas de `documentacion` con `obligatorio: true` (las `condicional` se resuelven al evaluar)."""
        return [d for d in self.documentacion if d.get("obligatorio") is True]

    def interpretacion(self, id: str) -> Mapping[str, object]:
        for interpretacion in self.interpretaciones:
            if interpretacion.get("id") == id:
                return interpretacion
        raise KeyError(f"la spec {self.codigo} v{self.version_ficha} no declara {id!r}")

    @property
    def ids_reglas(self) -> list[str]:
        return [r.id for r in self.reglas]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def raiz_de(nombre: str) -> str:
    """Raiz de un identificador: sin sufijos de consolidacion y, con punto, lo anterior al punto."""
    for sufijo in SUFIJOS_CONSOLIDACION:
        if nombre.endswith(sufijo):
            nombre = nombre[: -len(sufijo)]
            break
    raiz = nombre.split(".", 1)[0]
    if raiz.endswith(SUFIJO_POR_FUENTE):
        raiz = raiz[: -len(SUFIJO_POR_FUENTE)]
    return raiz


def clave_version(version: str) -> tuple[tuple[int, object], ...]:
    """Clave de orden de una version de ficha: numerica por segmentos, texto si no es numerico."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in str(version).split("."))


def _fecha(valor: object, contexto: str) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        raise ErrorCargaSpec(f"{contexto}: se esperaba una fecha (AAAA-MM-DD) sin hora, no {valor!r}")
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ErrorCargaSpec(f"{contexto}: fecha {valor!r} no es ISO (AAAA-MM-DD)") from exc
    raise ErrorCargaSpec(f"{contexto}: fecha con tipo inesperado {type(valor).__name__}")


def _vigencia(valor: object, contexto: str) -> Vigencia:
    if valor is None:
        return Vigencia()
    if not isinstance(valor, Mapping):
        raise ErrorCargaSpec(f"{contexto}: 'vigencia' debe ser un mapa con 'desde' y 'hasta'")
    desconocidas = set(valor) - {"desde", "hasta"}
    if desconocidas:
        raise ErrorCargaSpec(f"{contexto}: 'vigencia' con claves desconocidas {sorted(desconocidas)}")
    return Vigencia(
        desde=_fecha(valor.get("desde"), f"{contexto} vigencia.desde"),
        hasta=_fecha(valor.get("hasta"), f"{contexto} vigencia.hasta"),
    )


def _texto(valor: object, contexto: str, obligatorio: bool = True) -> str | None:
    if valor is None:
        if obligatorio:
            raise ErrorCargaSpec(f"{contexto}: falta")
        return None
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorCargaSpec(f"{contexto}: debe ser una cadena no vacia, no {valor!r}")
    return valor


def _lista_de_cadenas(valor: object, contexto: str) -> list[str]:
    if valor is None:
        return []
    if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
        raise ErrorCargaSpec(f"{contexto}: debe ser una lista de cadenas, no {valor!r}")
    return list(valor)


def _listas_de_cadenas(valor: object) -> Iterable[str]:
    """Cadenas de toda lista de cadenas contenida (recursivamente) en un bloque de la spec."""
    if isinstance(valor, list):
        if valor and all(isinstance(v, str) for v in valor):
            yield from valor
        else:
            for v in valor:
                yield from _listas_de_cadenas(v)
    elif isinstance(valor, Mapping):
        for v in valor.values():
            yield from _listas_de_cadenas(v)


def _referencias_interpretacion(valor: object, ruta: str) -> Iterable[tuple[str, str]]:
    """Pares (ruta, INT-xx) de toda cadena que sea exactamente una referencia a interpretacion."""
    if isinstance(valor, str):
        if re.match(PATRON_INTERPRETACION, valor):
            yield ruta, valor
    elif isinstance(valor, Mapping):
        for k, v in valor.items():
            yield from _referencias_interpretacion(v, f"{ruta}.{k}" if ruta else str(k))
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            yield from _referencias_interpretacion(v, f"{ruta}[{i}]")


def _compilar(texto: object, modo: str, enumerados: frozenset[str] | None, contexto: str) -> Expresion:
    if not isinstance(texto, str):
        raise ErrorCargaSpec(f"{contexto}: la expresion debe ser una cadena, no {texto!r}")
    try:
        return compilar(texto, modo=modo, enumerados=enumerados)
    except ErrorCargaExpresion as exc:
        raise ErrorCargaSpec(f"{contexto}: {exc}") from exc


def hash_canonico(bloque: object) -> str:
    """SHA-256 de un bloque YAML canonizado: JSON con claves ordenadas, sin espacios, UTF-8."""
    canonico = json.dumps(bloque, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validacion de bloques
# ---------------------------------------------------------------------------


def _validar_cabecera(datos: Mapping[str, object], ruta: Path) -> tuple[str, str, str, Vigencia | None]:
    cabecera = datos.get("spec")
    if not isinstance(cabecera, Mapping):
        raise ErrorCargaSpec(f"{ruta.name}: el bloque 'spec' debe ser un mapa")
    codigo = _texto(cabecera.get("id"), f"{ruta.name}: spec.id")
    version_ficha = cabecera.get("version_ficha")
    if not isinstance(version_ficha, str) or not version_ficha.strip():
        raise ErrorCargaSpec(
            f'{ruta.name}: spec.version_ficha debe ser una cadena entre comillas (p. ej. "1.1"), '
            f"no {version_ficha!r}"
        )
    version_spec = _texto(cabecera.get("version_spec"), f"{ruta.name}: spec.version_spec")
    if not re.match(PATRON_SEMVER, str(version_spec)):
        raise ErrorCargaSpec(f"{ruta.name}: spec.version_spec {version_spec!r} no es semver (X.Y.Z)")
    m = re.match(PATRON_NOMBRE_FICHERO, ruta.name)
    if m is None:
        raise ErrorCargaSpec(f"{ruta.name}: el nombre debe ser <CODIGO>_v<version_ficha>{EXTENSION_SPEC}")
    if m.group("codigo") != codigo or m.group("version") != version_ficha:
        raise ErrorCargaSpec(
            f"{ruta.name}: el nombre del fichero no coincide con spec.id={codigo!r} y "
            f"spec.version_ficha={version_ficha!r} (esperado {codigo}_v{version_ficha}{EXTENSION_SPEC})"
        )
    vigencia = _vigencia(cabecera["vigencia"], f"{ruta.name}: spec") if "vigencia" in cabecera else None
    return str(codigo), version_ficha, str(version_spec), vigencia


def _validar_interpretaciones(datos: Mapping[str, object], ruta: Path) -> list[Mapping[str, object]]:
    bloque = datos.get("interpretaciones") or []
    if not isinstance(bloque, list):
        raise ErrorCargaSpec(f"{ruta.name}: 'interpretaciones' debe ser una lista")
    ids: set[str] = set()
    for i, interpretacion in enumerate(bloque):
        ctx = f"{ruta.name}: interpretaciones[{i}]"
        if not isinstance(interpretacion, Mapping):
            raise ErrorCargaSpec(f"{ctx}: debe ser un mapa")
        id_int = str(_texto(interpretacion.get("id"), f"{ctx}.id"))
        if not re.match(PATRON_INTERPRETACION, id_int):
            raise ErrorCargaSpec(f"{ctx}: id {id_int!r} no tiene la forma INT-nn")
        if id_int in ids:
            raise ErrorCargaSpec(f"{ctx}: id {id_int!r} repetido")
        ids.add(id_int)
        for campo in ("tema", "criterio_poc", "impacto"):
            _texto(interpretacion.get(campo), f"{ctx} ({id_int}).{campo}")
    for ruta_ref, id_ref in _referencias_interpretacion(
        {k: v for k, v in datos.items() if k != "interpretaciones"}, ""
    ):
        if id_ref not in ids:
            raise ErrorCargaSpec(
                f"{ruta.name}: {ruta_ref} referencia {id_ref}, que no existe en interpretaciones[].id "
                "(regla de oro 7: toda interpretacion se declara con tema, criterio, alternativa e impacto)"
            )
    return list(bloque)


def _validar_variables(datos: Mapping[str, object], ruta: Path) -> dict[str, Mapping[str, object]]:
    bloque = datos.get("variables")
    if not isinstance(bloque, Mapping) or not bloque:
        raise ErrorCargaSpec(f"{ruta.name}: 'variables' debe ser un mapa no vacio {{nombre: {{...}}}}")
    variables: dict[str, Mapping[str, object]] = {}
    for nombre, variable in bloque.items():
        ctx = f"{ruta.name}: variables.{nombre}"
        if not isinstance(nombre, str) or not re.match(r"^[^\W\d]\w*$", nombre):
            raise ErrorCargaSpec(f"{ctx}: nombre de variable no valido (identificador sin puntos)")
        if not isinstance(variable, Mapping):
            raise ErrorCargaSpec(f"{ctx}: debe ser un mapa")
        _texto(variable.get("nivel"), f"{ctx}.nivel")
        evidencia = variable.get("evidencia")
        if evidencia not in TIPOS_EVIDENCIA:
            raise ErrorCargaSpec(f"{ctx}.evidencia: {evidencia!r} no esta en {sorted(TIPOS_EVIDENCIA)}")
        _lista_de_cadenas(variable.get("fuentes"), f"{ctx}.fuentes")
        _lista_de_cadenas(variable.get("valores"), f"{ctx}.valores")
        derivacion = variable.get("derivacion")
        if derivacion is not None and not isinstance(derivacion, Mapping):
            raise ErrorCargaSpec(f"{ctx}.derivacion: debe ser un mapa")
        if evidencia == "derivado" and derivacion is None:
            raise ErrorCargaSpec(f"{ctx}: una variable 'derivado' debe declarar 'derivacion'")
        if isinstance(derivacion, Mapping):
            fuente = derivacion.get("fuente")
            if fuente is not None and not isinstance(fuente, str):
                raise ErrorCargaSpec(f"{ctx}.derivacion.fuente: debe ser una cadena")
            if fuente is None and derivacion.get("metodo") is None:
                raise ErrorCargaSpec(f"{ctx}.derivacion: sin 'fuente' debe declarar 'metodo' (expresion)")
        variables[nombre] = variable
    return variables


def _validar_documentacion(datos: Mapping[str, object], ruta: Path) -> list[Mapping[str, object]]:
    bloque = datos.get("documentacion")
    if not isinstance(bloque, list) or not bloque:
        raise ErrorCargaSpec(f"{ruta.name}: 'documentacion' debe ser una lista no vacia")
    ids: set[str] = set()
    for i, doc in enumerate(bloque):
        ctx = f"{ruta.name}: documentacion[{i}]"
        if not isinstance(doc, Mapping):
            raise ErrorCargaSpec(f"{ctx}: debe ser un mapa")
        id_doc = str(_texto(doc.get("id"), f"{ctx}.id"))
        if id_doc in ids:
            raise ErrorCargaSpec(f"{ctx}: id {id_doc!r} repetido")
        ids.add(id_doc)
        _texto(doc.get("tipo"), f"{ctx} ({id_doc}).tipo")
        obligatorio = doc.get("obligatorio")
        if obligatorio not in (True, False, OBLIGATORIO_CONDICIONAL):
            raise ErrorCargaSpec(
                f"{ctx} ({id_doc}).obligatorio: debe ser true, false o {OBLIGATORIO_CONDICIONAL!r}"
            )
        if obligatorio == OBLIGATORIO_CONDICIONAL:
            _texto(doc.get("condicion"), f"{ctx} ({id_doc}).condicion")
    return list(bloque)


def _validar_calculo(datos: Mapping[str, object], ruta: Path) -> Mapping[str, object]:
    calculo = datos.get("calculo")
    if not isinstance(calculo, Mapping):
        raise ErrorCargaSpec(f"{ruta.name}: 'calculo' debe ser un mapa")
    for bloque in (CALCULO_POR_UNIDAD, CALCULO_TOTAL):
        sub = calculo.get(bloque)
        if sub is None:
            continue
        if not isinstance(sub, Mapping):
            raise ErrorCargaSpec(f"{ruta.name}: calculo.{bloque} debe ser un mapa")
        _texto(sub.get("salida"), f"{ruta.name}: calculo.{bloque}.salida")
        _texto(sub.get("formula"), f"{ruta.name}: calculo.{bloque}.formula")
    if not any(bloque in calculo for bloque in (CALCULO_POR_UNIDAD, CALCULO_TOTAL)):
        raise ErrorCargaSpec(f"{ruta.name}: calculo debe declarar '{CALCULO_POR_UNIDAD}' o '{CALCULO_TOTAL}'")
    precondiciones = calculo.get("precondiciones") or []
    if not isinstance(precondiciones, list) or not all(isinstance(p, str) for p in precondiciones):
        raise ErrorCargaSpec(f"{ruta.name}: calculo.precondiciones debe ser una lista de cadenas")
    controles = calculo.get("controles_fisicos") or []
    if not isinstance(controles, list):
        raise ErrorCargaSpec(f"{ruta.name}: calculo.controles_fisicos debe ser una lista")
    ids: set[str] = set()
    for i, control in enumerate(controles):
        ctx = f"{ruta.name}: calculo.controles_fisicos[{i}]"
        if not isinstance(control, Mapping):
            raise ErrorCargaSpec(f"{ctx}: debe ser un mapa")
        id_control = str(_texto(control.get("id"), f"{ctx}.id"))
        if id_control in ids:
            raise ErrorCargaSpec(f"{ctx}: id {id_control!r} repetido")
        ids.add(id_control)
        _texto(control.get("regla"), f"{ctx} ({id_control}).regla")
    return calculo


def _validar_estados(datos: Mapping[str, object], ruta: Path) -> Mapping[str, object]:
    estados = datos.get("estados")
    if not isinstance(estados, Mapping):
        raise ErrorCargaSpec(f"{ruta.name}: 'estados' debe ser un mapa")
    orden = _lista_de_cadenas(estados.get("orden_evaluacion"), f"{ruta.name}: estados.orden_evaluacion")
    if not orden:
        raise ErrorCargaSpec(f"{ruta.name}: estados.orden_evaluacion debe listar los veredictos")
    for veredicto in orden:
        if not isinstance(estados.get(veredicto), Mapping):
            raise ErrorCargaSpec(f"{ruta.name}: estados.{veredicto} (de orden_evaluacion) no esta definido")
    return estados


def _validar_reglas_crudas(datos: Mapping[str, object], ruta: Path) -> list[Mapping[str, object]]:
    bloque = datos.get("reglas")
    if not isinstance(bloque, list) or not bloque:
        raise ErrorCargaSpec(f"{ruta.name}: 'reglas' debe ser una lista no vacia")
    ids: set[str] = set()
    for i, regla in enumerate(bloque):
        ctx = f"{ruta.name}: reglas[{i}]"
        if not isinstance(regla, Mapping):
            raise ErrorCargaSpec(f"{ctx}: debe ser un mapa")
        for campo in CAMPOS_REGLA_OBLIGATORIOS:
            _texto(regla.get(campo), f"{ctx} ({regla.get('id', '?')}).{campo}")
        id_regla = str(regla["id"])
        if id_regla in ids:
            raise ErrorCargaSpec(f"{ctx}: id {id_regla!r} repetido")
        ids.add(id_regla)
        if regla["severidad"] not in SEVERIDADES:
            raise ErrorCargaSpec(
                f"{ctx} ({id_regla}).severidad: {regla['severidad']!r} no esta en el catalogo {SEVERIDADES}"
            )
    return list(bloque)


# ---------------------------------------------------------------------------
# Analisis estatico sobre la spec: enumerados, fase, nivel y garantia
# ---------------------------------------------------------------------------


@dataclass
class _Analizador:
    """Indice estatico de una spec para derivar fase y nivel y comprobar la garantia (sin ids en codigo)."""

    variables: Mapping[str, Mapping[str, object]]
    documentacion: list[Mapping[str, object]]
    calculo: Mapping[str, object]
    tablas: frozenset[str]
    constantes: frozenset[str]  # bloques de la spec referenciables como `bloque.lista`
    expresiones_calculo: dict[str, Expresion]
    expresiones_metodo: dict[str, Expresion]  # variable → derivacion.metodo compilado

    def __post_init__(self) -> None:
        self.tipos_documento = frozenset(str(d["tipo"]) for d in self.documentacion)
        self.tipos_obligatorios = frozenset(
            str(d["tipo"]) for d in self.documentacion if d.get("obligatorio") is True
        )
        self.salidas: dict[str, tuple[str, Expresion]] = {}  # salida (con y sin _cae) → (bloque, formula)
        for bloque in (CALCULO_POR_UNIDAD, CALCULO_TOTAL):
            sub = self.calculo.get(bloque)
            if isinstance(sub, Mapping):
                expresion = self.expresiones_calculo[f"calculo.{bloque}.formula"]
                self.salidas[str(sub["salida"])] = (bloque, expresion)
                self.salidas[str(sub["salida"]) + SUFIJO_CAE] = (bloque, expresion)
        self.controles: dict[str, Expresion] = {
            str(c["id"]): self.expresiones_calculo[f"calculo.controles_fisicos.{c['id']}"]
            for c in self.calculo.get("controles_fisicos") or []
        }
        self.raices_subsanables: set[str] = set()
        self.hay_regla_presencia = False

    # --- lo que una regla referencia --------------------------------------------------------------
    @staticmethod
    def _raices(expresion: Expresion) -> set[str]:
        return {raiz_de(n) for n in expresion.identificadores - expresion.colecciones_ligadas}

    def registrar_subsanables(self, reglas: Iterable[tuple[str, Expresion]]) -> None:
        for severidad, expresion in reglas:
            if severidad == SEVERIDAD_SUBSANABLE:
                self.raices_subsanables |= self._raices(expresion)
                if FUNCION_PRESENCIA in expresion.funciones:
                    self.hay_regla_presencia = True

    # --- fase -------------------------------------------------------------------------------------
    def fase_por_defecto(self, severidad: str, expresion: Expresion) -> str:
        if severidad == SEVERIDAD_AMBITO:
            return "ambito"
        raices = self._raices(expresion)
        if raices & (set(self.salidas) | set(self.controles)):
            return "post_calculo"
        if severidad == SEVERIDAD_DATOS or raices & self.tablas:
            return "consistencia"
        return "resto"

    # --- nivel ------------------------------------------------------------------------------------
    def nivel_por_defecto(self, expresion: Expresion) -> str:
        if re.search(PATRON_FOR_EACH, expresion.texto):
            return NIVEL_UNIDAD
        if any(self._es_unidad(raiz, frozenset()) for raiz in self._raices(expresion)):
            return NIVEL_UNIDAD
        return NIVEL_ACTUACION

    def _tipos_con_prefijo(self, raiz: str, tipos: Iterable[str]) -> list[str]:
        return [t for t in tipos if t == raiz or t.startswith(raiz + "_")]

    def _fuentes_de(self, variable: Mapping[str, object]) -> list[str]:
        fuentes = [str(f) for f in (variable.get("fuentes") or [])]
        derivacion = variable.get("derivacion")
        if isinstance(derivacion, Mapping):
            fuente = derivacion.get("fuente")
            if isinstance(fuente, str) and not fuente.startswith(PREFIJO_TABLA):
                fuentes.append(fuente)
        return fuentes

    def _es_unidad(self, raiz: str, visitados: frozenset[str]) -> bool:
        if raiz in visitados:
            return False
        visitados = visitados | {raiz}
        if raiz in self.variables:
            return self.variables[raiz].get("nivel") in NIVELES_VARIABLE_UNIDAD
        if raiz in self.salidas:
            return self.salidas[raiz][0] == CALCULO_POR_UNIDAD
        if raiz in self.controles:
            return any(self._es_unidad(r, visitados) for r in self._raices(self.controles[raiz]))
        tipos = self._tipos_con_prefijo(raiz, self.tipos_documento)
        if tipos:
            citan = [v for v in self.variables.values() if set(self._fuentes_de(v)) & set(tipos)]
            return bool(citan) and all(v.get("nivel") in NIVELES_VARIABLE_UNIDAD for v in citan)
        return False

    # --- garantia NO_EVALUABLE → SUBSANABLE -------------------------------------------------------
    def cubierta(self, raiz: str, visitados: frozenset[str] = frozenset()) -> bool | None:
        """True cubierta · False mapeable y no cubierta · None no mapeable a la spec."""
        if raiz in visitados:
            return True  # ciclo de derivacion: no reabrir
        visitados = visitados | {raiz}
        if raiz in self.raices_subsanables:  # (a)
            return True
        if raiz in self.variables:
            variable = self.variables[raiz]
            if self.hay_regla_presencia and set(self._fuentes_de(variable)) & self.tipos_obligatorios:
                return True  # (b)
            derivacion = variable.get("derivacion")
            if isinstance(derivacion, Mapping):  # (d)
                fuente = derivacion.get("fuente")
                if isinstance(fuente, str) and fuente.startswith(PREFIJO_TABLA):
                    clave = derivacion.get("clave")
                    return True if clave is None else self.cubierta(raiz_de(str(clave)), visitados)
                if raiz in self.expresiones_metodo:
                    return self._todas(self._raices(self.expresiones_metodo[raiz]), visitados)
            return False
        if self.hay_regla_presencia and self._tipos_con_prefijo(raiz, self.tipos_obligatorios):
            return True  # (c)
        if raiz in self.salidas:  # (e)
            return self._todas(self._raices(self.salidas[raiz][1]), visitados)
        if raiz in self.controles:  # (e)
            return self._todas(self._raices(self.controles[raiz]), visitados)
        if raiz in self.constantes:  # (f)
            return True
        return None

    def _todas(self, raices: Iterable[str], visitados: frozenset[str]) -> bool | None:
        resultados = [self.cubierta(r, visitados) for r in raices]
        if any(r is False for r in resultados):
            return False
        if all(r is True for r in resultados):
            return True
        return None


def _enumerados_de(
    datos: Mapping[str, object],
    variables: Mapping[str, Mapping[str, object]],
    reglas: list[Mapping[str, object]],
    ruta: Path,
) -> frozenset[str]:
    conjunto: set[str] = set(TIPOS_EVIDENCIA)
    conjunto |= set(_listas_de_cadenas(datos.get("ambito") or {}))
    for variable in variables.values():
        conjunto |= set(_lista_de_cadenas(variable.get("valores"), "variables.valores"))
    for regla in reglas:
        # sin `enumerados`, el parser toma como literal simbolico todo nombre dentro de `[...]`
        expresion = _compilar(regla["logica"], "logica", None, f"{ruta.name}: regla {regla['id']}")
        conjunto |= set(expresion.literales_simbolicos)
    choque = conjunto & set(variables)
    if choque:
        raise ErrorCargaSpec(
            f"{ruta.name}: los enumerados {sorted(choque)} coinciden con nombres de variables; "
            "esas variables nunca podrian resolverse en una logica"
        )
    return frozenset(conjunto)


def _compilar_calculo(
    calculo: Mapping[str, object],
    variables: Mapping[str, Mapping[str, object]],
    enumerados: frozenset[str],
    ruta: Path,
) -> tuple[dict[str, Expresion], dict[str, Expresion], list[str], list[str]]:
    """Expresiones del calculo y de las derivaciones.

    Devuelve (expresiones, metodos, precondiciones_texto, avisos).
    """
    expresiones: dict[str, Expresion] = {}
    avisos: list[str] = []
    for bloque in (CALCULO_POR_UNIDAD, CALCULO_TOTAL):
        sub = calculo.get(bloque)
        if isinstance(sub, Mapping):
            clave = f"calculo.{bloque}.formula"
            expresiones[clave] = _compilar(sub["formula"], "formula", enumerados, f"{ruta.name}: {clave}")
    for control in calculo.get("controles_fisicos") or []:
        clave = f"calculo.controles_fisicos.{control['id']}"
        expresiones[clave] = _compilar(control["regla"], "logica", enumerados, f"{ruta.name}: {clave}")
    precondiciones_texto: list[str] = []
    for i, precondicion in enumerate(calculo.get("precondiciones") or []):
        clave = f"calculo.precondiciones[{i}]"
        try:
            expresiones[clave] = compilar(precondicion, modo="logica", enumerados=enumerados)
        except ErrorCargaExpresion:
            precondiciones_texto.append(precondicion)
            avisos.append(
                f"{clave} no es una expresion del vocabulario y se conserva como precondicion de "
                f"procedimiento (texto): {precondicion!r}"
            )
    metodos: dict[str, Expresion] = {}
    for nombre, variable in variables.items():
        derivacion = variable.get("derivacion")
        if isinstance(derivacion, Mapping) and derivacion.get("fuente") is None:
            clave = f"variables.{nombre}.derivacion.metodo"
            metodos[nombre] = _compilar(derivacion["metodo"], "formula", enumerados, f"{ruta.name}: {clave}")
            expresiones[clave] = metodos[nombre]
    return expresiones, metodos, precondiciones_texto, avisos


def _construir_reglas(
    crudas: list[Mapping[str, object]],
    enumerados: frozenset[str],
    analizador: _Analizador,
    ruta: Path,
) -> list[Regla]:
    compiladas = [
        (r, _compilar(r["logica"], "logica", enumerados, f"{ruta.name}: regla {r['id']}")) for r in crudas
    ]
    analizador.registrar_subsanables((str(r["severidad"]), e) for r, e in compiladas)
    reglas: list[Regla] = []
    for cruda, expresion in compiladas:
        id_regla = str(cruda["id"])
        ctx = f"{ruta.name}: regla {id_regla}"
        severidad = str(cruda["severidad"])
        fase_declarada = cruda.get("fase") is not None
        fase = str(cruda["fase"]) if fase_declarada else analizador.fase_por_defecto(severidad, expresion)
        if fase not in FASES:
            raise ErrorCargaSpec(f"{ctx}.fase: {fase!r} no esta en {FASES}")
        nivel_declarado = cruda.get("nivel") is not None
        nivel = str(cruda["nivel"]) if nivel_declarado else analizador.nivel_por_defecto(expresion)
        if nivel not in NIVELES_REGLA:
            raise ErrorCargaSpec(f"{ctx}.nivel: {nivel!r} no esta en {NIVELES_REGLA}")
        diferencial = cruda.get("diferencial", True)
        if not isinstance(diferencial, bool):
            raise ErrorCargaSpec(f"{ctx}.diferencial: debe ser true o false")
        origen = cruda.get("origen_subsanacion")
        origen_subsanacion = (
            ORIGEN_SUBSANACION_DEFECTO
            if origen is None
            else tuple(_lista_de_cadenas(origen, f"{ctx}.origen_subsanacion"))
        )
        subsanacion_cruda = cruda.get("subsanacion") or {}
        if not isinstance(subsanacion_cruda, Mapping):
            raise ErrorCargaSpec(f"{ctx}.subsanacion: debe ser un mapa con 'mensaje' y 'documentos'")
        subsanacion = {
            "mensaje": _texto(subsanacion_cruda.get("mensaje"), f"{ctx}.subsanacion.mensaje", False)
            or str(cruda["descripcion"]),
            "documentos": _lista_de_cadenas(
                subsanacion_cruda.get("documentos"), f"{ctx}.subsanacion.documentos"
            ),
        }
        reglas.append(
            Regla(
                id=id_regla,
                descripcion=str(cruda["descripcion"]),
                logica=str(cruda["logica"]),
                severidad=severidad,
                referencia=_texto(cruda.get("referencia"), f"{ctx}.referencia", False),
                interpretacion=_texto(cruda.get("interpretacion"), f"{ctx}.interpretacion", False),
                fase=fase,
                nivel=nivel,
                diferencial=diferencial,
                equivalente_plataforma=_texto(
                    cruda.get("equivalente_plataforma"), f"{ctx}.equivalente_plataforma", False
                ),
                origen_subsanacion=origen_subsanacion,
                subsanacion=subsanacion,
                vigencia=_vigencia(cruda.get("vigencia"), ctx),
                expresion=expresion,
                fase_declarada=fase_declarada,
                nivel_declarado=nivel_declarado,
            )
        )
    return reglas


def _comprobar_garantia(reglas: list[Regla], analizador: _Analizador, ruta: Path) -> list[str]:
    """Garantia 3 de docs/04 §2.5. Devuelve los avisos (raices no mapeables); lanza si hay descubiertas."""
    avisos: list[str] = []
    descubiertas: list[str] = []
    for regla in reglas:
        if not regla.es_bloqueante:
            continue
        for raiz in sorted(regla.raices):
            resultado = analizador.cubierta(raiz)
            if resultado is None:
                avisos.append(f"garantia no verificable estaticamente para {regla.id}: {raiz}")
            elif resultado is False:
                descubiertas.append(f"{regla.id}: {raiz}")
    if descubiertas:
        raise ErrorCargaSpec(
            f"{ruta.name}: reglas bloqueantes que pueden quedar NO_EVALUABLE sin una regla SUBSANABLE que "
            f"recoja la carencia (docs/04 §2.5.3): {', '.join(descubiertas)}"
        )
    return avisos


# ---------------------------------------------------------------------------
# Carga de una spec
# ---------------------------------------------------------------------------


def cargar_spec(ruta: Path, raiz_datos: Path = RAIZ) -> Spec:
    """Carga y valida una spec activa. Ver el docstring del modulo para el orden y las garantias."""
    ruta = Path(ruta)
    if CARPETA_PROPUESTAS in ruta.resolve().parts:
        raise ErrorCargaSpec(
            f"{ruta}: las specs de '{CARPETA_PROPUESTAS}/' no se cargan; se activan moviendolas a "
            f"'{CARPETA_SPEC}/' tras la revision de Billy (docs/04 §2.2, regla de oro 9)"
        )
    if not ruta.is_file():
        raise ErrorCargaSpec(f"No existe la spec: {ruta}")
    contenido = ruta.read_bytes()
    hash_spec = hashlib.sha256(contenido).hexdigest()
    try:
        datos = yaml.safe_load(contenido.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ErrorCargaSpec(f"{ruta.name}: YAML ilegible ({exc})") from exc
    if not isinstance(datos, Mapping):
        raise ErrorCargaSpec(f"{ruta.name}: la spec no es un mapa YAML")
    faltan = [b for b in BLOQUES_OBLIGATORIOS if b not in datos]
    if faltan:
        raise ErrorCargaSpec(f"{ruta.name}: faltan los bloques obligatorios {faltan}")

    codigo, version_ficha, version_spec, vigencia = _validar_cabecera(datos, ruta)
    interpretaciones = _validar_interpretaciones(datos, ruta)
    variables = _validar_variables(datos, ruta)
    documentacion = _validar_documentacion(datos, ruta)
    calculo = _validar_calculo(datos, ruta)
    estados = _validar_estados(datos, ruta)
    crudas = _validar_reglas_crudas(datos, ruta)
    ambito = datos.get("ambito") or {}
    if not isinstance(ambito, Mapping):
        raise ErrorCargaSpec(f"{ruta.name}: 'ambito' debe ser un mapa")

    avisos: list[str] = []
    try:
        tablas = cargar_tablas(dict(datos.get("tablas") or {}), raiz_datos)
    except ErrorTabla as exc:
        raise ErrorCargaSpec(f"{ruta.name}: {exc}") from exc
    for tabla in tablas.values():
        avisos.extend(f"tabla {tabla.id}: {a}" for a in tabla.avisos_carga)

    enumerados = _enumerados_de(datos, variables, crudas, ruta)
    expresiones_calculo, metodos, precondiciones_texto, avisos_calculo = _compilar_calculo(
        calculo, variables, enumerados, ruta
    )
    avisos.extend(avisos_calculo)
    analizador = _Analizador(
        variables=variables,
        documentacion=documentacion,
        calculo=calculo,
        tablas=frozenset(tablas),
        constantes=frozenset(k for k, v in datos.items() if isinstance(v, Mapping) and k != "variables"),
        expresiones_calculo=expresiones_calculo,
        expresiones_metodo=metodos,
    )
    reglas = _construir_reglas(crudas, enumerados, analizador, ruta)
    avisos.extend(_comprobar_garantia(reglas, analizador, ruta))

    # Criterio unico de validacion del bloque `calculo` (ADR-002 §3, fila QA-2): la spec que el registro
    # activa es, por construccion, calculable. `planificar` valida derivaciones, formulas, controles,
    # precondiciones y redondeo; lo que rechaza no se activa.
    try:
        plan = planificar(datos, tablas)
    except ErrorCalculo as exc:
        raise ErrorCargaSpec(f"{ruta.name}: {exc}") from exc
    precondiciones_texto = list(plan.precondiciones_delegadas)
    avisos.extend(f"calculo: {nota}" for nota in plan.notas)

    return Spec(
        codigo=codigo,
        version_ficha=version_ficha,
        version_spec=version_spec,
        ruta=ruta,
        datos=datos,
        reglas=reglas,
        variables=variables,
        documentacion=documentacion,
        calculo=calculo,
        ambito=ambito,
        estados=estados,
        interpretaciones=interpretaciones,
        tablas=tablas,
        enumerados=enumerados,
        expresiones_calculo=expresiones_calculo,
        precondiciones_texto=precondiciones_texto,
        plan=plan,
        vigencia=vigencia,
        hash_reglas=hash_canonico(datos["reglas"]),
        hash_spec=hash_spec,
        avisos_carga=avisos,
    )


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------


class SpecRegistry:
    """Specs activas de `carpeta_spec/*.yaml` (solo ficheros del primer nivel), varias versiones por ficha."""

    def __init__(self, carpeta_spec: Path = RAIZ / CARPETA_SPEC, raiz_datos: Path = RAIZ) -> None:
        self.carpeta_spec = Path(carpeta_spec)
        self.raiz_datos = Path(raiz_datos)
        self._specs: dict[str, dict[str, Spec]] = {}
        self.avisos: list[str] = []

    def cargar_todas(self) -> list[Spec]:
        """Carga cada `*.yaml` de la carpeta; ignora subcarpetas (`propuestas/` incluida).

        Falla al primer error: ninguna spec invalida se registra.
        """
        if not self.carpeta_spec.is_dir():
            raise ErrorCargaSpec(f"No existe la carpeta de specs: {self.carpeta_spec}")
        cargadas: list[Spec] = []
        for ruta in sorted(self.carpeta_spec.glob(f"*{EXTENSION_SPEC}")):
            if not ruta.is_file():
                continue
            cargadas.append(self.registrar(cargar_spec(ruta, self.raiz_datos)))
        return cargadas

    def registrar(self, spec: Spec) -> Spec:
        versiones = self._specs.setdefault(spec.codigo, {})
        if spec.version_ficha in versiones:
            raise ErrorCargaSpec(f"la ficha {spec.codigo} v{spec.version_ficha} ya esta registrada")
        versiones[spec.version_ficha] = spec
        return spec

    def codigos(self) -> list[str]:
        return sorted(self._specs)

    def versiones(self, codigo: str) -> list[str]:
        """Versiones de ficha cargadas para `codigo`, de menor a mayor."""
        return sorted(self._specs.get(codigo, {}), key=clave_version)

    def _avisar(self, aviso: str) -> None:
        if aviso not in self.avisos:
            self.avisos.append(aviso)

    def obtener(self, codigo: str, version_ficha: str | None = None, fecha: date | None = None) -> Spec:
        versiones = self._specs.get(codigo)
        if not versiones:
            raise ErrorCargaSpec(f"ficha {codigo!r} no cargada; cargadas: {self.codigos()}")
        if version_ficha is not None:
            if version_ficha not in versiones:
                raise ErrorCargaSpec(
                    f"ficha {codigo} sin version {version_ficha!r}; cargadas: {self.versiones(codigo)}"
                )
            return versiones[version_ficha]
        ordenadas = [versiones[v] for v in self.versiones(codigo)]
        if len(ordenadas) == 1:
            return ordenadas[0]
        if fecha is not None and all(s.vigencia is not None for s in ordenadas):
            vigentes = [s for s in ordenadas if s.vigencia is not None and s.vigencia.contiene(fecha)]
            if not vigentes:
                raise ErrorCargaSpec(
                    f"ficha {codigo}: ninguna version vigente en {fecha.isoformat()} "
                    f"(cargadas: {self.versiones(codigo)})"
                )
            if len(vigentes) > 1:
                self._avisar(
                    f"ficha {codigo}: varias versiones vigentes en {fecha.isoformat()} "
                    f"({[s.version_ficha for s in vigentes]}); se usa la mas alta"
                )
            return vigentes[-1]
        self._avisar(
            f"ficha {codigo}: {AVISO_VIGENCIA_NO_DECIDIDA}; con varias versiones cargadas "
            f"{self.versiones(codigo)} se devuelve la mas alta ({ordenadas[-1].version_ficha})"
        )
        return ordenadas[-1]


__all__ = [
    "AVISO_VIGENCIA_NO_DECIDIDA",
    "FASES",
    "NIVELES_REGLA",
    "SEVERIDADES",
    "SEVERIDADES_BLOQUEANTES",
    "TIPOS_EVIDENCIA",
    "ErrorCargaSpec",
    "Regla",
    "Spec",
    "SpecRegistry",
    "Vigencia",
    "cargar_spec",
    "clave_version",
    "hash_canonico",
    "raiz_de",
]
