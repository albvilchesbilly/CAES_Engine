"""Tests de `engine/motor.py` (F0.10): la cadena completa sobre los 7 casos del banco de pruebas.

El ground truth se lee de `expedientes/_resultados_esperados/` (`docs/05` §3): los tests lo leen, `engine/`
no lo conoce. Los casos se procesan **sin OCR** porque `docs/05` §8.2 exige 7/7 en un clon sin `tesseract`;
la suite con OCR es la misma comprobacion marcada `@pytest.mark.ocr` y debe dar veredicto y ahorro identicos.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields as dataclass_fields
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from engine.calculo import ResultadoUnidad
from engine.evidencias import DatoConsolidado, Evidencia
from engine.ingesta import hay_tesseract
from engine.motor import ETAPAS, Actuacion, ErrorMotor, procesar_actuacion
from engine.reglas import Resultado
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_GROUND_TRUTH = CARPETA_CASOS / "_resultados_esperados"
FECHA = date(2026, 9, 18)

CASOS = (
    "EXP001-A_completo",
    "EXP001-B_falta_registro",
    "EXP001-C_contradictorio",
    "EXP001-D_fuera_ambito",
    "EXP001-E_dos_motores",
    "EXP001-F_tres_motores",
    "EXP001-G_desordenado",
)

#: Fases que no deben evaluarse cuando el ambito falla (caso D, `docs/04` §5.1).
FASES_POSTERIORES_AL_AMBITO = ("consistencia", "calculo", "post_calculo", "resto")

MODULOS_F010 = ("motor.py", "informe.py", "cli.py")


def ground_truth(caso: str) -> dict:
    return json.loads((CARPETA_GROUND_TRUTH / f"{caso}.json").read_text(encoding="utf-8"))


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


@cache
def procesado(caso: str, ocr: bool = False) -> Actuacion:
    """Un caso procesado una sola vez por sesion (la cadena completa tarda entre 1 y 4 s por caso)."""
    return procesar_actuacion(
        CARPETA_CASOS / caso,
        fecha_evaluacion=FECHA,
        ocr=ocr,
        registro=_registro(),
    )


# ---------------------------------------------------------------------------
# Los 7 casos contra el ground truth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_veredicto_de_cada_caso_es_el_del_ground_truth(caso):
    esperado = ground_truth(caso)
    assert procesado(caso).veredicto == esperado["veredicto_esperado"]


@pytest.mark.parametrize("caso", CASOS)
def test_reglas_falladas_coinciden_con_el_ground_truth(caso):
    esperado = ground_truth(caso)
    assert sorted(procesado(caso).evaluacion.falladas) == sorted(esperado["reglas_falladas_esperadas"])


@pytest.mark.parametrize("caso", CASOS)
def test_reglas_no_evaluables_esperadas_lo_son(caso):
    esperado = ground_truth(caso)["reglas_no_evaluables_esperadas"]
    obtenidas = set(procesado(caso).evaluacion.no_evaluables)
    assert set(esperado) <= obtenidas


@pytest.mark.parametrize("caso", CASOS)
def test_las_26_reglas_de_la_spec_aparecen_en_la_evaluacion(caso):
    actuacion = procesado(caso)
    assert [r.id for r in actuacion.evaluacion.resultados] != []
    assert sorted(r.id for r in actuacion.evaluacion.resultados) == sorted(actuacion.spec.ids_reglas)


@pytest.mark.parametrize(
    "caso", ["EXP001-A_completo", "EXP001-E_dos_motores", "EXP001-F_tres_motores", "EXP001-G_desordenado"]
)
def test_aetotal_exacto_como_decimal(caso):
    esperado = ground_truth(caso)["aetotal_esperado"]
    calculo = procesado(caso).calculo
    assert calculo is not None
    assert calculo.total == Decimal(esperado["exacto"])
    assert calculo.total_cae == esperado["cae"]
    assert calculo.provisional is False


def test_caso_a_da_el_criterio_de_aceptacion_de_la_fase():
    calculo = procesado("EXP001-A_completo").calculo
    assert calculo is not None and calculo.total == Decimal("305829.6")


def test_caso_b_calcula_pero_marcado_como_provisional():
    actuacion = procesado("EXP001-B_falta_registro")
    esperado = ground_truth("EXP001-B_falta_registro")["aetotal_esperado"]
    assert actuacion.veredicto == "SUBSANABLE"
    assert actuacion.calculo is not None
    assert actuacion.calculo.provisional is True
    assert actuacion.calculo.total == Decimal(esperado["exacto"])
    assert actuacion.evaluacion.carencias


def test_caso_c_no_calcula_y_conserva_las_dos_evidencias_del_conflicto():
    actuacion = procesado("EXP001-C_contradictorio")
    esperado = ground_truth("EXP001-C_contradictorio")
    assert actuacion.veredicto == "BLOQUEADO"
    assert actuacion.calculo is None
    variables = {c["variable"] for c in esperado["conflictos_esperados"]}
    assert set(actuacion.evaluacion.bloqueo_por_conflicto) == variables
    for dato in actuacion.consolidada.conflictos:
        assert dato.valor_consumido is None
        assert len({ev.valor for ev in dato.evidencias}) >= 2
        for ev in dato.evidencias:
            assert ev.texto_literal and ev.tipo_doc


def test_caso_d_se_detiene_en_ambito_sin_fallos_en_fases_posteriores():
    actuacion = procesado("EXP001-D_fuera_ambito")
    assert actuacion.veredicto == "NO_ELEGIBLE"
    assert actuacion.calculo is None
    for fase in FASES_POSTERIORES_AL_AMBITO:
        assert fase in actuacion.evaluacion.fases_saltadas
        assert fase not in actuacion.evaluacion.fases_evaluadas
    posteriores = [r for r in actuacion.evaluacion.resultados if r.fase in FASES_POSTERIORES_AL_AMBITO]
    assert posteriores
    assert all(r.resultado is Resultado.NO_EVALUABLE for r in posteriores)


@pytest.mark.parametrize("caso", ["EXP001-C_contradictorio", "EXP001-D_fuera_ambito"])
def test_casos_sin_ahorro_no_publican_ningun_total(caso):
    assert ground_truth(caso)["aetotal_esperado"]["exacto"] is None
    assert procesado(caso).calculo is None


@pytest.mark.parametrize("caso", CASOS)
def test_interpretaciones_esperadas_estan_entre_las_aplicadas(caso):
    esperadas = set(ground_truth(caso)["interpretaciones_esperadas"])
    assert esperadas <= set(procesado(caso).evaluacion.interpretaciones_aplicadas)


@pytest.mark.parametrize("caso", CASOS)
def test_cada_caso_tiene_las_unidades_del_ground_truth(caso):
    esperado = ground_truth(caso)
    assert procesado(caso).consolidada.n_unidades == esperado["n_motores"]


# ---------------------------------------------------------------------------
# Contrato de `procesar_actuacion`
# ---------------------------------------------------------------------------


def test_la_actuacion_agrega_identidad_spec_tiempos_y_version():
    actuacion = procesado("EXP001-A_completo")
    assert actuacion.id == "EXP001-A_completo"
    assert actuacion.codigo_identificativo_propio == actuacion.id
    assert actuacion.carpeta.name == actuacion.id
    assert actuacion.fecha_evaluacion == FECHA
    identidad = actuacion.identidad_spec
    assert identidad.codigo == "IND240" and identidad.version_ficha == "1.1"
    assert identidad.version_spec and len(identidad.hash_spec) == 64 and len(identidad.hash_reglas) == 64
    assert identidad.hash_reglas == actuacion.evaluacion.hash_reglas
    assert actuacion.version_engine
    assert set(actuacion.tiempos) == set(ETAPAS)
    assert actuacion.tiempos["total"] > 0
    assert actuacion.calculo is actuacion.evaluacion.calculo


def test_la_extraccion_recorre_las_partes_y_no_el_pdf_combinado():
    actuacion = procesado("EXP001-G_desordenado")
    combinados = [d for d in actuacion.documentos if d.es_combinado]
    assert combinados, "el caso G trae un PDF combinado"
    ids_consolidados = {d.doc_id for d in actuacion.consolidada.documentos}
    for combinado in combinados:
        assert combinado.doc_id not in ids_consolidados
        assert set(combinado.partes) <= ids_consolidados


def test_los_avisos_de_ingesta_van_delante_de_los_de_consolidacion():
    actuacion = procesado("EXP001-G_desordenado")
    avisos_ingesta = [a for doc in actuacion.documentos for a in doc.avisos]
    assert avisos_ingesta, "el caso G deja avisos de ingesta y clasificacion"
    assert set(avisos_ingesta) <= set(actuacion.avisos)
    primeros = actuacion.avisos[: len(set(avisos_ingesta))]
    assert set(primeros) <= set(avisos_ingesta)


def test_carpeta_inexistente_da_error_de_motor():
    with pytest.raises(ErrorMotor):
        procesar_actuacion(CARPETA_CASOS / "no_existe", fecha_evaluacion=FECHA, ocr=False)


def test_un_fichero_no_es_una_carpeta_de_actuacion():
    with pytest.raises(ErrorMotor):
        procesar_actuacion(RAIZ / "pyproject.toml", fecha_evaluacion=FECHA, ocr=False)


def test_sin_fecha_se_evalua_con_la_de_hoy():
    actuacion = procesar_actuacion(CARPETA_CASOS / "EXP001-A_completo", ocr=False, registro=_registro())
    assert actuacion.fecha_evaluacion == date.today()


def test_el_registro_recibido_se_reutiliza_sin_recargar():
    registro = _registro()
    antes = registro.codigos()
    procesar_actuacion(
        CARPETA_CASOS / "EXP001-B_falta_registro", fecha_evaluacion=FECHA, ocr=False, registro=registro
    )
    assert registro.codigos() == antes


def test_ficha_desconocida_no_se_inventa():
    from engine.spec_registry import ErrorCargaSpec

    with pytest.raises(ErrorCargaSpec):
        procesar_actuacion(
            CARPETA_CASOS / "EXP001-A_completo",
            spec_id="NO_EXISTE",
            fecha_evaluacion=FECHA,
            ocr=False,
            registro=_registro(),
        )


# ---------------------------------------------------------------------------
# Higiene de los tres modulos de F0.10
# ---------------------------------------------------------------------------


def _fuente(modulo: str) -> str:
    return (RAIZ / "engine" / modulo).read_text(encoding="utf-8")


@pytest.mark.parametrize("modulo", MODULOS_F010)
def test_sin_eval_exec_ni_compile(modulo):
    fuente = _fuente(modulo)
    for prohibido in ("eval(", "exec(", "compile("):
        assert prohibido not in fuente, f"{modulo} contiene {prohibido}"


@pytest.mark.parametrize("modulo", MODULOS_F010)
def test_sin_float_en_magnitudes(modulo):
    assert "float(" not in _fuente(modulo)


@pytest.mark.parametrize("modulo", MODULOS_F010)
def test_no_importa_de_fuera_del_nucleo(modulo):
    fuente = _fuente(modulo)
    for paquete in ("agentes", "salida", "generator", "tests"):
        assert not re.search(rf"^\s*(from|import)\s+{paquete}\b", fuente, re.MULTILINE)


@pytest.mark.parametrize("modulo", MODULOS_F010)
def test_ninguna_rama_por_ficha(modulo):
    fuente = _fuente(modulo)
    assert not re.search(r"if\s+\w*ficha\w*\s*==", fuente)
    assert not re.search(r'==\s*["\']IND\d+["\']', fuente)


def test_el_informe_no_cita_ninguna_regla_ni_variable_de_la_ficha(spec_ind240):
    """Lo que el informe muestra sale de la spec y de los resultados, nunca escrito en `informe.py`."""
    fuente = _fuente("informe.py")
    assert not re.search(r"\bR-[A-Z]{3}-\d{2}\b", fuente)
    assert not re.search(r"\bINT-\d{2}\b", fuente)
    # Los campos de los tipos del contrato (ADR-002 §2.1) no son vocabulario de la ficha aunque
    # coincidan con una variable de la spec: `num_serie_motor` es un atributo de `Evidencia`.
    del_contrato = {
        f.name for tipo in (Evidencia, DatoConsolidado, ResultadoUnidad) for f in dataclass_fields(tipo)
    }
    nombres = {n for n in spec_ind240.variables if len(n) >= 2}
    nombres |= {spec_ind240.plan.salida_unidad, spec_ind240.plan.salida_total}
    citados = sorted(n for n in nombres - del_contrato if re.search(rf"\b{re.escape(n)}\b", fuente))
    assert citados == []


# ---------------------------------------------------------------------------
# Con OCR: el mismo resultado (docs/05 §8.2)
# ---------------------------------------------------------------------------


@pytest.mark.ocr
@pytest.mark.skipif(not hay_tesseract(), reason="tesseract no instalado")
@pytest.mark.parametrize("caso", CASOS)
def test_con_ocr_el_veredicto_y_el_ahorro_no_cambian(caso):
    sin_ocr = procesado(caso, ocr=False)
    con_ocr = procesado(caso, ocr=True)
    assert con_ocr.veredicto == sin_ocr.veredicto == ground_truth(caso)["veredicto_esperado"]
    total_sin = sin_ocr.calculo.total if sin_ocr.calculo else None
    total_con = con_ocr.calculo.total if con_ocr.calculo else None
    assert total_con == total_sin
