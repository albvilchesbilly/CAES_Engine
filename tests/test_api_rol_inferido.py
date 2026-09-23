"""Inferencia del rol ejercido (`ADR-011` §6, punto 3, y `ADR-050`, opcion E).

La regla: si la capacidad la concede un solo perfil del usuario, ese es el rol; si la conceden varios,
desempata la pantalla del contexto; si sigue sin resolverse, **es un error y no una eleccion al azar**.

Importa porque el rol se persiste (`actor.rol`, A8): un rol elegido a dedo entre dos posibles parece
trazabilidad y no lo es. En un delegado pequeño, que acumula los tres perfiles de tenant, esto pasa todos
los dias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from api.comandos import ejecutar
from api.contrato import Peticion
from api.lecturas import leer
from api.permisos import Contexto, ErrorApi, Principal, matriz, rol_para
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.eventos.log import Actor

TENANT = "T-001"
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

#: Las dos capacidades compartidas que ademas generan eventos (`ADR-050`): el rol lo fija la pantalla.
COMPARTIDAS = ("CAP-02", "CAP-09")


@dataclass(frozen=True)
class ActuacionMinima:
    """Lo justo que la proyeccion necesita para identificar una actuacion, sin procesar el caso entero."""

    id: str
    codigo_identificativo_propio: str = "COD-1"
    fecha_evaluacion: str = "2026-09-18"
    spec: object = None


def _evaluada(repositorio: RepositorioMemoria, identificador: str) -> None:
    """Deja la actuacion en `EVALUADA`, que es desde donde se pide una subsanacion.

    Los dos eventos los escribe el **motor**, no una persona: son los que produce la cadena de proceso.
    """
    log = repositorio.log(identificador)
    motor = Actor("motor", "engine")
    log.anadir("DocumentoRegistrado", {"sha256": "0" * 64}, actor=motor, ocurrido_en=INSTANTE)
    log.anadir("VeredictoEmitido", {"veredicto": "SUBSANABLE"}, actor=motor, ocurrido_en=INSTANTE)


@pytest.fixture
def servicios() -> Servicios:
    repositorio = RepositorioMemoria()
    repositorio.anadir("A-1", TENANT, actuacion=ActuacionMinima("A-1"))
    _evaluada(repositorio, "A-1")
    return Servicios(repositorio=repositorio, instante=INSTANTE)


def delegado_pequeno() -> Principal:
    """Una sola persona con los tres perfiles de tenant: el segmento prioritario de `docs/08` §2."""
    return Principal("billy", ("T-RES", "T-OPE", "T-REV"), TENANT)


# ---------------------------------------------------------------------------
# 1. Un solo perfil que concede: no hay nada que inferir
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("identificador", sorted(matriz().capacidades))
def test_con_un_solo_perfil_el_rol_es_ese(identificador: str) -> None:
    capacidad = matriz().capacidad(identificador)
    if not capacidad.concede:
        pytest.skip(f"{identificador} no la concede hoy ningun perfil")
    for perfil in sorted(capacidad.concede):
        declarado = matriz().perfil(perfil)
        ambito = matriz().ambitos[declarado.ambito]
        quien = Principal("u", (perfil,), TENANT if ambito.exige_tenant else None)
        contexto = Contexto(declarado.superficie, quien.tenant_id)
        assert rol_para(matriz(), identificador, quien, contexto) == perfil


@pytest.mark.parametrize("identificador", sorted(matriz().capacidades))
def test_el_delegado_pequeno_resuelve_el_rol_sin_ambiguedad(identificador: str) -> None:
    """Con los tres perfiles de tenant, solo las dos capacidades compartidas necesitan desempate."""
    capacidad = matriz().capacidad(identificador)
    candidatos = [p for p in delegado_pequeno().perfiles if p in capacidad.concede]
    if len(candidatos) != 1:
        pytest.skip(f"{identificador} no la concede exactamente un perfil de tenant")
    contexto = Contexto("workspace", TENANT)
    assert rol_para(matriz(), identificador, delegado_pequeno(), contexto) == candidatos[0]


def test_las_unicas_capacidades_compartidas_del_workspace_son_las_dos_de_adr_050() -> None:
    compartidas = sorted(
        capacidad.id
        for capacidad in matriz().capacidades.values()
        if len([p for p in delegado_pequeno().perfiles if p in capacidad.concede]) > 1
        and capacidad.es_comando
    )
    assert compartidas == list(COMPARTIDAS)


# ---------------------------------------------------------------------------
# 2. Capacidades compartidas: desempata la pantalla
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("identificador", COMPARTIDAS)
@pytest.mark.parametrize(
    ("pantalla", "esperado"),
    [
        ("cola_revision", "T-REV"),
        # `GAP-REV-06`: la vista de revision ya es una pantalla propia y desempata igual que la cola. Antes
        # tenia que decir que venia de `cola_revision`, y el contexto mentia sobre desde donde se actuaba.
        ("vista_revision", "T-REV"),
        ("bandeja_actuaciones", "T-OPE"),
    ],
)
def test_la_pantalla_desempata_la_capacidad_compartida(
    identificador: str, pantalla: str, esperado: str
) -> None:
    contexto = Contexto(pantalla, TENANT, "A-1")
    assert rol_para(matriz(), identificador, delegado_pequeno(), contexto) == esperado


def test_sin_pantalla_la_capacidad_compartida_no_se_resuelve_al_azar() -> None:
    contexto = Contexto("workspace", TENANT, "A-1")
    with pytest.raises(ErrorApi) as fallo:
        rol_para(matriz(), COMPARTIDAS[0], delegado_pequeno(), contexto)
    mensaje = str(fallo.value)
    assert "T-OPE" in mensaje and "T-REV" in mensaje
    assert "desempata" in mensaje


def test_una_superficie_inventada_es_error_y_no_una_eleccion(servicios: Servicios) -> None:
    contexto = Contexto("pantalla-que-no-existe", TENANT, "A-1")
    with pytest.raises(ErrorApi, match="no es ninguna"):
        rol_para(matriz(), COMPARTIDAS[0], delegado_pequeno(), contexto)


def test_la_pantalla_de_otro_perfil_no_desempata_a_su_favor() -> None:
    """Desde "pendiente de mi" (`T-RES`), una capacidad que `T-RES` no tiene sigue sin resolverse."""
    contexto = Contexto("pendiente_de_mi", TENANT, "A-1")
    with pytest.raises(ErrorApi, match="desempata"):
        rol_para(matriz(), COMPARTIDAS[1], delegado_pequeno(), contexto)


def test_en_la_consola_dos_perfiles_internos_tampoco_se_eligen_al_azar() -> None:
    """`CAP-66` y `CAP-67` las tienen los dos perfiles internos: la consola cambia de rol explicitamente."""
    interno = Principal("adm", ("ADM-MOD", "ADM-OPS"), None)
    with pytest.raises(ErrorApi, match="desempata"):
        rol_para(matriz(), "CAP-66", interno, Contexto("consola", None))
    assert rol_para(matriz(), "CAP-66", interno, Contexto("consola_gobierno", None)) == "ADM-MOD"
    assert rol_para(matriz(), "CAP-66", interno, Contexto("consola_tenants", None)) == "ADM-OPS"


# ---------------------------------------------------------------------------
# 3. El rol sale en la respuesta y se persiste en el log (A8)
# ---------------------------------------------------------------------------


def test_el_rol_de_la_respuesta_es_el_que_queda_en_el_evento(servicios: Servicios) -> None:
    peticion = Peticion(
        "CAP-09",
        delegado_pequeno(),
        Contexto("cola_revision", TENANT, "A-1"),
        {"texto": "falta la factura"},
    )
    respuesta = ejecutar(peticion, servicios=servicios)
    assert respuesta.rol == "T-REV"
    evento = servicios.repositorio.log("A-1").ultimo("SubsanacionSolicitada")
    assert evento is not None
    assert evento.actor.rol == "T-REV"
    assert evento.actor.id == "billy"
    assert evento.evento_id in respuesta.eventos


def test_la_misma_persona_desde_otra_pantalla_actua_con_otro_rol(servicios: Servicios) -> None:
    respuesta = ejecutar(
        Peticion(
            "CAP-09",
            delegado_pequeno(),
            Contexto("bandeja_actuaciones", TENANT, "A-1"),
            {"texto": "falta la factura"},
        ),
        servicios=servicios,
    )
    assert respuesta.rol == "T-OPE"
    assert servicios.repositorio.log("A-1").ultimo("SubsanacionSolicitada").actor.rol == "T-OPE"


def test_una_lectura_tambien_declara_el_rol_pero_no_escribe_nada(servicios: Servicios) -> None:
    servicios.repositorio.anadir("A-2", TENANT, actuacion=ActuacionMinima("A-2"))
    respuesta = leer(
        Peticion("CAP-14", delegado_pequeno(), Contexto("pendiente_de_mi", TENANT, "A-2")),
        servicios=servicios,
    )
    assert respuesta.rol in delegado_pequeno().perfiles
    assert respuesta.eventos == ()
    assert len(servicios.repositorio.log("A-2")) == 0


def test_el_log_rechaza_un_rol_que_no_puede_producir_ese_evento(servicios: Servicios) -> None:
    """El control de A8 esta en el log, no en el llamante: escribir el evento a mano no lo rodea."""
    from engine.eventos.canonico import ErrorEvento

    log = servicios.repositorio.log("A-1")
    with pytest.raises(ErrorEvento, match="no tiene ninguna capacidad que lo produzca"):
        log.anadir(
            "SpecActivada",
            {"spec": "X"},
            actor=Actor("humano", "billy", rol="T-REV"),
            ocurrido_en=INSTANTE,
        )


def test_el_log_rechaza_que_una_persona_selle_lo_que_produce_el_motor(servicios: Servicios) -> None:
    """`R-UI-02` en el ultimo sitio donde se puede defender: nadie fija un veredicto a mano."""
    from engine.eventos.canonico import ErrorEvento

    log = servicios.repositorio.log("A-1")
    with pytest.raises(ErrorEvento, match="ninguna capacidad"):
        log.anadir(
            "VeredictoEmitido",
            {"veredicto": "PREVALIDADO"},
            actor=Actor("humano", "billy", rol="T-REV"),
            ocurrido_en=INSTANTE,
        )
