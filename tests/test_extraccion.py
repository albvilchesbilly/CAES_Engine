"""Pruebas del extractor por reglas (F0.7): cobertura por caso, cita obligatoria y trampas de docs/05 §4.3.

Comparten la ingesta cacheada con `test_ingesta.py` (los PDF se leen una sola vez por sesion).

Criterio de cobertura: para cada variable de `variables_consolidadas` del ground truth debe existir al menos
una evidencia con el mismo valor y, ademas, una evidencia por cada tipo de documento que el ground truth
espera **de los que estan presentes en el caso** (sin `tesseract`, el escaneo del caso G no se clasifica y su
tipo no cuenta: EVD-04 no es obligatorio y G debe dar el mismo resultado que A sin OCR).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from engine.extraccion import (
    VERSION_EXTRACTOR,
    Extractor,
    ExtractorReglas,
    candidatos_en_texto,
    categoria_de_linea,
    fecha_iso,
    numero_canonico,
    serie_de,
)
from tests.test_ingesta import documentos_de, evidencias_de, ground_truth

CASOS_CON_TODAS_LAS_VARIABLES = ("EXP001-A_completo", "EXP001-E_dos_motores", "EXP001-F_tres_motores")


def _tipos_presentes(caso: str) -> set[str]:
    return {doc.tipo for doc in documentos_de(caso) if doc.tipo}


def _evidencias_de(caso: str, variable: str, serie: str | None = None) -> list:
    return [
        e
        for e in evidencias_de(caso)
        if e.variable == variable and (serie is None or e.num_serie_motor == serie)
    ]


def _coincide(valor: str, esperado: str) -> bool:
    try:
        return Decimal(valor) == Decimal(esperado)
    except Exception:  # noqa: BLE001 - valores no numericos se comparan como texto
        return valor == esperado


def _comprobar_variable(caso: str, variable: str, declarado: dict, serie: str | None) -> None:
    evidencias = _evidencias_de(caso, variable, serie)
    esperado = declarado["valor"]
    tipos_esperados = {f["tipo"] for f in declarado.get("fuentes", [])}
    tipos_esperados |= {f["tipo"] for f in declarado.get("fuentes_declaradas", [])}
    tipos_esperados &= _tipos_presentes(caso)
    if esperado is None:
        if declarado.get("conflicto"):
            assert len({e.valor for e in evidencias}) > 1, f"{caso}/{variable}: falta el conflicto"
        else:
            assert not evidencias, f"{caso}/{variable}: no deberia haber evidencia"
        return
    assert evidencias, f"{caso}/{variable} ({serie}): sin evidencia"
    assert any(_coincide(e.valor, str(esperado)) for e in evidencias), (
        f"{caso}/{variable} ({serie}): {sorted({e.valor for e in evidencias})} != {esperado}"
    )
    obtenidas = {e.tipo_doc for e in evidencias}
    assert tipos_esperados <= obtenidas, (
        f"{caso}/{variable} ({serie}): faltan fuentes {sorted(tipos_esperados - obtenidas)}"
    )


@pytest.mark.parametrize("caso", CASOS_CON_TODAS_LAS_VARIABLES)
def test_todas_las_variables_de_calculo_salen_con_evidencia(caso: str) -> None:
    consolidadas = ground_truth(caso)["variables_consolidadas"]
    for variable, declarado in consolidadas["actuacion"].items():
        _comprobar_variable(caso, variable, declarado, None)
    for serie, variables in consolidadas["motores"].items():
        for variable, declarado in variables.items():
            _comprobar_variable(caso, variable, declarado, serie)


def test_el_caso_g_se_lee_igual_que_el_a_pese_al_desorden() -> None:
    """Mismo contenido repartido en 13 ficheros con otros nombres: mismos valores por variable."""

    def valores(caso: str) -> dict[str, set[str]]:
        interesantes = {"PM", "N1", "N2", "h_antes", "h_despues", "P_prom", "titular_nif", "n_motores"}
        salida: dict[str, set[str]] = {}
        for evidencia in evidencias_de(caso):
            if evidencia.variable in interesantes:
                salida.setdefault(evidencia.variable, set()).add(evidencia.valor)
        return salida

    a, g = valores("EXP001-A_completo"), valores("EXP001-G_desordenado")
    assert set(a) == set(g)
    for variable in a:
        assert {Decimal(v) if v.replace(".", "").isdigit() else v for v in a[variable]} == {
            Decimal(v) if v.replace(".", "").isdigit() else v for v in g[variable]
        }, variable


def test_en_el_caso_b_n2_es_declarado_y_no_hay_derivados_del_registro() -> None:
    caso = "EXP001-B_falta_registro"
    n2 = _evidencias_de(caso, "N2")
    assert n2, "N2 declarado en certificado y ficha debe estar"
    assert {e.tipo_evidencia for e in n2} == {"declarado"}
    assert {e.tipo_doc for e in n2} == {"certificado_instalador", "ficha_cumplimentada"}
    assert _evidencias_de(caso, "h_despues") == []
    assert _evidencias_de(caso, "registro.datos_canonicos") == []
    assert {e.tipo_evidencia for e in _evidencias_de(caso, "P_prom")} == {"declarado"}
    # sin registro, el certificado tampoco declara su huella: R-EVD-03 quedara NO_EVALUABLE
    assert _evidencias_de(caso, "registro.hash_declarado") == []
    assert _evidencias_de(caso, "registro.dias") == []


def test_en_el_caso_a_n2_derivado_y_declarado_conviven_marcados() -> None:
    n2 = _evidencias_de("EXP001-A_completo", "N2")
    por_tipo = {e.tipo_evidencia: e for e in n2}
    assert set(por_tipo) == {"declarado", "derivado"}
    assert por_tipo["derivado"].tipo_doc == "registro_funcionamiento"
    assert por_tipo["derivado"].interpretacion == "INT-03"
    assert por_tipo["derivado"].metodo == "xlsx"
    assert por_tipo["declarado"].interpretacion is None
    assert _evidencias_de("EXP001-A_completo", "h_despues")[0].interpretacion == "INT-04"


# ---------------------------------------------------------------------------
# Tablas antes que texto, cita obligatoria
# ---------------------------------------------------------------------------


def test_pm_del_caso_a_se_lee_de_las_tablas_no_del_texto() -> None:
    pm = _evidencias_de("EXP001-A_completo", "PM")
    nativas = [e for e in pm if e.metodo != "ocr"]
    assert nativas
    assert {e.metodo for e in nativas} == {"tabla"}
    assert all(e.confianza == Decimal(1) for e in nativas)


@pytest.mark.parametrize(
    "caso", ["EXP001-A_completo", "EXP001-B_falta_registro", "EXP001-F_tres_motores", "EXP001-G_desordenado"]
)
def test_toda_evidencia_lleva_cita_completa(caso: str) -> None:
    documentos = {doc.doc_id for doc in documentos_de(caso)}
    for evidencia in evidencias_de(caso):
        assert evidencia.doc_id in documentos, evidencia.variable
        assert evidencia.tipo_doc
        assert evidencia.pagina >= 0
        assert evidencia.texto_literal.strip(), evidencia.variable
        assert evidencia.extractor_version == VERSION_EXTRACTOR
        assert evidencia.tipo_evidencia in {"demostrado", "declarado", "derivado"}
        assert evidencia.confianza in {Decimal(1), Decimal("0.75")}
        assert isinstance(evidencia.valor, str) and evidencia.valor != ""


def test_el_texto_solo_actua_de_respaldo() -> None:
    """Si la tabla ya dio la variable, no se vuelve a emitir por regex con otro valor."""
    for evidencia in evidencias_de("EXP001-A_completo"):
        if evidencia.metodo == "regex":
            assert evidencia.variable in {
                "foto.antes",
                "foto.despues",
                "ficha_cumplimentada.firmada",
                "factura.menciona_motor_existente",
                "convenio.requisitos_presentes",
            }, evidencia.variable


# ---------------------------------------------------------------------------
# Trampas de docs/05 §4.3
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["EXP001-A_completo", "EXP001-E_dos_motores", "EXP001-G_desordenado"])
def test_las_perdidas_del_variador_nunca_se_emiten_como_p_ni_perdidas_ref(caso: str) -> None:
    variables = {e.variable for e in evidencias_de(caso)}
    assert "perdidas_ref_kw" not in variables
    assert "p" not in variables
    declaradas = _evidencias_de(caso, "perdidas_declaradas_variador")
    esperado = ground_truth(caso)["trampas"]["ficha_variador_declara_perdidas_kw"]
    if "ficha_tecnica_variador" in _tipos_presentes(caso):
        assert declaradas
        assert {Decimal(e.valor) for e in declaradas} == {Decimal(v) for v in esperado.values()}
        assert {e.tipo_evidencia for e in declaradas} == {"declarado"}


@pytest.mark.parametrize("caso", ["EXP001-A_completo", "EXP001-E_dos_motores"])
def test_las_lineas_de_factura_se_categorizan_por_su_cabeza(caso: str) -> None:
    import json

    lineas = _evidencias_de(caso, "factura.lineas")
    assert len(lineas) == 1
    obtenidas = json.loads(lineas[0].valor)
    esperadas = ground_truth(caso)["hechos_documentales"]["factura.lineas"]
    assert obtenidas == esperadas


def test_mencionar_un_motor_existente_no_convierte_la_linea_en_compra_de_motor() -> None:
    descripcion = (
        "Variador de frecuencia Variadores Ficticios Europa, S.L. modelo VFE-110-T4 (110 kW), "
        "nº serie VSD-SYN-0001 (instalación sobre motor existente MTR-SYN-0001)"
    )
    assert categoria_de_linea(descripcion) == "variador"
    instalacion = (
        "Instalación, parametrización y puesta en marcha del variador (1 motor(es) existente(s); "
        "no incluye suministro de motor ni de equipo accionado)"
    )
    assert categoria_de_linea(instalacion) == "instalacion"
    assert categoria_de_linea("Motor asíncrono trifásico 110 kW, nuevo") == "motor"
    assert categoria_de_linea("Bomba centrífuga BCN-250-400") == "bomba"
    assert categoria_de_linea("Portes y embalaje") == "otro"


def test_el_caso_d_declara_un_ahorro_que_el_motor_no_debe_usar() -> None:
    declarado = _evidencias_de("EXP001-D_fuera_ambito", "ficha_cumplimentada.ahorro_declarado_kwh")
    assert declarado and declarado[0].tipo_evidencia == "declarado"
    assert _evidencias_de("EXP001-A_completo", "ficha_cumplimentada.ahorro_declarado_kwh") == []


def test_el_caso_c_produce_dos_valores_de_pm_sin_elegir() -> None:
    valores = {e.valor for e in _evidencias_de("EXP001-C_contradictorio", "PM") if e.metodo != "ocr"}
    assert valores == {"110", "90"}


# ---------------------------------------------------------------------------
# La spec manda sobre el lexico
# ---------------------------------------------------------------------------


def test_solo_entran_las_fuentes_que_la_spec_declara(spec_ind240) -> None:
    caso = "EXP001-A_completo"
    # P_prom solo cruza con el certificado, aunque la ficha cumplimentada tambien lo declara
    assert {e.tipo_doc for e in _evidencias_de(caso, "P_prom")} == {
        "certificado_instalador",
        "registro_funcionamiento",
    }
    # h_antes solo del registro de horas previo, aunque la ficha lo repite
    assert {e.tipo_doc for e in _evidencias_de(caso, "h_antes")} == {"registro_horas_previo"}
    # num_serie_motor no sale de la factura (la spec no la declara como fuente)
    assert "factura" not in {e.tipo_doc for e in _evidencias_de(caso, "num_serie_motor")}
    for variable in ("PM", "N1", "N2", "h_antes", "tipo_equipo_accionado", "regimen_previo"):
        declaracion = spec_ind240.variables[variable]
        admitidas = set(declaracion.get("fuentes", [])) | set(declaracion.get("cruce_con", []))
        derivacion = declaracion.get("derivacion") or {}
        if isinstance(derivacion.get("fuente"), str):
            admitidas.add(derivacion["fuente"])
        assert {e.tipo_doc for e in _evidencias_de(caso, variable)} <= admitidas, variable


def test_los_requisitos_del_convenio_salen_de_la_spec(spec_ind240) -> None:
    import json

    evidencia = _evidencias_de("EXP001-A_completo", "convenio.requisitos_presentes")[0]
    declarados = next(d["requisitos"] for d in spec_ind240.documentacion if d.get("tipo") == "convenio_cae")
    assert json.loads(evidencia.valor) == list(declarados)


def test_n_motores_por_fuente_es_coherente_en_todos_los_casos() -> None:
    for caso in (
        "EXP001-A_completo",
        "EXP001-E_dos_motores",
        "EXP001-F_tres_motores",
        "EXP001-G_desordenado",
    ):
        esperado = str(ground_truth(caso)["n_motores"])
        evidencias = _evidencias_de(caso, "n_motores")
        assert evidencias
        assert {e.valor for e in evidencias} == {esperado}, caso
        assert "registro_funcionamiento" in {e.tipo_doc for e in evidencias}


def test_el_enumerado_se_valida_contra_la_spec() -> None:
    assert {e.valor for e in _evidencias_de("EXP001-A_completo", "tipo_equipo_accionado")} == {
        "bomba_dinamica"
    }
    assert {e.valor for e in _evidencias_de("EXP001-D_fuera_ambito", "tipo_equipo_accionado")} == {
        "bomba_desplazamiento_positivo"
    }


# ---------------------------------------------------------------------------
# Normalizacion de valores
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("110 kW", "110"),
        ("1.485 rpm", "1485"),
        ("6.000 h", "6000"),
        ("60,0 kW", "60.0"),
        ("3,90 kW", "3.90"),
        ("305.829 kWh", "305829"),
        ("97,5 %", "97.5"),
        ("sin numero", None),
    ],
)
def test_numeros_en_formato_espanol(crudo: str, esperado: str | None) -> None:
    assert numero_canonico(crudo) == esperado


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [("02/03/2026", "2026-03-02"), ("10/02/2026", "2026-02-10"), ("2026-03-05", "2026-03-05"), ("", None)],
)
def test_fechas_a_iso(crudo: str, esperado: str | None) -> None:
    assert fecha_iso(crudo) == esperado


def test_numeros_de_serie() -> None:
    assert serie_de("nº serie VSD-SYN-0001 (instalación)") == "VSD-SYN-0001"
    assert serie_de("MTR-SYN-0001") == "MTR-SYN-0001"
    assert serie_de("sin serie") is None


def test_una_etiqueta_sin_valor_en_su_linea_toma_la_siguiente() -> None:
    lineas = ["Nº de serie del variador", "VSD-SYN-0001", "Potencia nominal", "110 kw"]
    candidatos = candidatos_en_texto(lineas, "no de serie del variador")
    assert candidatos[0][0] == "VSD-SYN-0001"
    assert "Nº de serie del variador" in candidatos[0][1]


def test_una_etiqueta_no_casa_con_la_parecida() -> None:
    lineas = ["Fecha de inicio de la actuación 10/02/2026", "Fecha de fin de la actuación 02/03/2026"]
    assert candidatos_en_texto(lineas, "fecha de fin de la actuacion")[0][0] == "02/03/2026"
    assert candidatos_en_texto(lineas, "fecha de inicio de la actuacion")[0][0] == "10/02/2026"


# ---------------------------------------------------------------------------
# Interfaz `Extractor`
# ---------------------------------------------------------------------------


def test_extractor_reglas_cumple_la_interfaz(spec_ind240) -> None:
    extractor: Extractor = ExtractorReglas()
    assert extractor.version == "reglas-0.1.0"
    assert isinstance(extractor, Extractor)


def test_un_documento_sin_tipo_no_produce_evidencias(spec_ind240) -> None:
    notas = next(d for d in documentos_de("EXP001-G_desordenado") if d.nombre == "notas.pdf")
    assert ExtractorReglas().extraer(notas, spec_ind240) == []


def test_un_pdf_combinado_no_se_extrae_dos_veces(spec_ind240) -> None:
    """El combinado no aporta evidencias: las aportan sus partes (si no, todo saldria duplicado)."""
    combinado = next(
        d for d in documentos_de("EXP001-G_desordenado") if d.nombre == "doc1.pdf" and d.es_combinado
    )
    assert ExtractorReglas().extraer(combinado, spec_ind240) == []
    nif = _evidencias_de("EXP001-G_desordenado", "titular_nif")
    assert len(nif) == len({(e.doc_id, e.pagina) for e in nif})
    assert {e.tipo_doc for e in nif} == {
        "ficha_cumplimentada",
        "declaracion_responsable",
        "factura",
        "convenio_cae",
    }


def test_las_partes_citan_la_pagina_absoluta_del_fichero_original() -> None:
    evidencias = [
        e
        for e in evidencias_de("EXP001-G_desordenado")
        if e.variable == "convenio.fecha_firma" or e.variable == "titular_nif"
    ]
    convenio = next(e for e in evidencias if e.tipo_doc == "convenio_cae")
    assert convenio.pagina >= 3  # el convenio empieza en la pagina 3 de doc1.pdf


# ---------------------------------------------------------------------------
# OCR (se salta sin tesseract)
# ---------------------------------------------------------------------------


@pytest.mark.ocr
@pytest.mark.skipif(
    not __import__("engine.ingesta", fromlist=["hay_tesseract"]).hay_tesseract(),
    reason="tesseract no esta instalado",
)
def test_con_ocr_el_escaneo_de_g_aporta_el_numero_de_serie_del_variador() -> None:
    evidencias = [
        e for e in evidencias_de("EXP001-G_desordenado", True) if e.tipo_doc == "ficha_tecnica_variador"
    ]
    assert evidencias
    assert {e.metodo for e in evidencias} == {"ocr"}
    assert all(e.confianza == Decimal("0.75") for e in evidencias)
    assert "VSD-SYN-0001" in {e.valor for e in evidencias if e.variable == "num_serie_variador"}
