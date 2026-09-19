"""Requerimientos y su interpretacion (P7 con origen, A9 sin LLM): contrato C10 de `ADR-010`.

Un requerimiento es lo que dice quien nos para: el verificador (`PDTE_RECTIFICACION_VER` + motivos), el GA
(fase 3A) o la CN (fase 3B). Llega como texto y un PDF; lo que hace falta para reabrir la subsanacion es
saber **que regla o que documento** toca. Eso es interpretar, y aqui se interpreta **sin ningun LLM**.

`Interprete` es la interfaz (`version` + `interpretar`), exactamente como `Extractor` en
`engine/extraccion.py`; `InterpreteLexico` es la implementacion determinista de hoy. La variante con LLM
(A9) entra en S3.6 en `agentes/redactor/` **detras de esta misma interfaz**, sin tocar nada de aqui. Con el
LLM apagado el circuito funciona: es la regla de oro del modo degradado.

Los invariantes de la familia `R-REQ` (`docs/04` §10.4), y donde estan:

- **R-REQ-01** — un requerimiento de origen externo sin `informe_sha256` no reabre nada:
  `ErrorRequerimiento`. Un requerimiento sin documento es un rumor. (`reabrir`, en codigo.)
- **R-REQ-02** — `reabrir` exige `confirmada_por_humano` **y** actor humano. Una interpretacion, venga de un
  lexico o de un modelo, es una **propuesta**: nunca reabre sola. Es lo que impide que un error de lectura
  mueva una actuacion firmada. (`reabrir`, en codigo; ademas el log exige actor humano cuando
  `RequerimientoInterpretado` lleva `confirmada: true`, `CONFIRMACIONES_SOLO_HUMANO`.)
- **R-REQ-03** — tras la firma, un cambio de dato fuera de un requerimiento abierto no mueve el estado y se
  anota como rechazo. Ya lo hace `engine/estados.py` (invariante 3): aqui se **usa**, no se reimplementa.
- **R-REQ-04** — un requerimiento de `GA`/`CN` alcanza a **todas** las actuaciones del expediente. El
  alcance esta en `ALCANCE_DE_ORIGEN` y quien lo ejecuta es `engine/seguimiento.py` con
  `engine.estados.propagar_requerimiento`. Es invariante de test, no regla de spec.

Las dos decisiones del interprete determinista (`ADR-010` §3):

1. **Sin cita no hay item.** El `texto_literal` de un item es el motivo del propio requerimiento, palabra por
   palabra; un item que no se pueda citar se descarta al interpretar y se rechaza al reabrir. El lexico no
   "deduce" reglas: las **reconoce** en el texto.
2. **`no_lo_se` es una salida legitima.** Un requerimiento que el lexico no sabe mapear produce una
   interpretacion con cero items (`Interpretacion.escala_a_humano`), y eso escala a revision humana
   (`escalar`), que es lo correcto, en vez de inventar una regla plausible.

**Como reconoce el lexico sin conocer la ficha** (no hay ni un `if ficha ==` ni un codigo de ficha aqui):
el indice de candidatos se construye **de la spec cargada**. Cada regla, cada documento y cada variable de
la spec aportan sus terminos (descripcion, mensaje de subsanacion, nombre del documento, definicion de la
variable) y sus identificadores citables (`id` de la regla, su `equivalente_plataforma`, `id` del
documento). Un termino pesa `1 / numero de candidatos que lo contienen`: "documento" o "actuacion" pesan
casi nada y "instaladora" o "rotodinamico" pesan mucho, sin ninguna lista de palabras clave cableada. Un
motivo propone los candidatos que mas peso reconocido acumulan, y solo los que superan dos umbrales; si
ninguno los supera, no hay item. Cambiar de ficha es cambiar de YAML, tambien para el interprete.

Este modulo no importa de `agentes/`, `salida/`, `generator/` ni `tests/`, no usa `eval` ni `float` y no
mira el reloj: el instante lo trae el requerimiento.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from engine.estados import ORIGEN_ESCALADO, ErrorEstado
from engine.eventos.catalogo import ORIGENES_SUBSANACION
from engine.eventos.log import CLASE_HUMANO, Actor, Evento, LogEventos
from engine.seguimiento import ErrorSeguimiento, anadir_una_vez

#: Los origenes de subsanacion del catalogo de eventos (`docs/03` §10.5). No se declaran dos veces.
ORIGENES = ORIGENES_SUBSANACION

#: A quien alcanza cada origen (`docs/03` §10.5, `docs/02` §5.6). Quien lo ejecuta es `seguimiento.py`.
ALCANCE_DE_ORIGEN: Mapping[str, str] = {
    "interno": "actuacion",
    "verificador": "grupo",
    "GA": "expediente",
    "CN": "expediente",
}

#: Origenes que vienen de fuera: exigen requerimiento con informe (R-REQ-01).
ORIGENES_EXTERNOS = tuple(origen for origen in ORIGENES if origen != "interno")

VERSION_INTERPRETE = "lexico-0.1.0"
METODO_LEXICO = "lexico"

TIPO_REQUERIMIENTO = "RequerimientoRecibido"
TIPO_INTERPRETACION = "RequerimientoInterpretado"
TIPO_OBSERVACION = "ObservacionRegistrada"

#: Longitud maxima de una cita, como en `engine/extraccion.py`: una cita es una cita, no un documento.
LONGITUD_CITA = 400

#: Un termino cuenta si tiene al menos estas letras (o algun digito) y no es una palabra de relleno.
LONGITUD_MINIMA_TERMINO = 4

#: Palabras de relleno del castellano. No es vocabulario de dominio: el peso por rareza se encarga de eso.
PALABRAS_VACIAS = frozenset(
    {
        "ante",
        "aunque",
        "cada",
        "como",
        "cual",
        "cuales",
        "cuando",
        "desde",
        "donde",
        "ellos",
        "entre",
        "esta",
        "estan",
        "este",
        "esto",
        "estos",
        "hace",
        "hacia",
        "hasta",
        "mediante",
        "misma",
        "mismo",
        "para",
        "pero",
        "porque",
        "puede",
        "pueden",
        "queda",
        "salvo",
        "segun",
        "sido",
        "siendo",
        "sino",
        "sobre",
        "toda",
        "todas",
        "todo",
        "todos",
    }
)

#: Familias de candidato, en orden de preferencia cuando dos empatan (la regla es mas concreta que el dato).
FAMILIA_REGLA = "regla"
FAMILIA_DOCUMENTO = "documento"
FAMILIA_VARIABLE = "variable"
FAMILIAS = (FAMILIA_REGLA, FAMILIA_DOCUMENTO, FAMILIA_VARIABLE)

#: Peso reconocido minimo para aceptar un candidato: equivale a un termino exclusivo de ese candidato.
PESO_MINIMO = Decimal("1")

#: Y ademas hay que reconocer esta parte del peso total del candidato.
COBERTURA_MINIMA = Decimal("0.2")

#: Un motivo senala a menudo dos cosas (la regla y el documento que la arregla): se proponen las dos.
MAXIMO_ITEMS_POR_MOTIVO = 3

#: Y solo las que se acercan al mejor candidato: por debajo de esta parte de su peso, es ruido.
MARGEN_CANDIDATOS = Decimal("0.6")

#: Techo de confianza del reconocimiento por terminos: el lexico reconoce, no entiende.
CONFIANZA_MAXIMA_LEXICO = Decimal("0.9")

#: Confianza de una cita explicita de identificador ("...incumple R-DOC-01..."): eso no se interpreta.
CONFIANZA_CITA = Decimal("1")

ESCALA_CONFIANZA = Decimal("0.01")


class ErrorRequerimiento(Exception):
    """Requerimiento mal formado, interpretacion sin confirmar humana o reapertura que el ciclo no admite."""


# ---------------------------------------------------------------------------
# Los datos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requerimiento:
    """Lo que dice quien nos para, tal cual, con su documento por huella (`ADR-010` §3)."""

    id: str
    origen: str
    actuacion_id: str
    recibido_en: datetime
    expediente_id: str | None = None
    grupo_id: str | None = None
    #: El texto tal cual lo emitio quien requiere. Es de donde salen las citas: no se reescribe.
    motivos: tuple[str, ...] = ()
    #: El PDF del requerimiento, por su huella. Sin el, un requerimiento externo es un rumor (R-REQ-01).
    informe_sha256: str | None = None
    literal_plataforma: str | None = None
    #: La CN admite una segunda ronda (`docs/02` §5.6). No se acota: `TODO(API-03)`, ver `docs/HUECOS.md`.
    ronda: int = 1

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ErrorRequerimiento("un requerimiento necesita `id`")
        if self.origen not in ORIGENES:
            raise ErrorRequerimiento(
                f"origen de requerimiento desconocido {self.origen!r}; los validos son {list(ORIGENES)} "
                "(`docs/03` §10.5)"
            )
        if not str(self.actuacion_id).strip():
            raise ErrorRequerimiento(f"el requerimiento {self.id!r} no dice sobre que actuacion es")
        if not isinstance(self.recibido_en, datetime) or self.recibido_en.tzinfo is None:
            raise ErrorRequerimiento(
                f"el requerimiento {self.id!r}: `recibido_en` es un instante con zona explicita (UTC); "
                "este modulo no tiene reloj propio"
            )
        if not isinstance(self.motivos, tuple):
            raise ErrorRequerimiento("`motivos` es una tupla de textos tal cual los emitio quien requiere")
        if not isinstance(self.ronda, int) or isinstance(self.ronda, bool) or self.ronda < 1:
            raise ErrorRequerimiento(f"el requerimiento {self.id!r}: `ronda` es un entero >= 1")

    @property
    def alcance(self) -> str:
        """A quien alcanza este requerimiento (`ALCANCE_DE_ORIGEN`). Quien lo propaga es `seguimiento.py`."""
        return ALCANCE_DE_ORIGEN[self.origen]

    @property
    def externo(self) -> bool:
        """`True` si viene de fuera (verificador, GA o CN): entonces exige informe (R-REQ-01)."""
        return self.origen in ORIGENES_EXTERNOS


@dataclass(frozen=True)
class Item:
    """Lo que una interpretacion propone, **con su cita**: sin `texto_literal` no hay item."""

    texto_literal: str
    regla_id: str | None = None
    documento: str | None = None
    variable: str | None = None
    confianza: Decimal = Decimal("0")
    metodo: str = METODO_LEXICO

    def __post_init__(self) -> None:
        if not str(self.texto_literal).strip():
            raise ErrorRequerimiento(
                "un item sin cita no existe: `texto_literal` es el motivo del requerimiento, palabra por "
                "palabra (`ADR-010` §3)"
            )
        if not isinstance(self.confianza, Decimal):
            raise ErrorRequerimiento(
                f"la confianza de un item es Decimal, no {type(self.confianza).__name__} "
                "(`CLAUDE.md` §2: nada de float)"
            )
        if not (Decimal("0") <= self.confianza <= Decimal("1")):
            raise ErrorRequerimiento(f"confianza fuera de [0, 1]: {self.confianza}")
        if not str(self.metodo).strip():
            raise ErrorRequerimiento("un item declara su `metodo` ('lexico' hoy, 'llm:<modelo>' en S3.6)")

    def a_dict(self) -> dict[str, object]:
        return {
            "texto_literal": self.texto_literal,
            "regla_id": self.regla_id,
            "documento": self.documento,
            "variable": self.variable,
            "confianza": self.confianza,
            "metodo": self.metodo,
        }


@dataclass(frozen=True)
class Interpretacion:
    """La propuesta de un `Interprete`. Mientras no la confirme un humano, no reabre nada (R-REQ-02)."""

    requerimiento_id: str
    version_interprete: str
    items: tuple[Item, ...] = ()
    confirmada_por_humano: bool = False
    confirmada_por: str | None = None

    def __post_init__(self) -> None:
        if not str(self.requerimiento_id).strip():
            raise ErrorRequerimiento("una interpretacion dice de que requerimiento es")
        if not isinstance(self.items, tuple):
            raise ErrorRequerimiento("`items` es una tupla")
        for item in self.items:
            if not isinstance(item, Item):
                raise ErrorRequerimiento(f"se esperaba un Item y llego {type(item).__name__}")

    @property
    def escala_a_humano(self) -> bool:
        """Cero items = `no_lo_se`: escala a revision humana en vez de inventar una regla plausible."""
        return not self.items

    @property
    def reglas(self) -> tuple[str, ...]:
        """Las reglas propuestas, sin repetir y en el orden en que se reconocieron."""
        vistas: list[str] = []
        for item in self.items:
            if item.regla_id and item.regla_id not in vistas:
                vistas.append(item.regla_id)
        return tuple(vistas)

    @property
    def documentos(self) -> tuple[str, ...]:
        """Los documentos propuestos, sin repetir y en el orden en que se reconocieron."""
        vistos: list[str] = []
        for item in self.items:
            if item.documento and item.documento not in vistos:
                vistos.append(item.documento)
        return tuple(vistos)

    def a_dict(self) -> dict[str, object]:
        return {
            "requerimiento_id": self.requerimiento_id,
            "version_interprete": self.version_interprete,
            "items": [item.a_dict() for item in self.items],
            "confirmada_por_humano": self.confirmada_por_humano,
            "confirmada_por": self.confirmada_por,
        }


# ---------------------------------------------------------------------------
# La interfaz y el lexico
# ---------------------------------------------------------------------------


@runtime_checkable
class Interprete(Protocol):
    """Contrato de todo interprete de requerimientos (lexico hoy, LLM en S3.6, siempre con cita)."""

    version: str

    def interpretar(self, requerimiento: Requerimiento, *, spec: object) -> Interpretacion: ...


def normalizar(texto: str) -> str:
    """Minusculas, sin tildes y con los espacios colapsados (comparacion de motivos y de terminos)."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.lower().split())


