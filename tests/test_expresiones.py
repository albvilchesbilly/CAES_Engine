"""Tests de engine/expresiones.py: parser de lista blanca, trivaluacion y construcciones de la spec."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.expresiones import (
    FUNCIONES_PERMITIDAS,
    NO_EVALUABLE,
    ContextoDict,
    ErrorCargaExpresion,
    ErrorEvaluacionExpresion,
    Expresion,
    compilar,
)

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / "spec" / "IND240_v1.1.yaml"
FUENTE = RAIZ / "engine" / "expresiones.py"


@pytest.fixture(scope="module")
def spec() -> dict:
    with SPEC.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def ev(texto: str, datos: dict | None = None, modo: str = "logica") -> object:
    return compilar(texto, modo=modo).evaluar(ContextoDict(datos or {}))


# ---------------------------------------------------------------------------
# 1. Todo lo que hay en la spec compila
# ---------------------------------------------------------------------------


def test_las_26_logicas_de_la_spec_compilan(spec):
    reglas = spec["reglas"]
    assert len(reglas) == 26
    for regla in reglas:
        expr = compilar(regla["logica"], modo="logica")
        assert isinstance(expr, Expresion), regla["id"]
        assert expr.funciones <= FUNCIONES_PERMITIDAS


def test_formulas_y_controles_de_la_spec_compilan(spec):
    motor = compilar(spec["calculo"]["motor"]["formula"], modo="formula")
    assert motor.identificadores == {"PM", "N2", "N1", "p", "h"}
    total = compilar(spec["calculo"]["total"]["formula"], modo="formula")
    assert total.funciones == {"sum"} and total.identificadores == {"AEM"}
    h = compilar(spec["variables"]["h"]["derivacion"]["metodo"], modo="formula")
    assert h.funciones == {"min"} and h.identificadores == {"h_antes", "h_despues"}
    for control in spec["calculo"]["controles_fisicos"]:
        expr = compilar(control["regla"], modo="logica")
        assert "PM" in expr.identificadores, control["id"]


def test_identificadores_referenciados(spec):
    por_id = {r["id"]: r["logica"] for r in spec["reglas"]}
    assert compilar(por_id["R-CON-01"]).identificadores == {"PM.valores_por_fuente"}
    assert compilar(por_id["R-EVD-01"]).identificadores == {"registro.dias"}
    assert compilar(por_id["R-CAL-03"]).identificadores == {"FIS-01", "FIS-02"}
    assert compilar(por_id["R-AMB-01"]).identificadores == {
        "tipo_equipo_accionado",
        "ambito.tipos_equipo_incluidos",
    }
    # los nombres dentro de una lista literal son simbolicos: no son identificadores
    assert compilar(por_id["R-AMB-02"]).identificadores == {"factura.linea", "categoria"}
    assert compilar(por_id["R-DOC-02"]).identificadores == {"motor", "foto.antes", "foto.despues"}
    assert compilar(por_id["R-CAL-04"]).identificadores == {"p.fuente"}


# ---------------------------------------------------------------------------
# 2. Vocabulario cerrado: errores de CARGA, no de ejecucion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "foo(x)",
        "anio(fecha) == 2026",
        "unique_in_tenant(x)",
        "x +",
        "(a and b",
        "a < b < c",
        "x in",
        "for each motor",
        "[a, b] where c",
        "x == $y",
        "min(a)",
        "count(a, b)",
        "not",
        "",
    ],
)
def test_construccion_desconocida_es_error_de_carga(texto):
    with pytest.raises(ErrorCargaExpresion):
        compilar(texto)


def test_modo_desconocido_es_error_de_carga():
    with pytest.raises(ErrorCargaExpresion):
        compilar("a == b", modo="python")


def test_potencia_solo_en_formula():
    with pytest.raises(ErrorCargaExpresion):
        compilar("(N2 / N1) ** 3 < 1", modo="logica")
    assert ev("2 ** 3", modo="formula") == Decimal(8)


# ---------------------------------------------------------------------------
# 3. Sin eval en el fuente
# ---------------------------------------------------------------------------


def test_el_fuente_no_usa_eval_exec_compile_ni_ast():
    fuente = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("eval(", "exec(", "compile(", "import ast", "from ast", "literal_eval"):
        assert prohibido not in fuente, prohibido


def test_engine_no_importa_de_agentes_ni_salida():
    fuente = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("agentes", "salida", "generator", "tests"):
        assert f"from {prohibido}" not in fuente and f"import {prohibido}" not in fuente


# ---------------------------------------------------------------------------
# 4. Trivaluacion
# ---------------------------------------------------------------------------

V, F, N = True, False, NO_EVALUABLE
CTX3 = {"v": True, "f": False}  # `n` no esta: resuelve a NO_EVALUABLE


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("v and v", V),
        ("v and f", F),
        ("f and n", F),
        ("n and f", F),
        ("v and n", N),
        ("n and n", N),
        ("v or f", V),
        ("n or v", V),
        ("f or f", F),
        ("f or n", N),
        ("n or n", N),
        ("not v", F),
        ("not f", V),
        ("not n", N),
        ("v -> v", V),
        ("v -> f", F),
        ("f -> n", V),
        ("n -> v", V),
        ("v -> n", N),
        ("n -> f", N),
        ("n and f or v", V),
        ("not (n or v)", F),
    ],
)
def test_tabla_de_verdad_trivaluada(texto, esperado):
    assert ev(texto, CTX3) is esperado


def test_no_evaluable_es_un_centinela_unico():
    assert NO_EVALUABLE is not None and NO_EVALUABLE is not True and NO_EVALUABLE is not False
    assert repr(NO_EVALUABLE) == "NO_EVALUABLE"
    with pytest.raises(TypeError):
        bool(NO_EVALUABLE)


def test_operando_logico_no_booleano_es_error_de_contexto():
    with pytest.raises(ErrorEvaluacionExpresion):
        ev("a and b", {"a": "si", "b": True})


# ---------------------------------------------------------------------------
# 5. Construcciones, una a una, con contexto en memoria
# ---------------------------------------------------------------------------


def test_unique_sobre_dict_de_valores_por_fuente():
    logica = "unique(PM.valores_por_fuente)"
    assert (
        ev(logica, {"PM": {"valores_por_fuente": {"ficha_tecnica_motor": "110", "certificado": "110"}}})
        is True
    )
    assert (
        ev(logica, {"PM": {"valores_por_fuente": {"ficha_tecnica_motor": "110", "certificado": "90"}}})
        is False
    )
    assert ev(logica, {"PM": {"valores_por_fuente": {"ficha_tecnica_motor": "110"}}}) is True
    assert ev(logica, {"PM": {"valores_por_fuente": {}}}) is NO_EVALUABLE
    assert ev(logica, {"PM": {"valores_por_fuente": {"a": None, "b": "110"}}}) is True
    assert ev(logica, {}) is NO_EVALUABLE
    assert ev("unique(x)", {"x": ["S1", "S1", "S1"]}) is True
    assert ev("unique(x)", {"x": ["S1", "S2"]}) is False
    assert ev("unique(x)", {"x": "S1"}) is True  # escalar: un solo valor
    # no aplica tolerancias: 110 y 110.5 son distintos
    assert ev("unique(x)", {"x": [Decimal("110"), Decimal("110.5")]}) is False


def test_unique_and_unique():
    logica = "unique(num_serie_variador) and unique(num_serie_motor)"
    assert ev(logica, {"num_serie_variador": ["V1", "V1"], "num_serie_motor": ["M1", "M1"]}) is True
    assert ev(logica, {"num_serie_variador": ["V1", "V2"], "num_serie_motor": ["M1", "M1"]}) is False
    assert ev(logica, {"num_serie_variador": ["V1", "V1"]}) is NO_EVALUABLE


def test_exists_con_where_y_lista_de_la_spec(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-AMB-02")
    solo_variador = {"factura": {"linea": [{"categoria": "variador"}, {"categoria": "instalacion"}]}}
    con_motor = {"factura": {"linea": [{"categoria": "variador"}, {"categoria": "motor"}]}}
    assert ev(logica, solo_variador) is True
    assert ev(logica, con_motor) is False
    assert ev(logica, {"factura": {"linea": []}}) is True
    assert ev(logica, {}) is NO_EVALUABLE
    # una linea sin categoria y ninguna que coincida: no se puede afirmar nada
    assert ev(logica, {"factura": {"linea": [{"descripcion": "x"}]}}) is NO_EVALUABLE
    # una linea sin categoria pero otra que coincide: existe, luego falla
    assert ev(logica, {"factura": {"linea": [{"descripcion": "x"}, {"categoria": "bomba"}]}}) is False


def test_where_no_resuelve_motor_como_coleccion_dentro_de_la_lista():
    # `motor` es tambien el nombre de la coleccion de unidades: dentro de [..] es literal simbolico
    datos = {"motor": [{"n": 1}], "factura": {"linea": [{"categoria": "motor"}]}}
    assert ev("exists(factura.linea where categoria in [motor, bomba])", datos) is True


def test_all_con_implicacion_y_presente(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-DOC-01")
    docs = [
        {"id": "DOC-01", "tipo": "ficha_cumplimentada", "obligatorio": True},
        {"id": "EVD-01", "tipo": "registro_funcionamiento", "obligatorio": True},
        {"id": "EVD-04", "tipo": "ficha_tecnica_variador", "obligatorio": False},
        {"id": "DOC-05B", "tipo": "certificado_tecnico_competente", "obligatorio": "condicional"},
    ]

    def contexto(presentes: set[str]) -> dict:
        return {"doc": docs, "presente": lambda d: d["tipo"] in presentes}

    assert ev(logica, contexto({"ficha_cumplimentada", "registro_funcionamiento"})) is True
    assert ev(logica, contexto({"ficha_cumplimentada"})) is False
    assert ev(logica, {"doc": docs}) is NO_EVALUABLE  # sin funcion presente en el contexto
    assert ev(logica, {}) is NO_EVALUABLE
    assert ev(logica, {"doc": [], "presente": lambda d: False}) is True  # vacuo
    # `presente` como atributo del elemento
    assert ev(logica, {"doc": [{"obligatorio": True, "presente": True}]}) is True
    assert ev(logica, {"doc": [{"obligatorio": True, "presente": False}]}) is False


def test_all_requisito_in_convenio_cae(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-DOC-04")
    requisitos = spec["documentacion"][-1]["requisitos"]
    assert ev(logica, {"requisito": requisitos, "convenio_cae": list(requisitos)}) is True
    assert ev(logica, {"requisito": requisitos, "convenio_cae": requisitos[:-1]}) is False
    assert ev(logica, {"requisito": requisitos}) is NO_EVALUABLE
    assert ev(logica, {"convenio_cae": requisitos}) is NO_EVALUABLE


def test_exists_con_predicado_ligado_a_filas_de_tabla(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-CAL-02")
    filas = [{"kw_motor": Decimal("90"), "perdidas_ref_kw": Decimal("4.5")}, {"kw_motor": Decimal("110")}]
    assert ev(logica, {"REG1781_CUADRO6": filas, "PM": Decimal("110")}) is True
    assert ev(logica, {"REG1781_CUADRO6": filas, "PM": Decimal("100")}) is False
    assert ev(logica, {"REG1781_CUADRO6": filas}) is NO_EVALUABLE
    assert ev(logica, {"PM": Decimal("110")}) is NO_EVALUABLE
    # tambien como proyeccion coleccion.atributo
    assert ev(logica, {"REG1781_CUADRO6": {"kw_motor": [Decimal("90"), Decimal("110")]}, "PM": 110}) is True


def test_for_each_motor(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-DOC-02")
    ok = {"foto": {"antes": ["f1"], "despues": ["f2"]}}
    sin_despues = {"foto": {"antes": ["f1"], "despues": []}}
    plano = {"foto.antes": ["f1", "f3"], "foto.despues": ["f2"]}
    assert ev(logica, {"motor": [ok, plano]}) is True
    assert ev(logica, {"motor": [ok, sin_despues]}) is False
    assert ev(logica, {"motor": [ok, {"foto": {"antes": ["f1"]}}]}) is NO_EVALUABLE
    assert ev(logica, {"motor": [sin_despues, {"foto": {"antes": ["f1"]}}]}) is False
    assert ev(logica, {"motor": []}) is NO_EVALUABLE
    assert ev(logica, {}) is NO_EVALUABLE


def test_in_con_lista_de_la_spec(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-AMB-01")
    incluidos = spec["ambito"]["tipos_equipo_incluidos"]
    ctx = {"ambito": {"tipos_equipo_incluidos": incluidos}}
    assert ev(logica, {**ctx, "tipo_equipo_accionado": "bomba_dinamica"}) is True
    assert ev(logica, {**ctx, "tipo_equipo_accionado": "bomba_desplazamiento_positivo"}) is False
    assert ev(logica, ctx) is NO_EVALUABLE
    assert ev(logica, {"tipo_equipo_accionado": "bomba_dinamica"}) is NO_EVALUABLE


def test_in_con_lista_literal_de_numeros_y_cadenas():
    assert ev("x in [1, 2, 3]", {"x": Decimal("2")}) is True
    assert ev("x in [1, 2, 3]", {"x": 4}) is False
    assert ev('x in ["a", b]', {"x": "b"}) is True


def test_suma_de_anios_a_fecha(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-TMP-03")
    fin = date(2026, 3, 2)
    assert ev(logica, {"solicitud": {"fecha": date(2029, 3, 2)}, "fecha_fin_actuacion": fin}) is True
    assert ev(logica, {"solicitud": {"fecha": date(2029, 3, 3)}, "fecha_fin_actuacion": fin}) is False
    assert ev(logica, {"fecha_fin_actuacion": fin}) is NO_EVALUABLE
    assert ev("f + 1 año", {"f": date(2024, 2, 29)}, modo="formula") == date(2025, 2, 28)
    assert ev("f + 3 meses", {"f": date(2026, 11, 30)}, modo="formula") == date(2027, 2, 28)
    assert ev("f + 30 dias", {"f": date(2026, 1, 1)}, modo="formula") == date(2026, 1, 31)
    assert ev("f - 1 años", {"f": date(2026, 1, 1)}, modo="formula") == date(2025, 1, 1)


def test_comparacion_de_fechas(spec):
    por_id = {r["id"]: r["logica"] for r in spec["reglas"]}
    assert (
        ev(
            por_id["R-TMP-01"],
            {"fecha_inicio_actuacion": date(2026, 1, 1), "fecha_fin_actuacion": date(2026, 3, 2)},
        )
        is True
    )
    assert (
        ev(
            por_id["R-TMP-01"],
            {"fecha_inicio_actuacion": date(2026, 4, 1), "fecha_fin_actuacion": date(2026, 3, 2)},
        )
        is False
    )
    assert (
        ev(
            por_id["R-EVD-02"],
            {"registro": {"inicio": date(2026, 3, 5)}, "fecha_fin_actuacion": date(2026, 3, 2)},
        )
        is True
    )
    assert ev(por_id["R-EVD-02"], {"registro": {"inicio": date(2026, 3, 5)}}) is NO_EVALUABLE


def test_abs_de_diferencia_con_decimal(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-CON-03")
    assert ev(logica, {"N2": {"declarado": Decimal("1188"), "derivado": Decimal("1188.7")}}) is True
    assert ev(logica, {"N2": {"declarado": Decimal("1188"), "derivado": Decimal("1186.9")}}) is False
    assert ev(logica, {"N2": {"declarado": Decimal("1190"), "derivado": Decimal("1189")}}) is True
    assert ev(logica, {"N2": {"declarado": Decimal("1188")}}) is NO_EVALUABLE
    assert ev(logica, {"N2": {"declarado": Decimal("1188"), "derivado": None}}) is NO_EVALUABLE
    assert ev("abs(a - b)", {"a": Decimal("1"), "b": Decimal("3.5")}, modo="formula") == Decimal("2.5")


def test_float_en_el_contexto_es_defecto_no_silencio():
    with pytest.raises(ErrorEvaluacionExpresion):
        ev("abs(a - b) <= 1", {"a": 1188.0, "b": Decimal("1188")})


def test_sha256(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-EVD-03")
    datos = "ts;rpm;kw\n1;1188;95.1\n"
    huella = hashlib.sha256(datos.encode("utf-8")).hexdigest()
    assert ev(logica, {"registro": {"hash_declarado": huella, "datos_canonicos": datos}}) is True
    assert ev(logica, {"registro": {"hash_declarado": huella, "datos_canonicos": datos.encode()}}) is True
    assert ev(logica, {"registro": {"hash_declarado": "0" * 64, "datos_canonicos": datos}}) is False
    assert ev(logica, {"registro": {"hash_declarado": huella}}) is NO_EVALUABLE


def test_identificadores_con_guion(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-CAL-03")
    assert logica == "FIS-01 and FIS-02"
    assert ev(logica, {"FIS-01": True, "FIS-02": True}) is True
    assert ev(logica, {"FIS-01": True, "FIS-02": False}) is False
    assert ev(logica, {"FIS-01": True}) is NO_EVALUABLE
    assert ev("R-CON-01 or R-CON-02", {"R-CON-01": False, "R-CON-02": True}) is True
    # con espacios, o con minusculas, el guion es una resta
    assert ev("a - b", {"a": Decimal(5), "b": Decimal(2)}, modo="formula") == Decimal(3)
    assert ev("PM - N1", {"PM": Decimal(5), "N1": Decimal(2)}, modo="formula") == Decimal(3)
    assert ev("PM-1", {"PM": Decimal(5)}, modo="formula") is NO_EVALUABLE  # `PM-1` es un identificador
    assert compilar("PM-1").identificadores == {"PM-1"}


def test_literal_de_origen_tabla(spec):
    logica = next(r["logica"] for r in spec["reglas"] if r["id"] == "R-CAL-04")
    assert ev(logica, {"p": {"fuente": "tabla:REG1781_CUADRO6"}}) is True
    assert ev(logica, {"p": {"fuente": "ficha_tecnica_variador"}}) is False
    assert ev(logica, {}) is NO_EVALUABLE
    assert compilar(logica).identificadores == {"p.fuente"}


def test_enumerado_sin_comillas_en_lado_derecho(spec):
    por_id = {r["id"]: r["logica"] for r in spec["reglas"]}
    assert ev(por_id["R-EVD-04"], {"N2": {"evidencia": "derivado"}}) is True
    assert ev(por_id["R-EVD-04"], {"N2": {"evidencia": "declarado"}}) is False
    assert ev(por_id["R-EVD-04"], {}) is NO_EVALUABLE
    assert ev(por_id["R-AMB-03"], {"regimen_previo": "constante_sin_modulacion"}) is True
    assert ev(por_id["R-AMB-03"], {"regimen_previo": "con_modulacion"}) is False
    assert ev(por_id["R-AMB-03"], {}) is NO_EVALUABLE
    # el lado derecho se resuelve si existe en el contexto; solo si falta es simbolico
    assert ev("a == b", {"a": "x", "b": "x"}) is True
    assert ev("a == b", {"a": "b"}) is True
    assert ev("a != b", {"a": "c"}) is True
    # si el lado izquierdo no es texto, el nombre ausente no es un enumerado: NO_EVALUABLE
    assert ev("a == b", {"a": Decimal(1)}) is NO_EVALUABLE
    assert ev("a == b", {"a": True}) is NO_EVALUABLE
    # fuera de ==/!= un nombre ausente es NO_EVALUABLE, no un literal
    assert ev("a < b", {"a": Decimal(1)}) is NO_EVALUABLE
    assert ev("b == a", {"a": "b"}) is NO_EVALUABLE  # solo el lado derecho


def test_predicados_como_atributo(spec):
    por_id = {r["id"]: r["logica"] for r in spec["reglas"]}
    assert ev(por_id["R-DOC-03"], {"factura": {"campos_minimos_presentes": True}}) is True
    assert ev(por_id["R-DOC-03"], {"factura": {"campos_minimos_presentes": False}}) is False
    assert ev(por_id["R-DOC-03"], {"factura": {}}) is NO_EVALUABLE
    assert ev(por_id["R-DOC-05"], {"ficha_cumplimentada": {"firmada": True}}) is True
    assert ev(por_id["R-DOC-05"], {"ficha_cumplimentada": {"firmada": False}}) is False


def test_comparadores_numericos(spec):
    por_id = {r["id"]: r["logica"] for r in spec["reglas"]}
    assert ev(por_id["R-EVD-01"], {"registro": {"dias": 35}}) is True
    assert ev(por_id["R-EVD-01"], {"registro": {"dias": Decimal("29.5")}}) is False
    assert ev(por_id["R-EVD-01"], {"registro": {}}) is NO_EVALUABLE
    assert ev(por_id["R-CAL-01"], {"N2": Decimal(1188), "N1": Decimal(1485)}) is True
    assert ev(por_id["R-CAL-01"], {"N2": Decimal(1485), "N1": Decimal(1485)}) is False
    assert (
        ev(por_id["R-CON-06"], {"convenio": {"ahorro_kwh": Decimal(305829)}, "AETOTAL_cae": 305829}) is True
    )
    assert (
        ev(por_id["R-CON-06"], {"convenio": {"ahorro_kwh": Decimal(305000)}, "AETOTAL_cae": 305829}) is False
    )
    assert ev(por_id["R-CON-06"], {"convenio": {"ahorro_kwh": Decimal(305829)}}) is NO_EVALUABLE
    assert ev("a == b", {"a": Decimal("110"), "b": "110.0"}) is True  # texto numerico se coerciona


def test_controles_fisicos(spec):
    controles = {c["id"]: c["regla"] for c in spec["calculo"]["controles_fisicos"]}
    ctx = {"AEM": Decimal("305829.6"), "PM": Decimal(110), "h": Decimal(6000), "P_prom": Decimal("95.1")}
    assert ev(controles["FIS-01"], ctx) is True
    assert ev(controles["FIS-02"], ctx) is True
    assert ev(controles["FIS-01"], {**ctx, "AEM": Decimal(700000)}) is False
    assert ev(controles["FIS-02"], {**ctx, "P_prom": Decimal(111)}) is False
    assert ev(controles["FIS-02"], {"PM": Decimal(110)}) is NO_EVALUABLE


def test_count_sum_min():
    assert ev("count(x)", {"x": []}, modo="formula") == 0
    assert ev("count(x)", {"x": ["a", "b"]}, modo="formula") == 2
    assert ev("count(x)", {}, modo="formula") is NO_EVALUABLE
    assert ev("count(x)", {"x": {"a": 1}}, modo="formula") == 1
    assert ev("count(fila.v > 1)", {"fila": [{"v": 2}, {"v": 0}, {"v": 5}]}, modo="formula") == 2
    assert ev("count(fila.v > 1)", {"fila": [{"v": 2}, {}]}, modo="formula") is NO_EVALUABLE
    assert ev("sum(AEM)", {"AEM": [Decimal("1.5"), 2]}, modo="formula") == Decimal("3.5")
    assert ev("sum(AEM)", {"AEM": []}, modo="formula") == Decimal(0)
    assert ev("sum(AEM)", {"AEM": [Decimal(1), None]}, modo="formula") is NO_EVALUABLE
    assert ev(
        "min(h_antes, h_despues)", {"h_antes": Decimal(6000), "h_despues": Decimal(6100)}, modo="formula"
    ) == Decimal(6000)
    assert ev("min(h_antes, h_despues)", {"h_antes": Decimal(6000)}, modo="formula") is NO_EVALUABLE
    assert ev("min(a, b, c)", {"a": 3, "b": 1, "c": 2}, modo="formula") == Decimal(1)
    assert ev("exists(x)", {"x": []}) is False
    assert ev("exists(x)", {"x": [1]}) is True
    assert ev("all(x)", {"x": [True, True]}) is True
    assert ev("all(x)", {"x": [True, False]}) is False


def test_formula_ind240_caso_a_con_decimal(spec):
    formula = spec["calculo"]["motor"]["formula"]
    ctx = {
        "PM": Decimal("110"),
        "N1": Decimal("1485"),
        "N2": Decimal("1188"),
        "p": Decimal("5.55") / Decimal("110"),
        "h": Decimal("6000"),
    }
    resultado = ev(formula, ctx, modo="formula")
    assert isinstance(resultado, Decimal)
    assert resultado == Decimal("305829.6")
    assert resultado.quantize(Decimal("0.1")) == Decimal("305829.6")
    assert str(resultado).startswith("305829.6")
    assert ev(formula, {k: v for k, v in ctx.items() if k != "h"}, modo="formula") is NO_EVALUABLE


def test_formula_no_produce_float():
    r = ev("(a / b) * c", {"a": Decimal(1), "b": Decimal(3), "c": 3}, modo="formula")
    assert isinstance(r, Decimal)
    assert ev("-a + 2", {"a": Decimal(1)}, modo="formula") == Decimal(1)
    assert ev("0.5 * 4", modo="formula") == Decimal(2)
    with pytest.raises(ErrorEvaluacionExpresion):
        ev("a / b", {"a": Decimal(1), "b": Decimal(0)}, modo="formula")


def test_precedencia():
    assert ev("1 + 2 * 3", modo="formula") == Decimal(7)
    assert ev("(1 + 2) * 3", modo="formula") == Decimal(9)
    assert ev("2 ** 3 ** 2", modo="formula") == Decimal(512)
    assert ev("-2 ** 2", modo="formula") == Decimal(-4)
    assert ev("not a == b", {"a": 1, "b": 2}) is True
    assert ev("a or b and c", {"a": False, "b": True, "c": True}) is True
    assert ev("a -> b -> c", {"a": True, "b": True, "c": False}) is False


def test_cadenas_con_comillas():
    assert ev('x == "constante sin modulacion"', {"x": "constante sin modulacion"}) is True
    assert ev("x == 'a'", {"x": "a"}) is True


# ---------------------------------------------------------------------------
# 6. Ausencias: NO_EVALUABLE, nunca excepcion
# ---------------------------------------------------------------------------


def test_identificador_ausente_es_no_evaluable_en_todas_las_posiciones(spec):
    for regla in spec["reglas"]:
        assert compilar(regla["logica"]).evaluar(ContextoDict({})) is NO_EVALUABLE, regla["id"]
    assert ev("abs(x)", modo="formula") is NO_EVALUABLE
    assert ev("x + 1", modo="formula") is NO_EVALUABLE
    assert ev("sha256(x) == y") is NO_EVALUABLE
    assert ev("x in y") is NO_EVALUABLE
    assert ev("unique(x)") is NO_EVALUABLE
    assert ev("f + 3 años <= g", {"g": date(2030, 1, 1)}) is NO_EVALUABLE


def test_valor_none_en_el_contexto_es_ausencia():
    assert ev("x < 30", {"x": None}) is NO_EVALUABLE
    assert ev("registro.dias >= 30", {"registro": None}) is NO_EVALUABLE


def test_contexto_con_objetos_y_dataclasses():
    from dataclasses import dataclass

    @dataclass
    class Dato:
        valores_por_fuente: dict
        evidencia: str

    ctx = {"PM": Dato({"a": "110", "b": "110"}, "demostrado"), "N2": Dato({}, "derivado")}
    assert ev("unique(PM.valores_por_fuente)", ctx) is True
    assert ev("N2.evidencia == derivado", ctx) is True
    assert ev("N2.valor", ctx) is NO_EVALUABLE


def test_contexto_personalizado_con_protocolo():
    class Ctx:
        def resolver(self, nombre: str) -> object:
            return {"a": Decimal(2)}.get(nombre, NO_EVALUABLE)

    assert compilar("a * 2", modo="formula").evaluar(Ctx()) == Decimal(4)
    assert compilar("a == b").evaluar(Ctx()) is NO_EVALUABLE  # a es Decimal: b no es un enumerado
    assert compilar("b == a").evaluar(Ctx()) is NO_EVALUABLE
