"""F0.4: Spec Registry (docs/04 §2, §3, §5.2; docs/03 §14.b/c; ADR-002 §2.4).

Carga de la spec activa, rechazo de `spec/propuestas/`, validacion de campos y valores por defecto,
derivacion de `fase` y `nivel` sin ids en codigo, enumerados del parser, garantia NO_EVALUABLE → SUBSANABLE,
hashes, tablas y versiones.
"""

from __future__ import annotations

import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
import yaml

from engine import spec_registry
from engine.expresiones import Expresion
from engine.spec_registry import (
    AVISO_VIGENCIA_NO_DECIDIDA,
    FASES,
    ErrorCargaSpec,
    Regla,
    Spec,
    SpecRegistry,
    Vigencia,
    cargar_spec,
    clave_version,
    hash_canonico,
    raiz_de,
)

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_SPEC = RAIZ / "spec"
SPEC_ACTIVA = CARPETA_SPEC / "IND240_v1.1.yaml"
PROPUESTAS = CARPETA_SPEC / "propuestas"
FUENTE = RAIZ / "engine" / "spec_registry.py"

# docs/04 §5.2: asignacion regla a regla (decision de diseño de la Fase 0). Se reproduce por derivacion.
FASE_ESPERADA = {
    "R-AMB-01": "ambito",
    "R-AMB-02": "ambito",
    "R-AMB-03": "ambito",
    "R-CON-01": "consistencia",
    "R-CON-02": "consistencia",
    "R-CON-03": "consistencia",
    "R-CON-04": "consistencia",
    "R-CON-05": "consistencia",
    "R-CON-07": "consistencia",
    "R-TMP-01": "consistencia",
    "R-CAL-01": "consistencia",
    "R-CAL-02": "consistencia",
    "R-CAL-04": "consistencia",
    "R-CAL-03": "post_calculo",
    "R-CON-06": "post_calculo",
    "R-DOC-01": "resto",
    "R-DOC-02": "resto",
    "R-DOC-03": "resto",
    "R-DOC-04": "resto",
    "R-DOC-05": "resto",
    "R-EVD-01": "resto",
    "R-EVD-02": "resto",
    "R-EVD-03": "resto",
    "R-EVD-04": "resto",
    "R-TMP-02": "resto",
    "R-TMP-03": "resto",
}
# ADR-002 §2.4: reglas de nivel motor (una evaluacion por unidad).
NIVEL_UNIDAD_ESPERADO = {
    "R-CON-01",
    "R-CON-02",
    "R-CON-03",
    "R-CON-04",
    "R-CAL-01",
    "R-CAL-02",
    "R-CAL-03",
    "R-CAL-04",
    "R-EVD-01",
    "R-EVD-02",
    "R-EVD-03",
    "R-EVD-04",
    "R-DOC-02",
    "R-AMB-01",
    "R-AMB-03",
}


# ---------------------------------------------------------------------------
# Utilidades: specs en memoria escritas en tmp_path
# ---------------------------------------------------------------------------


def spec_minima() -> dict:
    """Spec sintetica minima y valida: dos variables, un calculo, dos documentos, dos reglas."""
    return {
        "spec": {"id": "FICHA", "version_ficha": "1.0", "version_spec": "0.1.0"},
        "ambito": {"tipos_incluidos": ["equipo_a", "equipo_b"]},
        "variables": {
            "X": {
                "nivel": "motor",
                "tipo": "decimal",
                "evidencia": "demostrado",
                "fuentes": ["doc_opcional"],
            },
            "Y": {
                "nivel": "expediente",
                "tipo": "decimal",
                "evidencia": "demostrado",
                "fuentes": ["doc_obligatorio"],
            },
        },
        "calculo": {
            "motor": {"salida": "S", "formula": "X * Y"},
            "total": {"salida": "T", "formula": "sum(S)"},
            # el registro valida el bloque con `calculo.planificar` (ADR-002 §3, QA-2): la spec activa
            # debe ser calculable, asi que la minima declara tambien aritmetica y redondeo
            "aritmetica": "decimal_exacta",
            "redondeo_salida": {"T_cae": "truncar a kWh entero"},
        },
        "documentacion": [
            {"id": "D-01", "tipo": "doc_obligatorio", "obligatorio": True},
            {"id": "D-02", "tipo": "doc_opcional", "obligatorio": False},
        ],
        "reglas": [
            {
                "id": "R-PRE-01",
                "descripcion": "Presencia documental",
                "logica": "all(doc.obligatorio == true -> presente(doc))",
                "severidad": "SUBSANABLE",
            },
            {
                "id": "R-BLQ-01",
                "descripcion": "Y positivo",
                "logica": "Y > 0",
                "severidad": "BLOQUEANTE_DATOS",
            },
        ],
        "estados": {
            "orden_evaluacion": ["NO_ELEGIBLE", "BLOQUEADO", "SUBSANABLE", "PREVALIDADO"],
            "NO_ELEGIBLE": {"calcula": False},
            "BLOQUEADO": {"calcula": False},
            "SUBSANABLE": {"calcula": "provisional"},
            "PREVALIDADO": {"calcula": True},
        },
        "interpretaciones": [],
    }


def escribir(carpeta: Path, datos: dict, nombre: str | None = None) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre or f"{datos['spec']['id']}_v{datos['spec']['version_ficha']}.yaml"
    ruta = carpeta / nombre
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ruta


def cargar(tmp_path: Path, datos: dict, nombre: str | None = None) -> Spec:
    return cargar_spec(escribir(tmp_path / "spec", datos, nombre), raiz_datos=RAIZ)