def terminos(texto: str) -> frozenset[str]:
    """Los terminos significativos de un texto: >= 4 letras o con digito, sin palabras de relleno."""
    encontrados = {
        pieza
        for pieza in re.split(r"[^0-9a-z]+", normalizar(texto))
        if pieza
        and pieza not in PALABRAS_VACIAS
        and (len(pieza) >= LONGITUD_MINIMA_TERMINO or any(c.isdigit() for c in pieza))
    }
    return frozenset(encontrados)


@dataclass(frozen=True)
class Candidato:
    """Algo de la spec que un motivo puede senalar: una regla, un documento o una variable."""

    clave: str
    familia: str
    terminos: frozenset[str]
    #: Identificadores que se pueden citar tal cual en un motivo (`R-DOC-01`, `DOC-03`, ...).
    citas: tuple[str, ...] = ()


def _texto_de(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, Mapping):
        return " ".join(_texto_de(v) for v in valor.values())
    if isinstance(valor, Sequence):
        return " ".join(_texto_de(v) for v in valor)
    return str(valor)


def _campo(origen: object, nombre: str) -> object:
    return origen.get(nombre) if isinstance(origen, Mapping) else getattr(origen, nombre, None)


def candidatos_de(spec: object) -> tuple[Candidato, ...]:
    """El indice de lo que el lexico puede reconocer, **construido de la spec cargada** (ver cabecera).

    Ni un codigo de ficha ni una lista de reglas cableada: lo que la spec declare es lo que se reconoce.
    """
    if spec is None:
        raise ErrorRequerimiento(
            "el interprete lexico necesita la spec activa: lo que puede reconocer sale de ella, no de una "
            "lista en el codigo (`CLAUDE.md` §2 punto 4)"
        )
    candidatos: list[Candidato] = []
    for regla in _campo(spec, "reglas") or ():
        clave = str(_campo(regla, "id") or "").strip()
        if not clave:
            continue
        subsanacion = _campo(regla, "subsanacion") or {}
        texto = " ".join(
            (
                _texto_de(_campo(regla, "descripcion")),
                _texto_de(_campo(subsanacion, "mensaje")),
                _texto_de(_campo(subsanacion, "documentos")),
            )
        )
        equivalente = _campo(regla, "equivalente_plataforma")
        citas = (clave, *(str(equivalente).strip(),)) if equivalente else (clave,)
        candidatos.append(
            Candidato(clave=clave, familia=FAMILIA_REGLA, terminos=terminos(texto), citas=citas)
        )
    for documento in _campo(spec, "documentacion") or ():
        clave = str(_campo(documento, "tipo") or "").strip()
        if not clave:
            continue
        texto = " ".join(
            (
                clave.replace("_", " "),
                _texto_de(_campo(documento, "nombre")),
                _texto_de(_campo(documento, "requisitos")),
            )
        )
        identificador = _campo(documento, "id")
        citas = (str(identificador).strip(),) if identificador else ()
        candidatos.append(
            Candidato(clave=clave, familia=FAMILIA_DOCUMENTO, terminos=terminos(texto), citas=citas)
        )
    variables = _campo(spec, "variables") or {}
    nombres = variables.keys() if isinstance(variables, Mapping) else ()
    for nombre in nombres:
        definicion = variables[nombre] if isinstance(variables, Mapping) else {}
        texto = " ".join(
            (
                str(nombre).replace("_", " "),
                _texto_de(_campo(definicion, "definicion")),
                _texto_de(_campo(definicion, "descripcion")),
            )
        )
        candidatos.append(Candidato(clave=str(nombre), familia=FAMILIA_VARIABLE, terminos=terminos(texto)))
    return tuple(c for c in candidatos if c.terminos or c.citas)


