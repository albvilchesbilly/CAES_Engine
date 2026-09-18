"""Hallazgos QA de F0.4 (`engine/spec_registry.py`). Tests EN ROJO a proposito: cada uno reproduce un defecto.

No se borran ni se relajan: se corrige `engine/spec_registry.py` (agente spec-fichas) y pasan a verde. La
numeracion sigue el informe QA de la oleada 3 (H-F04-n). Las specs sinteticas se escriben en tmp_path; las
tablas se leen de RAIZ/data.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from engine.calculo import ErrorCalculo, calcular
from engine.spec_registry import ErrorCargaSpec, Spec, cargar_spec

RAIZ = Path(__file__).resolve().parents[1]
SPEC_ACTIVA = RAIZ / "spec" / "IND240_v1.1.yaml"


def _activa() -> dict:
    with SPEC_ACTIVA.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _cargar(tmp_path: Path, datos: dict) -> Spec:
    carpeta = tmp_path / "spec"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{datos['spec']['id']}_v{datos['spec']['version_ficha']}.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return cargar_spec(ruta, raiz_datos=RAIZ)


def _variable(datos: dict, nombre: str) -> dict:
    return datos["variables"][nombre]


# --- H-F04-1: el registro acepta specs que el calculo rechaza ----------------------------------------------
#
# docs/04 §2.5: "Al cargar una spec, el registro falla (la ficha no se activa) si ...". Hoy una spec puede
# pasar el registro y reventar en la primera llamada a `calcular` (ErrorCalculo de carga, no de datos). El
# registro debe ser la unica puerta: planificar el calculo al cargar (p. ej. exponer `calculo.planificar` y
# llamarlo desde `cargar_spec`, envolviendo ErrorCalculo en ErrorCargaSpec) o replicar las comprobaciones.

CASOS_ACEPTA_REGISTRO_RECHAZA_CALCULO: dict[str, Callable[[dict], None]] = {
    "ciclo entre derivaciones": lambda d: (
        _variable(d, "h")["derivacion"].__setitem__("metodo", "min(h_antes, p)"),
        _variable(d, "p")["derivacion"].__setitem__("metodo", "perdidas_ref_kw / h"),
    ),
    "derivacion autorreferente": lambda d: _variable(d, "h")["derivacion"].__setitem__("metodo", "h + 1"),
    "derivacion cita una tabla no declarada en `tablas`": lambda d: _variable(d, "perdidas_ref_kw")[
        "derivacion"
    ].__setitem__("fuente", "tabla:NOEXISTE"),
    "derivacion de tabla sin `clave`": lambda d: _variable(d, "perdidas_ref_kw")["derivacion"].pop("clave"),
    "calculo.aritmetica no soportada": lambda d: d["calculo"].__setitem__("aritmetica", "float"),
    "redondeo_salida no soportado": lambda d: d["calculo"]["redondeo_salida"].__setitem__(
        "AETOTAL_cae", "redondear al alza"
    ),
    "calculo.total.formula no usa la salida por unidad": lambda d: d["calculo"]["total"].__setitem__(
        "formula", "sum(PM)"
    ),
    "calculo sin bloque total": lambda d: d["calculo"].pop("total"),
}


@pytest.mark.parametrize("caso", list(CASOS_ACEPTA_REGISTRO_RECHAZA_CALCULO))
def test_h_f04_1_toda_spec_aceptada_por_el_registro_es_calculable(tmp_path: Path, caso: str) -> None:
    datos = _activa()
    CASOS_ACEPTA_REGISTRO_RECHAZA_CALCULO[caso](datos)
    try:
        spec = _cargar(tmp_path, datos)
    except ErrorCargaSpec:
        return  # rechazada al cargar: correcto
    try:
        calcular(spec.datos, {}, spec.tablas)
    except ErrorCalculo as exc:
        pytest.fail(f"el registro activo una spec que el calculo rechaza ({caso}): {exc}")


# --- H-F04-2: dos criterios para la misma precondicion -----------------------------------------------------
#
# `0 < h <= 8760` es para el registro una "precondicion de procedimiento (texto)"
# (`Spec.precondiciones_texto`) y para calculo.py una expresion evaluable (la reescribe como conjuncion).
# Un consumidor (reglas.py, informe) no puede saber cual de los dos tiene razon. Criterio unico: soporte
# nativo de la comparacion encadenada en `engine/expresiones.py` (pendiente F0.9 segun ADR-002) o la misma
# reescritura compartida; en ambos casos `precondiciones_texto` (registro) == `precondiciones_delegadas`
# (calculo).


def test_h_f04_2_registro_y_calculo_delegan_las_mismas_precondiciones(spec_ind240: Spec) -> None:
    resultado = calcular(spec_ind240.datos, {}, spec_ind240.tablas)
    assert spec_ind240.precondiciones_texto == resultado.precondiciones_delegadas
    assert "0 < h <= 8760" not in spec_ind240.precondiciones_texto


# --- H-F04-3: precondicion con funcion desconocida no es error de carga ------------------------------------
#
# docs/04 §2.5 garantia 1 y CLAUDE.md §2 ("funcion desconocida = error de carga de la spec").
# `_compilar_calculo` conserva como texto cualquier precondicion que no compile, incluida `raiz(N2) < N1` o
# `N2 << N1`. Una precondicion de procedimiento (prosa) y una expresion con errata deben distinguirse: como
# minimo, el error "funcion desconocida" del parser es siempre error de carga.


@pytest.mark.parametrize("precondicion", ["raiz(N2) < N1", "N2 << N1"])
def test_h_f04_3_precondicion_con_funcion_desconocida_o_errata_es_error_de_carga(
    tmp_path: Path, precondicion: str
) -> None:
    datos = _activa()
    datos["calculo"]["precondiciones"] = [precondicion]
    with pytest.raises(ErrorCargaSpec):
        _cargar(tmp_path, datos)


# --- H-F04-4: la garantia da por cubierta una derivacion ciclica -----------------------------------------
#
# `_Analizador.cubierta` devuelve True al reencontrar una raiz visitada ("ciclo de derivacion: no reabrir").
# Un ciclo `Q <- Q2 <- Q` no cubre nada: nunca habra valor. Debe ser error de carga (es la misma condicion
# que calculo.py rechaza como "dependencias circulares").


def test_h_f04_4_ciclo_de_derivacion_no_cuenta_como_cubierto(tmp_path: Path) -> None:
    datos = _activa()
    datos["variables"]["Q"] = {"nivel": "motor", "evidencia": "derivado", "derivacion": {"metodo": "Q2 + 1"}}
    datos["variables"]["Q2"] = {"nivel": "motor", "evidencia": "derivado", "derivacion": {"metodo": "Q - 1"}}
    datos["reglas"].append(
        {"id": "R-QA-01", "descripcion": "Q positivo", "logica": "Q > 0", "severidad": "BLOQUEANTE_DATOS"}
    )
    with pytest.raises(ErrorCargaSpec, match="R-QA-01|circular"):
        _cargar(tmp_path, copy.deepcopy(datos))
