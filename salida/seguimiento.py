"""Puente del puerto de salida al seguimiento del nucleo (C11 de `ADR-010` §4).

El nucleo decide y el nucleo escribe; lo unico que falta es **preguntar al destino**, y eso no puede vivir en
`engine/`: `engine/` no importa de `salida/` (regla de oro, test desde la Fase 0). Este modulo es esa
pregunta, y nada mas:

    puerto (simulador hoy, API en S3.7)  ->  datos planos de `engine.seguimiento`  ->  el nucleo decide

Tres cosas que este modulo **no** hace, a proposito:

1. **No interpreta.** Traduce `EstadoPlataforma` a `EstadoRecibido` campo a campo y se aparta. Que le hace
   cada literal al ciclo lo dice `estados_plataforma.yaml`; si el literal no esta en la tabla, el nucleo lo
   refleja y lo senala como hueco (`ADR-010` §2 regla 2).
2. **No inventa un estado cuando la via no puede darlo.** El handoff se niega a consultar, y esa negativa
   sube tal cual como `ErrorSalida`: una lista vacia se confundiria con "no hay nada pendiente", que es
   exactamente lo contrario de lo que pasa cuando el tenant tiene un requerimiento sin leer.
3. **No tiene reloj.** El instante lo trae el destino. Dos sincronizaciones del mismo estado dan el mismo
   log, y la segunda no duplica nada (idempotencia del nucleo).

Con el destino apagado, el Engine sigue dando veredicto: este modulo solo existe cuando hay a quien
preguntar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from engine.eventos.log import Actor, LogEventos
from engine.seguimiento import EstadoRecibido, Sincronizacion, TareaRecibida, sincronizar
from salida.puerto import ErrorSalida, EstadoPlataforma, TareaPendiente

__all__ = [
    "estado_recibido_de",
    "sincronizar_desde",
    "tarea_recibida_de",
]


def estado_recibido_de(estado: EstadoPlataforma) -> EstadoRecibido:
    """`EstadoPlataforma` del puerto -> el dato plano del nucleo. Campo a campo, sin criterio propio."""
    if not isinstance(estado, EstadoPlataforma):
        raise ErrorSalida(f"se esperaba un EstadoPlataforma y llego {type(estado).__name__}")
    return EstadoRecibido(
        referencia=estado.referencia,
        literal=estado.literal,
        nivel=estado.nivel,
        oficial=estado.oficial,
        instante=estado.instante,
        motivos=tuple(estado.motivos),
    )


def tarea_recibida_de(tarea: TareaPendiente) -> TareaRecibida:
    """`salida.puerto.TareaPendiente` -> el dato plano que consume el nucleo."""
    if not isinstance(tarea, TareaPendiente):
        raise ErrorSalida(f"se esperaba una TareaPendiente y llego {type(tarea).__name__}")
    return TareaRecibida(
        id=tarea.id,
        tenant_id=tarea.tenant_id,
        asunto=tarea.asunto,
        instante=tarea.instante,
        referencia=tarea.referencia,
        vence_en=tarea.vence_en,
    )


def sincronizar_desde(
    puerto: object,
    *,
    logs: Mapping[str, LogEventos] | Iterable[LogEventos],
    indice: Mapping[str, str],
    referencias: Sequence[str] = (),
    tenant_id: str | None = None,
    actor: Actor | None = None,
) -> Sincronizacion:
    """Pregunta al destino por esas referencias (y por las tareas del tenant) y lo refleja en los logs.

    `referencias` son las del destino, no nuestras: las devuelve el acuse de la entrega. Sin referencias no
    se consulta ningun estado, y sin `tenant_id` no se consultan tareas: **preguntar por todo** no es una
    operacion que la plataforma documente (`TODO(API-01)`: ver `docs/HUECOS.md`), y no se simula que exista.

    Una via que no puede consultar levanta `ErrorSalida` y **no se captura**: que el handoff no sepa el
    estado es informacion, no un vacio.
    """
    for nombre in ("consultar_estado", "consultar_tareas"):
        if not callable(getattr(puerto, nombre, None)):
            raise ErrorSalida(
                f"{type(puerto).__name__} no cumple el puerto de salida: le falta {nombre}() "
                "(`salida.puerto.PuertoSalida`)"
            )

    recibidos: list[EstadoRecibido | TareaRecibida] = [
        estado_recibido_de(puerto.consultar_estado(referencia)) for referencia in referencias
    ]
    if tenant_id is not None:
        recibidos.extend(tarea_recibida_de(tarea) for tarea in puerto.consultar_tareas(tenant_id))
    return sincronizar(logs, recibidos, indice=indice, actor=actor)
