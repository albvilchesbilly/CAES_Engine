"""Mapeo declarativo modelo canonico -> destino (C5 de `ADR-009` §3, `docs/03` §10.1).

Dar de alta una ficha en la salida es **anadir un YAML**, no escribir codigo (regla de oro 4). Este modulo
no sabe que ficha esta procesando: que variable va a que campo del destino lo dice
`mapping/<FICHA>.<destino>.yaml`, y aqui solo se **selecciona**.

Que significa "solo selecciona":

- `origen` es una **ruta punteada del modelo canonico ya serializado** (`engine.modelo.a_dict`), por ejemplo
  `variables_actuacion.titular_nif.valor_consumido`. Nada mas: ni expresion, ni funcion, ni condicional, ni
  comodin, ni `eval`. Un mapeo no calcula, no convierte unidades y no redondea: los `Decimal` salen tal y
  como los dio el modelo canonico, es decir como cadena.
- **Indices de lista**: un paso que sea un entero no negativo indexa una lista (`partes.0.nif`). Es la unica
  forma de entrar en una lista; no hay filtros ni busquedas.
- **Claves con punto**: el modelo canonico tiene claves que llevan punto (`convenio.ahorro_kwh`,
  `registro.dias`). Al descender por un mapa se prueba primero la clave mas larga que encaje con el resto de
  la ruta, asi que `variables_actuacion.convenio.ahorro_kwh.valor_consumido` resuelve sin comillas ni
  escapes. Sigue siendo seleccion pura: la ruta no elige, solo nombra.

Tres criterios que este modulo hereda de `engine/spec_registry.py` y de `ADR-009` §3, y por que:

1. **Una clave desconocida en el YAML es error de carga**, no un campo que se ignora en silencio. Un mapeo
   con una errata se descubre al cargarlo, no en mitad de una entrega al tenant.
2. **Un `origen` que no resuelve deja el campo a `null`**; si el campo es `obligatorio`, su clave entra en
   `carencias`. Eso **no** es un error: declarado != demostrado (`CLAUDE.md` §2 regla 5) y el tenant tiene
   derecho a ver en la carpeta que recibe que le falta.
3. **Un campo con `hueco` no puede ser `obligatorio`**: un hueco es lo que todavia no sabemos pedir
   (`TODO(API-08)`: ver docs/HUECOS.md), y exigir lo que no se sabe pedir seria inventarselo.

Nada de aqui imita un campo de la API oficial. El destino `handoff` es **nuestro** formato; el destino `api`
no tiene fichero todavia. TODO(API-01) y TODO(API-08): ver docs/HUECOS.md.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import yaml

from engine.modelo import ActuacionCanonica, a_dict
from salida.puerto import DESTINOS, ErrorSalida

#: Donde viven los mapeos (`docs/01` §3.9). Es el valor por defecto de `carpeta` en `cargar`.
CARPETA_MAPEOS = Path(__file__).resolve().parents[1] / "mapping"

#: Extension de un fichero de mapeo. El nombre es `<FICHA>.<destino>.yaml` y se comprueba al cargar.
EXTENSION_MAPEO = ".yaml"

#: Bloques admitidos en la raiz de un mapeo de ficha. Cualquier otro es error de carga.
BLOQUES_MAPEO = ("mapeo", "cabecera", "detalle_actuacion", "detalle_unidad", "documentos", "ficheros")

#: Claves del bloque de identidad `mapeo:`.
CLAVES_IDENTIDAD = ("id", "ficha", "destino", "version")

#: Claves de un campo. Son exactamente los atributos de `Campo` (contrato C5).
CLAVES_CAMPO = ("clave", "etiqueta", "origen", "unidad", "obligatorio", "nota", "hueco")

#: Claves del bloque `documentos`: como se agrupan los adjuntos en la carpeta del destino.
CLAVES_DOCUMENTOS = ("carpeta", "por_tipo", "sin_tipo")

#: Un hueco es un identificador de `docs/HUECOS.md`, nunca texto libre: si no tiene esta forma, no es un
#: hueco enumerado y el mapeo no carga (regla de oro 10). Se contrasta con `re.fullmatch`, no se precompila:
#: en `salida/` no se compila texto de ninguna clase (hay un test del banco que lo comprueba).
PATRON_HUECO = r"API-\d{2}"

#: Bloques admitidos en la raiz de un mapeo de render del manifiesto (`mapping/manifiesto.<destino>.yaml`).
BLOQUES_MANIFIESTO = ("manifiesto", "campos", "ficheros")

#: Nombre del mapeo de render del manifiesto, por destino.
NOMBRE_MANIFIESTO = "manifiesto"

#: Clave con la que el contexto de una unidad ve su resultado de calculo (ver `aplicar`). No es un nombre
#: de ninguna ficha: es como se llama el bloque en el modelo canonico.
CLAVE_CALCULO_EN_UNIDAD = "calculo"

#: Campo por el que `calculo.por_unidad[]` dice a que unidad pertenece cada resultado. Es un campo del
#: **nucleo** (`engine.calculo.ResultadoUnidad`), la identidad de unidad del modelo, no un nombre de ficha.
CLAVE_UNIDAD_EN_CALCULO = "num_serie_motor"


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Campo:
    """Un campo del destino: de donde sale, como se llama para una persona y si falta cuando no esta.

    `unidad` es documentacion, **no** una instruccion de conversion: nadie convierte nada aqui. `hueco` es
    el `API-xx` que este campo espera para existir de verdad en el destino oficial.
    """

    clave: str
    etiqueta: str
    origen: str | None = None
    unidad: str | None = None
    obligatorio: bool = False
    nota: str | None = None
    hueco: str | None = None

    def a_dict(self) -> dict[str, object]:
        return {
            "clave": self.clave,
            "etiqueta": self.etiqueta,
            "origen": self.origen,
            "unidad": self.unidad,
            "obligatorio": self.obligatorio,
            "nota": self.nota,
            "hueco": self.hueco,
        }


@dataclass(frozen=True)
class Mapeo:
    """Un mapeo de ficha a destino, ya validado. Inmutable: cargarlo dos veces da lo mismo.

    `cabecera` puede venir vacia: la spec transversal de cabecera comun es S3.2 y depende de la aprobacion
    de Billy. El bloque existe siempre; su contenido lo pone el YAML, nunca este modulo.
    """

    id: str
    ficha: str
    destino: str
    version: str
    cabecera: tuple[Campo, ...]
    detalle_actuacion: tuple[Campo, ...]
    detalle_unidad: tuple[Campo, ...]
    documentos: Mapping[str, object]
    ficheros: Mapping[str, str]

    def carpeta_de_tipo(self, tipo: str | None) -> str:
        """Subcarpeta en la que va un adjunto de ese tipo documental. Un tipo no declarado va al cajon."""
        por_tipo = self.documentos.get("por_tipo") or {}
        sin_tipo = str(self.documentos.get("sin_tipo") or "otros")
        if tipo is None:
            return sin_tipo
        return str(por_tipo.get(tipo, sin_tipo))

    def fichero(self, clave: str) -> str:
        """Nombre del fichero del arbol del destino declarado bajo esa clave."""
        nombre = self.ficheros.get(clave)
        if nombre is None:
            raise ErrorSalida(
                f"el mapeo {self.id} no declara el fichero {clave!r}; declara {sorted(self.ficheros)}"
            )
        return nombre

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "ficha": self.ficha,
            "destino": self.destino,
            "version": self.version,
            "cabecera": [c.a_dict() for c in self.cabecera],
            "detalle_actuacion": [c.a_dict() for c in self.detalle_actuacion],
            "detalle_unidad": [c.a_dict() for c in self.detalle_unidad],
            "documentos": dict(self.documentos),
            "ficheros": dict(self.ficheros),
        }


@dataclass(frozen=True)
class RenderManifiesto:
    """Como se presenta el manifiesto interno dentro del destino (`mapping/manifiesto.<destino>.yaml`).

    **No duplica el calculo de hashes**: el manifiesto lo produce `salida/constructor/` y se escribe tal
    cual. Esto es solo nombre de fichero, orden y etiquetas de sus campos, para que la carpeta que recibe
    una persona se lea sin conocer nuestro esquema.
    """

    id: str
    destino: str
    version: str
    fichero: str
    campos: tuple[Campo, ...]
    ficheros: Mapping[str, str]  # etiqueta de cada columna de la tabla de ficheros del manifiesto

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "destino": self.destino,
            "version": self.version,
            "fichero": self.fichero,
            "campos": [c.a_dict() for c in self.campos],
            "ficheros": dict(self.ficheros),
        }


# ---------------------------------------------------------------------------
# Resolucion de rutas
# ---------------------------------------------------------------------------


def _es_indice(paso: str) -> bool:
    return paso.isdigit()


def resolver(documento: object, ruta: str) -> object:
    """El valor que hay en `ruta` dentro de `documento`, o `None` si la ruta no lleva a ninguna parte.

    `documento` es el modelo canonico **ya serializado** (`engine.modelo.a_dict`). La ruta es punteada, con
    indices enteros para listas y con la regla de clave mas larga para las claves que llevan punto (ver la
    cabecera del modulo). Una ruta vacia o que no sea cadena es error: eso es un mapeo mal escrito, no un
    dato ausente.
    """
    if not isinstance(ruta, str) or not ruta.strip():
        raise ErrorSalida(f"una ruta de origen debe ser una cadena no vacia, no {ruta!r}")
    pasos = ruta.split(".")
    if any(not paso for paso in pasos):
        raise ErrorSalida(f"ruta de origen mal formada: {ruta!r} tiene un paso vacio")
    actual: object = documento
    posicion = 0
    while posicion < len(pasos):
        if actual is None:
            return None
        if isinstance(actual, Mapping):
            elegida: tuple[str, int] | None = None
            for fin in range(len(pasos), posicion, -1):  # la clave mas larga primero: `convenio.ahorro_kwh`
                clave = ".".join(pasos[posicion:fin])
                if clave in actual:
                    elegida = (clave, fin)
                    break
            if elegida is None:
                return None
            actual = actual[elegida[0]]
            posicion = elegida[1]
        elif isinstance(actual, Sequence) and not isinstance(actual, str | bytes):
            paso = pasos[posicion]
            if not _es_indice(paso) or int(paso) >= len(actual):
                return None
            actual = actual[int(paso)]
            posicion += 1
        else:
            return None
    return actual


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------


def _mapa(valor: object, contexto: str) -> dict[str, object]:
    if not isinstance(valor, Mapping):
        raise ErrorSalida(f"{contexto}: debe ser un mapa, no {type(valor).__name__}")
    return {str(clave): valor[clave] for clave in valor}


def _sin_desconocidas(valor: Mapping[str, object], admitidas: Sequence[str], contexto: str) -> None:
    """Criterio de `engine/spec_registry.py`: una clave que no esperamos es error **de carga**."""
    desconocidas = sorted(set(valor) - set(admitidas))
    if desconocidas:
        raise ErrorSalida(
            f"{contexto}: claves desconocidas {desconocidas}; las admitidas son {list(admitidas)}"
        )


def _texto(valor: object, contexto: str, *, obligatorio: bool = True) -> str | None:
    if valor is None:
        if obligatorio:
            raise ErrorSalida(f"{contexto}: falta")
        return None
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorSalida(f"{contexto}: debe ser una cadena no vacia, no {valor!r}")
    return valor


def _campo(crudo: object, contexto: str) -> Campo:
    datos = _mapa(crudo, contexto)
    _sin_desconocidas(datos, CLAVES_CAMPO, contexto)
    clave = _texto(datos.get("clave"), f"{contexto}.clave")
    obligatorio = datos.get("obligatorio", False)
    if not isinstance(obligatorio, bool):
        raise ErrorSalida(f"{contexto}.obligatorio: debe ser true o false, no {obligatorio!r}")
    hueco = _texto(datos.get("hueco"), f"{contexto}.hueco", obligatorio=False)
    if hueco is not None and not re.fullmatch(PATRON_HUECO, hueco):
        raise ErrorSalida(
            f"{contexto}.hueco: {hueco!r} no tiene la forma API-nn de docs/HUECOS.md; un hueco se enumera, "
            "no se describe"
        )
    if hueco is not None and obligatorio:
        raise ErrorSalida(
            f"{contexto}: un campo con hueco ({hueco}) no puede ser obligatorio; es lo que todavia no "
            "sabemos pedir (ADR-009 §3)"
        )
    origen = _texto(datos.get("origen"), f"{contexto}.origen", obligatorio=False)
    if origen is None and hueco is None:
        raise ErrorSalida(
            f"{contexto}: un campo sin `origen` solo se admite si declara su `hueco` (API-nn); si no, es un "
            "campo inventado"
        )
    if origen is not None:
        resolver({}, origen)  # valida la forma de la ruta al cargar, no al entregar
    return Campo(
        clave=str(clave),
        etiqueta=str(_texto(datos.get("etiqueta"), f"{contexto}.etiqueta")),
        origen=origen,
        unidad=_texto(datos.get("unidad"), f"{contexto}.unidad", obligatorio=False),
        obligatorio=obligatorio,
        nota=_texto(datos.get("nota"), f"{contexto}.nota", obligatorio=False),
        hueco=hueco,
    )


def _campos(crudo: object, contexto: str) -> tuple[Campo, ...]:
    if crudo is None:
        return ()
    if not isinstance(crudo, list):
        raise ErrorSalida(f"{contexto}: debe ser una lista de campos, no {type(crudo).__name__}")
    campos = tuple(_campo(elemento, f"{contexto}[{indice}]") for indice, elemento in enumerate(crudo))
    claves = [campo.clave for campo in campos]
    repetidas = sorted({clave for clave in claves if claves.count(clave) > 1})
    if repetidas:
        raise ErrorSalida(f"{contexto}: claves repetidas {repetidas}")
    return campos


def _documentos(crudo: object, contexto: str) -> Mapping[str, object]:
    datos = _mapa(crudo, contexto)
    _sin_desconocidas(datos, CLAVES_DOCUMENTOS, contexto)
    carpeta = _texto(datos.get("carpeta"), f"{contexto}.carpeta")
    por_tipo = _mapa(datos.get("por_tipo") or {}, f"{contexto}.por_tipo")
    for tipo, destino in por_tipo.items():
        _texto(destino, f"{contexto}.por_tipo.{tipo}")
    return MappingProxyType(
        {
            "carpeta": str(carpeta),
            "por_tipo": MappingProxyType({tipo: str(valor) for tipo, valor in por_tipo.items()}),
            "sin_tipo": str(_texto(datos.get("sin_tipo"), f"{contexto}.sin_tipo")),
        }
    )


def _ficheros(crudo: object, contexto: str) -> Mapping[str, str]:
    datos = _mapa(crudo, contexto)
    for clave, valor in datos.items():
        _texto(valor, f"{contexto}.{clave}")
    return MappingProxyType({clave: str(valor) for clave, valor in datos.items()})


def _leer(ruta: Path) -> dict[str, object]:
    if not ruta.is_file():
        raise ErrorSalida(f"no existe el mapeo {ruta}")
    try:
        crudo = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ErrorSalida(f"{ruta.name}: YAML ilegible: {exc}") from exc
    return _mapa(crudo, ruta.name)


def _destino(destino: str) -> str:
    if destino not in DESTINOS:
        raise ErrorSalida(f"destino desconocido: {destino!r}; los declarados son {list(DESTINOS)}")
    return destino


def cargar(ficha: str, destino: str, *, carpeta: str | Path | None = None) -> Mapeo:
    """El mapeo `<ficha>.<destino>.yaml` de `carpeta` (por defecto `mapping/`), validado entero.

    Falla **al cargar** ante cualquier defecto: clave desconocida, campo sin origen ni hueco, hueco
    obligatorio, clave repetida o identidad que no cuadra con el nombre del fichero. Nunca a mitad de una
    entrega.
    """
    destino = _destino(destino)
    base = Path(carpeta) if carpeta is not None else CARPETA_MAPEOS
    ruta = base / f"{ficha}.{destino}{EXTENSION_MAPEO}"
    crudo = _leer(ruta)
    _sin_desconocidas(crudo, BLOQUES_MAPEO, ruta.name)

    identidad = _mapa(crudo.get("mapeo"), f"{ruta.name}: bloque 'mapeo'")
    _sin_desconocidas(identidad, CLAVES_IDENTIDAD, f"{ruta.name}: bloque 'mapeo'")
    declarada_ficha = str(_texto(identidad.get("ficha"), f"{ruta.name}: mapeo.ficha"))
    declarado_destino = str(_texto(identidad.get("destino"), f"{ruta.name}: mapeo.destino"))
    if (declarada_ficha, declarado_destino) != (ficha, destino):
        raise ErrorSalida(
            f"{ruta.name}: el fichero dice ser de {declarada_ficha}/{declarado_destino} y se pidio "
            f"{ficha}/{destino}; el nombre del fichero y su identidad tienen que coincidir"
        )

    return Mapeo(
        id=str(_texto(identidad.get("id"), f"{ruta.name}: mapeo.id")),
        ficha=declarada_ficha,
        destino=declarado_destino,
        version=str(_texto(identidad.get("version"), f"{ruta.name}: mapeo.version")),
        cabecera=_campos(crudo.get("cabecera"), f"{ruta.name}: cabecera"),
        detalle_actuacion=_campos(crudo.get("detalle_actuacion"), f"{ruta.name}: detalle_actuacion"),
        detalle_unidad=_campos(crudo.get("detalle_unidad"), f"{ruta.name}: detalle_unidad"),
        documentos=_documentos(crudo.get("documentos"), f"{ruta.name}: documentos"),
        ficheros=_ficheros(crudo.get("ficheros"), f"{ruta.name}: ficheros"),
    )


def cargar_manifiesto(destino: str, *, carpeta: str | Path | None = None) -> RenderManifiesto:
    """El render del manifiesto interno en ese destino (`mapping/manifiesto.<destino>.yaml`).

    Sus `origen` son rutas punteadas **del manifiesto serializado** (`Manifiesto.a_dict`), no del modelo
    canonico: es el unico documento de este modulo que no se resuelve contra la actuacion.
    """
    destino = _destino(destino)
    base = Path(carpeta) if carpeta is not None else CARPETA_MAPEOS
    ruta = base / f"{NOMBRE_MANIFIESTO}.{destino}{EXTENSION_MAPEO}"
    crudo = _leer(ruta)
    _sin_desconocidas(crudo, BLOQUES_MANIFIESTO, ruta.name)

    identidad = _mapa(crudo.get("manifiesto"), f"{ruta.name}: bloque 'manifiesto'")
    _sin_desconocidas(identidad, ("id", "destino", "version", "fichero"), f"{ruta.name}: bloque 'manifiesto'")
    declarado_destino = str(_texto(identidad.get("destino"), f"{ruta.name}: manifiesto.destino"))
    if declarado_destino != destino:
        raise ErrorSalida(
            f"{ruta.name}: el fichero dice ser del destino {declarado_destino} y se pidio {destino}"
        )
    return RenderManifiesto(
        id=str(_texto(identidad.get("id"), f"{ruta.name}: manifiesto.id")),
        destino=declarado_destino,
        version=str(_texto(identidad.get("version"), f"{ruta.name}: manifiesto.version")),
        fichero=str(_texto(identidad.get("fichero"), f"{ruta.name}: manifiesto.fichero")),
        campos=_campos(crudo.get("campos"), f"{ruta.name}: campos"),
        ficheros=_ficheros(crudo.get("ficheros"), f"{ruta.name}: ficheros"),
    )


# ---------------------------------------------------------------------------
# Aplicacion
# ---------------------------------------------------------------------------


def _documento_de(actuacion_canonica: object) -> Mapping[str, object]:
    if isinstance(actuacion_canonica, ActuacionCanonica):
        return a_dict(actuacion_canonica)
    if isinstance(actuacion_canonica, Mapping):  # ya serializado: util en tests y al releer un paquete
        return actuacion_canonica
    raise ErrorSalida(
        f"aplicar espera una ActuacionCanonica o su serializacion, no {type(actuacion_canonica).__name__}"
    )


def _aplicar_campos(
    campos: Sequence[Campo], documento: object, prefijo: str
) -> tuple[dict[str, object], list[str]]:
    valores: dict[str, object] = {}
    carencias: list[str] = []
    for campo in campos:
        valor = resolver(documento, campo.origen) if campo.origen is not None else None
        valores[campo.clave] = valor
        if valor is None and campo.obligatorio:
            carencias.append(f"{prefijo}{campo.clave}")
    return valores, carencias


def _calculo_por_unidad(documento: Mapping[str, object]) -> dict[str, object]:
    """`{clave de unidad: su resultado de calculo}`. Empareja por la identidad de unidad del modelo.

    No es un calculo ni una decision: el bloque `calculo.por_unidad` del modelo canonico ya dice a que
    unidad pertenece cada resultado (`CLAVE_UNIDAD_EN_CALCULO`); aqui solo se indexa por esa clave para que
    un campo de `detalle_unidad` pueda **seleccionar** el ahorro de su unidad sin salir de ella.
    """
    por_unidad = resolver(documento, "calculo.por_unidad")
    if not isinstance(por_unidad, Sequence) or isinstance(por_unidad, str | bytes):
        return {}
    indice: dict[str, object] = {}
    for resultado in por_unidad:
        clave = resolver(resultado, CLAVE_UNIDAD_EN_CALCULO)
        if isinstance(clave, str):
            indice[clave] = resultado
    return indice


def aplicar(mapeo: Mapeo, actuacion_canonica: object) -> tuple[dict[str, object], tuple[str, ...]]:
    """`(payload, carencias)` del mapeo sobre la actuacion. No calcula, no convierte y no redondea.

    El payload es **nuestro** formato: `{"cabecera": {...}, "detalle": {"actuacion": {...},
    "unidades": [{"clave": ..., "campos": {...}}]}}`. Los campos de `detalle_unidad` se resuelven contra
    **cada unidad**, no contra la actuacion entera: sus `origen` empiezan en `variables.<nombre>...`, no en
    `unidades.0...`. A esa unidad se le anade la clave `calculo` con **su** entrada de `calculo.por_unidad`
    (emparejada por la identidad de unidad del modelo), para que el ahorro de la unidad se pueda seleccionar
    sin que el mapeo tenga que saber en que posicion de la lista cayo.

    `carencias` lleva la clave de cada campo obligatorio sin valor, cualificada con su sitio en el payload
    (`detalle.unidades[MTR-0001].PM`) para que dos unidades a las que falta lo mismo no se confundan.
    """
    if not isinstance(mapeo, Mapeo):
        raise ErrorSalida(f"aplicar espera un Mapeo, no {type(mapeo).__name__}")
    documento = _documento_de(actuacion_canonica)

    cabecera, carencias = _aplicar_campos(mapeo.cabecera, documento, "cabecera.")
    actuacion, faltan = _aplicar_campos(mapeo.detalle_actuacion, documento, "detalle.actuacion.")
    carencias.extend(faltan)

    unidades: list[dict[str, object]] = []
    crudas = documento.get("unidades") or ()
    if not isinstance(crudas, Sequence) or isinstance(crudas, str | bytes):
        raise ErrorSalida(f"`unidades` del modelo canonico deberia ser una lista, no {type(crudas).__name__}")
    calculos = _calculo_por_unidad(documento)
    for indice, cruda in enumerate(crudas):
        contexto = _mapa(cruda, f"unidades[{indice}]")
        if CLAVE_CALCULO_EN_UNIDAD in contexto:
            raise ErrorSalida(
                f"unidades[{indice}] ya trae una clave {CLAVE_CALCULO_EN_UNIDAD!r}: el contexto de unidad "
                "del mapeo la reserva para el resultado de calculo de esa unidad"
            )
        clave = str(contexto.get("clave") or indice)
        contexto[CLAVE_CALCULO_EN_UNIDAD] = calculos.get(clave)
        campos, faltan = _aplicar_campos(mapeo.detalle_unidad, contexto, f"detalle.unidades[{clave}].")
        carencias.extend(faltan)
        unidades.append({"clave": clave, "campos": campos})

    payload = {"cabecera": cabecera, "detalle": {"actuacion": actuacion, "unidades": unidades}}
    return payload, tuple(carencias)


__all__ = [
    "BLOQUES_MANIFIESTO",
    "BLOQUES_MAPEO",
    "CARPETA_MAPEOS",
    "CLAVES_CAMPO",
    "CLAVES_DOCUMENTOS",
    "CLAVES_IDENTIDAD",
    "EXTENSION_MAPEO",
    "NOMBRE_MANIFIESTO",
    "PATRON_HUECO",
    "Campo",
    "Mapeo",
    "RenderManifiesto",
    "aplicar",
    "cargar",
    "cargar_manifiesto",
    "resolver",
]