def pesos_de(candidatos: Iterable[Candidato]) -> dict[str, Decimal]:
    """Peso de cada termino: `1 / candidatos que lo contienen`. Lo comun pesa poco (ver cabecera)."""
    frecuencia: Counter[str] = Counter()
    for candidato in candidatos:
        frecuencia.update(candidato.terminos)
    return {termino: Decimal(1) / Decimal(veces) for termino, veces in frecuencia.items()}


def _peso(conjunto: Iterable[str], pesos: Mapping[str, Decimal]) -> Decimal:
    return sum((pesos.get(termino, Decimal(0)) for termino in conjunto), Decimal(0))


def _cita(motivo: str) -> str:
    """La cita de un motivo: el motivo mismo, con los espacios colapsados y acotado."""
    return " ".join(str(motivo).split())[:LONGITUD_CITA]


def _citado_en(texto: str, identificador: object) -> bool:
    """`True` si el identificador aparece en el texto **delimitado**, no dentro de otro identificador.

    Sin esto, `DOC-01` (el documento) se daria por citado dentro de `R-DOC-01` (la regla), que es otra cosa.
    """
    aguja = normalizar(str(identificador or ""))
    if not aguja:
        return False
    limite = set("0123456789abcdefghijklmnopqrstuvwxyz-")
    inicio = texto.find(aguja)
    while inicio >= 0:
        fin = inicio + len(aguja)
        antes = texto[inicio - 1] if inicio > 0 else ""
        despues = texto[fin] if fin < len(texto) else ""
        if antes not in limite and despues not in limite:
            return True
        inicio = texto.find(aguja, inicio + 1)
    return False


