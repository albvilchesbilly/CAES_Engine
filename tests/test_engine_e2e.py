"""Tests end-to-end de la cadena completa y de `evaluar_casos.py` (F0.11; `docs/05` §8 y §8.1).

Que cubre esta fila de `docs/05` §8 (`engine/motor.py`, `engine/informe.py`, `engine/cli.py`,
`evaluar_casos.py`):

- **7/7 veredictos** contra el ground truth de `expedientes/_resultados_esperados/`, que los tests leen y
  `engine/` no conoce (`docs/05` §3).
- **A, E, F y G** con el `aetotal_esperado.exacto` comparado como `Decimal`, no como texto ni como truncado;
  **B** con el mismo total pero marcado `provisional`; **C y D** sin ningun ahorro publicado.
- **Reglas falladas exactas** por caso: una de mas o una de menos es un fallo aunque el veredicto coincida.
- **Informe markdown y JSON del caso A**: veredicto, ahorro exacto y truncado, reglas, evidencias con pagina
  y texto literal, traza del calculo e interpretaciones aplicadas.
- **`evaluar_casos.py`**: la matriz, los criterios de comparacion (igualdad en falladas, subconjunto en
  `NO_EVALUABLE` e interpretaciones, `ADR-002` §6.5) y el codigo de salida.

**OCR.** El grueso se ejecuta con `ocr=False` porque `docs/05` §8.2 exige 7/7 en un clon sin `tesseract`.
Lo que necesita OCR va en `@pytest.mark.ocr` con `skipif`: la suite completa se ejecuta donde haya tesseract.

**Tiempos.** La referencia del Engine 0.1 es ~1 s por caso sin OCR y ~12 s en G con OCR (`docs/05` §1). Aqui
los siete casos sin OCR tardan ~4 s y con OCR ~22 s en el contenedor de la Fase 0. El tope que se comprueba
es **`TOPE_SEGUNDOS_SIN_OCR = 120`** para los siete casos: es generoso a proposito (una maquina lenta o un
disco frio no deben poner la suite en rojo) y sigue detectando lo unico que este test puede detectar de
verdad, una regresion de orden de magnitud (un bucle cuadratico, un OCR que se cuela, una spec recargada por
documento). El limite por caso no se comprueba: con siete casos la varianza de uno solo es demasiado alta.
"""

from __future__ import annotations

import json
import time
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

import evaluar_casos
from engine.cli import main as cli_main
from engine.informe import ROTULO_PROVISIONAL, a_json, a_markdown
from engine.ingesta import hay_tesseract
from engine.motor import Actuacion, procesar_actuacion
from engine.reglas import Resultado
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_GROUND_TRUTH = CARPETA_CASOS / "_resultados_esperados"

CASOS = (
    "EXP001-A_completo",
    "EXP001-B_falta_registro",
    "EXP001-C_contradictorio",
    "EXP001-D_fuera_ambito",
    "EXP001-E_dos_motores",
    "EXP001-F_tres_motores",
    "EXP001-G_desordenado",
)
CASOS_CON_AHORRO_ACREDITADO = (
    "EXP001-A_completo",
    "EXP001-E_dos_motores",
    "EXP001-F_tres_motores",
    "EXP001-G_desordenado",
)
CASOS_SIN_AHORRO = ("EXP001-C_contradictorio", "EXP001-D_fuera_ambito")

CASO_A = "EXP001-A_completo"
AETOTAL_A = Decimal("305829.6")

#: Tope del conjunto de los siete casos sin OCR (ver cabecera: detecta regresiones de orden de magnitud).
TOPE_SEGUNDOS_SIN_OCR = 120.0

requiere_ocr = pytest.mark.skipif(not hay_tesseract(), reason="tesseract no esta instalado")


def ground_truth(caso: str) -> dict:
    return json.loads((CARPETA_GROUND_TRUTH / f"{caso}.json").read_text(encoding="utf-8"))


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


@cache
def procesado(caso: str, ocr: bool = False) -> Actuacion:
    """Un caso procesado una sola vez por sesion, con la fecha que declara su ground truth."""
    esperado = ground_truth(caso)
    return procesar_actuacion(
        CARPETA_CASOS / caso,
        fecha_evaluacion=date.fromisoformat(esperado["fecha_evaluacion"]),
        ocr=ocr,
        registro=_registro(),
    )