def activa_modificada(tmp_path: Path, modificar) -> Spec:
    """Copia la spec activa a tmp, aplica `modificar(datos)` y la carga (las tablas se leen de RAIZ/data)."""
    with SPEC_ACTIVA.open(encoding="utf-8") as fh:
        datos = yaml.safe_load(fh)
    modificar(datos)
    return cargar(tmp_path, datos)


def regla_activa(datos: dict, id_regla: str) -> dict:
    return next(r for r in datos["reglas"] if r["id"] == id_regla)


# ---------------------------------------------------------------------------
# 1. Carga de la spec activa
# ---------------------------------------------------------------------------


def test_carga_la_spec_activa_con_26_reglas(spec_ind240: Spec) -> None:
    assert spec_ind240.codigo == "IND240"
    assert spec_ind240.version_ficha == "1.1"
    assert spec_ind240.version_spec == "0.1.0"
    assert spec_ind240.ruta == SPEC_ACTIVA
    assert len(spec_ind240.reglas) == 26
    assert len(set(spec_ind240.ids_reglas)) == 26
    assert all(isinstance(r, Regla) and isinstance(r.expresion, Expresion) for r in spec_ind240.reglas)
    assert all(r.expresion.modo == "logica" for r in spec_ind240.reglas)
    assert spec_ind240.datos["spec"]["id"] == "IND240"
    assert set(spec_ind240.variables) >= {"PM", "N1", "N2", "h", "p", "perdidas_ref_kw"}
    assert [i["id"] for i in spec_ind240.interpretaciones] == [f"INT-0{n}" for n in range(1, 8)]
    assert spec_ind240.vigencia is None  # la activa no declara vigencia (docs/04 §2.4)


def test_regla_por_id_y_reglas_por_fase(spec_ind240: Spec) -> None:
    assert spec_ind240.regla("R-CON-01").severidad == "BLOQUEANTE_DATOS"
    with pytest.raises(KeyError):
        spec_ind240.regla("R-XXX-99")
    por_fase = spec_ind240.reglas_por_fase()
    assert list(por_fase) == list(FASES)
    assert por_fase["cabecera"] == []
    assert sum(len(v) for v in por_fase.values()) == 26
    assert [r.id for r in por_fase["post_calculo"]] == ["R-CON-06", "R-CAL-03"]


def test_variables_nivel_y_documentos_obligatorios(spec_ind240: Spec) -> None:
    unidad = spec_ind240.variables_nivel("unidad")
    assert set(unidad) == set(spec_ind240.variables_nivel("motor"))
    assert {"PM", "N1", "N2", "h"} <= set(unidad)
    actuacion = spec_ind240.variables_nivel("actuacion")
    assert set(actuacion) == {
        "titular_nif",
        "titular_razon_social",
        "fecha_inicio_actuacion",
        "fecha_fin_actuacion",
    }
    assert set(actuacion) == set(spec_ind240.variables_nivel("expediente"))
    assert spec_ind240.variables_nivel("grupo") == {}
    obligatorios = spec_ind240.documentos_obligatorios()
    assert all(d["obligatorio"] is True for d in obligatorios)
    tipos = {d["tipo"] for d in obligatorios}
    assert "registro_funcionamiento" in tipos and "ficha_tecnica_motor" in tipos
    assert "ficha_tecnica_variador" not in tipos  # obligatorio: false
    assert "certificado_tecnico_competente" not in tipos  # obligatorio: condicional (se resuelve al evaluar)
    assert spec_ind240.interpretacion("INT-02")["impacto"] == "bajo"
    with pytest.raises(KeyError):
        spec_ind240.interpretacion("INT-99")


def test_expresiones_del_calculo_y_precondiciones(spec_ind240: Spec) -> None:
    claves = set(spec_ind240.expresiones_calculo)
    assert {"calculo.motor.formula", "calculo.total.formula"} <= claves
    assert {"calculo.controles_fisicos.FIS-01", "calculo.controles_fisicos.FIS-02"} <= claves
    assert {"variables.h.derivacion.metodo", "variables.p.derivacion.metodo"} <= claves
    assert spec_ind240.expresiones_calculo["calculo.motor.formula"].modo == "formula"
    assert spec_ind240.expresiones_calculo["calculo.motor.formula"].identificadores == {
        "PM",
        "N2",
        "N1",
        "p",
        "h",
    }
    assert spec_ind240.expresiones_calculo["calculo.controles_fisicos.FIS-01"].modo == "logica"
    assert spec_ind240.expresiones_calculo["variables.h.derivacion.metodo"].identificadores == {
        "h_antes",
        "h_despues",
    }
    # las derivaciones con `fuente` (documento o tabla) describen la extraccion y no se compilan
    assert "variables.N2.derivacion.metodo" not in claves
    assert "variables.perdidas_ref_kw.derivacion.metodo" not in claves
    # precondiciones: las dos expresiones compilan (la encadenada `0 < h <= 8760` de forma nativa desde
    # F0.1); solo la de procedimiento, que es prosa, queda delegada al motor de reglas
    assert "calculo.precondiciones[0]" in claves
    assert spec_ind240.precondiciones_texto == ["ninguna regla con severidad BLOQUEANTE fallida"]


def test_avisos_de_carga_de_la_spec_activa(spec_ind240: Spec) -> None:
    avisos = spec_ind240.avisos_carga
    assert any("garantia no verificable estaticamente para R-CON-07: n_motores" in a for a in avisos)
    assert any("garantia no verificable estaticamente para R-AMB-02: categoria" in a for a in avisos)
    assert sum("precondicion" in a and "prosa" in a for a in avisos) == 1
    assert not any("tabla" in a for a in avisos)  # el cuadro 6 carga sin avisos propios


