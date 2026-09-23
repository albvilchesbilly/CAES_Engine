"""La matriz es configuracion, y lo es de verdad (`ADR-011` §6, primer punto).

Tres cosas se comprueban aqui, y las tres son la misma: **quien puede hacer que sale del YAML**.

1. La matriz de `engine/capacidades.yaml` es la tabla de `ADR-006`: estan todas sus capacidades, todos sus
   perfiles, y ninguno de mas. La lista de este fichero esta transcrita del ADR a mano, a proposito: si el
   ADR cambia y el YAML no, o al reves, el test lo dice.
2. Para cada capacidad, un caso concedido y otro denegado. Las que hoy no concede nadie (porque todas sus
   celdas estan `(?)`) se prueban solo por el lado de la denegacion, y el error tiene que nombrar la
   decision que las cerraria.
3. Ni `api/*.py` ni `engine/capacidades.py` contienen un identificador de perfil o de capacidad. Es la
   regla de oro 4 aplicada a los permisos, comprobada como la comprueba `salida/` con los literales de la
   plataforma: leyendo el fuente con `ast` y mirando las cadenas del codigo, no los docstrings.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from api.permisos import Contexto, ErrorApi, ErrorPermiso, Principal, concede, exigir, matriz
from engine.capacidades import ErrorCapacidades, cargar_matriz
from engine.eventos.catalogo import TIPOS

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_API = RAIZ / "api"
FUENTE_MATRIZ = RAIZ / "engine" / "capacidades.py"
RUTA_YAML = RAIZ / "engine" / "capacidades.yaml"

#: Los 8 perfiles de la tabla de `ADR-006`, transcritos del ADR.
PERFILES_ADR = ("T-RES", "T-OPE", "T-REV", "EXT-INS", "EXT-CLI", "ADM-MOD", "ADM-OPS", "SYS-API")

#: La matriz de `ADR-006`: capacidad → (perfiles con ✅, perfiles con `(?)`). Transcrita del ADR.
MATRIZ_ADR: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "CAP-01": (("T-OPE",), ()),
    "CAP-02": (("T-OPE", "T-REV"), ("EXT-INS", "EXT-CLI")),
    "CAP-03": (("T-RES", "T-OPE", "T-REV"), ()),
    "CAP-04": (("T-RES", "T-OPE", "T-REV"), ("EXT-INS", "EXT-CLI")),
    "CAP-05": (("T-REV",), ()),
    "CAP-06": (("T-REV",), ()),
    "CAP-07": (("T-REV",), ()),
    "CAP-08": (("T-REV",), ()),
    "CAP-09": (("T-OPE", "T-REV"), ()),
    "CAP-10": (("T-REV",), ()),
    "CAP-11": (("T-OPE",), ()),
    "CAP-12": (("T-OPE",), ()),
    "CAP-13": (("T-OPE",), ()),
    "CAP-14": (("T-RES", "T-OPE", "T-REV"), ()),
    "CAP-15": (("T-REV",), ()),
    "CAP-16": (("T-REV",), ()),
    "CAP-17": (("T-REV",), ()),
    "CAP-20": (("T-RES",), ()),
    "CAP-21": (("T-RES",), ()),
    "CAP-22": (("T-RES",), ()),
    "CAP-23": (("T-RES",), ()),
    "CAP-30": (("T-RES",), ()),
    "CAP-31": (("T-RES",), ()),
    "CAP-32": ((), ("T-RES",)),
    "CAP-33": (("T-RES",), ()),
    "CAP-34": (("T-RES",), ()),
    "CAP-35": (("T-RES",), ("T-OPE", "T-REV")),
    "CAP-36": (("T-RES",), ()),
    "CAP-40": ((), ("EXT-INS", "EXT-CLI")),
    "CAP-50": (("ADM-MOD",), ()),
    "CAP-51": (("ADM-MOD",), ()),
    "CAP-52": (("ADM-MOD",), ()),
    "CAP-53": (("ADM-MOD",), ()),
    "CAP-54": (("ADM-MOD",), ()),
    "CAP-55": (("ADM-MOD",), ()),
    "CAP-56": (("ADM-MOD",), ()),
    "CAP-57": (("ADM-MOD",), ()),
    "CAP-58": (("ADM-MOD",), ()),
    "CAP-60": (("ADM-OPS",), ()),
    "CAP-61": (("ADM-OPS",), ()),
    "CAP-62": (("ADM-OPS",), ()),
    "CAP-63": (("ADM-OPS",), ()),
    "CAP-64": (("ADM-OPS",), ()),
    "CAP-65": (("ADM-OPS",), ()),
    "CAP-66": (("ADM-MOD", "ADM-OPS"), ()),
    "CAP-67": (("ADM-MOD", "ADM-OPS"), ()),
    "CAP-70": (("SYS-API",), ()),
}

#: La celda de `ADR-006` que no es ni ✅ ni — ni `(?)`: "solo con CAP-63".
CONDICIONADAS_ADR = {"CAP-03": "ADM-OPS"}

TENANT = "T-001"


def superficie_de(perfil: str) -> str:
    return matriz().perfil(perfil).superficie


def principal(perfil: str) -> Principal:
    ambito = matriz().ambitos[matriz().perfil(perfil).ambito]
    return Principal(f"usuario-{perfil}", (perfil,), TENANT if ambito.exige_tenant else None)


def contexto(perfil: str) -> Contexto:
    ambito = matriz().ambitos[matriz().perfil(perfil).ambito]
    return Contexto(
        superficie=superficie_de(perfil),
        tenant_id=TENANT if ambito.exige_tenant else None,
    )


# ---------------------------------------------------------------------------
# 1. La matriz del YAML es la tabla de ADR-006
# ---------------------------------------------------------------------------


def test_estan_todos_los_perfiles_del_adr_y_ninguno_mas() -> None:
    assert tuple(matriz().perfiles) == PERFILES_ADR


def test_estan_todas_las_capacidades_del_adr_y_ninguna_mas() -> None:
    assert sorted(matriz().capacidades) == sorted(MATRIZ_ADR)


@pytest.mark.parametrize("identificador", sorted(MATRIZ_ADR))
def test_cada_celda_del_adr_esta_transcrita(identificador: str) -> None:
    concedidos, pendientes = MATRIZ_ADR[identificador]
    capacidad = matriz().capacidad(identificador)
    assert capacidad.concede == frozenset(concedidos), identificador
    assert capacidad.pendiente == frozenset(pendientes), identificador


def test_la_celda_condicionada_no_se_concede_sino_que_se_explica() -> None:
    for identificador, perfil in CONDICIONADAS_ADR.items():
        capacidad = matriz().capacidad(identificador)
        condicion = capacidad.condicion_de(perfil)
        assert condicion is not None, identificador
        assert perfil not in capacidad.concede
        assert condicion.requiere and condicion.nota


def test_la_identidad_tecnica_no_tiene_pantallas() -> None:
    """`ADR-011` §2 regla 4: `SYS-API` aparece como identidad tecnica, no como usuario con pantallas."""
    sin_front = [p for p in matriz().perfiles.values() if not matriz().superficies[p.superficie].pantallas]
    assert [p.id for p in sin_front] == ["SYS-API"]


def test_un_comando_declara_eventos_del_catalogo_cerrado_y_una_lectura_ninguno() -> None:
    for capacidad in matriz().capacidades.values():
        if capacidad.es_comando:
            assert capacidad.eventos or capacidad.efecto, capacidad.id
            assert set(capacidad.eventos) <= TIPOS, capacidad.id
        else:
            assert not capacidad.eventos and not capacidad.efecto, capacidad.id


def test_cada_capacidad_declara_o_manejador_o_lo_que_le_falta() -> None:
    for capacidad in matriz().capacidades.values():
        assert capacidad.implementada != bool(capacidad.falta), capacidad.id


# ---------------------------------------------------------------------------
# 2. Concesion y denegacion, capacidad por capacidad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("identificador", sorted(MATRIZ_ADR))
def test_cada_capacidad_tiene_un_caso_concedido(identificador: str) -> None:
    concedidos = MATRIZ_ADR[identificador][0]
    if not concedidos:
        pytest.skip(f"{identificador} no la concede hoy ningun perfil: solo se prueba la denegacion")
    for perfil in concedidos:
        quien = principal(perfil)
        assert concede(matriz(), identificador, quien), f"{identificador} deberia concederse a {perfil}"
        assert exigir(matriz(), identificador, quien, contexto(perfil)) in concedidos


@pytest.mark.parametrize("identificador", sorted(MATRIZ_ADR))
def test_cada_capacidad_tiene_un_caso_denegado(identificador: str) -> None:
    concedidos, pendientes = MATRIZ_ADR[identificador]
    ajenos = [p for p in PERFILES_ADR if p not in concedidos and p not in pendientes]
    assert ajenos, f"{identificador} la tienen todos los perfiles: no hay denegacion que probar"
    perfil = ajenos[0]
    quien = principal(perfil)
    assert not concede(matriz(), identificador, quien)
    with pytest.raises(ErrorPermiso) as fallo:
        exigir(matriz(), identificador, quien, contexto(perfil))
    assert identificador in str(fallo.value)


@pytest.mark.parametrize("identificador", sorted(i for i, (_, p) in MATRIZ_ADR.items() if p))
def test_una_celda_pendiente_se_deniega_y_dice_que_decision_la_cierra(identificador: str) -> None:
    capacidad = matriz().capacidad(identificador)
    for perfil in sorted(capacidad.pendiente):
        quien = principal(perfil)
        assert not concede(matriz(), identificador, quien), f"{identificador} no se concede sin decidir"
        with pytest.raises(ErrorPermiso) as fallo:
            exigir(matriz(), identificador, quien, contexto(perfil))
        mensaje = str(fallo.value)
        assert "pendiente" in mensaje
        assert capacidad.decide in mensaje, f"{identificador} no dice que decision la cierra"


def test_las_celdas_pendientes_son_las_nueve_del_adr() -> None:
    """Nueve celdas en cinco capacidades. `ADR-011` §1 dice "siete": la tabla de `ADR-006` dice nueve."""
    celdas = sorted((c.id, perfil) for c in matriz().capacidades.values() for perfil in sorted(c.pendiente))
    assert len(celdas) == 9
    assert len({identificador for identificador, _ in celdas}) == 5


def test_un_perfil_desconocido_no_se_ignora_en_silencio() -> None:
    quien = Principal("colado", ("T-XXX",), TENANT)
    with pytest.raises(ErrorApi, match="no conoce"):
        exigir(matriz(), "CAP-03", quien, Contexto("workspace", TENANT))


def test_una_capacidad_inexistente_es_error_y_no_una_denegacion() -> None:
    with pytest.raises(ErrorApi, match="desconocida"):
        exigir(matriz(), "CAP-99", principal("T-REV"), contexto("T-REV"))


# ---------------------------------------------------------------------------
# 3. La matriz es configuracion: nada cableado en el codigo
# ---------------------------------------------------------------------------


def cadenas_de_codigo(arbol: ast.AST) -> list[str]:
    """Las cadenas del **codigo**, sin docstrings: citar una capacidad en la cabecera no es cablearla."""
    docstrings = {
        id(nodo.body[0].value)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and nodo.body
        and isinstance(nodo.body[0], ast.Expr)
        and isinstance(nodo.body[0].value, ast.Constant)
        and isinstance(nodo.body[0].value.value, str)
    }
    return [
        nodo.value
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in docstrings
    ]


FUENTES = sorted([*CARPETA_API.rglob("*.py"), FUENTE_MATRIZ])
PATRON_CAPACIDAD = re.compile(r"\bCAP-\d{2}\b")
PATRON_PERFIL = re.compile(r"\b(T-RES|T-OPE|T-REV|EXT-INS|EXT-CLI|ADM-MOD|ADM-OPS|SYS-API)\b")


def test_hay_fuentes_que_analizar() -> None:
    assert len(FUENTES) >= 10, FUENTES


@pytest.mark.parametrize("fuente", FUENTES, ids=lambda f: f.name)
def test_ningun_fuente_cablea_una_capacidad_ni_un_perfil(fuente: Path) -> None:
    arbol = ast.parse(fuente.read_text(encoding="utf-8"), filename=str(fuente))
    for cadena in cadenas_de_codigo(arbol):
        assert not PATRON_CAPACIDAD.search(cadena), f"{fuente.name}: capacidad cableada en {cadena[:60]!r}"
        assert not PATRON_PERFIL.search(cadena), f"{fuente.name}: perfil cableado en {cadena[:60]!r}"


@pytest.mark.parametrize("fuente", FUENTES, ids=lambda f: f.name)
def test_ningun_fuente_evalua_ni_usa_coma_flotante(fuente: Path) -> None:
    codigo = ast.unparse(ast.parse(fuente.read_text(encoding="utf-8")))
    for patron in (r"(?<![\w.])eval\(", r"(?<![\w.])exec\(", r"(?<![\w.])compile\(", r"(?<![\w.])float\("):
        assert not re.search(patron, codigo), f"{fuente.name} usa {patron}"


def test_el_analisis_encontraria_un_perfil_cableado(tmp_path: Path) -> None:
    """Control del control: con un `if perfil ==` de verdad, el test de arriba fallaria."""
    ruta = tmp_path / "malo.py"
    ruta.write_text(
        '"""Un modulo que habla de `if perfil == ...` en su cabecera, que si vale."""\n'
        'def f(perfil):\n    return perfil == "T-RES" and CAPACIDADES["CAP-05"]\n',
        encoding="utf-8",
    )
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    cadenas = cadenas_de_codigo(arbol)
    assert any(PATRON_PERFIL.search(c) for c in cadenas), "el perfil cableado tiene que verse"
    assert any(PATRON_CAPACIDAD.search(c) for c in cadenas), "la capacidad cableada tiene que verse"
    assert not any("cabecera" in c for c in cadenas), "un docstring no es codigo cableado"


# ---------------------------------------------------------------------------
# 4. La matriz mal formada no carga (error de arranque, no de peticion)
# ---------------------------------------------------------------------------


def yaml_modificado(tmp_path: Path, viejo: str, nuevo: str) -> Path:
    texto = RUTA_YAML.read_text(encoding="utf-8")
    assert viejo in texto
    destino = tmp_path / "capacidades.yaml"
    destino.write_text(texto.replace(viejo, nuevo, 1), encoding="utf-8")
    return destino


def test_un_evento_inventado_no_carga(tmp_path: Path) -> None:
    ruta = yaml_modificado(tmp_path, "eventos: [VerificadorAsignado]", "eventos: [VerificadorBendecido]")
    with pytest.raises(ErrorCapacidades, match="catalogo cerrado"):
        cargar_matriz(ruta)


def test_un_perfil_concedido_y_pendiente_a_la_vez_no_carga(tmp_path: Path) -> None:
    ruta = yaml_modificado(
        tmp_path, "    pendiente: [T-OPE, T-REV]\n", "    pendiente: [T-OPE, T-REV, T-RES]\n"
    )
    with pytest.raises(ErrorCapacidades):
        cargar_matriz(ruta)


def test_una_celda_pendiente_sin_decision_no_carga(tmp_path: Path) -> None:
    ruta = yaml_modificado(tmp_path, '    decide: "A3"\n', "")
    with pytest.raises(ErrorCapacidades, match="decide"):
        cargar_matriz(ruta)


def test_un_campo_de_mas_no_carga(tmp_path: Path) -> None:
    ruta = yaml_modificado(
        tmp_path, "    manejador: abrir_actuacion", "    manejador: abrir_actuacion\n    color: azul"
    )
    with pytest.raises(ErrorCapacidades, match="no permitido"):
        cargar_matriz(ruta)


def test_una_capacidad_sin_manejador_y_sin_falta_no_carga(tmp_path: Path) -> None:
    ruta = yaml_modificado(tmp_path, "    manejador: asignar_verificador", "")
    with pytest.raises(ErrorCapacidades, match="manejador"):
        cargar_matriz(ruta)


def test_dos_capacidades_no_comparten_manejador(tmp_path: Path) -> None:
    ruta = yaml_modificado(tmp_path, "    manejador: resolver_desacuerdo", "    manejador: corregir_dato")
    with pytest.raises(ErrorCapacidades, match="comparten el manejador"):
        cargar_matriz(ruta)
