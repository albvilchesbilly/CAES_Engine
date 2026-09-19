"""Tests del mapeo declarativo modelo canonico -> destino (S3.4, C5 de `ADR-009` §3): `salida/mapeo.py`.

Lo que se protege aqui, en este orden:

1. **El mapeo real de IND240 carga** y es lo que dice ser: identidad, cabecera vacia a proposito, campos de
   actuacion y de unidad, carpetas por tipo documental y nombres del arbol.
2. **Falla al cargar, no al entregar** (criterio de `engine/spec_registry.py`): clave desconocida, campo sin
   origen ni hueco, hueco con forma libre, hueco obligatorio, clave repetida, identidad que no cuadra con el
   nombre del fichero, destino desconocido y fichero que no existe.
3. **`resolver` solo selecciona**: ruta punteada, claves con punto, indices de lista, y `None` -- nunca una
   excepcion -- cuando la ruta no lleva a ninguna parte.
4. **`aplicar` no calcula, no convierte y no redondea**: los `Decimal` salen como cadena tal y como los dio
   el modelo canonico, y un obligatorio sin valor es una **carencia**, no un error.
5. **Higiene del fuente**: sin `eval`, sin coma flotante y sin conocer ninguna ficha.
"""

from __future__ import annotations

import re
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest
import yaml

from engine.modelo import a_dict, desde_motor
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry
from salida.mapeo import (
    CARPETA_MAPEOS,
    Campo,
    Mapeo,
    RenderManifiesto,
    aplicar,
    cargar,
    cargar_manifiesto,
    resolver,
)
from salida.puerto import ErrorSalida

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
FUENTE_MAPEO = RAIZ / "salida" / "mapeo.py"
FECHA = __import__("datetime").date(2026, 9, 18)

CASO_A = "EXP001-A_completo"
CASO_D = "EXP001-D_fuera_ambito"
CASO_E = "EXP001-E_dos_motores"


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


@cache
def canonico(caso: str) -> dict:
    """El modelo canonico **ya serializado** del caso: es contra esto contra lo que resuelve un mapeo."""
    actuacion = procesar_actuacion(
        CARPETA_CASOS / caso, fecha_evaluacion=FECHA, ocr=False, registro=_registro()
    )
    return a_dict(desde_motor(actuacion))


@pytest.fixture(scope="module")
def mapeo() -> Mapeo:
    return cargar("IND240", "handoff")


