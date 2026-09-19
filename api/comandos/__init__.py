"""`ejecutar`: la unica puerta de entrada de un comando (contrato C15, `ADR-011` §4).

**Hay una entrada por capacidad, siempre.** Las que todavia no tienen implementacion en `engine/` no se
quedan fuera del contrato: se invocan igual, pasan el mismo control de permisos y levantan un `ErrorApi`
que dice **que falta** (lo que declara `falta` en `engine/capacidades.yaml`). El contrato de `FR0` es
completo aunque la implementacion no lo sea; eso es justo lo que `FR0` significa.

Dos garantias que se comprueban en tiempo de ejecucion y no solo en un test:

1. **Un comando solo escribe los eventos que su capacidad declara.** Si un manejador sella un tipo que la
   matriz no le atribuye, la peticion falla. Es la contrapartida de la comprobacion que el log hace por su
   lado con el perfil (A8): la matriz manda en los dos sentidos.
2. **El evento se ensaya contra la maquina de estados antes de tocar el log** (`engine.seguimiento`), asi
   que un comando que el ciclo no admite no deja el log envenenado.

Aqui no hay ni un `CAP-nn` ni un `if perfil == ...`: el despachador busca el manejador por el nombre que
declara la matriz.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from api.comandos import actos, actuaciones
from api.contrato import Peticion, Respuesta, Salida, manejador_de, preparar
from api.permisos import Capacidad, ErrorApi, Matriz
from api.servicios import Servicios
from engine.capacidades import TIPO_COMANDO

#: Todos los manejadores de comando, por el nombre con el que los llama `engine/capacidades.yaml`.
MANEJADORES: Mapping[str, object] = {**actuaciones.MANEJADORES, **actos.MANEJADORES}


def _comprobar_eventos_escritos(capacidad: Capacidad, salida: Salida) -> tuple[str, ...]:
    """Lo escrito es lo declarado: ni un tipo de evento que la capacidad no atribuya a su manejador."""
    indebidos = sorted({e.tipo for e in salida.eventos} - set(capacidad.eventos))
    if indebidos:
        raise ErrorApi(
            f"{capacidad.id} ({capacidad.nombre}) ha escrito {indebidos}, que no estan entre los eventos "
            f"que declara ({list(capacidad.eventos)}). O sobra el evento o falta en la matriz"
        )
    return tuple(evento.evento_id for evento in salida.eventos)


def ejecutar(
    peticion: Peticion,
    *,
    servicios: Servicios | None = None,
    matriz_actual: Matriz | None = None,
) -> Respuesta:
    """Ejecuta un comando: valida, delega en `engine/` y devuelve lo que paso. No calcula nada."""
    _, capacidad, rol, recursos = preparar(
        peticion, TIPO_COMANDO, servicios=servicios, matriz_actual=matriz_actual
    )
    manejador = manejador_de(MANEJADORES, capacidad)
    salida = manejador(peticion, recursos, capacidad, rol)
    if not isinstance(salida, Salida):  # pragma: no cover - contrato interno de los manejadores
        raise ErrorApi(f"{capacidad.id}: el manejador ha devuelto {type(salida).__name__} y no una Salida")
    return Respuesta(
        capacidad=capacidad.id,
        rol=rol,
        eventos=_comprobar_eventos_escritos(capacidad, salida),
        datos=dict(salida.datos),
        avisos=tuple(salida.avisos),
    )


def capacidades_atendidas(matriz_actual: Matriz) -> Sequence[str]:
    """Los comandos con manejador registrado. El resto existe en el contrato y dice que le falta."""
    return sorted(
        capacidad.id
        for capacidad in matriz_actual.capacidades.values()
        if capacidad.es_comando and capacidad.manejador in MANEJADORES
    )


__all__ = ["MANEJADORES", "capacidades_atendidas", "ejecutar"]
