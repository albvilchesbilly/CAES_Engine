"""Modelo de datos de los requerimientos sintéticos y del expediente de tres actuaciones (ADR-010 §5, C12).

Mismo principio que `modelo_caso.py`: **un solo modelo produce el documento y el ground truth**, de modo que
el PDF del requerimiento y lo que se espera que el intérprete reconozca no pueden discrepar. Todo lo que hay
aquí es inventado: organismos, personas, NIF (formato válido, ficticios), números de referencia y plazos.

Un `Motivo` lleva, además del texto tal como lo emitiría quien requiere, **lo que debe reconocerse de él**:

- `regla_esperada`: identificador de una regla real de `spec/IND240_v1.1.yaml`.
- `documento_esperado`: un `tipo` documental real de la misma spec.
- `dificultad`: `explicita` (el texto cita el identificador de la regla) · `lexica` (hay que reconocerlo por
  el vocabulario, sin identificador) · `no_mapeable` (prosa administrativa que no cita regla ni documento:
  debe producir **cero items** y escalar a un humano, ADR-010 §3, decisión 2).
- `pistas`: las subcadenas del propio texto que sostienen el mapeo. Se comprueba en `__post_init__` que están
  literalmente en el texto: si no, la expectativa sería una deducción y no una cita (ADR-010 §3, decisión 1).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

DIFICULTADES = ("explicita", "lexica", "no_mapeable")
ORIGENES = ("verificador", "GA", "CN")
ALCANCE_DE_ORIGEN = {"verificador": "grupo", "GA": "expediente", "CN": "expediente"}


def normalizar(texto: str) -> str:
    """Minúsculas sin tildes: la comprobación de pistas no depende de la acentuación del texto."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Organismo:
    """Quien emite el requerimiento. Ficticio; el nombre lo dice para que nadie lo confunda con uno real."""

    nombre: str
    papel: str  # verificador | organo_gestor_autonomico | coordinacion_nacional
    codigo: str  # código ficticio del organismo en la plataforma
    nif: str | None = None


@dataclass(frozen=True)
class Motivo:
    """Un motivo del requerimiento y lo que debe reconocerse de él."""

    numero: int
    texto: str
    dificultad: str
    regla_esperada: str | None = None
    documento_esperado: str | None = None
    variable_esperada: str | None = None
    pistas: tuple[str, ...] = ()
    nota: str = ""

    def __post_init__(self) -> None:
        if self.dificultad not in DIFICULTADES:
            raise ValueError(f"dificultad desconocida: {self.dificultad}")
        mapea = self.regla_esperada is not None or self.documento_esperado is not None
        if self.dificultad == "no_mapeable":
            if mapea or self.pistas:
                raise ValueError(f"motivo {self.numero}: un motivo no mapeable no declara regla ni pistas")
        else:
            if not mapea:
                raise ValueError(f"motivo {self.numero}: un motivo mapeable declara regla o documento")
            if not self.pistas:
                raise ValueError(f"motivo {self.numero}: sin pistas no hay cita que sostenga el mapeo")
        texto = normalizar(self.texto)
        for pista in self.pistas:
            if normalizar(pista) not in texto:
                raise ValueError(f"motivo {self.numero}: la pista {pista!r} no está en el texto del motivo")
        if self.dificultad == "explicita" and self.regla_esperada is not None:
            if normalizar(self.regla_esperada) not in texto:
                raise ValueError(
                    f"motivo {self.numero}: dificultad 'explicita' exige que el texto cite "
                    f"{self.regla_esperada}"
                )

    @property
    def tipo_esperado(self) -> str:
        """`regla` · `documento` · `nada` (escala a humano). Es la columna que contrasta el intérprete."""
        if self.dificultad == "no_mapeable":
            return "nada"
        return "regla" if self.regla_esperada is not None else "documento"


@dataclass(frozen=True)
class Requerimiento:
    """Un requerimiento sintético: cabecera, motivos y el alcance que debe tener sobre el expediente."""

    id: str
    origen: str
    organismo: Organismo
    literal_plataforma: str
    fase: str
    asunto: str
    referencia_oficial: str
    recibido_en: datetime
    plazo_dias: int
    actuacion_id: str
    expediente_id: str | None
    grupo_id: str | None
    motivos: tuple[Motivo, ...]
    preambulo: str
    advertencia: str
    ronda: int = 1

    def __post_init__(self) -> None:
        if self.origen not in ORIGENES:
            raise ValueError(f"origen desconocido: {self.origen}")
        if not self.motivos:
            raise ValueError(f"{self.id}: un requerimiento sin motivos no es un requerimiento")
        if [m.numero for m in self.motivos] != list(range(1, len(self.motivos) + 1)):
            raise ValueError(f"{self.id}: los motivos se numeran 1..n en orden")
        if self.ronda < 1:
            raise ValueError(f"{self.id}: la ronda empieza en 1")
        if self.origen in ("GA", "CN") and self.expediente_id is None:
            raise ValueError(f"{self.id}: un requerimiento de {self.origen} alcanza a un expediente")

    @property
    def alcance(self) -> str:
        """Alcance declarado por el origen (ADR-010 §3). Con `grupo_id` a `None`, el grupo es la actuación."""
        return ALCANCE_DE_ORIGEN[self.origen]

    @property
    def nombre_fichero(self) -> str:
        return f"{self.id}_{self.origen}.pdf"

    @property
    def titulo(self) -> str:
        return f"Requerimiento {self.id} – {self.asunto}"


@dataclass(frozen=True)
class ActuacionEnExpediente:
    """Una actuación del expediente: su identidad en la plataforma y el caso del banco que la materializa."""

    actuacion_id: str
    codigo_identificativo_propio: str
    caso_id: str
    carpeta: str
    estado_plataforma: str = "VERIFICADA_FAVORABLE"


@dataclass(frozen=True)
class Expediente:
    """Agregación oficial de actuaciones `VERIFICADA_FAVORABLE` con misma CCAA + año + sector + verificador
    (`CLAUDE.md` §3). Las cuatro claves son lo que lo hace expediente y lo que comprueba el test."""

    id: str
    ccaa: str
    anio: int
    sector: str
    verificador: Organismo
    estado_plataforma: str
    presentado_en: date
    actuaciones: tuple[ActuacionEnExpediente, ...]
    nota_solape: str = ""

    def __post_init__(self) -> None:
        if len(self.actuaciones) < 3:
            raise ValueError(
                f"{self.id}: con menos de tres actuaciones el contagio no se distingue de no contagiar"
            )
        ids = [a.actuacion_id for a in self.actuaciones]
        codigos = [a.codigo_identificativo_propio for a in self.actuaciones]
        if len(set(ids)) != len(ids) or len(set(codigos)) != len(codigos):
            raise ValueError(f"{self.id}: identidades repetidas entre actuaciones")
        if any(a.estado_plataforma != "VERIFICADA_FAVORABLE" for a in self.actuaciones):
            raise ValueError(f"{self.id}: al expediente solo entra lo VERIFICADA_FAVORABLE (docs/02 §5.1)")

    @property
    def ids_actuacion(self) -> tuple[str, ...]:
        return tuple(a.actuacion_id for a in self.actuaciones)

    def actuacion(self, actuacion_id: str) -> ActuacionEnExpediente:
        for a in self.actuaciones:
            if a.actuacion_id == actuacion_id:
                return a
        raise KeyError(actuacion_id)
