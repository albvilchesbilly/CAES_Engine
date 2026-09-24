"""Lo que se comprueba **recorriendo el arbol** de `api/http/`, y no levantando ningun servidor.

Contrato C27 (`ADR-015` §3): el servidor es una capa de traduccion y nada mas. Casi todo lo que eso
significa son **ausencias** —no decide permisos, no proyecta, no valida el contrato por segunda vez, no
importa `engine/`— y una ausencia no se comprueba con una peticion de ejemplo: se comprueba mirando todo
el fuente. Es el mismo criterio de `front/workspace/tests/arbol.test.ts`, que hace esto mismo del lado de
las pantallas.

Y contrato C29: que **ninguna ruta de arranque elija sola** el autenticador de desarrollo. Eso tampoco se
ve en una peticion; se ve en quien lo nombra.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("starlette", reason="`FR-HTTP` es un extra: pip install -e '.[http]'")

from api.contrato import Respuesta  # noqa: E402
from api.http import crear_app  # noqa: E402
from api.http.autenticacion import AutenticadorAusente  # noqa: E402
from api.http.servidor import CAMPOS_CONTEXTO, _sobre_de  # noqa: E402
from api.permisos import Contexto  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PAQUETE = RAIZ / "api" / "http"
ARRANQUE = RAIZ / "servidor_desarrollo.py"
TRANSPORTE = RAIZ / "front" / "compartido" / "api" / "transporte.ts"

#: Todo `api/http/`, por su ruta relativa, para que el identificador del test diga donde esta el defecto.
MODULOS = sorted(ruta.relative_to(PAQUETE).as_posix() for ruta in PAQUETE.rglob("*.py"))


def fuente(modulo: str) -> str:
    return (PAQUETE / modulo).read_text(encoding="utf-8")


def arbol(modulo: str) -> ast.Module:
    return ast.parse(fuente(modulo))


def importados(modulo: str) -> set[str]:
    """Los paquetes que el modulo importa de verdad, incluido un `importlib` escondido.

    Una mencion en un docstring o en un comentario no cuenta: aqui se mira lo que el programa **hace**.
    """
    nombres: set[str] = set()
    for nodo in ast.walk(arbol(modulo)):
        if isinstance(nodo, ast.Import):
            nombres.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module is not None and nodo.level == 0:
            nombres.add(nodo.module)
        elif isinstance(nodo, ast.Call):
            funcion = nodo.func
            nombre = getattr(funcion, "attr", None) or getattr(funcion, "id", None)
            if nombre == "import_module" and nodo.args and isinstance(nodo.args[0], ast.Constant):
                nombres.add(str(nodo.args[0].value))
    return nombres


def test_hay_algo_que_recorrer() -> None:
    assert len(MODULOS) >= 3, MODULOS


# ---------------------------------------------------------------------------
# C27 · lo que el servidor no hace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("modulo", MODULOS)
def test_el_servidor_no_importa_nada_de_engine(modulo: str) -> None:
    """Regla de dependencias (`CLAUDE.md` §2) y C27: componer es del arranque, no de esta capa."""
    prohibidos = [
        nombre for nombre in importados(modulo) if nombre == "engine" or nombre.startswith("engine.")
    ]
    assert prohibidos == [], f"{modulo} importa {prohibidos}"


@pytest.mark.parametrize("modulo", MODULOS)
def test_el_servidor_no_importa_el_generador_ni_la_salida_ni_los_tests(modulo: str) -> None:
    prohibidos = sorted(
        nombre
        for nombre in importados(modulo)
        if nombre.split(".")[0] in {"salida", "generator", "tests", "agentes"}
    )
    assert prohibidos == [], f"{modulo} importa {prohibidos}"


#: Lo que decide los permisos, que es `api/` y esta probado alli. Aqui no se llama a nada de esto.
DECIDE_PERMISOS = ("exigir", "concede", "rol_para", "ambito_de", "comprobar_alcance", "preparar")

#: Lo que proyecta. Un bloque fuera de ambito no se construye; decidirlo aqui seria una segunda verdad.
PROYECTA = ("proyectar_vista", "bloques_a_construir", "CONSTRUCTORES", "Vista")


@pytest.mark.parametrize("modulo", MODULOS)
def test_el_servidor_no_decide_permisos_ni_proyecta(modulo: str) -> None:
    llamadas = {
        getattr(nodo.func, "attr", None) or getattr(nodo.func, "id", None)
        for nodo in ast.walk(arbol(modulo))
        if isinstance(nodo, ast.Call)
    }
    nombres = {nodo.id for nodo in ast.walk(arbol(modulo)) if isinstance(nodo, ast.Name)} | llamadas
    for prohibido in (*DECIDE_PERMISOS, *PROYECTA):
        assert prohibido not in nombres, f"{modulo} usa {prohibido}: eso lo decide `api/`, no el servidor"


@pytest.mark.parametrize("modulo", MODULOS)
def test_no_hay_ningun_identificador_de_capacidad_escrito(modulo: str) -> None:
    """Ni un `CAP-nn`. La capacidad llega en la ruta o se deriva de la matriz (ver `servidor.py`)."""
    import re

    escritos = re.findall(r"CAP-\d+", fuente(modulo))
    assert escritos == [], f"{modulo} cablea {sorted(set(escritos))}"


@pytest.mark.parametrize("modulo", MODULOS)
def test_no_hay_ejecucion_dinamica(modulo: str) -> None:
    llamadas = {
        getattr(nodo.func, "id", None) for nodo in ast.walk(arbol(modulo)) if isinstance(nodo, ast.Call)
    }
    assert not llamadas & {"eval", "exec", "compile"}, modulo


@pytest.mark.parametrize("modulo", MODULOS)
def test_el_servidor_no_toca_ninguna_cifra(modulo: str) -> None:
    """`CLAUDE.md` §2: una magnitud que pase por `float` ya perdio exactitud. Aqui no se convierte nada.

    El unico `int` del paquete es el limite de tamano del cuerpo, que son bytes y no una magnitud; se
    comprueba que no hay ninguna conversion de coma flotante ni redondeo.
    """
    llamadas = {
        getattr(nodo.func, "id", None) for nodo in ast.walk(arbol(modulo)) if isinstance(nodo, ast.Call)
    }
    assert not llamadas & {"float", "round", "Decimal"}, modulo


def test_el_contexto_del_sobre_es_el_del_contrato() -> None:
    """Los campos del contexto no se enumeran a mano dos veces: son los de `api.permisos.Contexto`."""
    assert CAMPOS_CONTEXTO == set(Contexto.__dataclass_fields__)


def test_el_sobre_lleva_todos_los_campos_de_la_respuesta() -> None:
    """Lo que el contrato devuelva y el sobre no copie, la pantalla no lo vera nunca.

    Enumerar los campos tiene este precio, y este test es el precio: el dia que `api.contrato.Respuesta`
    crezca, esto se pone rojo en vez de perderse un campo en silencio.
    """
    respuesta = Respuesta(
        capacidad="X", rol="T-REV", rol_nombre="Revisor tecnico", eventos=(), datos={}, avisos=()
    )

    assert set(_sobre_de(respuesta, ())) == set(Respuesta.__dataclass_fields__)


# ---------------------------------------------------------------------------
# C27 · las rutas son las del sobre, y el sobre es `transporte.ts`
# ---------------------------------------------------------------------------


def test_las_rutas_son_exactamente_las_que_declara_transporte_ts() -> None:
    """La forma del sobre se lee de `front/compartido/api/transporte.ts`; aqui no se inventa otra vez.

    Si alguien anade una ruta al servidor sin escribirla alli (o al reves), este test lo dice. Son un
    cliente y 208 tests de front los que dependen de esa forma.
    """
    import re

    declaradas = set(re.findall(r"POST \{base\}(/[A-Za-z{}/_-]+)", TRANSPORTE.read_text(encoding="utf-8")))
    app = crear_app()
    servidas = {ruta.path for ruta in app.routes}

    assert declaradas == servidas, (
        f"transporte.ts declara {sorted(declaradas)} y el servidor sirve {sorted(servidas)}"
    )


def test_solo_se_atiende_post() -> None:
    for ruta in crear_app().routes:
        assert set(ruta.methods) <= {"POST", "HEAD"}, ruta.path


# ---------------------------------------------------------------------------
# C29 · ninguna ruta de arranque elige sola el autenticador de desarrollo
# ---------------------------------------------------------------------------


def _fuentes_del_repositorio() -> list[tuple[str, str]]:
    """Todo el Python del repositorio que se entrega, sin entornos ni cachés."""
    excluidos = {".venv", "node_modules", "__pycache__", ".git", "informes", "expedientes"}
    fuentes = []
    for ruta in RAIZ.rglob("*.py"):
        if set(ruta.relative_to(RAIZ).parts) & excluidos:
            continue
        fuentes.append((ruta.relative_to(RAIZ).as_posix(), ruta.read_text(encoding="utf-8")))
    return fuentes


#: Los unicos sitios del codigo que se entrega donde puede nombrarse el autenticador de desarrollo: donde
#: se define, donde se reexporta y el arranque de desarrollo, que ademas exige `--desarrollo`. Los tests
#: quedan fuera de la cuenta porque su trabajo es precisamente instanciarlo para probarlo.
PUEDEN_NOMBRARLO = ("api/http/autenticacion.py", "api/http/__init__.py", "servidor_desarrollo.py")


def _quien_nombra(texto: str) -> list[str]:
    return [
        ruta
        for ruta, contenido in _fuentes_del_repositorio()
        if texto in contenido and ruta not in PUEDEN_NOMBRARLO and not ruta.startswith("tests/")
    ]


def test_solo_el_arranque_de_desarrollo_nombra_el_autenticador_de_desarrollo() -> None:
    """Ninguna otra ruta de arranque puede elegirlo, porque ninguna otra lo nombra siquiera (C29)."""
    assert _quien_nombra("AutenticadorDeDesarrollo") == []


def test_la_senal_solo_se_escribe_donde_se_define_y_en_el_arranque() -> None:
    """La cadena literal de la confirmacion no anda suelta por ahi: se escribe donde toca."""
    assert _quien_nombra("acepto-autenticacion-de-desarrollo") == []


def test_el_servidor_por_defecto_no_autentica_a_nadie() -> None:
    """C28: el valor por defecto de `crear_app` es el que deniega, y eso se lee en la firma."""
    import inspect

    firma = inspect.signature(crear_app)
    assert firma.parameters["autenticador"].default is None
    cuerpo = (PAQUETE / "servidor.py").read_text(encoding="utf-8")
    assert "AutenticadorAusente()" in cuerpo
    assert AutenticadorAusente().avisos == ()


def test_el_arranque_de_desarrollo_no_arranca_sin_decirlo() -> None:
    """`--desarrollo` no tiene valor por defecto: sin el, el proceso no levanta nada."""
    import servidor_desarrollo

    assert servidor_desarrollo.main([]) == 2
    opciones = servidor_desarrollo._argumentos(["--desarrollo"])
    assert opciones.desarrollo is True
    assert servidor_desarrollo._argumentos([]).desarrollo is False
    # Y el anfitrion por defecto es el bucle local, que es lo unico que el autenticador admite.
    assert opciones.anfitrion == "127.0.0.1"
