"""Seguimiento post-envio (P9): lo que la plataforma devuelve, reflejado en el log (`ADR-010` C9).

Aqui empieza lo que pasa **despues** de la entrega: la plataforma (o el simulador) dice en que estado esta
una actuacion, o manda una tarea pendiente, y este modulo lo convierte en eventos del log. No decide nada
sobre el fondo: quien decide que le hace cada literal a nuestro ciclo es `estados_plataforma.yaml`, y quien
lo aplica es `engine/estados.py`.

`engine/` no puede importar de `salida/`, asi que el seguimiento trabaja sobre **datos planos**
(`EstadoRecibido`, `TareaRecibida`), no sobre los tipos del puerto. El puente que traduce los tipos del
puerto a estos es `salida/seguimiento.py` (C11), del lado de la salida.

Las cinco reglas de `ADR-010` §2, y donde se cumplen:

1. **Reconciliacion por `codigo_identificativo_propio`**, nunca por posicion ni por nombre de fichero
   (`docs/03` §10.5). Es `indexar` + `actuacion_de`. Una referencia que no cuadra con ninguna actuacion es
   `ErrorSeguimiento`: perder un estado en silencio es peor que fallar.
2. **Un estado se registra siempre, aunque no se entienda** (`docs/02` §5.6). Un literal que la tabla no
   conoce no se descarta: se refleja, la actuacion escala a `EN_REVISION_HUMANA` (lo hace `aplicar`) y el
   literal sale en `Sincronizacion.desconocidos`. **Este modulo no abre el hueco en `docs/HUECOS.md`: lo
   senala.**
3. **El contagio lo decide la tabla, no este modulo.** Que `REQUERIDO_GA` alcance al expediente entero esta
   en `estados_plataforma.yaml` (`alcance: expediente` + `origen_subsanacion: GA`); `sincronizar` solo llama
   a `engine.estados.propagar_requerimiento` con las actuaciones del expediente que tiene delante.
4. **Idempotencia**: sincronizar dos veces el mismo estado no duplica eventos ni vuelve a contagiar. El log
   es solo-anadir, pero no es un buzon que se llene de repeticiones. Dos eventos son el mismo si coinciden
   tipo, instante y payload codificado.
5. **Sin reloj propio.** El instante lo trae el dato recibido. Dos sincronizaciones iguales dan el mismo log,
   byte a byte (los `evento_id` y los hashes del log son deterministas).

Decisiones propias de esta pieza, todas para el ADR:

- **Nada se anade a un log que no lo admita.** Antes de escribir, el evento se prueba contra la proyeccion
  actual en un log de ensayo; si `aplicar` lo rechaza (p. ej. `ENVIADA_A_VERIFICACION` sin `FirmaRegistrada`
  previa), es `ErrorSeguimiento` y el log **no se toca**. El log es solo-anadir: un evento que lo deja sin
  proyectar lo envenena para siempre. Fallar aqui es ruidoso, no silencioso.
- **La referencia puede no ser el codigo propio.** El simulador compone `SIM-<codigo>-<huella>`
  (`TODO(API-01)`: las referencias oficiales no estan publicadas; ver `docs/HUECOS.md`). `actuacion_de`
  prueba primero la igualdad y solo despues busca el codigo **delimitado** dentro de la referencia; si
  encajan dos codigos, es `ErrorSeguimiento` por ambigua, nunca "el primero".
- **El contagio se persiste, no solo se devuelve.** A cada companera alcanzada se le anade un
  `RequerimientoRecibido` con `afectada_directamente: false`, para que su estado siga siendo una proyeccion
  de su log (`docs/03` §6) y no un dato que solo vive en la respuesta de esta llamada.
- **`alcance: grupo` (el `PDTE_RECTIFICACION_VER` del verificador con dictamen unico) no se propaga aqui**:
  la composicion de grupos es `R-GRP` (S4.1) y es decision de Billy. Se refleja en la actuacion referida.
- **Una actuacion sin `expediente_id` no contagia a nadie**: no hay expediente al que alcanzar. Se registra
  su estado y ya.

Este modulo no importa de `agentes/`, `salida/`, `generator/` ni `tests/`, no usa `eval` ni `float`, no mira
el reloj y no sabe que fichas existen.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType

from engine.estados import (
    NIVELES,
    ErrorEstado,
    Proyeccion,
    aplicar,
    propagar_requerimiento,
    proyectar,
    tabla_plataforma,
)
from engine.eventos.canonico import codificar, normalizar_instante
from engine.eventos.log import Actor, Evento, LogEventos

#: Quien escribe estos eventos: la plataforma habla, nosotros anotamos (`docs/03` §6.1).
CLASE_PLATAFORMA = "plataforma"
ACTOR_PLATAFORMA = Actor(CLASE_PLATAFORMA, "plataforma")

TIPO_ESTADO = "EstadoPlataformaRecibido"
TIPO_TAREA = "TareaPendienteRecibida"
TIPO_REQUERIMIENTO = "RequerimientoRecibido"


class ErrorSeguimiento(Exception):
    """Referencia que no reconcilia, log que falta o estado que el ciclo no admite."""


# ---------------------------------------------------------------------------
# Datos planos: lo que llega de fuera, sin tipos de `salida/`
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EstadoRecibido:
    """Un estado tal y como lo devuelve el destino (mismos campos que `salida.puerto.EstadoPlataforma`).

    `oficial` distingue los 8 confirmados de `docs/02` §5.1 de los provisionales de fases 2-4
    (`TODO(API-03)`: nombres nuestros; ver `docs/HUECOS.md`). Aqui se refleja, no se juzga.
    """

    referencia: str
    literal: str
    nivel: str
    oficial: bool
    instante: datetime
    motivos: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.referencia).strip():
            raise ErrorSeguimiento("un estado recibido necesita `referencia`: sin ella no reconcilia")
        if not str(self.literal).strip():
            raise ErrorSeguimiento(f"el estado de {self.referencia!r} llega sin literal")
        if self.nivel not in NIVELES:
            raise ErrorSeguimiento(f"nivel desconocido: {self.nivel!r}; los declarados son {list(NIVELES)}")
        _exigir_instante(self.instante, f"estado {self.literal!r} de {self.referencia!r}")
        if not isinstance(self.motivos, tuple):
            raise ErrorSeguimiento("`motivos` es una tupla de textos tal cual los emitio quien requiere")

    def a_payload(self) -> dict[str, object]:
        """El payload de `EstadoPlataformaRecibido`. `estado` es la clave que lee `engine.estados`."""
        return {
            "estado": self.literal,
            "referencia": self.referencia,
            "nivel": self.nivel,
            "oficial": self.oficial,
            "motivos": list(self.motivos),
        }


@dataclass(frozen=True)
class TareaRecibida:
    """Una tarea pendiente del tenant en el destino (`docs/02` §6.1, `docs/03` §10.5).

    `vence_en` solo se rellena si el destino lo da: la plataforma no publica plazos
    (`TODO(API-10)`: ver `docs/HUECOS.md`).
    """

    id: str
    tenant_id: str
    asunto: str
    instante: datetime
    referencia: str | None = None
    vence_en: date | None = None

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ErrorSeguimiento("una tarea recibida necesita `id`")
        if not str(self.tenant_id).strip():
            raise ErrorSeguimiento(f"la tarea {self.id!r} llega sin `tenant_id`")
        _exigir_instante(self.instante, f"tarea {self.id!r}")
        if self.vence_en is not None and not isinstance(self.vence_en, date):
            raise ErrorSeguimiento(f"la tarea {self.id!r}: `vence_en` es una fecha o nada")

    def a_payload(self) -> dict[str, object]:
        """El payload de `TareaPendienteRecibida`. No mueve el ciclo: se registra y se prioriza en S4."""
        return {
            "tarea_id": self.id,
            "tenant_id": self.tenant_id,
            "asunto": self.asunto,
            "referencia": self.referencia,
            "vence_en": self.vence_en,
        }


def _exigir_instante(valor: object, contexto: str) -> None:
    if not isinstance(valor, datetime) or valor.tzinfo is None or valor.utcoffset() is None:
        raise ErrorSeguimiento(
            f"{contexto}: `instante` necesita zona horaria explicita (UTC). El seguimiento no tiene reloj "
            "propio: el instante lo trae el dato recibido"
        )


@dataclass(frozen=True)
class Sincronizacion:
    """El resultado de una pasada de seguimiento (`ADR-010` §2).

    - `proyecciones`: el estado de cada actuacion **derivado de su log**, ya con lo recibido aplicado.
    - `eventos`: los eventos **nuevos**, en el orden en que se escribieron. Vacio = nada que anotar.
    - `desconocidos`: literales que la tabla no conoce. Cada uno es un hueco para `docs/HUECOS.md`.
    - `contagiadas`: expediente -> actuaciones que el requerimiento alcanza (incluida la senalada).
    """

    proyecciones: Mapping[str, Proyeccion]
    eventos: tuple[Evento, ...]
    desconocidos: tuple[str, ...]
    contagiadas: Mapping[str, tuple[str, ...]]


# ---------------------------------------------------------------------------
# Reconciliacion: por codigo identificativo propio, nunca por posicion
# ---------------------------------------------------------------------------


def _campo(actuacion: object, *nombres: str) -> str | None:
    """Un campo de una actuacion, venga como objeto del modelo canonico o como mapping."""
    for nombre in nombres:
        valor = actuacion.get(nombre) if isinstance(actuacion, Mapping) else getattr(actuacion, nombre, None)
        if valor is not None and str(valor).strip():
            return str(valor).strip()
    return None


def indexar(actuaciones: Iterable[object]) -> dict[str, str]:
    """`codigo_identificativo_propio` -> `actuacion_id`, que es por donde se reconcilia (`docs/03` §10.5).

    Acepta objetos del modelo canonico (`ActuacionCanonica`) o mappings equivalentes. Dos actuaciones
    distintas con el mismo codigo propio son `ErrorSeguimiento`: el codigo es la clave de reconciliacion y
    si se repite no hay reconciliacion posible.
    """
    indice: dict[str, str] = {}
    for actuacion in actuaciones:
        codigo = _campo(actuacion, "codigo_identificativo_propio")
        identificador = _campo(actuacion, "actuacion_id", "id")
        if codigo is None:
            raise ErrorSeguimiento(
                f"la actuacion {identificador or actuacion!r} no declara `codigo_identificativo_propio`: "
                "sin el no se puede reconciliar lo que devuelva la plataforma"
            )
        if identificador is None:
            raise ErrorSeguimiento(f"la actuacion de codigo propio {codigo!r} no declara `id`")
        previo = indice.get(codigo)
        if previo is not None and previo != identificador:
            raise ErrorSeguimiento(
                f"el codigo identificativo propio {codigo!r} lo declaran dos actuaciones ({previo} y "
                f"{identificador}); es la clave de reconciliacion y tiene que ser unico"
            )
        indice[codigo] = identificador
    return indice


def _delimitado(referencia: str, codigo: str) -> bool:
    """`codigo` aparece en `referencia` como segmento, no dentro de otra palabra (ver cabecera)."""
    inicio = referencia.find(codigo)
    while inicio >= 0:
        fin = inicio + len(codigo)
        antes = referencia[inicio - 1] if inicio > 0 else ""
        despues = referencia[fin] if fin < len(referencia) else ""
        if not antes.isalnum() and not despues.isalnum():
            return True
        inicio = referencia.find(codigo, inicio + 1)
    return False


def actuacion_de(recibido: EstadoRecibido | TareaRecibida, indice: Mapping[str, str]) -> str:
    """El `actuacion_id` de lo recibido, reconciliado por codigo propio. `ErrorSeguimiento` si no cuadra."""
    referencia = getattr(recibido, "referencia", None)
    if referencia is None or not str(referencia).strip():
        raise ErrorSeguimiento(
            f"lo recibido no trae referencia y no se puede reconciliar: {recibido!r}. Un estado sin "
            "referencia no se adivina por posicion (`docs/03` §10.5)"
        )
    referencia = str(referencia).strip()
    if referencia in indice:
        return indice[referencia]
    candidatos = sorted(codigo for codigo in indice if codigo and _delimitado(referencia, codigo))
    if len(candidatos) == 1:
        return indice[candidatos[0]]
    if candidatos:
        raise ErrorSeguimiento(
            f"la referencia {referencia!r} encaja con varios codigos identificativos propios "
            f"({candidatos}): es ambigua y no se elige uno"
        )
    raise ErrorSeguimiento(
        f"la referencia {referencia!r} no cuadra con ninguna actuacion conocida "
        f"({sorted(indice)}); un estado que no reconcilia no se descarta: se falla"
    )


# ---------------------------------------------------------------------------
# Registro de eventos: idempotente y sin envenenar el log
# ---------------------------------------------------------------------------


def _log_de(logs: Mapping[str, LogEventos], actuacion_id: str) -> LogEventos:
    log = logs.get(actuacion_id)
    if log is None:
        raise ErrorSeguimiento(
            f"no hay log de la actuacion {actuacion_id!r}: no se puede registrar lo que devuelve la "
            "plataforma sobre una actuacion que no conocemos"
        )
    return log


def _equivalente(
    log: LogEventos, tipo: str, payload: Mapping[str, object], instante: datetime
) -> Evento | None:
    """El mismo hecho ya anotado: mismo tipo, mismo instante y mismo payload codificado (idempotencia)."""
    codificado = codificar(dict(payload))
    momento = normalizar_instante(instante)
    for evento in log.por_tipo(tipo):
        if evento.ocurrido_en == momento and dict(evento.payload) == codificado:
            return evento
    return None


def anadir_una_vez(
    log: LogEventos,
    tipo: str,
    payload: Mapping[str, object],
    *,
    instante: datetime,
    actor: Actor,
) -> tuple[Evento, bool]:
    """Anade el evento si no estaba ya. Devuelve `(evento, es_nuevo)`. La comparte `requerimientos.py`.

    El evento se sella primero en un log de ensayo y se prueba contra la proyeccion actual: si la maquina de
    estados lo rechaza, el log real no se toca (ver cabecera). El ensayo produce el mismo sobre que el log
    real porque el hash solo depende del contenido y del hash previo, que son los mismos.
    """
    ya = _equivalente(log, tipo, payload, instante)
    if ya is not None:
        return ya, False
    ensayo = LogEventos(log.actuacion_id, log.eventos)
    candidato = ensayo.anadir(tipo, dict(payload), actor=actor, ocurrido_en=instante)
    try:
        aplicar(proyectar(log), candidato)
    except ErrorEstado as exc:
        raise ErrorSeguimiento(
            f"{tipo} sobre {log.actuacion_id}: el ciclo no lo admite y el log no se toca ({exc})"
        ) from exc
    return log.anadir(tipo, dict(payload), actor=actor, ocurrido_en=instante), True


def _actor_plataforma(actor: Actor | None) -> Actor:
    if actor is None:
        return ACTOR_PLATAFORMA
    actor = Actor.de(actor)
    if actor.clase != CLASE_PLATAFORMA:
        raise ErrorSeguimiento(
            f"lo que devuelve el destino lo escribe un actor {CLASE_PLATAFORMA!r}, no {actor.clase!r}: "
            "nosotros no fijamos el estado de plataforma, lo reflejamos (`docs/03` §7.1)"
        )
    return actor


def registrar_estado(log: LogEventos, recibido: EstadoRecibido, *, actor: Actor | None = None) -> Evento:
    """Anota un `EstadoPlataformaRecibido` (actor `plataforma`). Idempotente: devuelve el que ya estaba."""
    if not isinstance(recibido, EstadoRecibido):
        raise ErrorSeguimiento(f"se esperaba un EstadoRecibido y llego {type(recibido).__name__}")
    evento, _ = anadir_una_vez(
        log,
        TIPO_ESTADO,
        recibido.a_payload(),
        instante=recibido.instante,
        actor=_actor_plataforma(actor),
    )
    return evento


def registrar_tarea(log: LogEventos, tarea: TareaRecibida, *, actor: Actor | None = None) -> Evento:
    """Anota una `TareaPendienteRecibida` (actor `plataforma`). No mueve el ciclo; se prioriza en S4."""
    if not isinstance(tarea, TareaRecibida):
        raise ErrorSeguimiento(f"se esperaba una TareaRecibida y llego {type(tarea).__name__}")
    evento, _ = anadir_una_vez(
        log,
        TIPO_TAREA,
        tarea.a_payload(),
        instante=tarea.instante,
        actor=_actor_plataforma(actor),
    )
    return evento


# ---------------------------------------------------------------------------
# Sincronizacion
# ---------------------------------------------------------------------------


def _logs_por_actuacion(logs: Mapping[str, LogEventos] | Iterable[LogEventos]) -> dict[str, LogEventos]:
    if isinstance(logs, Mapping):
        indexados: dict[str, LogEventos] = {}
        for clave, log in logs.items():
            if not isinstance(log, LogEventos):
                raise ErrorSeguimiento(f"{clave!r}: se esperaba un LogEventos y llego {type(log).__name__}")
            if str(clave) != log.actuacion_id:
                raise ErrorSeguimiento(
                    f"el log indexado como {clave!r} es de la actuacion {log.actuacion_id!r}"
                )
            indexados[str(clave)] = log
        return indexados
    indexados = {}
    for log in logs:
        if not isinstance(log, LogEventos):
            raise ErrorSeguimiento(f"se esperaba un LogEventos y llego {type(log).__name__}")
        if log.actuacion_id in indexados:
            raise ErrorSeguimiento(f"hay dos logs de la actuacion {log.actuacion_id!r}")
        indexados[log.actuacion_id] = log
    return indexados


def _clase_de_orden(recibido: object) -> int:
    """A igual instante, primero los estados y despues las tareas: el estado es el que mueve el ciclo."""
    return 0 if isinstance(recibido, EstadoRecibido) else 1


def _contagiar(
    logs: Mapping[str, LogEventos],
    evento: Evento,
    recibido: EstadoRecibido,
    actuacion_id: str,
    actor: Actor,
) -> tuple[str | None, tuple[str, ...], list[Evento]]:
    """Propaga un requerimiento de GA/CN a todo el expediente (invariante 4 de `engine/estados.py`).

    Quien decide que este literal contagia es la tabla; quien decide a quien alcanza y con que
    `afectada_directamente` es `propagar_requerimiento`. Aqui solo se persiste el resultado en el log de
    cada companera, para que su estado siga siendo una proyeccion de su log.
    """
    proyecciones = {identificador: proyectar(log) for identificador, log in logs.items()}
    expediente_id = proyecciones[actuacion_id].expediente_id
    if expediente_id is None:
        return None, (), []
    miembros = [p for _, p in sorted(proyecciones.items()) if p.expediente_id == expediente_id]
    try:
        propagadas = propagar_requerimiento(miembros, evento, directas={actuacion_id})
    except ErrorEstado as exc:
        raise ErrorSeguimiento(
            f"el contagio del expediente {expediente_id!r} no es aplicable: {exc}"
        ) from exc
    fila = tabla_plataforma()[recibido.literal]
    nuevos: list[Evento] = []
    alcanzadas: list[str] = []
    for antes, despues in zip(miembros, propagadas, strict=True):
        if antes.terminal:
            continue  # `CERRADA` y `DESCARTADA` no se contagian: son terminales
        alcanzadas.append(despues.actuacion_id)
        if despues.actuacion_id == actuacion_id:
            continue  # la senalada ya lo tiene por su propio `EstadoPlataformaRecibido`
        payload = {
            "origen": fila.origen_subsanacion,
            "afectada_directamente": despues.afectada_directamente,
            "contagio": True,
            "literal_plataforma": recibido.literal,
            "expediente_id": expediente_id,
            "referencia": recibido.referencia,
            "actuacion_senalada": actuacion_id,
            "motivos": list(recibido.motivos),
        }
        companera = logs[despues.actuacion_id]
        anadido, es_nuevo = anadir_una_vez(
            companera, TIPO_REQUERIMIENTO, payload, instante=recibido.instante, actor=actor
        )
        if es_nuevo:
            nuevos.append(anadido)
    return expediente_id, tuple(alcanzadas), nuevos


def sincronizar(
    logs: Mapping[str, LogEventos] | Iterable[LogEventos],
    recibidos: Iterable[EstadoRecibido | TareaRecibida],
    *,
    indice: Mapping[str, str],
    actor: Actor | None = None,
) -> Sincronizacion:
    """Refleja en los logs lo que devuelve el destino y devuelve el estado resultante.

    Lo recibido se procesa por instante (y, a igual instante, estados antes que tareas, con el orden de
    entrada como ultimo desempate): el seguimiento no tiene reloj propio y dos pasadas iguales dan el mismo
    log. Un estado que ya estaba anotado no se duplica ni vuelve a contagiar.
    """
    por_actuacion = _logs_por_actuacion(logs)
    escritor = _actor_plataforma(actor)
    entradas = list(recibidos)
    for entrada in entradas:
        if not isinstance(entrada, EstadoRecibido | TareaRecibida):
            raise ErrorSeguimiento(
                f"el seguimiento consume EstadoRecibido y TareaRecibida, no {type(entrada).__name__}"
            )
    ordenados = sorted(
        enumerate(entradas),
        key=lambda par: (par[1].instante, _clase_de_orden(par[1]), par[0]),
    )
    eventos: list[Evento] = []
    desconocidos: list[str] = []
    contagiadas: dict[str, tuple[str, ...]] = {}
    for _, recibido in ordenados:
        actuacion_id = actuacion_de(recibido, indice)
        log = _log_de(por_actuacion, actuacion_id)
        if isinstance(recibido, TareaRecibida):
            evento, es_nuevo = anadir_una_vez(
                log, TIPO_TAREA, recibido.a_payload(), instante=recibido.instante, actor=escritor
            )
            if es_nuevo:
                eventos.append(evento)
            continue
        evento, es_nuevo = anadir_una_vez(
            log, TIPO_ESTADO, recibido.a_payload(), instante=recibido.instante, actor=escritor
        )
        if not es_nuevo:
            continue  # ya estaba: ni evento nuevo ni contagio repetido (regla 4)
        eventos.append(evento)
        fila = tabla_plataforma().get(recibido.literal)
        if fila is None:
            # Regla 2: se refleja y escala (lo hace `aplicar`); aqui solo se senala el hueco.
            if recibido.literal not in desconocidos:
                desconocidos.append(recibido.literal)
            continue
        if not fila.contagia_expediente:
            continue
        expediente_id, alcanzadas, nuevos = _contagiar(
            por_actuacion, evento, recibido, actuacion_id, escritor
        )
        eventos.extend(nuevos)
        if expediente_id is not None and alcanzadas:
            previas = contagiadas.get(expediente_id, ())
            contagiadas[expediente_id] = previas + tuple(a for a in alcanzadas if a not in previas)
    proyecciones = {identificador: proyectar(log) for identificador, log in sorted(por_actuacion.items())}
    return Sincronizacion(
        proyecciones=MappingProxyType(proyecciones),
        eventos=tuple(eventos),
        desconocidos=tuple(desconocidos),
        contagiadas=MappingProxyType(contagiadas),
    )


__all__ = [
    "ACTOR_PLATAFORMA",
    "CLASE_PLATAFORMA",
    "TIPO_ESTADO",
    "TIPO_REQUERIMIENTO",
    "TIPO_TAREA",
    "ErrorSeguimiento",
    "EstadoRecibido",
    "Sincronizacion",
    "TareaRecibida",
    "actuacion_de",
    "anadir_una_vez",
    "indexar",
    "registrar_estado",
    "registrar_tarea",
    "sincronizar",
]