# ---------------------------------------------------------------------------
# 7/7 veredictos y ahorro exacto
# ---------------------------------------------------------------------------


def test_los_siete_casos_dan_el_veredicto_del_ground_truth():
    obtenidos = {caso: procesado(caso).veredicto for caso in CASOS}
    esperados = {caso: ground_truth(caso)["veredicto_esperado"] for caso in CASOS}
    assert obtenidos == esperados


@pytest.mark.parametrize("caso", CASOS_CON_AHORRO_ACREDITADO)
def test_aetotal_exacto_como_decimal(caso):
    """No basta el truncado: el total exacto se compara como `Decimal` (`docs/05` §8.1)."""
    esperado = ground_truth(caso)["aetotal_esperado"]
    calculo = procesado(caso).calculo
    assert calculo is not None and calculo.total is not None
    assert calculo.total == Decimal(esperado["exacto"])
    assert calculo.total_cae == esperado["cae"]
    assert calculo.provisional is False


def test_el_caso_a_da_el_criterio_de_aceptacion_de_la_fase():
    """305.829,6 kWh/año exactos (`CLAUDE.md` §5, `docs/05` §2.3)."""
    calculo = procesado(CASO_A).calculo
    assert calculo is not None
    assert calculo.total == AETOTAL_A
    assert calculo.total_cae == 305829


def test_el_caso_b_publica_el_mismo_total_pero_como_estimacion_no_acreditada():
    esperado = ground_truth("EXP001-B_falta_registro")["aetotal_esperado"]
    assert esperado["provisional"] is True
    calculo = procesado("EXP001-B_falta_registro").calculo
    assert calculo is not None
    assert calculo.total == Decimal(esperado["exacto"]) == AETOTAL_A
    assert calculo.total_cae == esperado["cae"]
    assert calculo.provisional is True


@pytest.mark.parametrize("caso", CASOS_SIN_AHORRO)
def test_los_casos_sin_ahorro_no_publican_ningun_total(caso):
    esperado = ground_truth(caso)["aetotal_esperado"]
    assert esperado["exacto"] is None and esperado["cae"] is None
    actuacion = procesado(caso)
    calculo = actuacion.calculo
    assert calculo is None or (calculo.total is None and calculo.total_cae is None)
    seccion = a_markdown(actuacion).split("## 2. Ahorro")[1].split("## 3.")[0]
    assert "Sin ahorro publicable" in seccion
    assert "305829" not in seccion and "305.829" not in seccion
    assert a_json(actuacion)["ahorro"]["exacto"] is None


def test_el_caso_c_no_elige_entre_las_dos_evidencias_de_pm():
    """Regla de oro 6: ante conflicto entre fiables, `valor_consumido = null` y se ven las dos."""
    actuacion = procesado("EXP001-C_contradictorio")
    esperado = ground_truth("EXP001-C_contradictorio")["conflictos_esperados"][0]
    dato = actuacion.consolidada.dato(esperado["variable"], esperado["num_serie_motor"])
    assert dato is not None
    assert dato.valor_consumido is None
    assert dato.conflicto is True
    valores = {e["valor"] for e in esperado["evidencias"]}
    assert valores <= {e.valor for e in dato.evidencias}


def test_el_caso_f_toma_el_menor_h_en_el_tercer_motor():
    """La trampa de `docs/05` §4.3: en M3 `h_despues < h_antes`, asi que `h = h_despues`."""
    esperado = {m["num_serie_motor"]: m for m in ground_truth("EXP001-F_tres_motores")["motores"]}
    actuacion = procesado("EXP001-F_tres_motores")
    calculo = actuacion.calculo
    assert calculo is not None
    assert len(calculo.por_unidad) == 3
    for unidad in calculo.por_unidad:
        motor = esperado[unidad.num_serie_motor]
        assert unidad.derivadas["h"] == Decimal(motor["h"])
        assert unidad.derivadas["h"] == min(Decimal(motor["h_antes"]), Decimal(motor["h_despues"]))
        assert unidad.salida == Decimal(motor["AEM"])
    menores = {u.num_serie_motor for u in calculo.por_unidad if u.derivadas["h"] == u.entradas["h_despues"]}
    assert menores == {"MTR-SYN-0003"}


