"""Pruebas de ingesta, clasificacion y lectura del registro (F0.6 y F0.7).

Lo que esta suite protege (docs/05 §8): SHA-256 de todo fichero **antes** de cualquier transformacion;
separacion de PDF combinados conservando el hash del original y el de cada parte; vinculacion por huella
cuando el nombre del fichero no coincide (caso G); clasificacion lexica con confianza y avisos; EXIF leido;
y el registro xlsx dando N2, P_prom, h_despues y su huella.

Las pruebas con OCR llevan `@pytest.mark.ocr` y se saltan si `tesseract` no esta instalado (Billy trabaja en
Windows y el clon limpio de `docs/05` §8.2 no lo tiene). Ninguna de ellas es imprescindible para el veredicto.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from engine.clasificacion import AVISO_NO_CLASIFICADO, clasificar, clasificar_todos, tipo_por_titulo
from engine.extraccion import extraer_todos
from engine.ingesta import (
    TIPO_COMBINADO,
    Documento,
    avisos_de,
    doc_id_parte,
    documentos_legibles,
    hay_tesseract,
    ingestar,
    ingestar_fichero,
    sha256_bytes,
)
from engine.registro_xlsx import leer_registro

RAIZ = Path(__file__).resolve().parents[1]
EXPEDIENTES = RAIZ / "expedientes"
ESPERADOS = EXPEDIENTES / "_resultados_esperados"
CASOS = tuple(sorted(p.stem for p in ESPERADOS.glob("EXP001-*.json")))

sin_ocr = pytest.mark.skipif(not hay_tesseract(), reason="tesseract no esta instalado")


@cache
def ground_truth(caso: str) -> dict:
    return json.loads((ESPERADOS / f"{caso}.json").read_text(encoding="utf-8"))


@cache
def _spec():
    from engine.spec_registry import cargar_spec

    return cargar_spec(RAIZ / "spec" / "IND240_v1.1.yaml")


@cache
def _documentos(caso: str, ocr: bool) -> tuple[Documento, ...]:
    return tuple(clasificar_todos(ingestar(EXPEDIENTES / caso, ocr=ocr), _spec()))


@cache
def _evidencias(caso: str, ocr: bool) -> tuple:
    return tuple(extraer_todos(list(_documentos(caso, ocr)), _spec()))


def documentos_de(caso: str, ocr: bool = False) -> tuple[Documento, ...]:
    """Ingesta + clasificacion de un caso (cacheada: la suite no vuelve a leer los PDF)."""
    return _documentos(caso, ocr)


def evidencias_de(caso: str, ocr: bool = False) -> tuple:
    """Evidencias del caso; comparte los `Documento` con `documentos_de` (y por tanto sus avisos)."""
    return _evidencias(caso, ocr)


def originales(documentos) -> list[Documento]:
    """Documentos que corresponden a un fichero real (sin las partes de un combinado)."""
    return [doc for doc in documentos if not doc.es_parte]


# ---------------------------------------------------------------------------
# Huellas: SHA-256 antes de cualquier transformacion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_sha256_de_cada_fichero_coincide_con_el_ground_truth(caso: str) -> None:
    esperados = {d["fichero"]: d["sha256"] for d in ground_truth(caso)["documentos"]}
    obtenidos = {doc.nombre: doc.sha256 for doc in originales(documentos_de(caso))}
    assert obtenidos == esperados


@pytest.mark.parametrize("caso", CASOS)
def test_sha256_es_el_de_los_bytes_del_fichero(caso: str) -> None:
    for doc in originales(documentos_de(caso)):
        assert doc.sha256 == hashlib.sha256(doc.ruta.read_bytes()).hexdigest()
        assert doc.bytes == len(doc.ruta.read_bytes())


def test_el_hash_no_cambia_al_transformar_el_documento() -> None:
    """Rotar, pasar OCR o reprocesar un PDF no toca la huella: se calcula antes de abrir el fichero."""
    ruta = EXPEDIENTES / "EXP001-G_desordenado" / "scan.pdf"
    huella = sha256_bytes(ruta.read_bytes())
    sin_reconocer = ingestar_fichero(ruta, ocr=False)[0]
    reconocido = ingestar_fichero(ruta, ocr=True)[0]
    assert sin_reconocer.sha256 == reconocido.sha256 == huella
    assert reconocido.doc_id == huella
    # el OCR (si lo hay) cambia el texto de la pagina, nunca la huella
    assert sin_reconocer.paginas[0].texto != reconocido.paginas[0].texto or not hay_tesseract()


def test_el_hash_no_depende_del_nombre_del_fichero(tmp_path: Path) -> None:
    """Renombrar un fichero no cambia nada (propiedad metamorfica de docs/05 §6)."""
    original = EXPEDIENTES / "EXP001-A_completo" / "06_registro_funcionamiento_MTR-SYN-0001.xlsx"
    copia = tmp_path / "cualquier_nombre.xlsx"
    copia.write_bytes(original.read_bytes())
    assert ingestar_fichero(copia)[0].sha256 == ingestar_fichero(original)[0].sha256


# ---------------------------------------------------------------------------
# Clasificacion
# ---------------------------------------------------------------------------


def test_caso_a_clasifica_los_once_documentos_con_confianza(spec_ind240) -> None:
    documentos = documentos_de("EXP001-A_completo")
    assert len(documentos) == 11
    esperado = {d["fichero"]: d["tipo"] for d in ground_truth("EXP001-A_completo")["documentos"]}
    for doc in documentos:
        assert doc.tipo == esperado[doc.nombre], doc.nombre
        assert doc.confianza_tipo is not None and doc.confianza_tipo > 0
        assert isinstance(doc.confianza_tipo, Decimal)
    assert avisos_de(documentos) == []


@pytest.mark.parametrize("caso", CASOS)
def test_cada_documento_se_clasifica_como_dice_el_ground_truth(caso: str) -> None:
    """Tipo por fichero en los 7 casos (sin OCR: el escaneo de G queda sin clasificar, y el GT lo admite)."""
    esperado = {d["fichero"]: d["tipo"] for d in ground_truth(caso)["documentos"]}
    for doc in originales(documentos_de(caso)):
        if doc.nombre == "scan.pdf" and not doc.paginas[0].texto:
            continue  # sin OCR no hay nada que clasificar; EVD-04 no es obligatorio
        assert doc.tipo == esperado[doc.nombre], doc.nombre


def test_documento_irrelevante_queda_sin_clasificar_con_aviso() -> None:
    documentos = {doc.nombre: doc for doc in documentos_de("EXP001-G_desordenado")}
    notas = documentos["notas.pdf"]
    assert notas.tipo is None
    assert notas.confianza_tipo == Decimal(0)
    assert any(aviso.startswith(AVISO_NO_CLASIFICADO) for aviso in notas.avisos)
    foto = documentos["foto4.jpg"]
    assert foto.tipo is None
    assert any(aviso.startswith(AVISO_NO_CLASIFICADO) for aviso in foto.avisos)


def test_fotos_sueltas_se_clasifican_por_exif() -> None:
    documentos = {doc.nombre: doc for doc in documentos_de("EXP001-G_desordenado")}
    esperado = {"foto1.jpg": "foto_antes", "foto2.jpg": "foto_despues", "foto3.jpg": "placa"}
    for nombre, subtipo in esperado.items():
        doc = documentos[nombre]
        assert doc.tipo == "informe_fotografico"
        assert doc.subtipo == subtipo
        assert "DOCUMENTO SINT" in doc.exif["descripcion"]
        assert any("exif" in aviso for aviso in doc.avisos)


def test_el_xlsx_se_clasifica_por_su_estructura_no_por_su_nombre() -> None:
    """`datos.xlsx` (G) y `06_registro_funcionamiento_...xlsx` (A) dan el mismo tipo."""
    generico = next(d for d in documentos_de("EXP001-G_desordenado") if d.nombre == "datos.xlsx")
    explicito = next(d for d in documentos_de("EXP001-A_completo") if d.formato == "xlsx")
    assert generico.tipo == explicito.tipo == "registro_funcionamiento"
    assert generico.paginas == []  # el contenido lo lee registro_xlsx


def test_tipo_por_titulo_distingue_registro_previo_de_registro_de_funcionamiento() -> None:
    tipo, confianza = tipo_por_titulo("Registro de horas de funcionamiento previo a la actuación – motor X")
    assert tipo == "registro_horas_previo"
    assert confianza > 0
    assert tipo_por_titulo("Acta de reunión – Comité de mantenimiento") == (None, Decimal(0))


def test_clasificar_no_lanza_con_un_fichero_desconocido(tmp_path: Path, spec_ind240) -> None:
    ruta = tmp_path / "cualquiera.txt"
    ruta.write_text("contenido sin relacion", encoding="utf-8")
    doc = clasificar(ingestar_fichero(ruta)[0], spec_ind240)
    assert doc.formato == "otro"
    assert doc.tipo is None
    assert doc.avisos


# ---------------------------------------------------------------------------
# Separacion de PDF combinados
# ---------------------------------------------------------------------------


def test_el_pdf_combinado_de_g_produce_tres_partes() -> None:
    documentos = documentos_de("EXP001-G_desordenado")
    combinado = next(d for d in documentos if d.nombre == "doc1.pdf" and d.tipo == TIPO_COMBINADO)
    esperado = next(
        d for d in ground_truth("EXP001-G_desordenado")["documentos"] if d["fichero"] == "doc1.pdf"
    )
    partes = [d for d in documentos if d.origen == combinado.sha256]

    assert combinado.sha256 == esperado["sha256"]  # el original conserva su huella
    assert combinado.tipo == esperado["tipo"] == TIPO_COMBINADO
    assert [p.doc_id for p in partes] == list(combinado.partes)
    assert [p.tipo for p in partes] == [p["tipo"] for p in esperado["partes"]]
    for parte, parte_esperada in zip(partes, esperado["partes"], strict=True):
        rango = (parte_esperada["pagina_inicio"], parte_esperada["pagina_fin"])
        assert parte.rango_paginas == rango
        assert parte.doc_id == doc_id_parte(combinado.sha256, *rango)
        assert parte.doc_id != parte.sha256  # la parte tiene identidad propia
        assert parte.sha256 == combinado.sha256  # y conserva la huella del original
        assert [p.numero for p in parte.paginas] == list(range(rango[0], rango[1] + 1))


def test_la_separacion_deja_aviso_con_los_tipos() -> None:
    avisos = avisos_de(documentos_de("EXP001-G_desordenado"))
    separado = [a for a in avisos if a.startswith("pdf_separado")]
    assert len(separado) == 1
    for tipo in ("ficha_cumplimentada", "declaracion_responsable", "convenio_cae"):
        assert tipo in separado[0]


def test_un_pdf_de_un_solo_documento_no_se_separa() -> None:
    """El convenio del caso A tiene dos paginas y un solo titulo: no se parte."""
    documentos = ingestar_fichero(EXPEDIENTES / "EXP001-A_completo" / "11_convenio_cae.pdf", ocr=False)
    assert len(documentos) == 1
    assert documentos[0].partes == ()
    assert len(documentos[0].paginas) == 2


def test_documentos_legibles_sustituye_el_combinado_por_sus_partes() -> None:
    documentos = documentos_de("EXP001-G_desordenado")
    legibles = documentos_legibles(documentos)
    assert all(d.tipo != TIPO_COMBINADO for d in legibles)
    assert len(legibles) == len(documentos) - 1


# ---------------------------------------------------------------------------
# Vinculacion por huella, nunca por nombre
# ---------------------------------------------------------------------------


def test_el_registro_de_g_se_vincula_por_hash_y_no_por_nombre() -> None:
    """El certificado declara otro nombre de fichero; el registro se reconoce por su huella."""
    caso = "EXP001-G_desordenado"
    evidencias = evidencias_de(caso)
    declarado = next(e for e in evidencias if e.variable == "registro.hash_declarado")
    canonico = next(e for e in evidencias if e.variable == "registro.datos_canonicos")
    nombre_declarado = next(e for e in evidencias if e.variable == "registro.nombre_declarado")
    xlsx = next(d for d in documentos_de(caso) if d.formato == "xlsx")

    assert xlsx.nombre == "datos.xlsx" != nombre_declarado.valor
    assert hashlib.sha256(canonico.valor.encode("utf-8")).hexdigest() == declarado.valor
    assert declarado.valor == ground_truth(caso)["registro"]["por_motor"]["MTR-SYN-0001"]["sha256_canonico"]
    assert xlsx.sha256 == ground_truth(caso)["registro"]["por_motor"]["MTR-SYN-0001"]["sha256_fichero"]
    assert canonico.doc_id == xlsx.doc_id
    assert any(a.startswith("registro_vinculado_por_hash") for a in avisos_de(documentos_de(caso)))


def test_el_certificado_de_a_declara_la_huella_del_registro_que_acompana() -> None:
    caso = "EXP001-A_completo"
    evidencias = evidencias_de(caso)
    declarado = next(e for e in evidencias if e.variable == "registro.hash_declarado")
    canonico = next(e for e in evidencias if e.variable == "registro.datos_canonicos")
    assert declarado.tipo_doc == "certificado_instalador"
    assert declarado.tipo_evidencia == "declarado"
    assert hashlib.sha256(canonico.valor.encode("utf-8")).hexdigest() == declarado.valor
    assert not any(a.startswith("registro_vinculado_por_hash") for a in avisos_de(documentos_de(caso)))


# ---------------------------------------------------------------------------
# Registro xlsx (F0.7)
# ---------------------------------------------------------------------------


def test_el_registro_del_caso_a_da_n2_p_prom_y_h_despues(spec_ind240) -> None:
    caso = "EXP001-A_completo"
    esperado = ground_truth(caso)["registro"]
    por_motor = esperado["por_motor"]["MTR-SYN-0001"]
    xlsx = next(d for d in documentos_de(caso) if d.formato == "xlsx")
    registro = leer_registro(xlsx, spec_ind240)

    assert registro.legible and registro.avisos == []
    assert registro.n2 == Decimal(por_motor["N2_derivado"]) == Decimal("1188")
    assert registro.p_prom == Decimal(por_motor["P_prom_derivado"])
    assert registro.h_despues == Decimal(por_motor["h_despues_derivado"]) == Decimal("6570")
    assert registro.dias == Decimal(esperado["dias"]) == Decimal(36)
    assert registro.inicio.isoformat() == esperado["inicio"]
    assert registro.fin.isoformat() == esperado["fin"]
    assert registro.n_filas == por_motor["filas"]
    assert registro.n_marcha == por_motor["filas_marcha"]
    assert registro.intervalo_min == Decimal(esperado["intervalo_min"])
    assert registro.num_serie_motor == "MTR-SYN-0001"


def test_la_huella_de_los_datos_canonicos_coincide_con_la_declarada(spec_ind240) -> None:
    for caso in ("EXP001-A_completo", "EXP001-E_dos_motores", "EXP001-G_desordenado"):
        esperado = ground_truth(caso)["registro"]["por_motor"]
        for xlsx in (d for d in documentos_de(caso) if d.formato == "xlsx"):
            registro = leer_registro(xlsx, spec_ind240)
            declarado = esperado[registro.num_serie_motor]["sha256_canonico"]
            assert registro.sha256_datos == declarado, (caso, xlsx.nombre)
            assert (
                registro.sha256_datos == hashlib.sha256(registro.datos_canonicos.encode("utf-8")).hexdigest()
            )


def test_las_derivaciones_del_registro_salen_de_la_spec(spec_ind240) -> None:
    """Los nombres y los INT no estan cableados: vienen de `variables.*.derivacion`."""
    xlsx = next(d for d in documentos_de("EXP001-A_completo") if d.formato == "xlsx")
    registro = leer_registro(xlsx, spec_ind240)
    assert set(registro.derivados) == {"N2", "P_prom", "h_despues"}
    assert registro.interpretaciones["N2"] == "INT-03"
    assert registro.interpretaciones["h_despues"] == "INT-04"
    assert registro.metodos["N2"] == spec_ind240.variables["N2"]["derivacion"]["metodo"]


def test_sin_spec_el_registro_se_lee_pero_no_deriva_variables_de_ficha() -> None:
    xlsx = next(d for d in documentos_de("EXP001-A_completo") if d.formato == "xlsx")
    registro = leer_registro(xlsx)
    assert registro.derivados == {}
    assert registro.n_filas == 3456
    assert registro.sha256_datos  # los datos canonicos no dependen de la ficha


def test_un_xlsx_que_no_es_un_registro_no_lanza(tmp_path: Path, spec_ind240) -> None:
    from openpyxl import Workbook

    libro = Workbook()
    libro.active.append(["cualquier", "cosa"])
    ruta = tmp_path / "otro.xlsx"
    libro.save(ruta)
    doc = clasificar(ingestar_fichero(ruta)[0], spec_ind240)
    registro = leer_registro(doc, spec_ind240)
    assert not registro.legible
    assert any(a.startswith("registro_sin_columnas") for a in registro.avisos)


# ---------------------------------------------------------------------------
# OCR (se salta sin tesseract)
# ---------------------------------------------------------------------------


@pytest.mark.ocr
@sin_ocr
def test_el_escaneo_girado_de_g_se_lee_y_se_clasifica(spec_ind240) -> None:
    doc = clasificar(
        ingestar_fichero(EXPEDIENTES / "EXP001-G_desordenado" / "scan.pdf", ocr=True)[0], spec_ind240
    )
    esperado = next(
        d for d in ground_truth("EXP001-G_desordenado")["documentos"] if d["fichero"] == "scan.pdf"
    )
    assert doc.sha256 == esperado["sha256"]
    assert doc.tipo == esperado["tipo"] == "ficha_tecnica_variador"
    assert doc.subtipo == esperado["subtipo"] == "escaneo_girado"
    assert doc.paginas[0].metodo == "ocr"
    assert "VSD-SYN-0001" in doc.paginas[0].texto
    assert any(a.startswith("escaneo_ocr") and "giro" in a for a in doc.avisos)


@pytest.mark.ocr
@sin_ocr
def test_sin_tesseract_el_escaneo_no_rompe_nada() -> None:
    doc = ingestar_fichero(EXPEDIENTES / "EXP001-G_desordenado" / "scan.pdf", ocr=False)[0]
    assert doc.paginas[0].texto == ""
    assert any(a.startswith("ocr_no_disponible") for a in doc.avisos)
    assert doc.sha256  # la huella se calcula igual


@pytest.mark.ocr
@sin_ocr
def test_la_placa_fotografiada_entra_por_ocr_con_confianza_075(spec_ind240) -> None:
    doc = clasificar(
        ingestar_fichero(EXPEDIENTES / "EXP001-A_completo" / "04_informe_fotografico.pdf", ocr=True)[0],
        spec_ind240,
    )
    from engine.extraccion import ExtractorReglas

    evidencias = ExtractorReglas().extraer(doc, spec_ind240)
    placa = [e for e in evidencias if e.metodo == "ocr"]
    assert {e.variable for e in placa} == {"PM", "N1"}
    for evidencia in placa:
        assert evidencia.confianza == Decimal("0.75")
        assert evidencia.tipo_doc == "placa_caracteristicas_foto"
        assert evidencia.pagina == 2
        assert evidencia.num_serie_motor == "MTR-SYN-0001"
        assert evidencia.texto_literal
    assert {e.valor for e in placa} == {"110", "1485"}


# ---------------------------------------------------------------------------
# Higiene del paquete `engine/`
# ---------------------------------------------------------------------------

FUENTES_ENGINE = sorted((RAIZ / "engine").rglob("*.py"))


@pytest.mark.parametrize("fuente", FUENTES_ENGINE, ids=lambda p: p.name)
def test_engine_sin_eval_compile_ni_float(fuente: Path) -> None:
    codigo = fuente.read_text(encoding="utf-8")
    for prohibido in ("eval(", "compile(", "float(", "exec("):
        assert prohibido not in codigo, f"{fuente.name} usa {prohibido}"


@pytest.mark.parametrize("fuente", FUENTES_ENGINE, ids=lambda p: p.name)
def test_engine_no_importa_hacia_fuera(fuente: Path) -> None:
    codigo = fuente.read_text(encoding="utf-8")
    for paquete in ("agentes", "salida", "generator", "tests"):
        assert f"import {paquete}" not in codigo, f"{fuente.name} importa {paquete}"
        assert f"from {paquete}" not in codigo, f"{fuente.name} importa de {paquete}"


@pytest.mark.parametrize("fuente", FUENTES_ENGINE, ids=lambda p: p.name)
def test_engine_sin_ramas_por_ficha(fuente: Path) -> None:
    codigo = fuente.read_text(encoding="utf-8")
    assert "if ficha ==" not in codigo
    assert "IND240" not in codigo.replace("IND240_v1.1.yaml", ""), f"{fuente.name} nombra una ficha"
