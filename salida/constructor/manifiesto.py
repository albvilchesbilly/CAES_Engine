"""Manifiesto interno e integridad total (S3.3, `ADR-008`, `docs/03` §9).

El manifiesto es **una fotografia fechada del paquete**, no una vista que se recalcula: se genera una vez,
se sella con su propio hash y `verificar()` lo contrasta contra los ficheros reales diciendo **que** cambio
(que fichero, y si falta, sobra o esta alterado), no solo que algo cambio.

Cinco hashes, todos SHA-256 y todos sobre el **JSON canonico del log** (`engine.eventos.json_canonico`:
claves ordenadas, UTF-8, sin espacios, `Decimal` y fechas como cadena). No hay una segunda canonicalizacion
en este repositorio, y este modulo no la introduce:

| Hash | Sobre que |
|---|---|
| `sha256` de cada fichero | Los bytes tal y como entraron en ingesta. **No se recalculan**: se toman de
  `DocumentoRef.sha256`, que `engine.ingesta` calculo antes de cualquier transformacion; `verificar` es
  quien lee el disco y los contrasta |
| `hash_cabecera` | `json_canonico` de la cabecera de la actuacion |
| `hash_detalle` | `json_canonico` de unidades, variables de actuacion, evaluacion y calculo |
| `hash_log_eventos` | El `hash` del ultimo evento, que ya encadena todo el log; `None` si no se pasa log |
| `hash_manifiesto` | `json_canonico` del manifiesto **sin** ese campo: cualquier manipulacion posterior
  lo invalida |

Decisiones de este modulo (van al `ADR-008`):

- **La cabecera esta vacia hoy.** `hash_cabecera` se calcula igualmente sobre `{}`: es el hash real de un
  contenido real, no un hueco. Cuando S3.2 llene la cabecera (`cabecera_v1.yaml`, aprobacion de Billy) el
  hash cambiara y los manifiestos antiguos seguiran siendo verificables contra su propio contenido.
- **Los hashes se calculan sobre `engine.modelo.a_dict(actuacion)`**, la serializacion oficial del modelo
  canonico, y no sobre las dataclasses: asi `Decimal` y fechas tienen **una** forma textual, la del modelo,
  y no dos segun por donde entren.
- **Las rutas se resuelven por huella, nunca por nombre de fichero** (`CLAUDE.md` §2). `construir` indexa el
  paquete por SHA-256 con el mismo criterio de ficheros que la ingesta (`engine.ingesta.ficheros_de`) y
  coloca cada `DocumentoRef` en la ruta cuya huella coincide. Si una huella no esta, el paquete ya no es el
  que se evaluo y el manifiesto **no se genera** (`ErrorManifiesto`).
- **`raiz` es obligatoria en la practica.** La firma la deja opcional (`ADR-008`), pero sin la raiz del
  paquete no hay ruta que declarar y un manifiesto sin rutas daria por ausente todo el paquete al
  verificarlo: se rechaza con un mensaje que lo explica.
- **Un PDF combinado figura entero y ademas por sus partes.** El combinado es el fichero que entrego el
  cliente y es el que se verifica contra el disco; cada parte separada por `engine.ingesta` se declara con
  su `origen` (el SHA-256 del combinado) y una ruta `«ruta del combinado»#«doc_id de la parte»`, que **no es
  un fichero en disco** y por eso no se busca alli: una parte se sostiene sobre su combinado, y si el
  combinado cambia, sus partes se dan por alteradas tambien.
- **El manifiesto describe, no juzga.** Un caso con conflicto entre fuentes o sin registro produce su
  manifiesto igual que uno completo: el veredicto es del Rules Engine y viaja en el detalle.

El formato del manifiesto **oficial** de la plataforma (algoritmo de hash, estructura, campos) no esta
publicado. Lo que construye este modulo es el nuestro; el mapeo al oficial vivira en `mapping/`, nunca aqui.
# TODO(API-02): ver docs/HUECOS.md

Nada de `eval`, `exec`, `compile` ni coma flotante. Importa de `engine/` y de nada mas; `engine/` no importa
de `salida/` (test de la Fase 0, y uno propio en `tests/test_manifiesto.py`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from engine.eventos import ErrorEvento, ahora_utc, json_canonico, normalizar_instante, texto_instante
from engine.ingesta import ficheros_de, sha256_bytes, sha256_texto
from engine.modelo import ActuacionCanonica, a_dict

#: Version del formato **de nuestro** manifiesto. Nada que ver con el oficial.
#: TODO(API-02): ver docs/HUECOS.md
MANIFIESTO_VERSION = "1.0"

#: Bloques del modelo canonico que componen el detalle de la actuacion (`ADR-008`, tabla de hashes).
CLAVES_DETALLE = ("unidades", "variables_actuacion", "evaluacion", "calculo")

#: Separador entre la ruta del PDF combinado y el `doc_id` de una de sus partes (ver cabecera).
SEPARADOR_PARTE = "#"


class ErrorManifiesto(Exception):
    """El manifiesto no se puede construir o verificar: falta la raiz, falta un fichero o sobra un tipo."""


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FicheroManifiesto:
    """Un fichero del paquete tal y como entro en ingesta (o una parte de un PDF combinado).

    `ruta` es relativa a la raiz del paquete, en forma POSIX, estable y ordenable. `sha256` es la huella de
    los bytes originales, calculada por la ingesta antes de cualquier transformacion; nunca se recalcula al
    construir. `origen` es el SHA-256 del PDF combinado del que se separo esta parte, o `None`.
    """

    ruta: str
    tipo: str | None
    sha256: str
    bytes: int
    origen: str | None = None

    @property
    def es_parte(self) -> bool:
        """Una parte de un PDF combinado: no es un fichero en disco, se sostiene sobre su `origen`."""
        return self.origen is not None

    def a_dict(self) -> dict[str, object]:
        return {
            "ruta": self.ruta,
            "tipo": self.tipo,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "origen": self.origen,
        }


@dataclass(frozen=True)
class Manifiesto:
    """Que se entrega, con que huella y bajo que ficha (`docs/03` §9). Inmutable y sellado por su hash."""

    actuacion_id: str
    codigo_identificativo_propio: str
    modelo_version: str
    manifiesto_version: str
    generado_en: datetime  # UTC explicito, siempre
    ficha: Mapping[str, object]
    ficheros: tuple[FicheroManifiesto, ...]  # orden estable por `ruta`
    hash_cabecera: str
    hash_detalle: str
    hash_log_eventos: str | None
    hash_manifiesto: str

    def contenido(self) -> dict[str, object]:
        """El manifiesto **sin** `hash_manifiesto`: exactamente lo que se sella (`ADR-008`)."""
        return {
            "actuacion_id": self.actuacion_id,
            "codigo_identificativo_propio": self.codigo_identificativo_propio,
            "modelo_version": self.modelo_version,
            "manifiesto_version": self.manifiesto_version,
            "generado_en": texto_instante(self.generado_en),
            "ficha": dict(self.ficha),
            "ficheros": [fichero.a_dict() for fichero in self.ficheros],
            "hash_cabecera": self.hash_cabecera,
            "hash_detalle": self.hash_detalle,
            "hash_log_eventos": self.hash_log_eventos,
        }

    def a_dict(self) -> dict[str, object]:
        """El manifiesto entero como JSON puro (`json.dumps` lo acepta sin `default=`)."""
        return {**self.contenido(), "hash_manifiesto": self.hash_manifiesto}

    def a_json(self) -> str:
        """La forma canonica del manifiesto entero: dos manifiestos iguales dan la misma cadena."""
        return json_canonico(self.a_dict())

    def fichero(self, ruta: str) -> FicheroManifiesto | None:
        """El fichero declarado con esa ruta, o `None`."""
        for fichero in self.ficheros:
            if fichero.ruta == ruta:
                return fichero
        return None


@dataclass(frozen=True)
class ResultadoVerificacion:
    """Que dice el disco del manifiesto. `integro` es cierto solo si no hay nada en las tres listas."""

    integro: bool
    alterados: tuple[str, ...] = ()  # ruta de cada fichero cuyo sha256 no coincide
    ausentes: tuple[str, ...] = ()  # declarados que no estan en el paquete
    sobrantes: tuple[str, ...] = ()  # ficheros del paquete que el manifiesto no declara
    motivo: str | None = None  # si el propio `hash_manifiesto` no cuadra

    def a_dict(self) -> dict[str, object]:
        return {
            "integro": self.integro,
            "alterados": list(self.alterados),
            "ausentes": list(self.ausentes),
            "sobrantes": list(self.sobrantes),
            "motivo": self.motivo,
        }


# ---------------------------------------------------------------------------
# Hashes
# ---------------------------------------------------------------------------


def hash_canonico(valor: object) -> str:
    """SHA-256 del JSON canonico de `valor`. La unica forma de hashear contenido en este modulo."""
    return sha256_texto(json_canonico(valor))


def hash_de_manifiesto(manifiesto: Manifiesto) -> str:
    """El hash que sella un manifiesto: sobre su contenido **sin** `hash_manifiesto` (`ADR-008`)."""
    return hash_canonico(manifiesto.contenido())


def _hashes_de_payload(documento: Mapping[str, object]) -> tuple[str, str]:
    """`(hash_cabecera, hash_detalle)` del modelo canonico ya serializado."""
    cabecera = documento.get("cabecera", {})
    detalle = {clave: documento.get(clave) for clave in CLAVES_DETALLE}
    return hash_canonico(cabecera), hash_canonico(detalle)


def _hash_de_log(log: object, actuacion_id: str) -> str | None:
    """El hash del ultimo evento del log, que ya encadena todo (`docs/03` §6.1). Sin log, `None`."""
    if log is None:
        return None
    hash_actual = getattr(log, "hash_actual", None)
    if not isinstance(hash_actual, str):
        raise ErrorManifiesto(f"`log` no parece un LogEventos: no tiene `hash_actual` ({type(log).__name__})")
    del_log = getattr(log, "actuacion_id", actuacion_id)
    if str(del_log) != str(actuacion_id):
        raise ErrorManifiesto(
            f"el log es de la actuacion {del_log!r} y el manifiesto de {actuacion_id!r}: no se mezclan"
        )
    return hash_actual or None  # un log vacio no encadena nada


# ---------------------------------------------------------------------------
# El paquete en disco
# ---------------------------------------------------------------------------


def _raiz(raiz: object, que: str) -> Path:
    if raiz is None:
        raise ErrorManifiesto(
            f"{que} necesita la raiz del paquete: sin ella no hay ruta que declarar y el manifiesto "
            "daria por ausente todo el paquete al verificarlo"
        )
    if not isinstance(raiz, str | Path):
        raise ErrorManifiesto(f"`raiz` debe ser una ruta, no {type(raiz).__name__}")
    carpeta = Path(raiz)
    if not carpeta.is_dir():
        raise ErrorManifiesto(f"la raiz del paquete no es una carpeta: {carpeta}")
    return carpeta


def _ruta_relativa(fichero: Path, raiz: Path) -> str:
    """Ruta del fichero relativa a la raiz, siempre en forma POSIX (estable entre sistemas)."""
    return fichero.relative_to(raiz).as_posix()


def huellas_del_paquete(raiz: Path) -> dict[str, str]:
    """`{ruta relativa: sha256}` de los ficheros del paquete, con el criterio de ingesta (mismo universo).

    Es el unico sitio de este modulo que lee bytes del disco: `construir` lo usa para **colocar** cada
    documento en su ruta por huella y `verificar` para contrastar las huellas declaradas.
    """
    return {_ruta_relativa(f, raiz): sha256_bytes(f.read_bytes()) for f in ficheros_de(raiz)}


def _rutas_por_huella(huellas: Mapping[str, str]) -> dict[str, list[str]]:
    indice: dict[str, list[str]] = {}
    for ruta in sorted(huellas):
        indice.setdefault(huellas[ruta], []).append(ruta)
    return indice


# ---------------------------------------------------------------------------
# Construccion
# ---------------------------------------------------------------------------


def _documentos_de(actuacion: ActuacionCanonica) -> Sequence[object]:
    documentos = getattr(actuacion, "documentos", None)
    if not isinstance(documentos, Sequence):
        raise ErrorManifiesto("la actuacion canonica no trae `documentos`")
    return documentos


def _ficheros_de(actuacion: ActuacionCanonica, raiz: Path) -> tuple[FicheroManifiesto, ...]:
    """Cada `DocumentoRef` en su ruta, localizada **por huella** (nunca por nombre de fichero)."""
    indice = _rutas_por_huella(huellas_del_paquete(raiz))
    pendientes = {huella: list(rutas) for huella, rutas in indice.items()}
    ruta_de_huella: dict[str, str] = {}
    ficheros: list[FicheroManifiesto] = []
    partes: list[object] = []

    for documento in _documentos_de(actuacion):
        if documento.origen is not None:  # las partes van despues: necesitan la ruta de su combinado
            partes.append(documento)
            continue
        if documento.sha256 not in indice:
            raise ErrorManifiesto(
                f"el paquete {raiz} no contiene ningun fichero con la huella {documento.sha256}: "
                "no es el paquete que se evaluo y el manifiesto no se genera sobre otro"
            )
        # Dos ficheros identicos son dos entradas del manifiesto, cada una en su ruta; si la ingesta
        # trajera mas documentos que ficheros con esa huella, el ultimo repite ruta (no se inventa una).
        disponibles = pendientes[documento.sha256]
        ruta = disponibles.pop(0) if disponibles else indice[documento.sha256][-1]
        ruta_de_huella.setdefault(documento.sha256, ruta)
        ficheros.append(
            FicheroManifiesto(
                ruta=ruta,
                tipo=documento.tipo,
                sha256=documento.sha256,
                bytes=documento.bytes,
                origen=None,
            )
        )

    for parte in partes:
        ruta_combinado = ruta_de_huella.get(parte.origen)
        if ruta_combinado is None:
            raise ErrorManifiesto(
                f"la parte {parte.doc_id} dice venir del combinado {parte.origen}, que no esta en el paquete"
            )
        ficheros.append(
            FicheroManifiesto(
                ruta=f"{ruta_combinado}{SEPARADOR_PARTE}{parte.doc_id}",
                tipo=parte.tipo,
                sha256=parte.sha256,
                bytes=parte.bytes,
                origen=parte.origen,
            )
        )

    return tuple(sorted(ficheros, key=lambda f: f.ruta))


def construir(
    actuacion_canonica: ActuacionCanonica,
    *,
    log: object | None = None,
    generado_en: datetime | None = None,
    raiz: str | Path | None = None,
) -> Manifiesto:
    """El manifiesto interno de una actuacion canonica sobre el paquete que hay en `raiz` (ver cabecera).

    `log` es el `LogEventos` de la actuacion, si lo hay: aporta `hash_log_eventos`. `generado_en` se usa tal
    cual (en UTC; un instante sin zona es un error): pasandolo explicito, dos construcciones del mismo
    paquete dan el mismo JSON byte a byte. Sin el, se mira el reloj una sola vez, en UTC.
    """
    if not isinstance(actuacion_canonica, ActuacionCanonica):
        raise ErrorManifiesto(
            f"construir espera una ActuacionCanonica, no {type(actuacion_canonica).__name__}"
        )
    carpeta = _raiz(raiz, "construir")
    try:
        instante = normalizar_instante(generado_en) if generado_en is not None else ahora_utc()
    except ErrorEvento as exc:  # un `datetime` naive: nunca `datetime.now()` sin zona
        raise ErrorManifiesto(f"`generado_en` invalido: {exc}") from exc

    documento = a_dict(actuacion_canonica)
    hash_cabecera, hash_detalle = _hashes_de_payload(documento)
    manifiesto = Manifiesto(
        actuacion_id=actuacion_canonica.id,
        codigo_identificativo_propio=actuacion_canonica.codigo_identificativo_propio,
        modelo_version=actuacion_canonica.modelo_version,
        manifiesto_version=MANIFIESTO_VERSION,
        generado_en=instante,
        ficha=MappingProxyType(dict(actuacion_canonica.ficha)),
        ficheros=_ficheros_de(actuacion_canonica, carpeta),
        hash_cabecera=hash_cabecera,
        hash_detalle=hash_detalle,
        hash_log_eventos=_hash_de_log(log, actuacion_canonica.id),
        hash_manifiesto="",
    )
    return replace(manifiesto, hash_manifiesto=hash_de_manifiesto(manifiesto))


# ---------------------------------------------------------------------------
# Verificacion
# ---------------------------------------------------------------------------


def verificar(manifiesto: Manifiesto, *, raiz: str | Path) -> ResultadoVerificacion:
    """Contrasta el manifiesto contra los ficheros reales de `raiz` y dice **que** cambio (ver cabecera).

    Tres listas y un motivo: `alterados` (la huella del disco no es la declarada), `ausentes` (declarado y
    no esta), `sobrantes` (esta y no se declaro) y `motivo` cuando el propio `hash_manifiesto` no cuadra,
    es decir cuando el manifiesto se manipulo despues de sellarse.
    """
    if not isinstance(manifiesto, Manifiesto):
        raise ErrorManifiesto(f"verificar espera un Manifiesto, no {type(manifiesto).__name__}")
    carpeta = _raiz(raiz, "verificar")

    motivo: str | None = None
    sellado = hash_de_manifiesto(manifiesto)
    if sellado != manifiesto.hash_manifiesto:
        motivo = (
            "el manifiesto se altero despues de sellarse: su contenido tiene hash "
            f"{sellado} y declara {manifiesto.hash_manifiesto}"
        )

    huellas = huellas_del_paquete(carpeta)
    alterados: list[str] = []
    ausentes: list[str] = []
    declaradas: set[str] = set()

    for fichero in manifiesto.ficheros:
        if fichero.es_parte:
            continue  # una parte no es un fichero en disco: se resuelve despues, por su combinado
        declaradas.add(fichero.ruta)
        huella = huellas.get(fichero.ruta)
        if huella is None:
            ausentes.append(fichero.ruta)
        elif huella != fichero.sha256:
            alterados.append(fichero.ruta)

    for fichero in manifiesto.ficheros:
        if not fichero.es_parte:
            continue
        combinado = manifiesto.fichero(fichero.ruta.split(SEPARADOR_PARTE)[0])
        if combinado is None or combinado.ruta in ausentes:
            ausentes.append(fichero.ruta)  # sin el combinado, la parte no se sostiene
        elif combinado.ruta in alterados:
            alterados.append(fichero.ruta)  # el combinado cambio: sus partes ya no son demostrables

    sobrantes = [ruta for ruta in sorted(huellas) if ruta not in declaradas]
    return ResultadoVerificacion(
        integro=not (alterados or ausentes or sobrantes) and motivo is None,
        alterados=tuple(sorted(alterados)),
        ausentes=tuple(sorted(ausentes)),
        sobrantes=tuple(sobrantes),
        motivo=motivo,
    )


__all__ = [
    "CLAVES_DETALLE",
    "MANIFIESTO_VERSION",
    "SEPARADOR_PARTE",
    "ErrorManifiesto",
    "FicheroManifiesto",
    "Manifiesto",
    "ResultadoVerificacion",
    "construir",
    "hash_canonico",
    "hash_de_manifiesto",
    "huellas_del_paquete",
    "verificar",
]