# ---------------------------------------------------------------------------
# Reglas falladas: igualdad exacta por caso
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_las_reglas_falladas_son_exactamente_las_del_ground_truth(caso):
    esperadas = set(ground_truth(caso)["reglas_falladas_esperadas"])
    obtenidas = set(procesado(caso).evaluacion.falladas)
    assert obtenidas == esperadas, f"sobran {obtenidas - esperadas}, faltan {esperadas - obtenidas}"


@pytest.mark.parametrize("caso", CASOS)
def test_las_no_evaluables_esperadas_lo_son(caso):
    """Subconjunto: la spec puede dejar mas reglas sin evaluar (fases saltadas), nunca menos."""
    esperadas = set(ground_truth(caso)["reglas_no_evaluables_esperadas"])
    assert esperadas <= set(procesado(caso).evaluacion.no_evaluables)


@pytest.mark.parametrize("caso", CASOS)
def test_cada_caso_evalua_las_26_reglas_de_la_spec(caso):
    actuacion = procesado(caso)
    ids_spec = {regla.id for regla in actuacion.spec.reglas}
    assert {r.id for r in actuacion.evaluacion.resultados} == ids_spec
    assert len(ids_spec) == 26


def test_en_d_ninguna_regla_posterior_al_ambito_aparece_como_falla():
    """`docs/05` §2.1: D se detiene en fase 1; las fases 2–5 no pueden producir `FALLA`."""
    actuacion = procesado("EXP001-D_fuera_ambito")
    posteriores = ("consistencia", "calculo", "post_calculo", "resto")
    assert set(actuacion.evaluacion.fases_saltadas) == set(posteriores)
    falladas = [r.id for r in actuacion.evaluacion.resultados if r.falla and r.fase in posteriores]
    assert falladas == []
    assert actuacion.evaluacion.resultado("R-AMB-01").resultado is Resultado.FALLA


def test_en_c_no_se_evaluan_las_fases_de_calculo():
    actuacion = procesado("EXP001-C_contradictorio")
    assert set(actuacion.evaluacion.fases_saltadas) == {"calculo", "post_calculo"}


# ---------------------------------------------------------------------------
# Informe del caso A: markdown y JSON
# ---------------------------------------------------------------------------


@cache
def _markdown_a() -> str:
    return a_markdown(procesado(CASO_A))


def test_el_markdown_del_caso_a_lleva_veredicto_y_ahorro():
    texto = _markdown_a()
    assert "PREVALIDADO" in texto
    assert "305829.6" in texto  # exacto
    assert "305.829" in texto  # truncado (INT-06)
    assert ROTULO_PROVISIONAL not in texto


def test_el_markdown_del_caso_a_lleva_las_reglas_evaluadas():
    texto = _markdown_a()
    for regla in procesado(CASO_A).spec.reglas:
        assert regla.id in texto


def test_el_markdown_del_caso_a_lleva_la_traza_del_calculo():
    texto = _markdown_a()
    calculo = procesado(CASO_A).calculo
    assert calculo is not None and calculo.traza
    for linea in calculo.traza:
        assert linea in texto
    assert "MTR-SYN-0001" in texto


def test_el_markdown_del_caso_a_cita_cada_evidencia_con_pagina_y_texto_literal():
    """Regla de oro 2: sin cita no entra. Se comprueba sobre las variables que entran en la formula."""
    actuacion = procesado(CASO_A)
    texto = _markdown_a()
    entradas = sorted(actuacion.spec.plan.entradas_requeridas)
    assert entradas, "el plan de calculo deberia exigir entradas al consolidador"
    for datos in actuacion.consolidada.unidades.values():
        for nombre in entradas:
            dato = datos[nombre]
            assert dato.evidencias, f"{nombre} sin evidencia"
            for evidencia in dato.evidencias:
                assert evidencia.texto_literal.strip()
                assert evidencia.confianza > 0
            primera = dato.evidencias[0]
            assert primera.texto_literal[:40] in texto
            assert str(primera.pagina) in texto


def test_el_markdown_del_caso_a_lleva_las_interpretaciones_aplicadas():
    texto = _markdown_a()
    aplicadas = procesado(CASO_A).evaluacion.interpretaciones_aplicadas
    assert aplicadas
    for interpretacion in aplicadas:
        assert interpretacion in texto