def escribir(carpeta: Path, nombre: str, contenido: dict) -> Path:
    """Un mapeo de prueba en `tmp_path`: los tests de carga nunca tocan `mapping/`."""
    ruta = carpeta / nombre
    ruta.write_text(yaml.safe_dump(contenido, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ruta


def mapeo_minimo(**cambios: object) -> dict:
    base = {
        "mapeo": {"id": "XXX999.handoff", "ficha": "XXX999", "destino": "handoff", "version": "1.0"},
        "cabecera": [],
        "detalle_actuacion": [
            {"clave": "veredicto", "etiqueta": "Veredicto", "origen": "evaluacion.veredicto"}
        ],
        "detalle_unidad": [],
        "documentos": {"carpeta": "documentos", "sin_tipo": "otros", "por_tipo": {"factura": "facturas"}},
        "ficheros": {"leeme": "00_LEEME.md"},
    }
    base.update(cambios)
    return base


# ---------------------------------------------------------------------------
# 1. El mapeo real de IND240
# ---------------------------------------------------------------------------


def test_el_mapeo_de_ind240_carga_y_es_lo_que_dice_ser(mapeo: Mapeo) -> None:
    assert (mapeo.id, mapeo.ficha, mapeo.destino) == ("IND240.handoff", "IND240", "handoff")
    assert mapeo.detalle_actuacion and mapeo.detalle_unidad
    assert all(isinstance(campo, Campo) for campo in mapeo.detalle_actuacion)


def test_la_cabecera_va_vacia_a_proposito_porque_es_s32(mapeo: Mapeo) -> None:
    """La cabecera comun la define `cabecera_v1.yaml` (S3.2, aprobacion de Billy): aqui no se inventa."""
    assert mapeo.cabecera == ()


def test_el_mapeo_declara_carpetas_por_tipo_y_un_cajon_para_lo_no_clasificado(mapeo: Mapeo) -> None:
    assert mapeo.carpeta_de_tipo("factura") != mapeo.carpeta_de_tipo(None)
    assert mapeo.carpeta_de_tipo("un_tipo_que_no_existe") == mapeo.carpeta_de_tipo(None)


def test_el_mapeo_declara_los_nombres_del_arbol_del_handoff(mapeo: Mapeo) -> None:
    for clave in ("leeme", "payload", "informe_markdown", "informe_json", "log_eventos", "verificacion"):
        assert mapeo.fichero(clave)
    with pytest.raises(ErrorSalida, match="no declara el fichero"):
        mapeo.fichero("inexistente")


def test_ningun_campo_con_hueco_es_obligatorio_en_el_mapeo_real(mapeo: Mapeo) -> None:
    todos = (*mapeo.cabecera, *mapeo.detalle_actuacion, *mapeo.detalle_unidad)
    assert [c.clave for c in todos if c.hueco and c.obligatorio] == []


def test_cada_hueco_del_mapeo_esta_enumerado_en_huecos_md(mapeo: Mapeo) -> None:
    """Regla de oro 10: un hueco del mapeo tiene su fila en `docs/HUECOS.md`, no es texto libre."""
    tabla = (RAIZ / "docs" / "HUECOS.md").read_text(encoding="utf-8")
    todos = (*mapeo.cabecera, *mapeo.detalle_actuacion, *mapeo.detalle_unidad)
    for campo in todos:
        if campo.hueco:
            assert f"| {campo.hueco} |" in tabla, campo.hueco


def test_el_mapeo_del_manifiesto_carga_y_declara_su_fichero() -> None:
    render = cargar_manifiesto("handoff")
    assert isinstance(render, RenderManifiesto)
    assert render.fichero.endswith(".json")
    assert [campo.clave for campo in render.campos].count("hash_manifiesto") == 1


def test_no_hay_mapeo_de_api_todavia() -> None:
    """`mapping/IND240.api.yaml` espera al diccionario (`API-08`); no se escribe adivinando."""
    assert not (CARPETA_MAPEOS / "IND240.api.yaml").exists()
    with pytest.raises(ErrorSalida, match="no existe el mapeo"):
        cargar("IND240", "api")


# ---------------------------------------------------------------------------
# 2. Falla al cargar, no al entregar
# ---------------------------------------------------------------------------


def test_clave_desconocida_en_el_yaml_es_error_de_carga(tmp_path: Path) -> None:
    escribir(tmp_path, "XXX999.handoff.yaml", mapeo_minimo(reglas=[]))
    with pytest.raises(ErrorSalida, match="claves desconocidas"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_clave_desconocida_dentro_de_un_campo_es_error_de_carga(tmp_path: Path) -> None:
    contenido = mapeo_minimo(
        detalle_actuacion=[
            {"clave": "x", "etiqueta": "X", "origen": "evaluacion.veredicto", "formula": "1 + 1"}
        ]
    )
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    with pytest.raises(ErrorSalida, match="claves desconocidas \\['formula'\\]"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_un_campo_con_hueco_no_puede_ser_obligatorio(tmp_path: Path) -> None:
    contenido = mapeo_minimo(
        detalle_actuacion=[
            {
                "clave": "ccaa",
                "etiqueta": "CCAA",
                "origen": "atributos_agrupacion.ccaa",
                "hueco": "API-07",
                "obligatorio": True,
            }
        ]
    )
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    with pytest.raises(ErrorSalida, match="no puede ser obligatorio"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_un_hueco_que_no_tiene_forma_api_nn_es_error_de_carga(tmp_path: Path) -> None:
    contenido = mapeo_minimo(
        detalle_actuacion=[
            {"clave": "x", "etiqueta": "X", "origen": "evaluacion.veredicto", "hueco": "no lo sabemos"}
        ]
    )
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    with pytest.raises(ErrorSalida, match="no tiene la forma API-nn"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_un_campo_sin_origen_y_sin_hueco_es_un_campo_inventado(tmp_path: Path) -> None:
    contenido = mapeo_minimo(detalle_actuacion=[{"clave": "x", "etiqueta": "X"}])
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    with pytest.raises(ErrorSalida, match="campo inventado"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_un_campo_sin_origen_pero_con_hueco_si_carga(tmp_path: Path) -> None:
    contenido = mapeo_minimo(
        detalle_actuacion=[{"clave": "x", "etiqueta": "X", "hueco": "API-08", "nota": "no se sabe pedir"}]
    )
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    cargado = cargar("XXX999", "handoff", carpeta=tmp_path)
    assert cargado.detalle_actuacion[0].origen is None


def test_claves_repetidas_en_un_bloque_son_error_de_carga(tmp_path: Path) -> None:
    campo = {"clave": "x", "etiqueta": "X", "origen": "evaluacion.veredicto"}
    escribir(tmp_path, "XXX999.handoff.yaml", mapeo_minimo(detalle_actuacion=[campo, dict(campo)]))
    with pytest.raises(ErrorSalida, match="claves repetidas"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_la_identidad_tiene_que_coincidir_con_el_nombre_del_fichero(tmp_path: Path) -> None:
    contenido = mapeo_minimo()
    contenido["mapeo"]["ficha"] = "OTRA"
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    with pytest.raises(ErrorSalida, match="tienen que coincidir"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_una_ruta_mal_formada_es_error_de_carga(tmp_path: Path) -> None:
    contenido = mapeo_minimo(detalle_actuacion=[{"clave": "x", "etiqueta": "X", "origen": "a..b"}])
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    with pytest.raises(ErrorSalida, match="paso vacio"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


def test_un_destino_desconocido_no_se_carga(tmp_path: Path) -> None:
    with pytest.raises(ErrorSalida, match="destino desconocido"):
        cargar("XXX999", "ftp", carpeta=tmp_path)


def test_un_yaml_ilegible_es_error_de_carga(tmp_path: Path) -> None:
    (tmp_path / "XXX999.handoff.yaml").write_text("mapeo: [a\n  b", encoding="utf-8")
    with pytest.raises(ErrorSalida, match="YAML ilegible"):
        cargar("XXX999", "handoff", carpeta=tmp_path)


# ---------------------------------------------------------------------------
# 3. resolver: solo selecciona
# ---------------------------------------------------------------------------


def test_resolver_sigue_una_ruta_punteada() -> None:
    assert resolver(canonico(CASO_A), "evaluacion.veredicto") == "PREVALIDADO"
    assert resolver(canonico(CASO_A), "ficha.codigo") == "IND240"


def test_resolver_entiende_las_claves_que_llevan_punto() -> None:
    """El modelo canonico tiene claves como `convenio.ahorro_kwh`; la ruta las nombra sin escapes."""
    valor = resolver(canonico(CASO_A), "variables_actuacion.convenio.ahorro_kwh.valor_consumido")
    assert valor is not None


def test_resolver_indexa_listas_con_enteros() -> None:
    assert resolver(canonico(CASO_A), "partes.0.rol") == "propietario_inicial"
    assert resolver(canonico(CASO_A), "partes.99.rol") is None
    assert resolver(canonico(CASO_A), "partes.primera.rol") is None


def test_una_ruta_que_no_existe_devuelve_none_no_una_excepcion() -> None:
    assert resolver(canonico(CASO_A), "no.existe.esta.ruta") is None
    assert resolver(canonico(CASO_A), "evaluacion.veredicto.mas_alla") is None
    assert resolver(None, "lo.que.sea") is None


def test_una_ruta_vacia_o_mal_formada_si_es_un_error() -> None:
    for ruta in ("", "   ", "a..b"):
        with pytest.raises(ErrorSalida):
            resolver({"a": 1}, ruta)
    with pytest.raises(ErrorSalida):
        resolver({"a": 1}, 7)


# ---------------------------------------------------------------------------
# 4. aplicar: ni calcula, ni convierte, ni redondea
# ---------------------------------------------------------------------------


def test_aplicar_el_caso_a_no_deja_ninguna_carencia(mapeo: Mapeo) -> None:
    payload, carencias = aplicar(mapeo, canonico(CASO_A))
    assert carencias == ()
    assert payload["cabecera"] == {}
    assert payload["detalle"]["actuacion"]["veredicto"] == "PREVALIDADO"
    assert len(payload["detalle"]["unidades"]) == 1


def test_aplicar_no_convierte_ni_redondea_los_decimales(mapeo: Mapeo) -> None:
    """Los `Decimal` salen como cadena tal y como los dio `engine.modelo.a_dict`."""
    payload, _ = aplicar(mapeo, canonico(CASO_A))
    campos = payload["detalle"]["unidades"][0]["campos"]
    assert campos["PM"] == "110"
    assert campos["ahorro_unidad"] == "305829.6"
    assert campos["p"].startswith("0.05045454545454")
    assert len(campos["p"]) > 20  # ni se redondea ni se acorta: es el valor del motor, tal cual
    assert Decimal(campos["perdidas_ref_kw"]) == Decimal("5.55")


def test_cada_unidad_ve_su_propio_calculo(mapeo: Mapeo) -> None:
    """El emparejamiento unidad -> calculo es por identidad, no por posicion.

    La version anterior comparaba `len(set(ahorros))` sobre un `dict`, es decir sobre sus **claves**: era
    cierta pasara lo que pasara y no habria visto un emparejamiento por posicion. Ahora se contrasta cada
    ahorro contra la entrada de `calculo.por_unidad` que lleva el mismo numero de serie de motor.
    """
    canonica = canonico(CASO_E)
    payload, _ = aplicar(mapeo, canonica)
    unidades = payload["detalle"]["unidades"]
    assert len(unidades) == 2

    esperado = {
        str(entrada["num_serie_motor"]): entrada["salida"] for entrada in canonica["calculo"]["por_unidad"]
    }
    assert len(set(esperado.values())) == 2, "los dos motores deben ahorrar distinto o el test no prueba nada"

    obtenido = {u["clave"]: u["campos"]["ahorro_unidad"] for u in unidades}
    assert obtenido == esperado


def test_un_obligatorio_sin_valor_es_una_carencia_y_el_campo_va_a_null(mapeo: Mapeo) -> None:
    """Declarado != demostrado: el caso D no tiene calculo y el tenant tiene derecho a verlo."""
    payload, carencias = aplicar(mapeo, canonico(CASO_D))
    assert "detalle.actuacion.ahorro_total" in carencias
    assert payload["detalle"]["actuacion"]["ahorro_total"] is None


def test_una_carencia_de_unidad_dice_de_que_unidad_es(tmp_path: Path) -> None:
    contenido = mapeo_minimo(
        detalle_unidad=[
            {
                "clave": "inexistente",
                "etiqueta": "Lo que no esta",
                "origen": "variables.no_existe.valor_consumido",
                "obligatorio": True,
            }
        ]
    )
    escribir(tmp_path, "XXX999.handoff.yaml", contenido)
    cargado = cargar("XXX999", "handoff", carpeta=tmp_path)
    _, carencias = aplicar(cargado, canonico(CASO_E))
    assert len(carencias) == 2
    assert all(clave.startswith("detalle.unidades[") for clave in carencias)
    assert len(set(carencias)) == 2  # dos unidades a las que falta lo mismo no se confunden


def test_aplicar_rechaza_lo_que_no_es_un_mapeo_o_una_actuacion(mapeo: Mapeo) -> None:
    with pytest.raises(ErrorSalida, match="espera un Mapeo"):
        aplicar("IND240", canonico(CASO_A))
    with pytest.raises(ErrorSalida, match="ActuacionCanonica"):
        aplicar(mapeo, "una actuacion")


# ---------------------------------------------------------------------------
# 5. Higiene del fuente
# ---------------------------------------------------------------------------


def test_el_mapeo_no_evalua_nada_ni_usa_coma_flotante() -> None:
    fuente = FUENTE_MAPEO.read_text(encoding="utf-8")
    for prohibido in ("eval", "exec", "compile", "float"):
        # `re.compile` vale; `compile(` a secas, no: por eso se exige que no vaya precedido de un punto.
        assert not re.search(rf"(?<![\w.]){prohibido}\(", fuente), prohibido


def test_el_modulo_de_mapeo_no_conoce_ninguna_ficha() -> None:
    """Regla de oro 4: la ficha es configuracion. Ni un `if ficha == ...` ni un identificador de ficha."""
    fuente = FUENTE_MAPEO.read_text(encoding="utf-8")
    codigo = "\n".join(linea for linea in fuente.splitlines() if not linea.strip().startswith("#"))
    assert not re.search(r"\bIND\d{3}\b", codigo)
