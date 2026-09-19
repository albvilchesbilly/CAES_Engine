"""Maquina de estados del ciclo (N6): `docs/03` §7, `docs/02` §5, `ADR-004` C3.

Este modulo fija **un** nivel de estado, el nuestro, y **refleja** otro, el de la plataforma. Los cuatro
niveles de `docs/03` §7.1 no se mezclan nunca:

| Nivel | Valores | Quien lo fija | Aqui |
|---|---|---|---|
| Veredicto | `NO_ELEGIBLE` > … > `PREVALIDADO` | Rules Engine (`engine/reglas.py`) | se **lee**, no se toca |
| Estado de ciclo | `ESTADOS_CICLO` | esta maquina, como proyeccion del log | se **fija** |
| Estado de plataforma (actuacion) | los 8 confirmados de `docs/02` §5.1 | la plataforma | se **refleja** |
| Estado de plataforma (expediente) | provisionales, `TODO(API-03)` | la plataforma | se **refleja** |

**El estado no es un campo mutable: es una proyeccion del log** (`docs/03` §6). `proyectar(log)` recorre los
eventos en orden de secuencia y `aplicar(proyeccion, evento)` es pura: misma proyeccion mas mismo evento da
siempre el mismo resultado, y la proyeccion de entrada no se toca (`Proyeccion` es `frozen`). Una transicion
no declarada es `ErrorEstado` con el par origen -> destino; nunca un estado silenciosamente equivocado.

Los literales de plataforma y su efecto sobre el ciclo viven en `estados_plataforma.yaml`, **no aqui**: los de
fases 2-4 son nombres nuestros (`TODO(API-03)`) y cuando llegue el diccionario oficial cambiar nombres tiene
que ser cambiar YAML (`docs/03` §7.1). Este modulo no contiene ni un literal de plataforma.

Los cinco invariantes que protege (`ADR-004` C3, criterios de `docs/06`):

1. **`ENTREGADA` -> `EN_PLATAFORMA` exige `FirmaRegistrada` de actor humano.** Un evento de actor `motor`,
   `agente` o `plataforma` que intente esa transicion es `ErrorEstado`. La firma es un acto humano: nosotros
   solo registramos que ocurrio (`CLAUDE.md` §2).
2. **Solo `PREVALIDADO` y revisada por un humano llega a `LISTA_PARA_ENVIO`.** Las dos condiciones, no una.
3. **Inalterabilidad post-firma** (`docs/02` §5.4): firmada la actuacion, un cambio de datos fuera de un
   requerimiento abierto no cambia el estado y se anota como rechazo, para que el llamante emita
   `CorreccionRechazadaPostFirma`. No se pierde: queda en `Proyeccion.rechazos`.
4. **Contagio** (`docs/02` §5.6): un requerimiento de GA o CN pone `PENDIENTE_SUBSANACION` en **todas** las
   actuaciones del expediente, con `afectada_directamente: bool`. Es `propagar_requerimiento`.
5. **Un literal de plataforma desconocido no se descarta**: se refleja, se anota en
   `Proyeccion.literales_desconocidos` y la actuacion pasa a `EN_REVISION_HUMANA` (`docs/02` §5.6). No es una
   excepcion ni un silencio: es un hueco nuevo para `docs/HUECOS.md`.

Decisiones propias de esta pieza (todas para el ADR):

- **El catalogo de eventos no tiene tipo para "un humano reviso esto", "escalar a revision" ni "descartar".**
  Se resuelven con `ObservacionRegistrada` (el evento de P6) y un `origen` en el payload:
  `revision_humana` (exige actor humano), `escalado` y `descarte` (exige humano y veredicto `NO_ELEGIBLE`).
  Propuesta: tipos propios `RevisionHumanaRegistrada` y `ActuacionDescartada`.
- **`LISTA_PARA_ENVIO` la marca el empaquetado** (`PayloadConstruido` / `ManifiestoGenerado`, P8): es el
  primer evento del catalogo que solo tiene sentido sobre una actuacion lista.
- **Una transicion a uno mismo no es una transicion**: veinte `DocumentoRegistrado` seguidos dejan la
  actuacion en `EN_PROCESO` sin que `EN_PROCESO -> EN_PROCESO` figure en el grafo.
- **`propagar_requerimiento` no toca `estado_plataforma`** de las contagiadas: `REQUERIDO_GA`/`REQUERIDO_CN`
  son estados del **expediente**, no de cada actuacion. Lo que se propaga es el ciclo, el origen y el flag.
- **Una actuacion `CERRADA` o `DESCARTADA` no se contagia**: son terminales. Se devuelven intactas.

`engine/estados.py` no importa de `agentes/`, `salida/`, `generator/` ni `tests/`, no usa `eval` ni `float`, y
no sabe que fichas existen.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import yaml

from engine.eventos.catalogo import CLASES_ACTOR, ORIGENES_SUBSANACION, TIPOS
from engine.eventos.log import Evento, LogEventos
from engine.reglas import VEREDICTO_NO_ELEGIBLE, VEREDICTO_PREVALIDADO

# ---------------------------------------------------------------------------
# Estado de ciclo (nivel 2): lo unico que esta maquina decide
# ---------------------------------------------------------------------------

#: Los 10 estados de ciclo (`ADR-004` C3, `docs/03` §7.2). **Deben coincidir con el enumerado
#: `ciclo.estado_ciclo` de `engine/modelo/esquemas/actuacion-1.0.json`**; hay un test que lo comprueba.
ESTADOS_CICLO = (
    "ABIERTA",
    "EN_PROCESO",
    "EVALUADA",
    "PENDIENTE_SUBSANACION",
    "EN_REVISION_HUMANA",
    "LISTA_PARA_ENVIO",
    "ENTREGADA",
    "EN_PLATAFORMA",
    "CERRADA",
    "DESCARTADA",
)

#: Estado en el que nace una actuacion.
ESTADO_INICIAL = "ABIERTA"

#: De aqui no se sale: una actuacion cerrada o descartada no vuelve al circuito (se abre una nueva).
ESTADOS_TERMINALES = ("CERRADA", "DESCARTADA")

#: Grafo de `docs/03` §7.2. Sin transiciones a uno mismo (ver cabecera).
#:
#: Lecturas del grafo que no estan dibujadas en §7.2 pero si escritas en la prosa de §7.3 y en `docs/02` §5.6:
#: `EN_REVISION_HUMANA` es alcanzable desde cualquier estado no terminal ("presupuesto agotado, revision
#: humana", §7.3, y el literal desconocido de §5.6); `ENTREGADA -> EN_PROCESO` existe porque en `BORRADOR` y
#: `COMPLETA` la actuacion "sigue siendo modificable por nosotros" (§5.6) -- la inalterabilidad empieza en
#: `EN_PLATAFORMA`, no en la entrega.
TRANSICIONES: dict[str, frozenset[str]] = {
    "ABIERTA": frozenset({"EN_PROCESO", "EN_REVISION_HUMANA"}),
    "EN_PROCESO": frozenset({"EVALUADA", "EN_REVISION_HUMANA"}),
    "EVALUADA": frozenset(
        {"EN_PROCESO", "PENDIENTE_SUBSANACION", "EN_REVISION_HUMANA", "LISTA_PARA_ENVIO", "DESCARTADA"}
    ),
    "PENDIENTE_SUBSANACION": frozenset({"EN_PROCESO", "EN_REVISION_HUMANA", "CERRADA"}),
    "EN_REVISION_HUMANA": frozenset({"EN_PROCESO", "EVALUADA", "PENDIENTE_SUBSANACION", "CERRADA"}),
    "LISTA_PARA_ENVIO": frozenset({"EN_PROCESO", "ENTREGADA", "EN_REVISION_HUMANA"}),
    "ENTREGADA": frozenset({"EN_PROCESO", "EN_PLATAFORMA", "EN_REVISION_HUMANA"}),
    "EN_PLATAFORMA": frozenset({"PENDIENTE_SUBSANACION", "EN_REVISION_HUMANA", "CERRADA"}),
    "CERRADA": frozenset(),
    "DESCARTADA": frozenset(),
}


class ErrorEstado(Exception):
    """Transicion no declarada, guarda incumplida o tabla de mapeo mal formada."""


def transiciones_validas(estado: str) -> frozenset[str]:
    """Los estados de ciclo alcanzables desde `estado`. Un estado desconocido es `ErrorEstado`."""
    if estado not in TRANSICIONES:
        raise ErrorEstado(f"estado de ciclo desconocido: {estado!r}; los validos son {ESTADOS_CICLO}")
    return TRANSICIONES[estado]


def es_transicion_valida(origen: str, destino: str) -> bool:
    """`True` si `origen -> destino` esta declarada. Quedarse donde uno esta siempre vale (ver cabecera)."""
    if destino not in TRANSICIONES:
        raise ErrorEstado(f"estado de ciclo desconocido: {destino!r}; los validos son {ESTADOS_CICLO}")
    return destino == origen or destino in transiciones_validas(origen)


# ---------------------------------------------------------------------------
# Estado de plataforma (niveles 3 y 4): se refleja, no se decide
# ---------------------------------------------------------------------------

#: La tabla de mapeo. Ni un literal de plataforma en este fichero .py (ver cabecera).
RUTA_TABLA = Path(__file__).resolve().parent / "estados_plataforma.yaml"

#: Niveles de la tabla: fase 1 (actuacion, confirmada) y fases 2-4 (expediente, provisional).
NIVELES = ("actuacion", "expediente")

#: Claves admitidas en una fila de la tabla. Una clave de mas es un error de carga, no un campo ignorado.
CLAVES_FILA = frozenset(
    {
        "literal",
        "nivel",
        "fase",
        "oficial",
        "ciclo",
        "origen_subsanacion",
        "alcance",
        "resultado",
        "exige_firma",
        "exige_desistimiento",
        "inicial",
        "validacion_automatica",
        "modificable",
        "candidata_expediente",
        "nota",
    }
)

#: Alcances admitidos (`docs/03` §10.5).
ALCANCES = ("actuacion", "grupo", "expediente")


@dataclass(frozen=True)
class ProyeccionPlataforma:
    """Una fila de `estados_plataforma.yaml`: que le hace al ciclo un literal de la plataforma."""

    literal: str
    nivel: str
    fase: str
    oficial: bool
    ciclo: str | None
    origen_subsanacion: str | None = None
    alcance: str = "actuacion"
    resultado: str | None = None
    exige_firma: bool = False
    exige_desistimiento: bool = False
    #: Estado en el que nace una actuacion en la plataforma (`docs/02` §5.1: la crea el sujeto).
    inicial: bool = False
    #: Estado al que lleva la validacion automatica de la plataforma. **Fin de la automatizacion**
    #: (`docs/02` §5.1 y §6.2): ningun componente nuestro avanza mas alla de aqui.
    validacion_automatica: bool = False
    modificable: bool = False
    candidata_expediente: bool = False
    nota: str = ""

    @property
    def contagia_expediente(self) -> bool:
        """`REQUERIDO_GA` y `REQUERIDO_CN`: el requerimiento alcanza a todo el expediente (`docs/02` §5.6)."""
        return self.alcance == "expediente" and self.origen_subsanacion in ("GA", "CN")


def _fila(cruda: object, indice: int) -> ProyeccionPlataforma:
    if not isinstance(cruda, Mapping):
        raise ErrorEstado(f"fila {indice} de la tabla de plataforma: se esperaba un mapa")
    sobran = sorted(set(map(str, cruda)) - CLAVES_FILA)
    if sobran:
        raise ErrorEstado(f"fila {indice} de la tabla de plataforma: claves no admitidas {sobran}")
    faltan = [c for c in ("literal", "nivel", "fase", "oficial", "ciclo") if c not in cruda]
    if faltan:
        raise ErrorEstado(f"fila {indice} de la tabla de plataforma: faltan {faltan}")
    literal = str(cruda["literal"])
    nivel = str(cruda["nivel"])
    if nivel not in NIVELES:
        raise ErrorEstado(f"{literal}: nivel {nivel!r} desconocido; los validos son {NIVELES}")
    oficial = cruda["oficial"]
    if not isinstance(oficial, bool):
        raise ErrorEstado(f"{literal}: `oficial` es booleano, no {type(oficial).__name__}")
    if nivel == "expediente" and oficial:
        raise ErrorEstado(
            f"{literal}: los estados de expediente (fases 2-4) son nombres nuestros, nunca `oficial: true` "
            "(TODO(API-03), docs/02 §5.2)"
        )
    ciclo = cruda["ciclo"]
    if ciclo is not None and str(ciclo) not in ESTADOS_CICLO:
        raise ErrorEstado(f"{literal}: proyecta a un estado de ciclo inexistente {ciclo!r}")
    origen = cruda.get("origen_subsanacion")
    if origen is not None and str(origen) not in ORIGENES_SUBSANACION:
        raise ErrorEstado(f"{literal}: origen de subsanacion desconocido {origen!r}")
    alcance = str(cruda.get("alcance", "actuacion"))
    if alcance not in ALCANCES:
        raise ErrorEstado(f"{literal}: alcance desconocido {alcance!r}; los validos son {ALCANCES}")
    return ProyeccionPlataforma(
        literal=literal,
        nivel=nivel,
        fase=str(cruda["fase"]),
        oficial=oficial,
        ciclo=None if ciclo is None else str(ciclo),
        origen_subsanacion=None if origen is None else str(origen),
        alcance=alcance,
        resultado=None if cruda.get("resultado") is None else str(cruda["resultado"]),
        exige_firma=bool(cruda.get("exige_firma", False)),
        exige_desistimiento=bool(cruda.get("exige_desistimiento", False)),
        inicial=bool(cruda.get("inicial", False)),
        validacion_automatica=bool(cruda.get("validacion_automatica", False)),
        modificable=bool(cruda.get("modificable", False)),
        candidata_expediente=bool(cruda.get("candidata_expediente", False)),
        nota=str(cruda.get("nota", "")),
    )


@lru_cache(maxsize=1)
def tabla_plataforma(ruta: Path | None = None) -> dict[str, ProyeccionPlataforma]:
    """La tabla de mapeo, por literal. Se lee una vez; una tabla mal formada es `ErrorEstado` al cargar."""
    origen = ruta or RUTA_TABLA
    if not origen.is_file():
        raise ErrorEstado(f"no encuentro la tabla de estados de plataforma en {origen}")
    datos = yaml.safe_load(origen.read_text(encoding="utf-8"))
    if not isinstance(datos, Mapping) or not isinstance(datos.get("estados"), list):
        raise ErrorEstado(f"{origen.name}: se esperaba un mapa con una lista `estados`")
    tabla: dict[str, ProyeccionPlataforma] = {}
    for indice, cruda in enumerate(datos["estados"], start=1):
        fila = _fila(cruda, indice)
        if fila.literal in tabla:
            raise ErrorEstado(f"{origen.name}: el literal {fila.literal!r} esta declarado dos veces")
        tabla[fila.literal] = fila
    _garantia_de_carga(tabla, origen.name)
    return tabla


def _garantia_de_carga(tabla: Mapping[str, ProyeccionPlataforma], nombre: str) -> None:
    """Las tres marcas que el simulador (`salida/simulador/`) necesita para no depender del orden del YAML.

    Sin ellas habria que distinguir "crear" de "validado" por la posicion de la fila, y reordenar el fichero
    cambiaria el comportamiento en silencio. Se comprueba **al cargar**: una tabla mal marcada es un error de
    carga, nunca un estado equivocado en mitad de una entrega.
    """
    for marca, que in (
        ("inicial", "el estado en el que nace una actuacion"),
        ("validacion_automatica", "el estado al que lleva la validacion automatica"),
        ("exige_firma", "el estado al que solo se llega firmando"),
    ):
        marcadas = [f for f in tabla.values() if getattr(f, marca)]
        if len(marcadas) != 1:
            raise ErrorEstado(
                f"{nombre}: exactamente una fila declara `{marca}` ({que}, `docs/02` §5.1) y hay "
                f"{len(marcadas)}: {sorted(f.literal for f in marcadas)}"
            )
        if marcadas[0].nivel != "actuacion":
            raise ErrorEstado(
                f"{nombre}: `{marca}` es de nivel actuacion (fase 1) y lo declara {marcadas[0].literal!r}, "
                f"que es de nivel {marcadas[0].nivel!r}"
            )


def _literales(nivel: str) -> tuple[str, ...]:
    return tuple(f.literal for f in tabla_plataforma().values() if f.nivel == nivel)


def estados_plataforma_actuacion() -> tuple[str, ...]:
    """Los 8 confirmados de `docs/02` §5.1, en el orden de la tabla."""
    return _literales("actuacion")


def estados_plataforma_expediente() -> tuple[str, ...]:
    """Los provisionales de fases 2-4 (`docs/02` §5.2). Nombres nuestros: `TODO(API-03)`."""
    return _literales("expediente")


#: Los 8 estados de actuacion de `docs/02` §5.1, **confirmados**. Se leen de la tabla al importar: una
#: tabla mal formada es un error de carga, no un fallo en mitad de una evaluacion.
ESTADOS_PLATAFORMA_ACTUACION: tuple[str, ...] = estados_plataforma_actuacion()

#: Los de expediente (fases 2-4): **nombres nuestros, NO OFICIALES** (`TODO(API-03)`, docs/HUECOS.md).
ESTADOS_PLATAFORMA_EXPEDIENTE: tuple[str, ...] = estados_plataforma_expediente()

#: Todos los literales que la tabla conoce hoy. Uno que no este aqui es un hueco, no un error (invariante 5).
ESTADOS_PLATAFORMA: tuple[str, ...] = ESTADOS_PLATAFORMA_ACTUACION + ESTADOS_PLATAFORMA_EXPEDIENTE


def proyectar_estado_plataforma(literal: str) -> str | None:
    """El estado de ciclo al que proyecta un literal de la plataforma (`docs/02` §5.6).

    `None` si el literal se refleja sin mover el ciclo **o si es desconocido**: la diferencia entre las dos
    cosas la resuelve `aplicar`, que ademas anota el desconocido y escala a `EN_REVISION_HUMANA`.
    """
    fila = tabla_plataforma().get(str(literal))
    return None if fila is None else fila.ciclo


# ---------------------------------------------------------------------------
# La proyeccion
# ---------------------------------------------------------------------------

#: Payload de `ObservacionRegistrada` (P6) que usa esta maquina, a falta de tipos propios (ver cabecera).
CLAVE_ORIGEN_OBSERVACION = "origen"
ORIGEN_REVISION = "revision_humana"
ORIGEN_ESCALADO = "escalado"
ORIGEN_DESCARTE = "descarte"
ORIGENES_OBSERVACION = (ORIGEN_REVISION, ORIGEN_ESCALADO, ORIGEN_DESCARTE)

#: Claves del payload de `EstadoPlataformaRecibido` donde puede venir el literal.
CLAVES_LITERAL = ("estado", "literal", "estado_plataforma")

CLASE_HUMANO = "humano"

#: Eventos que dejan la actuacion trabajandose (P1, P2, P3 parcial, P4, P5).
TIPOS_TRABAJO = (
    "DocumentoRegistrado",
    "DocumentoClasificado",
    "PdfSeparado",
    "EvidenciaPropuesta",
    "EvidenciaDescartadaSinCita",
    "DesacuerdoExtractores",
    "CabeceraConsolidada",
    "DatoConsolidado",
    "ConflictoDetectado",
    "DatoCorregidoPorHumano",
    "CalculoRealizado",
)

#: Eventos que cambian lo que se firmo. Post-firma y sin requerimiento abierto, se rechazan (`docs/02` §5.4).
TIPOS_CAMBIO_DATOS = (*TIPOS_TRABAJO, "VeredictoEmitido")

#: P8: el empaquetado solo tiene sentido sobre una actuacion lista para enviar.
TIPOS_EMPAQUETADO = ("PayloadConstruido", "ManifiestoGenerado")

#: P8: la entrega, por handoff al delegado o por API.
VIAS_ENTREGA = {"EntregadoADelegado": "handoff", "EnviadoAPI": "API"}

#: Eventos que abren una subsanacion (el origen va en el payload, `docs/03` §10.5).
TIPOS_REQUERIMIENTO = ("SubsanacionSolicitada", "RequerimientoRecibido")

#: Eventos que esta maquina reconoce pero que no mueven el ciclo (se registran y ya).
TIPOS_SIN_EFECTO = (
    "TenantAsignado",
    "VerificadorAsignado",
    "FichaAsignada",
    "DiscrepanciaCalculoPlataforma",
    "TareaPendienteRecibida",
    "RequerimientoInterpretado",
    "CorreccionRechazadaPostFirma",
    "GrupoPropuesto",
    "ExpedientePropuesto",
    "AvisoContagio",
    "ActuacionHuerfana",
)


@dataclass(frozen=True)
class Proyeccion:
    """El estado de una actuacion **derivado del log**. Inmutable: `aplicar` devuelve una nueva."""

    actuacion_id: str
    estado_ciclo: str = ESTADO_INICIAL
    estado_plataforma: str | None = None
    veredicto: str | None = None
    revisada_por_humano: bool = False
    firmada: bool = False
    desistimiento_registrado: bool = False
    via_entrega: str | None = None
    origen_subsanacion: str | None = None
    afectada_directamente: bool | None = None
    requerimiento_abierto: str | None = None
    resultado: str | None = None
    grupo_id: str | None = None
    expediente_id: str | None = None
    secuencia: int = 0
    literales_desconocidos: tuple[str, ...] = ()
    rechazos: tuple[Mapping[str, object], ...] = field(default=())

    def __post_init__(self) -> None:
        if self.estado_ciclo not in ESTADOS_CICLO:
            raise ErrorEstado(f"estado de ciclo desconocido: {self.estado_ciclo!r}")

    @property
    def terminal(self) -> bool:
        return self.estado_ciclo in ESTADOS_TERMINALES

    def a_dict(self) -> dict[str, object]:
        """Vista serializable, con las mismas claves que el bloque `ciclo` del modelo canonico."""
        return {
            "actuacion_id": self.actuacion_id,
            "estado_ciclo": self.estado_ciclo,
            "estado_plataforma": self.estado_plataforma,
            "veredicto": self.veredicto,
            "revisada_por_humano": self.revisada_por_humano,
            "firmada": self.firmada,
            "via_entrega": self.via_entrega,
            "origen_subsanacion": self.origen_subsanacion,
            "afectada_directamente": self.afectada_directamente,
            "requerimiento_abierto": self.requerimiento_abierto,
            "resultado": self.resultado,
            "grupo_id": self.grupo_id,
            "expediente_id": self.expediente_id,
            "secuencia": self.secuencia,
            "literales_desconocidos": list(self.literales_desconocidos),
            "rechazos": [dict(r) for r in self.rechazos],
        }


def inicial(actuacion_id: str) -> Proyeccion:
    """La proyeccion de una actuacion recien abierta."""
    if not str(actuacion_id).strip():
        raise ErrorEstado("una proyeccion necesita `actuacion_id`")
    return Proyeccion(actuacion_id=str(actuacion_id))


# ---------------------------------------------------------------------------
# aplicar: un evento sobre una proyeccion
# ---------------------------------------------------------------------------


def _transitar(proyeccion: Proyeccion, destino: str, motivo: str, **cambios: object) -> Proyeccion:
    if not es_transicion_valida(proyeccion.estado_ciclo, destino):
        raise ErrorEstado(
            f"transicion invalida {proyeccion.estado_ciclo} -> {destino} ({motivo}); "
            f"desde {proyeccion.estado_ciclo} solo se puede ir a "
            f"{sorted(transiciones_validas(proyeccion.estado_ciclo))}"
        )
    return replace(proyeccion, estado_ciclo=destino, **cambios)  # type: ignore[arg-type]


def _origen_declarado(datos: Mapping[str, object], tipo: str) -> str:
    origen = datos.get("origen")
    if origen is None or str(origen) not in ORIGENES_SUBSANACION:
        raise ErrorEstado(
            f"{tipo}: el payload declara `origen` en {ORIGENES_SUBSANACION} (`docs/03` §10.5); "
            f"llego {origen!r}"
        )
    return str(origen)


def _literal_recibido(datos: Mapping[str, object]) -> str:
    for clave in CLAVES_LITERAL:
        valor = datos.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    raise ErrorEstado(
        f"EstadoPlataformaRecibido: el payload no trae el literal (se busca en {list(CLAVES_LITERAL)})"
    )


def _rechazo(proyeccion: Proyeccion, evento: Evento, motivo: str) -> Proyeccion:
    """No cambia el estado: anota el intento para que el llamante emita `CorreccionRechazadaPostFirma`."""
    anotacion: Mapping[str, object] = {
        "tipo": evento.tipo,
        "evento_id": evento.evento_id,
        "secuencia": evento.secuencia,
        "motivo": motivo,
    }
    return replace(proyeccion, rechazos=(*proyeccion.rechazos, anotacion), secuencia=evento.secuencia)


def _aplicar_observacion(proyeccion: Proyeccion, evento: Evento, datos: Mapping[str, object]) -> Proyeccion:
    origen = datos.get(CLAVE_ORIGEN_OBSERVACION)
    if origen not in ORIGENES_OBSERVACION:
        return proyeccion  # una observacion cualquiera (p. ej. la de consolidacion) no mueve el ciclo
    if origen == ORIGEN_ESCALADO:
        if proyeccion.terminal:
            raise ErrorEstado(
                f"transicion invalida {proyeccion.estado_ciclo} -> EN_REVISION_HUMANA (escalado sobre una "
                "actuacion terminal)"
            )
        return _transitar(proyeccion, "EN_REVISION_HUMANA", "escalado a revision humana")
    if evento.actor.clase != CLASE_HUMANO:
        raise ErrorEstado(
            f"ObservacionRegistrada con origen {origen!r} solo es valida con actor humano; llego actor "
            f"{evento.actor.clase!r} (`docs/03` §7.3)"
        )
    if origen == ORIGEN_REVISION:
        destino = "EVALUADA" if proyeccion.estado_ciclo == "EN_REVISION_HUMANA" else proyeccion.estado_ciclo
        return _transitar(proyeccion, destino, "revision humana conforme", revisada_por_humano=True)
    if proyeccion.veredicto != VEREDICTO_NO_ELEGIBLE:
        raise ErrorEstado(
            f"DESCARTADA exige veredicto {VEREDICTO_NO_ELEGIBLE} confirmado por un humano "
            f"(`docs/03` §7.2); el veredicto es {proyeccion.veredicto!r}"
        )
    return _transitar(proyeccion, "DESCARTADA", "descarte confirmado por un humano", resultado="descartada")


def _aplicar_plataforma(proyeccion: Proyeccion, evento: Evento, datos: Mapping[str, object]) -> Proyeccion:
    literal = _literal_recibido(datos)
    fila = tabla_plataforma().get(literal)
    if fila is None:
        # `docs/02` §5.6: no se descarta, se refleja y se escala. Un literal nuevo es un hueco, no un error.
        desconocidos = proyeccion.literales_desconocidos
        if literal not in desconocidos:
            desconocidos = (*desconocidos, literal)
        visto = replace(proyeccion, estado_plataforma=literal, literales_desconocidos=desconocidos)
        if visto.terminal:
            return visto
        return _transitar(visto, "EN_REVISION_HUMANA", f"literal de plataforma desconocido {literal!r}")
    if fila.exige_firma and not proyeccion.firmada:
        raise ErrorEstado(
            f"{literal} exige un `FirmaRegistrada` previo de actor humano (`docs/02` §5.6); la actuacion "
            f"{proyeccion.actuacion_id} no esta firmada"
        )
    if fila.exige_desistimiento and not proyeccion.desistimiento_registrado:
        raise ErrorEstado(
            f"{literal} exige un `DesistimientoRegistrado` previo de actor humano (`docs/02` §5.5); la "
            f"actuacion {proyeccion.actuacion_id} no lo tiene"
        )
    reflejado = replace(proyeccion, estado_plataforma=literal)
    if fila.ciclo is None:
        return reflejado
    cambios: dict[str, object] = {}
    if fila.ciclo == "PENDIENTE_SUBSANACION":
        cambios = {
            "origen_subsanacion": fila.origen_subsanacion,
            "requerimiento_abierto": fila.origen_subsanacion,
            "afectada_directamente": True,
        }
    elif fila.ciclo == "CERRADA":
        cambios = {"resultado": fila.resultado}
    return _transitar(reflejado, fila.ciclo, f"estado de plataforma {literal}", **cambios)


def aplicar(proyeccion: Proyeccion, evento: Evento) -> Proyeccion:
    """El evento sobre la proyeccion. **Pura**: no toca la de entrada y no mira el reloj ni el disco.

    Una transicion no declarada, una guarda incumplida o un evento de otra actuacion son `ErrorEstado`.
    """
    if not isinstance(proyeccion, Proyeccion):
        raise ErrorEstado(f"se esperaba una Proyeccion y llego {type(proyeccion).__name__}")
    if not isinstance(evento, Evento):
        raise ErrorEstado(f"se esperaba un Evento y llego {type(evento).__name__}")
    if evento.actuacion_id != proyeccion.actuacion_id:
        raise ErrorEstado(
            f"el evento es de la actuacion {evento.actuacion_id!r} y la proyeccion de "
            f"{proyeccion.actuacion_id!r}"
        )
    if evento.tipo not in TIPOS:
        raise ErrorEstado(f"tipo de evento no declarado: {evento.tipo!r} (engine.eventos.catalogo)")
    if evento.actor.clase not in CLASES_ACTOR:
        raise ErrorEstado(f"clase de actor desconocida: {evento.actor.clase!r}")

    tipo = evento.tipo
    datos = evento.datos

    # Inalterabilidad (`docs/02` §5.4): firmada y sin requerimiento abierto, el dato no se toca.
    if tipo in TIPOS_CAMBIO_DATOS and proyeccion.firmada and proyeccion.requerimiento_abierto is None:
        return _rechazo(
            proyeccion,
            evento,
            "inalterabilidad post-firma: solo se modifica por requerimiento oficial (docs/02 §5.4)",
        )

    if tipo == "ActuacionAbierta":
        siguiente = replace(
            proyeccion,
            grupo_id=_texto(datos.get("grupo_id")) or proyeccion.grupo_id,
            expediente_id=_texto(datos.get("expediente_id")) or proyeccion.expediente_id,
        )
    elif tipo in TIPOS_TRABAJO:
        siguiente = _transitar(proyeccion, "EN_PROCESO", f"trabajo sobre la actuacion ({tipo})")
    elif tipo == "VeredictoEmitido":
        siguiente = _transitar(
            proyeccion, "EVALUADA", "veredicto emitido", veredicto=_texto(datos.get("veredicto"))
        )
    elif tipo in TIPOS_EMPAQUETADO:
        siguiente = _empaquetar(proyeccion, tipo)
    elif tipo in VIAS_ENTREGA:
        siguiente = _transitar(
            proyeccion, "ENTREGADA", f"entrega por {VIAS_ENTREGA[tipo]}", via_entrega=VIAS_ENTREGA[tipo]
        )
    elif tipo == "FirmaRegistrada":
        siguiente = _firmar(proyeccion, evento)
    elif tipo == "DesistimientoRegistrado":
        siguiente = _desistir(proyeccion, evento)
    elif tipo in TIPOS_REQUERIMIENTO:
        origen = _origen_declarado(datos, tipo)
        # `docs/02` §5.6: el contagio de GA/CN llega a las companeras con `afectada_directamente: false`.
        # El payload lo declara (lo escribe `engine/seguimiento.py`); sin declararlo, la senalada es esta.
        senalada = datos.get("afectada_directamente")
        siguiente = _transitar(
            proyeccion,
            "PENDIENTE_SUBSANACION",
            f"subsanacion de origen {origen}",
            origen_subsanacion=origen,
            requerimiento_abierto=origen,
            afectada_directamente=True if senalada is None else bool(senalada),
        )
    elif tipo == "SubsanacionCerrada":
        siguiente = replace(
            proyeccion, requerimiento_abierto=None, origen_subsanacion=None, afectada_directamente=None
        )
    elif tipo == "EstadoPlataformaRecibido":
        siguiente = _aplicar_plataforma(proyeccion, evento, datos)
    elif tipo == "ObservacionRegistrada":
        siguiente = _aplicar_observacion(proyeccion, evento, datos)
    elif tipo in TIPOS_SIN_EFECTO:
        siguiente = proyeccion
    else:  # pragma: no cover - el catalogo es cerrado y esta cubierto arriba
        raise ErrorEstado(f"la maquina de estados no sabe que hacer con {tipo!r}")

    return replace(siguiente, secuencia=evento.secuencia)


def _empaquetar(proyeccion: Proyeccion, tipo: str) -> Proyeccion:
    """`LISTA_PARA_ENVIO` exige las dos condiciones de `docs/03` §7.3, no una (invariante 2)."""
    if proyeccion.estado_ciclo == "LISTA_PARA_ENVIO":
        return proyeccion
    if proyeccion.veredicto != VEREDICTO_PREVALIDADO:
        raise ErrorEstado(
            f"LISTA_PARA_ENVIO exige veredicto {VEREDICTO_PREVALIDADO} (`docs/03` §7.3); el veredicto es "
            f"{proyeccion.veredicto!r} ({tipo})"
        )
    if not proyeccion.revisada_por_humano:
        raise ErrorEstado(
            "LISTA_PARA_ENVIO exige que un humano haya revisado la actuacion (`docs/03` §7.3); no consta "
            f"revision humana en {proyeccion.actuacion_id} ({tipo})"
        )
    return _transitar(proyeccion, "LISTA_PARA_ENVIO", f"empaquetado ({tipo})")


def _firmar(proyeccion: Proyeccion, evento: Evento) -> Proyeccion:
    """Invariante 1: la firma es un acto humano y es lo unico que abre `ENTREGADA -> EN_PLATAFORMA`."""
    if evento.actor.clase != CLASE_HUMANO:
        raise ErrorEstado(
            "ENTREGADA -> EN_PLATAFORMA exige un `FirmaRegistrada` de actor humano (`docs/03` §7.3, "
            f"`ADR-004` C3); llego actor {evento.actor.clase!r}: ningun componente nuestro firma"
        )
    destino = "EN_PLATAFORMA" if proyeccion.estado_ciclo == "ENTREGADA" else proyeccion.estado_ciclo
    return _transitar(proyeccion, destino, "firma registrada", firmada=True)


def _desistir(proyeccion: Proyeccion, evento: Evento) -> Proyeccion:
    """`docs/02` §5.5: el desistimiento es del sujeto (humano) y cierra la actuacion como desistida."""
    if evento.actor.clase != CLASE_HUMANO:
        raise ErrorEstado(
            f"DesistimientoRegistrado solo es valido con actor humano (`docs/02` §5.5); llego actor "
            f"{evento.actor.clase!r}"
        )
    anotado = replace(proyeccion, desistimiento_registrado=True)
    return _transitar(anotado, "CERRADA", "desistimiento del sujeto", resultado="desistida")


def _texto(valor: object) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


# ---------------------------------------------------------------------------
# proyectar: el estado es el log
# ---------------------------------------------------------------------------


def proyectar(log: LogEventos, *, desde: Proyeccion | None = None) -> Proyeccion:
    """El estado de la actuacion **derivado del log**, recorriendo los eventos en orden de secuencia."""
    if not isinstance(log, LogEventos):
        raise ErrorEstado(f"se esperaba un LogEventos y llego {type(log).__name__}")
    proyeccion = desde if desde is not None else inicial(log.actuacion_id)
    if proyeccion.actuacion_id != log.actuacion_id:
        raise ErrorEstado(
            f"el log es de {log.actuacion_id!r} y la proyeccion de partida de {proyeccion.actuacion_id!r}"
        )
    for evento in sorted(log.eventos, key=lambda e: e.secuencia):
        proyeccion = aplicar(proyeccion, evento)
    return proyeccion


# ---------------------------------------------------------------------------
# Contagio: un requerimiento de GA o CN alcanza a todo el expediente
# ---------------------------------------------------------------------------


def _origen_de_contagio(evento: Evento, datos: Mapping[str, object]) -> str:
    if evento.tipo == "EstadoPlataformaRecibido":
        fila = tabla_plataforma().get(_literal_recibido(datos))
        if fila is None or not fila.contagia_expediente:
            raise ErrorEstado(
                f"{evento.tipo}: solo contagian al expediente los literales con alcance `expediente` y "
                "origen GA o CN (`docs/02` §5.6)"
            )
        return str(fila.origen_subsanacion)
    if evento.tipo == "RequerimientoRecibido":
        origen = _origen_declarado(datos, evento.tipo)
        if origen not in ("GA", "CN"):
            raise ErrorEstado(
                f"un requerimiento de origen {origen!r} no contagia al expediente: solo GA y CN lo hacen "
                "(`docs/03` §10.5)"
            )
        return origen
    raise ErrorEstado(
        f"{evento.tipo!r} no es un requerimiento: el contagio lo abren `RequerimientoRecibido` y "
        "`EstadoPlataformaRecibido`"
    )


def propagar_requerimiento(
    proyecciones: Iterable[Proyeccion],
    evento: Evento,
    *,
    directas: Iterable[str] | None = None,
) -> tuple[Proyeccion, ...]:
    """Contagio (invariante 4, `docs/02` §5.6): `PENDIENTE_SUBSANACION` en **todo** el expediente.

    `directas` son las actuaciones que el requerimiento senala; por omision, la del evento mas las que el
    payload liste en `actuaciones_afectadas`. Las demas quedan igual de bloqueadas, con
    `afectada_directamente = False`: es el riesgo de contagio hecho estado.

    Pura, como `aplicar`. Las actuaciones terminales (`CERRADA`, `DESCARTADA`) se devuelven intactas.
    """
    datos = evento.datos
    origen = _origen_de_contagio(evento, datos)
    senaladas = set(directas) if directas is not None else {evento.actuacion_id}
    if directas is None:
        listadas = datos.get("actuaciones_afectadas")
        if isinstance(listadas, list | tuple):
            senaladas |= {str(a) for a in listadas}
    resultado: list[Proyeccion] = []
    for proyeccion in proyecciones:
        if proyeccion.terminal:
            resultado.append(proyeccion)
            continue
        resultado.append(
            _transitar(
                proyeccion,
                "PENDIENTE_SUBSANACION",
                f"contagio de un requerimiento de {origen}",
                origen_subsanacion=origen,
                requerimiento_abierto=origen,
                afectada_directamente=proyeccion.actuacion_id in senaladas,
                secuencia=evento.secuencia,
            )
        )
    return tuple(resultado)


__all__ = [
    "ALCANCES",
    "CLAVES_FILA",
    "ESTADOS_CICLO",
    "ESTADOS_PLATAFORMA",
    "ESTADOS_PLATAFORMA_ACTUACION",
    "ESTADOS_PLATAFORMA_EXPEDIENTE",
    "ESTADOS_TERMINALES",
    "ESTADO_INICIAL",
    "NIVELES",
    "ORIGENES_OBSERVACION",
    "ORIGEN_DESCARTE",
    "ORIGEN_ESCALADO",
    "ORIGEN_REVISION",
    "RUTA_TABLA",
    "TIPOS_CAMBIO_DATOS",
    "TIPOS_EMPAQUETADO",
    "TIPOS_REQUERIMIENTO",
    "TIPOS_SIN_EFECTO",
    "TIPOS_TRABAJO",
    "TRANSICIONES",
    "VIAS_ENTREGA",
    "ErrorEstado",
    "Proyeccion",
    "ProyeccionPlataforma",
    "aplicar",
    "es_transicion_valida",
    "estados_plataforma_actuacion",
    "estados_plataforma_expediente",
    "inicial",
    "propagar_requerimiento",
    "proyectar",
    "proyectar_estado_plataforma",
    "tabla_plataforma",
    "transiciones_validas",
]
