"""F0.3: motor de calculo (`engine/calculo.py`) segun docs/04 §7, docs/05 §2.3 y §4.3, ADR-002 §2.5.

Fixtures propias del modulo: la spec real (`spec/IND240_v1.1.yaml`) cargada con `yaml.safe_load` y sus
tablas con `cargar_tablas`. Los nombres de variables de la ficha (PM, N1, h, p, ...) aparecen SOLO aqui: el
motor los lee de la spec.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date
from decimal import Decimal, getcontext, localcontext
from pathlib import Path

import pytest
import yaml

from engine.calculo import PRECISION_DECIMAL, ErrorCalculo, ResultadoCalculo, a_dict, calcular
from engine.expresiones import NO_EVALUABLE
from engine.tablas import Tabla, cargar_tablas

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / "spec" / "IND240_v1.1.yaml"
FUENTE = RAIZ / "engine" / "calculo.py"
ID_TABLA = "REG1781_CUADRO6"
ORIGEN_TABLA = f"tabla:{ID_TABLA}"
TOTAL_A = Decimal("305829.6")

# Caso A (docs/05 §2.3): PM 110, N1 1485, N2 1188, h_antes 6000, h_despues 6200 (no es el menor), P_prom 60.
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
def tablas(spec: dict) -> dict[str, Tabla]:
    return cargar_tablas(spec["tablas"])


@pytest.fixture
def unidad_a() -> dict[str, dict[str, Decimal]]:
    return {"M1": dict(CASO_A)}


def _variante(**cambios: Decimal | int) -> dict[str, Decimal]:
    return {**CASO_A, **{k: Decimal(v) for k, v in cambios.items()}}


def _div(a: str, b: str) -> Decimal:
    """Cociente con la precision del motor (la global del test puede ser otra)."""
    with localcontext() as ctx:
        ctx.prec = PRECISION_DECIMAL
        return Decimal(a) / Decimal(b)


def _formula_a(pm: str, n1: str, n2: str, p: Decimal, h: str) -> Decimal:
    """La formula de la ficha escrita a mano en el test (no en el motor), con la precision del motor."""
    with localcontext() as ctx:
        ctx.prec = PRECISION_DECIMAL
        return Decimal(pm) * (1 - (Decimal(n2) / Decimal(n1)) ** 3) * (1 - p) * Decimal(h)


P_A = _div("5.55", "110")


# --- caso A ---------------------------------------------------------------------------------------


def test_caso_a_total_exacto(spec: dict, tablas: dict, unidad_a: dict) -> None:
    r = calcular(spec, unidad_a, tablas)
    assert r.total == TOTAL_A
    assert r.total_cae == 305829
    assert r.motivo_no_calculo is None
    assert r.provisional is False
    assert r.controles_ok is True
    assert r.precondiciones_ok is True


def test_caso_a_derivadas(spec: dict, tablas: dict, unidad_a: dict) -> None:
    u = calcular(spec, unidad_a, tablas).por_unidad[0]
    assert u.num_serie_motor == "M1"
    assert u.derivadas["h"] == Decimal("6000")
    assert u.derivadas["perdidas_ref_kw"] == Decimal("5.55")
    assert u.derivadas["p"] == P_A
    assert u.salida == TOTAL_A
    assert u.fuentes["p"] == ORIGEN_TABLA  # R-CAL-04 lo lee de `fuentes`, no de un campo por ficha
    assert u.fuentes["perdidas_ref_kw"] == ORIGEN_TABLA
    assert u.fuentes["h"] == "derivado"
    assert u.entradas == CASO_A
    assert u.controles == {"FIS-01": True, "FIS-02": True}
    assert u.precondiciones == {"N2 < N1": True, "0 < h <= 8760": True}


def test_caso_a_interpretaciones(spec: dict, tablas: dict, unidad_a: dict) -> None:
    r = calcular(spec, unidad_a, tablas)
    assert "INT-01" in r.interpretaciones
    assert "INT-06" in r.interpretaciones
    assert "INT-02" not in r.interpretaciones
    # INT-03 y INT-04 son las `derivacion.interpretacion` de N2 y h_despues,
    # entradas que consume la formula
    assert r.por_unidad[0].interpretaciones == ["INT-03", "INT-04", "INT-01"]
    assert "INT-03" in r.interpretaciones and "INT-04" in r.interpretaciones
    assert r.avisos == []


def test_caso_a_traza(spec: dict, tablas: dict, unidad_a: dict) -> None:
    traza = "\n".join(calcular(spec, unidad_a, tablas).traza)
    for esperado in (
        "entradas PM=110 N1=1485 N2=1188 h_antes=6000 h_despues=6200 P_prom=60",
        "h = min(h_antes, h_despues) = 6000",
        f"perdidas_ref_kw = 5.55 ({ORIGEN_TABLA}, fila exacta kw_motor = 110)",
        "p = perdidas_ref_kw / PM = 0.0504545",
        "(INT-01)",
        "(N2 / N1) = 0.8",
        "(1 - (N2 / N1) ** 3) = 0.488",
        "AEM = PM * (1 - (N2 / N1) ** 3) * (1 - p) * h = 305829.6",
        "control FIS-01 'AEM <= PM * h' = True",
        "control FIS-02 'P_prom <= PM' = True",
        "precondicion 'N2 < N1' = True",
        "AETOTAL = sum(AEM) = 305829.6",
        "AETOTAL_cae = 305829 (truncar a kWh entero (criterio conservador); INT-06)",
        "interpretaciones aplicadas: INT-03, INT-04, INT-01, INT-06",
    ):
        assert esperado in traza, esperado
    assert "1E+" not in traza and "e+" not in traza  # Decimal como cadena legible, sin exponente


def test_provisional_se_propaga(spec: dict, tablas: dict, unidad_a: dict) -> None:
    r = calcular(spec, unidad_a, tablas, provisional=True)
    assert r.provisional is True
    assert r.total == TOTAL_A
    assert any("provisional" in linea for linea in r.traza)


# --- precision --------------------------------------------------------------------------------------


def test_precision_global_alterada_no_afecta(spec: dict, tablas: dict, unidad_a: dict) -> None:
    previa = getcontext().prec
    getcontext().prec = 6
    try:
        r = calcular(spec, unidad_a, tablas)
        assert r.total == TOTAL_A
        assert a_dict(r)["total"] == "305829.6"
    finally:
        getcontext().prec = previa


# --- regla del menor h (docs/05 §4.3) ---------------------------------------------------------------


def test_regla_del_menor_h(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {"M1": _variante(h_despues=5000)}, tablas)
    u = r.por_unidad[0]
    assert u.derivadas["h"] == Decimal("5000")
    assert r.total == _formula_a("110", "1485", "1188", u.derivadas["p"], "5000")
    assert r.total != TOTAL_A


def test_cambiar_cual_es_el_menor_cambia_el_resultado(spec: dict, tablas: dict) -> None:
    menor_antes = calcular(spec, {"M1": _variante(h_antes=5000, h_despues=6000)}, tablas)
    menor_despues = calcular(spec, {"M1": _variante(h_antes=6000, h_despues=5000)}, tablas)
    iguales = calcular(spec, {"M1": _variante(h_antes=6000, h_despues=6000)}, tablas)
    assert menor_antes.total == menor_despues.total  # min es simetrico: 5000 en ambos
    assert menor_antes.por_unidad[0].derivadas["h"] == Decimal("5000")
    assert iguales.total == TOTAL_A
    assert menor_antes.total != iguales.total


# --- controles fisicos ------------------------------------------------------------------------------


def test_fis_02_retira_el_resultado(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {"M1": _variante(P_prom=200)}, tablas)
    assert r.controles_ok is False
    assert r.total is None
    assert r.total_cae is None
    u = r.por_unidad[0]
    assert u.controles["FIS-02"] is False
    assert u.controles["FIS-01"] is True
    assert u.salida is None
    assert u.motivo_no_calculo is not None and "FIS-02" in u.motivo_no_calculo
    assert "La potencia promedio con variador no puede superar la nominal." in u.motivo_no_calculo
    assert r.motivo_no_calculo is not None and "FIS-02" in r.motivo_no_calculo
    # la traza conserva los valores intermedios para el informe
    assert any("AEM = PM * (1 - (N2 / N1) ** 3) * (1 - p) * h = 305829.6" in linea for linea in r.traza)
    assert any("305829.6 retirado por FIS-02" in linea for linea in r.traza)


def test_fis_02_no_evaluable_sin_p_prom_no_retira(spec: dict, tablas: dict) -> None:
    valores = dict(CASO_A)
    del valores["P_prom"]
    r = calcular(spec, {"M1": valores}, tablas)
    assert r.por_unidad[0].controles["FIS-02"] is NO_EVALUABLE
    assert r.por_unidad[0].controles["FIS-01"] is True
    assert r.controles_ok is NO_EVALUABLE
    assert r.total == TOTAL_A
    assert r.total_cae == 305829


def test_fis_01_cumple_siempre_con_la_formula_real(spec: dict, tablas: dict) -> None:
    """Con N2 < N1 y 0 <= p < 1, `(1 - (N2/N1)**3) * (1 - p) < 1`, luego AEM < PM * h siempre: FIS-01 no
    puede fallar con la formula real y datos que pasen las precondiciones. Se comprueba que cumple en los
    extremos plausibles y el retiro se verifica con un control sintetico (test siguiente)."""
    for n2 in (Decimal("1"), Decimal("1484")):
        for h in (Decimal("1"), Decimal("8760")):
            r = calcular(spec, {"M1": _variante(N2=n2, h_antes=h, h_despues=h)}, tablas)
            assert r.por_unidad[0].controles["FIS-01"] is True
            assert r.total is not None


def test_fis_01_sintetico_retira_el_resultado(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    control = next(c for c in spec_mod["calculo"]["controles_fisicos"] if c["id"] == "FIS-01")
    control["regla"] = "AEM <= 1"
    r = calcular(spec_mod, unidad_a, tablas)
    assert r.por_unidad[0].controles["FIS-01"] is False
    assert r.controles_ok is False
    assert r.total is None and r.total_cae is None
    assert "FIS-01" in (r.motivo_no_calculo or "")
    assert any("305829.6 retirado por FIS-01" in linea for linea in r.traza)


# --- precondiciones ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cambios", "precondicion"),
    [
        ({"N2": 1485}, "N2 < N1"),
        ({"N2": 1500}, "N2 < N1"),
        ({"h_antes": 0}, "0 < h <= 8760"),
        ({"h_antes": 9000, "h_despues": 9000}, "0 < h <= 8760"),
    ],
)
def test_precondicion_fallida_no_calcula(spec: dict, tablas: dict, cambios: dict, precondicion: str) -> None:
    r = calcular(spec, {"M1": _variante(**cambios)}, tablas)
    u = r.por_unidad[0]
    assert u.precondiciones[precondicion] is False
    assert u.salida is None
    assert u.motivo_no_calculo == f"precondicion {precondicion!r} no se cumple"
    assert r.total is None and r.total_cae is None
    assert r.precondiciones_ok is False
    assert r.motivo_no_calculo is not None and precondicion in r.motivo_no_calculo
    assert not any("AEM =" in linea for linea in r.traza)


def test_precondicion_h_8760_es_limite_inclusivo(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {"M1": _variante(h_antes=8760, h_despues=8760)}, tablas)
    assert r.por_unidad[0].precondiciones["0 < h <= 8760"] is True
    assert r.total is not None


def test_precondicion_de_reglas_se_delega_con_nota(spec: dict, tablas: dict, unidad_a: dict) -> None:
    r = calcular(spec, unidad_a, tablas)
    assert r.precondiciones_delegadas == ["ninguna regla con severidad BLOQUEANTE fallida"]
    assert "ninguna regla con severidad BLOQUEANTE fallida" not in r.por_unidad[0].precondiciones
    assert any("la aplica reglas.py" in linea for linea in r.traza)
    # la comparacion encadenada la evalua el parser de forma nativa; ya no se reescribe el texto
    assert r.por_unidad[0].precondiciones["0 < h <= 8760"] is True


# --- varias unidades y truncado del total -----------------------------------------------------------


def test_dos_unidades_suma_exacta(spec: dict, tablas: dict) -> None:
    r = calcular(
        spec, {"M1": dict(CASO_A), "M2": _variante(PM=55, P_prom=30, h_antes=4000, h_despues=4500)}, tablas
    )
    assert [u.num_serie_motor for u in r.por_unidad] == ["M1", "M2"]
    salidas = [u.salida for u in r.por_unidad]
    assert all(s is not None for s in salidas)
    assert r.total == salidas[0] + salidas[1]
    m2 = r.por_unidad[1]
    assert m2.derivadas["perdidas_ref_kw"] == Decimal("3.12")
    assert m2.derivadas["h"] == Decimal("4000")
    assert m2.salida == _formula_a("55", "1485", "1188", m2.derivadas["p"], "4000")


def test_tres_unidades_con_menor_h_en_una(spec: dict, tablas: dict) -> None:
    unidades = {
        "M1": dict(CASO_A),
        "M2": _variante(PM=55, P_prom=30, h_antes=4000, h_despues=4500),
        "M3": _variante(PM=160, h_antes=7000, h_despues=6500),
    }
    r = calcular(spec, unidades, tablas)
    assert r.total == sum((u.salida for u in r.por_unidad), Decimal(0))
    assert r.por_unidad[2].derivadas["h"] == Decimal("6500")
    assert r.por_unidad[2].derivadas["perdidas_ref_kw"] == Decimal("8.82")
    assert sum(1 for linea in r.traza if "AEM = PM" in linea) == 3


def test_truncado_del_total_no_de_cada_unidad(spec: dict, tablas: dict) -> None:
    """Dos unidades como A: 305829.6 + 305829.6 = 611659.2 → 611659; truncar cada una daria 611658."""
    r = calcular(spec, {"M1": dict(CASO_A), "M2": dict(CASO_A)}, tablas)
    assert r.total == Decimal("611659.2")
    assert r.total_cae == 611659
    assert r.total_cae != sum(int(u.salida) for u in r.por_unidad)


def test_una_unidad_no_calculable_impide_el_total(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {"M1": dict(CASO_A), "M2": _variante(N2=1485)}, tablas)
    assert r.por_unidad[0].salida == TOTAL_A
    assert r.por_unidad[1].salida is None
    assert r.total is None
    assert r.motivo_no_calculo is not None and "unidad M2" in r.motivo_no_calculo


def test_sin_unidades(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {}, tablas)
    assert r.por_unidad == []
    assert r.total is None
    assert r.motivo_no_calculo == "sin unidades que calcular"
    assert r.controles_ok is NO_EVALUABLE and r.precondiciones_ok is NO_EVALUABLE


# --- tabla: INT-02, fuera de rango, vigencia --------------------------------------------------------


def test_int_02_interpolacion_sin_fila_exacta(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {"M1": _variante(PM=100)}, tablas)
    u = r.por_unidad[0]
    assert u.derivadas["perdidas_ref_kw"] == Decimal("5.29")  # 5.03 + (5.55 - 5.03) * (100 - 90) / (110 - 90)
    assert u.derivadas["p"] == _div("5.29", "100")
    assert "INT-02" in u.interpretaciones and "INT-02" in r.interpretaciones
    assert r.interpretaciones.index("INT-02") < r.interpretaciones.index("INT-01")
    assert any("INT-02" in aviso for aviso in r.avisos)
    assert any("pendiente de verificacion humana" in aviso for aviso in r.avisos)
    assert any("interpolado entre kw_motor = 90 y 110 (INT-02)" in linea for linea in r.traza)
    assert r.total == _formula_a("100", "1485", "1188", u.derivadas["p"], "6000")


def test_pm_fuera_de_rango_no_calcula(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {"M1": _variante(PM=5000)}, tablas)
    u = r.por_unidad[0]
    assert "perdidas_ref_kw" not in u.derivadas and "p" not in u.derivadas
    assert "p" not in u.fuentes
    assert u.salida is None
    assert u.motivo_no_calculo is not None and "fuera del rango" in u.motivo_no_calculo
    assert r.total is None and r.total_cae is None
    assert any("no se extrapola" in aviso for aviso in r.avisos)


def test_vigencia_de_tabla_solo_avisa(spec: dict, tablas: dict, unidad_a: dict) -> None:
    antes = calcular(spec, unidad_a, tablas, fecha=date(2019, 1, 1))
    assert antes.total == TOTAL_A
    assert any("no vigente en 2019-01-01" in aviso for aviso in antes.avisos)
    despues = calcular(spec, unidad_a, tablas, fecha=date(2026, 9, 18))
    assert despues.avisos == []


def test_tabla_no_cargada_es_error_de_carga(spec: dict, unidad_a: dict) -> None:
    with pytest.raises(ErrorCalculo, match=ID_TABLA):
        calcular(spec, unidad_a, {})


# --- p nunca de fuera de la tabla (trampa de la ficha del variador) ---------------------------------


@pytest.mark.parametrize("nombre", ["p", "perdidas_ref_kw", "h"])
def test_valor_derivable_suministrado_se_ignora(spec: dict, tablas: dict, nombre: str) -> None:
    valores = {**CASO_A, nombre: Decimal("0.0001")}
    r = calcular(spec, {"M1": valores}, tablas)
    u = r.por_unidad[0]
    assert r.total == TOTAL_A
    assert nombre not in u.entradas
    assert u.derivadas["p"] == P_A
    assert u.fuentes["p"] == ORIGEN_TABLA
    assert any(f"valor de {nombre} suministrado externamente ignorado" in aviso for aviso in r.avisos)


def test_p_de_la_ficha_del_variador_no_cambia_el_ahorro(spec: dict, tablas: dict) -> None:
    ficha_variador = {**CASO_A, "perdidas_ref_kw": Decimal("3.90"), "p": Decimal("3.90") / Decimal("110")}
    r = calcular(spec, {"M1": ficha_variador}, tablas)
    assert r.total == TOTAL_A
    assert r.por_unidad[0].derivadas["perdidas_ref_kw"] == Decimal("5.55")


# --- tipos de entrada -------------------------------------------------------------------------------


def test_float_en_entradas_es_error(spec: dict, tablas: dict) -> None:
    with pytest.raises(ErrorCalculo, match="float"):
        calcular(spec, {"M1": {**CASO_A, "PM": 110.0}}, tablas)


def test_bool_y_texto_en_entradas_es_error(spec: dict, tablas: dict) -> None:
    with pytest.raises(ErrorCalculo):
        calcular(spec, {"M1": {**CASO_A, "PM": True}}, tablas)
    with pytest.raises(ErrorCalculo):
        calcular(spec, {"M1": {**CASO_A, "PM": "110"}}, tablas)


def test_int_en_entradas_se_convierte(spec: dict, tablas: dict) -> None:
    r = calcular(spec, {"M1": {k: int(v) for k, v in CASO_A.items()}}, tablas)
    assert r.total == TOTAL_A
    assert all(isinstance(v, Decimal) for v in r.por_unidad[0].entradas.values())


def test_variable_ausente_en_la_formula(spec: dict, tablas: dict) -> None:
    valores = dict(CASO_A)
    del valores["N1"]
    r = calcular(spec, {"M1": valores}, tablas)
    u = r.por_unidad[0]
    assert u.salida is None
    assert u.motivo_no_calculo == "faltan variables para la formula: N1"
    assert u.precondiciones["N2 < N1"] is NO_EVALUABLE
    assert r.precondiciones_ok is NO_EVALUABLE
    assert r.total is None


# --- todo sale de la spec ---------------------------------------------------------------------------


def test_formula_de_la_spec_gobierna_el_calculo(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["calculo"]["motor"]["formula"] = "PM * h"
    r = calcular(spec_mod, unidad_a, tablas)
    assert r.total == Decimal("660000")
    assert r.total_cae == 660000


def test_derivacion_de_h_de_la_spec_gobierna(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["variables"]["h"]["derivacion"]["metodo"] = "h_despues"
    r = calcular(spec_mod, unidad_a, tablas)
    assert r.por_unidad[0].derivadas["h"] == Decimal("6200")


def test_funcion_desconocida_en_formula_es_error_de_carga(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["calculo"]["motor"]["formula"] = "raiz(PM) * h"
    with pytest.raises(ErrorCalculo, match="calculo.motor.formula"):
        calcular(spec_mod, unidad_a, tablas)


def test_control_no_compilable_es_error_de_carga(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["calculo"]["controles_fisicos"][0]["regla"] = "el ahorro es razonable"
    with pytest.raises(ErrorCalculo, match="FIS-01"):
        calcular(spec_mod, unidad_a, tablas)


def test_redondeo_no_soportado_es_error_de_carga(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["calculo"]["redondeo_salida"]["AETOTAL_cae"] = "redondear al kWh mas cercano"
    with pytest.raises(ErrorCalculo, match="redondeo"):
        calcular(spec_mod, unidad_a, tablas)


def test_sin_redondeo_declarado_no_publica_cae(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    del spec_mod["calculo"]["redondeo_salida"]
    r = calcular(spec_mod, unidad_a, tablas)
    assert r.total == TOTAL_A
    assert r.total_cae is None
    assert "INT-06" not in r.interpretaciones


def test_dependencias_circulares_es_error_de_carga(spec: dict, tablas: dict, unidad_a: dict) -> None:
    spec_mod = copy.deepcopy(spec)
    spec_mod["variables"]["h"]["derivacion"]["metodo"] = "min(h_antes, p)"
    spec_mod["variables"]["p"]["derivacion"]["metodo"] = "perdidas_ref_kw / h"
    with pytest.raises(ErrorCalculo, match="circulares"):
        calcular(spec_mod, unidad_a, tablas)


def test_orden_topologico_independiente_del_orden_de_la_spec(
    spec: dict, tablas: dict, unidad_a: dict
) -> None:
    spec_mod = copy.deepcopy(spec)
    variables = spec_mod["variables"]
    reordenadas = {k: variables[k] for k in ("p", "perdidas_ref_kw", "h")}
    reordenadas.update({k: v for k, v in variables.items() if k not in reordenadas})
    spec_mod["variables"] = reordenadas
    r = calcular(spec_mod, unidad_a, tablas)
    assert r.total == TOTAL_A
    assert r.por_unidad[0].fuentes["p"] == ORIGEN_TABLA


# --- serializacion ----------------------------------------------------------------------------------


def test_a_dict_serializa_decimal_como_cadena(spec: dict, tablas: dict, unidad_a: dict) -> None:
    valores = dict(CASO_A)
    del valores["P_prom"]
    r = calcular(spec, {"M1": valores}, tablas)
    d = a_dict(r)
    texto = json.dumps(d, ensure_ascii=False)
    assert d["total"] == "305829.6"
    assert d["total_cae"] == 305829
    assert d["por_unidad"][0]["derivadas"]["perdidas_ref_kw"] == "5.55"
    assert d["por_unidad"][0]["entradas"]["PM"] == "110"
    assert d["por_unidad"][0]["fuentes"]["p"] == ORIGEN_TABLA
    assert d["por_unidad"][0]["controles"]["FIS-02"] == "NO_EVALUABLE"
    assert d["controles_ok"] == "NO_EVALUABLE"
    assert d["precondiciones_delegadas"] == ["ninguna regla con severidad BLOQUEANTE fallida"]
    assert "Decimal(" not in texto
    assert isinstance(r, ResultadoCalculo)


# --- higiene del fuente ----------------------------------------------------------------------------


def test_fuente_sin_eval_ni_float_ni_nombres_de_la_ficha() -> None:
    fuente = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("eval(", "exec(", "compile(", "float(", "import ast", "from ast"):
        assert prohibido not in fuente, prohibido
    nombres_ficha = ("perdidas_ref_kw", "REG1781", "5.55", "110", "h_antes", "h_despues", "PM", "N1", "N2")
    for literal in nombres_ficha:
        assert f'"{literal}"' not in fuente, literal
    assert "IND240" not in fuente
    assert "if ficha" not in fuente


def test_engine_no_importa_de_fuera_del_nucleo() -> None:
    fuente = FUENTE.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+(agentes|salida|generator|tests)\b", fuente, re.MULTILINE)