def test_el_json_del_caso_a_es_serializable_y_reproduce_el_informe():
    actuacion = procesado(CASO_A)
    datos = a_json(actuacion)
    texto = json.dumps(datos, ensure_ascii=False)  # sin `default=`: Decimal y date ya son cadena
    vuelta = json.loads(texto)
    assert vuelta["veredicto"]["valor"] == "PREVALIDADO"
    assert vuelta["ahorro"]["exacto"] == "305829.6"
    assert vuelta["ahorro"]["truncado"] == 305829
    assert vuelta["evaluacion"]["hash_reglas"] == actuacion.spec.hash_reglas
    assert len(vuelta["evaluacion"]["resultados"]) == 26
    assert vuelta["calculo"]["traza"]
    assert [d["sha256"] for d in vuelta["documentos"]] == [d.sha256 for d in actuacion.documentos]


def test_el_json_del_caso_a_conserva_las_tres_capas_por_dato():
    vuelta = json.loads(json.dumps(a_json(procesado(CASO_A)), ensure_ascii=False))
    unidades = vuelta["consolidada"]["unidades"]
    (datos,) = unidades.values()
    pm = datos["PM"]
    assert pm["evidencias"] and all(e["texto_literal"] for e in pm["evidencias"])  # capa 1
    assert pm["valor_normalizado"] == "110"  # capa 2
    assert pm["valor_consumido"] == "110"  # capa 3
    assert all(e["pagina"] >= 0 and e["doc_id"] for e in pm["evidencias"])


def test_la_cli_escribe_los_dos_informes_del_caso_a(tmp_path):
    md = tmp_path / "informe.md"
    js = tmp_path / "informe.json"
    codigo = cli_main(
        [
            str(CARPETA_CASOS / CASO_A),
            "--md",
            str(md),
            "--json",
            str(js),
            "--sin-ocr",
            "--fecha",
            ground_truth(CASO_A)["fecha_evaluacion"],
            "--silencioso",
        ]
    )
    assert codigo == 0
    assert "PREVALIDADO" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["ahorro"]["exacto"] == "305829.6"


@pytest.mark.parametrize(
    ("caso", "codigo"),
    [("EXP001-C_contradictorio", 1), ("EXP001-D_fuera_ambito", 1), ("EXP001-B_falta_registro", 0)],
)
def test_la_cli_devuelve_el_codigo_del_veredicto(caso, codigo):
    fecha = ground_truth(caso)["fecha_evaluacion"]
    argv = [str(CARPETA_CASOS / caso), "--sin-ocr", "--silencioso", "--fecha", fecha]
    assert cli_main(argv) == codigo


# ---------------------------------------------------------------------------
# Tiempos
# ---------------------------------------------------------------------------


def test_los_siete_casos_sin_ocr_caben_en_el_tope():
    """Ver cabecera: tope generoso (120 s) que solo detecta regresiones de orden de magnitud."""
    registro = _registro()
    inicio = time.perf_counter()
    for caso in CASOS:
        procesar_actuacion(
            CARPETA_CASOS / caso,
            fecha_evaluacion=date.fromisoformat(ground_truth(caso)["fecha_evaluacion"]),
            ocr=False,
            registro=registro,
        )
    transcurrido = time.perf_counter() - inicio
    assert transcurrido < TOPE_SEGUNDOS_SIN_OCR, f"los 7 casos tardaron {transcurrido:.1f} s"


@pytest.mark.parametrize("caso", CASOS)
def test_cada_caso_registra_el_tiempo_de_todas_sus_etapas(caso):
    tiempos = procesado(caso).tiempos
    etapas = {"spec", "ingesta", "clasificacion", "extraccion", "consolidacion", "evaluacion", "total"}
    assert set(tiempos) == etapas
    assert all(v >= 0 for v in tiempos.values())


# ---------------------------------------------------------------------------
# `evaluar_casos.py`
# ---------------------------------------------------------------------------


def test_evaluar_casos_encuentra_los_siete_casos():
    assert [c.name for c in evaluar_casos.carpetas_de_casos()] == list(CASOS)


