"""Los tipos del front salen del contrato y no de la cabeza de nadie (`ADR-012` §3, regla 4).

`front/compartido/api/contrato.generado.ts` esta commiteado porque el compilador de TypeScript no puede
ejecutar Python. Este test es la otra mitad del trato: **si `api/` cambia y el fichero no se regenera, esto
se pone rojo**. Y una vez regenerado, la compilacion del front senala cada sitio que usaba un bloque o una
capacidad que ya no existe. Ese es todo el mecanismo: enterarse al compilar y no en produccion.

Se comprueba ademas lo que el fichero **no** puede ser: una tabla de permisos. Que una capacidad aparezca
ahi no autoriza nada; quien concede es el servidor, en cada peticion (`R-UI-01`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.permisos import matriz
from api.proyeccion import CONSTRUCTORES
from api.tipos_front import RUTA_GENERADA, typescript

RAIZ = Path(__file__).resolve().parents[1]
GENERADO = RAIZ / RUTA_GENERADA


def test_el_fichero_generado_esta_al_dia() -> None:
    """La comprobacion que importa. Si falla: `python -c "from api.tipos_front import ..."` y regenerar."""
    assert GENERADO.is_file(), f"falta {RUTA_GENERADA}"
    esperado = typescript()
    actual = GENERADO.read_text(encoding="utf-8")
    assert actual == esperado, (
        f"{RUTA_GENERADA} no cuadra con `api/`. Regeneralo:\n"
        '  python -c "from pathlib import Path; from api.tipos_front import RUTA_GENERADA, '
        "typescript; Path(RUTA_GENERADA).write_text(typescript(), encoding='utf-8')\""
    )


def test_los_bloques_generados_son_los_que_el_servidor_sabe_construir() -> None:
    generados = re.findall(r'^  "([a-z_]+)",$', typescript().split("export const LECTURAS")[0], re.M)
    assert generados == list(CONSTRUCTORES)


def test_toda_capacidad_de_la_matriz_esta_una_vez_y_en_su_lista() -> None:
    texto = typescript()
    lecturas, comandos = texto.split("export const COMANDOS")
    for capacidad in matriz().capacidades.values():
        donde = comandos if capacidad.es_comando else lecturas
        assert f'"{capacidad.id}"' in donde, capacidad.id
        assert texto.count(f'"{capacidad.id}"') == 1, f"{capacidad.id} aparece dos veces"


def test_los_bloques_de_cada_lectura_son_los_de_la_matriz() -> None:
    texto = typescript()
    for capacidad in matriz().capacidades.values():
        if capacidad.es_comando:
            continue
        esperado = ", ".join(f'"{bloque}"' for bloque in capacidad.bloques)
        assert f'"{capacidad.id}": [{esperado}],' in texto, capacidad.id


def test_no_se_filtra_ningun_perfil_ni_ninguna_concesion() -> None:
    """El fichero dice que existe, no quien puede. La matriz de permisos no baja al navegador."""
    texto = typescript()
    for perfil in matriz().perfiles:
        assert perfil not in texto, f"{perfil} no pinta nada en el front"
    for prohibido in ("concede", "pendiente", "condicionada"):
        assert prohibido not in texto


@pytest.mark.parametrize("prohibido", ["eval(", "new Function", "innerHTML", "import "])
def test_el_fichero_generado_no_ejecuta_nada(prohibido: str) -> None:
    """Es una declaracion de tipos y constantes: sin imports, sin codigo y sin efectos."""
    assert prohibido not in GENERADO.read_text(encoding="utf-8")


def test_api_no_importa_de_front_para_generarlo() -> None:
    """`api/tipos_front.py` produce texto; la dependencia sigue yendo hacia dentro."""
    fuente = (RAIZ / "api" / "tipos_front.py").read_text(encoding="utf-8")
    assert "import front" not in fuente and "from front" not in fuente
