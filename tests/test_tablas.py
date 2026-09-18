"""F0.2: tablas de data/ con vigencia, busqueda exacta e interpolacion INT-02 (docs/04 §2.5 y §7).

Incluye los tests de la revision QA de F0.2 (18/09/2026): H1 (esquema generico desde el meta, regla de
oro 4), H4 (sanidad en carga) y H11 (errores no ocultados, `vigente()` tipado, tabla vacia).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest
import yaml

from engine import tablas
from engine.tablas import ErrorTabla, FilaTabla, Tabla, cargar_tabla, cargar_tabla_desde, cargar_tablas

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / "spec" / "IND240_v1.1.yaml"
ID_TABLA = "REG1781_CUADRO6"
CAB6 = "kva_salida,kw_motor,perdidas_ref_kw,cos_phi,verificado"
META6 = {
    "id": "SINTETICA",
    "columnas": ["kva_salida", "kw_motor", "perdidas_ref_kw", "cos_phi", "verificado"],
    "clave": "kw_motor",
    "valor": "perdidas_ref_kw",
    "vigencia": {"desde": "2019-10-25", "hasta": None},
}


@pytest.fixture(scope="module")
def cuadro6() -> Tabla:
    return cargar_tabla(ID_TABLA)


@pytest.fixture(scope="module")
def bloque_tablas_spec() -> dict:
    with SPEC.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["tablas"]


def _tabla(tmp_path: Path, cabecera: str, filas: str, meta: dict, nombre: str = "t") -> Path:
    """Escribe una tabla en tmp_path/data y devuelve la raiz para cargar_tabla."""
    carpeta = tmp_path / "data"
    carpeta.mkdir(exist_ok=True)
    (carpeta / f"{nombre}.csv").write_text(cabecera + "\n" + filas, encoding="utf-8")
    (carpeta / f"{nombre}.meta.yaml").write_text(yaml.safe_dump(meta), encoding="utf-8")
    return tmp_path


def _tabla_sintetica(tmp_path: Path, filas_csv: str, meta: dict | None = None) -> Path:
    """Tabla minima con el esquema del cuadro 6 (id SINTETICA); `meta` sobreescribe campos del meta base."""
    return _tabla(tmp_path, CAB6, filas_csv, {**META6, **(meta or {})}, nombre="sintetica")


# --- valor verificado y busqueda exacta -----------------------------------------------------------


def test_110_kw_da_5_55_exacto(cuadro6: Tabla) -> None:
    resultado = cuadro6.buscar(Decimal("110"))
    assert resultado.exacta is True
    assert resultado.valor == Decimal("5.55")
    assert resultado.interpretacion is None
    assert resultado.filas_adyacentes is None
    assert resultado.fila is not None and resultado.fila.verificado is True
    assert resultado.aviso is None  # fila verificada por Billy: sin aviso de tabla pendiente
    assert cuadro6.avisos_carga == []  # la serie transcrita es no-decreciente: sin avisos de carga


def test_buscar_exacta_devuelve_fila_o_none(cuadro6: Tabla) -> None:
    fila = cuadro6.buscar_exacta(Decimal("110"))
    assert isinstance(fila, FilaTabla)
    assert fila["kw_motor"] == Decimal("110")
    assert fila.clave == Decimal("110")
    assert cuadro6.buscar_exacta(Decimal("100")) is None


def test_todos_los_valores_son_decimal(cuadro6: Tabla) -> None:
    for fila in cuadro6.filas:
        assert isinstance(fila["kw_motor"], Decimal)
        assert isinstance(fila["perdidas_ref_kw"], Decimal)
        assert fila["kva_salida"] is None or isinstance(fila["kva_salida"], Decimal)
        assert fila["cos_phi"] is None or isinstance(fila["cos_phi"], Decimal)
        assert isinstance(fila["verificado"], bool)
        assert set(fila) == set(cuadro6.columnas)


def test_filas_ordenadas_por_clave_sin_duplicados(cuadro6: Tabla) -> None:
    claves = [f.clave for f in cuadro6.filas]
    assert claves == sorted(claves)
    assert len(set(claves)) == len(claves)
    assert cuadro6.clave == "kw_motor"
    assert cuadro6.valor == "perdidas_ref_kw"


# --- INT-02: sin fila exacta -> interpolacion lineal; fuera de rango -> None ------------------------


def test_sin_fila_exacta_interpola_con_int_02(cuadro6: Tabla) -> None:
    assert cuadro6.buscar_exacta(Decimal("100")) is None, "el test supone que 100 kW no tiene fila"
    fila_90 = cuadro6.buscar_exacta(Decimal("90"))
    fila_110 = cuadro6.buscar_exacta(Decimal("110"))
    assert fila_90 is not None and fila_110 is not None
    # Interpolacion lineal calculada a mano con Decimal entre las filas adyacentes 90 y 110 kW.
    p90, p110 = fila_90["perdidas_ref_kw"], fila_110["perdidas_ref_kw"]
    assert isinstance(p90, Decimal) and isinstance(p110, Decimal)
    esperado = p90 + (p110 - p90) * ((Decimal("100") - Decimal("90")) / (Decimal("110") - Decimal("90")))
    resultado = cuadro6.buscar(Decimal("100"))
    assert resultado.exacta is False
    assert resultado.fila is None
    assert resultado.interpretacion == "INT-02"
    assert resultado.valor == esperado
    assert resultado.filas_adyacentes == (fila_90, fila_110)
    assert resultado.aviso and "INT-02" in resultado.aviso


def test_interpolacion_decimal_exacta_en_tabla_sintetica(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n24,20,3.0,,si\n36,30,4.0,,si\n")
    tabla = cargar_tabla("SINTETICA", raiz)
    # (10, 1.0) - (20, 3.0): en 15 -> 2.0; en 12 -> 1.0 + 2.0 * 2/10 = 1.4
    assert tabla.buscar(Decimal("15")).valor == Decimal("2.0")
    assert tabla.buscar(Decimal("12")).valor == Decimal("1.4")
    # (20, 3.0) - (30, 4.0): en 25 -> 3.5
    r = tabla.buscar(Decimal("25"))
    assert r.valor == Decimal("3.5") and r.interpretacion == "INT-02" and not r.exacta
    # sin filas pendientes, el aviso solo lleva INT-02
    assert r.aviso is not None and "pendiente" not in r.aviso


def test_fuera_de_rango_no_extrapola(cuadro6: Tabla) -> None:
    for valor in (Decimal("5000"), Decimal("0.01")):
        resultado = cuadro6.buscar(valor)
        assert resultado.valor is None
        assert resultado.exacta is False
        assert resultado.fila is None
        assert resultado.filas_adyacentes is None
        assert resultado.aviso and "fuera del rango" in resultado.aviso


# --- marca `verificado` (data/README.md) ---------------------------------------------------------


def test_toda_fila_lleva_marca_verificado_y_la_de_110_es_si(cuadro6: Tabla) -> None:
    with cuadro6.fichero.open(encoding="utf-8") as fh:
        lineas = fh.read().splitlines()
    assert lineas[0] == CAB6
    marcas = {linea.split(",")[-1] for linea in lineas[1:]}
    assert marcas <= {"si", "pendiente"}
    fila_110 = cuadro6.buscar_exacta(Decimal("110"))
    assert fila_110 is not None and fila_110.verificado is True
    assert len(lineas) - 1 == len(cuadro6.filas)


def test_fila_pendiente_usada_produce_aviso(cuadro6: Tabla) -> None:
    pendientes = [f for f in cuadro6.filas if not f.verificado]
    if not pendientes:
        pytest.skip("todas las filas ya estan verificadas por Billy")
    assert cuadro6.todas_verificadas is False
    resultado = cuadro6.buscar(pendientes[0].clave)
    assert resultado.exacta is True
    assert resultado.aviso and "pendiente de verificacion humana" in resultado.aviso


def test_marca_verificado_desconocida_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n24,20,3.0,,verificado\n")
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


def test_meta_con_id_distinto_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"id": "OTRA"})
    with pytest.raises(ErrorTabla):
        cargar_tabla_desde(raiz / "data" / "sintetica.csv", id_esperado="SINTETICA")
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


# --- H1 (QA F0.2, regla de oro 4): el esquema lo declara el meta, no engine/ ------------------------


def test_una_tabla_con_otro_esquema_se_carga_desde_su_meta_sin_tocar_engine(tmp_path: Path):
    meta = {
        "id": "SEPR_REF",
        "columnas": ["potencia_kw", "sepr_ref", "verificado"],
        "clave": "potencia_kw",
        "valor": "sepr_ref",
        "vigencia": {"desde": "2020-01-01", "hasta": None},
    }
    raiz = _tabla(tmp_path, "potencia_kw,sepr_ref,verificado", "10,1.0,si\n20,3.0,si\n", meta)
    tabla = cargar_tabla("SEPR_REF", raiz)
    assert tabla.buscar(Decimal("10")).valor == Decimal("1.0")
    assert tabla.buscar(Decimal("15")).valor == Decimal("2.0")  # INT-02 tambien sobre esta tabla


def test_fila_es_un_mapa_columna_valor_segun_el_meta(tmp_path: Path) -> None:
    meta = {
        "id": "FD",
        "columnas": ["zona", "fd", "nota", "verificado"],
        "clave": "zona",
        "valor": "fd",
        "vigencia": {"desde": "2020-01-01", "hasta": None},
    }
    raiz = _tabla(tmp_path, "zona,fd,nota,verificado", "1,0.80,,pendiente\n2,0.95,7,si\n", meta)
    tabla = cargar_tabla("FD", raiz)
    assert tabla.columnas == ["zona", "fd", "nota", "verificado"]
    fila = tabla.filas[0]
    esperado = {"zona": Decimal("1"), "fd": Decimal("0.80"), "nota": None, "verificado": False}
    assert fila.como_dict() == esperado
    assert fila.clave == Decimal("1") and fila.verificado is False
    assert fila.get("no_existe") is None and "nota" in fila
    assert tabla.como_coleccion() == [
        {"zona": Decimal("1"), "fd": Decimal("0.80"), "nota": None, "verificado": False},
        {"zona": Decimal("2"), "fd": Decimal("0.95"), "nota": Decimal("7"), "verificado": True},
    ]
    assert tabla.buscar(Decimal("2")).valor == Decimal("0.95")
    assert tabla.buscar(Decimal("2")).aviso is None


def test_engine_tablas_no_cita_columnas_del_cuadro_6() -> None:
    fuente = Path(tablas.__file__).read_text(encoding="utf-8")
    for nombre in ("kw_motor", "perdidas_ref_kw", "kva_salida", "cos_phi", "REG1781", "COLUMNAS_FILA"):
        assert nombre not in fuente, f"engine/tablas.py cablea el cuadro 6: '{nombre}'"


@pytest.mark.parametrize("campo", ["clave", "valor"])
def test_meta_sin_clave_o_sin_valor_es_error(tmp_path: Path, campo: str) -> None:
    meta = {k: v for k, v in META6.items() if k != campo}
    raiz = _tabla(tmp_path, CAB6, "12,10,1.0,,si\n", meta, nombre="sintetica")
    with pytest.raises(ErrorTabla, match=campo):
        cargar_tabla("SINTETICA", raiz)


@pytest.mark.parametrize("campo", ["clave", "valor"])
def test_clave_o_valor_que_no_es_columna_numerica_es_error(tmp_path: Path, campo: str) -> None:
    for nombre in ("no_existe", "verificado"):
        raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={campo: nombre})
        with pytest.raises(ErrorTabla, match=campo):
            cargar_tabla("SINTETICA", raiz)


def test_clave_y_valor_no_pueden_coincidir(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"valor": "kw_motor"})
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


def test_columnas_del_meta_deben_coincidir_con_la_cabecera_en_conjunto_y_orden(tmp_path: Path) -> None:
    # mismo conjunto, otro orden
    columnas = ["kw_motor", "kva_salida", "perdidas_ref_kw", "cos_phi", "verificado"]
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"columnas": columnas})
    with pytest.raises(ErrorTabla, match="cabecera"):
        cargar_tabla("SINTETICA", raiz)
    # columna de mas en el meta
    columnas = [*META6["columnas"], "extra"]
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"columnas": columnas})
    with pytest.raises(ErrorTabla, match="cabecera"):
        cargar_tabla("SINTETICA", raiz)
    # columna de menos en el meta
    columnas = ["kw_motor", "perdidas_ref_kw", "verificado"]
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"columnas": columnas})
    with pytest.raises(ErrorTabla, match="cabecera"):
        cargar_tabla("SINTETICA", raiz)


def test_meta_sin_columna_verificado_es_error(tmp_path: Path) -> None:
    meta = {**META6, "columnas": ["kva_salida", "kw_motor", "perdidas_ref_kw", "cos_phi"]}
    cabecera = "kva_salida,kw_motor,perdidas_ref_kw,cos_phi"
    raiz = _tabla(tmp_path, cabecera, "12,10,1.0,\n", meta, nombre="sintetica")
    with pytest.raises(ErrorTabla, match="verificado"):
        cargar_tabla("SINTETICA", raiz)


def test_fila_con_numero_de_celdas_distinto_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,si\n")
    with pytest.raises(ErrorTabla, match="celdas"):
        cargar_tabla("SINTETICA", raiz)
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si,extra\n")
    with pytest.raises(ErrorTabla, match="celdas"):
        cargar_tabla("SINTETICA", raiz)


# --- H4 (QA F0.2): sanidad en carga -----------------------------------------------------------------


@pytest.mark.parametrize("celda", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_valor_no_finito_en_el_csv_es_error_de_carga(tmp_path: Path, celda: str):
    raiz = _tabla(tmp_path, CAB6, f"1,{celda},1,,si\n2,2,2,,si\n", {**META6, "id": "T"})
    with pytest.raises(ErrorTabla):
        cargar_tabla("T", raiz)


@pytest.mark.parametrize("columna", ["kva_salida", "perdidas_ref_kw", "cos_phi"])
@pytest.mark.parametrize("celda", ["NaN", "Infinity", "sNaN"])
def test_valor_no_finito_en_cualquier_columna_es_error_de_carga(tmp_path: Path, columna: str, celda: str):
    valores = {"kva_salida": "12", "kw_motor": "10", "perdidas_ref_kw": "1.0", "cos_phi": ""}
    valores[columna] = celda
    fila = ",".join([*(valores[c] for c in ("kva_salida", "kw_motor", "perdidas_ref_kw", "cos_phi")), "si"])
    raiz = _tabla_sintetica(tmp_path, fila + "\n")
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


@pytest.mark.parametrize("celda", ["1e3", "1E3", "1.5e-2", "1_000", "1,5", " 1 0", "0x10", "1."])
def test_notacion_exponencial_y_formatos_no_admitidos_son_error(tmp_path: Path, celda: str) -> None:
    raiz = _tabla_sintetica(tmp_path, f"12,10,{celda},,si\n")
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


def test_buscar_con_nan_es_error_tabla_no_invalidoperation():
    tabla = cargar_tabla("REG1781_CUADRO6")
    with pytest.raises(ErrorTabla):
        tabla.buscar(Decimal("NaN"))


NO_BUSCABLES = [Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity"), "NaN", "abc", 1.5, True]


@pytest.mark.parametrize("valor", NO_BUSCABLES)
def test_buscar_con_valor_no_finito_o_de_otro_tipo_es_error_tabla(cuadro6: Tabla, valor: object) -> None:
    try:
        with pytest.raises(ErrorTabla):
            cuadro6.buscar(valor)  # type: ignore[arg-type]
        with pytest.raises(ErrorTabla):
            cuadro6.buscar_exacta(valor)  # type: ignore[arg-type]
    except InvalidOperation:  # pragma: no cover - documenta el defecto original de QA
        pytest.fail("buscar() dejo escapar InvalidOperation en lugar de ErrorTabla")


def test_restriccion_positivo_se_lee_del_meta(tmp_path: Path) -> None:
    restricciones = {"positivo": ["kw_motor", "perdidas_ref_kw"]}
    for fila in ("12,0,1.0,,si\n", "12,-10,1.0,,si\n", "12,10,0,,si\n", "12,10,-1.0,,si\n"):
        raiz = _tabla_sintetica(tmp_path, fila, meta={"restricciones": restricciones})
        with pytest.raises(ErrorTabla, match="positivo"):
            cargar_tabla("SINTETICA", raiz)
    # una columna fuera de la restriccion puede ser negativa o cero
    raiz = _tabla_sintetica(tmp_path, "-12,10,1.0,-0.5,si\n", meta={"restricciones": restricciones})
    tabla = cargar_tabla("SINTETICA", raiz)
    assert tabla.filas[0]["kva_salida"] == Decimal("-12") and tabla.filas[0]["cos_phi"] == Decimal("-0.5")
    assert tabla.restricciones == restricciones


def test_sin_restriccion_positivo_una_tabla_admite_valores_negativos(tmp_path: Path) -> None:
    meta = {
        "id": "CORR",
        "columnas": ["temperatura", "coeficiente", "verificado"],
        "clave": "temperatura",
        "valor": "coeficiente",
        "vigencia": {"desde": "2020-01-01", "hasta": None},
    }
    raiz = _tabla(tmp_path, "temperatura,coeficiente,verificado", "-10,-0.5,si\n0,0,si\n10,0.5,si\n", meta)
    tabla = cargar_tabla("CORR", raiz)
    assert tabla.restricciones == {}
    assert tabla.buscar(Decimal("-5")).valor == Decimal("-0.25")


def test_restriccion_desconocida_o_sobre_columna_desconocida_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"restricciones": {"entero": ["kw_motor"]}})
    with pytest.raises(ErrorTabla, match="restriccion"):
        cargar_tabla("SINTETICA", raiz)
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"restricciones": {"positivo": ["no_existe"]}})
    with pytest.raises(ErrorTabla, match="no_existe"):
        cargar_tabla("SINTETICA", raiz)
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"restricciones": {"positivo": ["verificado"]}})
    with pytest.raises(ErrorTabla, match="verificado"):
        cargar_tabla("SINTETICA", raiz)


def test_cuadro6_declara_positivo_en_su_meta_y_lo_cumple(cuadro6: Tabla) -> None:
    assert set(cuadro6.restricciones.get("positivo", [])) >= {"kw_motor", "perdidas_ref_kw"}
    for fila in cuadro6.filas:
        for columna in cuadro6.restricciones["positivo"]:
            valor = fila[columna]
            assert valor is None or (isinstance(valor, Decimal) and valor > 0)


def test_clave_duplicada_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n12,10,1.1,,si\n")
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


def test_clave_no_estrictamente_creciente_en_el_csv_es_error(tmp_path: Path) -> None:
    # el motor no reordena una transcripcion: el orden del CSV debe ser el creciente por clave
    raiz = _tabla_sintetica(tmp_path, "24,20,3.0,,si\n12,10,1.0,,si\n")
    with pytest.raises(ErrorTabla, match="creciente"):
        cargar_tabla("SINTETICA", raiz)


@pytest.mark.parametrize("fila", ["12,,1.0,,si\n", "12,10,,,si\n"])
def test_clave_o_valor_vacios_en_una_fila_es_error(tmp_path: Path, fila: str) -> None:
    raiz = _tabla_sintetica(tmp_path, fila)
    with pytest.raises(ErrorTabla, match="vacia"):
        cargar_tabla("SINTETICA", raiz)


def test_valor_decreciente_con_la_clave_es_aviso_de_carga_no_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n24,20,3.0,,si\n36,30,2.0,,si\n48,40,2.0,,si\n")
    tabla = cargar_tabla("SINTETICA", raiz)
    assert len(tabla.avisos_carga) == 1
    assert "20" in tabla.avisos_carga[0] and "30" in tabla.avisos_carga[0]
    assert tabla.buscar(Decimal("25")).valor == Decimal("2.5")  # sigue operativa


def test_tabla_vacia_es_error_de_carga(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "")
    with pytest.raises(ErrorTabla, match="filas"):
        cargar_tabla("SINTETICA", raiz)
    raiz = _tabla_sintetica(tmp_path, "\n\n")
    with pytest.raises(ErrorTabla, match="filas"):
        cargar_tabla("SINTETICA", raiz)


# --- H11 (QA F0.2): errores no ocultados y tipos ----------------------------------------------------


def test_cargar_tabla_muestra_el_error_real_de_un_meta_malformado_del_id_buscado(tmp_path: Path) -> None:
    meta = {k: v for k, v in META6.items() if k != "valor"}
    raiz = _tabla(tmp_path, CAB6, "12,10,1.0,,si\n", meta, nombre="sintetica")
    with pytest.raises(ErrorTabla) as exc:
        cargar_tabla("SINTETICA", raiz)
    assert "valor" in str(exc.value)
    assert "Ninguna tabla" not in str(exc.value)


def test_cargar_tabla_enumera_los_metas_ilegibles_si_no_encuentra_el_id(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n")
    (raiz / "data" / "rota.meta.yaml").write_text("id: [sin cerrar\n", encoding="utf-8")
    (raiz / "data" / "lista.meta.yaml").write_text("- no es un mapa\n", encoding="utf-8")
    with pytest.raises(ErrorTabla) as exc:
        cargar_tabla("NO_EXISTE", raiz)
    assert "rota.meta.yaml" in str(exc.value) and "lista.meta.yaml" in str(exc.value)
    # los metas ajenos ilegibles no impiden cargar la tabla buscada
    assert cargar_tabla("SINTETICA", raiz).id == "SINTETICA"


def test_vigente_con_un_tipo_que_no_es_date_es_error(cuadro6: Tabla) -> None:
    for fecha in ("2020-01-01", 20200101, None, datetime(2020, 1, 1, 12, 0)):
        with pytest.raises(ErrorTabla):
            cuadro6.vigente(fecha)  # type: ignore[arg-type]


def test_vigencia_con_hora_en_el_meta_es_error(tmp_path: Path) -> None:
    vigencia = {"desde": "2020-01-01T00:00:00", "hasta": None}
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"vigencia": vigencia})
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


# --- cargar_tablas con el bloque real de la spec (docs/04 §2.5 garantia 4) ------------------------


def test_cargar_tablas_con_bloque_real_de_la_spec(bloque_tablas_spec: dict) -> None:
    cargadas = cargar_tablas(bloque_tablas_spec)
    assert set(cargadas) == {ID_TABLA}
    tabla = cargadas[ID_TABLA]
    assert tabla.fichero == RAIZ / bloque_tablas_spec[ID_TABLA]["fichero"]
    for columna in bloque_tablas_spec[ID_TABLA]["columnas"]:
        assert columna in tabla.columnas
    assert tabla.buscar(Decimal("110")).valor == Decimal("5.55")


def test_cargar_tablas_columna_inexistente_es_error(bloque_tablas_spec: dict) -> None:
    bloque = {ID_TABLA: dict(bloque_tablas_spec[ID_TABLA])}
    bloque[ID_TABLA]["columnas"] = [*bloque[ID_TABLA]["columnas"], "columna_que_no_existe"]
    with pytest.raises(ErrorTabla):
        cargar_tablas(bloque)


def test_cargar_tablas_fichero_inexistente_es_error(bloque_tablas_spec: dict) -> None:
    bloque = {ID_TABLA: dict(bloque_tablas_spec[ID_TABLA])}
    bloque[ID_TABLA]["fichero"] = "data/no_existe.csv"
    with pytest.raises(ErrorTabla):
        cargar_tablas(bloque)


def test_cargar_tabla_id_desconocido_es_error() -> None:
    with pytest.raises(ErrorTabla):
        cargar_tabla("TABLA_INEXISTENTE")


# --- vigencia y coleccion para el contexto de reglas ----------------------------------------------


def test_vigencia_leida_del_meta(cuadro6: Tabla) -> None:
    assert cuadro6.vigencia_desde == date(2019, 10, 25)
    assert cuadro6.vigencia_hasta is None
    assert cuadro6.vigente(date(2020, 1, 1)) is True
    assert cuadro6.vigente(date(2019, 10, 25)) is True
    assert cuadro6.vigente(date(2019, 10, 24)) is False


def test_vigencia_con_hasta(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(
        tmp_path, "12,10,1.0,,si\n", meta={"vigencia": {"desde": "2020-01-01", "hasta": "2020-12-31"}}
    )
    tabla = cargar_tabla("SINTETICA", raiz)
    assert tabla.vigente(date(2020, 6, 30)) is True
    assert tabla.vigente(date(2021, 1, 1)) is False


def test_como_coleccion_permite_exists_sobre_kw_motor(cuadro6: Tabla) -> None:
    coleccion = cuadro6.como_coleccion()
    assert len(coleccion) == len(cuadro6.filas)
    assert all(isinstance(fila["kw_motor"], Decimal) for fila in coleccion)
    assert any(fila["kw_motor"] == Decimal("110") for fila in coleccion)
    assert not any(fila["kw_motor"] == Decimal("100") for fila in coleccion)


def test_meta_del_cuadro6_declara_fuente_oficial_y_metodo(cuadro6: Tabla) -> None:
    assert cuadro6.fuente and cuadro6.fuente.startswith("https://www.boe.es/")
    assert cuadro6.metodo_transcripcion in {"doue", "boe", "memoria_agente"}


# --- reglas de implementacion (CLAUDE.md §2) -----------------------------------------------------


def test_sin_float_en_el_fuente() -> None:
    fuente = Path(tablas.__file__).read_text(encoding="utf-8")
    assert "float(" not in fuente
    assert "eval(" not in fuente


def test_tablas_no_importa_periferia() -> None:
    fuente = Path(tablas.__file__).read_text(encoding="utf-8")
    for modulo in ("agentes", "salida", "generator", "tests"):
        assert f"from {modulo}" not in fuente and f"import {modulo}" not in fuente
