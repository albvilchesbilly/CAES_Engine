"""Contrato C17 (`ADR-012` §2): servir el documento original, bajo `CAP-03` y sin tocarlo.

Por que existe (`ADR-012` §1): una pantalla de revision que solo ensena el texto extraido le pide al
revisor que se fie de nuestra extraccion, que es justo lo que la revision existe para comprobar. Asi que
`FR1` sirve el papel. No hace falta capacidad nueva: `CAP-03` es literalmente "consultar la actuacion
completa: **documentos**, evidencias, conflictos, calculo, veredicto, historial".

Las cuatro condiciones del ADR, y donde se cumple cada una:

1. **Aislamiento por tenant**: los bytes pasan por la misma puerta que el resto (`contrato.preparar` →
   `exigir` + `comprobar_alcance`). Un documento de otro tenant es `ErrorPermiso`, no un vacio ambiguo.
2. **Se pide por huella, nunca por ruta.** La peticion solo admite `doc_id`, que ademas tiene que ser una
   huella bien formada **y** estar en la lista de documentos de esa actuacion. La ruta la resuelve el
   repositorio, que es quien sabe donde guardo los bytes. Una ruta en la peticion es un camino para leer
   ficheros arbitrarios del servidor, y aqui no hay por donde colarla.
3. **La huella se comprueba al servir**: se recalcula el sha256 de los bytes y, si no casa con el que
   declaro la ingesta, no se sirve (`ErrorIntegridad`). Es el mismo criterio del manifiesto.
4. **`R-UI-12` tambien aqui**: un perfil sin ambito de contenido documental **no recibe los bytes**, no es
   que no los pinte. El ambito de contenido no se cablea con un `CAP-nn` ni con un perfil: es el bloque de
   proyeccion `documentos` de `engine/capacidades.yaml`, el mismo que decide si la lectura normal puede
   construir la ficha del documento. Si la capacidad no lo proyecta o el ambito del rol no lo admite, no
   hay bytes.

**No se transforma nada.** Ni recorte, ni rotacion, ni compresion, ni resaltado: se entregan los bytes tal
y como entraron en ingesta. Un servidor que retoca un documento deja de poder demostrar que es el mismo;
resaltar la cita es del navegador.

Un caso que `ADR-012` no nombra y que la ingesta obliga a resolver: **las partes de un PDF combinado**. Una
parte no es un fichero (`Documento.doc_id` es `sha256(original + ":pX-Y")`, y su `sha256` y sus bytes son
los del combinado). Recortar el PDF para servir solo la parte seria transformarlo. Se sirve el combinado
entero, se dice en `origen` y `rango_paginas` que paginas son la parte, y va un aviso en la respuesta.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from api.contrato import Peticion, Respuesta, preparar
from api.permisos import Capacidad, ErrorApi, ErrorPermiso, Matriz, ambito_de
from api.servicios import Servicios
from engine.capacidades import TIPO_LECTURA
from engine.ingesta import sha256_bytes

#: El bloque de proyeccion que marca "este rol ve contenido documental" (`R-UI-12`). Sale de la matriz y
#: de `api.proyeccion.CONSTRUCTORES`; no es un identificador de capacidad ni de perfil.
BLOQUE_CONTENIDO = "documentos"

#: Clave con la que la respuesta lleva el documento, dentro de `Respuesta.datos` (`ADR-012` §2).
CLAVE_DOCUMENTO = "documento"

#: Una huella es 64 caracteres hexadecimales en minuscula. Tambien lo es el `doc_id` de una parte, que es
#: el sha256 de un texto (`engine.ingesta.doc_id_parte`). Nada mas se acepta como identificador.
HUELLA = re.compile(r"^[0-9a-f]{64}$")

#: Extension registrada por la ingesta → tipo de medio. Se declara para que el navegador sepa como
#: ensenarlo; no cambia ni un byte de lo que se sirve.
MEDIOS: Mapping[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
}

#: Lo que se declara cuando no se reconoce el formato. Nunca se adivina un medio "parecido".
MEDIO_DESCONOCIDO = "application/octet-stream"

#: Formato de la ingesta → medio, para los registros que no conservan el nombre del fichero.
MEDIOS_POR_FORMATO: Mapping[str, str] = {"pdf": "application/pdf"}


class ErrorIntegridad(ErrorApi):
    """Los bytes guardados no casan con la huella que declaro la ingesta: el documento fue alterado.

    Es `ErrorApi` y no `ErrorPermiso` a proposito: no es que no se pueda ver, es que lo que hay no es lo
    que se ingesto. Quien lo recibe tiene que enterarse de que el documento cambio, no creer que no existe.
    """


@dataclass(frozen=True)
class Documento:
    """El documento tal y como entro en ingesta, con lo justo para ensenarlo (`ADR-012` §2).

    `paginas` son las del **registro** (las de la parte, si es una parte), no las del fichero servido; la
    diferencia la explica `rango_paginas`. `bytes` es el tamano de lo que va en `contenido`.
    """

    doc_id: str
    tipo: str | None
    medio: str
    bytes: int
    paginas: int
    contenido: bytes
    #: sha256 del combinado del que salio esta parte, o `None`. Si no es `None`, `contenido` es el suyo.
    origen: str | None = None
    #: Paginas del original que forman la parte, en numeracion absoluta. `None` si no es una parte.
    rango_paginas: tuple[int, int] | None = None

    @property
    def es_parte(self) -> bool:
        return self.origen is not None


# ---------------------------------------------------------------------------
# Lectura de los registros de la actuacion (sin suponer una implementacion concreta)
# ---------------------------------------------------------------------------


def _entero(valor: object, por_defecto: int = 0) -> int:
    if isinstance(valor, bool):  # pragma: no cover - defensivo: un bool no es un tamano
        return por_defecto
    if isinstance(valor, int):
        return valor
    if isinstance(valor, Sequence):
        return len(valor)
    return por_defecto


def _medio_de(registro: object) -> str:
    """El medio que se declara, deducido del nombre que registro la ingesta. Nunca de la peticion."""
    nombre = getattr(registro, "nombre", None)
    if isinstance(nombre, str) and nombre.strip():
        # `PurePosixPath` solo se usa para quedarse con el sufijo del nombre; no se abre nada por aqui.
        extension = PurePosixPath(nombre.replace("\\", "/")).suffix.lower()
        if extension in MEDIOS:
            return MEDIOS[extension]
    formato = getattr(registro, "formato", None)
    if isinstance(formato, str):
        return MEDIOS_POR_FORMATO.get(formato, MEDIO_DESCONOCIDO)
    return MEDIO_DESCONOCIDO


def _rango(registro: object) -> tuple[int, int] | None:
    rango = getattr(registro, "rango_paginas", None)
    if isinstance(rango, Sequence) and len(rango) == 2:
        return (_entero(rango[0]), _entero(rango[1]))
    return None


def _registro_de(actuacion: object, doc_id: str, capacidad: Capacidad) -> object:
    """El documento de **esta** actuacion con esa huella, o error. La lista la trae el nucleo.

    Esto es lo que impide pedir un fichero cualquiera: no se busca en el disco, se busca en los documentos
    que la ingesta adjudico a la actuacion, que ya paso el control de tenant.
    """
    for registro in getattr(actuacion, "documentos", ()) or ():
        if str(getattr(registro, "doc_id", "")) == doc_id:
            return registro
    raise ErrorApi(
        f"{capacidad.id}: la actuacion no tiene ningun documento con la huella {doc_id!r}. Un documento "
        "se pide por su huella y solo se sirve si es de esta actuacion"
    )


def _doc_id_de(peticion: Peticion, capacidad: Capacidad) -> str:
    """La huella pedida, comprobada. Aqui no se admite ninguna ruta, ni relativa ni absoluta."""
    if "ruta" in peticion.datos or "nombre" in peticion.datos:
        raise ErrorApi(
            f"{capacidad.id}: un documento se pide por `doc_id` (la huella), nunca por ruta ni por "
            "nombre de fichero. La ruta la resuelve el repositorio; vincular por nombre no vincula nada"
        )
    doc_id = str(peticion.exige("doc_id")).strip()
    if not HUELLA.match(doc_id):
        raise ErrorApi(
            f"{capacidad.id}: {doc_id!r} no es una huella (64 caracteres hexadecimales en minuscula). "
            "Un identificador de documento no es un nombre ni un camino"
        )
    return doc_id


# ---------------------------------------------------------------------------
# La lectura
# ---------------------------------------------------------------------------


def _exigir_ambito_de_contenido(matriz_actual: Matriz, capacidad: Capacidad, rol: str, doc_id: str) -> None:
    """`R-UI-12` sobre los bytes: sin ambito de contenido documental no se sirve, no es que no se pinte."""
    if BLOQUE_CONTENIDO not in capacidad.bloques:
        raise ErrorPermiso(
            f"{capacidad.id} ({capacidad.nombre}) no proyecta el bloque {BLOQUE_CONTENIDO!r}: no da "
            "acceso al contenido de los documentos, solo a lo que declare en sus bloques"
        )
    admitidos = ambito_de(matriz_actual, rol).bloques
    if BLOQUE_CONTENIDO not in admitidos:
        raise ErrorPermiso(
            f"{capacidad.id}: el ambito del rol {rol!r} no admite el bloque {BLOQUE_CONTENIDO!r}, asi que "
            f"no recibe los bytes del documento {doc_id!r}. Lo que admite: {sorted(admitidos)}"
        )


def _contenido(
    servicios: Servicios, actuacion_id: str, registro: object, doc_id: str, capacidad: Capacidad
) -> tuple[bytes, str]:
    """Los bytes que guarda el repositorio para esa huella, comprobados contra ella."""
    declarada = str(getattr(registro, "sha256", "") or "")
    if not HUELLA.match(declarada):  # pragma: no cover - la ingesta siempre deja huella
        raise ErrorIntegridad(
            f"{capacidad.id}: el registro del documento {doc_id!r} no trae una huella valida "
            f"({declarada!r}); sin huella no hay nada que comprobar y no se sirve"
        )
    contenido = servicios.repositorio.bytes_de_documento(actuacion_id, declarada)
    if contenido is None:
        raise ErrorApi(
            f"{capacidad.id}: el repositorio no tiene los bytes del documento {doc_id!r} (huella "
            f"{declarada}). El documento esta registrado y su contenido no; no se sirve nada en su lugar"
        )
    if not isinstance(contenido, bytes | bytearray):  # pragma: no cover - contrato del repositorio
        raise ErrorApi(f"{capacidad.id}: el repositorio ha devuelto {type(contenido).__name__} y no bytes")
    contenido = bytes(contenido)
    obtenida = sha256_bytes(contenido)
    if obtenida != declarada:
        raise ErrorIntegridad(
            f"{capacidad.id}: el documento {doc_id!r} fue alterado despues de la ingesta. La ingesta "
            f"declaro sha256 {declarada} y lo guardado suma {obtenida}: no se sirve. Lo que se ensena en "
            "una revision tiene que ser demostrablemente el mismo fichero que se calculo"
        )
    return contenido, declarada


def leer_documento(
    peticion: Peticion,
    *,
    servicios: Servicios | None = None,
    matriz_actual: Matriz | None = None,
) -> Respuesta:
    """Sirve el documento original de una actuacion. `datos["documento"]` es un `Documento`.

    No es un manejador de `api.lecturas.MANEJADORES` ni un bloque de proyeccion: unos bytes no son un
    bloque serializable, y la matriz (que vive en `engine/` y no se toca desde aqui) no declara ninguno
    para ellos. Es una entrada propia que pasa por la **misma** puerta, con la capacidad que diga la
    peticion: aqui no hay ningun `CAP-nn` escrito.
    """
    activa, capacidad, rol, recursos = preparar(
        peticion, TIPO_LECTURA, servicios=servicios, matriz_actual=matriz_actual
    )
    doc_id = _doc_id_de(peticion, capacidad)
    _exigir_ambito_de_contenido(activa, capacidad, rol, doc_id)

    actuacion_id = peticion.actuacion_id
    actuacion = recursos.repositorio.actuacion(actuacion_id)
    if actuacion is None:
        raise ErrorApi(
            f"{capacidad.id}: la actuacion {actuacion_id!r} no esta procesada todavia; no hay documentos"
        )
    registro = _registro_de(actuacion, doc_id, capacidad)
    contenido, declarada = _contenido(recursos, actuacion_id, registro, doc_id, capacidad)

    origen = getattr(registro, "origen", None)
    documento = Documento(
        doc_id=doc_id,
        tipo=getattr(registro, "tipo", None),
        medio=_medio_de(registro),
        bytes=len(contenido),
        paginas=_entero(getattr(registro, "paginas", 0)),
        contenido=contenido,
        origen=None if origen is None else str(origen),
        rango_paginas=_rango(registro),
    )
    avisos: tuple[str, ...] = ()
    if documento.es_parte:
        rango = documento.rango_paginas
        paginas = f"{rango[0]}-{rango[1]}" if rango else "desconocidas"
        avisos = (
            f"el documento {doc_id} es una parte del PDF combinado {declarada}: se sirve el combinado "
            f"entero, sin recortar, y la parte son sus paginas {paginas}",
        )
    return Respuesta(
        capacidad=capacidad.id,
        rol=rol,
        eventos=(),
        datos={CLAVE_DOCUMENTO: documento},
        avisos=avisos,
    )


def documento_a_transporte(documento: Documento) -> dict[str, object]:
    """El `Documento` en la forma que viaja al front: los bytes en base64, sin tocar su contenido.

    Base64 no es una transformacion del documento: es como se mete un binario en un sobre JSON y se
    deshace intacto al otro lado (`front/compartido/api/` lo decodifica). El sha256 de lo decodificado
    sigue siendo el de la ingesta, y hay un test que lo comprueba en los dos sentidos.
    """
    return {
        "doc_id": documento.doc_id,
        "tipo": documento.tipo,
        "medio": documento.medio,
        "bytes": documento.bytes,
        "paginas": documento.paginas,
        "origen": documento.origen,
        "rango_paginas": None if documento.rango_paginas is None else list(documento.rango_paginas),
        "contenido_base64": base64.b64encode(documento.contenido).decode("ascii"),
    }


__all__ = [
    "BLOQUE_CONTENIDO",
    "CLAVE_DOCUMENTO",
    "MEDIOS",
    "MEDIO_DESCONOCIDO",
    "Documento",
    "ErrorIntegridad",
    "documento_a_transporte",
    "leer_documento",
]
