"""Tablas de referencia de `data/` (N3): carga con vigencia, busqueda por clave e interpolacion (INT-02).

Toda tabla es dato normativo transcrito (data/README.md). Este modulo no conoce ninguna tabla concreta
(regla de oro 4: la ficha es configuracion): el esquema lo declara el `.meta.yaml` de cada tabla.

- lee `data/<fichero>.csv` y su `data/<fichero>.meta.yaml` (id, fuente, vigencia, columnas, clave, valor,
  restricciones); `columnas` del meta debe coincidir con la cabecera del CSV (mismo conjunto y orden);
- cada fila es un mapa columna -> valor: `Decimal` construido desde la cadena del CSV (nunca `float`),
  `None` si la celda esta vacia, y `bool` para la columna obligatoria `verificado` ({si, pendiente});
- sanidad en carga: toda celda numerica finita y sin notacion exponencial; `clave` y `valor` presentes en
  toda fila; `clave` estrictamente creciente en el orden del CSV; columnas de `restricciones.positivo` > 0;
  si `valor` no es no-decreciente con `clave`, aviso en `Tabla.avisos_carga` (no error);
- busca por clave exacta y, si no hay fila, interpola linealmente la columna `valor` entre las dos filas
  adyacentes (criterio INT-02 de la spec) devolviendo la marca `INT-02` y un aviso; fuera de rango no
  extrapola; propaga en el aviso si alguna fila usada esta `verificado: pendiente` (solo Billy marca `si`).

No importa nada de agentes/, salida/, generator/ ni tests/.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

RAIZ_REPO = Path(__file__).resolve().parents[1]
CARPETA_DATA = "data"
SUFIJO_META = ".meta.yaml"
COLUMNA_VERIFICADO = "verificado"
VALORES_VERIFICADO = {"si": True, "pendiente": False}
CAMPOS_META_OBLIGATORIOS = ("id", "columnas", "clave", "valor", "vigencia")
RESTRICCIONES_CONOCIDAS = ("positivo",)
# Formato de celda numerica de data/README.md: punto decimal, sin separador de miles, sin exponente.
PATRON_CELDA_NUMERICA = re.compile(r"^-?\d+(\.\d+)?$")

ValorCelda = Decimal | bool | None


class ErrorTabla(Exception):
    """Error de carga o de coherencia de una tabla de referencia. Es error de carga, no de evaluacion."""


@dataclass(frozen=True)
class FilaTabla:
    """Una fila de una tabla: mapa columna -> valor tipado segun `meta.columnas`.

    `columna_clave` es el nombre de la columna de busqueda declarada en el meta; `clave` devuelve su valor.
    `verificado` es True solo si la fila lleva `si` en el CSV.
    """

    valores: Mapping[str, ValorCelda]
    columna_clave: str

    def __getitem__(self, columna: str) -> ValorCelda:
        return self.valores[columna]

    def __contains__(self, columna: object) -> bool:
        return columna in self.valores

    def __iter__(self) -> Iterator[str]:
        return iter(self.valores)

    def get(self, columna: str, defecto: ValorCelda = None) -> ValorCelda:
        return self.valores.get(columna, defecto)

    @property
    def clave(self) -> Decimal:
        valor = self.valores[self.columna_clave]
        if not isinstance(valor, Decimal):
            raise ErrorTabla(f"La clave '{self.columna_clave}' no es Decimal en una fila: {valor!r}")
        return valor

    @property
    def verificado(self) -> bool:
        return self.valores[COLUMNA_VERIFICADO] is True

    def como_dict(self) -> dict[str, ValorCelda]:
        return dict(self.valores)


@dataclass
class ResultadoBusqueda:
    """Resultado de `Tabla.buscar`. `valor` es la columna `valor` exacta o interpolada; None si no procede."""

    fila: FilaTabla | None
    valor: Decimal | None
    exacta: bool
    interpretacion: str | None
    filas_adyacentes: tuple[FilaTabla, FilaTabla] | None
    aviso: str | None


@dataclass
class Tabla:
    """Tabla de referencia cargada: filas ordenadas por `clave`, vigencia y metadatos de transcripcion."""

    id: str
    fichero: Path
    columnas: list[str]
    clave: str
    valor: str
    vigencia_desde: date | None
    vigencia_hasta: date | None
    filas: list[FilaTabla] = field(default_factory=list)
    fuente: str | None = None
    metodo_transcripcion: str | None = None
    restricciones: dict[str, list[str]] = field(default_factory=dict)
    avisos_carga: list[str] = field(default_factory=list)

    @property
    def todas_verificadas(self) -> bool:
        return all(f.verificado for f in self.filas)

    @property
    def clave_minima(self) -> Decimal:
        return self.filas[0].clave

    @property
    def clave_maxima(self) -> Decimal:
        return self.filas[-1].clave

    def _valor_de(self, fila: FilaTabla) -> Decimal:
        valor = fila[self.valor]
        if not isinstance(valor, Decimal):
            raise ErrorTabla(f"Tabla {self.id}: la columna de valor '{self.valor}' no es Decimal en una fila")
        return valor

    def vigente(self, fecha: date) -> bool:
        if not isinstance(fecha, date) or isinstance(fecha, datetime):
            raise ErrorTabla(f"Tabla {self.id}: vigente() espera una fecha (date), no {type(fecha).__name__}")
        if self.vigencia_desde is not None and fecha < self.vigencia_desde:
            return False
        if self.vigencia_hasta is not None and fecha > self.vigencia_hasta:
            return False
        return True

    def buscar_exacta(self, valor: Decimal) -> FilaTabla | None:
        valor = _clave_buscada(valor, f"Tabla {self.id}: valor buscado")
        for fila in self.filas:
            if fila.clave == valor:
                return fila
        return None

    def buscar(self, valor: Decimal) -> ResultadoBusqueda:
        """Fila exacta si existe; si no, interpolacion lineal de `valor` (INT-02); fuera de rango, None."""
        valor = _clave_buscada(valor, f"Tabla {self.id}: valor buscado")
        if not self.filas:
            raise ErrorTabla(f"Tabla {self.id} sin filas")
        avisos: list[str] = []

        fila = self.buscar_exacta(valor)
        if fila is not None:
            self._aviso_pendiente(avisos, [fila])
            return ResultadoBusqueda(
                fila=fila,
                valor=self._valor_de(fila),
                exacta=True,
                interpretacion=None,
                filas_adyacentes=None,
                aviso=_unir(avisos),
            )

        minima, maxima = self.clave_minima, self.clave_maxima
        if valor < minima or valor > maxima:
            avisos.append(
                f"{self.clave} = {valor} fuera del rango de la tabla {self.id} "
                f"[{minima}, {maxima}]; no se extrapola; revision humana"
            )
            return ResultadoBusqueda(
                fila=None,
                valor=None,
                exacta=False,
                interpretacion=None,
                filas_adyacentes=None,
                aviso=_unir(avisos),
            )

        inferior, superior = self._adyacentes(valor)
        k0, k1 = inferior.clave, superior.clave
        p0, p1 = self._valor_de(inferior), self._valor_de(superior)
        interpolado = p0 + (p1 - p0) * (valor - k0) / (k1 - k0)
        avisos.append(
            f"INT-02: sin fila exacta en {self.id} para {self.clave} = {valor}; "
            f"{self.valor} interpolado linealmente entre {self.clave} = {k0} ({p0}) y {k1} ({p1}); "
            "revision humana"
        )
        self._aviso_pendiente(avisos, [inferior, superior])
        return ResultadoBusqueda(
            fila=None,
            valor=interpolado,
            exacta=False,
            interpretacion="INT-02",
            filas_adyacentes=(inferior, superior),
            aviso=_unir(avisos),
        )

    def _adyacentes(self, valor: Decimal) -> tuple[FilaTabla, FilaTabla]:
        for inferior, superior in zip(self.filas, self.filas[1:], strict=False):
            if inferior.clave < valor < superior.clave:
                return inferior, superior
        raise ErrorTabla(f"Tabla {self.id}: no hay filas adyacentes para {self.clave} = {valor}")

    def _aviso_pendiente(self, avisos: list[str], filas: list[FilaTabla]) -> None:
        pendientes = [str(f.clave) for f in filas if not f.verificado]
        if pendientes:
            avisos.append(
                f"tabla {self.id} pendiente de verificacion humana "
                f"(filas usadas sin verificar: {self.clave} = {', '.join(pendientes)})"
            )

    def como_coleccion(self) -> list[dict[str, ValorCelda]]:
        """Filas como lista de dicts tipados para el contexto de reglas (`exists(TABLA.col == X)`)."""
        return [fila.como_dict() for fila in self.filas]


def _unir(avisos: list[str]) -> str | None:
    return "; ".join(avisos) if avisos else None


def _clave_buscada(valor: object, contexto: str) -> Decimal:
    """Normaliza el valor con el que se busca: Decimal finito (o cadena/entero convertible)."""
    if isinstance(valor, Decimal):
        decimal = valor
    elif isinstance(valor, bool) or not isinstance(valor, str | int):
        raise ErrorTabla(f"{contexto}: se esperaba Decimal o cadena, no {type(valor).__name__}")
    else:
        try:
            decimal = Decimal(str(valor).strip())
        except InvalidOperation as exc:
            raise ErrorTabla(f"{contexto}: '{valor}' no es un numero decimal") from exc
    if not decimal.is_finite():
        raise ErrorTabla(f"{contexto}: '{decimal}' no es un numero finito")
    return decimal


def _celda_decimal(texto: str, contexto: str) -> Decimal | None:
    """Celda del CSV -> Decimal finito; vacia -> None. Rechaza exponentes, NaN, Infinity y separadores."""
    texto = texto.strip()
    if texto == "":
        return None
    if not PATRON_CELDA_NUMERICA.match(texto):
        raise ErrorTabla(
            f"{contexto}: '{texto}' no es un numero decimal admitido (digitos y punto decimal, sin exponente)"
        )
    try:
        decimal = Decimal(texto)
    except InvalidOperation as exc:  # el patron lo impide; defensa por si cambia
        raise ErrorTabla(f"{contexto}: '{texto}' no es un numero decimal") from exc
    if not decimal.is_finite():
        raise ErrorTabla(f"{contexto}: '{texto}' no es un numero finito")
    return decimal


def _fecha(valor: object, contexto: str) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        raise ErrorTabla(f"{contexto}: se esperaba una fecha (AAAA-MM-DD) sin hora, no '{valor}'")
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ErrorTabla(f"{contexto}: fecha '{valor}' no es ISO (AAAA-MM-DD)") from exc
    raise ErrorTabla(f"{contexto}: fecha con tipo inesperado {type(valor).__name__}")


def _leer_yaml(ruta_meta: Path) -> object:
    if not ruta_meta.is_file():
        raise ErrorTabla(f"Faltan metadatos de la tabla: {ruta_meta}")
    try:
        with ruta_meta.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ErrorTabla(f"{ruta_meta}: YAML ilegible ({exc})") from exc


def _lista_de_cadenas(valor: object, contexto: str) -> list[str]:
    if not isinstance(valor, list) or not valor or not all(isinstance(c, str) and c.strip() for c in valor):
        raise ErrorTabla(f"{contexto}: debe ser una lista no vacia de nombres de columna")
    return [c.strip() for c in valor]


def _leer_meta(ruta_meta: Path) -> dict:
    """Lee y valida el `.meta.yaml`: campos obligatorios, columnas, clave, valor, vigencia y restricciones."""
    meta = _leer_yaml(ruta_meta)
    if not isinstance(meta, dict):
        raise ErrorTabla(f"{ruta_meta}: los metadatos no son un mapa YAML")
    for campo in CAMPOS_META_OBLIGATORIOS:
        if campo not in meta or meta[campo] is None:
            raise ErrorTabla(f"{ruta_meta}: falta el campo '{campo}'")
    if not isinstance(meta["vigencia"], dict) or "desde" not in meta["vigencia"]:
        raise ErrorTabla(f"{ruta_meta}: 'vigencia' debe ser un mapa con 'desde' y 'hasta'")

    columnas = _lista_de_cadenas(meta["columnas"], f"{ruta_meta}: 'columnas'")
    if len(set(columnas)) != len(columnas):
        raise ErrorTabla(f"{ruta_meta}: 'columnas' repite nombres")
    if COLUMNA_VERIFICADO not in columnas:
        raise ErrorTabla(f"{ruta_meta}: 'columnas' debe incluir '{COLUMNA_VERIFICADO}'")
    numericas = [c for c in columnas if c != COLUMNA_VERIFICADO]
    for campo in ("clave", "valor"):
        nombre = meta[campo]
        if not isinstance(nombre, str) or nombre not in numericas:
            raise ErrorTabla(f"{ruta_meta}: '{campo}' = {nombre!r} no es una columna numerica de 'columnas'")
    if meta["clave"] == meta["valor"]:
        raise ErrorTabla(f"{ruta_meta}: 'clave' y 'valor' no pueden ser la misma columna")

    restricciones = meta.get("restricciones") or {}
    if not isinstance(restricciones, dict):
        raise ErrorTabla(f"{ruta_meta}: 'restricciones' debe ser un mapa")
    for nombre, cols in restricciones.items():
        if nombre not in RESTRICCIONES_CONOCIDAS:
            raise ErrorTabla(
                f"{ruta_meta}: restriccion desconocida '{nombre}' (admitidas: {RESTRICCIONES_CONOCIDAS})"
            )
        for col in _lista_de_cadenas(cols, f"{ruta_meta}: restricciones.{nombre}"):
            if col not in numericas:
                raise ErrorTabla(f"{ruta_meta}: restricciones.{nombre} cita una columna desconocida '{col}'")
    return meta


def _leer_filas(ruta_csv: Path, meta: dict, id_tabla: str) -> tuple[list[FilaTabla], list[str]]:
    """Lee el CSV segun `meta.columnas` y aplica la sanidad de carga. Devuelve (filas, avisos_carga)."""
    columnas: list[str] = [str(c) for c in meta["columnas"]]
    clave, valor = str(meta["clave"]), str(meta["valor"])
    positivas = [str(c) for c in (meta.get("restricciones") or {}).get("positivo", [])]

    with ruta_csv.open(encoding="utf-8", newline="") as fh:
        lector = csv.reader(fh)
        cabecera = [c.strip() for c in next(lector, [])]
        if cabecera != columnas:
            raise ErrorTabla(
                f"{ruta_csv}: la cabecera {cabecera} no coincide con 'columnas' del meta {columnas} "
                "(mismo conjunto y mismo orden)"
            )
        filas: list[FilaTabla] = []
        for numero, registro in enumerate(lector, start=2):
            if not registro or all(c.strip() == "" for c in registro):
                continue  # linea en blanco
            ctx = f"{ruta_csv.name} linea {numero}"
            if len(registro) != len(columnas):
                raise ErrorTabla(f"{ctx}: {len(registro)} celdas para {len(columnas)} columnas")
            valores: dict[str, ValorCelda] = {}
            for columna, celda in zip(columnas, registro, strict=True):
                if columna == COLUMNA_VERIFICADO:
                    marca = celda.strip()
                    if marca not in VALORES_VERIFICADO:
                        raise ErrorTabla(f"{ctx}: 'verificado' debe ser 'si' o 'pendiente', no '{marca}'")
                    valores[columna] = VALORES_VERIFICADO[marca]
                else:
                    valores[columna] = _celda_decimal(celda, f"{ctx} {columna}")
            for columna in (clave, valor):
                if valores[columna] is None:
                    papel = "clave" if columna == clave else "valor"
                    raise ErrorTabla(f"{ctx}: la columna '{columna}' ({papel}) esta vacia")
            for columna in positivas:
                celda_valor = valores[columna]
                if isinstance(celda_valor, Decimal) and celda_valor <= 0:
                    raise ErrorTabla(
                        f"{ctx}: '{columna}' = {celda_valor} debe ser > 0 (restricciones.positivo)"
                    )
            filas.append(FilaTabla(valores=valores, columna_clave=clave))

    if not filas:
        raise ErrorTabla(f"{ruta_csv}: la tabla no tiene filas")
    for anterior, siguiente in zip(filas, filas[1:], strict=False):
        if not anterior.clave < siguiente.clave:
            raise ErrorTabla(
                f"Tabla {id_tabla}: la clave '{clave}' debe ser estrictamente creciente en el orden del CSV "
                f"({anterior.clave} seguido de {siguiente.clave})"
            )
    avisos: list[str] = []
    for anterior, siguiente in zip(filas, filas[1:], strict=False):
        v0, v1 = anterior[valor], siguiente[valor]
        if isinstance(v0, Decimal) and isinstance(v1, Decimal) and v1 < v0:
            avisos.append(
                f"tabla {id_tabla}: '{valor}' decrece entre {clave} = {anterior.clave} ({v0}) "
                f"y {siguiente.clave} ({v1}); revisar la transcripcion"
            )
    return filas, avisos


def _ruta_meta_de(ruta_csv: Path) -> Path:
    return ruta_csv.with_name(ruta_csv.name[: -len(ruta_csv.suffix)] + SUFIJO_META)


def _ruta_csv_de(ruta_meta: Path) -> Path:
    return ruta_meta.with_name(ruta_meta.name[: -len(SUFIJO_META)] + ".csv")


def cargar_tabla_desde(ruta_csv: Path, id_esperado: str | None = None) -> Tabla:
    """Carga un CSV concreto y su `.meta.yaml` (mismo nombre base). Comprueba id, columnas, clave y valor."""
    ruta_csv = Path(ruta_csv)
    if not ruta_csv.is_file():
        raise ErrorTabla(f"No existe el fichero de tabla: {ruta_csv}")
    meta = _leer_meta(_ruta_meta_de(ruta_csv))
    id_tabla = str(meta["id"])
    if id_esperado is not None and id_tabla != id_esperado:
        raise ErrorTabla(f"{ruta_csv}: el meta declara id '{id_tabla}' pero se esperaba '{id_esperado}'")
    vigencia = meta["vigencia"]
    filas, avisos_carga = _leer_filas(ruta_csv, meta, id_tabla)
    restricciones = {str(k): [str(c) for c in v] for k, v in (meta.get("restricciones") or {}).items()}
    return Tabla(
        id=id_tabla,
        fichero=ruta_csv,
        columnas=[str(c) for c in meta["columnas"]],
        clave=str(meta["clave"]),
        valor=str(meta["valor"]),
        vigencia_desde=_fecha(vigencia.get("desde"), f"{id_tabla} vigencia.desde"),
        vigencia_hasta=_fecha(vigencia.get("hasta"), f"{id_tabla} vigencia.hasta"),
        filas=filas,
        fuente=str(meta["fuente"]) if meta.get("fuente") else None,
        metodo_transcripcion=str(meta["metodo_transcripcion"]) if meta.get("metodo_transcripcion") else None,
        restricciones=restricciones,
        avisos_carga=avisos_carga,
    )


def cargar_tabla(id: str, raiz: Path = RAIZ_REPO) -> Tabla:
    """Carga la tabla `id` buscando en `raiz/data/*.meta.yaml` el meta cuyo `id` coincide.

    La localizacion solo lee el `id` de cada meta; la validacion completa del meta elegido la hace
    `cargar_tabla_desde`, de modo que un meta malformado del id buscado muestra su error real.
    Un meta ilegible (YAML roto o sin mapa) se enumera en el error si no se encuentra el id.
    """
    carpeta = Path(raiz) / CARPETA_DATA
    if not carpeta.is_dir():
        raise ErrorTabla(f"No existe la carpeta de tablas: {carpeta}")
    candidatos: list[Path] = []
    ilegibles: list[str] = []
    for ruta_meta in sorted(carpeta.glob(f"*{SUFIJO_META}")):
        try:
            meta = _leer_yaml(ruta_meta)
        except ErrorTabla as exc:
            ilegibles.append(str(exc))
            continue
        if not isinstance(meta, dict):
            ilegibles.append(f"{ruta_meta}: los metadatos no son un mapa YAML")
            continue
        if str(meta.get("id")) == id:
            candidatos.append(ruta_meta)
    if not candidatos:
        detalle = f"; metas ilegibles: {ilegibles}" if ilegibles else ""
        raise ErrorTabla(f"Ninguna tabla de {carpeta} declara id '{id}'{detalle}")
    if len(candidatos) > 1:
        raise ErrorTabla(f"Varias tablas de {carpeta} declaran id '{id}': {[c.name for c in candidatos]}")
    return cargar_tabla_desde(_ruta_csv_de(candidatos[0]), id_esperado=id)


def cargar_tablas(spec_tablas: dict, raiz: Path = RAIZ_REPO) -> dict[str, Tabla]:
    """Carga el bloque `tablas` de una spec ({ID: {fichero, columnas, ...}}).

    ErrorTabla si el fichero no existe, si el CSV no tiene las columnas declaradas en la spec
    (garantia 4 de docs/04 §2.5: las declaradas son subconjunto de la cabecera) o si el meta declara otro id.
    """
    if not isinstance(spec_tablas, dict):
        raise ErrorTabla("El bloque 'tablas' de la spec debe ser un mapa {ID: {...}}")
    tablas: dict[str, Tabla] = {}
    for id_tabla, declaracion in spec_tablas.items():
        if not isinstance(declaracion, dict) or "fichero" not in declaracion:
            raise ErrorTabla(f"tablas.{id_tabla}: falta 'fichero'")
        ruta_csv = Path(raiz) / str(declaracion["fichero"])
        if not ruta_csv.is_file():
            raise ErrorTabla(f"tablas.{id_tabla}: no existe {ruta_csv}")
        declaradas = [str(c) for c in declaracion.get("columnas", [])]
        with ruta_csv.open(encoding="utf-8", newline="") as fh:
            cabecera = [c.strip() for c in next(csv.reader(fh), [])]
        faltan = [c for c in declaradas if c not in cabecera]
        if faltan:
            raise ErrorTabla(f"tablas.{id_tabla}: {ruta_csv.name} no tiene las columnas declaradas {faltan}")
        tablas[str(id_tabla)] = cargar_tabla_desde(ruta_csv, id_esperado=str(id_tabla))
    return tablas
