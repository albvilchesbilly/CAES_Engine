"""Contrato C27 (`ADR-015` §3): el servidor es una capa de traduccion, y nada mas.

Lee el sobre, construye una `api.contrato.Peticion`, llama a `api.lecturas.leer`,
`api.comandos.ejecutar` o `api.lecturas.documentos.leer_documento`, y traduce la `Respuesta` —o el
error— de vuelta al sobre. El sobre esta descrito en **`front/compartido/api/transporte.ts`**, que es la
fuente de su forma; aqui no se rediseña, se implementa:

- `POST {base}/lecturas/{capacidad}` · `POST {base}/comandos/{capacidad}` · `POST {base}/documentos`
- cuerpo `{contexto, datos}`; respuesta 200 `{capacidad, rol, rol_nombre, eventos, datos, avisos}`
- `403 {error: "permiso", motivo, codigo?}` · cualquier otra `{error: "api", motivo, codigo?}`

Lo que este modulo **no** hace, y hay tests que lo recorren sobre el arbol (`tests/test_http_arbol.py`):

- **No decide permisos**: eso es `api.contrato.preparar` → `api.permisos.exigir`, que ya esta probado.
  La unica comprobacion que se hace aqui es la de C30, y es deliberadamente redundante (ver abajo).
- **No proyecta ni filtra bloques**: eso es `api.proyeccion`, y se sirve tal cual lo devuelve.
- **No toca `engine/`**: ni un import. Componer el repositorio y cargar casos es del arranque, que vive
  fuera de este paquete (`servidor_desarrollo.py`), igual que `evaluar_casos.py`.
- **No añade validacion propia de los datos del contrato.** Si `Peticion` acepta algo, se pasa; si lo
  rechaza, se traduce el error. Una segunda validacion aqui es una segunda verdad, y divergira.
  Lo que si se comprueba es el **sobre**: que el cuerpo sea JSON, que `contexto` y `datos` sean objetos y
  que `contexto` no traiga campos que no existen. Eso no es el contrato: es el envoltorio.

**C30 — el tenant se comprueba, no se cree.** El `tenant_id` del contexto lo declara la pantalla. Se
compara con el del principal **antes** de llegar a `api/` y se deniega si no coinciden. Es la segunda
barrera: `api.contrato.comprobar_alcance` ya falla cerrado desde el 20/09, y que haya dos es deliberado.
La comparacion es exacta, incluido `None`: una pantalla que declara un tenant y un principal que no lo
tiene no se atiende. El dia que una consola global (`ADM-MOD`, `ADM-OPS`) necesite declarar el tenant que
esta mirando, esto dira que no, en voz alta y con el motivo; se cambia entonces y con una decision
delante, que es mejor que descubrirlo sirviendo datos.

**La capacidad de `/documentos`.** El sobre no la lleva —el cliente la usa solo para el mensaje de error—
asi que el servidor tiene que saber cual es. No se escribe ningun `CAP-nn` aqui: se **deriva de la
matriz**, que es la unica lectura que proyecta el bloque de contenido documental
(`api.lecturas.documentos.BLOQUE_CONTENIDO`), el mismo criterio con el que `leer_documento` decide si hay
bytes. Si algun dia hay dos, el servidor no arranca y obliga a decidir cual sirve el documento en vez de
elegir una. Queda anotado como discrepancia entre el sobre y `api/`: ver el informe de `FR-HTTP`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from api.comandos import ejecutar
from api.contrato import Peticion, Respuesta
from api.http.autenticacion import Autenticador, AutenticadorAusente, ErrorArranque, ErrorAutenticacion
from api.lecturas import leer
from api.lecturas.documentos import (
    BLOQUE_CONTENIDO,
    CLAVE_DOCUMENTO,
    documento_a_transporte,
    leer_documento,
)
from api.permisos import Contexto, ErrorApi, ErrorMatriz, ErrorPermiso, Matriz, matriz
from api.servicios import Servicios

registro = logging.getLogger("api.http")

#: Lo que como maximo se acepta en el cuerpo de una peticion. Un servidor que sirve documentos acepta
#: subidas, y sin limite la primera peticion grande se lleva la memoria del proceso. **El valor es
#: provisional y es una decision de producto que espera a Billy** (`ADR-015` §6): aqui hay uno para no
#: dejar el hueco abierto, no porque este medido. El documento mas grande del banco sintetico son 213 KB.
TAMANO_MAXIMO_CUERPO = 8 * 1024 * 1024

#: Los campos del contexto, que son los de `api.permisos.Contexto` y los del cliente de `front/`.
CAMPOS_CONTEXTO = frozenset({"superficie", "tenant_id", "actuacion_id"})

#: Cabeceras de toda respuesta. Lo que viaja son datos de una actuacion: ni se cachea ni se adivina el tipo.
CABECERAS_BASE: Mapping[str, str] = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


class _ErrorSobre(Exception):
    """El envoltorio no se puede leer (no es JSON, no es un objeto, el cuerpo no cabe). No es el contrato."""

    def __init__(self, motivo: str, *, estado: int = 400, codigo: str = "sobre") -> None:
        super().__init__(motivo)
        self.estado = estado
        self.codigo = codigo


# ---------------------------------------------------------------------------
# El sobre: leerlo y escribirlo
# ---------------------------------------------------------------------------


def _respuesta(cuerpo: Mapping[str, object], estado: int) -> Response:
    return JSONResponse(dict(cuerpo), status_code=estado, headers=dict(CABECERAS_BASE))


def _negativa(motivo: str, *, estado: int, clase: str, codigo: str | None = None) -> Response:
    cuerpo: dict[str, object] = {"error": clase, "motivo": motivo}
    if codigo is not None:
        cuerpo["codigo"] = codigo
    return _respuesta(cuerpo, estado)


def _sobre_de(respuesta: Respuesta, avisos_extra: Iterable[str]) -> dict[str, object]:
    """La `Respuesta` en la forma que espera el cliente. Todos los campos, y ninguno inventado."""
    return {
        "capacidad": respuesta.capacidad,
        "rol": respuesta.rol,
        "rol_nombre": respuesta.rol_nombre,
        "eventos": list(respuesta.eventos),
        "datos": dict(respuesta.datos),
        "avisos": [*respuesta.avisos, *avisos_extra],
    }


async def _cuerpo_crudo(peticion: Request, maximo: int) -> bytes:
    """Los bytes del cuerpo, cortando en cuanto pasan del maximo. No se acumula lo que no cabe."""
    declarado = peticion.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > maximo:
        raise _ErrorSobre(
            f"el cuerpo de la peticion dice ocupar {declarado} bytes y el maximo son {maximo}",
            estado=413,
            codigo="cuerpo_demasiado_grande",
        )
    trozos: list[bytes] = []
    total = 0
    async for trozo in peticion.stream():
        total += len(trozo)
        if total > maximo:
            raise _ErrorSobre(
                f"el cuerpo de la peticion pasa de {maximo} bytes",
                estado=413,
                codigo="cuerpo_demasiado_grande",
            )
        trozos.append(trozo)
    return b"".join(trozos)


def _objeto(valor: object, nombre: str) -> Mapping[str, Any]:
    if not isinstance(valor, Mapping):
        raise _ErrorSobre(f"`{nombre}` tiene que ser un objeto; ha llegado {type(valor).__name__}")
    return valor


def _contexto_de(cuerpo: Mapping[str, Any]) -> Contexto:
    """El contexto del sobre. Un campo que `Contexto` no tiene es un error, no algo que se ignora."""
    declarado = _objeto(cuerpo.get("contexto"), "contexto")
    sobrantes = sorted(set(declarado) - CAMPOS_CONTEXTO)
    if sobrantes:
        raise _ErrorSobre(
            f"el contexto trae campos que no existen: {sobrantes}. Los que hay son "
            f"{sorted(CAMPOS_CONTEXTO)}; uno mal escrito que se ignorase en silencio viajaria vacio"
        )
    try:
        return Contexto(
            superficie=str(declarado.get("superficie") or ""),
            tenant_id=declarado.get("tenant_id"),
            actuacion_id=declarado.get("actuacion_id"),
        )
    except ErrorApi as exc:
        raise _ErrorSobre(str(exc)) from exc


def _comprobar_tenant(principal: object, contexto: Contexto) -> None:
    """C30: el tenant que declara la pantalla se compara con el del principal, y si no, no se atiende."""
    del_principal = getattr(principal, "tenant_id", None)
    if contexto.tenant_id == del_principal:
        return
    raise ErrorPermiso(
        f"cruce de tenant: la pantalla declara el tenant {contexto.tenant_id!r} y el principal "
        f"{getattr(principal, 'usuario_id', None)!r} es de {del_principal!r}. El tenant lo fija la "
        "autenticacion, no el cliente (`ADR-015` C30)"
    )


# ---------------------------------------------------------------------------
# La aplicacion
# ---------------------------------------------------------------------------


def capacidad_del_documento(matriz_actual: Matriz) -> str:
    """La capacidad con la que se sirve `/documentos`, **leida de la matriz** (ver la cabecera).

    No hay ningun `CAP-nn` escrito: es la unica lectura que proyecta el bloque de contenido documental.
    Si no hay exactamente una, el servidor no arranca: elegir una de dos seria decidir aqui un alcance de
    autorizacion, que es justo lo que la matriz existe para decidir.
    """
    candidatas = sorted(
        capacidad.id
        for capacidad in matriz_actual.capacidades.values()
        if not capacidad.es_comando and BLOQUE_CONTENIDO in (capacidad.bloques or ())
    )
    if len(candidatas) != 1:
        raise ErrorArranque(
            f"la ruta `/documentos` no lleva capacidad en el sobre y la matriz declara {candidatas} "
            f"lecturas que proyectan el bloque {BLOQUE_CONTENIDO!r}. Con una se sabe cual es; con "
            "ninguna o con varias hay que decidirlo y cambiar el sobre "
            "(`front/compartido/api/transporte.ts` y `ADR-015`), no elegir aqui"
        )
    return candidatas[0]


def _exigir_puerto(autenticador: object) -> None:
    """Que lo que se ha pasado sea un `Autenticador` (C28). Se comprueba al arrancar, no al servir."""
    if not callable(getattr(autenticador, "principal", None)):
        raise ErrorArranque(
            f"{type(autenticador).__name__} no implementa el puerto `Autenticador`: le falta "
            "`principal(peticion) -> Principal` (`ADR-015` C28)"
        )
    if not isinstance(getattr(autenticador, "avisos", None), tuple):
        raise ErrorArranque(
            f"{type(autenticador).__name__} no declara `avisos`: el puerto lo exige para que una "
            "autenticacion que no es de verdad lo diga en cada respuesta (`ADR-015` C28 y C29)"
        )


def crear_app(
    *,
    autenticador: Autenticador | None = None,
    servicios: Servicios | None = None,
    matriz_actual: Matriz | None = None,
    origenes_cors: Iterable[str] = (),
    tamano_maximo_cuerpo: int = TAMANO_MAXIMO_CUERPO,
) -> Starlette:
    """La aplicacion ASGI que publica `api/`. Sin estado global: todo entra por aqui.

    `autenticador` por defecto es `AutenticadorAusente`, que **deniega todo**: un servidor sin
    autenticacion configurada no atiende a nadie, en vez de atender a cualquiera (C28).

    `origenes_cors` esta vacio por defecto —solo mismo origen— y se rellena a mano cuando las pantallas se
    sirven desde otro puerto en local. No hay comodin: un `*` en un servidor que sirve documentos de un
    tenant es un agujero, no una comodidad.
    """
    puerto = autenticador if autenticador is not None else AutenticadorAusente()
    _exigir_puerto(puerto)
    activa = matriz_actual if matriz_actual is not None else matriz()
    capacidad_documento = capacidad_del_documento(activa)
    recursos = servicios

    def _llamada(ruta: str) -> Callable[[Peticion], Respuesta]:
        if ruta == "lecturas":
            return lambda peticion: leer(peticion, servicios=recursos, matriz_actual=activa)
        if ruta == "comandos":
            return lambda peticion: ejecutar(peticion, servicios=recursos, matriz_actual=activa)
        return lambda peticion: leer_documento(peticion, servicios=recursos, matriz_actual=activa)

    async def _atender(peticion: Request, ruta: str) -> Response:
        capacidad = peticion.path_params.get("capacidad") or capacidad_documento
        try:
            # **Primero quien pide.** Antes de esta linea el servidor no ha leido ni un byte del cuerpo:
            # quien no se identifica no consigue que se le reserve memoria ni que se le parsee nada.
            principal = puerto.principal(peticion)
            crudo = await _cuerpo_crudo(peticion, tamano_maximo_cuerpo)
            try:
                cuerpo = json.loads(crudo) if crudo.strip() else {}
            except ValueError as exc:
                raise _ErrorSobre(f"el cuerpo de la peticion no es JSON: {exc}") from exc
            cuerpo = _objeto(cuerpo, "cuerpo")
            datos = _objeto(cuerpo.get("datos") or {}, "datos")
            contexto = _contexto_de(cuerpo)
            _comprobar_tenant(principal, contexto)
            respuesta = await run_in_threadpool(
                _llamada(ruta),
                Peticion(capacidad, principal, contexto, dict(datos)),
            )
        except _ErrorSobre as exc:
            return _negativa(str(exc), estado=exc.estado, clase="api", codigo=exc.codigo)
        except ErrorAutenticacion as exc:
            return _negativa(str(exc), estado=403, clase="permiso", codigo="autenticacion")
        except ErrorPermiso as exc:
            return _negativa(str(exc), estado=403, clase="permiso")
        except ErrorMatriz as exc:
            registro.error("la matriz de capacidades no carga: %s", exc)
            return _negativa(str(exc), estado=500, clase="api", codigo="arranque")
        except ErrorApi as exc:
            return _negativa(str(exc), estado=400, clase="api")
        except Exception:
            # Nada de detalles internos en el sobre: un traceback en la respuesta cuenta el servidor a
            # quien pregunta. Va al log, que es donde lo lee quien opera.
            registro.exception("fallo no previsto atendiendo %s", capacidad)
            return _negativa(
                f"{capacidad}: el servidor ha fallado atendiendo la peticion; el detalle esta en su log",
                estado=500,
                clase="api",
                codigo="interno",
            )
        try:
            sobre = _sobre_de(respuesta, puerto.avisos)
            if ruta == "documentos":
                # Base64 no transforma el documento: es como se mete un binario en un sobre JSON. Lo hace
                # `api/`, que es de quien es el `Documento`; aqui solo se llama.
                sobre["datos"] = {CLAVE_DOCUMENTO: documento_a_transporte(respuesta.datos[CLAVE_DOCUMENTO])}
            return _respuesta(sobre, 200)
        except (AttributeError, KeyError, TypeError, ValueError):
            registro.exception("la respuesta de %s no se puede serializar", capacidad)
            return _negativa(
                f"{capacidad}: la respuesta no se puede escribir como JSON, asi que no se sirve a medias",
                estado=500,
                clase="api",
                codigo="interno",
            )

    async def _lectura(peticion: Request) -> Response:
        return await _atender(peticion, "lecturas")

    async def _comando(peticion: Request) -> Response:
        return await _atender(peticion, "comandos")

    async def _documento(peticion: Request) -> Response:
        return await _atender(peticion, "documentos")

    async def _fuera_de_ruta(peticion: Request, exc: Exception) -> Response:
        """Tambien un 404 o un 405 salen en el sobre: el cliente solo sabe leer eso."""
        estado = getattr(exc, "status_code", 500)
        detalle = getattr(exc, "detail", "")
        return _negativa(
            f"{peticion.method} {peticion.url.path}: {detalle}", estado=estado, clase="api", codigo="ruta"
        )

    intermedios = []
    origenes = [origen for origen in origenes_cors if str(origen).strip()]
    if origenes:
        intermedios.append(
            Middleware(
                CORSMiddleware,
                allow_origins=origenes,
                allow_methods=["POST"],
                allow_headers=["content-type", "accept", "x-cae-principal-desarrollo"],
            )
        )
    return Starlette(
        routes=[
            Route("/lecturas/{capacidad}", _lectura, methods=["POST"]),
            Route("/comandos/{capacidad}", _comando, methods=["POST"]),
            Route("/documentos", _documento, methods=["POST"]),
        ],
        middleware=intermedios,
        exception_handlers={HTTPException: _fuera_de_ruta},
    )


__all__ = [
    "CABECERAS_BASE",
    "CAMPOS_CONTEXTO",
    "TAMANO_MAXIMO_CUERPO",
    "capacidad_del_documento",
    "crear_app",
]
