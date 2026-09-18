"""F0.2: tablas de data/ con vigencia, busqueda exacta e interpolacion INT-02 (docs/04 §2.5 y §7)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine import tablas
from engine.tablas import ErrorTabla, FilaTabla, Tabla, cargar_tabla, cargar_tabla_desde, cargar_tablas

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / "spec" / "IND240_v1.1.yaml"
ID_TABLA = "REG1781_CUADRO6"


@pytest.fixture(scope="module")
def cuadro6() -> Tabla:
    return cargar_tabla(ID_TABLA)


@pytest.fixture(scope="module")
def bloque_tablas_spec() -> dict:
    with SPEC.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["tablas"]


def _tabla_sintetica(tmp_path: Path, filas_csv: str, meta: dict | None = None) -> Path:
    """Escribe una tabla minima en tmp_path/data y devuelve la raiz para cargar_tabla."""
    carpeta = tmp_path / "data"
    carpeta.mkdir(exist_ok=True)
    (carpeta / "sintetica.csv").write_text(
        "kva_salida,kw_motor,perdidas_ref_kw,cos_phi,verificado\n" + filas_csv, encoding="utf-8"
    )
    meta_base = {
        "id": "SINTETICA",
        "columnas": ["kva_salida", "kw_motor", "perdidas_ref_kw", "cos_phi", "verificado"],
        "clave": "kw_motor",
        "vigencia": {"desde": "2019-10-25", "hasta": None},
    }
    if meta:
        meta_base.update(meta)
    (carpeta / "sintetica.meta.yaml").write_text(yaml.safe_dump(meta_base), encoding="utf-8")
    return tmp_path


# --- valor verificado y busqueda exacta -----------------------------------------------------------


def test_110_kw_da_5_55_exacto(cuadro6: Tabla) -> None:
    resultado = cuadro6.buscar(Decimal("110"))
    assert resultado.exacta is True
    assert resultado.valor == Decimal("5.55")
    assert resultado.interpretacion is None
    assert resultado.filas_adyacentes is None
    assert resultado.fila is not None and resultado.fila.verificado is True
    assert resultado.aviso is None  # fila verificada por Billy: sin aviso de tabla pendiente


def test_buscar_exacta_devuelve_fila_o_none(cuadro6: Tabla) -> None:
    fila = cuadro6.buscar_exacta(Decimal("110"))
    assert isinstance(fila, FilaTabla)
    assert fila.kw_motor == Decimal("110")
    assert cuadro6.buscar_exacta(Decimal("100")) is None


def test_todos_los_valores_son_decimal(cuadro6: Tabla) -> None:
    for fila in cuadro6.filas:
        assert isinstance(fila.kw_motor, Decimal)
        assert isinstance(fila.perdidas_ref_kw, Decimal)
        assert fila.kva_salida is None or isinstance(fila.kva_salida, Decimal)
        assert fila.cos_phi is None or isinstance(fila.cos_phi, Decimal)


def test_filas_ordenadas_por_clave_sin_duplicados(cuadro6: Tabla) -> None:
    claves = [f.kw_motor for f in cuadro6.filas]
    assert claves == sorted(claves)
    assert len(set(claves)) == len(claves)
    assert cuadro6.clave == "kw_motor"


# --- INT-02: sin fila exacta -> interpolacion lineal; fuera de rango -> None ------------------------


def test_sin_fila_exacta_interpola_con_int_02(cuadro6: Tabla) -> None:
    assert cuadro6.buscar_exacta(Decimal("100")) is None, "el test supone que 100 kW no tiene fila"
    fila_90 = cuadro6.buscar_exacta(Decimal("90"))
    fila_110 = cuadro6.buscar_exacta(Decimal("110"))
    assert fila_90 is not None and fila_110 is not None
    # Interpolacion lineal calculada a mano con Decimal entre las filas adyacentes 90 y 110 kW.
    esperado = fila_90.perdidas_ref_kw + (fila_110.perdidas_ref_kw - fila_90.perdidas_ref_kw) * (
        (Decimal("100") - Decimal("90")) / (Decimal("110") - Decimal("90"))
    )
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
    assert lineas[0] == "kva_salida,kw_motor,perdidas_ref_kw,cos_phi,verificado"
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
    resultado = cuadro6.buscar(pendientes[0].kw_motor)
    assert resultado.exacta is True
    assert resultado.aviso and "pendiente de verificacion humana" in resultado.aviso


def test_marca_verificado_desconocida_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n24,20,3.0,,verificado\n")
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


def test_clave_duplicada_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n12,10,1.1,,si\n")
    with pytest.raises(ErrorTabla):
        cargar_tabla("SINTETICA", raiz)


def test_meta_con_id_distinto_es_error(tmp_path: Path) -> None:
    raiz = _tabla_sintetica(tmp_path, "12,10,1.0,,si\n", meta={"id": "OTRA"})
    with pytest.raises(ErrorTabla):
        cargar_tabla_desde(raiz / "data" / "sintetica.csv", id_esperado="SINTETICA")
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
