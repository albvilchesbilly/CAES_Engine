"""Banco de pruebas del material sintético de S3.5 (ADR-010 §5, contrato C12).

Comprueba lo que hace utilizable ese material: los tres documentos se generan de forma **reproducible**,
llevan la marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS" en cada página, sus motivos salen enteros del PDF, lo
que el ground truth dice que debe reconocerse **existe de verdad** en `spec/IND240_v1.1.yaml`, el motivo no
mapeable no cita ni regla ni documento (si lo citara, el intérprete no tendría a quién escalar), y el
expediente cumple lo que lo hace expediente: tres actuaciones distintas con misma CCAA, año, sector y
verificador (`CLAUDE.md` §3).

Estos tests no prueban el intérprete (`engine/requerimientos.py`): prueban el material con el que se le juzga.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pdfplumber
import pytest
import yaml

from generator import requerimientos
from generator.casos import caso as caso_del_banco
from generator.marcas import MARCA
from generator.modelo_requerimiento import ALCANCE_DE_ORIGEN, Motivo, Requerimiento, normalizar

RAIZ = Path(__file__).resolve().parents[1]
EXPEDIENTES = RAIZ / "expedientes"
ESTADOS_PLATAFORMA = RAIZ / "engine" / "estados_plataforma.yaml"

ORIGENES_ESPERADOS = ("verificador", "GA", "CN")
PATRON_REGLA = re.compile(r"\bR-[A-Z]{3}-\d{2}\b")
# Cómo se nombra en prosa cada tipo documental de la ficha: lo que un léxico honesto puede reconocer y lo
# que el motivo no mapeable no debe contener.
FRASES_TIPO_DOCUMENTAL = (
    "ficha ind240",
    "declaración responsable",
    "factura",
    "informe fotográfico",
    "certificado de la empresa instaladora",
    "certificado de técnico competente",
    "registro de parámetros de funcionamiento",
    "registro de horas",
    "ficha técnica del motor",
    "ficha técnica del variador",
    "ficha técnica del equipo accionado",
    "convenio cae",
)


@pytest.fixture(scope="module")
def material() -> requerimientos.MaterialGenerado:
    return requerimientos.generar()


@pytest.fixture(scope="module")
def salida(tmp_path_factory, material) -> Path:
    destino = tmp_path_factory.mktemp("s35")
    requerimientos.escribir(destino, material)
    return destino / requerimientos.CARPETA_REQUERIMIENTOS


@pytest.fixture(scope="module")
def ground_truth(salida: Path) -> dict:
    return json.loads((salida / requerimientos.FICHERO_GROUND_TRUTH).read_text("utf-8"))


def _norma(texto: str) -> str:
    return " ".join((texto or "").split())


def _celdas_numeradas(ruta: Path) -> list[str]:
    """Texto de las filas 'nº | motivo' de las tablas del PDF, normalizado."""
    with pdfplumber.open(ruta) as pdf:
        return [
            _norma(fila[1])
            for pagina in pdf.pages
            for tabla in pagina.extract_tables()
            for fila in tabla
            if fila and fila[0] and fila[0].strip().isdigit()
        ]


def _texto_paginas(ruta: Path) -> list[str]:
    with pdfplumber.open(ruta) as pdf:
        return [pagina.extract_text() or "" for pagina in pdf.pages]


# ---------------------------------------------------------------------------
# Los tres documentos: uno por origen, con su marca
# ---------------------------------------------------------------------------


def test_tres_requerimientos_uno_por_origen(material, salida: Path) -> None:
    assert tuple(g.requerimiento.origen for g in material.requerimientos) == ORIGENES_ESPERADOS
    ficheros = sorted(p.name for p in salida.iterdir())
    assert ficheros == sorted(
        [g.nombre for g in material.requerimientos] + [requerimientos.FICHERO_GROUND_TRUTH]
    )
    literales = {g.requerimiento.origen: g.requerimiento.literal_plataforma for g in material.requerimientos}
    assert literales == {
        "verificador": "PDTE_RECTIFICACION_VER",
        "GA": "REQUERIDO_GA",
        "CN": "REQUERIDO_CN",
    }
    cn = material.generado("REQ-SYN-2026-003").requerimiento
    assert cn.ronda == 2 and cn.fase == "3B", "la CN admite una segunda vuelta (docs/02 §5.6)"


def test_marca_sintetica_en_cada_pagina_de_cada_requerimiento(material, salida: Path) -> None:
    for g in material.requerimientos:
        paginas = _texto_paginas(salida / g.nombre)
        assert paginas, g.nombre
        for numero, texto in enumerate(paginas, 1):
            assert MARCA in texto, f"{g.nombre} página {numero} sin la marca sintética"


def test_marca_y_organismos_ficticios_en_el_ground_truth(ground_truth) -> None:
    """Todo inventado: organismos que dicen serlo y NIF con control válido pero ficticios."""
    from generator.modelo_caso import cif_empresa

    assert ground_truth["marca"] == MARCA
    organismos = [r["organismo"] for r in ground_truth["requerimientos"]]
    organismos.append(ground_truth["expediente"]["verificador"])
    for organismo in organismos:
        assert "ficticia" in organismo["nombre"] or "ficticio" in organismo["nombre"], organismo["nombre"]
        assert (
            "Sintétic" in organismo["nombre"]
            or "Sintétic" in organismo["codigo"]
            or ("SYN" in organismo["codigo"])
        )
        nif = organismo["nif"]
        assert nif == cif_empresa(nif[0], int(nif[1:8])), nif
    identidades = [a["actuacion_id"] for a in ground_truth["expediente"]["actuaciones"]]
    identidades += [r["id"] for r in ground_truth["requerimientos"]]
    assert all("SYN" in i for i in identidades), identidades


def test_los_motivos_salen_enteros_del_pdf(material, salida: Path) -> None:
    """Van en tabla a propósito: la marca de agua desordena el texto plano (docs/05 §4.4.1)."""
    for g in material.requerimientos:
        celdas = _celdas_numeradas(salida / g.nombre)
        assert len(celdas) == len(g.requerimiento.motivos)
        for motivo in g.requerimiento.motivos:
            assert _norma(motivo.texto) in celdas, f"{g.nombre}: el motivo {motivo.numero} llega partido"


def test_el_informe_sha256_es_el_del_pdf_generado(material, salida: Path, ground_truth) -> None:
    """R-REQ-01: un requerimiento externo sin informe es un rumor; aquí los tres traen su huella."""
    huellas = {r["id"]: r["informe_sha256"] for r in ground_truth["requerimientos"]}
    assert all(huellas.values())
    for g in material.requerimientos:
        en_disco = hashlib.sha256((salida / g.nombre).read_bytes()).hexdigest()
        assert huellas[g.requerimiento.id] == en_disco == g.sha256


# ---------------------------------------------------------------------------
# Los motivos: qué debe reconocerse de cada uno
# ---------------------------------------------------------------------------


def test_cobertura_regla_documento_y_nada(ground_truth) -> None:
    cobertura = ground_truth["cobertura_de_motivos"]
    assert len(cobertura["regla"]) >= 1 and len(cobertura["documento"]) >= 1
    assert len(cobertura["nada"]) >= 1, "sin un motivo que escale, el banco mentiría (ADR-010 §5)"
    assert cobertura["nada"] == ["REQ-SYN-2026-003#1"]
    tipos = {m["tipo_esperado"] for r in ground_truth["requerimientos"] for m in r["motivos"]}
    assert tipos == {"regla", "documento", "nada"}


def test_las_reglas_esperadas_existen_en_la_spec(ground_truth, spec_ind240) -> None:
    reglas = {r["id"] for r in spec_ind240.datos["reglas"]}
    citadas = {
        m["regla_esperada"]
        for r in ground_truth["requerimientos"]
        for m in r["motivos"]
        if m["regla_esperada"]
    }
    assert citadas and citadas <= reglas, citadas - reglas


def test_los_documentos_esperados_son_tipos_reales_de_la_spec(ground_truth, spec_ind240) -> None:
    tipos = {d["tipo"] for d in spec_ind240.datos["documentacion"]}
    citados = {
        m["documento_esperado"]
        for r in ground_truth["requerimientos"]
        for m in r["motivos"]
        if m["documento_esperado"]
    }
    assert citados and citados <= tipos, citados - tipos


def test_cada_pista_esta_literalmente_en_su_motivo(ground_truth) -> None:
    """Sin cita no hay item (ADR-010 §3): la expectativa se apoya en el texto, no en una deducción."""
    for r in ground_truth["requerimientos"]:
        for m in r["motivos"]:
            texto = normalizar(m["texto"])
            assert (m["tipo_esperado"] == "nada") == (not m["pistas"])
            for pista in m["pistas"]:
                assert normalizar(pista) in texto, (r["id"], m["numero"], pista)


def test_el_motivo_facil_cita_el_identificador_de_la_regla(ground_truth) -> None:
    motivo = ground_truth["requerimientos"][0]["motivos"][0]
    assert motivo["dificultad"] == "explicita" and motivo["regla_esperada"] == "R-CON-06"
    assert "R-CON-06" in motivo["texto"]


def test_el_motivo_lexico_no_cita_ningun_identificador(ground_truth) -> None:
    """El de la GA se reconoce por vocabulario o no se reconoce: es el motivo de dificultad media."""
    motivo = next(
        m for r in ground_truth["requerimientos"] for m in r["motivos"] if m["regla_esperada"] == "R-EVD-03"
    )
    assert motivo["dificultad"] == "lexica"
    assert not PATRON_REGLA.search(motivo["texto"])


def test_el_motivo_no_mapeable_no_cita_regla_ni_documento(ground_truth) -> None:
    """Si citara algo, dejaría de medir lo que mide: que el intérprete escale en vez de inventar."""
    motivo = next(
        m for r in ground_truth["requerimientos"] for m in r["motivos"] if m["tipo_esperado"] == "nada"
    )
    assert motivo["regla_esperada"] is None and motivo["documento_esperado"] is None
    texto = normalizar(motivo["texto"])
    assert not PATRON_REGLA.search(motivo["texto"])
    for frase in FRASES_TIPO_DOCUMENTAL:
        assert normalizar(frase) not in texto, f"el motivo no mapeable nombra {frase!r}"


def test_las_frases_documentales_del_test_aparecen_donde_deben(ground_truth) -> None:
    """Guarda del test anterior: la lista de frases sirve de algo porque los motivos fáciles sí las usan."""
    mapeables = normalizar(
        " ".join(
            m["texto"]
            for r in ground_truth["requerimientos"]
            for m in r["motivos"]
            if m["tipo_esperado"] == "documento"
        )
    )
    usadas = [f for f in FRASES_TIPO_DOCUMENTAL if normalizar(f) in mapeables]
    assert set(usadas) == {"certificado de técnico competente", "ficha técnica del equipo accionado"}


def test_interpretacion_esperada_y_confirmacion_humana(ground_truth) -> None:
    por_id = {r["id"]: r for r in ground_truth["requerimientos"]}
    for r in ground_truth["requerimientos"]:
        esperada = r["interpretacion_esperada"]
        assert esperada["confirmacion_humana_obligatoria"] is True, "R-REQ-02"
        mapeables = [m for m in r["motivos"] if m["tipo_esperado"] != "nada"]
        assert len(esperada["items"]) == len(mapeables)
        assert all(i["texto_literal"] for i in esperada["items"])
    assert por_id["REQ-SYN-2026-003"]["interpretacion_esperada"] == {
        "items": [],
        "motivos_sin_mapear": [1],
        "escala_a_humano": True,
        "confirmacion_humana_obligatoria": True,
    }
    assert por_id["REQ-SYN-2026-001"]["interpretacion_esperada"]["escala_a_humano"] is False


# ---------------------------------------------------------------------------
# El expediente de tres actuaciones y el contagio
# ---------------------------------------------------------------------------


def test_expediente_de_tres_actuaciones_con_las_cuatro_claves(material, ground_truth) -> None:
    expediente = ground_truth["expediente"]
    casos = [caso_del_banco(a["caso"]) for a in expediente["actuaciones"]]
    assert len(casos) == 3, "con menos de tres, contagiar y no contagiar son indistinguibles"
    assert expediente["claves_de_agrupacion"] == ["ccaa", "anio", "sector", "verificador"]
    assert {c.fechas.fin.year for c in casos} == {expediente["anio"]}
    assert len({c.localizacion.referencia_catastral for c in casos}) == 1, (
        "misma localización, luego misma CCAA"
    )
    assert [a.caso_id for a in material.expediente.actuaciones] == ["A", "E", "F"]
    assert expediente["sector"] == "industrial"
    identidades = [a["actuacion_id"] for a in expediente["actuaciones"]]
    codigos = [a["codigo_identificativo_propio"] for a in expediente["actuaciones"]]
    assert len(set(identidades)) == len(set(codigos)) == 3
    assert all(a["estado_plataforma"] == "VERIFICADA_FAVORABLE" for a in expediente["actuaciones"])
    assert all(a["veredicto_esperado"] == "PREVALIDADO" for a in expediente["actuaciones"])
    assert expediente["nota_solape"], "el solape de motor entre A, E y F se declara, no se esconde"


def test_el_expediente_reutiliza_los_casos_del_banco_sin_tocarlos(ground_truth) -> None:
    for actuacion in ground_truth["expediente"]["actuaciones"]:
        carpeta = EXPEDIENTES / actuacion["carpeta"]
        assert carpeta.is_dir(), carpeta
        commiteado = json.loads(
            (EXPEDIENTES / "_resultados_esperados" / f"{actuacion['carpeta']}.json").read_text("utf-8")
        )
        assert commiteado["aetotal_esperado"]["exacto"] == actuacion["aetotal_exacto"]
        assert commiteado["aetotal_esperado"]["cae"] == actuacion["aetotal_cae"]
        assert commiteado["veredicto_esperado"] == actuacion["veredicto_esperado"]
        assert commiteado["n_motores"] == actuacion["n_motores"]


def test_el_contagio_alcanza_a_quien_debe(ground_truth) -> None:
    """Verificador: solo su actuación. GA y CN: las tres (docs/02 §5.6, docs/03 §10.5)."""
    todas = {a["actuacion_id"] for a in ground_truth["expediente"]["actuaciones"]}
    alcance = {
        r["origen"]: {c["actuacion_id"] for c in r["contagio_esperado"]}
        for r in ground_truth["requerimientos"]
    }
    assert alcance["verificador"] == {"ACT-SYN-2026-001"}
    assert alcance["GA"] == alcance["CN"] == todas
    for r in ground_truth["requerimientos"]:
        directas = [c for c in r["contagio_esperado"] if c["afectada_directamente"]]
        assert [c["actuacion_id"] for c in directas] == [r["actuacion_id"]]
        assert all(c["ciclo_esperado"] == "PENDIENTE_SUBSANACION" for c in r["contagio_esperado"])
    assert {r["actuacion_id"] for r in ground_truth["requerimientos"]} == todas, (
        "cada origen entra por una actuación distinta: así el contagio no se confunde con la coincidencia"
    )


def test_alcance_y_literales_coinciden_con_estados_plataforma(ground_truth) -> None:
    """El contagio lo decide la tabla, no el generator (ADR-010 §2, regla 3): los literales son los suyos."""
    tabla = yaml.safe_load(ESTADOS_PLATAFORMA.read_text("utf-8"))
    estados = {e["literal"]: e for e in tabla["estados"]}
    for r in ground_truth["requerimientos"]:
        estado = estados[r["literal_plataforma"]]
        assert estado["ciclo"] == "PENDIENTE_SUBSANACION"
        assert estado["origen_subsanacion"] == r["origen"]
        assert estado["alcance"] == ALCANCE_DE_ORIGEN[r["origen"]] == r["alcance"]


# ---------------------------------------------------------------------------
# Reproducibilidad y modelo
# ---------------------------------------------------------------------------


def test_reproducible_dos_generaciones_mismos_bytes(material) -> None:
    otra = requerimientos.generar()
    assert [(g.nombre, g.sha256) for g in otra.requerimientos] == [
        (g.nombre, g.sha256) for g in material.requerimientos
    ]
    assert otra.ground_truth == material.ground_truth


def test_lo_commiteado_coincide_con_la_regeneracion(material, salida: Path) -> None:
    commiteado = EXPEDIENTES / requerimientos.CARPETA_REQUERIMIENTOS
    if not commiteado.is_dir():
        pytest.skip("expedientes/_requerimientos/ no generado en este clon")
    assert sorted(p.name for p in commiteado.iterdir()) == sorted(p.name for p in salida.iterdir())
    for p in sorted(salida.iterdir()):
        assert (commiteado / p.name).read_bytes() == p.read_bytes(), (
            f"{p.name} difiere: regenera con `python -m generator.generar` y commitea"
        )


def test_el_modelo_rechaza_expectativas_sin_cita() -> None:
    with pytest.raises(ValueError):  # pista que no está en el texto
        Motivo(
            numero=1,
            texto="Falta el convenio.",
            dificultad="lexica",
            documento_esperado="convenio_cae",
            pistas=("registro de funcionamiento",),
        )
    with pytest.raises(ValueError):  # no mapeable pero con regla
        Motivo(numero=1, texto="Prosa.", dificultad="no_mapeable", regla_esperada="R-DOC-01")
    with pytest.raises(ValueError):  # mapeable sin regla ni documento
        Motivo(numero=1, texto="Prosa.", dificultad="lexica", pistas=("Prosa",))
    with pytest.raises(ValueError):  # 'explicita' sin el identificador en el texto
        Motivo(
            numero=1,
            texto="El ahorro no cuadra.",
            dificultad="explicita",
            regla_esperada="R-CON-06",
            pistas=("ahorro",),
        )


def test_el_modelo_exige_expediente_en_ga_y_cn() -> None:
    base = requerimientos.REQUERIMIENTO_GA
    with pytest.raises(ValueError):
        Requerimiento(
            id=base.id,
            origen="GA",
            organismo=base.organismo,
            literal_plataforma=base.literal_plataforma,
            fase=base.fase,
            asunto=base.asunto,
            referencia_oficial=base.referencia_oficial,
            recibido_en=base.recibido_en,
            plazo_dias=base.plazo_dias,
            actuacion_id=base.actuacion_id,
            expediente_id=None,
            grupo_id=None,
            motivos=base.motivos,
            preambulo=base.preambulo,
            advertencia=base.advertencia,
        )
