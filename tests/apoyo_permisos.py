"""Apoyo de los tests de permisos (S3.1b). **No es un modulo de test**: no contiene ningun `test_`.

Por que existe: desde A8 (`ADR-006`) el log exige `actor.rol` en todo evento humano, y un test que pone un
rol cualquiera para que el log no proteste es peor que no tener el rol. Este modulo responde a "¿que perfil
puede escribir de verdad este tipo de evento?" **leyendo la matriz** (`engine/capacidades.yaml`), que es la
unica fuente de quien concede que. Aqui no hay ninguna tabla perfil → capacidad copiada.

El puente entre las dos mitades:

- `engine.capacidades.capacidades_que_producen`: tipo de evento → capacidades que lo producen (de la matriz,
  que es del nucleo).
- `engine/capacidades.yaml`: capacidad → perfiles que la conceden (la matriz, que es configuracion).

`tests/test_permisos_log.py` comprueba que las dos mitades coinciden. Mientras la matriz declare los eventos
nuevos en `eventos_propuestos` (porque hasta hoy no estaban en el catalogo cerrado), se leen las dos claves;
al integrar S3.1b esa lista deberia quedar vacia y `eventos` traerlo todo.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from pathlib import Path

import yaml

from engine.eventos import Actor, ErrorEvento

RAIZ = Path(__file__).resolve().parents[1]

#: La matriz de `ADR-006` como configuracion. La escribe y la mantiene el trabajo de `FR0`; aqui solo se lee.
RUTA_MATRIZ = RAIZ / "engine" / "capacidades.yaml"

#: Los tres actos humanos que ya existian antes de A8, con el perfil que `ADR-006` les da. Estan aqui para
#: que el banco de pruebas de S3.1 (log, estados, seguimiento, salida) no dependa de un fichero que en este
#: momento escribe otro agente: si la matriz falta, estos tres siguen teniendo rol correcto y el resto de
#: tests de permisos se salta. No es una matriz alternativa; son tres celdas, y el test de coherencia las
#: contrasta contra la matriz cuando existe.
ROLES_LEGADO: Mapping[str, str] = {
    "DatoCorregidoPorHumano": "T-REV",  # CAP-05 / CAP-06
    "FirmaRegistrada": "T-RES",  # CAP-22
    "DesistimientoRegistrado": "T-RES",  # CAP-23
}


def _capacidades_de(tipo: str) -> tuple[str, ...]:
    """Las capacidades que producen ese tipo, **segun la matriz**: unica fuente de verdad (19/09/2026)."""
    from engine.capacidades import capacidades_que_producen

    return tuple(capacidad.id for capacidad in capacidades_que_producen(tipo))


def hay_matriz() -> bool:
    """`True` si la matriz esta en su sitio. Los tests que la necesitan se saltan cuando no lo esta."""
    return RUTA_MATRIZ.is_file()


@cache
def matriz() -> Mapping[str, object]:
    """La matriz cruda, tal cual esta en el YAML. Sin interpretar: eso es de `engine/capacidades.py`."""
    datos = yaml.safe_load(RUTA_MATRIZ.read_text(encoding="utf-8"))
    if not isinstance(datos, Mapping):
        raise AssertionError(f"{RUTA_MATRIZ.name}: se esperaba un mapa y llego {type(datos).__name__}")
    return datos


@cache
def capacidades() -> Mapping[str, Mapping[str, object]]:
    """Las capacidades de la matriz por `id`."""
    filas = matriz().get("capacidades") or []
    return {str(fila["id"]): fila for fila in filas if isinstance(fila, Mapping) and "id" in fila}


@cache
def perfiles() -> tuple[str, ...]:
    """Los codigos de perfil declarados en la matriz, en su orden."""
    filas = matriz().get("perfiles") or []
    return tuple(str(fila["id"]) for fila in filas if isinstance(fila, Mapping) and "id" in fila)


def eventos_de(capacidad: Mapping[str, object]) -> tuple[str, ...]:
    """Los eventos que declara una capacidad, esten ya en el catalogo o todavia como propuesta."""
    declarados: list[str] = []
    for clave in ("eventos", "eventos_propuestos"):
        for tipo in capacidad.get(clave) or ():
            declarados.append(str(tipo))
    return tuple(declarados)


def perfiles_que_conceden(tipo: str) -> tuple[str, ...]:
    """Perfiles que, segun la matriz, pueden producir ese tipo de evento. Vacio si nadie o si no hay matriz.

    Se recorre en el orden de la matriz y de `concede`, no ordenado alfabeticamente: asi
    `rol_para` devuelve siempre el mismo y los logs de prueba son reproducibles.
    """
    if not hay_matriz():
        return ()
    salida: list[str] = []
    for capacidad_id in _capacidades_de(tipo):
        fila = capacidades().get(capacidad_id)
        if fila is None:
            continue
        for perfil in fila.get("concede") or ():
            if str(perfil) not in salida:
                salida.append(str(perfil))
    return tuple(salida)


def perfiles_pendientes(tipo: str) -> tuple[str, ...]:
    """Perfiles con la celda `(?)` para ese tipo: `ADR-006` los apunta, la matriz los **deniega** hasta que
    Billy decida (A1 a A4). Hoy le pasa a `ActuacionReasignada` (CAP-32, espera A3): nadie puede escribirlo.
    """
    if not hay_matriz():
        return ()
    salida: list[str] = []
    for capacidad_id in _capacidades_de(tipo):
        fila = capacidades().get(capacidad_id)
        if fila is None:
            continue
        for perfil in fila.get("pendiente") or ():
            if str(perfil) not in salida:
                salida.append(str(perfil))
    return tuple(salida)


def rol_para(tipo: str) -> str:
    """Un perfil que puede escribir ese tipo de evento, para construir el actor humano de un test.

    Cuando la matriz concede el tipo a varios perfiles (CAP-02 y CAP-09 son compartidas) devuelve el primero:
    el test no esta probando el desempate por pantalla, que es de `api/permisos.py`.
    """
    concedido = perfiles_que_conceden(tipo)
    if concedido:
        return concedido[0]
    if tipo in ROLES_LEGADO:
        return ROLES_LEGADO[tipo]
    # Celda `(?)`: el perfil que `ADR-006` apunta, aunque la matriz lo deniegue hasta la decision. Sirve
    # para construir un actor humano con un rol **real**; quien comprueba que se deniega es el autorizador.
    pendiente = perfiles_pendientes(tipo)
    if pendiente:
        return pendiente[0]
    raise AssertionError(
        f"ningun perfil de la matriz produce {tipo!r} y no esta en ROLES_LEGADO: o falta en "
        f"{RUTA_MATRIZ.name}, o ninguna capacidad lo declara, o el evento no lo escribe una persona"
    )


def humano_para(tipo: str, id_actor: str = "persona@tenant") -> Actor:
    """El actor humano con el que un test escribe ese tipo de evento, con el rol que de verdad le toca."""
    return Actor("humano", id_actor, rol=rol_para(tipo))


def autorizador_de_matriz():
    """El gancho de `LogEventos`, construido **desde la matriz**: deniega lo que ningun perfil concede.

    Es la pieza que `ADR-011` §3 llamara `concede()` cuando `engine/capacidades.py` exista; aqui se escribe
    en diez lineas para poder probar hoy el contrato del log sin duplicar la tabla ni invadir ese fichero.
    """

    def autorizar(tipo: str, actor: Actor) -> None:
        if actor.rol is None:
            return  # el rol obligatorio ya lo exige el log; aqui solo se autoriza lo que trae rol
        concedido = perfiles_que_conceden(tipo)
        if not concedido:
            raise ErrorEvento(
                f"ninguna capacidad de `ADR-006` produce {tipo!r}: el rol {actor.rol!r} no puede escribirlo"
            )
        if actor.rol not in concedido:
            raise ErrorEvento(
                f"el perfil {actor.rol!r} no puede producir {tipo!r}: lo conceden {list(concedido)} "
                f"(capacidades {list(_capacidades_de(tipo))}, matriz {RUTA_MATRIZ.name})"
            )

    return autorizar


__all__ = [
    "ROLES_LEGADO",
    "RUTA_MATRIZ",
    "autorizador_de_matriz",
    "capacidades",
    "eventos_de",
    "hay_matriz",
    "humano_para",
    "matriz",
    "perfiles",
    "perfiles_pendientes",
    "perfiles_que_conceden",
    "rol_para",
]
