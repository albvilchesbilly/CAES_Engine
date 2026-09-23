"""Tests de `engine/informe.py` y `engine/cli.py` (F0.10).

Lo que se protege es lo que `docs/05` §2.2 pide que el informe muestre en cada caso: veredicto, ahorro (o su
ausencia con las dos evidencias del conflicto), reglas por fase, carencias, evidencias con cita y pagina,
interpretaciones aplicadas, avisos y documentos con su huella. Los casos se reutilizan de `test_motor.py`
(una sola ejecucion de la cadena por sesion).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.cli import CODIGO_ERROR, CODIGO_OK, CODIGO_VEREDICTO_NEGATIVO, main, ruta_de_salida
from engine.informe import (
    ROTULO_PROVISIONAL,
    a_json,
    a_markdown,
    descargo_de,
    miles,
    motivo_sin_calculo,
    texto_decimal,
    texto_es,
)
from tests.test_motor import CASOS, FECHA, RAIZ, ground_truth, procesado

CASO_A = "EXP001-A_completo"
CASO_B = "EXP001-B_falta_registro"
CASO_C = "EXP001-C_contradictorio"
CASO_D = "EXP001-D_fuera_ambito"
CASO_G = "EXP001-G_desordenado"

FASES_POSTERIORES_AL_AMBITO = ("consistencia", "calculo", "post_calculo", "resto")


def md(caso: str) -> str:
    return a_markdown(procesado(caso))


# ---------------------------------------------------------------------------
# Markdown: cabecera, veredicto y ahorro
# ---------------------------------------------------------------------------


def test_la_cabecera_identifica_actuacion_spec_y_engine():
    actuacion = procesado(CASO_A)
    texto = md(CASO_A)
    identidad = actuacion.identidad_spec
    for esperado in (
        actuacion.id,
        str(actuacion.carpeta),
        identidad.codigo,
        identidad.version_ficha,
        identidad.version_spec,
        identidad.hash_spec,
        identidad.hash_reglas,
        actuacion.fecha_evaluacion.isoformat(),
        actuacion.version_engine,
    ):
        assert esperado in texto


def test_el_descargo_sale_de_la_spec_y_no_esta_escrito_en_el_codigo():
    actuacion = procesado(CASO_A)
    descargo = descargo_de(actuacion)
    assert descargo, "la spec declara `estados.descargo`"
    assert descargo in md(CASO_A)
    fuente = (RAIZ / "engine" / "informe.py").read_text(encoding="utf-8")
    assert descargo[:40] not in fuente


def test_ningun_informe_promete_un_cae_mas_alla_del_descargo_de_la_spec():
    for caso in CASOS:
        actuacion = procesado(caso)
        texto = a_markdown(actuacion)
        descargo = descargo_de(actuacion)
        assert texto.replace(descargo, "").count("CAE garantizado") == 0


@pytest.mark.parametrize("caso", CASOS)
def test_el_veredicto_aparece_con_su_semaforo_de_la_spec(caso):
    actuacion = procesado(caso)
    texto = a_markdown(actuacion)
    estado = actuacion.spec.estados[actuacion.veredicto]
    assert actuacion.veredicto in texto
    assert str(estado["semaforo"]) in texto
    mensaje = str(estado.get("mensaje") or "")
    if mensaje:
        assert mensaje in texto


def test_el_caso_a_publica_el_ahorro_exacto_y_el_truncado():
    texto = md(CASO_A)
    esperado = ground_truth(CASO_A)["aetotal_esperado"]
    assert esperado["exacto"] in texto
    assert "305.829" in texto or str(esperado["cae"]) in texto
    assert ROTULO_PROVISIONAL not in texto


def test_el_caso_b_rotula_el_ahorro_como_estimacion_no_acreditada():
    texto = md(CASO_B)
    assert ROTULO_PROVISIONAL in texto
    assert ground_truth(CASO_B)["aetotal_esperado"]["exacto"] in texto


@pytest.mark.parametrize("caso", [CASO_C, CASO_D])
def test_sin_calculo_el_informe_dice_el_motivo_y_no_publica_ahorro(caso):
    actuacion = procesado(caso)
    texto = a_markdown(actuacion)
    assert actuacion.calculo is None
    assert "Sin ahorro publicable" in texto
    assert motivo_sin_calculo(actuacion) in texto
    assert ground_truth(caso)["aetotal_esperado"].get("referencia_no_publicada") not in texto


def test_el_conflicto_del_caso_c_se_muestra_con_las_dos_evidencias():
    actuacion = procesado(CASO_C)
    texto = a_markdown(actuacion)
    assert actuacion.evaluacion.bloqueo_por_conflicto
    for variable in actuacion.evaluacion.bloqueo_por_conflicto:
        assert variable in texto
    for dato in actuacion.consolidada.conflictos:
        assert len(dato.evidencias) >= 2
        for ev in dato.evidencias:
            assert ev.tipo_doc in texto
            assert ev.texto_literal[:60] in texto


# ---------------------------------------------------------------------------
# Markdown: calculo, reglas, carencias, evidencias, interpretaciones, documentos
# ---------------------------------------------------------------------------


def test_el_calculo_muestra_entradas_derivadas_controles_y_traza():
    actuacion = procesado(CASO_A)
    texto = a_markdown(actuacion)
    calculo = actuacion.calculo
    assert calculo is not None
    for unidad in calculo.por_unidad:
        assert unidad.num_serie_motor in texto
        for nombre in list(unidad.entradas) + list(unidad.derivadas) + list(unidad.controles):
            assert nombre in texto
    for linea in calculo.traza:
        assert linea in texto


def test_el_caso_f_muestra_un_bloque_de_calculo_por_motor():
    actuacion = procesado("EXP001-F_tres_motores")
    texto = a_markdown(actuacion)
    assert actuacion.calculo is not None
    assert len(actuacion.calculo.por_unidad) == 3
    for unidad in actuacion.calculo.por_unidad:
        assert f"### Unidad {unidad.num_serie_motor}" in texto


@pytest.mark.parametrize("caso", CASOS)
def test_todas_las_reglas_aparecen_con_fase_severidad_y_resultado(caso):
    actuacion = procesado(caso)
    texto = a_markdown(actuacion)
    assert len(actuacion.evaluacion.resultados) == len(actuacion.spec.reglas)
    for resultado in actuacion.evaluacion.resultados:
        assert resultado.id in texto
        assert resultado.severidad in texto
        assert f"### Fase {resultado.fase}" in texto
    for fase in actuacion.evaluacion.fases_saltadas:
        assert f"### Fase {fase} (saltada)" in texto


def test_en_el_caso_d_ninguna_regla_de_las_fases_posteriores_aparece_como_falla():
    actuacion = procesado(CASO_D)
    texto = a_markdown(actuacion)
    for fase in FASES_POSTERIORES_AL_AMBITO:
        bloque = (
            texto.split(f"### Fase {fase}")[1].split("### Fase")[0] if f"### Fase {fase}" in texto else ""
        )
        assert "FALLA" not in bloque


def test_las_carencias_dicen_que_falta_y_con_que_documentos():
    actuacion = procesado(CASO_B)
    texto = a_markdown(actuacion)
    assert actuacion.evaluacion.carencias
    for carencia in actuacion.evaluacion.carencias:
        assert str(carencia["id"]) in texto
        assert str(carencia["mensaje"])[:40] in texto
        for documento in carencia["documentos"]:
            assert documento in texto


def test_las_evidencias_llevan_las_tres_capas_con_pagina_y_texto_literal():
    actuacion = procesado(CASO_A)
    texto = a_markdown(actuacion)
    datos = list(actuacion.consolidada.variables.values())
    for unidad in actuacion.consolidada.unidades.values():
        datos.extend(unidad.values())
    assert datos
    for dato in datos:
        assert dato.variable in texto
        if dato.tipo_evidencia:
            assert dato.tipo_evidencia in texto
        for ev in dato.evidencias[:2]:
            assert ev.texto_literal[:60] in texto
            assert ev.metodo in texto


def test_las_evidencias_de_ocr_discrepantes_se_muestran_como_posibles_errores():
    actuacion = procesado(CASO_C)
    texto = a_markdown(actuacion)
    discrepantes = [
        ev
        for datos in actuacion.consolidada.unidades.values()
        for dato in datos.values()
        for ev in dato.posibles_errores_ocr
    ]
    if discrepantes:
        assert "Posibles errores de OCR" in texto


def test_las_interpretaciones_aplicadas_salen_de_la_spec_con_su_tema():
    actuacion = procesado(CASO_A)
    texto = a_markdown(actuacion)
    assert actuacion.evaluacion.interpretaciones_aplicadas
    for id_int in actuacion.evaluacion.interpretaciones_aplicadas:
        assert id_int in texto
        try:
            declarada = actuacion.spec.interpretacion(id_int)
        except KeyError:
            continue
        assert str(declarada["tema"])[:40] in texto


def test_los_avisos_de_ingesta_del_caso_g_estan_en_el_informe():
    actuacion = procesado(CASO_G)
    texto = a_markdown(actuacion)
    assert actuacion.avisos
    for aviso in actuacion.avisos:
        assert aviso[:80] in texto


def test_los_documentos_aparecen_con_tipo_huella_y_origen():
    actuacion = procesado(CASO_G)
    texto = a_markdown(actuacion)
    for doc in actuacion.documentos:
        assert doc.nombre in texto
        assert doc.sha256 in texto
        if doc.origen:
            assert doc.origen[:12] in texto


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_el_json_es_serializable_y_trae_las_claves_principales(caso):
    actuacion = procesado(caso)
    texto = json.dumps(a_json(actuacion), ensure_ascii=False)
    datos = json.loads(texto)
    for clave in (
        "version_engine",
        "actuacion",
        "spec",
        "descargo",
        "veredicto",
        "ahorro",
        "calculo",
        "evaluacion",
        "carencias",
        "interpretaciones_aplicadas",
        "conflictos",
        "consolidada",
        "documentos",
        "avisos",
        "tiempos",
    ):
        assert clave in datos
    assert datos["veredicto"]["valor"] == actuacion.veredicto
    assert datos["spec"]["hash_reglas"] == actuacion.spec.hash_reglas
    assert len(datos["evaluacion"]["resultados"]) == len(actuacion.spec.reglas)


def test_el_json_publica_el_ahorro_como_cadena_decimal():
    datos = a_json(procesado(CASO_A))
    esperado = ground_truth(CASO_A)["aetotal_esperado"]
    assert datos["ahorro"]["exacto"] == esperado["exacto"]
    assert datos["ahorro"]["truncado"] == esperado["cae"]
    assert datos["ahorro"]["provisional"] is False
    assert datos["ahorro"]["rotulo"] is None


def test_el_json_de_b_marca_el_ahorro_como_provisional():
    datos = a_json(procesado(CASO_B))
    assert datos["ahorro"]["provisional"] is True
    assert datos["ahorro"]["rotulo"] == ROTULO_PROVISIONAL


def test_el_json_de_c_no_trae_ahorro_y_conserva_las_evidencias_enfrentadas():
    datos = a_json(procesado(CASO_C))
    assert datos["ahorro"]["exacto"] is None and datos["ahorro"]["truncado"] is None
    assert datos["ahorro"]["motivo_no_calculo"]
    assert datos["ahorro"]["bloqueo_por_conflicto"]
    assert datos["conflictos"]
    for conflicto in datos["conflictos"]:
        assert conflicto["valor_consumido"] is None
        assert len(conflicto["evidencias"]) >= 2
        for ev in conflicto["evidencias"]:
            assert ev["pagina"] is not None and ev["texto_literal"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_el_comando_de_docs_06_produce_los_dos_informes(tmp_path):
    destino_md = tmp_path / "a.md"
    destino_json = tmp_path / "a.json"
    proceso = subprocess.run(
        [
            sys.executable,
            "-m",
            "engine.cli",
            "expedientes/EXP001-A_completo",
            "--md",
            str(destino_md),
            "--json",
            str(destino_json),
            "--fecha",
            FECHA.isoformat(),
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proceso.returncode == CODIGO_OK, proceso.stderr
    texto = destino_md.read_text(encoding="utf-8")
    assert "PREVALIDADO" in texto
    assert "305.829" in texto or "305829" in texto
    actuacion = procesado(CASO_A)
    for regla in actuacion.spec.ids_reglas:
        assert regla in texto
    assert descargo_de(actuacion) in texto
    datos = json.loads(destino_json.read_text(encoding="utf-8"))
    assert datos["veredicto"]["valor"] == "PREVALIDADO"
    assert datos["ahorro"]["exacto"] == "305829.6"


@pytest.mark.parametrize(
    ("caso", "codigo"),
    [
        (CASO_A, CODIGO_OK),
        (CASO_B, CODIGO_OK),
        (CASO_C, CODIGO_VEREDICTO_NEGATIVO),
        (CASO_D, CODIGO_VEREDICTO_NEGATIVO),
    ],
)
def test_el_codigo_de_salida_depende_del_veredicto(caso, codigo, tmp_path, capsys):
    resultado = main(
        [
            str(RAIZ / "expedientes" / caso),
            "--sin-ocr",
            "--fecha",
            FECHA.isoformat(),
            "--md",
            str(tmp_path / f"{caso}.md"),
        ]
    )
    capsys.readouterr()
    assert resultado == codigo


def test_carpeta_inexistente_devuelve_codigo_de_error(tmp_path, capsys):
    assert main([str(tmp_path / "no_existe"), "--sin-ocr"]) == CODIGO_ERROR
    assert "error" in capsys.readouterr().err


def test_fecha_invalida_devuelve_codigo_de_error(capsys):
    codigo = main([str(RAIZ / "expedientes" / CASO_A), "--sin-ocr", "--fecha", "18/09/2026"])
    capsys.readouterr()
    assert codigo == CODIGO_ERROR


def test_ficha_desconocida_devuelve_codigo_de_error(capsys):
    codigo = main([str(RAIZ / "expedientes" / CASO_A), "--sin-ocr", "--ficha", "NO_EXISTE"])
    capsys.readouterr()
    assert codigo == CODIGO_ERROR


def test_sin_rutas_escribe_un_resumen_por_pantalla(capsys):
    codigo = main([str(RAIZ / "expedientes" / CASO_B), "--sin-ocr", "--fecha", FECHA.isoformat()])
    salida = capsys.readouterr().out
    assert codigo == CODIGO_OK
    assert "Veredicto: SUBSANABLE" in salida
    assert "305.829" in salida
    assert "provisional" in salida


def test_silencioso_no_escribe_nada(tmp_path, capsys):
    codigo = main(
        [
            str(RAIZ / "expedientes" / CASO_A),
            "--sin-ocr",
            "--silencioso",
            "--fecha",
            FECHA.isoformat(),
            "--md",
            str(tmp_path / "a.md"),
        ]
    )
    assert codigo == CODIGO_OK
    assert capsys.readouterr().out == ""
    assert (tmp_path / "a.md").exists()


def test_una_ruta_relativa_se_escribe_bajo_informes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    destino = ruta_de_salida(Path("sub/informe.md"))
    assert destino == Path("informes/sub/informe.md")
    assert destino.parent.is_dir()
    codigo = main(
        [str(RAIZ / "expedientes" / CASO_A), "--sin-ocr", "--fecha", FECHA.isoformat(), "--md", "a.md"]
    )
    capsys.readouterr()
    assert codigo == CODIGO_OK
    assert (tmp_path / "informes" / "a.md").exists()


def test_una_ruta_absoluta_se_respeta(tmp_path):
    destino = ruta_de_salida(tmp_path / "x" / "informe.json")
    assert destino == tmp_path / "x" / "informe.json"
    assert destino.parent.is_dir()


def test_sin_fecha_la_cli_usa_hoy(tmp_path, capsys):
    codigo = main([str(RAIZ / "expedientes" / CASO_A), "--sin-ocr", "--md", str(tmp_path / "a.md")])
    capsys.readouterr()
    assert codigo == CODIGO_OK
    assert date.today().isoformat() in (tmp_path / "a.md").read_text(encoding="utf-8")


def test_sin_ocr_el_caso_g_da_el_mismo_informe_de_ahorro_que_con_datos_nativos(tmp_path, capsys):
    codigo = main(
        [
            str(RAIZ / "expedientes" / CASO_G),
            "--sin-ocr",
            "--fecha",
            FECHA.isoformat(),
            "--md",
            str(tmp_path / "g.md"),
        ]
    )
    capsys.readouterr()
    texto = (tmp_path / "g.md").read_text(encoding="utf-8")
    assert codigo == CODIGO_OK
    assert "PREVALIDADO" in texto
    assert ground_truth(CASO_G)["aetotal_esperado"]["exacto"] in texto


# ---------------------------------------------------------------------------
# La cifra presentable (`GAP-COLA-04` / `GAP-REV-08`)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("305829.6000000000000000000000000000"), "305.829,6"),
        (Decimal("305829"), "305.829"),
        (Decimal("1000"), "1.000"),
        (Decimal("999"), "999"),
        (Decimal("0"), "0"),
        (Decimal("0.5"), "0,5"),
        (Decimal("5.0455"), "5,0455"),
        (Decimal("-1234.5"), "-1.234,5"),
        (Decimal("1234567.89"), "1.234.567,89"),
        (305829, "305.829"),
    ],
)
def test_texto_es_escribe_la_cifra_como_la_lee_una_persona(valor, esperado):
    assert texto_es(valor) == esperado


def test_texto_es_no_pasa_por_coma_flotante_y_no_pierde_un_digito():
    """`CLAUDE.md` §2: el ahorro no se formatea convirtiendolo a `float`, ni siquiera "solo para verlo"."""
    exacto = Decimal("12345.67890123456789012345")
    assert texto_es(exacto) == "12.345,67890123456789012345"
    assert texto_es(exacto).replace(".", "").replace(",", ".") == texto_decimal(exacto)


def test_miles_es_el_caso_entero_de_texto_es():
    """Una sola implementacion del agrupamiento: dos darian dos formatos el dia que una cambie."""
    for entero in (0, 7, 999, 1000, 305829, 1234567):
        assert miles(entero) == texto_es(Decimal(entero))