def cita_verbatim(item: Item, requerimiento: Requerimiento) -> bool:
    """`True` si la cita del item esta, palabra por palabra, en algun motivo del requerimiento."""
    aguja = normalizar(item.texto_literal)
    return bool(aguja) and any(aguja in normalizar(motivo) for motivo in requerimiento.motivos)


class InterpreteLexico:
    """Interprete determinista: reconoce en el motivo los terminos de la spec. Sin LLM, sin adivinar.

    Dos interpretaciones del mismo requerimiento con la misma spec son identicas, item a item.
    """

    version = VERSION_INTERPRETE

    def interpretar(self, requerimiento: Requerimiento, *, spec: object) -> Interpretacion:
        """La propuesta para este requerimiento. Cero items (`no_lo_se`) es una salida legitima."""
        if not isinstance(requerimiento, Requerimiento):
            raise ErrorRequerimiento(f"se esperaba un Requerimiento y llego {type(requerimiento).__name__}")
        candidatos = candidatos_de(spec)
        pesos = pesos_de(candidatos)
        items: list[Item] = []
        for motivo in requerimiento.motivos:
            cita = _cita(motivo)
            if not cita:
                continue  # sin cita no hay item (`ADR-010` §3)
            citados = self._citados(cita, candidatos)
            if citados:
                items.extend(self._item(candidato, cita, CONFIANZA_CITA) for candidato in citados)
                continue
            items.extend(
                self._item(candidato, cita, confianza)
                for candidato, confianza in self._reconocidos(cita, candidatos, pesos)
            )
        return Interpretacion(
            requerimiento_id=requerimiento.id,
            version_interprete=self.version,
            items=tuple(items),
        )

    @staticmethod
    def _citados(cita: str, candidatos: Sequence[Candidato]) -> tuple[Candidato, ...]:
        """Candidatos cuyo identificador aparece tal cual en el motivo. Eso no se interpreta: se lee."""
        texto = normalizar(cita)
        citados = [
            candidato
            for candidato in candidatos
            if any(_citado_en(texto, identificador) for identificador in candidato.citas)
        ]
        return tuple(sorted(citados, key=lambda c: (FAMILIAS.index(c.familia), c.clave)))

    @staticmethod
    def _reconocidos(
        cita: str, candidatos: Sequence[Candidato], pesos: Mapping[str, Decimal]
    ) -> tuple[tuple[Candidato, Decimal], ...]:
        """Los candidatos que el motivo reconoce, por peso reconocido. Ninguno que no supere los umbrales.

        Se ordena por peso reconocido, no por cobertura: si no, ganaria siempre el candidato con menos
        terminos (dos palabras acertadas de una descripcion corta batirian a tres terminos exclusivos de un
        documento). La cobertura es un **filtro**, para que un candidato larguisimo no gane por acumulacion.

        **Un motivo puede senalar mas de una cosa** y casi siempre lo hace: "no consta la ficha tecnica del
        equipo accionado, necesaria para acreditar que es rotodinamico" senala el documento que falta *y* la
        regla de ambito. El lexico propone los dos (hasta `MAXIMO_ITEMS_POR_MOTIVO`, y solo los que se
        acercan al mejor por `MARGEN_CANDIDATOS`) y **el humano confirma**: quedarse solo con el primero
        seria elegir por el, y para eso esta la puerta de `R-REQ-02`.
        """
        del_motivo = terminos(cita)
        peso_motivo = _peso(del_motivo, pesos)
        puntuados: list[tuple[Decimal, int, str, Candidato, Decimal]] = []
        for candidato in candidatos:
            comunes = candidato.terminos & del_motivo
            if not comunes:
                continue
            peso_comun = _peso(comunes, pesos)
            peso_total = _peso(candidato.terminos, pesos)
            if peso_total <= 0 or peso_comun < PESO_MINIMO:
                continue
            cobertura = peso_comun / peso_total
            if cobertura < COBERTURA_MINIMA:
                continue
            reconocido = peso_comun / peso_motivo if peso_motivo > 0 else Decimal(0)
            confianza = min(CONFIANZA_MAXIMA_LEXICO, (cobertura + reconocido) / 2)
            puntuados.append(
                (peso_comun, FAMILIAS.index(candidato.familia), candidato.clave, candidato, confianza)
            )
        if not puntuados:
            return ()
        ordenados = sorted(puntuados, key=lambda p: (-p[0], p[1], p[2]))
        corte = ordenados[0][0] * MARGEN_CANDIDATOS
        return tuple(
            (fila[3], fila[4].quantize(ESCALA_CONFIANZA))
            for fila in ordenados[:MAXIMO_ITEMS_POR_MOTIVO]
            if fila[0] >= corte
        )

    @staticmethod
    def _item(candidato: Candidato, cita: str, confianza: Decimal) -> Item:
        return Item(
            texto_literal=cita,
            regla_id=candidato.clave if candidato.familia == FAMILIA_REGLA else None,
            documento=candidato.clave if candidato.familia == FAMILIA_DOCUMENTO else None,
            variable=candidato.clave if candidato.familia == FAMILIA_VARIABLE else None,
            confianza=confianza,
            metodo=METODO_LEXICO,
        )


