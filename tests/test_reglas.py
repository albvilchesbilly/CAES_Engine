"""F0.9: motor de reglas (`engine/reglas.py`) segun docs/04 §3–§6, docs/05 §2.1 y ADR-002 §2.4.

Las actuaciones se construyen en memoria (`engine/ingesta.py` no participa): `dato()` fabrica un
`DatoConsolidado` con sus evidencias y `actuacion()` una `ActuacionConsolidada`. Los casos A–D se arman con
los parametros del ground truth de F0.5 (`expedientes/_resultados_esperados/*.json`), que estos tests leen y
`engine/` nunca lee. Los nombres de la ficha (PM, N2, R-CON-01, ...) solo aparecen aqui: el motor los saca de
la spec.

Por cada una de las 26 reglas hay un caso que `CUMPLE` y uno que `FALLA`, construidos a partir de lo que dice
su `logica` en el YAML (que el test lee de la spec), no de como esta implementado el motor.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.evidencias import ActuacionConsolidada, DatoConsolidado, Evidencia
from engine.expresiones import NO_EVALUABLE
from engine.reglas import (
    ALIAS_CONTEXTO,
    ORDEN_FASES,
    VEREDICTO_BLOQUEADO,
    VEREDICTO_NO_ELEGIBLE,
    VEREDICTO_PREVALIDADO,
    VEREDICTO_SUBSANABLE,
    ErrorReglas,
    Evaluacion,
    Resultado,
    argumentos_unique,
    construir_contexto,
    evaluar_actuacion,
    evaluar_regla,
    veredicto_de,
)

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "engine" / "reglas.py"
GROUND_TRUTH = RAIZ / "expedientes" / "_resultados_esperados"
FECHA = date(2026, 9, 18)
SERIE = "MTR-SYN-0001"
UNO = Decimal("1")
CANONICO = "datos canonicos sinteticos del registro"


# ---------------------------------------------------------------------------
# Constructores en memoria
# ---------------------------------------------------------------------------


@dataclass
class Doc:
    """Cumple `DocumentoLike` sin importar `engine.ingesta`."""

    doc_id: str
    sha256: str
    tipo: str | None
    nombre: str
    origen: str | None = None
    subtipo: str | None = None


def _texto(valor: object) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, list):
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, date):
        return valor.isoformat()
    if valor is None:
        return ""
    return str(valor)


def _evidencia(variable: str, valor: str, tipo_doc: str, serie: str | None, tipo_evidencia: str) -> Evidencia:
    return Evidencia(
        variable=variable,
        valor=valor,
        doc_id=hashlib.sha256(f"{tipo_doc}:{variable}".encode()).hexdigest(),
        tipo_doc=tipo_doc,
        pagina=1,
        texto_literal=f"{variable}: {valor}",
        metodo="tabla",
        confianza=UNO,
        extractor_version="test-0.1",
        tipo_evidencia=tipo_evidencia,
        num_serie_motor=serie,
    )


def dato(
    variable: str,
    valor: object,
    *,
    fuentes: list[str] | None = None,
    tipo_evidencia: str = "demostrado",
    tipados: dict[str, object] | None = None,
    valores_por_fuente: dict[str, str] | None = None,
    interpretacion: str | None = None,
    fuente_primaria: str | None = None,
    conflicto: bool = False,
    nivel: str = "actuacion",
    serie: str | None = None,
) -> DatoConsolidado:
    """Un `DatoConsolidado` con sus tres capas (evidencias, texto canonico, valor consumido tipado)."""
    tipos_doc = list(fuentes or ["ficha_cumplimentada"])
    texto = _texto(valor)
    por_fuente = dict(valores_por_fuente) if valores_por_fuente is not None else {t: texto for t in tipos_doc}
    evidencias = [_evidencia(variable, por_fuente.get(t, texto), t, serie, tipo_evidencia) for t in tipos_doc]
    if tipados is None:
        tipados = {tipo_evidencia: valor} if valor is not None else {}
    return DatoConsolidado(
        variable=variable,
        evidencias=evidencias,
        valor_normalizado=texto or None,
        tipo_evidencia=tipo_evidencia,
        fuente_primaria=fuente_primaria or (tipos_doc[0] if tipos_doc else None),
        interpretacion=interpretacion,
        valores_por_fuente=por_fuente,
        valor_consumido=valor,
        conflicto=conflicto,
        posibles_errores_ocr=[],
        valores_tipados_por_tipo_evidencia=dict(tipados),
        nivel=nivel,
        num_serie_motor=serie,
    )


def unidad_dato(variable: str, valor: object, serie: str = SERIE, **kwargs) -> DatoConsolidado:
    return dato(variable, valor, nivel="unidad", serie=serie, **kwargs)


def actuacion(
    *,
    variables: dict[str, DatoConsolidado] | None = None,
    unidades: dict[str, dict[str, DatoConsolidado]] | None = None,
    documentos: list[str] | None = None,
    conflictos: list[DatoConsolidado] | None = None,
    avisos: list[str] | None = None,
) -> ActuacionConsolidada:
    docs = [Doc(doc_id=f"sha-{t}", sha256=f"sha-{t}", tipo=t, nombre=f"{t}.pdf") for t in (documentos or [])]
    por_tipo: dict[str, list[Doc]] = {}
    for doc in docs:
        por_tipo.setdefault(str(doc.tipo), []).append(doc)
    return ActuacionConsolidada(
        documentos=list(docs),
        unidades=unidades or {},
        variables=variables or {},
        conflictos=list(conflictos or []),
        avisos=list(avisos or []),
        documentos_por_tipo=por_tipo,
    )


# ---------------------------------------------------------------------------
# Casos A-D desde el ground truth de F0.5
# ---------------------------------------------------------------------------


def ground_truth(caso: str) -> dict:
    ruta = next(GROUND_TRUTH.glob(f"EXP001-{caso}_*.json"))
    return json.loads(ruta.read_text(encoding="utf-8"))


def _valor_spec(nombre: str, texto: str, spec) -> object:
    decl = spec.variables.get(nombre) or {}
    tipo = decl.get("tipo")
    if tipo == "decimal":
        return Decimal(texto)
    if tipo == "date":
        return date.fromisoformat(texto)
    return texto


def _valor_hecho(valor: object) -> object:
    if isinstance(valor, bool) or isinstance(valor, list):
        return valor
    if isinstance(valor, int):
        return Decimal(str(valor))
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            return valor
    return valor


def _dato_desde_gt(nombre: str, info: dict, spec, nivel: str, serie: str | None) -> DatoConsolidado | None:
    fuentes = [f["tipo"] for f in info.get("fuentes") or []]
    declaradas = [f["tipo"] for f in info.get("fuentes_declaradas") or []]
    texto = info.get("valor")
    if texto is None and not fuentes:
        return None
    valor = None if texto is None else _valor_spec(nombre, str(texto), spec)
    evidencia = str(info.get("evidencia") or "demostrado")
    tipados: dict[str, object] = {}
    if valor is not None:
        if fuentes:
            tipados[evidencia] = valor
        if declaradas:
            tipados["declarado"] = valor
    por_fuente = info.get("valores_por_fuente")
    if por_fuente is None:
        por_fuente = {t: _texto(valor) for t in (fuentes + declaradas)}
    return dato(
        nombre,
        valor,
        fuentes=fuentes + [t for t in declaradas if t not in fuentes] or ["ficha_cumplimentada"],
        tipo_evidencia=evidencia,
        tipados=tipados,
        valores_por_fuente=dict(por_fuente),
        interpretacion=info.get("interpretacion"),
        fuente_primaria=info.get("fuente_primaria"),
        conflicto=bool(info.get("conflicto")),
        nivel=nivel,
        serie=serie,
    )


def caso(nombre: str, spec) -> ActuacionConsolidada:
    """Actuacion en memoria equivalente al caso sintetico `nombre` (A, B, C, D) del ground truth."""
    gt = ground_truth(nombre)
    variables: dict[str, DatoConsolidado] = {}
    for var, info in gt["variables_consolidadas"]["actuacion"].items():
        construido = _dato_desde_gt(var, info, spec, "actuacion", None)
        if construido is not None:
            variables[var] = construido

    registro = gt.get("registro") or {}
    unidades: dict[str, dict[str, DatoConsolidado]] = {}
    for serie, datos_motor in gt["variables_consolidadas"]["motores"].items():
        unidad: dict[str, DatoConsolidado] = {}
        for var, info in datos_motor.items():
            construido = _dato_desde_gt(var, info, spec, "unidad", serie)
            if construido is not None:
                unidad[var] = construido
        if not registro.get("ausente"):
            canonico = f"{CANONICO}|{serie}"
            unidad["registro.dias"] = unidad_dato(
                "registro.dias", Decimal(str(registro["dias"])), serie, fuentes=["registro_funcionamiento"]
            )
            unidad["registro.inicio"] = unidad_dato(
                "registro.inicio",
                date.fromisoformat(registro["inicio"]),
                serie,
                fuentes=["registro_funcionamiento"],
            )
            unidad["registro.datos_canonicos"] = unidad_dato(
                "registro.datos_canonicos", canonico, serie, fuentes=["registro_funcionamiento"]
            )
            unidad["registro.hash_declarado"] = unidad_dato(
                "registro.hash_declarado",
                hashlib.sha256(canonico.encode("utf-8")).hexdigest(),
                serie,
                fuentes=["certificado_instalador"],
                tipo_evidencia="declarado",
            )
        unidades[serie] = unidad

    for clave, valor in (gt.get("hechos_documentales") or {}).items():
        if valor is None or clave in ALIAS_CONTEXTO:
            continue
        marca = re.match(r"^(?P<nombre>[^\[]+)\[(?P<serie>[^\]]+)\]$", clave)
        if marca:
            nombre_hecho, serie = marca["nombre"], marca["serie"]
            if serie not in unidades or nombre_hecho.startswith("registro."):
                continue
            if nombre_hecho.startswith("foto."):
                fotos = [f"{serie}-{nombre_hecho.split('.')[-1]}-{i}" for i in range(int(valor))]
                unidades[serie][nombre_hecho] = unidad_dato(
                    nombre_hecho, fotos, serie, fuentes=["informe_fotografico"]
                )
            continue
        tipo_doc = clave.split(".")[0]
        variables[clave] = dato(
            clave,
            _valor_hecho(valor),
            fuentes=[tipo_doc if tipo_doc != "convenio" else "convenio_cae"],
        )

    return actuacion(
        variables=variables,
        unidades=unidades,
        documentos=[d["tipo"] for d in gt["documentos"]],
        conflictos=[d for unidad in unidades.values() for d in unidad.values() if d.conflicto],
    )


@pytest.fixture
def caso_a(spec_ind240):
    return caso("A", spec_ind240)


def sin(act: ActuacionConsolidada, nombre: str, serie: str | None = SERIE) -> ActuacionConsolidada:
    """Copia de la actuacion sin ese dato (ausencia de dato, no valor nulo)."""
    if serie is not None and nombre in act.unidades.get(serie, {}):
        act.unidades[serie].pop(nombre)
    act.variables.pop(nombre, None)
    return act


def con(act: ActuacionConsolidada, nuevo: DatoConsolidado, serie: str | None = None) -> ActuacionConsolidada:
    if serie is not None:
        act.unidades.setdefault(serie, {})[nuevo.variable] = nuevo
    else:
        act.variables[nuevo.variable] = nuevo
    return act


# ---------------------------------------------------------------------------
# Utilidades de evaluacion
# ---------------------------------------------------------------------------


def evaluar_una(spec, id_regla: str, act: ActuacionConsolidada, fecha: date = FECHA) -> Resultado:
    contexto = construir_contexto(act, spec, fecha_evaluacion=fecha)
    avisos: list[str] = []
    return evaluar_regla(spec.regla(id_regla), act, spec, contexto, avisos, fecha_evaluacion=fecha).resultado


def logica(spec, id_regla: str) -> str:
    return spec.regla(id_regla).logica


# ---------------------------------------------------------------------------
# Fase 1 - ambito
# ---------------------------------------------------------------------------


def test_r_amb_01_cumple_con_equipo_incluido(spec_ind240, caso_a):
    assert "in ambito.tipos_equipo_incluidos" in logica(spec_ind240, "R-AMB-01")
    assert evaluar_una(spec_ind240, "R-AMB-01", caso_a) is Resultado.CUMPLE


def test_r_amb_01_falla_con_equipo_excluido(spec_ind240, caso_a):
    excluido = spec_ind240.ambito["tipos_equipo_excluidos"][0]
    con(caso_a, unidad_dato("tipo_equipo_accionado", excluido), SERIE)
    assert evaluar_una(spec_ind240, "R-AMB-01", caso_a) is Resultado.FALLA


def test_r_amb_01_no_evaluable_sin_tipo_de_equipo(spec_ind240, caso_a):
    sin(caso_a, "tipo_equipo_accionado")
    assert evaluar_una(spec_ind240, "R-AMB-01", caso_a) is Resultado.NO_EVALUABLE


def test_r_amb_02_cumple_aunque_la_factura_mencione_el_motor_existente(spec_ind240, caso_a):
    lineas = caso_a.variables["factura.lineas"].valor_consumido
    assert any("motor existente" in linea["descripcion"] for linea in lineas)
    assert {linea["categoria"] for linea in lineas} == {"variador", "instalacion"}
    assert evaluar_una(spec_ind240, "R-AMB-02", caso_a) is Resultado.CUMPLE


def test_r_amb_02_falla_si_la_factura_compra_un_motor(spec_ind240, caso_a):
    con(caso_a, dato("factura.lineas", [{"descripcion": "Motor nuevo 110 kW", "categoria": "motor"}]))
    assert evaluar_una(spec_ind240, "R-AMB-02", caso_a) is Resultado.FALLA


def test_r_amb_03_cumple_con_regimen_constante(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-AMB-03", caso_a) is Resultado.CUMPLE


def test_r_amb_03_falla_con_modulacion(spec_ind240, caso_a):
    valores = spec_ind240.variables["regimen_previo"]["valores"]
    con(caso_a, unidad_dato("regimen_previo", valores[1]), SERIE)
    assert evaluar_una(spec_ind240, "R-AMB-03", caso_a) is Resultado.FALLA


# ---------------------------------------------------------------------------
# Fase 2 - consistencia
# ---------------------------------------------------------------------------


def test_r_con_01_cumple_con_pm_igual_en_todas_las_fuentes(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CON-01", caso_a) is Resultado.CUMPLE


def test_r_con_01_falla_con_pm_distinto_entre_fuentes(spec_ind240, caso_a):
    con(
        caso_a,
        unidad_dato(
            "PM",
            None,
            fuentes=["ficha_tecnica_motor", "certificado_instalador"],
            valores_por_fuente={"ficha_tecnica_motor": "110", "certificado_instalador": "90"},
            conflicto=True,
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-CON-01", caso_a) is Resultado.FALLA


def test_r_con_02_cumple_y_falla_con_n1(spec_ind240, caso_a, spec_ind240_b=None):
    assert evaluar_una(spec_ind240, "R-CON-02", caso_a) is Resultado.CUMPLE
    con(
        caso_a,
        unidad_dato(
            "N1",
            Decimal("1485"),
            fuentes=["ficha_tecnica_motor", "certificado_instalador"],
            valores_por_fuente={"ficha_tecnica_motor": "1485", "certificado_instalador": "1480"},
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-CON-02", caso_a) is Resultado.FALLA


def test_r_con_03_cumple_dentro_de_tolerancia(spec_ind240, caso_a):
    assert "abs(" in logica(spec_ind240, "R-CON-03")
    assert evaluar_una(spec_ind240, "R-CON-03", caso_a) is Resultado.CUMPLE


def test_r_con_03_falla_fuera_de_tolerancia(spec_ind240, caso_a):
    con(
        caso_a,
        unidad_dato(
            "N2",
            Decimal("1188"),
            tipo_evidencia="derivado",
            tipados={"derivado": Decimal("1188"), "declarado": Decimal("1200")},
            fuentes=["registro_funcionamiento", "certificado_instalador"],
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-CON-03", caso_a) is Resultado.FALLA


def test_r_con_03_no_evaluable_sin_n2_derivado(spec_ind240, caso_a):
    con(
        caso_a,
        unidad_dato(
            "N2",
            Decimal("1188"),
            tipo_evidencia="declarado",
            tipados={"declarado": Decimal("1188")},
            fuentes=["certificado_instalador"],
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-CON-03", caso_a) is Resultado.NO_EVALUABLE


def test_r_con_04_cumple_con_numeros_de_serie_coincidentes(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CON-04", caso_a) is Resultado.CUMPLE


def test_r_con_04_falla_con_numero_de_serie_distinto_entre_documentos(spec_ind240, caso_a):
    con(
        caso_a,
        unidad_dato(
            "num_serie_variador",
            "VSD-SYN-0001",
            fuentes=["factura", "certificado_instalador"],
            valores_por_fuente={"factura": "VSD-SYN-0001", "certificado_instalador": "VSD-SYN-0002"},
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-CON-04", caso_a) is Resultado.FALLA


def test_r_con_05_cumple_con_nif_unico(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CON-05", caso_a) is Resultado.CUMPLE


def test_r_con_05_falla_con_nif_distinto(spec_ind240, caso_a):
    con(
        caso_a,
        dato(
            "titular_nif",
            "B99001018",
            fuentes=["ficha_cumplimentada", "factura"],
            valores_por_fuente={"ficha_cumplimentada": "B99001018", "factura": "B00000000"},
        ),
    )
    assert evaluar_una(spec_ind240, "R-CON-05", caso_a) is Resultado.FALLA


def test_r_con_05_no_evaluable_sin_titular(spec_ind240, caso_a):
    sin(caso_a, "titular_nif", serie=None)
    assert evaluar_una(spec_ind240, "R-CON-05", caso_a) is Resultado.NO_EVALUABLE


def test_r_con_07_cumple_con_numero_de_motores_coherente(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CON-07", caso_a) is Resultado.CUMPLE


def test_r_con_07_falla_con_numero_de_motores_incoherente(spec_ind240, caso_a):
    con(
        caso_a,
        dato(
            "n_motores",
            Decimal("1"),
            fuentes=["factura", "certificado_instalador"],
            valores_por_fuente={"factura": "1", "certificado_instalador": "2"},
        ),
    )
    assert evaluar_una(spec_ind240, "R-CON-07", caso_a) is Resultado.FALLA


def test_r_tmp_01_cumple_con_fechas_ordenadas(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-TMP-01", caso_a) is Resultado.CUMPLE


def test_r_tmp_01_falla_con_inicio_posterior_al_fin(spec_ind240, caso_a):
    con(caso_a, dato("fecha_inicio_actuacion", date(2026, 6, 1), fuentes=["ficha_cumplimentada"]))
    assert evaluar_una(spec_ind240, "R-TMP-01", caso_a) is Resultado.FALLA


def test_r_cal_01_cumple_con_n2_menor_que_n1(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CAL-01", caso_a) is Resultado.CUMPLE


def test_r_cal_01_falla_con_n2_mayor_que_n1(spec_ind240, caso_a):
    con(caso_a, unidad_dato("N2", Decimal("1500"), tipo_evidencia="derivado"), SERIE)
    assert evaluar_una(spec_ind240, "R-CAL-01", caso_a) is Resultado.FALLA


def test_r_cal_01_no_evaluable_sin_n2(spec_ind240, caso_a):
    sin(caso_a, "N2")
    assert evaluar_una(spec_ind240, "R-CAL-01", caso_a) is Resultado.NO_EVALUABLE


def test_r_cal_02_cumple_con_fila_exacta(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CAL-02", caso_a) is Resultado.CUMPLE


def test_r_cal_02_falla_sin_fila_exacta(spec_ind240, caso_a):
    con(caso_a, unidad_dato("PM", Decimal("111"), fuentes=["ficha_tecnica_motor"]), SERIE)
    assert evaluar_una(spec_ind240, "R-CAL-02", caso_a) is Resultado.FALLA


def test_r_cal_04_cumple_porque_p_sale_de_la_tabla(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CAL-04", caso_a) is Resultado.CUMPLE


def test_r_cal_04_falla_si_p_viene_de_un_documento(spec_ind240, caso_a):
    con(
        caso_a,
        unidad_dato(
            "p",
            Decimal("0.0354"),
            fuentes=["ficha_tecnica_variador"],
            fuente_primaria="ficha_tecnica_variador",
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-CAL-04", caso_a) is Resultado.FALLA


# ---------------------------------------------------------------------------
# Fase 4 - posterior al calculo
# ---------------------------------------------------------------------------


def test_r_cal_03_cumple_con_controles_fisicos_correctos(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.resultado("R-CAL-03").resultado is Resultado.CUMPLE


def test_r_cal_03_falla_si_la_potencia_promedio_supera_la_nominal(spec_ind240, caso_a):
    con(caso_a, unidad_dato("P_prom", Decimal("200"), tipo_evidencia="derivado"), SERIE)
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.resultado("R-CAL-03").resultado is Resultado.FALLA
    assert evaluacion.veredicto == VEREDICTO_BLOQUEADO


def test_r_cal_03_no_evaluable_sin_calculo(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-CAL-03", caso_a) is Resultado.NO_EVALUABLE


def test_r_con_06_cumple_si_el_convenio_declara_el_ahorro_calculado(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.resultado("R-CON-06").resultado is Resultado.CUMPLE


def test_r_con_06_falla_si_el_convenio_declara_otro_ahorro(spec_ind240, caso_a):
    con(caso_a, dato("convenio.ahorro_kwh", Decimal("250000"), fuentes=["convenio_cae"]))
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.resultado("R-CON-06").resultado is Resultado.FALLA
    assert evaluacion.veredicto == VEREDICTO_SUBSANABLE


# ---------------------------------------------------------------------------
# Fase 5 - resto: documental
# ---------------------------------------------------------------------------


def test_r_doc_01_cumple_con_todos_los_obligatorios(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-DOC-01", caso_a) is Resultado.CUMPLE


def test_r_doc_01_falla_si_falta_un_documento_obligatorio(spec_ind240, caso_a):
    obligatorio = spec_ind240.documentos_obligatorios()[0]["tipo"]
    quedan = [d for d in caso_a.documentos if d.tipo != obligatorio]
    act = actuacion(
        variables=caso_a.variables,
        unidades=caso_a.unidades,
        documentos=[str(d.tipo) for d in quedan],
    )
    assert evaluar_una(spec_ind240, "R-DOC-01", act) is Resultado.FALLA


def test_r_doc_01_el_documento_condicional_no_obliga_y_deja_aviso(spec_ind240, caso_a):
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    condicionales = [d for d in contexto.datos["doc"] if d["tipo"] not in {x.tipo for x in caso_a.documentos}]
    assert any(d["obligatorio"] is False for d in condicionales)
    assert any("condicional no evaluable" in aviso for aviso in contexto.avisos)


def test_r_doc_02_cumple_con_fotos_antes_y_despues(spec_ind240, caso_a):
    assert "for each" in logica(spec_ind240, "R-DOC-02")
    assert evaluar_una(spec_ind240, "R-DOC-02", caso_a) is Resultado.CUMPLE


def test_r_doc_02_falla_sin_foto_despues(spec_ind240, caso_a):
    con(caso_a, unidad_dato("foto.despues", [], fuentes=["informe_fotografico"]), SERIE)
    assert evaluar_una(spec_ind240, "R-DOC-02", caso_a) is Resultado.FALLA


def test_r_doc_03_cumple_y_falla_con_los_campos_minimos_de_la_factura(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-DOC-03", caso_a) is Resultado.CUMPLE
    con(caso_a, dato("factura.campos_minimos_presentes", False, fuentes=["factura"]))
    assert evaluar_una(spec_ind240, "R-DOC-03", caso_a) is Resultado.FALLA


def test_r_doc_03_no_evaluable_sin_el_hecho(spec_ind240, caso_a):
    sin(caso_a, "factura.campos_minimos_presentes", serie=None)
    assert evaluar_una(spec_ind240, "R-DOC-03", caso_a) is Resultado.NO_EVALUABLE


def test_r_doc_04_cumple_con_todos_los_requisitos_del_convenio(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-DOC-04", caso_a) is Resultado.CUMPLE


def test_r_doc_04_falla_si_el_convenio_omite_un_requisito(spec_ind240, caso_a):
    presentes = list(caso_a.variables["convenio.requisitos_presentes"].valor_consumido)
    con(caso_a, dato("convenio.requisitos_presentes", presentes[:-1], fuentes=["convenio_cae"]))
    assert evaluar_una(spec_ind240, "R-DOC-04", caso_a) is Resultado.FALLA


def test_r_doc_05_cumple_y_falla_con_la_firma_de_la_ficha(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-DOC-05", caso_a) is Resultado.CUMPLE
    con(caso_a, dato("ficha_cumplimentada.firmada", False, fuentes=["ficha_cumplimentada"]))
    assert evaluar_una(spec_ind240, "R-DOC-05", caso_a) is Resultado.FALLA


# ---------------------------------------------------------------------------
# Fase 5 - resto: evidencia temporal y procedimiento
# ---------------------------------------------------------------------------


def test_r_evd_01_cumple_con_treinta_dias(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-EVD-01", caso_a) is Resultado.CUMPLE


def test_r_evd_01_falla_con_registro_corto(spec_ind240, caso_a):
    con(caso_a, unidad_dato("registro.dias", Decimal("12"), fuentes=["registro_funcionamiento"]), SERIE)
    assert evaluar_una(spec_ind240, "R-EVD-01", caso_a) is Resultado.FALLA


def test_r_evd_01_no_evaluable_sin_registro(spec_ind240, caso_a):
    sin(caso_a, "registro.dias")
    assert evaluar_una(spec_ind240, "R-EVD-01", caso_a) is Resultado.NO_EVALUABLE


def test_r_evd_02_cumple_con_registro_posterior_a_la_puesta_en_marcha(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-EVD-02", caso_a) is Resultado.CUMPLE


def test_r_evd_02_falla_con_registro_anterior(spec_ind240, caso_a):
    con(caso_a, unidad_dato("registro.inicio", date(2026, 1, 5), fuentes=["registro_funcionamiento"]), SERIE)
    assert evaluar_una(spec_ind240, "R-EVD-02", caso_a) is Resultado.FALLA


def test_r_evd_03_cumple_con_la_huella_del_registro(spec_ind240, caso_a):
    assert "sha256(" in logica(spec_ind240, "R-EVD-03")
    assert evaluar_una(spec_ind240, "R-EVD-03", caso_a) is Resultado.CUMPLE


def test_r_evd_03_falla_con_huella_que_no_coincide(spec_ind240, caso_a):
    con(
        caso_a,
        unidad_dato("registro.hash_declarado", "0" * 64, fuentes=["certificado_instalador"]),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-EVD-03", caso_a) is Resultado.FALLA


def test_r_evd_04_cumple_con_n2_derivado(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-EVD-04", caso_a) is Resultado.CUMPLE


def test_r_evd_04_falla_con_n2_solo_declarado(spec_ind240, caso_a):
    con(
        caso_a,
        unidad_dato(
            "N2",
            Decimal("1188"),
            tipo_evidencia="declarado",
            tipados={"declarado": Decimal("1188")},
            fuentes=["certificado_instalador"],
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-EVD-04", caso_a) is Resultado.FALLA


def test_r_tmp_02_cumple_con_convenio_firmado_antes(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-TMP-02", caso_a) is Resultado.CUMPLE


def test_r_tmp_02_falla_con_convenio_firmado_despues(spec_ind240, caso_a):
    con(caso_a, dato("convenio.fecha_firma", date(2026, 12, 1), fuentes=["convenio_cae"]))
    assert evaluar_una(spec_ind240, "R-TMP-02", caso_a) is Resultado.FALLA


def test_r_tmp_03_cumple_dentro_de_los_tres_anos(spec_ind240, caso_a):
    assert "3 años" in logica(spec_ind240, "R-TMP-03")
    assert evaluar_una(spec_ind240, "R-TMP-03", caso_a) is Resultado.CUMPLE


def test_r_tmp_03_falla_pasados_tres_anos(spec_ind240, caso_a):
    assert evaluar_una(spec_ind240, "R-TMP-03", caso_a, fecha=date(2030, 1, 1)) is Resultado.FALLA


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------


NOMBRES_ADR_2_4 = (
    "tipo_equipo_accionado",
    "ambito.tipos_equipo_incluidos",
    "regimen_previo",
    "doc",
    "presente",
    "motor",
    "foto.antes",
    "foto.despues",
    "factura.campos_minimos_presentes",
    "ficha_cumplimentada.firmada",
    "registro.dias",
    "registro.inicio",
    "registro.hash_declarado",
    "registro.datos_canonicos",
    "fecha_fin_actuacion",
    "fecha_inicio_actuacion",
    "N2.evidencia",
    "N2.declarado",
    "N2.derivado",
    "PM.valores_por_fuente",
    "N1.valores_por_fuente",
    "num_serie_variador",
    "num_serie_motor",
    "titular_nif",
    "n_motores_por_fuente",
    "convenio.ahorro_kwh",
    "convenio.fecha_firma",
    "solicitud.fecha",
    "N2",
    "N1",
    "PM",
    "p.fuente",
    "REG1781_CUADRO6",
)


def test_construir_contexto_resuelve_los_nombres_de_adr_2_4(spec_ind240, caso_a):
    unidad = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA).contexto_unidad(SERIE)
    for nombre in NOMBRES_ADR_2_4:
        assert unidad.resolver(nombre) is not NO_EVALUABLE, nombre


def test_ninguna_regla_queda_no_evaluable_en_el_caso_completo(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.no_evaluables == []


def test_argumentos_unique_detecta_los_nombres_sin_sufijo(spec_ind240):
    assert argumentos_unique("unique(num_serie_variador) and unique(num_serie_motor)") == (
        "num_serie_variador",
        "num_serie_motor",
    )
    assert argumentos_unique("unique(PM.valores_por_fuente)") == ()
    assert argumentos_unique("unique(n_motores_por_fuente)") == ()


def test_unique_sin_sufijo_se_resuelve_sobre_los_valores_por_fuente(spec_ind240, caso_a):
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    # Sin la sustitucion, el nombre a secas es el escalar consolidado y `unique` seria siempre cierto.
    assert isinstance(contexto.contexto_unidad(SERIE).resolver("num_serie_motor"), str)
    con(
        caso_a,
        unidad_dato(
            "num_serie_motor",
            "MTR-SYN-0001",
            fuentes=["ficha_tecnica_motor", "certificado_instalador"],
            valores_por_fuente={"ficha_tecnica_motor": "MTR-SYN-0001", "certificado_instalador": "MTR-X"},
        ),
        SERIE,
    )
    assert evaluar_una(spec_ind240, "R-CON-04", caso_a) is Resultado.FALLA


def test_contexto_expone_la_tabla_y_el_ambito(spec_ind240, caso_a):
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    id_tabla = next(iter(spec_ind240.tablas))
    filas = contexto.resolver(id_tabla)
    assert isinstance(filas, list) and filas and isinstance(filas[0], dict)
    assert contexto.resolver("ambito.tipos_equipo_incluidos") == spec_ind240.ambito["tipos_equipo_incluidos"]


def test_contexto_rechaza_una_fecha_que_no_es_date(spec_ind240, caso_a):
    with pytest.raises(ErrorReglas):
        construir_contexto(caso_a, spec_ind240, fecha_evaluacion="2026-09-18")


def test_identificador_no_resoluble_deja_no_evaluable_con_motivo(spec_ind240, caso_a):
    sin(caso_a, "registro.dias")
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    resultado = evaluar_regla(
        spec_ind240.regla("R-EVD-01"), caso_a, spec_ind240, contexto, [], fecha_evaluacion=FECHA
    )
    assert resultado.resultado is Resultado.NO_EVALUABLE
    assert "registro.dias" in (resultado.motivo or "")


def test_error_de_contexto_no_sale_como_excepcion(spec_ind240, caso_a):
    # Un valor de familia equivocada (texto donde la regla espera fecha) es contexto mal construido.
    con(caso_a, dato("fecha_fin_actuacion", "2026-03-02", fuentes=["ficha_cumplimentada"]))
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    avisos: list[str] = []
    resultado = evaluar_regla(
        spec_ind240.regla("R-TMP-01"), caso_a, spec_ind240, contexto, avisos, fecha_evaluacion=FECHA
    )
    assert resultado.resultado is Resultado.NO_EVALUABLE
    assert resultado.motivo and resultado.motivo.startswith("error de contexto")
    assert avisos


# ---------------------------------------------------------------------------
# Nivel unidad
# ---------------------------------------------------------------------------


def test_regla_de_unidad_falla_si_falla_en_una_de_dos_unidades(spec_ind240, caso_a):
    segunda = "MTR-SYN-0002"
    caso_a.unidades[segunda] = {
        nombre: replace(d, num_serie_motor=segunda) for nombre, d in caso_a.unidades[SERIE].items()
    }
    excluido = spec_ind240.ambito["tipos_equipo_excluidos"][0]
    con(caso_a, unidad_dato("tipo_equipo_accionado", excluido, serie=segunda), segunda)
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    resultado = evaluar_regla(
        spec_ind240.regla("R-AMB-01"), caso_a, spec_ind240, contexto, [], fecha_evaluacion=FECHA
    )
    assert resultado.resultado is Resultado.FALLA
    assert resultado.por_unidad[SERIE] is Resultado.CUMPLE
    assert resultado.por_unidad[segunda] is Resultado.FALLA


def test_regla_de_unidad_sin_unidades_es_no_evaluable(spec_ind240, caso_a):
    caso_a.unidades.clear()
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    resultado = evaluar_regla(
        spec_ind240.regla("R-AMB-01"), caso_a, spec_ind240, contexto, [], fecha_evaluacion=FECHA
    )
    assert resultado.resultado is Resultado.NO_EVALUABLE
    assert resultado.motivo == "sin unidades sobre las que evaluar"


# ---------------------------------------------------------------------------
# Casos A-D completos
# ---------------------------------------------------------------------------


def test_caso_a_prevalidado_con_el_ahorro_exacto(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    gt = ground_truth("A")
    assert evaluacion.veredicto == VEREDICTO_PREVALIDADO == gt["veredicto_esperado"]
    assert evaluacion.falladas == []
    assert evaluacion.calculo is not None
    assert evaluacion.calculo.total == Decimal(gt["aetotal_esperado"]["exacto"]) == Decimal("305829.6")
    assert evaluacion.calculo.total_cae == gt["aetotal_esperado"]["cae"]
    assert evaluacion.calculo.provisional is False
    assert evaluacion.resultado("R-CAL-02").resultado is Resultado.CUMPLE
    assert evaluacion.resultado("R-CAL-04").resultado is Resultado.CUMPLE
    assert evaluacion.resultado("R-EVD-03").resultado is Resultado.CUMPLE
    assert evaluacion.resultado("R-AMB-02").resultado is Resultado.CUMPLE
    assert evaluacion.fases_saltadas == ()
    assert set(evaluacion.fases_evaluadas) == set(ORDEN_FASES)


def test_caso_a_interpretaciones_y_hash(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.hash_reglas == spec_ind240.hash_reglas
    assert {"INT-01", "INT-06"} <= set(evaluacion.interpretaciones_aplicadas)
    assert {"INT-03", "INT-04"} <= set(evaluacion.interpretaciones_aplicadas)
    assert evaluacion.carencias == []


def test_caso_b_subsanable_con_calculo_provisional(spec_ind240):
    act = caso("B", spec_ind240)
    evaluacion = evaluar_actuacion(act, spec_ind240, fecha_evaluacion=FECHA)
    gt = ground_truth("B")
    assert evaluacion.veredicto == VEREDICTO_SUBSANABLE == gt["veredicto_esperado"]
    assert set(gt["reglas_falladas_esperadas"]) <= set(evaluacion.falladas)
    assert set(evaluacion.falladas) == {"R-EVD-04", "R-DOC-01"}
    for id_regla in gt["reglas_no_evaluables_esperadas"]:
        assert evaluacion.resultado(id_regla).resultado is Resultado.NO_EVALUABLE
    assert evaluacion.calculo is not None
    assert evaluacion.calculo.total == Decimal("305829.6")
    assert evaluacion.calculo.provisional is True
    assert any("calculo provisional" in aviso for aviso in evaluacion.avisos)


def test_caso_b_carencias_con_documentos(spec_ind240):
    act = caso("B", spec_ind240)
    evaluacion = evaluar_actuacion(act, spec_ind240, fecha_evaluacion=FECHA)
    carencias = {c["id"]: c for c in evaluacion.carencias}
    assert set(carencias) == {"R-EVD-04", "R-DOC-01"}
    assert "registro_funcionamiento" in carencias["R-DOC-01"]["documentos"]
    assert "registro_funcionamiento" in carencias["R-EVD-04"]["documentos"]
    assert carencias["R-EVD-04"]["mensaje"]


def test_caso_b_no_es_bloqueado_aunque_una_bloqueante_quede_no_evaluable(spec_ind240):
    act = caso("B", spec_ind240)
    evaluacion = evaluar_actuacion(act, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.resultado("R-CON-03").resultado is Resultado.NO_EVALUABLE
    assert evaluacion.resultado("R-CON-03").severidad == "BLOQUEANTE_DATOS"
    assert evaluacion.veredicto != VEREDICTO_BLOQUEADO


def test_caso_c_bloqueado_por_conflicto_sin_calculo(spec_ind240):
    act = caso("C", spec_ind240)
    evaluacion = evaluar_actuacion(act, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.veredicto == VEREDICTO_BLOQUEADO
    assert evaluacion.calculo is None
    assert evaluacion.resultado("R-CON-01").resultado is Resultado.FALLA
    assert evaluacion.resultado("R-CAL-03").resultado is Resultado.NO_EVALUABLE
    assert evaluacion.resultado("R-CON-06").resultado is Resultado.NO_EVALUABLE
    assert evaluacion.bloqueo_por_conflicto == ("PM",)
    assert "resto" in evaluacion.fases_evaluadas
    assert "post_calculo" in evaluacion.fases_saltadas
    assert evaluacion.resultado("R-DOC-05").resultado is Resultado.CUMPLE


def test_conflicto_bloquea_aunque_la_regla_no_sea_evaluable(spec_ind240, caso_a):
    conflictivo = unidad_dato(
        "N2",
        None,
        tipo_evidencia="derivado",
        tipados={},
        fuentes=["registro_funcionamiento"],
        conflicto=True,
    )
    con(caso_a, conflictivo, SERIE)
    act = actuacion(
        variables=caso_a.variables,
        unidades=caso_a.unidades,
        documentos=[str(d.tipo) for d in caso_a.documentos],
        conflictos=[conflictivo],
    )
    evaluacion = evaluar_actuacion(act, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.veredicto == VEREDICTO_BLOQUEADO
    assert evaluacion.bloqueo_por_conflicto == ("N2",)
    assert evaluacion.calculo is None


def test_caso_d_no_elegible_y_fases_posteriores_sin_evaluar(spec_ind240):
    act = caso("D", spec_ind240)
    evaluacion = evaluar_actuacion(act, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.veredicto == VEREDICTO_NO_ELEGIBLE
    assert evaluacion.resultado("R-AMB-01").resultado is Resultado.FALLA
    assert evaluacion.calculo is None
    assert evaluacion.resultado("R-CON-06").resultado is not Resultado.FALLA
    assert evaluacion.resultado("R-CON-06").motivo == "fase no evaluada: detenido en ambito"
    for fase in ("consistencia", "calculo", "post_calculo", "resto"):
        assert fase in evaluacion.fases_saltadas
    assert evaluacion.fases_evaluadas == ("cabecera", "ambito")
    assert evaluacion.falladas == ["R-AMB-01"]


def test_caso_d_ignora_el_ahorro_declarado(spec_ind240):
    gt = ground_truth("D")
    assert gt["hechos_documentales"]["ficha_cumplimentada.ahorro_declarado_kwh"]
    evaluacion = evaluar_actuacion(caso("D", spec_ind240), spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.calculo is None


# ---------------------------------------------------------------------------
# Veredicto
# ---------------------------------------------------------------------------


def test_veredicto_por_prioridad(spec_ind240, caso_a):
    excluido = spec_ind240.ambito["tipos_equipo_excluidos"][0]
    con(caso_a, unidad_dato("tipo_equipo_accionado", excluido), SERIE)
    con(caso_a, dato("ficha_cumplimentada.firmada", False, fuentes=["ficha_cumplimentada"]))
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.veredicto == VEREDICTO_NO_ELEGIBLE


def test_veredicto_de_es_el_peor_de_las_severidades_falladas(spec_ind240, caso_a):
    contexto = construir_contexto(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    resultados = [
        evaluar_regla(spec_ind240.regla(i), caso_a, spec_ind240, contexto, [], fecha_evaluacion=FECHA)
        for i in ("R-AMB-01", "R-DOC-05")
    ]
    assert veredicto_de(resultados) == VEREDICTO_PREVALIDADO
    assert veredicto_de(resultados, conflicto=True) == VEREDICTO_BLOQUEADO


def test_un_aviso_fallido_no_cambia_el_veredicto(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=date(2030, 1, 1))
    assert evaluacion.resultado("R-TMP-03").resultado is Resultado.FALLA
    assert evaluacion.resultado("R-TMP-03").severidad == "AVISO"
    assert evaluacion.veredicto == VEREDICTO_PREVALIDADO
    assert any("R-TMP-03" in aviso for aviso in evaluacion.avisos)


def test_no_evaluable_no_cambia_el_veredicto(spec_ind240, caso_a):
    sin(caso_a, "registro.dias")
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.resultado("R-EVD-01").resultado is Resultado.NO_EVALUABLE
    assert evaluacion.veredicto == VEREDICTO_PREVALIDADO


def test_la_evaluacion_es_determinista(spec_ind240, caso_a):
    primera = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    segunda = evaluar_actuacion(caso("A", spec_ind240), spec_ind240, fecha_evaluacion=FECHA)
    assert primera.a_dict() == segunda.a_dict()


def test_las_26_reglas_aparecen_en_el_resultado_y_en_orden_de_fase(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert len(evaluacion.resultados) == len(spec_ind240.reglas) == 26
    assert {r.id for r in evaluacion.resultados} == set(spec_ind240.ids_reglas)
    fases = [ORDEN_FASES.index(r.fase) for r in evaluacion.resultados]
    assert fases == sorted(fases)


def test_evaluar_actuacion_exige_una_actuacion_consolidada(spec_ind240):
    with pytest.raises(ErrorReglas):
        evaluar_actuacion({}, spec_ind240, fecha_evaluacion=FECHA)  # type: ignore[arg-type]


def test_el_calculo_se_puede_inyectar(spec_ind240, caso_a):
    llamadas: list[dict] = []

    def falso_calculo(*args, **kwargs):
        llamadas.append(kwargs)
        raise RuntimeError("calculo no disponible")

    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA, calcular_fn=falso_calculo)
    assert llamadas and llamadas[0]["provisional"] is False
    assert evaluacion.calculo is None
    assert any("error de calculo" in aviso for aviso in evaluacion.avisos)


def test_evaluacion_serializable(spec_ind240, caso_a):
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    datos = evaluacion.a_dict()
    assert json.dumps(datos, ensure_ascii=False)
    assert datos["veredicto"] == VEREDICTO_PREVALIDADO
    assert isinstance(evaluacion, Evaluacion)


# ---------------------------------------------------------------------------
# Higiene del fuente
# ---------------------------------------------------------------------------


def test_el_modulo_no_usa_eval_ni_float():
    fuente = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("eval(", "exec(", "compile(", "float("):
        assert prohibido not in fuente, prohibido


def test_el_modulo_no_importa_de_fuera_del_nucleo():
    fuente = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("agentes", "salida", "generator", "tests"):
        assert not re.search(rf"^\s*(from|import)\s+{prohibido}\b", fuente, re.MULTILINE)


def test_el_modulo_no_cablea_la_ficha(spec_ind240):
    """Ni el codigo de ficha, ni ids de regla o de tabla, ni nombres de variable como literal de cadena.

    El unico nombre de la ficha que aparece como literal es el del alias declarado (`ALIAS_CONTEXTO`);
    `num_serie_motor` aparece solo como **atributo** del contrato de `engine/calculo.py` (ADR-002 §2.5), que
    es vocabulario del marco, no un acceso por nombre a la ficha.
    """
    fuente = FUENTE.read_text(encoding="utf-8")
    for nombre in [spec_ind240.codigo, *spec_ind240.tablas, *spec_ind240.ids_reglas]:
        assert not re.search(rf"\b{re.escape(nombre)}\b", fuente), nombre
    literales = [v for v in spec_ind240.variables]
    literales += [str(c["id"]) for c in spec_ind240.calculo["controles_fisicos"]]
    literales += [str(spec_ind240.calculo["motor"]["salida"]), str(spec_ind240.calculo["total"]["salida"])]
    literales += [str(d["tipo"]) for d in spec_ind240.documentacion]
    for nombre in literales:
        assert f'"{nombre}"' not in fuente, nombre
        assert f"'{nombre}'" not in fuente, nombre
    assert "if ficha" not in fuente


def test_los_alias_estan_declarados_y_acotados():
    assert set(ALIAS_CONTEXTO) == {"solicitud.fecha"}
    for nombre, alias in ALIAS_CONTEXTO.items():
        assert alias["origen"] and alias["nota"], nombre


# ---------------------------------------------------------------------------
# Calculo provisional (docs/04 §4.1; caso B)
# ---------------------------------------------------------------------------


def test_nunca_hay_sustitucion_provisional_si_el_veredicto_es_prevalidado(spec_ind240, caso_a):
    """Sin el dato que sostiene el ahorro y sin ninguna regla que lo recoja, no se publica ahorro."""
    sin(caso_a, "h_despues")
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.veredicto == VEREDICTO_PREVALIDADO
    assert evaluacion.calculo is not None
    assert evaluacion.calculo.total is None
    assert evaluacion.calculo.provisional is False
    assert not any("calculo provisional" in aviso for aviso in evaluacion.avisos)


def test_el_caso_b_pide_el_calculo_como_provisional(spec_ind240):
    act = caso("B", spec_ind240)
    llamadas: list[dict] = []

    def espia(spec_datos, unidades, tablas, **kwargs):
        llamadas.append({"unidades": unidades, **kwargs})
        from engine.calculo import calcular as real

        return real(spec_datos, unidades, tablas, **kwargs)

    evaluacion = evaluar_actuacion(act, spec_ind240, fecha_evaluacion=FECHA, calcular_fn=espia)
    assert llamadas[0]["provisional"] is True
    entradas = llamadas[0]["unidades"][SERIE]
    assert entradas["h_despues"] == entradas["h_antes"] == Decimal("6000")
    assert evaluacion.calculo is not None and evaluacion.calculo.provisional is True


def test_un_subsanable_posterior_al_calculo_marca_el_resultado_como_provisional(spec_ind240, caso_a):
    con(caso_a, dato("convenio.ahorro_kwh", Decimal("250000"), fuentes=["convenio_cae"]))
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.veredicto == VEREDICTO_SUBSANABLE
    assert evaluacion.calculo is not None and evaluacion.calculo.provisional is True


# ---------------------------------------------------------------------------
# H3 (docs/05 §4.5) - la guarda que impide calcular con datos incoherentes
# ---------------------------------------------------------------------------

#: Precondicion del calculo declarada en la spec activa (`calculo.precondiciones`). Es prosa, no una
#: expresion del vocabulario, asi que `engine/calculo.py` no la evalua: la delega y la aplica la rama
#: `elif bloqueo_previo` de `evaluar_actuacion`. Los tests de esta seccion son su unica verificacion.
PRECONDICION_DELEGADA = "ninguna regla con severidad BLOQUEANTE fallida"


def espia_calculo() -> tuple[list[dict], object]:
    """Envoltorio del calculo real que registra si se ha llegado a pedir."""
    llamadas: list[dict] = []

    def espia(spec_datos, unidades, tablas, **kwargs):
        llamadas.append({"unidades": unidades, **kwargs})
        from engine.calculo import calcular as real

        return real(spec_datos, unidades, tablas, **kwargs)

    return llamadas, espia


def _sin_calculo_por_bloqueo(spec, act: ActuacionConsolidada, id_regla: str) -> Evaluacion:
    """Comprueba la propiedad completa: bloqueante no fisica fallada -> ni se pide el calculo ni hay ahorro.

    Es el test que mata el mutante de H3: sin la rama `elif bloqueo_previo` de `engine/reglas.py` el calculo
    se pide igual, sale bien (ninguna precondicion fisica lo para) y una actuacion BLOQUEADA publica su
    ahorro. `engine/calculo.py` no puede cubrir esto: la precondicion que lo prohibe (PRECONDICION_DELEGADA)
    es prosa y esta delegada en el motor de reglas.
    """
    llamadas, espia = espia_calculo()
    evaluacion = evaluar_actuacion(act, spec, fecha_evaluacion=FECHA, calcular_fn=espia)

    fallada = evaluacion.resultado(id_regla)
    assert fallada.resultado is Resultado.FALLA
    assert fallada.severidad == "BLOQUEANTE_DATOS"
    assert evaluacion.veredicto == VEREDICTO_BLOQUEADO
    # Entra por la rama de bloqueo previo, no por la de conflicto entre fuentes (caso C).
    assert evaluacion.bloqueo_por_conflicto == ()
    assert act.conflictos == []
    # No se pide el calculo...
    assert llamadas == [], f"con {id_regla} fallada no se puede pedir el calculo"
    # ...y no se publica ahorro por ninguna via.
    assert evaluacion.calculo is None
    assert evaluacion.a_dict()["veredicto"] == VEREDICTO_BLOQUEADO
    assert "calculo" in evaluacion.fases_saltadas
    assert "post_calculo" in evaluacion.fases_saltadas
    motivo = evaluacion.resultado("R-CAL-03").motivo or ""
    assert "sin calculo" in motivo and id_regla in motivo
    # El aviso de la precondicion delegada solo se emite cuando el calculo procede.
    assert not any(PRECONDICION_DELEGADA in aviso for aviso in evaluacion.avisos)
    return evaluacion


def test_bloqueo_temporal_sin_conflicto_no_calcula_ni_publica_ahorro(spec_ind240, caso_a):
    """R-TMP-01 (fecha de inicio posterior a la de fin): bloqueo sin precondicion fisica que lo tape."""
    con(caso_a, dato("fecha_inicio_actuacion", date(2026, 6, 1), fuentes=["ficha_cumplimentada"]))
    evaluacion = _sin_calculo_por_bloqueo(spec_ind240, caso_a, "R-TMP-01")
    assert evaluacion.resultado("R-CAL-01").resultado is Resultado.CUMPLE  # N2 < N1 se sigue cumpliendo


def test_bloqueo_documental_sin_conflicto_no_calcula_ni_publica_ahorro(spec_ind240, caso_a):
    """R-CON-05 (NIF del titular distinto entre documentos): tampoco hay precondicion fisica que lo pare."""
    con(
        caso_a,
        dato(
            "titular_nif",
            "B99001018",
            fuentes=["ficha_cumplimentada", "factura"],
            valores_por_fuente={"ficha_cumplimentada": "B99001018", "factura": "B00000000"},
        ),
    )
    _sin_calculo_por_bloqueo(spec_ind240, caso_a, "R-CON-05")


def test_el_bloqueo_previo_no_depende_de_que_el_calculo_sea_imposible(spec_ind240, caso_a):
    """El mismo caso A, sin la regla temporal rota, si calcula 305.829,6: lo que retira el ahorro es la
    regla bloqueante fallida, no una imposibilidad fisica ni un dato ausente."""
    llamadas, espia = espia_calculo()
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA, calcular_fn=espia)
    assert len(llamadas) == 1
    assert evaluacion.veredicto == VEREDICTO_PREVALIDADO
    assert evaluacion.calculo is not None and evaluacion.calculo.total == Decimal("305829.6")

    con(caso_a, dato("fecha_inicio_actuacion", date(2026, 6, 1), fuentes=["ficha_cumplimentada"]))
    bloqueada = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert bloqueada.veredicto == VEREDICTO_BLOQUEADO
    assert bloqueada.calculo is None


def test_la_precondicion_en_prosa_de_la_spec_la_aplica_el_motor_de_reglas(spec_ind240, caso_a):
    """Ata la precondicion declarada en `calculo.precondiciones` con el sitio donde se cumple.

    `engine/calculo.py` la deja en `precondiciones_delegadas` porque es prosa; el unico sitio donde se aplica
    es la rama `elif bloqueo_previo` de `engine/reglas.py`. Si desaparece de la spec o del codigo, este test
    lo dice.
    """
    assert PRECONDICION_DELEGADA in spec_ind240.plan.precondiciones_delegadas
    assert PRECONDICION_DELEGADA in spec_ind240.precondiciones_texto
    assert PRECONDICION_DELEGADA not in {e.texto for e in spec_ind240.plan.precondiciones}

    sin_bloqueo = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    comprobada = [a for a in sin_bloqueo.avisos if PRECONDICION_DELEGADA in a]
    assert len(comprobada) == 1
    assert "ninguna bloqueante fallida antes del calculo" in comprobada[0]

    con(caso_a, dato("fecha_inicio_actuacion", date(2026, 6, 1), fuentes=["ficha_cumplimentada"]))
    con_bloqueo = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert con_bloqueo.calculo is None
    assert not any(PRECONDICION_DELEGADA in a for a in con_bloqueo.avisos)


def test_r_cal_03_fallida_retira_el_ahorro_visto_desde_la_evaluacion(spec_ind240, caso_a):
    """H4 (docs/05 §4.5): la retirada del control fisico FIS-02, cerrada en la evaluacion, no solo en N3."""
    con(caso_a, unidad_dato("P_prom", Decimal("200"), tipo_evidencia="derivado"), SERIE)
    evaluacion = evaluar_actuacion(caso_a, spec_ind240, fecha_evaluacion=FECHA)
    assert evaluacion.resultado("R-CAL-03").resultado is Resultado.FALLA
    assert evaluacion.veredicto == VEREDICTO_BLOQUEADO
    assert evaluacion.calculo is not None, "el calculo se hace: el control fisico es posterior"
    assert evaluacion.calculo.total is None
    assert evaluacion.calculo.total_cae is None
    assert evaluacion.a_dict()["resultados"]
