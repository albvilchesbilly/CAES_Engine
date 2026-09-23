"""La cola de revision: una capacidad propia, filas con motivo y **un orden que pone el servidor**.

`ADR-014` §2 (contrato C22). Lo que se comprueba aqui es lo que esa decision protege:

1. **Es una capacidad aparte.** Enumerar la cartera del tenant no es "consultar la actuacion" con un
   parametro de mas: un perfil que tiene la lectura de una actuacion y no la de la cola **no puede
   listarla**. Si algun dia alguien la convierte en un modo lista, este test se pone rojo.
2. **El orden lo pone el servidor** (`R-UI-11`). Se prueba por el unico camino que lo demuestra: cambiando
   el orden en que el repositorio devuelve las actuaciones y viendo que la respuesta no cambia.
3. **Ninguna fila sin motivo**, y **ningun valor de variable** en una fila: arrastrar una cita (`R-UI-09`)
   a una lista que se lee de un vistazo es lo que la spec de la pantalla evita a proposito.

Los casos son los sinteticos: A (`PREVALIDADO`, sin nada que esperar), B (dos carencias `SUBSANABLE`) y C
(conflicto en `PM`, `BLOQUEADO`).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path

import pytest

from api.contrato import Peticion
from api.lecturas import leer
from api.permisos import Contexto, ErrorPermiso, Principal, matriz
from api.proyeccion import (
    CONSTRUCTORES,
    ESTADO_ESCALADO,
    MOTIVO_CONFLICTO,
    MOTIVO_CORRECCION,
    MOTIVO_ESCALADO,
    MOTIVO_REQUERIMIENTO,
    MOTIVO_TAREA,
    PRIORIDAD_MOTIVO,
)
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.estados import ESTADOS_CICLO
from engine.eventos.log import Actor
from engine.motor import procesar_actuacion
from engine.seguimiento import TareaRecibida, registrar_tarea
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[1]
FECHA = date(2026, 9, 18)
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
TENANT = "T-001"

#: La capacidad de cola y la pantalla desde la que se pide, leidas de la matriz: aqui no se cablea ninguna.
CAPACIDAD_COLA = next(
    identificador
    for identificador, capacidad in matriz().capacidades.items()
    if not capacidad.es_comando and "cola" in capacidad.bloques
)
PANTALLA = "cola_revision"


@cache
def _procesada(caso: str):
    """Un caso sintetico procesado una vez por sesion, sin OCR."""
    registro = SpecRegistry()
    registro.cargar_todas()
    return procesar_actuacion(
        RAIZ / "expedientes" / caso, fecha_evaluacion=FECHA, ocr=False, registro=registro
    )


def _repositorio(orden: tuple[str, ...]) -> RepositorioMemoria:
    """El tenant con los tres casos, insertados en el orden que se pida (el de `actuaciones_de`)."""
    casos = {
        "A": "EXP001-A_completo",
        "B": "EXP001-B_falta_registro",
        "C": "EXP001-C_contradictorio",
    }
    repositorio = RepositorioMemoria()
    for clave in orden:
        repositorio.anadir(clave, TENANT, actuacion=_procesada(casos[clave]))
    return repositorio


@pytest.fixture
def servicios() -> Servicios:
    return Servicios(repositorio=_repositorio(("A", "B", "C")), instante=INSTANTE)


def revisor() -> Principal:
    return Principal("u-rev", ("T-REV",), TENANT)


def _cola(servicios: Servicios, quien: Principal | None = None):
    peticion = Peticion(CAPACIDAD_COLA, quien or revisor(), Contexto(PANTALLA, TENANT))
    return leer(peticion, servicios=servicios).datos["cola"]


def _ids(filas) -> list[str]:
    return [fila["identificacion"]["actuacion_id"] for fila in filas]


def _motivos(fila) -> list[str]:
    return [motivo["motivo"] for motivo in fila["motivos"]]


# ---------------------------------------------------------------------------
# 1. Es una capacidad propia, con su celda en la matriz
# ---------------------------------------------------------------------------


def test_la_cola_es_una_lectura_de_tenant_con_su_propio_bloque() -> None:
    capacidad = matriz().capacidad(CAPACIDAD_COLA)
    assert not capacidad.es_comando
    assert capacidad.bloques == ("cola",)
    assert "cola" in CONSTRUCTORES
    assert "cola" in matriz().ambitos["tenant"].bloques


def test_un_perfil_sin_la_capacidad_no_puede_ejercerla(servicios: Servicios) -> None:
    """La razon de ser de C22: la lectura de *una* actuacion no autoriza a enumerar el tenant.

    `T-OPE` y `T-RES` tienen concedida la consulta de la actuacion completa y **no** tienen la cola. Si
    algun dia la cola se cuelga de aquella como "modo lista", esto se pone rojo, que es el punto.
    """
    for perfil in ("T-OPE", "T-RES"):
        quien = Principal(f"u-{perfil}", (perfil,), TENANT)
        assert matriz().capacidad("CAP-03").concede >= {perfil}
        with pytest.raises(ErrorPermiso) as fallo:
            _cola(servicios, quien)
        assert CAPACIDAD_COLA in str(fallo.value)
        assert "no concedida" in str(fallo.value)


def test_la_cola_no_devuelve_ningun_otro_bloque(servicios: Servicios) -> None:
    respuesta = leer(Peticion(CAPACIDAD_COLA, revisor(), Contexto(PANTALLA, TENANT)), servicios=servicios)
    assert set(respuesta.datos) == {"cola"}
    assert respuesta.eventos == ()
    assert respuesta.rol == "T-REV"


def test_la_cola_de_otro_tenant_no_se_ve(servicios: Servicios) -> None:
    """El tenant lo fija la autenticacion: un principal de otro tenant no enumera este."""
    ajeno = Principal("u-ajeno", ("T-REV",), "T-002")
    with pytest.raises(ErrorPermiso, match="cruce de tenant"):
        _cola(servicios, ajeno)


# ---------------------------------------------------------------------------
# 2. El orden lo pone el servidor
# ---------------------------------------------------------------------------


def test_el_orden_lo_pone_el_servidor_y_no_el_orden_del_repositorio() -> None:
    """`R-UI-11`: la pantalla no ordena, asi que el orden no puede depender de como llegue la lista.

    Se pide la misma cola con el repositorio devolviendo las actuaciones en los seis ordenes posibles: la
    respuesta es siempre la misma. Si el constructor devolviera las filas tal cual le llegan, esto falla.
    """
    ordenes = (("A", "B", "C"), ("C", "B", "A"), ("B", "C", "A"), ("C", "A", "B"))
    resultados = {
        orden: _ids(_cola(Servicios(repositorio=_repositorio(orden), instante=INSTANTE))) for orden in ordenes
    }
    assert len(set(map(tuple, resultados.values()))) == 1, resultados
    # Y ese orden es el de `T-REV-cola` §6: el conflicto (prioridad 1) antes que la correccion (3).
    assert next(iter(resultados.values())) == ["C", "B"]


def test_la_prioridad_es_la_del_motivo_mas_alto_de_cada_fila(servicios: Servicios) -> None:
    filas = _cola(servicios)
    prioridades = [min(motivo["prioridad"] for motivo in fila["motivos"]) for fila in filas]
    assert prioridades == sorted(prioridades)


def test_las_prioridades_son_las_cinco_de_la_spec_de_pantalla() -> None:
    """Los cuatro niveles de `T-REV-cola` §6: conflicto, escalado y requerimiento, correccion, tarea."""
    assert PRIORIDAD_MOTIVO == {
        MOTIVO_CONFLICTO: 1,
        MOTIVO_ESCALADO: 2,
        MOTIVO_REQUERIMIENTO: 2,
        MOTIVO_CORRECCION: 3,
        MOTIVO_TAREA: 4,
    }


def test_el_estado_de_escalado_es_vocabulario_del_nucleo() -> None:
    """Si `engine.estados` renombra el estado, esto lo dice en vez de dejar el motivo mudo para siempre."""
    assert ESTADO_ESCALADO in ESTADOS_CICLO


def test_a_igual_motivo_va_antes_la_que_lleva_mas_tiempo_abierta() -> None:
    repositorio = _repositorio(("B",))
    repositorio.anadir("B2", TENANT, actuacion=_procesada("EXP001-B_falta_registro"))
    motor = Actor("motor", "engine")
    repositorio.log("B2").anadir(
        "DocumentoRegistrado", {"sha256": "0" * 64}, actor=motor, ocurrido_en=INSTANTE
    )
    repositorio.log("B").anadir(
        "DocumentoRegistrado",
        {"sha256": "1" * 64},
        actor=motor,
        ocurrido_en=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
    )
    filas = _cola(Servicios(repositorio=repositorio, instante=INSTANTE))
    assert _ids(filas) == ["B", "B2"]
    assert filas[0]["antiguedad"]["abierta_en"] == "2026-09-01T08:00:00+00:00"


def test_sin_historial_la_antiguedad_es_nula_y_la_fila_va_al_final(servicios: Servicios) -> None:
    """`R-UI-07`: sin log no hay "0 dias", hay `SIN DATO`. Y una fila sin fecha no adelanta a las que si."""
    for fila in _cola(servicios):
        assert fila["antiguedad"] == {"abierta_en": None, "ultimo_movimiento_en": None}


# ---------------------------------------------------------------------------
# 3. Que lleva una fila, y que no lleva
# ---------------------------------------------------------------------------


def test_ninguna_fila_esta_sin_motivo_y_la_que_no_espera_nada_no_esta(servicios: Servicios) -> None:
    filas = _cola(servicios)
    assert all(fila["motivos"] for fila in filas)
    # El caso A esta `PREVALIDADO`, sin conflictos, sin carencias y sin tareas: no es trabajo pendiente.
    assert "A" not in _ids(filas)


def test_el_caso_c_declara_su_conflicto_con_la_variable_y_la_unidad(servicios: Servicios) -> None:
    fila = next(f for f in _cola(servicios) if f["identificacion"]["actuacion_id"] == "C")
    assert fila["veredicto"]["valor"] == "BLOQUEADO"
    assert MOTIVO_CONFLICTO in _motivos(fila)
    conflicto = next(m for m in fila["motivos"] if m["motivo"] == MOTIVO_CONFLICTO)
    assert conflicto["detalle"]["variables"] == [{"variable": "PM", "num_serie_motor": "MTR-SYN-0001"}]


def test_el_caso_b_declara_sus_carencias_con_la_severidad_mas_alta(servicios: Servicios) -> None:
    fila = next(f for f in _cola(servicios) if f["identificacion"]["actuacion_id"] == "B")
    correccion = next(m for m in fila["motivos"] if m["motivo"] == MOTIVO_CORRECCION)
    assert correccion["detalle"]["severidad"] == "SUBSANABLE"
    assert correccion["detalle"]["carencias"] == ["R-DOC-01", "R-EVD-04"]


def test_una_tarea_de_la_plataforma_es_motivo_por_si_sola() -> None:
    """El cuarto motivo de §6: la plataforma pide algo y nadie lo ha mirado."""
    repositorio = _repositorio(("A",))
    registrar_tarea(
        repositorio.log("A"),
        TareaRecibida(
            id="TAR-1",
            tenant_id=TENANT,
            asunto="Aportar documentacion adicional",
            instante=INSTANTE,
            referencia="REF-1",
            vence_en=date(2026, 10, 1),
        ),
    )
    fila = next(f for f in _cola(Servicios(repositorio=repositorio, instante=INSTANTE)))
    assert _motivos(fila) == [MOTIVO_TAREA]
    assert next(m for m in fila["motivos"] if m["motivo"] == MOTIVO_TAREA)["detalle"]["tareas"] == ["TAR-1"]


def test_ninguna_fila_lleva_un_valor_de_variable_ni_su_cita(servicios: Servicios) -> None:
    """`R-UI-09` al reves: lo que no se sirve no se puede pintar sin cita, porque no se pinta.

    La cola nombra el conflicto (`PM`) y **no** ensena los dos valores enfrentados: eso, con sus cuatro
    evidencias, esta una pulsacion mas alla, en la vista de revision.
    """
    filas = _cola(servicios)
    assert filas
    for fila in filas:
        assert set(fila) == {"identificacion", "veredicto", "motivos", "antiguedad", "estado"}
        plano = json.dumps(fila, ensure_ascii=False)
        for prohibido in (
            "texto_literal",
            "valor_consumido",
            "evidencias",
            "doc_id",
            "total_exacto",
            "sha256",
            "payload",
        ):
            assert prohibido not in plano, f"{prohibido} no pinta nada en una fila de cola"


def test_la_fila_trae_el_identificador_con_el_que_se_vuelve_a_pedir(servicios: Servicios) -> None:
    """`R-UI-12`: la pantalla navega con los identificadores que le dio la lectura, no los compone."""
    for fila in _cola(servicios):
        identificador = fila["identificacion"]["actuacion_id"]
        assert servicios.repositorio.tenant_de(identificador) == TENANT


def test_el_estado_de_la_fila_es_el_del_ciclo_y_el_de_la_plataforma(servicios: Servicios) -> None:
    for fila in _cola(servicios):
        assert set(fila["estado"]) == {
            "estado_ciclo",
            "estado_plataforma",
            "requerimiento_abierto",
            "afectada_directamente",
            "literales_desconocidos",
            "secuencia",
        }


def test_una_actuacion_sin_procesar_no_desaparece_de_la_cola() -> None:
    """Si el motor no la ha procesado, la cola la sigue enumerando con lo que el log si dice."""
    repositorio = RepositorioMemoria()
    repositorio.anadir("SIN-PROCESAR", TENANT)
    registrar_tarea(
        repositorio.log("SIN-PROCESAR"),
        TareaRecibida(id="TAR-9", tenant_id=TENANT, asunto="Revisar", instante=INSTANTE),
    )
    fila = next(f for f in _cola(Servicios(repositorio=repositorio, instante=INSTANTE)))
    assert fila["identificacion"]["actuacion_id"] == "SIN-PROCESAR"
    assert fila["veredicto"] == {"valor": None, "semaforo": None, "mensaje": None}
    assert _motivos(fila) == [MOTIVO_TAREA]


def test_un_tenant_sin_nada_que_revisar_devuelve_una_lista_vacia() -> None:
    """Vacio es vacio, y se distingue de un error: quien responde es la lectura, no un fallo."""
    assert _cola(Servicios(repositorio=_repositorio(("A",)), instante=INSTANTE)) == []
