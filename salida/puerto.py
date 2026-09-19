"""Puerto de salida (S5): las cuatro operaciones por las que una actuacion sale del sistema.

`docs/03` §10.1, contrato C4 de `ADR-009`. Aqui **no hay implementacion**: hay tipos y un protocolo. Quien
entrega de verdad es un adaptador (`salida/handoff/`, `salida/simulador/`, y `salida/api_oficial/` cuando
exista diccionario). Tener el contrato aparte es lo que permite que P9 (seguimiento) se escriba una sola vez y
funcione contra el simulador hoy y contra la plataforma manana.

Cinco decisiones de `ADR-009` §2 que este modulo fija y que no se reabren en un adaptador:

1. **`Paquete.veredicto` se transporta, no se juzga.** El puerto describe, igual que el manifiesto
   (`ADR-008` §4 bis punto 7). Quien decide si una actuacion puede salir es `engine/estados.py`.
2. **El estado de ciclo lo mueve el log, no el adaptador.** `construir` y `entregar` emiten eventos del
   catalogo P8 **solo si se les pasa un `log`**. Sin log entregan igual y no hay transicion: un adaptador no
   es una maquina de estados paralela. Con log, entregar algo que no sea `PREVALIDADO` y revisado por un
   humano es `ErrorEstado` de la maquina (invariante 2), no una comprobacion duplicada aqui.
3. **`hash_paquete` es el `hash_manifiesto`**: no se inventa una segunda huella del mismo contenido.
4. **Una operacion puede negarse.** El handoff no consulta la plataforma: levanta `ErrorSalida` diciendo que
   por esa via el estado lo trae el tenant. Es mas honesto que una lista vacia, que se confunde con "no hay".
5. **`Acuse.via` alimenta `Proyeccion.via_entrega`** con los mismos literales que
   `engine.estados.VIAS_ENTREGA`.

**Nada de aqui pretende ser un campo de la API oficial.** Estos tipos son nuestros; el conector de S3.7
traducira, no heredara. Lo desconocido lleva su `TODO(API-xx)` con fila en `docs/HUECOS.md`.

`salida/` puede importar de `engine/`; `engine/` nunca importa de `salida/` (test desde la Fase 0).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from salida.constructor.manifiesto import Manifiesto

#: Destinos de un mapeo (`mapping/<FICHA>.<destino>.yaml`). `api` no tiene adaptador hoy:
#: TODO(API-01): ver docs/HUECOS.md
DESTINOS = ("handoff", "api")

#: Vias de entrega. Las dos primeras son, literalmente, las de `engine.estados.VIAS_ENTREGA`; `simulador`
#: es nuestra y nunca se escribe en un evento de entrega del log (el simulador no entrega a nadie real).
VIAS = ("handoff", "API", "simulador")

#: Niveles de estado de plataforma (`docs/02` §5.1 y §5.2). Los de expediente son nombres NUESTROS:
#: TODO(API-03): ver docs/HUECOS.md
NIVELES = ("actuacion", "expediente")


class ErrorSalida(Exception):
    """No se puede construir, entregar o consultar: falta un dato, el destino no lo admite o no cuadra."""


@dataclass(frozen=True)
class Adjunto:
    """Un fichero que viaja con el paquete, tal y como lo declaro el manifiesto de S3.3.

    `es_parte` distingue las partes de un PDF combinado: no existen en disco (`ADR-008` §4 bis punto 1), asi
    que no se copian como fichero; se listan bajo su combinado.
    """

    ruta: str
    tipo: str | None
    sha256: str
    bytes: int
    origen: str | None = None
    es_parte: bool = False

    def a_dict(self) -> dict[str, object]:
        return {
            "ruta": self.ruta,
            "tipo": self.tipo,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "origen": self.origen,
            "es_parte": self.es_parte,
        }


@dataclass(frozen=True)
class Paquete:
    """Lo que sale: payload (cabecera + detalle), manifiesto y adjuntos (`docs/03` §10.1).

    El `payload` es **nuestro** formato, el que produce el mapeo declarativo. El de la API oficial no existe
    todavia. TODO(API-01) y TODO(API-08): ver docs/HUECOS.md.
    """

    actuacion_id: str
    codigo_identificativo_propio: str
    destino: str
    mapeo_id: str
    mapeo_version: str
    generado_en: datetime
    payload: Mapping[str, object]
    manifiesto: Manifiesto
    adjuntos: tuple[Adjunto, ...]
    raiz: str
    veredicto: str | None = None
    carencias: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.destino not in DESTINOS:
            raise ErrorSalida(f"destino desconocido: {self.destino!r}; los declarados son {list(DESTINOS)}")
        if self.generado_en.tzinfo is None:
            raise ErrorSalida("`generado_en` necesita zona horaria explicita (UTC)")

    @property
    def hash_paquete(self) -> str:
        """La huella del paquete es la del manifiesto: no hay una segunda (`ADR-009` §2 punto 3)."""
        return self.manifiesto.hash_manifiesto

    def a_dict(self) -> dict[str, object]:
        """Vista serializable. El manifiesto se incrusta con su propio `a_dict`, sin recalcular nada."""
        return {
            "actuacion_id": self.actuacion_id,
            "codigo_identificativo_propio": self.codigo_identificativo_propio,
            "destino": self.destino,
            "mapeo_id": self.mapeo_id,
            "mapeo_version": self.mapeo_version,
            "generado_en": self.generado_en.isoformat(),
            "payload": dict(self.payload),
            "manifiesto": self.manifiesto.a_dict(),
            "adjuntos": [a.a_dict() for a in self.adjuntos],
            "veredicto": self.veredicto,
            "carencias": list(self.carencias),
            "hash_paquete": self.hash_paquete,
        }


@dataclass(frozen=True)
class Acuse:
    """Que dice el destino de lo que le hemos dado.

    `aceptado: False` con `motivos` es una respuesta valida, no una excepcion.
    """

    referencia: str
    via: str
    instante: datetime
    aceptado: bool
    hash_paquete: str
    estado_plataforma: str | None = None
    motivos: tuple[str, ...] = ()
    detalle: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.via not in VIAS:
            raise ErrorSalida(f"via desconocida: {self.via!r}; las declaradas son {list(VIAS)}")
        if self.instante.tzinfo is None:
            raise ErrorSalida("`instante` necesita zona horaria explicita (UTC)")

    def a_dict(self) -> dict[str, object]:
        return {
            "referencia": self.referencia,
            "via": self.via,
            "instante": self.instante.isoformat(),
            "aceptado": self.aceptado,
            "hash_paquete": self.hash_paquete,
            "estado_plataforma": self.estado_plataforma,
            "motivos": list(self.motivos),
            "detalle": dict(self.detalle),
        }


@dataclass(frozen=True)
class EstadoPlataforma:
    """Un estado tal y como lo devuelve el destino.

    `oficial` distingue los 8 confirmados de los provisionales.

    Los provisionales son nombres NUESTROS. TODO(API-03): ver docs/HUECOS.md.
    """

    referencia: str
    literal: str
    nivel: str
    oficial: bool
    instante: datetime
    motivos: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.nivel not in NIVELES:
            raise ErrorSalida(f"nivel desconocido: {self.nivel!r}; los declarados son {list(NIVELES)}")
        if self.instante.tzinfo is None:
            raise ErrorSalida("`instante` necesita zona horaria explicita (UTC)")

    def a_dict(self) -> dict[str, object]:
        return {
            "referencia": self.referencia,
            "literal": self.literal,
            "nivel": self.nivel,
            "oficial": self.oficial,
            "instante": self.instante.isoformat(),
            "motivos": list(self.motivos),
        }


@dataclass(frozen=True)
class TareaPendiente:
    """Una tarea del tenant en el destino (`docs/02` §6.1). Se consume y se prioriza en la consola (S4).

    `vence_en` existe porque la presentacion menciona "seguimiento de plazos", pero **sin cifras**: la
    plataforma no publica plazos. TODO(API-10): ver docs/HUECOS.md. Se rellena solo si el destino lo da.
    """

    id: str
    tenant_id: str
    asunto: str
    instante: datetime
    referencia: str | None = None
    vence_en: date | None = None

    def __post_init__(self) -> None:
        if self.instante.tzinfo is None:
            raise ErrorSalida("`instante` necesita zona horaria explicita (UTC)")

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "asunto": self.asunto,
            "instante": self.instante.isoformat(),
            "referencia": self.referencia,
            "vence_en": self.vence_en.isoformat() if self.vence_en is not None else None,
        }


@runtime_checkable
class PuertoSalida(Protocol):
    """Las cuatro operaciones de `docs/03` §10.1.

    Un adaptador que no pueda con una de ellas la niega con `ErrorSalida`, nunca con un vacio ambiguo.
    """

    nombre: str

    def construir(
        self,
        actuacion: object,
        mapeo: object,
        *,
        raiz: object | None = None,
        log: object | None = None,
    ) -> Paquete:
        """Modelo canonico + mapeo declarativo -> paquete. No firma, no entrega y no calcula nada."""
        ...

    def entregar(self, paquete: Paquete, *, log: object | None = None) -> Acuse:
        """Entrega el paquete por esta via. Con `log`, deja el evento P8 que corresponda."""
        ...

    def consultar_estado(self, referencia: str) -> EstadoPlataforma:
        """El estado que el destino tenga de esa referencia. `ErrorSalida` si esta via no consulta."""
        ...

    def consultar_tareas(self, tenant_id: str) -> Sequence[TareaPendiente]:
        """Las tareas pendientes del tenant. `ErrorSalida` si esta via no las tiene."""
        ...


def adjuntos_de(manifiesto: Manifiesto) -> tuple[Adjunto, ...]:
    """Los adjuntos de un paquete, derivados del manifiesto: una sola fuente para lo que viaja.

    No lee el disco ni recalcula huellas; traduce lo que el manifiesto ya declaro (`ADR-008`).
    """
    return tuple(
        Adjunto(
            ruta=fichero.ruta,
            tipo=fichero.tipo,
            sha256=fichero.sha256,
            bytes=fichero.bytes,
            origen=fichero.origen,
            es_parte=fichero.origen is not None,
        )
        for fichero in manifiesto.ficheros
    )


__all__ = [
    "DESTINOS",
    "NIVELES",
    "VIAS",
    "Acuse",
    "Adjunto",
    "ErrorSalida",
    "EstadoPlataforma",
    "Paquete",
    "PuertoSalida",
    "TareaPendiente",
    "adjuntos_de",
]
