"""Regla de dependencias y modo degradado (`CLAUDE.md` §2, `docs/05` §6.3 y §8; F0.11).

> **Dependencias hacia dentro.** `engine/` no importa nada de `agentes/` ni de `salida/`. Con todos los
> agentes apagados el Engine sigue produciendo veredicto (modo degradado). Hay un test que lo comprueba.

Este fichero es ese test, en tres formas:

1. **Sin periferia.** Hoy `agentes/` y `salida/` **no existen** (`docs/01` §3.7 y §3.8 los marcan `S3`). Los
   siete casos se procesan igualmente y dan el mismo resultado que el ground truth.
2. **Con periferia rota.** Se crean `agentes/` y `salida/` en `tmp_path`, primero vacios y despues con un
   modulo que **lanza al importarse**, y se pone `tmp_path` al principio de `sys.path`. Si `engine/` los
   importara —directamente o a traves de cualquiera de sus modulos— la importacion reventaria. No revienta.
3. **Por importaciones reales.** El arbol de sintaxis de cada modulo de `engine/` se recorre con `ast` y se
   miran sus `import` / `from … import`: una mencion en un docstring o en un comentario no cuenta, y un
   `importlib.import_module("agentes…")` escondido tampoco pasa (se busca tambien esa llamada).

`ast` se usa **aqui**, en un test, no en `engine/`: la prohibicion de `eval`/`compile` es del nucleo, que
interpreta la spec con su propio parser de lista blanca (`engine/expresiones.py`).

**Lo que este fichero todavia no puede comprobar.** "Con el LLM apagado el resultado no cambia" no aplica en
la Fase 0 porque no hay ningun agente: no existe `agentes/runtime/` ni ninguna llamada a un modelo. Cuando
el Sprint 3 los añada (`docs/06` §2, paso S3.6), este fichero se amplia con el caso "agentes encendidos y
apagados dan el mismo veredicto y el mismo ahorro, y la diferencia esta solo en la confianza y en la traza".
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PAQUETE = RAIZ / "engine"
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_GROUND_TRUTH = CARPETA_CASOS / "_resultados_esperados"
FECHA = date(2026, 9, 18)

#: Paquetes que `engine/` no puede importar: la periferia (`S3`), el generador de casos y los propios tests.
PROHIBIDOS = ("agentes", "salida", "generator", "tests")

#: **Todo** el arbol de `engine/`, no solo el primer nivel: `engine/modelo/` y `engine/eventos/` (S3.1) son
#: nucleo igual que `engine/calculo.py` y estaban fuera de estas comprobaciones hasta que la revision de
#: S3.4 lo senalo. La ruta es relativa al paquete, para que el identificador del test diga donde esta.
MODULOS = sorted(p.relative_to(PAQUETE).as_posix() for p in PAQUETE.rglob("*.py"))

CASOS = (
    "EXP001-A_completo",
    "EXP001-B_falta_registro",
    "EXP001-C_contradictorio",
    "EXP001-D_fuera_ambito",
    "EXP001-E_dos_motores",
    "EXP001-F_tres_motores",
    "EXP001-G_desordenado",
)

#: Un modulo que revienta nada mas importarse: si `engine/` tocara la periferia, se sabria.
MODULO_QUE_REVIENTA = (
    "raise RuntimeError('engine/ no debe importar la periferia (CLAUDE.md §2, dependencias hacia dentro)')\n"
)


def ground_truth(caso: str) -> dict:
    return json.loads((CARPETA_GROUND_TRUTH / f"{caso}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1 · La periferia que hay: `agentes/` sigue sin existir; `salida/` nace en S3.3
# ---------------------------------------------------------------------------


def test_la_periferia_es_la_que_dice_docs_01():
    """`salida/` nace en S3.3 (`ADR-008`) con el constructor del manifiesto; `agentes/` es S3.6.

    Este test decia hasta S3.3 que `salida/` no existia. No se relaja: se actualiza a lo que docs/01 §3.8
    describe hoy, y lo que de verdad protege el modo degradado lo comprueban los tests de abajo (el nucleo
    resuelve los siete casos con la periferia ausente, vacia o rota, y `engine/` no la importa).
    """
    assert not (RAIZ / "agentes").exists()
    assert (RAIZ / "salida" / "constructor" / "manifiesto.py").is_file()
    #: La firma es un acto humano con certificado de representante: no existe como codigo (docs/03 §10.3).
    assert not (RAIZ / "salida" / "firma").exists()


@pytest.mark.parametrize("caso", CASOS)
def test_sin_agentes_ni_salida_el_engine_produce_veredicto(caso):
    """Modo degradado: el nucleo solo, sin ningun LLM, resuelve los siete casos."""
    from engine.motor import procesar_actuacion
    from engine.spec_registry import SpecRegistry

    registro = SpecRegistry()
    registro.cargar_todas()
    esperado = ground_truth(caso)
    actuacion = procesar_actuacion(
        CARPETA_CASOS / caso,
        fecha_evaluacion=date.fromisoformat(esperado["fecha_evaluacion"]),
        ocr=False,
        registro=registro,
    )
    assert actuacion.veredicto == esperado["veredicto_esperado"]
    assert set(actuacion.evaluacion.falladas) == set(esperado["reglas_falladas_esperadas"])


# ---------------------------------------------------------------------------
# 2 · Con periferia presente (vacia o rota): nada cambia
# ---------------------------------------------------------------------------
#
# Se ejecuta en un **subproceso** con `PYTHONPATH` apuntando a la periferia creada en `tmp_path`. Recargar
# `engine.*` dentro de esta sesion de pytest no vale: al borrar los modulos de `sys.modules`, las clases y
# las excepciones se redefinen y los tests que ya tenian referencias a las antiguas (`engine/spec_registry`,
# `engine/calculo`) empiezan a fallar por identidad de clase. El subproceso aisla el experimento y ademas es
# mas fiel: prueba el arranque del Engine con la periferia presente, que es la situacion real.


SCRIPT_MODO_DEGRADADO = """
import json, sys
from datetime import date
from engine.motor import procesar_actuacion

