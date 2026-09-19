"""Tests del puente puerto -> nucleo (C11 de `ADR-010` §4): `salida/seguimiento.py`.

Lo que se protege aqui es la **direccion de las dependencias** y la honestidad del puente:

1. Traduce campo a campo y no interpreta: lo que decide que le hace un literal al ciclo es la tabla.
2. Una via que no puede consultar **levanta**, no devuelve vacio. Que el handoff no sepa el estado es
   informacion; una lista vacia se confundiria con "no hay nada pendiente", que es lo contrario.
3. No pregunta por lo que la plataforma no documenta: sin referencias no consulta estados, y sin tenant no
   consulta tareas. Preguntar "por todo" no es una operacion publicada (`TODO(API-01)`).
4. El circuito completo contra el simulador: entrega -> firma -> requerimiento de GA -> contagio a todo el
   expediente, con una sola actuacion senalada.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engine.estados import tabla_plataforma
from engine.eventos.log import LogEventos
from engine.seguimiento import ErrorSeguimiento, EstadoRecibido, TareaRecibida
from salida.handoff import AdaptadorHandoff
from salida.puerto import ErrorSalida, EstadoPlataforma, TareaPendiente
from salida.seguimiento import estado_recibido_de, sincronizar_desde, tarea_recibida_de

INSTANTE = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)


def literal_de(marca: str) -> str:
    """El literal que la tabla marca con ese atributo. Ni un estado escrito a mano en los tests."""
    filas = [f for f in tabla_plataforma().values() if getattr(f, marca, False)]
    assert len(filas) == 1, f"{marca}: {[f.literal for f in filas]}"
    return filas[0].literal


def literal_que_solo_se_refleja() -> str:
    """Un estado de actuacion que la tabla refleja sin mover el ciclo (`ciclo: null`).

    Es lo que devuelve una plataforma sobre las companeras que no ha requerido. Derivado de la tabla: si
    manana cambia cual es, este test sigue valiendo.
    """
    filas = [f for f in tabla_plataforma().values() if f.nivel == "actuacion" and f.ciclo is None]
    assert filas, "la tabla no declara ningun estado de actuacion que solo se refleje"
    return filas[0].literal


def literal_que_contagia(origen: str) -> str:
    filas = [
        f for f in tabla_plataforma().values() if f.origen_subsanacion == origen and f.contagia_expediente
    ]
    assert filas, f"la tabla no declara ningun literal que contagie con origen {origen}"
    return filas[0].literal


# ---------------------------------------------------------------------------
# 1. Traduce campo a campo, sin criterio propio
# ---------------------------------------------------------------------------


def test_un_estado_del_puerto_se_traduce_campo_a_campo() -> None:
    literal = literal_de("validacion_automatica")
    estado = EstadoPlataforma(
        referencia="SIM-COD-1-abc",
        literal=literal,
        nivel="actuacion",
        oficial=True,
        instante=INSTANTE,
        motivos=("uno", "dos"),
    )
    recibido = estado_recibido_de(estado)
    assert isinstance(recibido, EstadoRecibido)
    assert recibido.referencia == estado.referencia
    assert (recibido.literal, recibido.nivel) == (literal, "actuacion")
    assert (recibido.oficial, recibido.instante, recibido.motivos) == (True, INSTANTE, ("uno", "dos"))


def test_una_tarea_del_puerto_se_traduce_campo_a_campo() -> None:
    tarea = TareaPendiente(
        id="T-1", tenant_id="TEN-1", asunto="subsanar", instante=INSTANTE, referencia="SIM-COD-1-abc"
    )
    recibida = tarea_recibida_de(tarea)
    assert isinstance(recibida, TareaRecibida)
    assert (recibida.id, recibida.tenant_id, recibida.asunto) == ("T-1", "TEN-1", "subsanar")
    assert recibida.vence_en is None  # TODO(API-10): la plataforma no publica plazos


@pytest.mark.parametrize(
    ("funcion", "basura"), [(estado_recibido_de, "no soy un estado"), (tarea_recibida_de, 42)]
)
def test_el_puente_no_traga_cualquier_cosa(funcion, basura) -> None:
    with pytest.raises(ErrorSalida):
        funcion(basura)


# ---------------------------------------------------------------------------
# 2. Una via que no consulta levanta; no devuelve vacio
# ---------------------------------------------------------------------------


def test_el_handoff_no_consulta_y_eso_sube_tal_cual() -> None:
    """Que el tenant tenga un requerimiento sin leer no puede parecerse a 'no hay tareas'."""
    log = LogEventos("ACT-1")
    with pytest.raises(ErrorSalida, match="no consulta la plataforma"):
        sincronizar_desde(
            AdaptadorHandoff(), logs={"ACT-1": log}, indice={"COD-1": "ACT-1"}, referencias=("COD-1",)
        )


def test_un_objeto_que_no_es_un_puerto_se_rechaza_antes_de_preguntar() -> None:
    with pytest.raises(ErrorSalida, match="no cumple el puerto de salida"):
        sincronizar_desde(object(), logs={}, indice={})


# ---------------------------------------------------------------------------
# 3. No pregunta por lo que la plataforma no documenta
# ---------------------------------------------------------------------------


class _PuertoEspia:
    """Un puerto que solo cuenta cuantas veces le preguntan."""

    nombre = "espia"

    def __init__(self) -> None:
        self.estados: list[str] = []
        self.tareas: list[str] = []

    def construir(self, actuacion, mapeo, *, raiz=None, log=None):  # pragma: no cover - no se usa
        raise ErrorSalida("el espia no construye")

    def entregar(self, paquete, *, log=None):  # pragma: no cover - no se usa
        raise ErrorSalida("el espia no entrega")

    def consultar_estado(self, referencia: str) -> EstadoPlataforma:
        self.estados.append(referencia)
        return EstadoPlataforma(
            referencia=referencia,
            literal=literal_de("validacion_automatica"),
            nivel="actuacion",
            oficial=True,
            instante=INSTANTE,
        )

    def consultar_tareas(self, tenant_id: str) -> tuple[TareaPendiente, ...]:
        self.tareas.append(tenant_id)
        return ()


def test_sin_referencias_y_sin_tenant_no_se_pregunta_nada() -> None:
    espia = _PuertoEspia()
    sincronizacion = sincronizar_desde(espia, logs={}, indice={})
    assert (espia.estados, espia.tareas) == ([], [])
    assert sincronizacion.eventos == ()


def test_las_tareas_solo_se_piden_con_tenant() -> None:
    espia = _PuertoEspia()
    sincronizar_desde(espia, logs={}, indice={}, tenant_id="TEN-1")
    assert espia.tareas == ["TEN-1"]


def test_una_referencia_que_no_reconcilia_es_error_y_no_se_pierde() -> None:
    espia = _PuertoEspia()
    with pytest.raises(ErrorSeguimiento):
        sincronizar_desde(espia, logs={}, indice={"COD-9": "ACT-9"}, referencias=("SIM-OTRO-xyz",))


# ---------------------------------------------------------------------------
# 4. El circuito: requerimiento de GA -> contagio de todo el expediente
# ---------------------------------------------------------------------------


def log_firmado(actuacion_id: str) -> LogEventos:
    """Una actuacion que llego a la plataforma: prevalidada, revisada, entregada y firmada."""
    log = LogEventos(actuacion_id)
    motor = ("motor", "engine@test")
    # `T-REV` aprueba la revision (CAP-10) y `T-RES` firma (CAP-22): son dos actos y dos perfiles.
    revisor = ("humano", "revisor@tenant", "T-REV")
    responsable = ("humano", "responsable@tenant", "T-RES")
    log.anadir("ActuacionAbierta", {"expediente_id": "EXP-1"}, actor=motor)
    log.anadir("DocumentoRegistrado", {}, actor=motor)
    log.anadir("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, actor=motor)
    log.anadir("ObservacionRegistrada", {"origen": "revision_humana", "texto": "revisado"}, actor=revisor)
    log.anadir("PayloadConstruido", {}, actor=motor)
    log.anadir("EntregadoADelegado", {}, actor=motor)
    log.anadir("FirmaRegistrada", {}, actor=responsable)
    log.anadir("ExpedientePropuesto", {"expediente_id": "EXP-1"}, actor=motor)
    return log


class _PuertoRequerido(_PuertoEspia):
    """Un destino que devuelve un requerimiento de GA sobre una referencia concreta."""

    def __init__(self, referencia_requerida: str) -> None:
        super().__init__()
        self._requerida = referencia_requerida

    def consultar_estado(self, referencia: str) -> EstadoPlataforma:
        self.estados.append(referencia)
        requerido = referencia == self._requerida
        return EstadoPlataforma(
            referencia=referencia,
            literal=literal_que_contagia("GA") if requerido else literal_que_solo_se_refleja(),
            nivel="expediente" if requerido else "actuacion",
            oficial=not requerido,
            instante=INSTANTE,
            motivos=("falta el informe de la instalacion",) if requerido else (),
        )


def test_un_requerimiento_de_ga_bloquea_el_expediente_completo() -> None:
    """El riesgo de contagio, de extremo a extremo por el puente: tres actuaciones, una señalada."""
    logs = {identificador: log_firmado(identificador) for identificador in ("ACT-1", "ACT-2", "ACT-3")}
    indice = {f"COD-{n}": f"ACT-{n}" for n in (1, 2, 3)}
    puerto = _PuertoRequerido("COD-2")

    sincronizacion = sincronizar_desde(
        puerto, logs=logs, indice=indice, referencias=("COD-1", "COD-2", "COD-3")
    )

    proyecciones = sincronizacion.proyecciones
    assert all(p.estado_ciclo == "PENDIENTE_SUBSANACION" for p in proyecciones.values()), {
        k: v.estado_ciclo for k, v in proyecciones.items()
    }
    senaladas = [k for k, v in proyecciones.items() if v.afectada_directamente]
    assert senaladas == ["ACT-2"], "solo la actuacion requerida esta señalada; las demas son contagio"
    assert all(p.origen_subsanacion == "GA" for p in proyecciones.values())
    assert sincronizacion.contagiadas["EXP-1"] == ("ACT-1", "ACT-2", "ACT-3")
    for log in logs.values():
        log.verificar()  # la cadena de hashes sigue entera despues del contagio


def test_sincronizar_dos_veces_no_contagia_dos_veces() -> None:
    logs = {identificador: log_firmado(identificador) for identificador in ("ACT-1", "ACT-2", "ACT-3")}
    indice = {f"COD-{n}": f"ACT-{n}" for n in (1, 2, 3)}
    puerto = _PuertoRequerido("COD-2")
    referencias = ("COD-1", "COD-2", "COD-3")

    primera = sincronizar_desde(puerto, logs=logs, indice=indice, referencias=referencias)
    longitudes = {k: len(v) for k, v in logs.items()}
    segunda = sincronizar_desde(puerto, logs=logs, indice=indice, referencias=referencias)

    assert primera.eventos, "la primera pasada tiene que anotar algo"
    assert segunda.eventos == (), "la segunda pasada no anota nada: el log no es un buzon de repeticiones"
    assert {k: len(v) for k, v in logs.items()} == longitudes