# ---------------------------------------------------------------------------
# La puerta humana: confirmar y reabrir
# ---------------------------------------------------------------------------


def _humano(actor: object, que: str) -> Actor:
    quien = Actor.de(actor)
    if quien.clase != CLASE_HUMANO:
        raise ErrorRequerimiento(
            f"{que} es un acto humano (`R-REQ-02`, `ADR-010` §3); llego actor {quien.clase!r}: una "
            "interpretacion, venga de un lexico o de un modelo, es una propuesta"
        )
    return quien


def confirmar(interpretacion: Interpretacion, *, actor: object) -> Interpretacion:
    """Un humano hace suya la propuesta. Es lo unico que la convierte en algo que puede reabrir (R-REQ-02)."""
    if not isinstance(interpretacion, Interpretacion):
        raise ErrorRequerimiento(f"se esperaba una Interpretacion y llego {type(interpretacion).__name__}")
    quien = _humano(actor, "confirmar una interpretacion")
    return replace(interpretacion, confirmada_por_humano=True, confirmada_por=quien.id)


def _sellar(
    log: LogEventos,
    tipo: str,
    payload: Mapping[str, object],
    *,
    instante: datetime,
    actor: Actor,
) -> tuple[Evento, bool]:
    """Anade el evento una sola vez y sin envenenar el log (lo comparte con `engine/seguimiento.py`)."""
    try:
        return anadir_una_vez(log, tipo, payload, instante=instante, actor=actor)
    except ErrorSeguimiento as exc:
        raise ErrorRequerimiento(str(exc)) from exc
    except ErrorEstado as exc:  # pragma: no cover - `anadir_una_vez` ya lo traduce
        raise ErrorRequerimiento(str(exc)) from exc