carpeta, fecha = sys.argv[1], sys.argv[2]
actuacion = procesar_actuacion(carpeta, fecha_evaluacion=date.fromisoformat(fecha), ocr=False)
print(json.dumps({
    "veredicto": actuacion.veredicto,
    "cae": actuacion.calculo.total_cae if actuacion.calculo else None,
    "exacto": str(actuacion.calculo.total) if actuacion.calculo else None,
    "falladas": sorted(actuacion.evaluacion.falladas),
    "agentes_importado": "agentes" in sys.modules,
    "salida_importada": "salida" in sys.modules,
}))
"""


def _crear_periferia(raiz: Path, contenido: str | None) -> None:
    """Crea `agentes/` y `salida/` en `raiz`. `contenido=None` los deja vacios (sin `__init__.py`)."""
    for nombre in ("agentes", "salida"):
        carpeta = raiz / nombre
        carpeta.mkdir()
        if contenido is not None:
            (carpeta / "__init__.py").write_text(contenido, encoding="utf-8")


def _ejecutar_con_periferia(raiz: Path, caso: str) -> dict:
    """Corre el Engine en un subproceso con `raiz` (la periferia) al principio del `PYTHONPATH`."""
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = os.pathsep.join([str(raiz), str(RAIZ)])
    esperado = ground_truth(caso)
    proceso = subprocess.run(  # noqa: S603 - interprete fijo, sin shell, argumentos controlados
        [
            sys.executable,
            "-c",
            SCRIPT_MODO_DEGRADADO,
            str(CARPETA_CASOS / caso),
            esperado["fecha_evaluacion"],
        ],
        capture_output=True,
        text=True,
        env=entorno,
        cwd=str(RAIZ),
    )
    assert proceso.returncode == 0, f"el Engine no arranco con la periferia presente:\n{proceso.stderr}"
    return json.loads(proceso.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    ("contenido", "descripcion"),
    [(None, "vacias"), (MODULO_QUE_REVIENTA, "con un modulo que lanza al importarse")],
)
@pytest.mark.parametrize("caso", CASOS)
def test_con_agentes_y_salida_presentes_el_resultado_no_cambia(tmp_path, contenido, descripcion, caso):
    _crear_periferia(tmp_path, contenido)
    obtenido = _ejecutar_con_periferia(tmp_path, caso)
    esperado = ground_truth(caso)
    assert obtenido["veredicto"] == esperado["veredicto_esperado"]
    assert obtenido["falladas"] == sorted(esperado["reglas_falladas_esperadas"])
    if esperado["aetotal_esperado"]["exacto"] is not None:
        assert Decimal(obtenido["exacto"]) == Decimal(esperado["aetotal_esperado"]["exacto"])
    else:
        assert obtenido["exacto"] is None
    assert obtenido["cae"] == esperado["aetotal_esperado"]["cae"]
    assert obtenido["agentes_importado"] is False
    assert obtenido["salida_importada"] is False


def test_el_modulo_que_revienta_revienta_de_verdad(tmp_path):
    """Control del control: si el modulo trampa no fallara, el test anterior no probaria nada."""
    _crear_periferia(tmp_path, MODULO_QUE_REVIENTA)
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = str(tmp_path)
    for nombre in ("agentes", "salida"):
        proceso = subprocess.run(  # noqa: S603 - interprete fijo, sin shell
            [sys.executable, "-c", f"import {nombre}"],
            capture_output=True,
            text=True,
            env=entorno,
            cwd=str(tmp_path),
        )
        assert proceso.returncode != 0
        assert "dependencias hacia dentro" in proceso.stderr


# ---------------------------------------------------------------------------
# 3 · Dependencias hacia dentro, por importaciones reales
# ---------------------------------------------------------------------------


def importaciones_de(ruta: Path) -> set[str]:
    """Paquetes de primer nivel que el modulo importa de verdad (`ast`, no busqueda de texto)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    paquetes: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            paquetes |= {alias.name.split(".")[0] for alias in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            paquetes.add(nodo.module.split(".")[0])
    return paquetes


def importaciones_dinamicas_de(ruta: Path) -> set[str]:
    """Modulos citados en `importlib.import_module("…")` o `__import__("…")` con literal de cadena."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or not nodo.args:
            continue
        funcion = nodo.func
        es_import_module = isinstance(funcion, ast.Attribute) and funcion.attr == "import_module"
        es_dunder = isinstance(funcion, ast.Name) and funcion.id == "__import__"
        primero = nodo.args[0]
        if (es_import_module or es_dunder) and isinstance(primero, ast.Constant):
            if isinstance(primero.value, str):
                nombres.add(primero.value.split(".")[0])
    return nombres


def test_hay_modulos_que_analizar():
    assert len(MODULOS) >= 10, f"solo se encontraron {MODULOS} en engine/"


@pytest.mark.parametrize("modulo", MODULOS)
def test_engine_no_importa_la_periferia_ni_el_generator_ni_los_tests(modulo):
    ruta = PAQUETE / modulo
    prohibidas = importaciones_de(ruta) & set(PROHIBIDOS)
    assert not prohibidas, f"engine/{modulo} importa {sorted(prohibidas)}"


@pytest.mark.parametrize("modulo", MODULOS)
def test_engine_no_importa_la_periferia_por_la_puerta_de_atras(modulo):
    ruta = PAQUETE / modulo
    prohibidas = importaciones_dinamicas_de(ruta) & set(PROHIBIDOS)
    assert not prohibidas, f"engine/{modulo} importa dinamicamente {sorted(prohibidas)}"


def test_una_mencion_en_un_docstring_no_cuenta_como_importacion(tmp_path):
    """El analisis es por `ast`: si fuera por texto, este fichero daria un falso positivo."""
    ruta = tmp_path / "ejemplo.py"
    ruta.write_text(
        '"""Este modulo no importa agentes ni salida: from agentes import x."""\n'
        "# import salida\n"
        "CONSTANTE = 'from generator import casos'\n",
        encoding="utf-8",
    )
    assert importaciones_de(ruta) == set()


def test_el_analisis_detecta_una_importacion_de_verdad(tmp_path):
    """Control del control: con un `import` real, la funcion lo encuentra."""
    ruta = tmp_path / "ejemplo.py"
    ruta.write_text("from agentes.runtime import algo\nimport salida\n", encoding="utf-8")
    assert {"agentes", "salida"} <= importaciones_de(ruta)


def test_el_analisis_detecta_una_importacion_dinamica(tmp_path):
    ruta = tmp_path / "ejemplo.py"
    ruta.write_text("import importlib\nm = importlib.import_module('agentes.runtime')\n", encoding="utf-8")
    assert "agentes" in importaciones_dinamicas_de(ruta)


@pytest.mark.parametrize("modulo", MODULOS)
def test_engine_no_usa_eval_exec_ni_compile(modulo):
    """Regla de oro: la `logica` se interpreta con el parser de lista blanca, nunca con `eval`."""
    arbol = ast.parse((PAQUETE / modulo).read_text(encoding="utf-8"), filename=modulo)
    llamadas = {
        nodo.func.id
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
    }
    assert not llamadas & {"eval", "exec", "compile"}, f"engine/{modulo} llama a eval/exec/compile"
