"""Matriz de perfiles y capacidades (`ADR-006`) como configuracion del nucleo (contrato C13, `ADR-011` §2).

Carga y valida `engine/capacidades.yaml`. **Ni un identificador de perfil ni uno de capacidad aparece en
este fuente**: todo lo que se sabe de quien puede hacer que sale del YAML, igual que el Spec Registry no
conoce ninguna ficha (regla de oro 4). Hay un test que lee este fichero y lo comprueba.

Por que vive en `engine/` y no en `api/`: con A8 aprobada (Billy, 19/09/2026), el log de eventos comprueba
**al sellar** que el perfil que actua puede producir ese tipo de evento. Ese control va en el log, no en el
llamante, porque una puerta que vive en una funcion se rodea escribiendo el evento a mano (es el mismo
hallazgo que `R-REQ-02` en `ADR-010`). Y `engine/` no importa de `api/`, asi que la matriz baja aqui, junto
a `engine/estados_plataforma.yaml`, que es el precedente exacto. `api/permisos.py` consume esta misma
matriz: no hay una segunda fuente de verdad.

Que se comprueba **al cargar** (todo es `ErrorCapacidades`, nunca un permiso raro en mitad de una peticion):

1. La forma, contra `engine/esquema_capacidades.json`, con el validador minimo del final de este modulo.
2. Ids unicos; ambitos, superficies, pantallas y perfiles coherentes entre si; una pantalla que declara
   perfil pertenece a la superficie de ese perfil (si no, no desempataria nada).
3. **Un comando declara eventos del catalogo cerrado** (`engine.eventos.catalogo.TIPOS`). Los que `ADR-006`
   marca "(nuevo)" y todavia no estan en el catalogo van en `eventos_propuestos`, que es lo contrario de
   inventar un evento: se declara lo que falta y la capacidad se queda **sin manejador**. En cuanto el
   catalogo los incorpore, la carga falla y obliga a moverlos a `eventos`. Una lectura no declara ninguno.
4. **Un perfil no esta a la vez en `concede` y en `pendiente`**, y una capacidad con celdas `(?)` dice que
   decision (`decide`) las cerraria. Las celdas `(?)` **se deniegan**: no se concede provisionalmente lo
   que nadie ha decidido.
5. Cada capacidad declara o `manejador` (hay implementacion) o `falta` (que es lo que lo impide). Nunca las
   dos, nunca ninguna: el contrato es completo aunque la implementacion no lo sea.

Para el enganche del log: `perfiles_que_pueden_emitir(tipo)` y `capacidades_que_producen(tipo)` responden
"quien puede generar este evento" sin que nadie tenga que recorrer la matriz por su cuenta.

No importa nada de `agentes/`, `salida/`, `api/`, `generator/` ni `tests/`. Sin `eval`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from engine.eventos.canonico import ErrorEvento
from engine.eventos.catalogo import TIPOS, TIPOS_POR_PROCESO

CARPETA = Path(__file__).resolve().parent
RUTA_MATRIZ = CARPETA / "capacidades.yaml"
RUTA_ESQUEMA = CARPETA / "esquema_capacidades.json"

#: Los dos tipos de entrada del contrato C15. Un comando escribe; una lectura proyecta.
TIPO_COMANDO = "comando"
TIPO_LECTURA = "lectura"

#: Prefijos de proceso admitidos en `capacidades[].proceso`, tomados del catalogo de eventos del nucleo.
PROCESOS = tuple(clave.split(" ", 1)[0] for clave in TIPOS_POR_PROCESO)


class ErrorCapacidades(Exception):
    """La matriz no carga, o se le pregunta por algo que no declara."""


# ---------------------------------------------------------------------------
# Lo que dice la configuracion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ambito:
    """Ambito de datos de un perfil: que bloques puede llegar a construir una lectura suya (`R-UI-12`)."""

    id: str
    nombre: str
    exige_tenant: bool
    bloques: frozenset[str]
    solo_actuaciones_propias: bool = False


@dataclass(frozen=True)
class Pantalla:
    """Una pantalla de una superficie. Si declara perfil, desempata el rol de una capacidad compartida."""

    id: str
    nombre: str
    superficie: str
    perfil: str | None


@dataclass(frozen=True)
class Superficie:
    """Una de las cuatro superficies de `ADR-050`. Sin pantallas = identidad tecnica, sin front."""

    id: str
    nombre: str
    pantallas: tuple[str, ...]


@dataclass(frozen=True)
class Perfil:
    """Un paquete de capacidades (`ADR-006`, opcion C), con su ambito de datos y su superficie."""

    id: str
    nombre: str
    ambito: str
    superficie: str


@dataclass(frozen=True)
class Condicion:
    """Celda concedida solo si se cumple algo que hoy no se puede comprobar: se deniega y se explica."""

    perfil: str
    requiere: str
    nota: str


@dataclass(frozen=True)
class Capacidad:
    """Una fila de la matriz de `ADR-006`, tal cual, sin interpretar."""

    id: str
    nombre: str
    grupo: str
    tipo: str
    concede: frozenset[str]
    pendiente: frozenset[str] = frozenset()
    decide: str | None = None
    condicionada: tuple[Condicion, ...] = ()
    proceso: str | None = None
    eventos: tuple[str, ...] = ()
    eventos_propuestos: tuple[str, ...] = ()
    efecto: str | None = None
    exige_justificacion: bool = False
    bloques: tuple[str, ...] = ()
    manejador: str | None = None
    falta: str | None = None

    @property
    def es_comando(self) -> bool:
        return self.tipo == TIPO_COMANDO

    @property
    def implementada(self) -> bool:
        """`True` si hay manejador. El contrato existe para todas; la implementacion, todavia no."""
        return self.manejador is not None

    def condicion_de(self, perfil: str) -> Condicion | None:
        for condicion in self.condicionada:
            if condicion.perfil == perfil:
                return condicion
        return None


@dataclass(frozen=True)
class Matriz:
    """La matriz cargada y validada. Se lee una vez al arrancar y no se toca despues."""

    version: str
    fuente: str
    ambitos: Mapping[str, Ambito]
    superficies: Mapping[str, Superficie]
    pantallas: Mapping[str, Pantalla]
    perfiles: Mapping[str, Perfil]
    capacidades: Mapping[str, Capacidad]
    ruta: Path | None = field(default=None, compare=False)

    def capacidad(self, identificador: str) -> Capacidad:
        declarada = self.capacidades.get(identificador)
        if declarada is None:
            raise ErrorCapacidades(f"capacidad desconocida: {identificador!r}; la matriz declara {len(self)}")
        return declarada

    def perfil(self, identificador: str) -> Perfil:
        perfil = self.perfiles.get(identificador)
        if perfil is None:
            raise ErrorCapacidades(f"perfil desconocido: {identificador!r}")
        return perfil

    def ambito_de(self, perfil: str) -> Ambito:
        """El ambito de datos del perfil con el que se esta actuando."""
        return self.ambitos[self.perfil(perfil).ambito]

    def capacidades_que_producen(self, tipo_evento: str) -> tuple[Capacidad, ...]:
        """Las capacidades que declaran ese tipo de evento del catalogo cerrado."""
        return tuple(c for c in self.capacidades.values() if tipo_evento in c.eventos)

    def perfiles_que_pueden_emitir(self, tipo_evento: str) -> frozenset[str]:
        """Los perfiles a los que la matriz concede alguna capacidad que produce ese evento.

        Es lo que necesita el log para negarse a sellar un evento que el rol del actor no puede producir
        (A8). Las celdas `pendiente` **no** cuentan: lo no decidido no emite.
        """
        perfiles: set[str] = set()
        for capacidad in self.capacidades_que_producen(tipo_evento):
            perfiles |= set(capacidad.concede)
        return frozenset(perfiles)

    def __len__(self) -> int:
        return len(self.capacidades)


# ---------------------------------------------------------------------------
# Carga: todo lo de aqui es error de arranque, no de peticion
# ---------------------------------------------------------------------------


def _lista(datos: Mapping[str, object], clave: str) -> tuple[str, ...]:
    valor = datos.get(clave) or []
    return tuple(str(elemento) for elemento in valor)


def _texto(datos: Mapping[str, object], clave: str) -> str | None:
    valor = datos.get(clave)
    return None if valor is None else str(valor)


def _sin_repetidos(elementos: Iterable[str], que: str) -> None:
    vistos: set[str] = set()
    for elemento in elementos:
        if elemento in vistos:
            raise ErrorCapacidades(f"{que} {elemento!r} esta declarado dos veces")
        vistos.add(elemento)


def _ambitos(crudos: Sequence[Mapping[str, object]]) -> dict[str, Ambito]:
    _sin_repetidos([str(c["id"]) for c in crudos], "el ambito")
    ambitos: dict[str, Ambito] = {}
    for crudo in crudos:
        bloques = _lista(crudo, "bloques")
        if not bloques:
            raise ErrorCapacidades(f"el ambito {crudo['id']!r} no declara ningun bloque: no podria leer nada")
        _sin_repetidos(bloques, f"el bloque del ambito {crudo['id']!r}")
        ambitos[str(crudo["id"])] = Ambito(
            id=str(crudo["id"]),
            nombre=str(crudo["nombre"]),
            exige_tenant=bool(crudo["exige_tenant"]),
            bloques=frozenset(bloques),
            solo_actuaciones_propias=bool(crudo.get("solo_actuaciones_propias", False)),
        )
    return ambitos


def _superficies(
    crudas: Sequence[Mapping[str, object]],
) -> tuple[dict[str, Superficie], dict[str, Pantalla]]:
    _sin_repetidos([str(c["id"]) for c in crudas], "la superficie")
    superficies: dict[str, Superficie] = {}
    pantallas: dict[str, Pantalla] = {}
    for cruda in crudas:
        identificador = str(cruda["id"])
        ids: list[str] = []
        for pantalla in cruda.get("pantallas") or []:
            pid = str(pantalla["id"])
            if pid in pantallas or pid in superficies or pid == identificador:
                raise ErrorCapacidades(
                    f"la pantalla {pid!r} choca con otra pantalla o con una superficie: el contexto de "
                    "una peticion admite los dos nombres y no podria distinguirlos"
                )
            pantallas[pid] = Pantalla(
                id=pid,
                nombre=str(pantalla["nombre"]),
                superficie=identificador,
                perfil=_texto(pantalla, "perfil"),
            )
            ids.append(pid)
        superficies[identificador] = Superficie(
            id=identificador, nombre=str(cruda["nombre"]), pantallas=tuple(ids)
        )
    return superficies, pantallas


def _perfiles(
    crudos: Sequence[Mapping[str, object]],
    ambitos: Mapping[str, Ambito],
    superficies: Mapping[str, Superficie],
) -> dict[str, Perfil]:
    _sin_repetidos([str(c["id"]) for c in crudos], "el perfil")
    perfiles: dict[str, Perfil] = {}
    for crudo in crudos:
        identificador = str(crudo["id"])
        ambito = str(crudo["ambito"])
        superficie = str(crudo["superficie"])
        if ambito not in ambitos:
            raise ErrorCapacidades(f"el perfil {identificador!r} declara el ambito inexistente {ambito!r}")
        if superficie not in superficies:
            raise ErrorCapacidades(
                f"el perfil {identificador!r} declara la superficie inexistente {superficie!r}"
            )
        perfiles[identificador] = Perfil(
            id=identificador, nombre=str(crudo["nombre"]), ambito=ambito, superficie=superficie
        )
    return perfiles


def _comprobar_pantallas(pantallas: Mapping[str, Pantalla], perfiles: Mapping[str, Perfil]) -> None:
    for pantalla in pantallas.values():
        if pantalla.perfil is None:
            continue
        perfil = perfiles.get(pantalla.perfil)
        if perfil is None:
            raise ErrorCapacidades(
                f"la pantalla {pantalla.id!r} apunta al perfil inexistente {pantalla.perfil!r}"
            )
        if perfil.superficie != pantalla.superficie:
            raise ErrorCapacidades(
                f"la pantalla {pantalla.id!r} es de la superficie {pantalla.superficie!r} y su perfil "
                f"{perfil.id!r} trabaja en {perfil.superficie!r}: no podria desempatar nada"
            )


def _comprobar_eventos(capacidad: Capacidad) -> None:
    """Regla 2 de `ADR-011` §2, con la salvedad que obliga la tabla de `ADR-006` (ver cabecera)."""
    fuera = [evento for evento in capacidad.eventos if evento not in TIPOS]
    if fuera:
        raise ErrorCapacidades(
            f"{capacidad.id}: {fuera} no estan en el catalogo cerrado de eventos "
            "(engine.eventos.catalogo.TIPOS). Un evento inventado no carga"
        )
    dentro = [evento for evento in capacidad.eventos_propuestos if evento in TIPOS]
    if dentro:
        raise ErrorCapacidades(
            f"{capacidad.id}: {dentro} ya estan en el catalogo cerrado; van en `eventos`, no en "
            "`eventos_propuestos`, y la capacidad ya se puede implementar"
        )
    if capacidad.es_comando:
        if not (capacidad.eventos or capacidad.eventos_propuestos or capacidad.efecto):
            raise ErrorCapacidades(
                f"{capacidad.id}: un comando declara al menos un evento o, si su resultado no es un "
                "evento del log, un `efecto`"
            )
        if capacidad.eventos_propuestos and capacidad.implementada:
            raise ErrorCapacidades(
                f"{capacidad.id}: declara eventos que el catalogo cerrado no admite y a la vez un "
                "manejador; no podria escribirlos"
            )
        if capacidad.bloques:
            raise ErrorCapacidades(f"{capacidad.id}: un comando no proyecta bloques de lectura")
    else:
        if capacidad.eventos or capacidad.eventos_propuestos or capacidad.efecto:
            raise ErrorCapacidades(f"{capacidad.id}: una lectura no produce eventos ni efectos")
        if capacidad.exige_justificacion:
            raise ErrorCapacidades(f"{capacidad.id}: una lectura no exige justificacion; no cambia nada")


def _comprobar_concesion(capacidad: Capacidad, perfiles: Mapping[str, Perfil]) -> None:
    for perfil in sorted(capacidad.concede | capacidad.pendiente):
        if perfil not in perfiles:
            raise ErrorCapacidades(f"{capacidad.id}: perfil inexistente {perfil!r}")
    solapan = sorted(capacidad.concede & capacidad.pendiente)
    if solapan:
        raise ErrorCapacidades(
            f"{capacidad.id}: {solapan} estan a la vez concedidos y pendientes; una celda `(?)` se "
            "deniega hasta que se decida (`ADR-011` §1)"
        )
    if capacidad.pendiente and not capacidad.decide:
        raise ErrorCapacidades(
            f"{capacidad.id}: tiene celdas pendientes y no dice que decision las cerraria (`decide`)"
        )
    if capacidad.decide and not capacidad.pendiente:
        raise ErrorCapacidades(f"{capacidad.id}: declara `decide` sin ninguna celda pendiente")
    for condicion in capacidad.condicionada:
        if condicion.perfil not in perfiles:
            raise ErrorCapacidades(
                f"{capacidad.id}: condicion sobre el perfil inexistente {condicion.perfil!r}"
            )
        if condicion.perfil in capacidad.concede or condicion.perfil in capacidad.pendiente:
            raise ErrorCapacidades(
                f"{capacidad.id}: {condicion.perfil!r} esta condicionado y ademas concedido o pendiente"
            )


def _comprobar_bloques(capacidad: Capacidad, ambitos: Mapping[str, Ambito]) -> None:
    declarados: set[str] = set()
    for ambito in ambitos.values():
        declarados |= ambito.bloques
    huerfanos = [bloque for bloque in capacidad.bloques if bloque not in declarados]
    if huerfanos:
        raise ErrorCapacidades(
            f"{capacidad.id}: los bloques {huerfanos} no los admite ningun ambito; nadie los veria nunca"
        )
    if not capacidad.es_comando and capacidad.implementada and not capacidad.bloques:
        raise ErrorCapacidades(f"{capacidad.id}: una lectura con manejador tiene que proyectar algo")


def _capacidad(crudo: Mapping[str, object]) -> Capacidad:
    condicionada = tuple(
        Condicion(perfil=str(c["perfil"]), requiere=str(c["requiere"]), nota=str(c["nota"]))
        for c in (crudo.get("condicionada") or [])
    )
    capacidad = Capacidad(
        id=str(crudo["id"]),
        nombre=str(crudo["nombre"]),
        grupo=str(crudo["grupo"]),
        tipo=str(crudo["tipo"]),
        concede=frozenset(_lista(crudo, "concede")),
        pendiente=frozenset(_lista(crudo, "pendiente")),
        decide=_texto(crudo, "decide"),
        condicionada=condicionada,
        proceso=_texto(crudo, "proceso"),
        eventos=_lista(crudo, "eventos"),
        eventos_propuestos=_lista(crudo, "eventos_propuestos"),
        efecto=_texto(crudo, "efecto"),
        exige_justificacion=bool(crudo.get("exige_justificacion", False)),
        bloques=_lista(crudo, "bloques"),
        manejador=_texto(crudo, "manejador"),
        falta=_texto(crudo, "falta"),
    )
    if capacidad.proceso is not None and capacidad.proceso not in PROCESOS:
        raise ErrorCapacidades(
            f"{capacidad.id}: proceso {capacidad.proceso!r} desconocido; los del catalogo son {PROCESOS}"
        )
    if capacidad.implementada == bool(capacidad.falta):
        raise ErrorCapacidades(
            f"{capacidad.id}: o declara `manejador` (hay implementacion) o declara `falta` (que es lo "
            "que impide implementarla), nunca las dos ni ninguna"
        )
    return capacidad


def cargar_matriz(ruta: Path | str | None = None) -> Matriz:
    """Lee, valida y devuelve la matriz. Sin cache: para el uso normal esta `matriz_capacidades`."""
    origen = Path(ruta) if ruta is not None else RUTA_MATRIZ
    if not origen.is_file():
        raise ErrorCapacidades(f"no encuentro la matriz de capacidades en {origen}")
    try:
        datos = yaml.safe_load(origen.read_text(encoding="utf-8"))
        esquema = json.loads(RUTA_ESQUEMA.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ErrorCapacidades(f"no se puede leer la matriz {origen.name}: {exc}") from exc
    _validar_esquema(datos, esquema, origen.name)

    ambitos = _ambitos(datos["ambitos"])
    superficies, pantallas = _superficies(datos["superficies"])
    perfiles = _perfiles(datos["perfiles"], ambitos, superficies)
    _comprobar_pantallas(pantallas, perfiles)

    _sin_repetidos([str(c["id"]) for c in datos["capacidades"]], "la capacidad")
    capacidades: dict[str, Capacidad] = {}
    manejadores: dict[str, str] = {}
    for crudo in datos["capacidades"]:
        capacidad = _capacidad(crudo)
        _comprobar_eventos(capacidad)
        _comprobar_concesion(capacidad, perfiles)
        _comprobar_bloques(capacidad, ambitos)
        if capacidad.manejador is not None:
            duplicado = manejadores.get(capacidad.manejador)
            if duplicado is not None:
                raise ErrorCapacidades(
                    f"{capacidad.id} y {duplicado} comparten el manejador {capacidad.manejador!r}: "
                    "dos capacidades distintas no se atienden con la misma funcion"
                )
            manejadores[capacidad.manejador] = capacidad.id
        capacidades[capacidad.id] = capacidad

    descolgadas = sorted({p.superficie for p in perfiles.values()} ^ set(superficies))
    if descolgadas:
        raise ErrorCapacidades(f"superficies que ningun perfil usa, o al reves: {descolgadas}")

    return Matriz(
        version=str(datos["version_matriz"]),
        fuente=str(datos.get("fuente", "")),
        ambitos=ambitos,
        superficies=superficies,
        pantallas=pantallas,
        perfiles=perfiles,
        capacidades=capacidades,
        ruta=origen,
    )


@lru_cache(maxsize=4)
def matriz_capacidades(ruta: Path | None = None) -> Matriz:
    """La matriz, leida una vez. Una matriz mal formada es `ErrorCapacidades` al cargar."""
    return cargar_matriz(ruta)


def capacidades_que_producen(tipo_evento: str, *, ruta: Path | None = None) -> tuple[Capacidad, ...]:
    """Atajo sobre la matriz por defecto: que capacidades producen ese evento."""
    return matriz_capacidades(ruta).capacidades_que_producen(tipo_evento)


def perfiles_que_pueden_emitir(tipo_evento: str, *, ruta: Path | None = None) -> frozenset[str]:
    """Atajo sobre la matriz por defecto: que perfiles pueden producir ese evento (enganche del log, A8)."""
    return matriz_capacidades(ruta).perfiles_que_pueden_emitir(tipo_evento)


def autorizador(ruta: Path | None = None):
    """El gancho que `LogEventos` instala para no sellar un evento que el rol del actor no puede producir.

    Firma `(tipo, actor) -> None`, `ErrorEvento` si se deniega. Tres criterios, y ninguno cableado:

    1. Un actor que no es humano no lleva rol y no se comprueba aqui: quien lo limita es el catalogo
       (`ACTORES_ADMITIDOS`, `TIPOS_SOLO_HUMANO`).
    2. Un rol que la matriz no conoce no escribe nada.
    3. **Si ninguna capacidad concede ese evento, ningun perfil lo escribe**, aunque el catalogo lo admita:
       los eventos que produce el motor o la plataforma no los sella una persona. Es lo que impide, por
       ejemplo, que alguien escriba a mano el veredicto (`R-UI-02`) rodeando al motor.
    """
    matriz = matriz_capacidades(ruta)

    def comprobar(tipo: str, actor: object) -> None:
        rol = getattr(actor, "rol", None)
        if rol is None:
            return
        if rol not in matriz.perfiles:
            raise ErrorEvento(
                f"{tipo}: el rol {rol!r} no esta en la matriz de perfiles ({matriz.ruta}). Un rol "
                "inventado en el log parece trazabilidad y no lo es"
            )
        permitidos = matriz.perfiles_que_pueden_emitir(tipo)
        if not permitidos:
            raise ErrorEvento(
                f"{tipo}: ninguna capacidad de la matriz lo concede a ningun perfil, asi que no lo "
                f"escribe una persona; {rol} no puede sellarlo a mano"
            )
        if rol not in permitidos:
            raise ErrorEvento(
                f"{tipo}: {rol} no tiene ninguna capacidad que lo produzca; lo pueden "
                f"{sorted(permitidos)} (`ADR-006`, matriz de capacidades)"
            )

    return comprobar


# ---------------------------------------------------------------------------
# Validador JSON Schema minimo
# ---------------------------------------------------------------------------
#
# Mismo criterio y mismo subconjunto que `engine/modelo/validacion.py`, y por los mismos motivos: el nucleo
# no gana dependencias para algo que se hace una vez al arrancar, y `pydantic` ademas coacciona tipos.
# Esta aqui y no reutilizado de `engine.modelo.validacion` porque aquel solo valida contra los tres
# esquemas del modelo canonico, que carga de su propia carpeta; unificar los dos validadores en uno es una
# mejora pendiente, no una urgencia.

#: Palabras de JSON Schema que este validador entiende. Otra cosa en el esquema es un error de carga: un
#: esquema que declara una restriccion que el validador ignoraria da falsa sensacion de validacion.
PALABRAS_ESQUEMA = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "enum",
        "minLength",
    }
)

_RAIZ = "(raiz)"


def _donde(ruta: str) -> str:
    return ruta or _RAIZ


def _tipo_json(valor: object) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, int):
        return "integer"
    if isinstance(valor, str):
        return "string"
    if isinstance(valor, Mapping):
        return "object"
    if isinstance(valor, list):
        return "array"
    return type(valor).__name__


def _comprobar_palabras(esquema: object, donde: str) -> None:
    if not isinstance(esquema, Mapping):
        return
    for clave, valor in esquema.items():
        if clave not in PALABRAS_ESQUEMA:
            raise ErrorCapacidades(f"{donde}: el esquema usa la palabra no soportada {clave!r}")
        if clave in ("properties", "$defs") and isinstance(valor, Mapping):
            for nombre, sub in valor.items():
                _comprobar_palabras(sub, f"{donde}.{clave}.{nombre}")
        elif clave in ("items", "additionalProperties"):
            _comprobar_palabras(valor, f"{donde}.{clave}")


def _resolver(sub: Mapping[str, object], raiz: Mapping[str, object]) -> Mapping[str, object]:
    """Resuelve un `$ref` local (`#/$defs/<nombre>`). No hay red ni referencias remotas."""
    ref = sub.get("$ref")
    if ref is None:
        return sub
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise ErrorCapacidades(f"referencia no soportada {ref!r} (solo #/$defs/<nombre>)")
    defs = raiz.get("$defs")
    nombre = ref[len("#/$defs/") :]
    if not isinstance(defs, Mapping) or nombre not in defs:
        raise ErrorCapacidades(f"el esquema no define {ref!r}")
    destino = defs[nombre]
    if not isinstance(destino, Mapping):  # pragma: no cover - esquema roto
        raise ErrorCapacidades(f"la definicion {ref!r} no es un esquema")
    return destino


def _validar_nodo(valor: object, sub: Mapping[str, object], raiz: Mapping[str, object], ruta: str) -> None:
    sub = _resolver(sub, raiz)

    tipos = sub.get("type")
    if tipos is not None:
        esperados = tuple(tipos) if isinstance(tipos, list) else (tipos,)
        real = _tipo_json(valor)
        if real not in esperados:
            raise ErrorCapacidades(f"{_donde(ruta)}: se esperaba {'|'.join(esperados)} y llego {real}")

    if "enum" in sub:
        permitidos = sub["enum"]
        if isinstance(permitidos, list) and not any(valor == permitido for permitido in permitidos):
            raise ErrorCapacidades(f"{_donde(ruta)}: {valor!r} no esta en el enumerado {permitidos}")

    if isinstance(valor, str):
        minimo = sub.get("minLength")
        if isinstance(minimo, int) and len(valor) < minimo:
            raise ErrorCapacidades(f"{_donde(ruta)}: cadena mas corta que el minimo ({minimo})")

    if isinstance(valor, Mapping):
        _validar_objeto(valor, sub, raiz, ruta)
    elif isinstance(valor, list):
        _validar_lista(valor, sub, raiz, ruta)


def _validar_objeto(
    valor: Mapping[str, object], sub: Mapping[str, object], raiz: Mapping[str, object], ruta: str
) -> None:
    requeridos = sub.get("required")
    if isinstance(requeridos, Sequence) and not isinstance(requeridos, str):
        for campo in requeridos:
            if campo not in valor:
                raise ErrorCapacidades(f"{_donde(ruta)}: falta el campo requerido {campo!r}")

    propiedades = sub.get("properties")
    propiedades = propiedades if isinstance(propiedades, Mapping) else {}
    adicionales = sub.get("additionalProperties", True)

    for clave, contenido in valor.items():
        hijo = f"{ruta}.{clave}" if ruta else str(clave)
        declarada = propiedades.get(clave)
        if isinstance(declarada, Mapping):
            _validar_nodo(contenido, declarada, raiz, hijo)
        elif adicionales is False:
            raise ErrorCapacidades(f"{_donde(ruta)}: campo no permitido {clave!r}")
        elif isinstance(adicionales, Mapping):
            _validar_nodo(contenido, adicionales, raiz, hijo)


def _validar_lista(valor: list, sub: Mapping[str, object], raiz: Mapping[str, object], ruta: str) -> None:
    minimo = sub.get("minItems")
    if isinstance(minimo, int) and len(valor) < minimo:
        raise ErrorCapacidades(f"{_donde(ruta)}: se esperaban al menos {minimo} elementos y hay {len(valor)}")
    elementos = sub.get("items")
    if isinstance(elementos, Mapping):
        for indice, elemento in enumerate(valor):
            _validar_nodo(elemento, elementos, raiz, f"{ruta}[{indice}]")


def _validar_esquema(datos: object, esquema: Mapping[str, object], nombre: str) -> None:
    _comprobar_palabras(esquema, nombre)
    if not isinstance(datos, Mapping):
        raise ErrorCapacidades(f"{nombre}: se esperaba un objeto y llego {_tipo_json(datos)}")
    _validar_nodo(datos, esquema, esquema, "")


__all__ = [
    "PALABRAS_ESQUEMA",
    "PROCESOS",
    "RUTA_ESQUEMA",
    "RUTA_MATRIZ",
    "TIPO_COMANDO",
    "TIPO_LECTURA",
    "Ambito",
    "Capacidad",
    "Condicion",
    "ErrorCapacidades",
    "Matriz",
    "Pantalla",
    "Perfil",
    "Superficie",
    "autorizador",
    "capacidades_que_producen",
    "cargar_matriz",
    "matriz_capacidades",
    "perfiles_que_pueden_emitir",
]