def reabrir(
    log: LogEventos,
    requerimiento: Requerimiento,
    interpretacion: Interpretacion,
    *,
    actor: object,
    confirmado_en: datetime | None = None,
) -> tuple[Evento, ...]:
    """Reabre la subsanacion de una actuacion por un requerimiento interpretado y **confirmado**.

    Devuelve los eventos escritos: `RequerimientoRecibido` (el hecho, que mueve el ciclo a
    `PENDIENTE_SUBSANACION` con su `origen`) y `RequerimientoInterpretado` (la lectura, con la marca
    `confirmada` que el propio log exige que firme un humano).

    No contagia: el alcance de `GA`/`CN` lo ejecuta `engine/seguimiento.py` sobre el expediente (R-REQ-04).
    No tiene reloj: el instante es el del requerimiento salvo que se diga otro.
    """
    if not isinstance(log, LogEventos):
        raise ErrorRequerimiento(f"se esperaba un LogEventos y llego {type(log).__name__}")
    if not isinstance(requerimiento, Requerimiento):
        raise ErrorRequerimiento(f"se esperaba un Requerimiento y llego {type(requerimiento).__name__}")
    if not isinstance(interpretacion, Interpretacion):
        raise ErrorRequerimiento(f"se esperaba una Interpretacion y llego {type(interpretacion).__name__}")
    if log.actuacion_id != requerimiento.actuacion_id:
        raise ErrorRequerimiento(
            f"el log es de la actuacion {log.actuacion_id!r} y el requerimiento de "
            f"{requerimiento.actuacion_id!r}"
        )
    if interpretacion.requerimiento_id != requerimiento.id:
        raise ErrorRequerimiento(
            f"la interpretacion es del requerimiento {interpretacion.requerimiento_id!r} y se pretende "
            f"reabrir con {requerimiento.id!r}"
        )
    # R-REQ-01: un requerimiento externo sin informe es un rumor.
    if requerimiento.externo and not str(requerimiento.informe_sha256 or "").strip():
        raise ErrorRequerimiento(
            f"el requerimiento {requerimiento.id!r} es de origen {requerimiento.origen} y no trae "
            "`informe_sha256`: toda subsanacion de origen externo referencia un requerimiento con informe "
            "(R-REQ-01, `docs/04` §10.4)"
        )
    # R-REQ-02: las dos condiciones, no una.
    if not interpretacion.confirmada_por_humano:
        raise ErrorRequerimiento(
            f"la interpretacion del requerimiento {requerimiento.id!r} no esta confirmada por un humano: "
            "una propuesta no reabre sola (R-REQ-02, `ADR-010` §3)"
        )
    quien = _humano(actor, "reabrir una subsanacion")
    sin_cita = [item for item in interpretacion.items if not cita_verbatim(item, requerimiento)]
    if sin_cita:
        raise ErrorRequerimiento(
            f"la interpretacion del requerimiento {requerimiento.id!r} propone "
            f"{len(sin_cita)} item(s) cuya cita no esta en los motivos del requerimiento: sin cita no hay "
            "item (`ADR-010` §3)"
        )
    instante = confirmado_en if confirmado_en is not None else requerimiento.recibido_en
    if not isinstance(instante, datetime) or instante.tzinfo is None:
        raise ErrorRequerimiento("`confirmado_en` es un instante con zona explicita (UTC) o nada")
    hecho = {
        "origen": requerimiento.origen,
        "requerimiento_id": requerimiento.id,
        "requerimiento_ref": requerimiento.id,
        "informe_sha256": requerimiento.informe_sha256,
        "literal_plataforma": requerimiento.literal_plataforma,
        "expediente_id": requerimiento.expediente_id,
        "grupo_id": requerimiento.grupo_id,
        "alcance": requerimiento.alcance,
        "ronda": requerimiento.ronda,
        "motivos": list(requerimiento.motivos),
        "afectada_directamente": True,
    }
    lectura = {
        "requerimiento_id": requerimiento.id,
        "version_interprete": interpretacion.version_interprete,
        "confirmada": True,
        "confirmada_por": interpretacion.confirmada_por or quien.id,
        "items": [item.a_dict() for item in interpretacion.items],
        "reglas": list(interpretacion.reglas),
        "documentos": list(interpretacion.documentos),
    }
    escritos: list[Evento] = []
    for tipo, payload in ((TIPO_REQUERIMIENTO, hecho), (TIPO_INTERPRETACION, lectura)):
        evento, es_nuevo = _sellar(log, tipo, payload, instante=instante, actor=quien)
        if es_nuevo:
            escritos.append(evento)
    return tuple(escritos)


