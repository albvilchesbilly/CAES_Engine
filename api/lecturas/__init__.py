"""`leer`: la unica puerta de entrada de una lectura (contrato C15, `ADR-011` §4).

**Hay una entrada por capacidad, siempre.** Las que todavia no tienen implementacion se invocan igual,
pasan el mismo control de permisos y levantan un `ErrorApi` que dice **que falta**.

Lo que distingue a `leer` de `ejecutar` es el final: la respuesta se construye **bloque a bloque**, y solo
los bloques que estan a la vez en lo que la capacidad proyecta y en lo que el ambito del rol admite
(`R-UI-12`). Un campo fuera del ambito no se construye; no es que no se pinte. Una lectura nunca escribe
eventos: `Respuesta.eventos` sale vacia siempre.

Aqui no hay ni un `CAP-nn` ni un `if perfil == ...`: el despachador busca el manejador por el nombre que
declara la matriz, y los bloques por el suyo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from api.contrato import Peticion, Respuesta, manejador_de, preparar
from api.lecturas import actuaciones, paneles
from api.permisos import ErrorApi, Matriz, ambito_de
from api.proyeccion import Vista, proyectar_vista
from api.servicios import Servicios
from engine.capacidades import TIPO_LECTURA

#: Todos los manejadores de lectura, por el nombre con el que los llama `engine/capacidades.yaml`.
MANEJADORES: Mapping[str, object] = {**actuaciones.MANEJADORES, **paneles.MANEJADORES}


def leer(
    peticion: Peticion,
    *,
    servicios: Servicios | None = None,
    matriz_actual: Matriz | None = None,
) -> Respuesta:
    """Ejecuta una lectura: valida, trae el material de `engine/` y proyecta lo que el ambito admite."""
    activa, capacidad, rol, recursos = preparar(
        peticion, TIPO_LECTURA, servicios=servicios, matriz_actual=matriz_actual
    )
    manejador = manejador_de(MANEJADORES, capacidad)
    vista = manejador(peticion, recursos, capacidad, rol)
    if not isinstance(vista, Vista):  # pragma: no cover - contrato interno de los manejadores
        raise ErrorApi(f"{capacidad.id}: el manejador ha devuelto {type(vista).__name__} y no una Vista")
    datos = proyectar_vista(capacidad.bloques, ambito_de(activa, rol).bloques, vista)
    return Respuesta(capacidad=capacidad.id, rol=rol, eventos=(), datos=datos, avisos=vista.avisos)


def capacidades_atendidas(matriz_actual: Matriz) -> Sequence[str]:
    """Las lecturas con manejador registrado. El resto existe en el contrato y dice que le falta."""
    return sorted(
        capacidad.id
        for capacidad in matriz_actual.capacidades.values()
        if not capacidad.es_comando and capacidad.manejador in MANEJADORES
    )


__all__ = ["MANEJADORES", "capacidades_atendidas", "leer"]