# ---------------------------------------------------------------------------
# 2. Solo spec/*.yaml: propuestas rechazadas, nombre de fichero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["cabecera_v1.yaml", "composicion_v1.yaml"])
def test_cargar_spec_rechaza_propuestas(nombre: str) -> None:
    ruta = PROPUESTAS / nombre
    assert ruta.is_file()
    with pytest.raises(ErrorCargaSpec, match="propuestas"):
        cargar_spec(ruta)


def test_el_registro_ignora_subcarpetas_y_solo_carga_la_activa() -> None:
    registro = SpecRegistry(CARPETA_SPEC)
    cargadas = registro.cargar_todas()
    assert [s.ruta.name for s in cargadas] == ["IND240_v1.1.yaml"]
    assert registro.codigos() == ["IND240"]
    assert registro.versiones("IND240") == ["1.1"]
    assert registro.obtener("IND240").version_ficha == "1.1"
    assert registro.avisos == []  # una sola version: el criterio de vigencia no tiene efecto


def test_cargar_todas_ignora_propuestas_en_tmp(tmp_path: Path) -> None:
    escribir(tmp_path / "spec", spec_minima())
    escribir(
        tmp_path / "spec" / "propuestas", {**spec_minima(), "spec": {**spec_minima()["spec"], "id": "OTRA"}}
    )
    registro = SpecRegistry(tmp_path / "spec", raiz_datos=RAIZ)
    registro.cargar_todas()
    assert registro.codigos() == ["FICHA"]
    with pytest.raises(ErrorCargaSpec, match="propuestas"):
        cargar_spec(tmp_path / "spec" / "propuestas" / "OTRA_v1.0.yaml", raiz_datos=RAIZ)


def test_nombre_de_fichero_debe_coincidir_con_id_y_version(tmp_path: Path) -> None:
    with pytest.raises(ErrorCargaSpec, match="no coincide"):
        cargar(tmp_path, spec_minima(), nombre="FICHA_v2.0.yaml")
    with pytest.raises(ErrorCargaSpec, match="no coincide"):
        cargar(tmp_path, spec_minima(), nombre="OTRA_v1.0.yaml")
    with pytest.raises(ErrorCargaSpec, match="<CODIGO>_v<version_ficha>"):
        cargar(tmp_path, spec_minima(), nombre="ficha.yaml")
    with pytest.raises(ErrorCargaSpec, match="No existe"):
        cargar_spec(tmp_path / "spec" / "NADA_v1.0.yaml")


def test_carpeta_inexistente_y_registro_duplicado(tmp_path: Path) -> None:
    with pytest.raises(ErrorCargaSpec, match="No existe la carpeta"):
        SpecRegistry(tmp_path / "no").cargar_todas()
    registro = SpecRegistry(tmp_path / "spec", raiz_datos=RAIZ)
    spec = cargar(tmp_path, spec_minima())
    registro.registrar(spec)
    with pytest.raises(ErrorCargaSpec, match="ya esta registrada"):
        registro.registrar(spec)
    with pytest.raises(ErrorCargaSpec, match="no cargada"):
        registro.obtener("NADIE")


# ---------------------------------------------------------------------------
# 3. Validacion de campos y valores por defecto (docs/04 §3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bloque", ["spec", "variables", "calculo", "documentacion", "reglas", "estados"])
def test_bloques_obligatorios(tmp_path: Path, bloque: str) -> None:
    datos = spec_minima()
    del datos[bloque]
    with pytest.raises(ErrorCargaSpec, match=bloque):
        cargar(tmp_path, datos, nombre="FICHA_v1.0.yaml")