def test_evaluar_casos_da_7_7_y_sale_con_cero(capsys):
    codigo = evaluar_casos.main(["--sin-ocr", "--sin-informes"])
    salida = capsys.readouterr().out
    assert "7/7 veredictos correctos" in salida
    assert "7/7 casos sin diferencias" in salida
    assert "305829.6" in salida
    assert codigo == evaluar_casos.CODIGO_OK


def test_evaluar_casos_solo_un_caso(capsys):
    assert evaluar_casos.main(["--caso", "A", "--sin-ocr", "--sin-informes"]) == 0
    salida = capsys.readouterr().out
    assert "1/1 veredictos correctos" in salida
    assert "EXP001-B_falta_registro" not in salida


def test_evaluar_casos_escribe_el_resumen_json(tmp_path, capsys):
    destino = tmp_path / "resumen.json"
    assert evaluar_casos.main(["--caso", "A", "--sin-ocr", "--sin-informes", "--json", str(destino)]) == 0
    capsys.readouterr()
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["veredictos_correctos"] == datos["total"] == 1
    assert datos["referencia_cumple"] is True
    assert datos["casos"][0]["aetotal_exacto"] == "305829.6"


def test_evaluar_casos_escribe_los_informes_donde_se_le_dice(tmp_path):
    rutas = evaluar_casos.escribir_informes_de(procesado(CASO_A), tmp_path)
    assert Path(rutas["markdown"]).read_text(encoding="utf-8").startswith("# Informe")
    informe = json.loads(Path(rutas["json"]).read_text(encoding="utf-8"))
    assert informe["veredicto"]["valor"] == "PREVALIDADO"


def test_evaluar_casos_mide_las_columnas_de_docs05():
    fila = evaluar_casos.evaluar_caso(
        CARPETA_CASOS / CASO_A, ocr=False, registro=_registro(), escribir_informes=False
    )
    assert fila["ok"] is True
    assert fila["documentos"] == len(ground_truth(CASO_A)["documentos"])
    assert fila["extraccion"] == "6/6"
    assert fila["datos_con_evidencia"] > 0
    assert fila["cae"] == "305.829"


def test_evaluar_casos_cuenta_los_ficheros_entregados_no_las_partes_del_combinado():
    """En G un PDF combinado se separa en partes; los ficheros del ground truth son 13, no 16."""
    actuacion = procesado("EXP001-G_desordenado")
    assert any(doc.es_combinado for doc in actuacion.documentos)
    assert evaluar_casos.n_ficheros(actuacion) == len(ground_truth("EXP001-G_desordenado")["documentos"])


def test_evaluar_casos_detecta_una_regla_fallada_de_mas():
    """Una diferencia en las falladas es fallo del caso aunque el veredicto coincida (`docs/05` §8.1)."""
    esperado = dict(ground_truth("EXP001-B_falta_registro"))
    esperado["reglas_falladas_esperadas"] = ["R-DOC-01"]  # falta R-EVD-04
    diferencias = evaluar_casos.comparar(procesado("EXP001-B_falta_registro"), esperado)
    assert any("R-EVD-04" in d for d in diferencias)
    assert any("reglas FALLA" in d for d in diferencias)


def test_evaluar_casos_detecta_un_aetotal_distinto_en_el_ultimo_decimal():
    esperado = dict(ground_truth(CASO_A))
    esperado["aetotal_esperado"] = {"exacto": "305829.7", "cae": 305829, "provisional": False}
    diferencias = evaluar_casos.comparar(procesado(CASO_A), esperado)
    assert any("AETOTAL exacto" in d for d in diferencias)


def test_evaluar_casos_compara_las_interpretaciones_como_subconjunto():
    """`ADR-002` §6.5: hoy se citan las de toda regla evaluada; los extras son nota, no fallo."""
    actuacion = procesado(CASO_A)
    esperado = dict(ground_truth(CASO_A))
    assert set(esperado["interpretaciones_esperadas"]) < set(actuacion.evaluacion.interpretaciones_aplicadas)
    assert evaluar_casos.comparar(actuacion, esperado) == []
    assert any("subconjunto" in n for n in evaluar_casos.notas(actuacion, esperado))

    esperado["interpretaciones_esperadas"] = ["INT-99"]
    assert any("INT-99" in d for d in evaluar_casos.comparar(actuacion, esperado))


