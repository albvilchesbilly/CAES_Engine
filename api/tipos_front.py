"""Los tipos que el front deriva del contrato, en vez de escribirlos a mano (`ADR-012` §3, regla 4).

La regla es corta: *si `api/` cambia un bloque, el front tiene que enterarse al compilar y no en
produccion*. Aqui se traduce a TypeScript lo que ya es configuracion en este lado —los bloques de
proyeccion (`api.proyeccion.CONSTRUCTORES`) y las capacidades de la matriz (`engine/capacidades.yaml`)— y
`front/compartido/api/contrato.generado.ts` es el resultado, **commiteado**.

Por que generado y commiteado, y no leido en tiempo de compilacion: el front no puede ejecutar Python para
compilar, y un tipo que se deduce de un YAML en tiempo de ejecucion no lo comprueba nadie. Commiteado, el
compilador de TypeScript lo ve; y `tests/test_api_tipos_front.py` vuelve a generarlo y compara, asi que
cambiar un bloque en `api/` sin regenerar el fichero **rompe el banco de pruebas de Python** y, en cuanto
se regenera, rompe la compilacion del front alli donde el bloque ya no exista. Las dos mitades se enteran.

Este modulo **no importa nada de `front/`**: solo produce texto. La dependencia sigue yendo hacia dentro.
"""

from __future__ import annotations

from collections.abc import Iterable

from api.permisos import Matriz, matriz
from api.proyeccion import CONSTRUCTORES

#: Donde vive el fichero generado, relativo a la raiz del repositorio.
RUTA_GENERADA = "front/compartido/api/contrato.generado.ts"

CABECERA = """// Fichero GENERADO por `api/tipos_front.py`. No se edita a mano.
//
// Sale de `api/proyeccion.py` (los bloques que el servidor sabe construir) y de
// `engine/capacidades.yaml` (que capacidad es lectura y cual es comando, y que bloques proyecta cada
// una). `tests/test_api_tipos_front.py` lo regenera y compara: si `api/` cambia y esto no, el banco de
// pruebas de Python se pone rojo; cuando se regenera, la compilacion de TypeScript senala cada sitio del
// front que usaba un bloque o una capacidad que ya no existe. De eso se trata (`ADR-012` §3, regla 4).
//
// Esto NO es una tabla de permisos. Que una capacidad exista aqui no significa que quien mira la pantalla
// pueda ejercerla: eso lo decide el servidor en cada peticion (`R-UI-01`).
"""


def _lista_ts(valores: Iterable[str]) -> str:
    return "\n".join(f'  "{valor}",' for valor in valores)


def typescript(matriz_actual: Matriz | None = None) -> str:
    """El contenido completo del fichero generado, terminado en salto de linea."""
    activa = matriz_actual if matriz_actual is not None else matriz()
    capacidades = list(activa.capacidades.values())
    lecturas = [c for c in capacidades if not c.es_comando]
    comandos = [c for c in capacidades if c.es_comando]

    filas_lectura = "\n".join(
        f'  "{c.id}": [{", ".join(chr(34) + b + chr(34) for b in c.bloques)}],' for c in lecturas
    )
    return f"""{CABECERA}
/** Los bloques que una lectura puede traer. Los construye `api/proyeccion.py` y nadie mas. */
export const BLOQUES = [
{_lista_ts(CONSTRUCTORES)}
] as const;

export type Bloque = (typeof BLOQUES)[number];

/**
 * Lo que viaja en `Respuesta.datos` de una lectura: **algunos** de los bloques, nunca todos.
 *
 * Todos son opcionales a proposito, y esa es la parte importante. `R-UI-12` dice que un bloque fuera del
 * ambito del rol **no se construye**; si aqui fueran obligatorios, el front creeria que siempre estan y
 * acabaria pintando `undefined` o, peor, inventandose un valor por defecto.
 */
export type Datos = {{ readonly [B in Bloque]?: unknown }};

/** Las lecturas del contrato y los bloques que proyecta cada una. */
export const LECTURAS = {{
{filas_lectura}
}} as const satisfies Readonly<Record<string, readonly Bloque[]>>;

export type CapacidadLectura = keyof typeof LECTURAS;

/** Los comandos del contrato. Lo que escriben lo decide el servidor, no esta lista. */
export const COMANDOS = [
{_lista_ts(c.id for c in comandos)}
] as const;

export type CapacidadComando = (typeof COMANDOS)[number];
"""


__all__ = ["RUTA_GENERADA", "typescript"]