def test_cabecera_version_ficha_cadena_y_version_spec_semver(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["spec"]["version_spec"] = "0.1"
    with pytest.raises(ErrorCargaSpec, match="semver"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["spec"]["version_ficha"] = 1.0  # sin comillas: float
    with pytest.raises(ErrorCargaSpec, match="version_ficha"):
        cargar(tmp_path, datos, nombre="FICHA_v1.0.yaml")
    datos = spec_minima()
    del datos["spec"]["id"]
    with pytest.raises(ErrorCargaSpec, match="spec.id"):
        cargar(tmp_path, datos, nombre="FICHA_v1.0.yaml")


@pytest.mark.parametrize("campo", ["id", "descripcion", "logica", "severidad"])
def test_regla_sin_campo_obligatorio(tmp_path: Path, campo: str) -> None:
    datos = spec_minima()
    del datos["reglas"][1][campo]
    with pytest.raises(ErrorCargaSpec, match=campo):
        cargar(tmp_path, datos)


def test_severidad_fuera_de_catalogo_e_id_repetido(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["reglas"][1]["severidad"] = "BLOQUEANTE"
    with pytest.raises(ErrorCargaSpec, match="catalogo"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["reglas"][1]["id"] = "R-PRE-01"
    with pytest.raises(ErrorCargaSpec, match="repetido"):
        cargar(tmp_path, datos)


def test_valores_por_defecto_de_la_anatomia(spec_ind240: Spec) -> None:
    regla = spec_ind240.regla("R-CON-01")
    assert regla.descripcion == "PM coincide en todas las fuentes"
    assert regla.logica == "unique(PM.valores_por_fuente)"
    assert regla.referencia is None and regla.interpretacion is None
    assert regla.nivel == "unidad" and not regla.nivel_declarado
    assert regla.fase == "consistencia" and not regla.fase_declarada
    assert regla.diferencial is True
    assert regla.equivalente_plataforma is None
    assert regla.origen_subsanacion == ("interno",)
    assert regla.subsanacion == {"mensaje": regla.descripcion, "documentos": []}
    assert regla.vigencia == Vigencia(None, None)
    assert regla.vigencia.contiene(date(1900, 1, 1)) and regla.vigencia.contiene(date(2999, 12, 31))
    assert regla.es_bloqueante
    assert spec_ind240.regla("R-CAL-02").interpretacion == "INT-02"
    assert spec_ind240.regla("R-AMB-02").referencia == "EXC-01, EXC-02"
    assert not spec_ind240.regla("R-DOC-01").es_bloqueante


def test_campos_declarados_se_respetan(tmp_path: Path) -> None:
    def modificar(datos: dict) -> None:
        regla = regla_activa(datos, "R-CON-01")
        regla.update(
            {
                "fase": "cabecera",
                "nivel": "actuacion",
                "diferencial": False,
                "equivalente_plataforma": "TODO(API-04)",
                "origen_subsanacion": ["interno", "verificador"],
                "subsanacion": {"mensaje": "PM no coincide.", "documentos": ["ficha_tecnica_motor"]},
                "vigencia": {"desde": "2025-05-07", "hasta": None},
            }
        )

    spec = activa_modificada(tmp_path, modificar)
    regla = spec.regla("R-CON-01")
    assert regla.fase == "cabecera" and regla.fase_declarada
    assert regla.nivel == "actuacion" and regla.nivel_declarado
    assert regla.diferencial is False
    assert regla.equivalente_plataforma == "TODO(API-04)"
    assert regla.origen_subsanacion == ("interno", "verificador")
    assert regla.subsanacion == {"mensaje": "PM no coincide.", "documentos": ["ficha_tecnica_motor"]}
    assert regla.vigencia == Vigencia(date(2025, 5, 7), None)
    assert not regla.vigencia.contiene(date(2025, 5, 6)) and regla.vigencia.contiene(date(2025, 5, 7))
    assert spec.reglas_por_fase()["cabecera"] == [regla]


@pytest.mark.parametrize(
    "campo, valor, mensaje",
    [
        ("fase", "calculo", "fase"),
        ("nivel", "motor", "nivel"),
        ("diferencial", "no", "diferencial"),
        ("vigencia", {"desde": "hoy"}, "ISO"),
        ("vigencia", {"inicio": "2025-01-01"}, "desconocidas"),
        ("subsanacion", "texto", "subsanacion"),
    ],
)
def test_campos_nuevos_con_valor_invalido(tmp_path: Path, campo: str, valor: object, mensaje: str) -> None:
    datos = spec_minima()
    datos["reglas"][1][campo] = valor
    with pytest.raises(ErrorCargaSpec, match=mensaje):
        cargar(tmp_path, datos)


def test_interpretacion_inexistente_es_error(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["reglas"][1]["interpretacion"] = "INT-99"
    with pytest.raises(ErrorCargaSpec, match="INT-99"):
        cargar(tmp_path, datos)
    # tambien en una variable (derivacion.interpretacion) y en la documentacion
    datos = spec_minima()
    datos["variables"]["Y"]["interpretacion"] = "INT-42"
    with pytest.raises(ErrorCargaSpec, match="variables.Y.interpretacion referencia INT-42"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["documentacion"][0]["interpretacion"] = "INT-07"
    with pytest.raises(ErrorCargaSpec, match="INT-07"):
        cargar(tmp_path, datos)
    # declarada, carga; una interpretacion declarada sin tema/criterio/impacto es error (regla de oro 7)
    datos["interpretaciones"] = [{"id": "INT-07", "tema": "t", "criterio_poc": "c", "impacto": "bajo"}]
    assert cargar(tmp_path, datos).interpretacion("INT-07")["tema"] == "t"
    datos["interpretaciones"] = [{"id": "INT-07", "tema": "t"}]
    with pytest.raises(ErrorCargaSpec, match="criterio_poc"):
        cargar(tmp_path, datos)


def test_validaciones_de_variables_documentacion_calculo_y_estados(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["variables"]["Y"]["evidencia"] = "supuesto"
    with pytest.raises(ErrorCargaSpec, match="evidencia"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["variables"]["Z"] = {"nivel": "motor", "evidencia": "derivado"}  # derivado sin derivacion
    with pytest.raises(ErrorCargaSpec, match="derivacion"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["documentacion"][1]["obligatorio"] = "si"
    with pytest.raises(ErrorCargaSpec, match="obligatorio"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["documentacion"][1]["obligatorio"] = "condicional"  # sin condicion
    with pytest.raises(ErrorCargaSpec, match="condicion"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    del datos["calculo"]["motor"]["formula"]
    with pytest.raises(ErrorCargaSpec, match="calculo.motor.formula"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["calculo"]["controles_fisicos"] = [{"id": "C-01"}]
    with pytest.raises(ErrorCargaSpec, match="regla"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    del datos["estados"]["BLOQUEADO"]
    with pytest.raises(ErrorCargaSpec, match="BLOQUEADO"):
        cargar(tmp_path, datos)


# ---------------------------------------------------------------------------
# 4. Fase y nivel derivados sin lista de ids en codigo (docs/04 §5.2, docs/03 §14.c)
# ---------------------------------------------------------------------------


def test_fase_derivada_reproduce_la_tabla_de_docs04_5_2(spec_ind240: Spec) -> None:
    assert len(FASE_ESPERADA) == 26
    obtenida = {r.id: r.fase for r in spec_ind240.reglas}
    assert obtenida == FASE_ESPERADA
    assert not any(r.fase_declarada for r in spec_ind240.reglas)  # la activa no declara `fase`
    recuento = Counter(obtenida.values())
    assert recuento == {"ambito": 3, "consistencia": 10, "post_calculo": 2, "resto": 11}


def test_fase_derivada_es_generica(tmp_path: Path) -> None:
    """Las mismas reglas de derivacion sobre una spec ajena: sin ids de la ficha por medio."""
    datos = spec_minima()
    datos["tablas"] = {
        "REG1781_CUADRO6": {"fichero": "data/reg_2019_1781_cuadro6.csv", "columnas": ["kw_motor"]}
    }
    datos["calculo"]["motor"]["formula"] = "Y * 2"  # S solo depende de Y (cubierta): C-01 queda cubierto
    datos["calculo"]["controles_fisicos"] = [{"id": "C-01", "regla": "S <= Y * Y"}]
    datos["reglas"] += [
        {
            "id": "R-A-01",
            "descripcion": "a",
            "logica": "Y in ambito.tipos_incluidos",
            "severidad": "BLOQUEANTE_AMBITO",
        },
        {"id": "R-A-02", "descripcion": "b", "logica": "C-01", "severidad": "BLOQUEANTE_DATOS"},
        {"id": "R-A-03", "descripcion": "c", "logica": "abs(T_cae - Y) <= 1", "severidad": "SUBSANABLE"},
        {
            "id": "R-A-04",
            "descripcion": "d",
            "logica": "exists(REG1781_CUADRO6.kw_motor == Y)",
            "severidad": "AVISO",
        },
        {"id": "R-A-05", "descripcion": "e", "logica": "Y >= 1", "severidad": "SUBSANABLE"},
        {"id": "R-A-06", "descripcion": "f", "logica": "Y >= 1", "severidad": "AVISO"},
        {"id": "R-A-07", "descripcion": "g", "logica": "S > 0", "severidad": "AVISO"},
    ]
    spec = cargar(tmp_path, datos)
    fases = {r.id: r.fase for r in spec.reglas}
    assert fases["R-A-01"] == "ambito"
    assert fases["R-BLQ-01"] == "consistencia"
    assert fases["R-A-02"] == "post_calculo"  # bloqueante, pero referencia un control fisico
    assert fases["R-A-03"] == "post_calculo"  # salida del calculo con sufijo _cae
    assert fases["R-A-07"] == "post_calculo"  # salida por unidad
    assert fases["R-A-04"] == "consistencia"  # referencia una tabla
    assert fases["R-A-05"] == "resto" and fases["R-A-06"] == "resto" and fases["R-PRE-01"] == "resto"


def test_nivel_derivado(spec_ind240: Spec) -> None:
    unidad = {r.id for r in spec_ind240.reglas if r.nivel == "unidad"}
    assert unidad == NIVEL_UNIDAD_ESPERADO
    assert all(r.nivel == "actuacion" for r in spec_ind240.reglas if r.id not in NIVEL_UNIDAD_ESPERADO)
    assert not any(r.nivel_declarado for r in spec_ind240.reglas)


def test_nivel_derivado_es_generico(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["variables"]["W"] = {
        "nivel": "motor",
        "evidencia": "derivado",
        "derivacion": {"fuente": "doc_unidad_registro"},
    }
    datos["documentacion"].append({"id": "D-03", "tipo": "doc_unidad_registro", "obligatorio": True})
    datos["calculo"]["controles_fisicos"] = [
        {"id": "C-01", "regla": "S <= X"},
        {"id": "C-02", "regla": "Y > 0"},  # solo variables de actuacion
    ]
    datos["reglas"] += [
        {"id": "R-N-01", "descripcion": "a", "logica": "for each unidad: Y > 0", "severidad": "AVISO"},
        {"id": "R-N-02", "descripcion": "b", "logica": "X.evidencia == demostrado", "severidad": "AVISO"},
        {"id": "R-N-03", "descripcion": "c", "logica": "doc_unidad.dias >= 30", "severidad": "AVISO"},
        {
            "id": "R-N-04",
            "descripcion": "d",
            "logica": "doc_obligatorio.firmado == true",
            "severidad": "AVISO",
        },
        {"id": "R-N-05", "descripcion": "e", "logica": "C-01", "severidad": "AVISO"},
        {"id": "R-N-06", "descripcion": "f", "logica": "C-02", "severidad": "AVISO"},
        {"id": "R-N-07", "descripcion": "g", "logica": "S > 0 and T > 0", "severidad": "AVISO"},
        {"id": "R-N-08", "descripcion": "h", "logica": "T_cae > 0", "severidad": "AVISO"},
    ]
    niveles = {r.id: r.nivel for r in cargar(tmp_path, datos).reglas}
    assert niveles["R-N-01"] == "unidad"  # for each
    assert niveles["R-N-02"] == "unidad"  # variable de nivel motor
    assert niveles["R-N-03"] == "unidad"  # hecho documental de un documento que solo citan variables motor
    assert niveles["R-N-04"] == "actuacion"  # documento citado por una variable de expediente
    assert niveles["R-N-05"] == "unidad"  # control fisico sobre variables de unidad
    assert niveles["R-N-06"] == "actuacion"  # control fisico solo sobre variables de actuacion
    assert niveles["R-N-07"] == "unidad"  # basta con una salida por unidad
    assert niveles["R-N-08"] == "actuacion"
    assert niveles["R-BLQ-01"] == "actuacion" and niveles["R-PRE-01"] == "actuacion"


# ---------------------------------------------------------------------------
# 5. Enumerados y compilacion con el parser
# ---------------------------------------------------------------------------


def test_enumerados_de_la_spec(spec_ind240: Spec) -> None:
    esperados = (
        set(spec_ind240.ambito["tipos_equipo_incluidos"])
        | set(spec_ind240.ambito["tipos_equipo_excluidos"])
        | {"constante_sin_modulacion", "con_modulacion"}
        | {"demostrado", "declarado", "derivado"}
        | {"motor", "bomba", "ventilador", "compresor", "equipo_completo"}
    )
    assert spec_ind240.enumerados == frozenset(esperados)
    assert not (spec_ind240.enumerados & set(spec_ind240.variables))
    for regla in spec_ind240.reglas:
        assert regla.expresion.enumerados == spec_ind240.enumerados
        assert regla.expresion.literales_simbolicos <= spec_ind240.enumerados
        assert (
            not (regla.expresion.identificadores & spec_ind240.enumerados)
            - regla.expresion.colecciones_ligadas
        )
    assert spec_ind240.regla("R-EVD-04").expresion.identificadores == {"N2.evidencia"}
    assert spec_ind240.regla("R-DOC-02").expresion.colecciones_ligadas == {"motor"}
    for expresion in spec_ind240.expresiones_calculo.values():
        assert expresion.enumerados == spec_ind240.enumerados


def test_enumerado_que_coincide_con_una_variable_es_error(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["variables"]["X"]["valores"] = ["Y", "Z"]
    with pytest.raises(ErrorCargaSpec, match="coinciden con nombres de variables"):
        cargar(tmp_path, datos)


def test_funcion_desconocida_en_regla_o_formula_es_error_de_carga(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["reglas"][1]["logica"] = "coherente(Y)"
    with pytest.raises(ErrorCargaSpec, match=r"regla R-BLQ-01.*funcion desconocida"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["calculo"]["motor"]["formula"] = "round(X * Y)"
    with pytest.raises(ErrorCargaSpec, match=r"calculo.motor.formula.*funcion desconocida"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["calculo"]["controles_fisicos"] = [{"id": "C-01", "regla": "S <= max(X, Y)"}]
    with pytest.raises(ErrorCargaSpec, match=r"controles_fisicos.C-01.*funcion desconocida"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["variables"]["Z"] = {"nivel": "motor", "evidencia": "derivado", "derivacion": {"metodo": "sqrt(X)"}}
    with pytest.raises(ErrorCargaSpec, match=r"variables.Z.derivacion.metodo.*funcion desconocida"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["reglas"][1]["logica"] = "Y ** 2 > 0"  # `**` solo en modo formula
    with pytest.raises(ErrorCargaSpec, match="R-BLQ-01"):
        cargar(tmp_path, datos)


def test_literal_de_lista_no_declarado_no_es_error_porque_la_lista_lo_declara(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["reglas"].append(
        {"id": "R-L-01", "descripcion": "l", "logica": "Y.categoria in [alfa, beta]", "severidad": "AVISO"}
    )
    spec = cargar(tmp_path, datos)
    assert {"alfa", "beta"} <= spec.enumerados
    assert spec.regla("R-L-01").expresion.literales_simbolicos == {"alfa", "beta"}


# ---------------------------------------------------------------------------
# 6. Garantia NO_EVALUABLE → SUBSANABLE (docs/04 §2.5.3)
# ---------------------------------------------------------------------------


def test_garantia_bloqueante_sin_subsanable_que_la_cubra_es_error(tmp_path: Path) -> None:
    datos = spec_minima()
    # X solo tiene fuentes `obligatorio: false`: si falta, la bloqueante queda NO_EVALUABLE
    # sin que ninguna SUBSANABLE lo recoja
    datos["reglas"][1] = {
        "id": "R-BLQ-01",
        "descripcion": "X",
        "logica": "X > 0",
        "severidad": "BLOQUEANTE_DATOS",
    }
    with pytest.raises(ErrorCargaSpec, match=r"NO_EVALUABLE.*R-BLQ-01: X"):
        cargar(tmp_path, datos)


def test_garantia_cubierta_por_subsanable_que_referencia_la_raiz(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["reglas"][1] = {
        "id": "R-BLQ-01",
        "descripcion": "X",
        "logica": "X > 0",
        "severidad": "BLOQUEANTE_DATOS",
    }
    datos["reglas"].append(
        {
            "id": "R-SUB-01",
            "descripcion": "X demostrado",
            "logica": "X.evidencia == demostrado",
            "severidad": "SUBSANABLE",
        }
    )
    spec = cargar(tmp_path, datos)
    assert not any("garantia" in a for a in spec.avisos_carga)


def test_garantia_cubierta_por_documento_obligatorio_solo_si_hay_regla_de_presencia(tmp_path: Path) -> None:
    datos = spec_minima()  # Y tiene fuente obligatoria y R-PRE-01 usa presente(): carga
    assert cargar(tmp_path, datos).regla("R-BLQ-01").es_bloqueante
    datos = spec_minima()
    datos["reglas"][0]["logica"] = "count(doc) >= 1"  # ya no hay regla SUBSANABLE con presente()
    with pytest.raises(ErrorCargaSpec, match="R-BLQ-01: Y"):
        cargar(tmp_path, datos)
    datos = spec_minima()
    datos["reglas"][0]["severidad"] = "AVISO"  # presente() pero no SUBSANABLE
    with pytest.raises(ErrorCargaSpec, match="R-BLQ-01: Y"):
        cargar(tmp_path, datos)


def test_garantia_prefijo_de_documento_tabla_derivacion_calculo_y_constante(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["tablas"] = {
        "REG1781_CUADRO6": {"fichero": "data/reg_2019_1781_cuadro6.csv", "columnas": ["kw_motor"]}
    }
    datos["variables"]["Z"] = {
        "nivel": "motor",
        "evidencia": "derivado",
        "derivacion": {"fuente": "tabla:REG1781_CUADRO6", "clave": "Y", "metodo": "fila cuya clave = Y"},
    }
    datos["variables"]["Q"] = {"nivel": "motor", "evidencia": "derivado", "derivacion": {"metodo": "Z / Y"}}
    datos["calculo"]["motor"]["formula"] = "Q * Y"
    datos["calculo"]["controles_fisicos"] = [{"id": "C-01", "regla": "S <= Y"}]
    datos["reglas"] += [
        {
            "id": "R-G-01",
            "descripcion": "doc",
            "logica": "doc_obligatorio.firmado == true",
            "severidad": "BLOQUEANTE_DATOS",
        },
        {"id": "R-G-02", "descripcion": "tabla", "logica": "Z > 0", "severidad": "BLOQUEANTE_DATOS"},
        {"id": "R-G-03", "descripcion": "metodo", "logica": "Q > 0", "severidad": "BLOQUEANTE_DATOS"},
        {"id": "R-G-04", "descripcion": "control", "logica": "C-01", "severidad": "BLOQUEANTE_DATOS"},
        {"id": "R-G-05", "descripcion": "salida", "logica": "T_cae > 0", "severidad": "BLOQUEANTE_DATOS"},
        {
            "id": "R-G-06",
            "descripcion": "constante",
            "logica": "Y in ambito.tipos_incluidos",
            "severidad": "BLOQUEANTE_AMBITO",
        },
    ]
    spec = cargar(tmp_path, datos)
    assert not any("garantia" in a for a in spec.avisos_carga)
    # si la derivacion por metodo depende de X (no cubierta), Q deja de estar cubierta
    datos["variables"]["Q"]["derivacion"]["metodo"] = "Z / X"
    with pytest.raises(ErrorCargaSpec, match="R-G-03: Q"):
        cargar(tmp_path, datos)


def test_garantia_raiz_no_mapeable_es_aviso_no_error(tmp_path: Path) -> None:
    datos = spec_minima()
    datos["reglas"].append(
        {
            "id": "R-G-07",
            "descripcion": "n",
            "logica": "unique(n_unidades_por_fuente)",
            "severidad": "BLOQUEANTE_DATOS",
        }
    )
    spec = cargar(tmp_path, datos)
    assert "garantia no verificable estaticamente para R-G-07: n_unidades" in spec.avisos_carga


def test_raiz_de() -> None:
    assert raiz_de("variable.valores_por_fuente") == "variable"
    assert raiz_de("variable.declarado") == "variable"
    assert raiz_de("variable.derivado") == "variable"
    assert raiz_de("variable.evidencia") == "variable"
    assert raiz_de("variable.fuente") == "variable"
    assert raiz_de("n_unidades_por_fuente") == "n_unidades"
    assert raiz_de("registro.dias") == "registro"
    assert raiz_de("bloque.lista.atributo") == "bloque"
    assert raiz_de("C-01") == "C-01"


# ---------------------------------------------------------------------------
# 7. Tablas (garantia 4)
# ---------------------------------------------------------------------------


def test_tablas_cargadas_y_error_de_tabla_envuelto(tmp_path: Path, spec_ind240: Spec) -> None:
    assert list(spec_ind240.tablas) == ["REG1781_CUADRO6"]
    tabla = spec_ind240.tablas["REG1781_CUADRO6"]
    assert tabla.buscar_exacta(tabla.filas[0].clave) is not None
    datos = spec_minima()
    datos["tablas"] = {"NOEXISTE": {"fichero": "data/no_existe.csv", "columnas": ["a"]}}
    with pytest.raises(ErrorCargaSpec, match="NOEXISTE"):
        cargar(tmp_path, datos)
    datos["tablas"] = {
        "REG1781_CUADRO6": {"fichero": "data/reg_2019_1781_cuadro6.csv", "columnas": ["kw_motor", "otra"]}
    }
    with pytest.raises(ErrorCargaSpec, match="otra"):
        cargar(tmp_path, datos)


# ---------------------------------------------------------------------------
# 8. Hashes
# ---------------------------------------------------------------------------


def test_hash_reglas_reproducible_y_hash_spec_del_fichero(spec_ind240: Spec) -> None:
    otra = cargar_spec(SPEC_ACTIVA)
    assert otra.hash_reglas == spec_ind240.hash_reglas
    assert re.fullmatch(r"[0-9a-f]{64}", spec_ind240.hash_reglas)
    assert spec_ind240.hash_reglas == hash_canonico(spec_ind240.datos["reglas"])
    import hashlib

    assert spec_ind240.hash_spec == hashlib.sha256(SPEC_ACTIVA.read_bytes()).hexdigest()


def test_hash_reglas_no_depende_del_resto_del_fichero(tmp_path: Path, spec_ind240: Spec) -> None:
    def modificar(datos: dict) -> None:
        datos["spec"]["fecha_revision"] = "2030-01-01"
        datos["interpretaciones"][0]["impacto"] = "alto"

    spec = activa_modificada(tmp_path, modificar)
    assert spec.hash_reglas == spec_ind240.hash_reglas
    assert spec.hash_spec != spec_ind240.hash_spec


@pytest.mark.parametrize(
    "campo, valor",
    [("logica", "N2 <= N1"), ("severidad", "AVISO"), ("fase", "resto"), ("descripcion", "otra")],
)
def test_hash_reglas_cambia_al_cambiar_una_regla(
    tmp_path: Path, spec_ind240: Spec, campo: str, valor: str
) -> None:
    def modificar(datos: dict) -> None:
        regla_activa(datos, "R-CAL-01")[campo] = valor

    spec = activa_modificada(tmp_path, modificar)
    assert spec.hash_reglas != spec_ind240.hash_reglas


def test_hash_canonico_es_estable_ante_orden_de_claves() -> None:
    assert hash_canonico({"b": 1, "a": [1, "ñ"]}) == hash_canonico({"a": [1, "ñ"], "b": 1})
    assert hash_canonico({"a": 1}) != hash_canonico({"a": 2})


# ---------------------------------------------------------------------------
# 9. Versiones (docs/04 §2.4)
# ---------------------------------------------------------------------------


def dos_versiones(tmp_path: Path, vigencias: tuple[dict | None, dict | None] = (None, None)) -> SpecRegistry:
    for version, vigencia in zip(("1.0", "1.1"), vigencias, strict=True):
        datos = spec_minima()
        datos["spec"]["version_ficha"] = version
        if vigencia is not None:
            datos["spec"]["vigencia"] = vigencia
        escribir(tmp_path / "spec", datos)
    registro = SpecRegistry(tmp_path / "spec", raiz_datos=RAIZ)
    registro.cargar_todas()
    return registro


def test_varias_versiones_de_la_misma_ficha(tmp_path: Path) -> None:
    registro = dos_versiones(tmp_path)
    assert registro.versiones("FICHA") == ["1.0", "1.1"]
    assert registro.obtener("FICHA", version_ficha="1.0").version_ficha == "1.0"
    assert registro.obtener("FICHA", version_ficha="1.1").version_ficha == "1.1"
    with pytest.raises(ErrorCargaSpec, match="sin version"):
        registro.obtener("FICHA", version_ficha="2.0")
    assert registro.avisos == []
    # sin criterio declarado: version mas alta y aviso (nunca se inventa el criterio)
    assert registro.obtener("FICHA").version_ficha == "1.1"
    assert registro.obtener("FICHA", fecha=date(2024, 1, 1)).version_ficha == "1.1"
    assert len(registro.avisos) == 1 and AVISO_VIGENCIA_NO_DECIDIDA in registro.avisos[0]


def test_vigencia_declarada_en_la_spec_decide_la_version(tmp_path: Path) -> None:
    registro = dos_versiones(
        tmp_path,
        ({"desde": None, "hasta": "2025-12-31"}, {"desde": "2026-01-01", "hasta": None}),
    )
    assert registro.obtener("FICHA", fecha=date(2025, 6, 1)).version_ficha == "1.0"
    assert registro.obtener("FICHA", fecha=date(2026, 3, 1)).version_ficha == "1.1"
    assert registro.obtener("FICHA", fecha=date(2025, 12, 31)).version_ficha == "1.0"
    assert registro.avisos == []
    assert registro.obtener("FICHA", fecha=date(2026, 3, 1)).vigencia == Vigencia(date(2026, 1, 1), None)


def test_vigencia_parcial_o_sin_version_vigente(tmp_path: Path) -> None:
    registro = dos_versiones(tmp_path, ({"desde": "2024-01-01", "hasta": "2024-12-31"}, None))
    assert registro.obtener("FICHA", fecha=date(2024, 6, 1)).version_ficha == "1.1"  # no todas declaran
    assert any(AVISO_VIGENCIA_NO_DECIDIDA in a for a in registro.avisos)
    registro = dos_versiones(
        tmp_path / "b",
        ({"desde": "2024-01-01", "hasta": "2024-12-31"}, {"desde": "2026-01-01", "hasta": None}),
    )
    with pytest.raises(ErrorCargaSpec, match="ninguna version vigente"):
        registro.obtener("FICHA", fecha=date(2025, 6, 1))


def test_orden_de_versiones_es_numerico() -> None:
    assert sorted(["1.10", "1.9", "1.2", "2.0"], key=clave_version) == ["1.2", "1.9", "1.10", "2.0"]


# ---------------------------------------------------------------------------
# 10. Sin datos de la ficha en codigo; dependencias hacia dentro
# ---------------------------------------------------------------------------


def test_el_fuente_no_contiene_ids_de_ficha_tabla_ni_regla() -> None:
    fuente = FUENTE.read_text(encoding="utf-8")
    for literal in ("IND240", "REG1781", "R-CAL-02", "R-CON-06", "FIS-01", "AETOTAL", "AEM"):
        assert literal not in fuente, literal
    assert not re.search(r"R-[A-Z]{3}-\d{2}", fuente)
    for prohibido in ("eval(", "exec(", "compile(", "import ast", "from ast"):
        assert prohibido not in fuente, prohibido


def test_engine_no_importa_agentes_salida_generator_ni_tests() -> None:
    for modulo in (RAIZ / "engine").glob("*.py"):
        fuente = modulo.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+(agentes|salida|generator|tests)\b", fuente, re.M), (
            modulo.name
        )
    assert spec_registry.RAIZ == RAIZ


def test_cargar_spec_no_modifica_el_fichero(tmp_path: Path) -> None:
    copia = tmp_path / "spec" / "IND240_v1.1.yaml"
    copia.parent.mkdir()
    shutil.copy(SPEC_ACTIVA, copia)
    antes = copia.read_bytes()
    cargar_spec(copia, raiz_datos=RAIZ)
    assert copia.read_bytes() == antes
