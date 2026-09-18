"""Tablas de referencia de `data/` (N3): carga con vigencia, busqueda por clave e interpolacion (INT-02).

Toda tabla es dato normativo transcrito (data/README.md). Este modulo:

- lee `data/<fichero>.csv` y su `data/<fichero>.meta.yaml` (id, fuente, vigencia, columnas, clave);
- guarda cada valor como `Decimal` construido desde la cadena del CSV (nunca `float`);
- busca por clave exacta y, si no hay fila, interpola linealmente entre las dos filas adyacentes
  (criterio INT-02 de la spec) devolviendo la marca `INT-02` y un aviso; fuera de rango no extrapola;
- propaga en el aviso si alguna fila usada esta `verificado: pendiente` (solo Billy marca `si`).

No importa nada de agentes/, salida/, generator/ ni tests/.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

RAIZ_REPO = Path(__file__).resolve().parents[1]
CARPETA_DATA = "data"
SUFIJO_META = ".meta.yaml"
VALORES_VERIFICADO = {"si": True, "pendiente": False}
COLUMNAS_FILA = ("kva_salida", "kw_motor", "perdidas_ref_kw", "cos_phi", "verificado")


class ErrorTabla(Exception):
    """Error de carga o de coherencia de una tabla de referencia. Es error de carga, no de evaluacion."""


@dataclass(frozen=True)
class FilaTabla:
    """Una fila del cuadro 6. `verificado` es True solo si la fila lleva `si` en el CSV."""

    kva_salida: Decimal | None
    kw_motor: Decimal
    perdidas_ref_kw: Decimal
    cos_phi: Decimal | None
    verificado: bool

    def como_dict(self) -> dict[str, Decimal | bool | None]:
        return {
            "kva_salida": self.kva_salida,
            "kw_motor": self.kw_motor,
            "perdidas_ref_kw": self.perdidas_ref_kw,
            "cos_phi": self.cos_phi,
            "verificado": self.verificado,
        }


@dataclass
class ResultadoBusqueda:
    """Resultado de `Tabla.buscar`. `valor` es `perdidas_ref_kw` exacto o interpolado; None si no procede."""

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
    vigencia_desde: date | None
    vigencia_hasta: date | None
    filas: list[FilaTabla] = field(default_factory=list)
    fuente: str | None = None
    metodo_transcripcion: str | None = None

    @property
    def todas_verificadas(self) -> bool:
        return all(f.verificado for f in self.filas)

    @property
    def clave_minima(self) -> Decimal:
        return self._clave_de(self.filas[0])

    @property
    def clave_maxima(self) -> Decimal:
        return self._clave_de(self.filas[-1])

    def _clave_de(self, fila: FilaTabla) -> Decimal:
        valor = getattr(fila, self.clave)
        if not isinstance(valor, Decimal):
            raise ErrorTabla(f"Tabla {self.id}: la clave {self.clave} no es Decimal en una fila")
        return valor

    def vigente(self, fecha: date) -> bool:
        if self.vigencia_desde is not None and fecha < self.vigencia_desde:
            return False
        if self.vigencia_hasta is not None and fecha > self.vigencia_hasta:
            return False
        return True

    def buscar_exacta(self, valor: Decimal) -> FilaTabla | None:
        valor = _a_decimal(valor, "valor buscado")
        for fila in self.filas:
            if self._clave_de(fila) == valor:
                return fila
        return None

    def buscar(self, valor: Decimal) -> ResultadoBusqueda:
        """Fila exacta si existe; si no, interpolacion lineal (INT-02); fuera de rango, valor None."""
        valor = _a_decimal(valor, "valor buscado")
        if not self.filas:
            raise ErrorTabla(f"Tabla {self.id} sin filas")
        avisos: list[str] = []

        fila = self.buscar_exacta(valor)
        if fila is not None:
            self._aviso_pendiente(avisos, [fila])
            return ResultadoBusqueda(
                fila=fila,
                valor=fila.perdidas_ref_kw,
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
        k0, k1 = self._clave_de(inferior), self._clave_de(superior)
        p0, p1 = inferior.perdidas_ref_kw, superior.perdidas_ref_kw
        interpolado = p0 + (p1 - p0) * (valor - k0) / (k1 - k0)
        avisos.append(
            f"INT-02: sin fila exacta en {self.id} para {self.clave} = {valor}; "
            f"perdidas_ref_kw interpoladas linealmente entre {k0} kW ({p0}) y {k1} kW ({p1}); revision humana"
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
            if self._clave_de(inferior) < valor < self._clave_de(superior):
                return inferior, superior
        raise ErrorTabla(f"Tabla {self.id}: no hay filas adyacentes para {self.clave} = {valor}")

    def _aviso_pendiente(self, avisos: list[str], filas: list[FilaTabla]) -> None:
        pendientes = [str(self._clave_de(f)) for f in filas if not f.verificado]
        if pendientes:
            avisos.append(
                f"tabla {self.id} pendiente de verificacion humana "
                f"(filas usadas sin verificar: {self.clave} = {', '.join(pendientes)})"
            )

    def como_coleccion(self) -> list[dict[str, Decimal | bool | None]]:
        """Filas como lista de dicts para el contexto de reglas (`exists(REG1781_CUADRO6.kw_motor == PM)`)."""
        return [fila.como_dict() for fila in self.filas]


def _unir(avisos: list[str]) -> str | None:
    return "; ".join(avisos) if avisos else None


def _a_decimal(texto: object, contexto: str) -> Decimal:
    if isinstance(texto, Decimal):
        return texto
    if isinstance(texto, bool) or not isinstance(texto, str | int):
        raise ErrorTabla(f"{contexto}: se esperaba Decimal o cadena, no {type(texto).__name__}")
    try:
        return Decimal(str(texto).strip())
    except InvalidOperation as exc:
        raise ErrorTabla(f"{contexto}: '{texto}' no es un numero decimal") from exc


def _decimal_opcional(texto: str, contexto: str) -> Decimal | None:
    texto = texto.strip()
    return None if texto == "" else _a_decimal(texto, contexto)


def _fecha(valor: object, contexto: str) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ErrorTabla(f"{contexto}: fecha '{valor}' no es ISO (AAAA-MM-DD)") from exc
    raise ErrorTabla(f"{contexto}: fecha con tipo inesperado {type(valor).__name__}")


def _leer_meta(ruta_meta: Path) -> dict:
    if not ruta_meta.is_file():
        raise ErrorTabla(f"Faltan metadatos de la tabla: {ruta_meta}")
    with ruta_meta.open(encoding="utf-8") as fh:
        meta = yaml.safe_load(fh)
    if not isinstance(meta, dict):
        raise ErrorTabla(f"{ruta_meta}: los metadatos no son un mapa YAML")
    for campo in ("id", "columnas", "clave", "vigencia"):
        if campo not in meta:
            raise ErrorTabla(f"{ruta_meta}: falta el campo '{campo}'")
    if not isinstance(meta["vigencia"], dict) or "desde" not in meta["vigencia"]:
        raise ErrorTabla(f"{ruta_meta}: 'vigencia' debe ser un mapa con 'desde' y 'hasta'")
    return meta


def _leer_filas(ruta_csv: Path, clave: str, id_tabla: str) -> list[FilaTabla]:
    with ruta_csv.open(encoding="utf-8", newline="") as fh:
        lector = csv.DictReader(fh)
        cabecera = lector.fieldnames or []
        faltan = [c for c in COLUMNAS_FILA if c not in cabecera]
        if faltan:
            raise ErrorTabla(f"{ruta_csv}: faltan columnas {faltan} en la cabecera")
        filas: list[FilaTabla] = []
        for numero, registro in enumerate(lector, start=2):
            ctx = f"{ruta_csv.name} linea {numero}"
            celda = {c: (registro.get(c) or "") for c in COLUMNAS_FILA}
            marca = celda["verificado"].strip()
            if marca not in VALORES_VERIFICADO:
                raise ErrorTabla(f"{ctx}: 'verificado' debe ser 'si' o 'pendiente', no '{marca}'")
            filas.append(
                FilaTabla(
                    kva_salida=_decimal_opcional(celda["kva_salida"], f"{ctx} kva_salida"),
                    kw_motor=_a_decimal(celda["kw_motor"], f"{ctx} kw_motor"),
                    perdidas_ref_kw=_a_decimal(celda["perdidas_ref_kw"], f"{ctx} perdidas_ref_kw"),
                    cos_phi=_decimal_opcional(celda["cos_phi"], f"{ctx} cos_phi"),
                    verificado=VALORES_VERIFICADO[marca],
                )
            )
    if not filas:
        raise ErrorTabla(f"{ruta_csv}: la tabla no tiene filas")
    if clave not in COLUMNAS_FILA or clave == "verificado":
        raise ErrorTabla(f"Tabla {id_tabla}: clave '{clave}' no es una columna numerica de la tabla")
    claves = [getattr(f, clave) for f in filas]
    if any(k is None for k in claves):
        raise ErrorTabla(f"Tabla {id_tabla}: hay filas sin valor en la clave '{clave}'")
    if len(set(claves)) != len(claves):
        raise ErrorTabla(f"Tabla {id_tabla}: claves '{clave}' duplicadas")
    return sorted(filas, key=lambda f: getattr(f, clave))


def cargar_tabla_desde(ruta_csv: Path, id_esperado: str | None = None) -> Tabla:
    """Carga un CSV concreto y su `.meta.yaml` (mismo nombre base). Comprueba id, columnas y clave."""
    ruta_csv = Path(ruta_csv)
    if not ruta_csv.is_file():
        raise ErrorTabla(f"No existe el fichero de tabla: {ruta_csv}")
    meta = _leer_meta(ruta_csv.with_name(ruta_csv.name[: -len(ruta_csv.suffix)] + SUFIJO_META))
    id_tabla = str(meta["id"])
    if id_esperado is not None and id_tabla != id_esperado:
        raise ErrorTabla(f"{ruta_csv}: el meta declara id '{id_tabla}' pero se esperaba '{id_esperado}'")
    columnas = [str(c) for c in meta["columnas"]]
    clave = str(meta["clave"])
    vigencia = meta["vigencia"]
    filas = _leer_filas(ruta_csv, clave, id_tabla)
    return Tabla(
        id=id_tabla,
        fichero=ruta_csv,
        columnas=columnas,
        clave=clave,
        vigencia_desde=_fecha(vigencia.get("desde"), f"{id_tabla} vigencia.desde"),
        vigencia_hasta=_fecha(vigencia.get("hasta"), f"{id_tabla} vigencia.hasta"),
        filas=filas,
        fuente=str(meta["fuente"]) if meta.get("fuente") else None,
        metodo_transcripcion=str(meta["metodo_transcripcion"]) if meta.get("metodo_transcripcion") else None,
    )


def cargar_tabla(id: str, raiz: Path = RAIZ_REPO) -> Tabla:
    """Carga la tabla `id` buscando en `raiz/data/*.meta.yaml` el meta cuyo `id` coincide."""
    carpeta = Path(raiz) / CARPETA_DATA
    if not carpeta.is_dir():
        raise ErrorTabla(f"No existe la carpeta de tablas: {carpeta}")
    candidatos: list[Path] = []
    for ruta_meta in sorted(carpeta.glob(f"*{SUFIJO_META}")):
        try:
            meta = _leer_meta(ruta_meta)
        except ErrorTabla:
            continue
        if str(meta.get("id")) == id:
            candidatos.append(ruta_meta)
    if not candidatos:
        raise ErrorTabla(f"Ninguna tabla de {carpeta} declara id '{id}'")
    if len(candidatos) > 1:
        raise ErrorTabla(f"Varias tablas de {carpeta} declaran id '{id}': {[c.name for c in candidatos]}")
    ruta_meta = candidatos[0]
    ruta_csv = ruta_meta.with_name(ruta_meta.name[: -len(SUFIJO_META)] + ".csv")
    return cargar_tabla_desde(ruta_csv, id_esperado=id)


def cargar_tablas(spec_tablas: dict, raiz: Path = RAIZ_REPO) -> dict[str, Tabla]:
    """Carga el bloque `tablas` de una spec ({ID: {fichero, columnas, ...}}).

    ErrorTabla si el fichero no existe, si el CSV no tiene las columnas declaradas en la spec
    (garantia 4 de docs/04 §2.5) o si el meta declara otro id.
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
            cabecera = next(csv.reader(fh), [])
        faltan = [c for c in declaradas if c not in cabecera]
        if faltan:
            raise ErrorTabla(f"tablas.{id_tabla}: {ruta_csv.name} no tiene las columnas declaradas {faltan}")
        tablas[str(id_tabla)] = cargar_tabla_desde(ruta_csv, id_esperado=str(id_tabla))
    return tablas