def test_evaluar_casos_devuelve_codigo_distinto_de_cero_si_un_caso_difiere():
    filas = [
        {"caso": "A", "ok": True, "veredicto_ok": True, "aetotal_exacto": "305829.6"},
        {"caso": "B", "ok": False, "veredicto_ok": True, "aetotal_exacto": "305829.6"},
    ]
    assert evaluar_casos.codigo_de_salida(filas) == evaluar_casos.CODIGO_DIFERENCIAS
    assert "1/2 casos sin diferencias" in "\n".join(evaluar_casos.resumen(filas))


def test_evaluar_casos_devuelve_codigo_distinto_de_cero_si_el_caso_a_se_mueve_un_decimal():
    filas = [{"caso": "A", "ok": True, "veredicto_ok": True, "aetotal_exacto": "305829.5"}]
    assert evaluar_casos.referencia_cumple(filas) is False
    assert evaluar_casos.codigo_de_salida(filas) == evaluar_casos.CODIGO_DIFERENCIAS
    assert "NO CUMPLE" in "\n".join(evaluar_casos.resumen(filas))


def test_evaluar_casos_sin_ground_truth_es_un_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(evaluar_casos, "CARPETA_CASOS", tmp_path)
    (tmp_path / "EXP001-Z_inventado").mkdir()
    assert evaluar_casos.main(["--sin-ocr", "--sin-informes"]) == evaluar_casos.CODIGO_ERROR
    assert "ground truth" in capsys.readouterr().err


def test_evaluar_casos_imprime_el_detalle_regla_a_regla():
    filas = [
        {
            "caso": "B",
            "carpeta": "EXP001-B_falta_registro",
            "ok": False,
            "diferencias": ["reglas FALLA: esperadas R-DOC-01, obtenidas R-DOC-01, R-EVD-04"],
        }
    ]
    texto = "\n".join(evaluar_casos.detalle(filas))
    assert "Caso B" in texto and "R-EVD-04" in texto


def test_evaluar_casos_no_importa_el_generator():
    fuente = (RAIZ / "evaluar_casos.py").read_text(encoding="utf-8")
    for prohibido in ("generator", "agentes", "salida"):
        assert f"import {prohibido}" not in fuente
        assert f"from {prohibido}" not in fuente


# ---------------------------------------------------------------------------
# Con OCR (se salta sin tesseract): el mismo resultado, mas el escaneo y las fotos de G
# ---------------------------------------------------------------------------


@pytest.mark.ocr
@requiere_ocr
@pytest.mark.parametrize("caso", CASOS)
def test_con_ocr_el_veredicto_y_el_ahorro_no_cambian(caso):
    sin_ocr = procesado(caso, ocr=False)
    con_ocr = procesado(caso, ocr=True)
    assert con_ocr.veredicto == sin_ocr.veredicto
    total_sin = sin_ocr.calculo.total if sin_ocr.calculo else None
    total_con = con_ocr.calculo.total if con_ocr.calculo else None
    assert total_con == total_sin
    assert set(con_ocr.evaluacion.falladas) == set(sin_ocr.evaluacion.falladas)


@pytest.mark.ocr
@requiere_ocr
def test_con_ocr_el_escaneo_girado_de_g_se_clasifica():
    tipos = {doc.nombre: doc.tipo for doc in procesado("EXP001-G_desordenado", ocr=True).documentos}
    assert tipos.get("scan.pdf") is not None


@pytest.mark.ocr
@requiere_ocr
def test_con_ocr_la_placa_entra_con_confianza_reducida():
    """`docs/05` §4.4: las evidencias de foto o escaneo entran con confianza 0,75 y no bloquean."""
    actuacion = procesado(CASO_A, ocr=True)
    ocr = [
        e
        for datos in actuacion.consolidada.unidades.values()
        for dato in datos.values()
        for e in dato.evidencias
        if e.metodo == "ocr"
    ]
    assert ocr, "el informe fotografico del caso A deberia aportar la placa por OCR"
    assert all(e.confianza == Decimal("0.75") for e in ocr)
    assert actuacion.veredicto == "PREVALIDADO"


@pytest.mark.ocr
@requiere_ocr
def test_con_ocr_evaluar_casos_sigue_dando_7_7(capsys):
    codigo = evaluar_casos.main(["--sin-informes"])
    assert "7/7 veredictos correctos" in capsys.readouterr().out
    assert codigo == evaluar_casos.CODIGO_OK