def escalar(
    log: LogEventos,
    requerimiento: Requerimiento,
    interpretacion: Interpretacion | None = None,
    *,
    actor: object,
    motivo: str = "el interprete no sabe a que regla se refiere el requerimiento",
) -> Evento:
    """Escala a revision humana un requerimiento que no se sabe interpretar (`no_lo_se`, `ADR-010` §3).

    No reabre nada: pone la actuacion en `EN_REVISION_HUMANA` para que una persona lo lea. Es la salida
    honesta cuando el lexico no reconoce el motivo, y la que evita inventar una regla plausible.
    """
    if not isinstance(requerimiento, Requerimiento):
        raise ErrorRequerimiento(f"se esperaba un Requerimiento y llego {type(requerimiento).__name__}")
    payload: dict[str, object] = {
        "origen": ORIGEN_ESCALADO,
        "motivo": motivo,
        "requerimiento_id": requerimiento.id,
        "origen_requerimiento": requerimiento.origen,
        "motivos": list(requerimiento.motivos),
    }
    if interpretacion is not None:
        payload["version_interprete"] = interpretacion.version_interprete
        payload["items"] = [item.a_dict() for item in interpretacion.items]
    evento, _ = _sellar(
        log, TIPO_OBSERVACION, payload, instante=requerimiento.recibido_en, actor=Actor.de(actor)
    )
    return evento


__all__ = [
    "ALCANCE_DE_ORIGEN",
    "CONFIANZA_CITA",
    "CONFIANZA_MAXIMA_LEXICO",
    "FAMILIAS",
    "FAMILIA_DOCUMENTO",
    "FAMILIA_REGLA",
    "FAMILIA_VARIABLE",
    "MARGEN_CANDIDATOS",
    "MAXIMO_ITEMS_POR_MOTIVO",
    "METODO_LEXICO",
    "ORIGENES",
    "ORIGENES_EXTERNOS",
    "VERSION_INTERPRETE",
    "Candidato",
    "ErrorRequerimiento",
    "Interpretacion",
    "Interprete",
    "InterpreteLexico",
    "Item",
    "Requerimiento",
    "candidatos_de",
    "cita_verbatim",
    "confirmar",
    "escalar",
    "normalizar",
    "pesos_de",
    "reabrir",
    "terminos",
]
