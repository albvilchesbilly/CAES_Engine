"""Puerta de calidad sobre `Spec.avisos_carga`: ningun aviso de carga pasa desapercibido.

Por que existe este fichero (Billy, 20/09/2026). La auditoria `/contrastar` del 20/09/2026 encontro dos
defectos serios —H1 (una actuacion excluida saldria `PREVALIDADA`) y H3 (la guarda que impide publicar un
ahorro incoherente no tenia test)— y result0 que **el Spec Registry ya los estaba senalando en cada carga**:

    garantia no verificable estaticamente para R-AMB-02: categoria
    calculo: precondicion 'ninguna regla con severidad BLOQUEANTE fallida' es prosa (sin operadores):
    no se evalua en el calculo; la aplica reglas.py

Los avisos llevaban ahi desde F0.4 y nadie los leia, porque nada los miraba. Un aviso que no rompe nada es
documentacion, no una alarma. A partir de aqui la lista de avisos de cada spec activa es **cerrada**: esta
declarada abajo con su razon, y cualquier desviacion rompe la puerta de calidad.

Rompe en los dos sentidos, y eso es deliberado:

- **Aviso nuevo** -> alguien introdujo una carencia que el registro no puede comprobar. Es lo que paso con
  H1. Se estudia; si es aceptable, se declara abajo **con su razon y su hallazgo**, nunca como una linea
  suelta que silencia la alarma.
- **Aviso que desaparece** -> la razon declarada abajo ya no vale. Se borra la entrada, en la misma sesion.
  Sin esto la linea base envejece y vuelve a ser documentacion.

`tests/test_spec_registry.py::test_avisos_de_carga_de_la_spec_activa` sigue existiendo y es complementario:
aquel afirma que ciertos avisos concretos **estan** (con `any`), este que no hay **ningun otro**.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.spec_registry import RAIZ, cargar_spec

CARPETA_SPECS = RAIZ / "spec"

# Aviso exacto -> por que se acepta hoy y quien lo cubre. Una entrada sin razon util no vale: la razon es lo
# que permite decidir, dentro de un ano, si el aviso sigue estando bien.
AVISOS_DECLARADOS: dict[str, dict[str, str]] = {
    "IND240_v1.1.yaml": {
        "garantia no verificable estaticamente para R-AMB-02: categoria": (
            "`categoria` no es una variable de la spec: la infiere `engine/extraccion.py` de la prosa de "
            "cada linea de factura, asi que el registro no puede comprobar estaticamente que su carencia "
            "quede recogida por una SUBSANABLE. Este aviso senalo el punto exacto donde aparecio H1. "
            "Seguira siendo verdad mientras el lexico viva en `engine/` y no en la spec (INT-15, ADR-003 "
            "H-06). Lo que si esta cubierto ahora es el comportamiento: `tests/test_ambito_factura.py`."
        ),
        "garantia no verificable estaticamente para R-CON-07: n_motores": (
            "Mismo caso: `n_motores` se deriva del recuento de unidades, no se declara como variable. La "
            "severidad de R-CON-07 esta ademas pendiente de Billy (ADR-002 §6, ADR-003)."
        ),
        (
            "calculo.precondiciones[2] no es una expresion del vocabulario y se conserva como precondicion "
            "de procedimiento (texto): 'ninguna regla con severidad BLOQUEANTE fallida'"
        ): (
            "Deliberado: la precondicion es prosa y el parser de lista blanca no la puede evaluar, asi que "
            "se conserva como texto en vez de inventarle una expresion. La aplica `engine/reglas.py`."
        ),
        (
            "calculo: precondicion 'ninguna regla con severidad BLOQUEANTE fallida' es prosa (sin "
            "operadores): no se evalua en el calculo; la aplica reglas.py"
        ): (
            "La otra cara del anterior, y la razon de ser de H3: esta precondicion de la spec tiene una "
            "unica implementacion, la rama `elif bloqueo_previo` de `engine/reglas.py`. El aviso dice con "
            "todas las letras donde vive, y aun asi la rama sobrevivia a su propia eliminacion con la suite "
            "entera en verde. Cubierta ahora en `tests/test_reglas.py`."
        ),
    },
}


def _specs_activas() -> list[Path]:
    return sorted(CARPETA_SPECS.glob("*.yaml"))


def test_hay_al_menos_una_spec_activa() -> None:
    """Si el glob no encuentra nada, los tests de abajo pasarian vacios y no probarian nada."""
    assert _specs_activas(), f"ninguna spec activa en {CARPETA_SPECS}"


@pytest.mark.parametrize("ruta", _specs_activas(), ids=lambda r: r.name)
def test_la_spec_activa_no_trae_avisos_de_carga_sin_declarar(ruta: Path) -> None:
    """Un aviso nuevo rompe la puerta: es una carencia que el registro no puede comprobar por si solo."""
    declarados = AVISOS_DECLARADOS.get(ruta.name)
    assert declarados is not None, (
        f"{ruta.name} es una spec activa sin entrada en AVISOS_DECLARADOS. Dar de alta una ficha incluye "
        f"declarar sus avisos de carga (aunque sean cero: una entrada con un dict vacio) y la razon de "
        f"cada uno. Ver docs/04 §15."
    )
    obtenidos = set(cargar_spec(ruta).avisos_carga)
    nuevos = obtenidos - set(declarados)
    assert not nuevos, (
        f"{ruta.name} trae {len(nuevos)} aviso(s) de carga sin declarar:\n"
        + "\n".join(f"  - {a}" for a in sorted(nuevos))
        + "\n\nUn aviso de carga es el registro diciendo que hay algo que no puede comprobar solo. No lo "
        "silencies anadiendolo a AVISOS_DECLARADOS sin mas: primero decide si la carencia es aceptable y "
        "que la cubre (un test, un hallazgo, un INT-xx), y escribe eso como razon. Si no es aceptable, "
        "arregla la spec o el codigo. Este test existe porque los avisos de H1 y H3 llevaban meses "
        "impresos sin que nadie los leyera."
    )


@pytest.mark.parametrize("ruta", _specs_activas(), ids=lambda r: r.name)
def test_no_quedan_avisos_declarados_que_ya_no_ocurren(ruta: Path) -> None:
    """Un aviso que desaparece tambien rompe: sin esto la linea base envejece y deja de ser una alarma."""
    declarados = set(AVISOS_DECLARADOS.get(ruta.name) or {})
    obsoletos = declarados - set(cargar_spec(ruta).avisos_carga)
    assert not obsoletos, (
        f"{ruta.name} declara {len(obsoletos)} aviso(s) que ya no ocurren:\n"
        + "\n".join(f"  - {a}" for a in sorted(obsoletos))
        + "\n\nBorra la entrada de AVISOS_DECLARADOS en esta misma sesion. Si el aviso desaparecio porque "
        "se arreglo la carencia, dilo en el commit: es una mejora real y merece constar."
    )


def test_cada_aviso_declarado_trae_una_razon_util() -> None:
    """Una razon vacia o de tres palabras convierte la linea base en una lista de silenciados."""
    for fichero, avisos in AVISOS_DECLARADOS.items():
        for aviso, razon in avisos.items():
            assert len(razon.split()) >= 12, (
                f"{fichero}: la razon declarada para {aviso!r} no explica nada ({razon!r}). Di por que la "
                f"carencia es aceptable y que la cubre."
            )
