"""Sobre de evento y log solo-anadir con hash encadenado (`docs/03` §6, `ADR-004` C2).

El log es la fuente de verdad del ciclo: el estado de una actuacion es una proyeccion del log, y cualquier
actuacion pasada se puede volver a ejecutar contra una spec nueva (`engine.eventos.replay`).

Reglas que este modulo hace cumplir:

- **Solo anadir.** No hay API publica para editar ni borrar: `eventos` es una tupla y `anadir` es la unica
  escritura. Una correccion es un evento nuevo (`DatoCorregidoPorHumano`), nunca un evento cambiado.
- **Cadena de hash.** `hash = sha256(hash_previo + json_canonico(evento sin hash))`; el `hash_previo` del
  primero es la cadena vacia. `verificar()` recorre la cadena y se detiene en el **primer** eslabon roto
  diciendo cual es.
- **Secuencia densa y creciente desde 1**, y un solo `actuacion_id` por log.
- **`ocurrido_en` en UTC con zona explicita.** Un instante naive es `ErrorEvento` (`ADR-003` H-08).
- **Catalogo cerrado** (`catalogo.TIPOS`) y **clases de actor cerradas** (`catalogo.CLASES_ACTOR`).
- **Eventos que exigen actor humano** (`TIPOS_SOLO_HUMANO`): con actor `motor` o `agente`, `ErrorEvento`.
  Ninguna firma, ninguna correccion humana y ningun desistimiento los puede escribir una maquina.
- **`actor.rol` obligatorio en actor humano** (A8, `ADR-006`, S3.1b). Una persona actua siempre **con un
  perfil**, y el perfil ejercido es parte de la traza: sin el, la auditoria dice quien pulso pero no con que
  autoridad. No hay rol por defecto y no se infiere ninguno: un rol inventado en el log es peor que ninguno,
  porque parece trazabilidad. La restriccion es **de escritura**, igual que la del catalogo de tipos: un log
  antiguo con actores humanos sin rol se lee (`desde_jsonl`) y se verifica (`verificar`) sin tocarlo, porque
  el log es solo-anadir y no se reescribe. Lo que no se puede es sellar hoy un evento humano sin rol.
- **Eventos de actor `agente`**: el payload trae `modelo`, `version_prompt`, `coste` y `latencia`
  (`docs/03` §11.2 punto 6). Hoy no hay agentes; el contrato se fija ya.
- **Autorizacion por capacidad, como gancho** (S3.1b). `LogEventos(autorizador=...)` recibe una funcion
  `(tipo, actor) -> None` que levanta `ErrorEvento` si ese rol no puede producir ese tipo. El log **no sabe**
  que perfil concede que capacidad: esa matriz es configuracion (`engine/capacidades.yaml`) y no se copia
  aqui. Sin autorizador el log valida todo lo demas igual; con el, un `ADM-OPS` no puede sellar una
  `SpecActivada`. Quien lo concede lo dice `engine/capacidades.yaml`, nunca este modulo.

  El otro extremo ya existe: `engine.capacidades.perfiles_que_pueden_emitir(tipo)`. Enchufarlos es esto, y
  va donde se compone el sistema, **no aqui** (el log no puede depender de un fichero de configuracion
  para sellar un evento, ni `engine/eventos/` de `engine/capacidades.py`):

      def autorizar(tipo, actor):
          if actor.rol is not None and actor.rol not in perfiles_que_pueden_emitir(tipo):
              raise ErrorEvento(...)
      log = LogEventos(actuacion_id, autorizador=autorizar)

Dos decisiones propias:

- **`evento_id` determinista**: `uuid5` sobre la forma canonica del sobre (sin hash ni `hash_previo`). Es un
  UUID como cadena, como pide el contrato, pero dos ejecuciones identicas del mismo motor producen el mismo
  log byte a byte, lo que convierte el log en artefacto comparable (F-22, prueba de regresion).
- **El payload se guarda codificado** (`canonico.codificar`): JSON puro con etiquetas de tipo. Asi el
  `a_jsonl` → `desde_jsonl` devuelve el mismo log (mismos hashes) y el replay recupera `Decimal` y `date`
  sin adivinar tipos.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from engine.eventos.canonico import (
    ErrorEvento,
    ahora_utc,
    calcular_hash,
    codificar,
    decodificar,
    instante_desde_texto,
    json_canonico,
    normalizar_instante,
    texto_instante,
)
from engine.eventos.catalogo import (
    ACTORES_ADMITIDOS,
    CAMPOS_AGENTE,
    CLASES_ACTOR,
    CONFIRMACIONES_SOLO_HUMANO,
    TIPOS,
    TIPOS_SOLO_HUMANO,
)

#: Espacio de nombres de los `evento_id` deterministas (ver cabecera). No cambia nunca.
NAMESPACE_EVENTOS = uuid.UUID("6f6a1a1e-1f0a-5c2e-9a4b-0f1d2c3b4a59")

#: Clase de actor que exigen los eventos de `TIPOS_SOLO_HUMANO`.
CLASE_HUMANO = "humano"
CLASE_AGENTE = "agente"

#: Hash previo del primer evento de un log.
HASH_INICIAL = ""


@dataclass(frozen=True)
class Actor:
    """Quien provoca el evento: `clase` en `CLASES_ACTOR`, `id` la persona o el componente, `rol` el perfil.

    `rol` es el codigo de perfil de `ADR-006` (`T-REV`, `ADM-MOD`…) **ejercido en este acto**, no todos los
    que el usuario acumula: un delegado pequeno junta `T-RES`, `T-OPE` y `T-REV`, y la auditoria necesita
    saber con cual aprobo. Aqui no se valida contra ningun catalogo de perfiles a proposito: los perfiles
    son configuracion (`engine/capacidades.yaml`) y duplicarlos en el nucleo seria el `if perfil == ...` que
    la regla de oro 4 prohibe. Quien comprueba que el rol existe y que puede producir el evento es el
    `autorizador` de `LogEventos`.

    **`rol` no se exige aqui sino al anadir** (`_validar_actor`). Construir un `Actor("humano", "x")` sin rol
    es legitimo: es lo que hace `Evento.desde_dict` al leer un log antiguo, que se lee y se verifica igual.
    """

    clase: str
    id: str
    rol: str | None = None

    def __post_init__(self) -> None:
        if self.clase not in CLASES_ACTOR:
            raise ErrorEvento(f"clase de actor desconocida {self.clase!r}; las validas son {CLASES_ACTOR}")
        if not isinstance(self.id, str) or not self.id.strip():
            raise ErrorEvento(f"el actor {self.clase!r} necesita un `id` no vacio")
        if self.rol is not None and (not isinstance(self.rol, str) or not self.rol.strip()):
            raise ErrorEvento(
                f"el `rol` del actor {self.id!r} es un codigo de perfil o `None`, no una cadena vacia"
            )

    def a_dict(self) -> dict[str, str]:
        """El actor como va al sobre. **`rol` solo aparece cuando lo hay**: asi un evento sellado antes de
        A8 conserva su hash byte a byte y `verificar()` sigue pasando sobre un log antiguo."""
        datos = {"clase": self.clase, "id": self.id}
        if self.rol is not None:
            datos["rol"] = self.rol
        return datos

    @classmethod
    def de(cls, valor: object) -> Actor:
        """Acepta un `Actor`, un mapping `{clase, id, rol?}` o una pareja `(clase, id)` / terna con rol."""
        if isinstance(valor, Actor):
            return valor
        if isinstance(valor, Mapping):
            rol = valor.get("rol")
            return cls(
                clase=str(valor.get("clase")),
                id=str(valor.get("id")),
                rol=None if rol is None else str(rol),
            )
        if isinstance(valor, tuple) and len(valor) in (2, 3):
            rol = valor[2] if len(valor) == 3 else None
            return cls(clase=str(valor[0]), id=str(valor[1]), rol=None if rol is None else str(rol))
        raise ErrorEvento(f"no es un actor: {valor!r}")


@dataclass(frozen=True)
class Evento:
    """El sobre de `docs/03` §6.1. Inmutable: una vez sellado, solo se lee."""

    evento_id: str
    actuacion_id: str
    secuencia: int
    tipo: str
    ocurrido_en: datetime
    actor: Actor
    payload: Mapping[str, object]
    hash_previo: str
    hash: str

    @property
    def datos(self) -> dict[str, object]:
        """El payload con sus tipos (`Decimal`, `date`, `datetime`) recuperados."""
        return dict(decodificar(dict(self.payload)))  # type: ignore[arg-type]

    def sobre_sin_hash(self) -> dict[str, object]:
        """Lo que se firma: el sobre entero menos `hash`. Es lo que recalcula `verificar`."""
        return {
            "evento_id": self.evento_id,
            "actuacion_id": self.actuacion_id,
            "secuencia": self.secuencia,
            "tipo": self.tipo,
            "ocurrido_en": texto_instante(self.ocurrido_en),
            "actor": self.actor.a_dict(),
            "payload": dict(self.payload),
            "hash_previo": self.hash_previo,
        }

    def a_dict(self) -> dict[str, object]:
        return {**self.sobre_sin_hash(), "hash": self.hash}

    @classmethod
    def desde_dict(cls, datos: Mapping[str, object]) -> Evento:
        """Lee un sobre tal cual se escribio (sin recalcular nada: eso es trabajo de `verificar`)."""
        if not isinstance(datos, Mapping):
            raise ErrorEvento(f"un evento es un Mapping, no {type(datos).__name__}")
        faltan = [c for c in ("evento_id", "actuacion_id", "secuencia", "tipo", "hash") if c not in datos]
        if faltan:
            raise ErrorEvento(f"sobre de evento incompleto: faltan {faltan}")
        payload = datos.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise ErrorEvento("el `payload` de un evento es un objeto JSON")
        secuencia = datos["secuencia"]
        if not isinstance(secuencia, int) or isinstance(secuencia, bool):
            raise ErrorEvento(f"`secuencia` debe ser entero, no {type(secuencia).__name__}")
        return cls(
            evento_id=str(datos["evento_id"]),
            actuacion_id=str(datos["actuacion_id"]),
            secuencia=secuencia,
            tipo=str(datos["tipo"]),
            ocurrido_en=instante_desde_texto(datos.get("ocurrido_en")),
            actor=Actor.de(datos.get("actor")),
            payload=MappingProxyType(dict(payload)),
            hash_previo=str(datos.get("hash_previo", HASH_INICIAL)),
            hash=str(datos["hash"]),
        )


def _validar_tipo(tipo: object) -> str:
    if not isinstance(tipo, str) or tipo not in TIPOS:
        raise ErrorEvento(
            f"tipo de evento no declarado: {tipo!r}. El catalogo es cerrado (engine.eventos.catalogo)"
        )
    return tipo


def _validar_actor(tipo: str, actor: Actor, payload: Mapping[str, object]) -> None:
    admitidas = ACTORES_ADMITIDOS.get(tipo)
    if admitidas is not None and actor.clase not in admitidas:
        raise ErrorEvento(
            f"{tipo} solo admite actor de clase {list(admitidas)} y llego {actor.clase!r}: ningun "
            "componente automatico nuestro reabre una actuacion (`R-REQ-02`, `ADR-010`)"
        )
    exige_humano = tipo in TIPOS_SOLO_HUMANO
    marca = CONFIRMACIONES_SOLO_HUMANO.get(tipo)
    if marca is not None and payload.get(marca) is True:
        exige_humano = True
    if exige_humano and actor.clase != CLASE_HUMANO:
        raise ErrorEvento(
            f"{tipo} solo es valido con actor humano (`docs/03` §6.1 y §7.3); llego actor {actor.clase!r}"
        )
    if actor.clase == CLASE_HUMANO and actor.rol is None:
        raise ErrorEvento(
            f"{tipo}: un actor humano escribe siempre con un perfil, y {actor.id!r} no declara `rol` "
            "(A8, `ADR-006`; `docs/06` S3.1b). No hay rol por defecto: un rol inventado en el log parece "
            "trazabilidad y no lo es. Los codigos de perfil estan en `engine/capacidades.yaml`"
        )
    if actor.clase == CLASE_AGENTE:
        faltan = [campo for campo in CAMPOS_AGENTE if campo not in payload]
        if faltan:
            raise ErrorEvento(
                f"{tipo}: un evento de agente declara {list(CAMPOS_AGENTE)} en el payload "
                f"(`docs/03` §11.2 punto 6); faltan {faltan}"
            )


#: Firma del gancho de autorizacion (ver cabecera): `(tipo, actor) -> None`, `ErrorEvento` si se deniega.
Autorizador = Callable[[str, Actor], None]


class LogEventos:
    """Log solo-anadir de una actuacion: en memoria, con serializacion JSONL (ver cabecera)."""

    def __init__(
        self,
        actuacion_id: str | None = None,
        eventos: Iterable[Evento] = (),
        *,
        autorizador: Autorizador | None = None,
    ) -> None:
        adoptados = list(eventos)
        if actuacion_id is None:
            if not adoptados:
                raise ErrorEvento("un log necesita `actuacion_id` (o al menos un evento del que sacarlo)")
            actuacion_id = adoptados[0].actuacion_id
        if not str(actuacion_id).strip():
            raise ErrorEvento("`actuacion_id` no puede estar vacio")
        self.actuacion_id = str(actuacion_id)
        self._eventos = adoptados
        # ENGANCHE S3.1b: lo instala quien compone el sistema, con la matriz ya cargada
        # (`engine/capacidades.py` sobre `engine/capacidades.yaml`). El log no conoce ningun perfil.
        # `desde_jsonl` no lo propaga a proposito: leer un log no vuelve a autorizar lo ya escrito.
        self.autorizador = autorizador

    # -- lectura ---------------------------------------------------------------------------------

    @property
    def eventos(self) -> tuple[Evento, ...]:
        """Los eventos en orden de secuencia. Es una tupla: el log no se edita desde fuera."""
        return tuple(self._eventos)

    @property
    def hash_actual(self) -> str:
        """Hash del ultimo evento; cadena vacia si el log esta vacio (es el `hash_previo` del siguiente)."""
        return self._eventos[-1].hash if self._eventos else HASH_INICIAL

    def __len__(self) -> int:
        return len(self._eventos)

    def __iter__(self) -> Iterator[Evento]:
        return iter(tuple(self._eventos))

    def por_tipo(self, tipo: str) -> tuple[Evento, ...]:
        """Los eventos de ese tipo, en orden. No valida el tipo: leer un log antiguo nunca falla."""
        return tuple(e for e in self._eventos if e.tipo == tipo)

    def ultimo(self, tipo: str) -> Evento | None:
        """El ultimo evento de ese tipo, o `None`."""
        for evento in reversed(self._eventos):
            if evento.tipo == tipo:
                return evento
        return None

    # -- escritura (la unica) --------------------------------------------------------------------

    def anadir(
        self,
        tipo: str,
        payload: Mapping[str, object] | None = None,
        *,
        actor: Actor | Mapping[str, object] | tuple[str, str],
        ocurrido_en: datetime | None = None,
    ) -> Evento:
        """Sella un evento al final del log: valida, codifica el payload y encadena el hash."""
        tipo = _validar_tipo(tipo)
        actor = Actor.de(actor)
        if payload is None:
            payload = {}
        if not isinstance(payload, Mapping):
            raise ErrorEvento(f"el payload de {tipo} debe ser un Mapping, no {type(payload).__name__}")
        _validar_actor(tipo, actor, payload)
        if self.autorizador is not None:
            self.autorizador(tipo, actor)
        codificado = codificar(dict(payload))
        if not isinstance(codificado, dict):  # pragma: no cover - codificar(dict) siempre da dict
            raise ErrorEvento(f"payload no codificable de {tipo}")
        instante = normalizar_instante(ocurrido_en) if ocurrido_en is not None else ahora_utc()

        base: dict[str, object] = {
            "actuacion_id": self.actuacion_id,
            "secuencia": len(self._eventos) + 1,
            "tipo": tipo,
            "ocurrido_en": texto_instante(instante),
            "actor": actor.a_dict(),
            "payload": codificado,
        }
        hash_previo = self.hash_actual
        sobre = {
            "evento_id": str(uuid.uuid5(NAMESPACE_EVENTOS, json_canonico(base))),
            **base,
            "hash_previo": hash_previo,
        }
        evento = Evento(
            evento_id=str(sobre["evento_id"]),
            actuacion_id=self.actuacion_id,
            secuencia=len(self._eventos) + 1,
            tipo=tipo,
            ocurrido_en=instante,
            actor=actor,
            payload=MappingProxyType(codificado),
            hash_previo=hash_previo,
            hash=calcular_hash(sobre, hash_previo),
        )
        self._eventos.append(evento)
        return evento

    # -- integridad ------------------------------------------------------------------------------

    def verificar(self) -> None:
        """Recorre la cadena; `ErrorEvento` en el **primer** eslabon roto, diciendo cual (`docs/03` §9)."""
        previo = HASH_INICIAL
        for posicion, evento in enumerate(self._eventos, start=1):
            donde = f"eslabon {posicion} (evento {evento.evento_id}, tipo {evento.tipo})"
            if evento.secuencia != posicion:
                raise ErrorEvento(
                    f"{donde}: la secuencia deberia ser {posicion} y es {evento.secuencia}; "
                    "la secuencia es densa y creciente desde 1"
                )
            if evento.actuacion_id != self.actuacion_id:
                raise ErrorEvento(
                    f"{donde}: es de la actuacion {evento.actuacion_id!r} y el log es de "
                    f"{self.actuacion_id!r}"
                )
            if evento.hash_previo != previo:
                raise ErrorEvento(
                    f"{donde}: `hash_previo` {evento.hash_previo[:12]!r} no encadena con el hash del "
                    f"evento anterior {previo[:12]!r}"
                )
            esperado = calcular_hash(evento.sobre_sin_hash(), evento.hash_previo)
            if esperado != evento.hash:
                raise ErrorEvento(
                    f"{donde}: el hash no corresponde a su contenido (esperado {esperado[:12]}…, "
                    f"guardado {evento.hash[:12]}…); el evento se altero despues de sellarse"
                )
            previo = evento.hash

    # -- serializacion ---------------------------------------------------------------------------

    def a_jsonl(self) -> str:
        """Una linea por evento, en orden de secuencia, cada una en forma canonica."""
        return "".join(f"{json_canonico(evento.a_dict())}\n" for evento in self._eventos)

    @classmethod
    def desde_jsonl(cls, texto: str, *, actuacion_id: str | None = None) -> LogEventos:
        """Inverso de `a_jsonl`. No recalcula hashes: para eso esta `verificar()`."""
        eventos: list[Evento] = []
        for numero, linea in enumerate(texto.splitlines(), start=1):
            if not linea.strip():
                continue
            try:
                datos = json.loads(linea)
            except json.JSONDecodeError as exc:
                raise ErrorEvento(f"linea {numero} del JSONL ilegible: {exc}") from exc
            eventos.append(Evento.desde_dict(datos))
        return cls(actuacion_id=actuacion_id, eventos=eventos)


__all__ = [
    "CLASE_AGENTE",
    "CLASE_HUMANO",
    "HASH_INICIAL",
    "NAMESPACE_EVENTOS",
    "Actor",
    "Autorizador",
    "Evento",
    "LogEventos",
]
