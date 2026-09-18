"""Hallazgos QA de F0.3 (`engine/calculo.py`). Tests EN ROJO a proposito: cada uno reproduce un defecto.

No se borran ni se relajan: se corrige `engine/calculo.py` (agente motor-nucleo) y pasan a verde. La
numeracion sigue el informe QA de la oleada 3 (H-F03-n). Los nombres de la ficha aparecen solo aqui.
"""

from __future__ import annotations

import copy
import re
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.calculo import ErrorCalculo, calcular
from engine.tablas import cargar_tablas

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / "spec" / "IND240_v1.1.yaml"
FUENTE = RAIZ / "engine" / "calculo.py"
TOTAL_A = Decimal("305829.6")
CASO_A = {
    "PM": Decimal("110"),
    "N1": Decimal("1485"),
    "N2": Decimal("1188"),
    "h_antes": Decimal("6000"),
    "h_despues": Decimal("6200"),
    "P_prom": Decimal("60"),
}


@pytest.fixture(scope="module")
def spec() -> dict:
    with SPEC.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def tablas(spec: dict) -> dict:
    return cargar_tablas(spec["tablas"])


def _variante(**cambios: int | str) -> dict[str, Decimal]:
    return {**CASO_A, **{k: Decimal(str(v)) for k, v in cambios.items()}}


# --- H-F03-1: la reescritura de comparaciones encadenadas ignora la precedencia --------------------------
#
# `_desencadenar` corta el texto por todo `<`/`>` de nivel superior sin mirar `or`, `and`, `not` ni `->`:
#   "0 < h <= 8760 or PM > 100" -> "(0 < h) and (h <= 8760 or PM) and (8760 or PM > 100)"
#       (deberia ser (0<h and h<=8760) or PM>100; lo reescrito compila y revienta al evaluar `8760 or PM`)
#   "not 8760 < h <= 100000"    -> "(not 8760 < h) and (h <= 100000)"  (deberia ser not (8760<h and h<=1e5))
#   "0 < h <= 8760 -> x"        -> "(0 < h) and (h <= 8760 -> x)"
# El texto original no compila (encadenada), el reescrito si, y se evalua con otra semantica en silencio.
# Correcto: o bien la reescritura respeta la precedencia (solo se aplica a una comparacion encadenada pura, o
# se reescribe dentro de cada operando logico), o bien se rechaza AL PLANIFICAR con ErrorCalculo. Nunca un
# resultado distinto ni un error en evaluacion.


@pytest.mark.parametrize(
    ("precondicion", "cambios", "esperado"),
    [
        ("0 < h <= 8760 or PM > 100", {"h_antes": 0}, True),  # (False) or True == True
        ("not 8760 < h <= 100000", {"h_antes": 200000, "h_despues": 200000}, True),  # not (True and False)
    ],
)
def test_h_f03_1_reescritura_encadenada_respeta_precedencia(
    spec: dict, tablas: dict, precondicion: str, cambios: dict, esperado: bool
) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["calculo"]["precondiciones"] = [precondicion]
    try:
        plan = calcular(spec_mod, {}, tablas)  # sin unidades: solo planifica
    except ErrorCalculo:
        return  # rechazar la reescritura ambigua al planificar tambien es correcto
    assert precondicion not in plan.precondiciones_delegadas, (
        "se delego en silencio una precondicion evaluable"
    )
    r = calcular(spec_mod, {"M1": _variante(**cambios)}, tablas)
    assert r.por_unidad[0].precondiciones[precondicion] is esperado


# --- H-F03-2: una precondicion con errata o funcion desconocida se delega en silencio ----------------------
#
# CLAUDE.md §2: "Funcion desconocida = error de carga de la spec, no de ejecucion". `_planificar` captura
# cualquier ErrorCalculo al compilar una precondicion y la manda a `precondiciones_delegadas` como si fuera
# "de procedimiento". Con `raiz(N2) < N1` o `N2 << N1` el calculo sigue y publica 305829.6.


@pytest.mark.parametrize("precondicion", ["raiz(N2) < N1", "N2 << N1", "N2 < N1 andd h > 0"])
def test_h_f03_2_precondicion_con_errata_es_error_de_carga(
    spec: dict, tablas: dict, precondicion: str
) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["calculo"]["precondiciones"] = [precondicion]
    with pytest.raises(ErrorCalculo):
        calcular(spec_mod, {"M1": dict(CASO_A)}, tablas)


# --- H-F03-3: una derivacion con `fuente` documental y `metodo` compilable sobreescribe la entrada ---------
#
# Spec Registry (F0.4) compila `derivacion.metodo` SOLO si la derivacion no declara `fuente` (con fuente, el
# metodo describe la extraccion). calculo.py compila el metodo si parsea y sus identificadores son variables,
# ignorando la fuente: con `N2.derivacion = {fuente: registro_funcionamiento, metodo: "N1 - 1"}` deriva
# N2 = 1484 y descarta el N2 consolidado del registro con un aviso. Criterio unico propuesto: el de F0.4.


def test_h_f03_3_derivacion_con_fuente_documental_no_se_recalcula(spec: dict, tablas: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    # `fuente: registro_funcionamiento` se mantiene; solo cambia el `metodo`
    spec_mod["variables"]["N2"]["derivacion"]["metodo"] = "N1 - 1"
    r = calcular(spec_mod, {"M1": dict(CASO_A)}, tablas)
    u = r.por_unidad[0]
    assert "N2" not in u.derivadas, "N2 tiene fuente documental: la deriva el consolidador, no calculo.py"
    assert u.entradas["N2"] == Decimal("1188")
    assert not any("N2 suministrado externamente ignorado" in a for a in r.avisos)
    assert r.total == TOTAL_A


# --- H-F03-4: vocabulario de la ficha en el fuente (`p_fuente`, `"p"`) ------------------------------------
#
# Regla de oro 4. `ResultadoUnidad.p_fuente` y `datos["p_fuente"]` en `_serializar` nombran la variable `p`
# de IND240 dentro de engine/. Una segunda ficha sin `p` arrastraria un campo muerto. Lo generico ya existe
# (`fuentes[<variable>]`); R-CAL-04 debe leer `p.fuente` del contexto que construya reglas.py desde `fuentes`.


def test_h_f03_4_fuente_sin_nombres_de_variables_de_la_ficha() -> None:
    fuente = FUENTE.read_text(encoding="utf-8")
    assert "p_fuente" not in fuente
    assert '"p"' not in fuente
    codigo = "\n".join(linea for linea in fuente.splitlines() if not linea.lstrip().startswith("#"))
    assert not re.search(r"R-[A-Z]{3}-\d{2}", codigo.split('"""', 2)[-1])  # ids de regla fuera del docstring


# --- H-F03-5: el criterio de redondeo se acepta por subcadena ---------------------------------------------
#
# `CRITERIO_TRUNCAR in criterio.lower()`: "no truncar; redondear al alza" se acepta y se trunca.


def test_h_f03_5_criterio_de_redondeo_negado_no_se_acepta(spec: dict, tablas: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["calculo"]["redondeo_salida"]["AETOTAL_cae"] = "no truncar; redondear al alza"
    with pytest.raises(ErrorCalculo, match="redondeo"):
        calcular(spec_mod, {"M1": dict(CASO_A)}, tablas)
