"""Tests del modelo canonico (N7, S3.1 pieza A): `engine/modelo/`.

Lo que se protege aqui, en este orden:

1. Los **7 casos** del banco de pruebas se convierten con `desde_motor` y **validan** contra su JSON Schema
   (criterio de aceptacion de `docs/06` para S3.1). Se procesan sin OCR, como en `tests/test_motor.py`.
2. `a_dict` produce JSON que `json.dumps` acepta **sin** `default=`: `Decimal` y `date` salen como cadena.
3. El validador **señala la ruta del campo** que falla, en las seis formas que el esquema puede romperse.
4. Lo que el modelo conserva (caso C: las dos lecturas de PM en conflicto) y lo que no inventa (`cabecera`
   vacia, `ccaa` nula, `subsanaciones` vacia, ninguna parte sin datos).
5. Higiene del fuente y determinismo: sin `eval`, sin `float`, sin dependencias nuevas, sin red, y dos
   conversiones de la misma actuacion dan exactamente el mismo `dict`.

El ground truth se lee de `expedientes/_resultados_esperados/` (`docs/05` §3); `engine/` no lo conoce.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from copy import deepcopy
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from engine.modelo import (
    MODELO_VERSION,
    ROLES_PARTE,
    TIPOS_TENANT,
    ActuacionCanonica,
    DocumentoRef,
    ErrorModelo,
    Expediente,
    GrupoActuaciones,
    Parte,
    Tenant,
    Unidad,
    Verificador,
    a_dict,
    desde_motor,
    validar,
    validar_documento,
)
from engine.modelo.conversion import (
    ESTADO_CICLO_TRAS_EVALUAR,
    VARIABLES_POR_ROL,
    metodo_lectura,
)
from engine.modelo.serializacion import decimal_a_texto
from engine.modelo.validacion import CARPETA_ESQUEMAS, ESQUEMAS, esquema
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_GROUND_TRUTH = CARPETA_CASOS / "_resultados_esperados"
CARPETA_MODELO = RAIZ / "engine" / "modelo"
HUECOS = RAIZ / "docs" / "HUECOS.md"
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
CASO_A = "EXP001-A_completo"
CASO_C = "EXP001-C_contradictorio"

#: El ahorro exacto del caso A (`CLAUDE.md` §5). En el modelo canonico viaja como cadena, nunca como numero.
AETOTAL_A = "305829.6"

VERIFICADOR = Verificador(
    id="OV-0001",
    razon_social="Organismo de Verificacion Sintetico, S.A.",
    nif="A00000000",
    acreditacion_enac_ref="ENAC 000/C-SIN",
)
TENANT = Tenant(
    id="TEN-0001", tipo="delegado", razon_social="Sujeto Delegado Sintetico, S.L.", nif="B00000000"
)


def ground_truth(caso: str) -> dict:
    return json.loads((CARPETA_GROUND_TRUTH / f"{caso}.json").read_text(encoding="utf-8"))


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


@cache
def procesado(caso: str):
    """Un caso procesado una sola vez por sesion (la cadena completa tarda entre 1 y 4 s por caso)."""
    return procesar_actuacion(
        CARPETA_CASOS / caso,
        fecha_evaluacion=FECHA,
        ocr=False,
        registro=_registro(),
    )


@cache
def canonica(caso: str) -> ActuacionCanonica:
    return desde_motor(procesado(caso))


@cache
def documento(caso: str) -> dict:
    return a_dict(canonica(caso))


def copia_a() -> dict:
    """Copia mutable del caso A ya serializado: el material de los tests de error del validador."""
    return deepcopy(documento(CASO_A))


def fuentes_modelo() -> dict[str, str]:
    return {ruta.name: ruta.read_text(encoding="utf-8") for ruta in sorted(CARPETA_MODELO.glob("*.py"))}


# ---------------------------------------------------------------------------
# 1. Los 7 casos: conversion y validacion contra el esquema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_cada_caso_produce_una_actuacion_canonica_valida(caso):
    """Criterio de aceptacion de `docs/06` para S3.1: los 7 casos validan contra `actuacion-1.0.json`."""
    entidad = canonica(caso)
    assert isinstance(entidad, ActuacionCanonica)
    validar(entidad)  # ErrorModelo con la ruta del campo si algo no encaja


@pytest.mark.parametrize("caso", CASOS)
def test_la_identidad_y_la_ficha_son_las_del_motor(caso):
    actuacion = procesado(caso)
    entidad = canonica(caso)
    assert entidad.id == actuacion.id == caso
    assert entidad.codigo_identificativo_propio == actuacion.codigo_identificativo_propio
    assert entidad.ficha == {
        "codigo": actuacion.spec.codigo,
        "version_ficha": actuacion.spec.version_ficha,
        "version_spec": actuacion.spec.version_spec,
        "hash_spec": actuacion.spec.hash_spec,
    }
    # `hash_reglas` no esta en `ficha` (el esquema no lo admite): viaja en `evaluacion`, con las reglas.
    assert "hash_reglas" not in entidad.ficha
    assert entidad.evaluacion["hash_reglas"] == actuacion.spec.hash_reglas


@pytest.mark.parametrize("caso", CASOS)
def test_el_veredicto_del_modelo_es_el_del_ground_truth(caso):
    assert canonica(caso).evaluacion["veredicto"] == ground_truth(caso)["veredicto_esperado"]


@pytest.mark.parametrize("caso", CASOS)
def test_modelo_version_presente_e_igual_a_la_del_paquete(caso):
    entidad = canonica(caso)
    assert entidad.modelo_version == MODELO_VERSION == "1.0"
    assert ESQUEMAS["actuacion"] == f"actuacion-{MODELO_VERSION}.json"


@pytest.mark.parametrize("caso", CASOS)
def test_lo_que_no_existe_todavia_sale_vacio_y_no_inventado(caso):
    """`cabecera` (S3.2), `subsanaciones` (S3.5), `ccaa` (API-07) y el estado de plataforma."""
    entidad = canonica(caso)
    assert entidad.cabecera == {}
    assert entidad.subsanaciones == ()
    assert entidad.atributos_agrupacion["ccaa"] is None
    assert entidad.ciclo == {
        "estado_ciclo": ESTADO_CICLO_TRAS_EVALUAR,
        "estado_plataforma": None,
        "grupo_id": None,
        "expediente_id": None,
    }
    assert entidad.ciclo["estado_ciclo"] == "EVALUADA"


@pytest.mark.parametrize("caso", CASOS)
def test_atributos_de_agrupacion_salen_de_la_spec_y_del_dato_consolidado(caso):
    actuacion = procesado(caso)
    atributos = canonica(caso).atributos_agrupacion
    assert atributos["sector"] == actuacion.spec.datos["ficha"]["sector"]
    fin = actuacion.consolidada.variables["fecha_fin_actuacion"].valor_consumido
    assert atributos["anio_finalizacion"] == (fin.year if isinstance(fin, date) else None)
    assert atributos["verificador_id"] is None  # no se ha pasado ningun verificador


@pytest.mark.parametrize("caso", CASOS)
def test_documentos_van_por_huella_y_con_su_metodo_de_lectura(caso):
    actuacion = procesado(caso)
    entidad = canonica(caso)
    assert len(entidad.documentos) == len(actuacion.documentos)
    for ref, doc in zip(entidad.documentos, actuacion.documentos, strict=True):
        assert isinstance(ref, DocumentoRef)
        assert ref.doc_id == doc.doc_id
        assert ref.sha256 == doc.sha256
        assert ref.origen == doc.origen
        assert ref.paginas == len(doc.paginas)
        assert ref.metodo_lectura
        assert ref.confianza_tipo is None or isinstance(ref.confianza_tipo, Decimal)
    # Nada se vincula por nombre de fichero (regla de oro de ingesta): el nombre no viaja en el modelo.
    nombres = {doc.nombre for doc in actuacion.documentos}
    serializado = json.dumps(documento(caso)["documentos"], ensure_ascii=False)
    assert not any(nombre in serializado for nombre in nombres)


@pytest.mark.parametrize("caso", CASOS)
def test_las_unidades_llevan_las_tres_capas_de_cada_dato(caso):
    actuacion = procesado(caso)
    entidad = canonica(caso)
    assert [u.clave for u in entidad.unidades] == sorted(actuacion.consolidada.unidades)
    assert len(entidad.unidades) == actuacion.consolidada.n_unidades
    for unidad in entidad.unidades:
        assert isinstance(unidad, Unidad)
        originales = actuacion.consolidada.unidades[unidad.clave]
        assert set(unidad.variables) == set(originales)
        for nombre, valores in unidad.variables.items():
            assert valores == originales[nombre].a_dict()  # no se reserializa: es el mismo dict
            assert valores["evidencias"], f"{nombre} sin evidencia: sin cita no entra"
            for evidencia in valores["evidencias"]:  # capa 1
                assert evidencia["doc_id"] and evidencia["texto_literal"] and evidencia["metodo"]
                assert evidencia["pagina"] >= 0
            assert "valor_normalizado" in valores  # capa 2
            assert "valor_consumido" in valores  # capa 3


@pytest.mark.parametrize("caso", CASOS)
def test_variables_de_actuacion_son_los_datos_consolidados(caso):
    actuacion = procesado(caso)
    entidad = canonica(caso)
    assert set(entidad.variables_actuacion) == set(actuacion.consolidada.variables)
    for nombre, valores in entidad.variables_actuacion.items():
        assert valores == actuacion.consolidada.variables[nombre].a_dict()


@pytest.mark.parametrize("caso", CASOS)
def test_evaluacion_y_calculo_reutilizan_la_serializacion_del_nucleo(caso):
    from engine.calculo import a_dict as calculo_a_dict

    actuacion = procesado(caso)
    entidad = canonica(caso)
    esperado = actuacion.evaluacion.a_dict()
    assert entidad.evaluacion["reglas"] == esperado["resultados"]
    assert "resultados" not in entidad.evaluacion
    assert entidad.evaluacion["evaluado_en"] == actuacion.fecha_evaluacion
    assert entidad.observaciones == tuple(actuacion.avisos)
    assert entidad.interpretaciones_aplicadas == tuple(actuacion.evaluacion.interpretaciones_aplicadas)
    if actuacion.calculo is None:
        assert entidad.calculo is None
    else:
        assert entidad.calculo == calculo_a_dict(actuacion.calculo)


@pytest.mark.parametrize("caso", CASOS)
def test_partes_solo_las_que_tienen_datos(caso):
    actuacion = procesado(caso)
    entidad = canonica(caso)
    roles = [parte.rol for parte in entidad.partes]
    assert roles == sorted(roles, key=ROLES_PARTE.index)  # orden estable
    assert all(parte.nif is not None or parte.razon_social is not None for parte in entidad.partes)
    assert "verificador" not in roles  # no se ha pasado ninguno: no se inventa
    # El instalador sale del emisor de la factura y la extraccion no lo aporta hoy: no hay parte instalador.
    assert VARIABLES_POR_ROL["instalador"][0] not in actuacion.consolidada.variables
    assert "instalador" not in roles
    titular = actuacion.consolidada.variables["titular_nif"].valor_consumido
    assert [parte.nif for parte in entidad.partes] == [titular, titular]
    assert roles == ["propietario_inicial", "solicitante"]


# ---------------------------------------------------------------------------
# 2. Serializacion: JSON sin `default=`, Decimal y date como cadena
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_a_dict_es_serializable_sin_default(caso):
    texto = json.dumps(documento(caso), ensure_ascii=False, sort_keys=True)
    assert json.loads(texto) == documento(caso)


@pytest.mark.parametrize("caso", CASOS)
def test_ni_un_float_ni_un_decimal_ni_una_fecha_sobreviven_en_el_json(caso):
    def recorrer(valor, ruta="(raiz)"):
        if isinstance(valor, dict):
            for clave, hijo in valor.items():
                recorrer(hijo, f"{ruta}.{clave}")
        elif isinstance(valor, list):
            for i, hijo in enumerate(valor):
                recorrer(hijo, f"{ruta}[{i}]")
        else:
            assert not isinstance(valor, float), f"{ruta}: coma flotante en el modelo canonico"
            assert not isinstance(valor, Decimal | date), f"{ruta}: {type(valor).__name__} sin serializar"

    recorrer(documento(caso))


@pytest.mark.parametrize("caso", CASOS)
def test_las_fechas_salen_como_cadena_iso(caso):
    doc = documento(caso)
    assert doc["creado_en"] == FECHA.isoformat()
    assert doc["evaluacion"]["evaluado_en"] == FECHA.isoformat()


def test_el_ahorro_del_caso_a_viaja_como_cadena_exacta():
    """Caso A = 305.829,6 kWh/año (`CLAUDE.md` §5), sin redondeo y sin coma flotante."""
    doc = documento(CASO_A)
    assert doc["calculo"]["total"] == AETOTAL_A
    assert isinstance(doc["calculo"]["total"], str)
    assert Decimal(doc["calculo"]["total"]) == Decimal(AETOTAL_A)
    assert doc["calculo"]["total"] == ground_truth(CASO_A)["aetotal_esperado"]["exacto"]
    assert doc["calculo"]["total_cae"] == ground_truth(CASO_A)["aetotal_esperado"]["cae"]


def test_decimal_a_texto_no_pierde_precision_ni_mete_exponente():
    assert decimal_a_texto(Decimal("305829.6000000000000000")) == AETOTAL_A
    assert decimal_a_texto(Decimal("0")) == "0"
    assert decimal_a_texto(Decimal("1E+3")) == "1000"
    assert decimal_a_texto(Decimal("NaN")) == "NaN"  # no se arregla: lo rechaza el validador


def test_un_float_en_una_entidad_es_un_defecto_con_su_ruta():
    unidad = Unidad(clave="MTR-1", variables={"PM": {"valor_consumido": 110.0}})
    with pytest.raises(ErrorModelo) as error:
        a_dict(unidad)
    assert "variables.PM.valor_consumido" in str(error.value)
    assert "Decimal" in str(error.value)


def test_a_dict_rechaza_lo_que_no_es_una_entidad():
    with pytest.raises(ErrorModelo):
        a_dict({"id": "X"})


# ---------------------------------------------------------------------------
# 3. El validador señala la ruta del campo que falla
# ---------------------------------------------------------------------------


def test_requerido_ausente_se_señala_con_su_ruta():
    doc = copia_a()
    del doc["ficha"]["hash_spec"]
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "ficha" in str(error.value)
    assert "hash_spec" in str(error.value)


def test_requerido_ausente_en_la_raiz_se_señala_como_raiz():
    doc = copia_a()
    del doc["ciclo"]
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "(raiz)" in str(error.value)
    assert "ciclo" in str(error.value)


def test_tipo_incorrecto_se_señala_con_su_ruta():
    doc = copia_a()
    doc["ciclo"]["grupo_id"] = 7
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "ciclo.grupo_id" in str(error.value)
    assert "integer" in str(error.value)


def test_tipo_incorrecto_dentro_de_una_lista_lleva_el_indice():
    doc = copia_a()
    doc["documentos"][0]["bytes"] = "4146"
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "documentos[0].bytes" in str(error.value)


def test_enumerado_invalido_se_señala_con_su_ruta():
    doc = copia_a()
    doc["evaluacion"]["veredicto"] = "CASI_PREVALIDADO"
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "evaluacion.veredicto" in str(error.value)


def test_estado_de_ciclo_fuera_del_enumerado_se_señala():
    doc = copia_a()
    doc["ciclo"]["estado_ciclo"] = "COMPLETA"  # es un estado de plataforma, no de ciclo
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "ciclo.estado_ciclo" in str(error.value)


def test_campo_no_permitido_se_señala_con_su_ruta():
    doc = copia_a()
    doc["campo_inventado"] = "no"
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "(raiz)" in str(error.value)
    assert "campo_inventado" in str(error.value)


def test_campo_no_permitido_en_un_subobjeto_se_señala_con_su_ruta():
    doc = copia_a()
    doc["atributos_agrupacion"]["provincia"] = "Zaragoza"
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "atributos_agrupacion" in str(error.value)
    assert "provincia" in str(error.value)


@pytest.mark.parametrize("no_finito", ["NaN", "Infinity", "-Infinity"])
def test_decimal_no_finito_se_rechaza_con_su_ruta(no_finito):
    doc = copia_a()
    doc["calculo"]["total"] = no_finito
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "calculo.total" in str(error.value)
    assert "finito" in str(error.value)


def test_decimal_que_no_es_numero_se_rechaza_con_su_ruta():
    doc = copia_a()
    doc["documentos"][0]["confianza_tipo"] = "casi seguro"
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "documentos[0].confianza_tipo" in str(error.value)


@pytest.mark.parametrize("mala", ["02/03/2026", "2026-3-2", "2026-13-01", "ayer"])
def test_fecha_mal_formada_se_rechaza_con_su_ruta(mala):
    doc = copia_a()
    doc["creado_en"] = mala
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "creado_en" in str(error.value)


def test_una_evidencia_sin_cita_no_entra():
    """`minItems: 1`: un dato sin ninguna evidencia no es un `DatoConsolidado` valido (regla de oro 2)."""
    doc = copia_a()
    doc["unidades"][0]["variables"]["PM"]["evidencias"] = []
    with pytest.raises(ErrorModelo) as error:
        validar_documento(doc)
    assert "unidades[0].variables.PM.evidencias" in str(error.value)


def test_validar_exige_una_entidad_y_dice_como_validar_un_dict():
    with pytest.raises(ErrorModelo) as error:
        validar(copia_a())
    assert "validar_documento" in str(error.value)
    with pytest.raises(ErrorModelo):
        validar("EXP001-A_completo")


def test_una_entidad_sin_esquema_propio_lo_dice():
    with pytest.raises(ErrorModelo) as error:
        validar(Parte(rol="solicitante", nif="B99001018"))
    assert "esquema propio" in str(error.value)


def test_un_esquema_desconocido_es_un_error_de_carga():
    with pytest.raises(ErrorModelo):
        esquema("actuacion-2.0")


# ---------------------------------------------------------------------------
# 4. Lo que el modelo conserva: caso C (conflicto) y caso E/F (varias unidades)
# ---------------------------------------------------------------------------


def test_caso_c_conserva_las_dos_lecturas_de_pm_y_no_elige():
    """Regla de oro 6: ante conflicto entre fuentes fiables, `valor_consumido` es nulo y quedan las dos."""
    doc = documento(CASO_C)
    pm = doc["unidades"][0]["variables"]["PM"]
    assert pm["conflicto"] is True
    assert pm["valor_consumido"] is None
    assert pm["valor_normalizado"] is None
    valores = {evidencia["valor"] for evidencia in pm["evidencias"]}
    assert {"110", "90"} <= valores, "las dos lecturas en conflicto tienen que seguir ahi"
    assert len(pm["evidencias"]) >= 2
    # Cada una con su cita completa: documento, pagina, texto literal, metodo, confianza.
    for evidencia in pm["evidencias"]:
        assert evidencia["doc_id"] and evidencia["tipo_doc"]
        assert evidencia["texto_literal"].strip()
        assert Decimal(evidencia["confianza"]).is_finite()
    assert set(pm["valores_por_fuente"].values()) >= {"110", "90"}
    assert doc["calculo"] is None or doc["calculo"]["total"] is None
    assert doc["evaluacion"]["veredicto"] == "BLOQUEADO"


@pytest.mark.parametrize("caso", ("EXP001-E_dos_motores", "EXP001-F_tres_motores"))
def test_varias_unidades_se_conservan_todas_y_ordenadas(caso):
    entidad = canonica(caso)
    claves = [unidad.clave for unidad in entidad.unidades]
    assert len(claves) == ground_truth(caso)["n_motores"]
    assert claves == sorted(claves)
    assert len(set(claves)) == len(claves)
    for unidad in entidad.unidades:
        assert unidad.num_serie_variador is None or unidad.num_serie_variador.strip()


# ---------------------------------------------------------------------------
# 5. `desde_motor`: tenant, verificador y contrato de entrada
# ---------------------------------------------------------------------------


def test_con_verificador_aparece_la_parte_y_el_atributo_de_agrupacion():
    entidad = desde_motor(procesado(CASO_A), verificador=VERIFICADOR)
    validar(entidad)
    assert entidad.atributos_agrupacion["verificador_id"] == VERIFICADOR.id
    verificadores = [parte for parte in entidad.partes if parte.rol == "verificador"]
    assert len(verificadores) == 1
    assert verificadores[0].nif == VERIFICADOR.nif
    assert entidad.partes[-1].rol == "verificador"


def test_el_tenant_se_acepta_pero_no_entra_en_la_actuacion():
    """El tenant contiene la actuacion (`docs/03` §5.2); `actuacion-1.0.json` no tiene campo para el."""
    entidad = desde_motor(procesado(CASO_A), tenant=TENANT)
    validar(entidad)
    assert TENANT.nif not in json.dumps(a_dict(entidad), ensure_ascii=False)
    assert TENANT.tipo in TIPOS_TENANT


def test_un_tenant_o_un_verificador_del_tipo_equivocado_fallan_aqui():
    with pytest.raises(ErrorModelo):
        desde_motor(procesado(CASO_A), tenant="TEN-0001")
    with pytest.raises(ErrorModelo):
        desde_motor(procesado(CASO_A), verificador={"id": "OV-0001"})


def test_desde_motor_rechaza_algo_que_no_es_la_actuacion_del_motor():
    with pytest.raises(ErrorModelo):
        desde_motor(object())


def test_metodo_lectura_declara_todas_las_formas_de_leer_un_documento():
    class _Pagina:
        def __init__(self, metodo):
            self.metodo = metodo

    class _Doc:
        doc_id = "abc"
        formato = "xlsx"

        def __init__(self, paginas):
            self.paginas = paginas

    assert metodo_lectura(_Doc([_Pagina("pdf_nativo")])) == "pdf_nativo"
    assert metodo_lectura(_Doc([_Pagina("pdf_nativo"), _Pagina("ocr")])) == "ocr+pdf_nativo"
    assert metodo_lectura(_Doc([_Pagina("ocr"), _Pagina("pdf_nativo")])) == "ocr+pdf_nativo"  # estable
    assert metodo_lectura(_Doc([])) == "xlsx"  # no paginado: lo dice su formato


# ---------------------------------------------------------------------------
# 6. Grupo y expediente: estructura, sin reglas de composicion (son S4)
# ---------------------------------------------------------------------------


def test_un_grupo_de_actuaciones_se_construye_y_valida():
    grupo = GrupoActuaciones(
        id="GRP-0001",
        tenant_id=TENANT.id,
        verificador_id=VERIFICADOR.id,
        actuaciones=tuple(CASOS[:2]),
    )
    validar(grupo)
    doc = a_dict(grupo)
    assert doc["actuaciones"] == list(CASOS[:2])
    assert doc["estado_plataforma"] is None  # lo fija la plataforma; aqui solo se refleja


def test_un_grupo_vacio_es_estructuralmente_valido_porque_la_composicion_es_s4():
    validar(GrupoActuaciones(id="GRP-0002", tenant_id=TENANT.id))


def test_un_expediente_se_construye_y_valida():
    expediente = Expediente(
        id="EXPED-0001",
        tenant_id=TENANT.id,
        ccaa=None,  # TODO(API-07): ver docs/HUECOS.md
        anio=2026,
        sector=procesado(CASO_A).spec.datos["ficha"]["sector"],
        verificador_id=VERIFICADOR.id,
        actuaciones=(CASO_A,),
        grupo_id="GRP-0001",
    )
    validar(expediente)
    doc = a_dict(expediente)
    assert doc["ccaa"] is None
    assert doc["estado_expediente"] is None  # nombre provisional NO OFICIAL, TODO(API-03)
    assert doc["requerimientos"] == []


def test_un_expediente_mal_formado_se_señala_con_su_ruta():
    with pytest.raises(ErrorModelo) as error:
        validar(Expediente(id="EXPED-0002", tenant_id=TENANT.id, anio=1999))
    assert "anio" in str(error.value)


def test_el_expediente_y_el_grupo_no_comparten_esquema_con_la_actuacion():
    assert len({ESQUEMAS[n] for n in ("actuacion", "grupo", "expediente")}) == 3
    with pytest.raises(ErrorModelo):
        validar_documento(copia_a(), "expediente")


# ---------------------------------------------------------------------------
# 7. Higiene del fuente y determinismo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prohibido", ["eval(", "exec(", "compile(", "float(", "__import__("])
def test_el_modelo_no_ejecuta_texto_ni_usa_coma_flotante(prohibido):
    for nombre, fuente in fuentes_modelo().items():
        assert prohibido not in fuente, f"engine/modelo/{nombre} usa {prohibido}"


@pytest.mark.parametrize("prohibida", ["jsonschema", "pydantic", "requests", "urllib", "httpx"])
def test_el_modelo_no_gana_dependencias(prohibida):
    for nombre, fuente in fuentes_modelo().items():
        assert f"import {prohibida}" not in fuente, f"engine/modelo/{nombre} importa {prohibida}"


@pytest.mark.parametrize("paquete", ["agentes", "salida", "generator", "tests"])
def test_el_modelo_no_importa_hacia_fuera(paquete):
    for nombre, fuente in fuentes_modelo().items():
        assert f"import {paquete}" not in fuente, f"engine/modelo/{nombre} importa {paquete}"
        assert f"from {paquete}" not in fuente


def test_ninguna_ficha_se_nombra_en_el_modelo():
    """Regla de oro 4: lo especifico de la ficha vive en su YAML, nunca en `engine/`."""
    for nombre, fuente in fuentes_modelo().items():
        codigo = fuente.split('"""', 2)[-1] if fuente.startswith('"""') else fuente
        assert "IND240" not in codigo, f"engine/modelo/{nombre} nombra una ficha"


def test_importar_el_modelo_no_arrastra_el_motor():
    """La dependencia va motor → modelo, nunca al reves (`engine.motor` solo se importa para tipar)."""
    codigo = "import sys, engine.modelo; print('engine.motor' in sys.modules)"
    salida = subprocess.run(
        [sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, check=True
    )
    assert salida.stdout.strip() == "False", salida.stdout


def test_los_esquemas_se_leen_del_paquete_y_no_de_la_red():
    assert CARPETA_ESQUEMAS.parent == CARPETA_MODELO
    for nombre, fichero in ESQUEMAS.items():
        ruta = CARPETA_ESQUEMAS / fichero
        assert ruta.is_file()
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        assert not str(datos["$id"]).startswith("http"), f"{nombre} referencia un esquema remoto"
        assert esquema(nombre) == datos
    for fuente in fuentes_modelo().values():
        assert "http://" not in fuente and "https://" not in fuente


def test_todo_hueco_citado_en_el_modelo_existe_en_docs_huecos():
    """Regla de oro 10: un `TODO(API-xx)` en el codigo tiene que tener su fila en `docs/HUECOS.md`."""
    texto_huecos = HUECOS.read_text(encoding="utf-8")
    citados = set()
    for ruta in sorted(CARPETA_MODELO.rglob("*")):
        if ruta.suffix not in (".py", ".json"):
            continue
        citados |= set(re.findall(r"TODO\(API-(\d+)\)", ruta.read_text(encoding="utf-8")))
    assert citados, "el modelo deberia citar al menos API-07"
    for hueco in sorted(citados):
        assert f"| API-{hueco} |" in texto_huecos, f"API-{hueco} no esta enumerado en docs/HUECOS.md"


@pytest.mark.parametrize("caso", CASOS)
def test_la_conversion_es_determinista(caso):
    """Dos conversiones de la misma actuacion dan el mismo `dict` y el mismo JSON, clave a clave."""
    primera = a_dict(desde_motor(procesado(caso)))
    segunda = a_dict(desde_motor(procesado(caso)))
    assert primera == segunda
    assert json.dumps(primera, ensure_ascii=False) == json.dumps(segunda, ensure_ascii=False)


def test_las_claves_de_los_diccionarios_salen_ordenadas():
    doc = documento(CASO_A)
    assert list(doc["atributos_agrupacion"]) == sorted(doc["atributos_agrupacion"])
    assert list(doc["variables_actuacion"]) == sorted(doc["variables_actuacion"])
    assert list(doc["unidades"][0]["variables"]) == sorted(doc["unidades"][0]["variables"])
    # Los campos de una entidad salen en su orden de declaracion, no alfabetico.
    assert list(doc)[:4] == ["id", "codigo_identificativo_propio", "modelo_version", "creado_en"]
