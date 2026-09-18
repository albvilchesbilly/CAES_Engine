"""F0.8: Evidence Store y consolidacion (`engine/evidencias.py`) segun docs/03 §5.3 y §8, docs/05 §4.3–§4.4 y
ADR-002 §2.1. Evidencias construidas a mano sobre la spec real (`spec_ind240`). Los nombres de la ficha
(PM, N2, ...) aparecen solo aqui: el consolidador los lee de la spec.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import FrozenInstanceError, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.evidencias import (
    AVISO_SOLO_OCR,
    ActuacionConsolidada,
    DatoConsolidado,
    ErrorConsolidacion,
    ErrorEvidencia,
    EvidenceStore,
    Evidencia,
    colecciones_de_spec,
    consolidar,
    normalizar,
)
from engine.expresiones import NO_EVALUABLE

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "engine" / "evidencias.py"
UNO = Decimal("1")
OCR = Decimal("0.75")


@dataclass
class Doc:
    """Cumple `DocumentoLike` sin importar `engine.ingesta` (que no existe en F0.8)."""

    doc_id: str
    sha256: str
    tipo: str | None
    nombre: str
    origen: str | None = None
    subtipo: str | None = None


def ev(
    variable: str,
    valor: str,
    tipo_doc: str,
    doc_id: str | None = None,
    *,
    motor: str | None = "M1",
    variador: str | None = "V1",
    metodo: str = "tabla",
    confianza: Decimal = UNO,
    tipo_evidencia: str = "demostrado",
    pagina: int = 1,
    interpretacion: str | None = None,
    unidad: str | None = None,
) -> Evidencia:
    return Evidencia(
        variable=variable,
        valor=valor,
        doc_id=doc_id or tipo_doc,
        tipo_doc=tipo_doc,
        pagina=pagina,
        texto_literal=f"{variable}: {valor}",
        metodo=metodo,
        confianza=confianza,
        extractor_version="test-0.1",
        tipo_evidencia=tipo_evidencia,
        num_serie_motor=motor,
        num_serie_variador=variador,
        unidad=unidad,
        interpretacion=interpretacion,
    )


def doc(tipo: str, nombre: str | None = None, contenido: bytes | None = None) -> Doc:
    huella = hashlib.sha256(contenido or tipo.encode()).hexdigest()
    return Doc(doc_id=huella, sha256=huella, tipo=tipo, nombre=nombre or f"{tipo}.pdf")


def unidad(actuacion: ActuacionConsolidada, serie: str = "M1") -> dict[str, DatoConsolidado]:
    return actuacion.unidades[serie]


# --- contrato y evidencia --------------------------------------------------------------------------


def test_evidencia_es_inmutable_y_exige_texto_y_decimal():
    e = ev("PM", "110", "ficha_tecnica_motor")
    with pytest.raises(FrozenInstanceError):
        e.valor = "90"  # type: ignore[misc]
    with pytest.raises(ErrorEvidencia):
        ev("PM", 110, "ficha_tecnica_motor")  # type: ignore[arg-type]
    with pytest.raises(ErrorEvidencia):
        ev("PM", "110", "ficha_tecnica_motor", confianza=0.75)  # type: ignore[arg-type]
    with pytest.raises(ErrorEvidencia):
        ev("PM", "110", "ficha_tecnica_motor", tipo_evidencia="supuesto")
    assert ev("PM", "110", "ficha_tecnica_motor", confianza=1).confianza == Decimal("1")  # type: ignore[arg-type]


def test_contrato_adr_002_nombres_exactos():
    campos_ev = {f for f in Evidencia.__dataclass_fields__}
    assert {
        "variable", "valor", "doc_id", "tipo_doc", "pagina", "texto_literal", "metodo", "confianza",
        "extractor_version", "tipo_evidencia", "num_serie_motor", "num_serie_variador", "unidad",
        "interpretacion",
    } <= campos_ev  # fmt: skip
    campos_dato = {f for f in DatoConsolidado.__dataclass_fields__}
    assert {
        "variable", "evidencias", "valor_normalizado", "tipo_evidencia", "fuente_primaria", "interpretacion",
        "valores_por_fuente", "valor_consumido", "conflicto", "posibles_errores_ocr",
        "valores_por_tipo_evidencia",
    } <= campos_dato  # fmt: skip
    campos_act = {f for f in ActuacionConsolidada.__dataclass_fields__}
    assert {"documentos", "unidades", "variables", "conflictos", "avisos"} <= campos_act


# --- tres capas -------------------------------------------------------------------------------------


def test_tres_capas_dos_evidencias_coincidentes(spec_ind240):
    evs = [ev("PM", "110", "ficha_tecnica_motor", pagina=2), ev("PM", "110,0", "certificado_instalador")]
    a = consolidar(evs, [doc("ficha_tecnica_motor"), doc("certificado_instalador")], spec_ind240)
    d = unidad(a)["PM"]
    assert len(d.evidencias) == 2 and d.evidencias[0].pagina == 2 and d.evidencias[0].texto_literal
    assert d.valor_normalizado == "110"
    assert d.valor_consumido == Decimal("110") and isinstance(d.valor_consumido, Decimal)
    assert d.tipo_evidencia == "demostrado" and d.fuente_primaria == "ficha_tecnica_motor"
    assert d.unidad == "kW" and d.nivel == "unidad" and d.num_serie_motor == "M1"
    assert d.conflicto is False and a.conflictos == [] and a.avisos == []
    assert d.valores_por_fuente == {"ficha_tecnica_motor": "110", "certificado_instalador": "110"}


def test_conflicto_pm_entre_fuentes_fiables_deja_null_y_conserva_las_dos(spec_ind240):
    evs = [ev("PM", "110", "ficha_tecnica_motor"), ev("PM", "90", "certificado_instalador")]
    a = consolidar(evs, [], spec_ind240)
    d = unidad(a)["PM"]
    assert d.valor_consumido is None and d.conflicto is True
    assert d.valores_por_fuente == {"ficha_tecnica_motor": "110", "certificado_instalador": "90"}
    assert len(d.evidencias) == 2
    assert a.conflictos == [d]
    assert d.fuente_primaria == "ficha_tecnica_motor"  # marca la capa 2 pero no rompe el empate
    assert d.tipo_evidencia is None and d.valores_por_tipo_evidencia == {}
    assert any("conflicto" in aviso and "PM" in aviso for aviso in a.avisos)


def test_mismo_tipo_de_documento_con_dos_valores_entra_como_tipo_doc_2(spec_ind240):
    evs = [
        ev("titular_nif", "B12345678", "factura", "f1", motor=None, variador=None),
        ev("titular_nif", "B12345679", "factura", "f2", motor=None, variador=None),
        ev("titular_nif", "B12345678", "convenio_cae", motor=None, variador=None),
    ]
    a = consolidar(evs, [], spec_ind240)
    d = a.variables["titular_nif"]
    assert d.valores_por_fuente == {
        "factura": "B12345678",
        "factura#2": "B12345679",
        "convenio_cae": "B12345678",
    }
    assert d.conflicto is True and d.valor_consumido is None


# --- OCR ----------------------------------------------------------------------------------------------


def test_ocr_discrepante_no_bloquea_y_va_a_posibles_errores_ocr(spec_ind240):
    evs = [
        ev("PM", "110", "ficha_tecnica_motor"),
        ev("PM", "110", "certificado_instalador"),
        ev("PM", "118", "placa_caracteristicas_foto", metodo="ocr", confianza=OCR),
    ]
    a = consolidar(evs, [], spec_ind240)
    d = unidad(a)["PM"]
    assert d.valor_consumido == Decimal("110") and d.conflicto is False
    assert [e.valor for e in d.posibles_errores_ocr] == ["118"]
    assert "placa_caracteristicas_foto" not in d.valores_por_fuente
    assert a.conflictos == []


def test_ocr_coincidente_refuerza(spec_ind240):
    evs = [
        ev("PM", "110", "ficha_tecnica_motor"),
        ev("PM", "110", "placa_caracteristicas_foto", metodo="ocr", confianza=OCR),
    ]
    d = unidad(consolidar(evs, [], spec_ind240))["PM"]
    assert d.valores_por_fuente == {"ficha_tecnica_motor": "110", "placa_caracteristicas_foto": "110"}
    assert d.posibles_errores_ocr == [] and d.valor_consumido == Decimal("110")


def test_solo_ocr_se_consume_con_aviso(spec_ind240):
    evs = [ev("PM", "110", "placa_caracteristicas_foto", metodo="ocr", confianza=OCR)]
    a = consolidar(evs, [], spec_ind240)
    d = unidad(a)["PM"]
    assert d.valor_consumido == Decimal("110") and d.tipo_evidencia == "demostrado"
    assert any(AVISO_SOLO_OCR in aviso for aviso in d.avisos)
    assert any(AVISO_SOLO_OCR in aviso and "PM" in aviso for aviso in a.avisos)


def test_ocr_con_confianza_plena_es_fiable_y_otros_metodos_lo_son_siempre():
    assert ev("PM", "110", "placa", metodo="ocr", confianza=UNO).fiable is True
    assert ev("PM", "110", "placa", metodo="ocr", confianza=OCR).fiable is False
    assert ev("PM", "110", "ficha", metodo="regex", confianza=Decimal("0.9")).fiable is True


# --- normalizacion ----------------------------------------------------------------------------------


def test_cruce_normalizado_iguala_sl_y_tildes(spec_ind240):
    evs = [
        ev(
            "titular_razon_social",
            "Industrias Sintéticas del Ebro, S.L.",
            "factura",
            motor=None,
            variador=None,
        ),
        ev(
            "titular_razon_social",
            "INDUSTRIAS SINTETICAS DEL EBRO SL",
            "convenio_cae",
            motor=None,
            variador=None,
        ),
        ev(
            "titular_razon_social",
            " Industrias Sintéticas del Ebro S. L. ",
            "ficha_cumplimentada",
            motor=None,
            variador=None,
        ),
    ]
    a = consolidar(evs, [], spec_ind240)
    d = a.variables["titular_razon_social"]
    assert d.conflicto is False and len(set(d.valores_por_fuente.values())) == 1
    assert d.valor_normalizado == "INDUSTRIASSINTETICASDELEBROSL"
    assert d.valor_consumido == "Industrias Sintéticas del Ebro, S.L."  # texto crudo de la primera fiable
    assert isinstance(d.valor_consumido, str)


def test_cruce_exacto_distingue_nifs(spec_ind240):
    evs = [
        ev("titular_nif", "B12345678", "factura", motor=None, variador=None),
        ev("titular_nif", "B12345679", "declaracion_responsable", motor=None, variador=None),
    ]
    d = consolidar(evs, [], spec_ind240).variables["titular_nif"]
    assert d.conflicto is True and d.valor_consumido is None


def test_numeros_equivalentes_no_son_conflicto_con_exacto(spec_ind240):
    evs = [
        ev("N1", "1485", "ficha_tecnica_motor"),
        ev("N1", "1485,0", "certificado_instalador"),
        ev("N1", " 1485.00 ", "ficha_cumplimentada"),
    ]
    d = unidad(consolidar(evs, [], spec_ind240))["N1"]
    assert d.conflicto is False and set(d.valores_por_fuente.values()) == {"1485"}
    assert d.valor_consumido == Decimal("1485")


@pytest.mark.parametrize(
    ("valor", "cruce", "tipo", "esperado"),
    [
        ("110,0", "exacto", "decimal", "110"),
        ("110.00", "exacto", "decimal", "110"),
        ("3,90", "exacto", "decimal", "3.9"),
        ("0.0500", "exacto", None, "0.05"),
        ("  B12345678 ", "exacto", "string", "B12345678"),
        ("02/03/2026", "exacto", "date", "2026-03-02"),
        ("2026-03-02", "exacto", None, "2026-03-02"),
        ("S. L.", "normalizado", "string", "SL"),
        ("Ñandú, S.A.", "normalizado", None, "NANDUSA"),
        ("no-numerico", "exacto", "decimal", "no-numerico"),
    ],
)
def test_normalizar(valor, cruce, tipo, esperado):
    assert normalizar(valor, cruce, tipo) == esperado


def test_cruce_desconocido_es_error():
    with pytest.raises(ErrorConsolidacion):
        normalizar("x", "aproximado")


# --- declarado ≠ demostrado ≠ derivado -----------------------------------------------------------------


def test_n2_declarado_y_derivado_consume_derivado_y_expone_ambos(spec_ind240):
    evs = [
        ev("N2", "1188", "certificado_instalador", tipo_evidencia="declarado"),
        ev("N2", "1188", "ficha_cumplimentada", tipo_evidencia="declarado"),
        ev(
            "N2",
            "1188",
            "registro_funcionamiento",
            tipo_evidencia="derivado",
            metodo="xlsx",
            interpretacion="INT-03",
        ),
    ]
    d = unidad(consolidar(evs, [], spec_ind240))["N2"]
    assert d.valor_consumido == Decimal("1188") and d.tipo_evidencia == "derivado"
    assert d.valores_por_tipo_evidencia == {"declarado": "1188", "derivado": "1188"}
    assert d.valores_tipados_por_tipo_evidencia == {"declarado": Decimal("1188"), "derivado": Decimal("1188")}
    assert d.interpretacion == "INT-03"
    assert d.conflicto is False


def test_n2_solo_declarado_entra_marcado_declarado(spec_ind240):
    evs = [
        ev("N2", "1188", "certificado_instalador", tipo_evidencia="declarado"),
        ev("N2", "1188", "ficha_cumplimentada", tipo_evidencia="declarado"),
    ]
    d = unidad(consolidar(evs, [], spec_ind240))["N2"]
    assert d.tipo_evidencia == "declarado" and d.valor_consumido == Decimal("1188")
    assert "derivado" not in d.valores_por_tipo_evidencia


def test_tolerancia_declarado_derivado_es_de_la_regla_no_del_consolidador(spec_ind240):
    """N2 ±1 rpm y P_prom ±0,5 kW (docs/05 §8): el consolidador expone ambos valores sin conflicto."""
    evs = [
        ev("N2", "1188", "certificado_instalador", tipo_evidencia="declarado"),
        ev("N2", "1189", "registro_funcionamiento", tipo_evidencia="derivado", metodo="xlsx"),
        ev("P_prom", "60.0", "certificado_instalador", tipo_evidencia="declarado"),
        ev("P_prom", "60.4", "registro_funcionamiento", tipo_evidencia="derivado", metodo="xlsx"),
    ]
    u = unidad(consolidar(evs, [], spec_ind240))
    assert u["N2"].conflicto is False and u["N2"].valor_consumido == Decimal("1189")
    assert u["N2"].valores_por_tipo_evidencia == {"declarado": "1188", "derivado": "1189"}
    assert u["P_prom"].conflicto is False and u["P_prom"].valor_consumido == Decimal("60.4")
    assert u["P_prom"].valores_por_tipo_evidencia == {"declarado": "60", "derivado": "60.4"}


def test_dos_derivados_distintos_si_son_conflicto(spec_ind240):
    """docs/04 §4.2, matiz de conflicto: dos N2 derivados de dos fuentes fiables → null."""
    evs = [
        ev("N2", "1188", "registro_funcionamiento", "r1", tipo_evidencia="derivado", metodo="xlsx"),
        ev("N2", "1200", "registro_funcionamiento", "r2", tipo_evidencia="derivado", metodo="xlsx"),
        ev("N2", "1188", "certificado_instalador", tipo_evidencia="declarado"),
    ]
    d = unidad(consolidar(evs, [], spec_ind240))["N2"]
    assert d.conflicto is True and d.valor_consumido is None
    assert "derivado" not in d.valores_por_tipo_evidencia


def test_sin_cruce_con_valores_distintos_entre_tipos_de_evidencia_son_conflicto(spec_ind240):
    evs = [
        ev(
            "convenio.ahorro_kwh",
            "305829",
            "convenio_cae",
            tipo_evidencia="declarado",
            motor=None,
            variador=None,
        ),
        ev(
            "convenio.ahorro_kwh",
            "300000",
            "convenio_cae",
            "c2",
            tipo_evidencia="demostrado",
            motor=None,
            variador=None,
        ),
    ]
    d = consolidar(evs, [], spec_ind240).variables["convenio.ahorro_kwh"]
    assert d.conflicto is True and d.valor_consumido is None


def test_prioridad_derivado_demostrado_declarado(spec_ind240):
    evs = [
        ev("h_despues", "6000", "ficha_cumplimentada", tipo_evidencia="declarado"),
        ev("h_despues", "6200", "registro_funcionamiento", tipo_evidencia="derivado", metodo="xlsx"),
    ]
    d = unidad(consolidar(evs, [], spec_ind240))["h_despues"]
    # h_despues no declara cruce_con: valores distintos son conflicto aunque sean de tipos distintos
    assert d.conflicto is True
    evs2 = [
        ev("h_antes", "6000", "registro_horas_previo"),
        ev("h_antes", "6000", "certificado_instalador", tipo_evidencia="declarado"),
    ]
    d2 = unidad(consolidar(evs2, [], spec_ind240))["h_antes"]
    assert d2.tipo_evidencia == "demostrado" and d2.valores_por_tipo_evidencia == {
        "demostrado": "6000",
        "declarado": "6000",
    }
    assert d2.interpretacion is None


def test_interpretacion_de_derivacion_se_toma_de_la_spec_si_la_evidencia_no_la_trae(spec_ind240):
    d = unidad(
        consolidar([ev("N2", "1188", "registro_funcionamiento", tipo_evidencia="derivado")], [], spec_ind240)
    )["N2"]
    assert d.interpretacion == "INT-03"


# --- unidades ----------------------------------------------------------------------------------------


def test_dos_motores_y_evidencia_solo_con_variador_se_asigna_a_su_unidad(spec_ind240):
    evs = [
        ev("num_serie_motor", "M1", "ficha_tecnica_motor", "ftm1", motor="M1", variador="V1"),
        ev("num_serie_motor", "M2", "ficha_tecnica_motor", "ftm2", motor="M2", variador="V2"),
        ev("PM", "110", "ficha_tecnica_motor", "ftm1", motor="M1", variador="V1"),
        ev("PM", "55", "ficha_tecnica_motor", "ftm2", motor="M2", variador="V2"),
        ev("PM", "55", "ficha_cumplimentada", motor=None, variador="V2"),
        ev("PM", "110", "ficha_cumplimentada", motor=None, variador="V1"),
        ev("num_serie_variador", "V2", "factura", motor=None, variador="V2"),
    ]
    a = consolidar(evs, [], spec_ind240)
    assert a.n_unidades == 2 and set(a.unidades) == {"M1", "M2"}
    assert a.unidades["M1"]["PM"].valores_por_fuente == {
        "ficha_tecnica_motor": "110",
        "ficha_cumplimentada": "110",
    }
    assert a.unidades["M2"]["PM"].valores_por_fuente == {
        "ficha_tecnica_motor": "55",
        "ficha_cumplimentada": "55",
    }
    assert a.unidades["M2"]["num_serie_variador"].valor_consumido == "V2"
    assert a.unidades["M1"]["num_serie_motor"].valor_consumido == "M1"
    assert a.avisos == [] and a.evidencias_no_asignadas == []


def test_evidencia_de_clave_usa_su_propio_valor_como_clave(spec_ind240):
    evs = [ev("num_serie_motor", "M9", "registro_horas_previo", motor=None, variador=None)]
    a = consolidar(evs, [], spec_ind240)
    assert "M9" in a.unidades and a.avisos == []


def test_evidencia_de_unidad_sin_clave_no_se_asigna_y_avisa(spec_ind240):
    evs = [
        ev("PM", "110", "ficha_tecnica_motor"),
        ev("N1", "1485", "ficha_cumplimentada", motor=None, variador=None),
    ]
    a = consolidar(evs, [doc("ficha_cumplimentada")], spec_ind240)
    assert "N1" not in a.unidades["M1"] and a.evidencias_no_asignadas == [evs[1]]
    assert any("sin clave de union" in aviso for aviso in a.avisos)


def test_variador_desconocido_o_ambiguo_avisa(spec_ind240):
    evs = [
        ev("PM", "110", "ficha_tecnica_motor", "f1", motor="M1", variador="V1"),
        ev("PM", "110", "ficha_tecnica_motor", "f2", motor="M2", variador="V1"),
        ev("N1", "1485", "ficha_cumplimentada", motor=None, variador="V1"),
        ev("N1", "1485", "ficha_cumplimentada", "fc2", motor=None, variador="V7"),
    ]
    a = consolidar(evs, [], spec_ind240)
    assert len(a.evidencias_no_asignadas) == 2
    assert any("varios motores" in aviso for aviso in a.avisos)
    assert any("no asociado a ningun motor" in aviso for aviso in a.avisos)


def _registro(contenido: bytes, nombre: str) -> tuple[Doc, str]:
    d = doc("registro_funcionamiento", nombre, contenido)
    return d, d.sha256


def test_registro_sin_serie_se_vincula_por_huella(spec_ind240):
    registro, huella = _registro(b"scada-M1", "registro_funcionamiento_M1.xlsx")
    evs = [
        ev("PM", "110", "certificado_instalador"),
        ev("registro.hash_declarado", huella, "certificado_instalador", tipo_evidencia="declarado"),
        ev(
            "registro.dias",
            "31",
            "registro_funcionamiento",
            huella,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
        ev(
            "N2",
            "1188",
            "registro_funcionamiento",
            huella,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
    ]
    a = consolidar(evs, [registro, doc("certificado_instalador")], spec_ind240)
    u = unidad(a)
    assert u["registro.dias"].valor_consumido == Decimal("31") and u["N2"].tipo_evidencia == "derivado"
    assert a.vinculos_por_huella == {huella: "M1"}
    assert a.avisos == [] and a.evidencias_no_asignadas == []


def test_registro_con_nombre_distinto_vincula_por_huella_con_aviso_informativo(spec_ind240):
    """Caso G: el xlsx se llama `datos.xlsx`; la vinculacion es por SHA-256 y el nombre solo da aviso."""
    registro, huella = _registro(b"scada-G", "datos.xlsx")
    evs = [
        ev("registro.hash_declarado", huella.upper(), "certificado_instalador", tipo_evidencia="declarado"),
        ev(
            "registro.dias",
            "31",
            "registro_funcionamiento",
            huella,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
    ]
    a = consolidar(evs, [registro], spec_ind240)
    assert a.vinculos_por_huella == {huella: "M1"} and "registro.dias" in unidad(a)
    assert len(a.avisos) == 1 and "datos.xlsx" in a.avisos[0] and "huella" in a.avisos[0]


def test_huella_declarada_puede_ser_la_de_los_datos_canonicos(spec_ind240):
    """R-EVD-03 compara `hash_declarado` con `sha256(registro.datos_canonicos)`: esa huella vincula."""
    registro, _ = _registro(b"bytes-del-fichero", "registro_funcionamiento.xlsx")
    canonicos = "2026-03-03;MARCHA;1188;60\n2026-03-04;MARCHA;1188;60"
    huella_canonica = hashlib.sha256(canonicos.encode("utf-8")).hexdigest()
    evs = [
        ev("registro.hash_declarado", huella_canonica, "certificado_instalador", tipo_evidencia="declarado"),
        ev(
            "registro.datos_canonicos",
            canonicos,
            "registro_funcionamiento",
            registro.doc_id,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
        ev(
            "registro.dias",
            "31",
            "registro_funcionamiento",
            registro.doc_id,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
    ]
    a = consolidar(evs, [registro], spec_ind240)
    assert a.vinculos_por_huella == {registro.doc_id: "M1"} and a.avisos == []


def test_registro_no_vinculable_avisa_y_no_se_asigna(spec_ind240):
    registro, huella = _registro(b"scada-X", "datos.xlsx")
    evs = [
        ev("PM", "110", "certificado_instalador"),
        ev("registro.hash_declarado", "0" * 64, "certificado_instalador", tipo_evidencia="declarado"),
        ev(
            "registro.dias",
            "31",
            "registro_funcionamiento",
            huella,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
    ]
    a = consolidar(evs, [registro], spec_ind240)
    assert "registro.dias" not in unidad(a) and a.vinculos_por_huella == {}
    assert len(a.evidencias_no_asignadas) == 1
    assert any("no vinculable" in aviso and "huella" in aviso for aviso in a.avisos)


def test_huella_declarada_por_dos_unidades_no_vincula(spec_ind240):
    registro, huella = _registro(b"scada-dup", "registro.xlsx")
    evs = [
        ev(
            "registro.hash_declarado",
            huella,
            "certificado_instalador",
            motor="M1",
            tipo_evidencia="declarado",
        ),
        ev(
            "registro.hash_declarado",
            huella,
            "certificado_instalador",
            motor="M2",
            variador="V2",
            tipo_evidencia="declarado",
        ),
        ev(
            "registro.dias",
            "31",
            "registro_funcionamiento",
            huella,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
    ]
    a = consolidar(evs, [registro], spec_ind240)
    assert a.vinculos_por_huella == {} and any("varias unidades" in aviso for aviso in a.avisos)


# --- tipado ------------------------------------------------------------------------------------------


def test_tipado_fecha_enum_y_string(spec_ind240):
    evs = [
        ev("fecha_fin_actuacion", "02/03/2026", "certificado_instalador", motor=None, variador=None),
        ev("fecha_fin_actuacion", "2026-03-02", "ficha_cumplimentada", motor=None, variador=None),
        ev("tipo_equipo_accionado", "bomba_dinamica", "ficha_tecnica_equipo_accionado"),
        ev("regimen_previo", "constante_sin_modulacion", "registro_horas_previo"),
        ev("titular_nif", "B12345678", "factura", motor=None, variador=None),
    ]
    a = consolidar(evs, [], spec_ind240)
    f = a.variables["fecha_fin_actuacion"]
    assert (
        f.valor_consumido == date(2026, 3, 2) and f.conflicto is False and f.valor_normalizado == "2026-03-02"
    )
    assert unidad(a)["tipo_equipo_accionado"].valor_consumido == "bomba_dinamica"
    assert unidad(a)["regimen_previo"].valor_consumido == "constante_sin_modulacion"
    assert a.variables["titular_nif"].valor_consumido == "B12345678"


def test_enum_fuera_del_enumerado_avisa_y_deja_none(spec_ind240):
    evs = [ev("tipo_equipo_accionado", "bomba_de_tornillo", "ficha_tecnica_equipo_accionado")]
    a = consolidar(evs, [], spec_ind240)
    d = unidad(a)["tipo_equipo_accionado"]
    assert d.valor_consumido is None and d.conflicto is False
    assert any("fuera del enumerado" in aviso for aviso in a.avisos)
    assert "bomba_desplazamiento_positivo" in a.avisos[0]  # valores_ref resuelto contra ambito.*


def test_hechos_documentales_bool_lista_fecha_decimal_texto(spec_ind240):
    lineas = (
        '[{"descripcion": "Variador ABB", "categoria": "variador"}, '
        '{"descripcion": "Mano de obra", "categoria": "instalacion"}]'
    )
    evs = [
        ev("factura.campos_minimos_presentes", "true", "factura", motor=None, variador=None),
        ev("ficha_cumplimentada.firmada", "false", "ficha_cumplimentada", motor=None, variador=None),
        ev("factura.lineas", lineas, "factura", motor=None, variador=None),
        ev("convenio.fecha_firma", "2026-01-15", "convenio_cae", motor=None, variador=None),
        ev(
            "convenio.ahorro_kwh",
            "305.829".replace(".", ""),
            "convenio_cae",
            tipo_evidencia="declarado",
            motor=None,
            variador=None,
        ),
        ev(
            "convenio.requisitos_presentes",
            '["ahorro anual (kWh)", "vida útil de la actuación"]',
            "convenio_cae",
            motor=None,
            variador=None,
        ),
        ev(
            "registro.inicio",
            "2026-03-03",
            "registro_funcionamiento",
            tipo_evidencia="derivado",
            metodo="xlsx",
        ),
        ev("registro.hash_declarado", "ab" * 32, "certificado_instalador", tipo_evidencia="declarado"),
    ]
    a = consolidar(evs, [], spec_ind240)
    v = a.variables
    assert v["factura.campos_minimos_presentes"].valor_consumido is True
    assert v["ficha_cumplimentada.firmada"].valor_consumido is False
    assert v["factura.lineas"].valor_consumido == [
        {"descripcion": "Variador ABB", "categoria": "variador"},
        {"descripcion": "Mano de obra", "categoria": "instalacion"},
    ]
    assert v["convenio.fecha_firma"].valor_consumido == date(2026, 1, 15)
    assert v["convenio.ahorro_kwh"].valor_consumido == Decimal("305829")
    assert v["convenio.requisitos_presentes"].valor_consumido == [
        "ahorro anual (kWh)",
        "vida útil de la actuación",
    ]
    u = unidad(a)
    assert u["registro.inicio"].valor_consumido == date(2026, 3, 3)  # `registro` es raiz de nivel unidad
    assert (
        u["registro.hash_declarado"].valor_consumido == "ab" * 32
        and u["registro.hash_declarado"].tipo == "string"
    )


def test_lista_json_con_numeros_nunca_produce_float(spec_ind240):
    evs = [ev("factura.importes", "[12.5, 3]", "factura", motor=None, variador=None)]
    d = consolidar(evs, [], spec_ind240).variables["factura.importes"]
    assert d.valor_consumido == [Decimal("12.5"), Decimal("3")]
    assert all(isinstance(x, Decimal) for x in d.valor_consumido)


def test_decimal_no_numerico_avisa(spec_ind240):
    a = consolidar([ev("PM", "ciento diez", "ficha_tecnica_motor")], [], spec_ind240)
    d = unidad(a)["PM"]
    assert d.valor_consumido is None and d.conflicto is False and any("no numerico" in x for x in a.avisos)


# --- colecciones, n_motores, rango ---------------------------------------------------------------------


def test_colecciones_detectadas_en_la_spec(spec_ind240):
    assert {"foto.antes", "foto.despues"} <= colecciones_de_spec(spec_ind240)
    assert not (colecciones_de_spec(spec_ind240) & set(spec_ind240.variables))


def test_fotos_se_consolidan_en_listas_por_unidad(spec_ind240):
    evs = [
        ev("foto.antes", "IMG_0001.jpg", "informe_fotografico"),
        ev("foto.antes", "IMG_0002.jpg", "informe_fotografico"),
        ev("foto.antes", "IMG_0002.jpg", "informe_fotografico"),  # duplicada
        ev("foto.despues", "IMG_0003.jpg", "informe_fotografico"),
        ev("foto.antes", "IMG_0010.jpg", "informe_fotografico", motor="M2", variador="V2"),
    ]
    a = consolidar(evs, [], spec_ind240)
    assert a.unidades["M1"]["foto.antes"].valor_consumido == ["IMG_0001.jpg", "IMG_0002.jpg"]
    assert a.unidades["M1"]["foto.despues"].valor_consumido == ["IMG_0003.jpg"]
    assert a.unidades["M2"]["foto.antes"].valor_consumido == ["IMG_0010.jpg"]
    assert a.unidades["M1"]["foto.antes"].conflicto is False and a.conflictos == []
    assert a.unidades["M1"]["foto.antes"].tipo == "list"


def test_colecciones_explicitas_se_respetan(spec_ind240):
    evs = [
        ev("x.ids", "a", "factura", motor=None, variador=None),
        ev("x.ids", "b", "factura", "f2", motor=None, variador=None),
    ]
    assert consolidar(evs, [], spec_ind240, colecciones={"x.ids"}).variables["x.ids"].valor_consumido == [
        "a",
        "b",
    ]
    assert consolidar(evs, [], spec_ind240).variables["x.ids"].conflicto is True


def test_n_motores_por_fuente_y_n_unidades(spec_ind240):
    evs = [
        ev("n_motores", "2", "factura", motor=None, variador=None),
        ev("n_motores", "2", "certificado_instalador", motor=None, variador=None),
        ev("n_motores", "2", "ficha_cumplimentada", motor=None, variador=None),
        ev("n_motores", "1", "registro_funcionamiento", motor=None, variador=None),
        ev("PM", "110", "ficha_tecnica_motor", "f1"),
        ev("PM", "55", "ficha_tecnica_motor", "f2", motor="M2", variador="V2"),
    ]
    a = consolidar(evs, [], spec_ind240)
    assert a.valores_por_fuente_de("n_motores") == {
        "factura": "2",
        "certificado_instalador": "2",
        "ficha_cumplimentada": "2",
        "registro_funcionamiento": "1",
    }
    assert a.variables["n_motores"].conflicto is True and a.n_unidades == 2
    assert a.valores_por_fuente_de("no_existe") == {}


def test_rango_plausible_fuera_avisa_sin_conflicto(spec_ind240):
    a = consolidar([ev("h_antes", "9000", "registro_horas_previo")], [], spec_ind240)
    d = unidad(a)["h_antes"]
    assert d.valor_consumido == Decimal("9000") and d.conflicto is False
    assert any("rango plausible" in aviso and "h_antes" in aviso for aviso in a.avisos)
    b = consolidar([ev("h_antes", "6000", "registro_horas_previo")], [], spec_ind240)
    assert b.avisos == []


# --- documentos y serializacion ----------------------------------------------------------------------


def test_documentos_por_tipo_y_acceso(spec_ind240):
    d1, d2, d3 = (
        doc("factura", "f1.pdf", b"1"),
        doc("factura", "f2.pdf", b"2"),
        Doc("x", "x", None, "raro.bin"),
    )
    a = consolidar([ev("PM", "110", "ficha_tecnica_motor")], [d1, d2, d3], spec_ind240)
    assert a.documentos == [d1, d2, d3]
    assert a.documentos_por_tipo == {"factura": [d1, d2]}
    assert a.dato("PM", "M1").valor_consumido == Decimal("110") and a.dato("PM") is None


def test_a_dict_es_serializable_con_json(spec_ind240):
    registro, huella = _registro(b"scada", "datos.xlsx")
    evs = [
        ev("PM", "110", "ficha_tecnica_motor"),
        ev("PM", "90", "certificado_instalador"),
        ev("fecha_fin_actuacion", "2026-03-02", "certificado_instalador", motor=None, variador=None),
        ev("registro.hash_declarado", huella, "certificado_instalador", tipo_evidencia="declarado"),
        ev(
            "registro.dias",
            "31",
            "registro_funcionamiento",
            huella,
            tipo_evidencia="derivado",
            metodo="xlsx",
            motor=None,
            variador=None,
        ),
        ev("foto.antes", "IMG1", "informe_fotografico"),
    ]
    a = consolidar(evs, [registro], spec_ind240)
    texto = json.dumps(a.a_dict(), ensure_ascii=False, sort_keys=True)
    datos = json.loads(texto)
    pm = datos["unidades"]["M1"]["PM"]
    assert pm["valor_consumido"] is None and pm["conflicto"] is True
    assert pm["evidencias"][0]["confianza"] == "1"
    assert datos["variables"]["fecha_fin_actuacion"]["valor_consumido"] == "2026-03-02"
    assert datos["unidades"]["M1"]["registro.dias"]["valor_consumido"] == "31"
    assert datos["conflictos"][0]["variable"] == "PM"
    assert datos["vinculos_por_huella"] == {huella: "M1"} and datos["n_unidades"] == 1
    assert datos["documentos"][0]["nombre"] == "datos.xlsx"
    assert "float" not in texto


def test_evidence_store_consultas_y_a_json(spec_ind240):
    store = EvidenceStore()
    store.agregar(ev("PM", "110", "ficha_tecnica_motor", "d1"))
    store.agregar_varias(
        [
            ev("PM", "110", "certificado_instalador", "d2"),
            ev("N1", "1485", "ficha_tecnica_motor", "d1", motor="M2"),
        ]
    )
    assert len(store) == 3 and len(store.por_variable("PM")) == 2
    assert len(store.por_unidad("M1")) == 2 and len(store.por_unidad("M2")) == 1
    assert len(store.por_documento("d1")) == 2
    salida = store.a_json()
    assert salida["n_evidencias"] == 3 and json.dumps(salida)
    assert salida["evidencias"][0]["confianza"] == "1" and salida["evidencias"][0]["num_serie_motor"] == "M1"
    with pytest.raises(ErrorEvidencia):
        store.agregar({"variable": "PM"})  # type: ignore[arg-type]
    a = store.consolidar([], spec_ind240)
    assert a.n_unidades == 2


def test_dato_a_dict_serializa_no_evaluable_como_null():
    d = DatoConsolidado("x", [], None, None, None, None, {}, NO_EVALUABLE, False, [])  # type: ignore[arg-type]
    assert d.a_dict()["valor_consumido"] is None


# --- higiene del fuente ------------------------------------------------------------------------------


def test_fuente_sin_eval_float_ni_nombres_de_ficha():
    fuente = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("eval(", "exec(", "compile(", "float(", "import ast", "from ast"):
        assert prohibido not in fuente, prohibido
    assert "IND240" not in fuente and "if ficha" not in fuente
    for literal in ("PM", "N1", "N2", "REG1781", "n_motores", "foto", "registro_funcionamiento"):
        assert f'"{literal}"' not in fuente, literal


def test_no_importa_ingesta_calculo_reglas_ni_fuera_del_nucleo():
    fuente = FUENTE.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+(agentes|salida|generator|tests)\b", fuente, re.MULTILINE)
    assert not re.search(
        r"^\s*from\s+engine\.(ingesta|calculo|reglas|clasificacion|extraccion)\b", fuente, re.MULTILINE
    )
    assert not re.search(r"^\s*import\s+engine\.(ingesta|calculo|reglas)\b", fuente, re.MULTILINE)
