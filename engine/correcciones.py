"""Correcciones humanas: una decision de una persona convertida en evidencia (`ADR-013` §1 y §2, C20).

`R-UI-02` —la pantalla de revision no tiene control para cambiar el veredicto— se sostiene sobre una frase:
«se corrige el dato y el motor recalcula». Este modulo es la primera mitad de la segunda mitad: traduce el
evento `DatoCorregidoPorHumano` del log a una `Evidencia` con sus **tres capas completas**, para que la
consolidacion la trate como una fuente mas y el motor recalcule **sin saber que vino de una persona**.

| Capa | Que lleva una correccion |
|---|---|
| Documento | El evento: `evento_id` como `doc_id` (la huella que lo encadena al log esta en el propio log) |
| Interpretacion | `metodo = "correccion_humana"`, `texto_literal` = la justificacion, `confianza = 1` |
| Calculo | El valor entra en la consolidacion como cualquier otra fuente fiable |

Las cinco reglas de `ADR-013` §2, y donde vive cada una:

1. **La ultima correccion de cada `(variable, num_serie_motor)` manda.** El log es solo-anadir: corregir dos
   veces no es un conflicto, es cambiar de opinion. `de_log` devuelve **todas** en orden de secuencia (las
   dos quedan en la traza) y quien elige la ultima es `evidencias._consolidar_grupo`, que es quien ya sabe
   ordenar fuentes.
2. **Precedencia sobre la evidencia documental**, y solo sobre ella. Vive en un unico sitio,
   `evidencias._consolidar_grupo`, al lado de la precedencia que ya existia (OCR por debajo de lo nativo):
   una correccion es una fuente mas, con la maxima precedencia, no una rama nueva del consolidador.
3. **El conflicto no se borra: se resuelve.** Las evidencias enfrentadas siguen en
   `DatoConsolidado.evidencias` con su cita y el consolidador deja un aviso que nombra lo que se descarto.
4. **Una correccion no inventa una variable que la spec no declara** (regla de oro 4): `validar`.
5. **Sin justificacion no hay evidencia**, porque no hay cita (regla de oro 2): `Correccion.__post_init__`.
   No hay justificacion por defecto y no se inventa ninguna.

Dos decisiones propias (candidatas a ADR; ver el informe de S3.8):

- **`tipo_evidencia = "demostrado"`.** Una correccion no es `derivado` (no sale de un registro) ni merece
  `declarado` (no es alguien diciendo un numero sin mirar: es alguien que ha visto las evidencias
  enfrentadas). La consecuencia buscada es que corregir a mano una variable que la spec exige `derivado`
  —`N2`, con `R-EVD-04`— la deja marcada como no derivada, que es exactamente lo que ha pasado.
- **Una correccion que el motor ignoraria en silencio es un error**, no un no-op: corregir una variable de
  unidad sin decir que unidad, o una de actuacion nombrando una, se rechaza en `validar`. El nivel lo dice
  la spec (`variables[].nivel`), nunca este modulo.

Este modulo **no lee el log por su cuenta** ni importa `engine.eventos`: `de_log` consume el log por
atributos (`por_tipo`, `eventos`, `evento.datos`), igual que `engine.eventos.grabacion` consume la
`Actuacion` del motor. Asi `engine/motor.py` no adquiere una dependencia de donde viven los eventos
(`ADR-013` §3). Nada de `eval`, nada de `float`, ninguna ficha nombrada.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from engine.evidencias import (
    CONFIANZA_FIABLE,
    METODO_CORRECCION,
    Evidencia,
)
from engine.spec_registry import NIVELES_VARIABLE_UNIDAD, Spec

#: Metodo de la evidencia que produce una correccion (el mismo que reconoce `engine.evidencias`).
METODO = METODO_CORRECCION

#: Tipo del evento del log del que sale una correccion (`engine.eventos.catalogo`).
TIPO_EVENTO = "DatoCorregidoPorHumano"

#: `tipo_doc` de la evidencia: la "fuente" de una correccion es el propio acto humano (ver cabecera).
TIPO_DOC = METODO_CORRECCION

#: `tipo_evidencia` de una correccion (ver cabecera: ni derivado ni declarado).
TIPO_EVIDENCIA = "demostrado"

#: Una correccion es una fuente fiable: la persona ha visto las evidencias y decide.
CONFIANZA = CONFIANZA_FIABLE

#: `pagina` de la cita: una correccion no sale de una pagina de un PDF.
PAGINA = 0

#: Claves del payload de `DatoCorregidoPorHumano` (las que escribe `api/comandos/actuaciones.py`).
CLAVE_VARIABLE = "variable"
CLAVE_VALOR = "valor"
CLAVE_JUSTIFICACION = "justificacion"
CLAVE_SERIE = "num_serie_motor"
CLAVES_ORIGEN = ("origen", "motivo")


class ErrorCorreccion(Exception):
    """Correccion mal formada o que la ficha no admite (sin justificacion, variable no declarada)."""


def _texto_valor(valor: object) -> str:
    """El valor como texto, tal como lo lleva una `Evidencia`. Un `float` es un defecto (`CLAUDE.md` §2)."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, float):
        raise ErrorCorreccion(
            f"valor {valor!r} de tipo float: toda magnitud es `Decimal` o texto (`CLAUDE.md` §2)"
        )
    if isinstance(valor, Decimal):
        return format(valor.normalize(), "f") if valor.is_finite() else str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, str):
        return valor
    if isinstance(valor, int):
        return str(valor)
    raise ErrorCorreccion(f"valor de tipo {type(valor).__name__} no convertible a texto: {valor!r}")


@dataclass(frozen=True)
class Correccion:
    """Contrato C20 de `ADR-013` §2: lo que una persona decidio, con quien, cuando y por que.

    `valor` es **texto**: a `Decimal` lo convierte la consolidacion con el `tipo` de la spec, nunca un
    `float` por el camino. `actor_rol` es obligatorio (A8): una persona actua siempre con un perfil.
    """

    variable: str
    valor: str
    justificacion: str
    actor_id: str
    actor_rol: str
    evento_id: str
    instante: datetime
    num_serie_motor: str | None = None
    origen: str | None = None

    def __post_init__(self) -> None:
        for campo in ("variable", "valor", "actor_id", "actor_rol", "evento_id"):
            valor = getattr(self, campo)
            if not isinstance(valor, str) or not valor.strip():
                raise ErrorCorreccion(f"una correccion necesita `{campo}` (llego {valor!r})")
        if not isinstance(self.justificacion, str) or not self.justificacion.strip():
            raise ErrorCorreccion(
                f"la correccion de {self.variable!r} no trae justificacion: sin justificacion no hay cita, "
                "y sin cita no entra (regla de oro 2; `R-UI-04`, `ADR-013` §2 regla 5)"
            )
        if not isinstance(self.instante, datetime):
            raise ErrorCorreccion(f"`instante` de la correccion de {self.variable!r} debe ser un datetime")
        if self.instante.tzinfo is None or self.instante.utcoffset() is None:
            raise ErrorCorreccion(
                f"`instante` de la correccion de {self.variable!r} llega sin zona horaria: el log solo "
                "sella instantes con zona explicita (`ADR-003` H-08)"
            )
        if self.num_serie_motor is not None:
            serie = str(self.num_serie_motor).strip()
            object.__setattr__(self, "num_serie_motor", serie or None)

    @property
    def clave(self) -> tuple[str, str | None]:
        """Lo que identifica el dato corregido: la ultima correccion de cada clave manda (regla 1)."""
        return (self.variable, self.num_serie_motor)

    @property
    def firma(self) -> str:
        """Quien, con que rol y cuando: lo que va en `extractor_version` de la evidencia.

        No va en `interpretacion` **a proposito**: ese campo es de los `INT-xx` (`engine.reglas`
        `_interpretaciones` lo lee como identificador de interpretacion aplicada) y meter ahi texto libre
        inventaria una interpretacion que la spec no declara.
        """
        firma = f"{self.actor_id}/{self.actor_rol}@{self.instante.isoformat()}"
        return f"{firma}#{self.origen}" if self.origen else firma

    def a_dict(self) -> dict[str, object]:
        return {
            "variable": self.variable,
            "valor": self.valor,
            "justificacion": self.justificacion,
            "actor_id": self.actor_id,
            "actor_rol": self.actor_rol,
            "evento_id": self.evento_id,
            "instante": self.instante.isoformat(),
            "num_serie_motor": self.num_serie_motor,
            "origen": self.origen,
        }


def a_evidencia(correccion: Correccion) -> Evidencia:
    """La correccion como `Evidencia`, con las tres capas (`ADR-013` §1).

    La cita literal es **la justificacion que escribio la persona**: por eso `R-UI-04` deja de ser
    burocracia de interfaz. Quien, con que rol y cuando va en `extractor_version` (`Correccion.firma`), que
    es el campo de "quien produjo esta lectura"; `interpretacion` se deja vacia porque es de los `INT-xx`.
    """
    if not isinstance(correccion, Correccion):
        raise ErrorCorreccion(f"se esperaba una Correccion y llego {type(correccion).__name__}")
    return Evidencia(
        variable=correccion.variable,
        valor=correccion.valor,
        doc_id=correccion.evento_id,
        tipo_doc=TIPO_DOC,
        pagina=PAGINA,
        texto_literal=correccion.justificacion,
        metodo=METODO,
        confianza=CONFIANZA,
        extractor_version=correccion.firma,
        tipo_evidencia=TIPO_EVIDENCIA,
        num_serie_motor=correccion.num_serie_motor,
    )


def a_evidencias(correcciones: Iterable[Correccion]) -> list[Evidencia]:
    """Las correcciones como evidencias, **en el mismo orden**: el orden es el que decide cual manda."""
    return [a_evidencia(c) for c in correcciones]


# ---------------------------------------------------------------------------
# Lectura del log (por atributos: este modulo no importa `engine.eventos`)
# ---------------------------------------------------------------------------


def _payload(evento: Any) -> Mapping[str, object]:
    datos = getattr(evento, "datos", None)
    if isinstance(datos, Mapping):
        return datos
    payload = getattr(evento, "payload", None)
    if isinstance(payload, Mapping):
        return payload
    raise ErrorCorreccion(f"no parece un evento del log: {evento!r}")


def _origen(payload: Mapping[str, object]) -> str | None:
    for clave in CLAVES_ORIGEN:
        valor = payload.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


def de_evento(evento: Any) -> Correccion:
    """Un `DatoCorregidoPorHumano` del log como `Correccion`. No valida contra la spec: eso es `validar`."""
    tipo = getattr(evento, "tipo", None)
    if tipo is not None and tipo != TIPO_EVENTO:
        raise ErrorCorreccion(f"una correccion sale de un {TIPO_EVENTO}, no de un {tipo!r}")
    payload = _payload(evento)
    actor = getattr(evento, "actor", None)
    actor_id = getattr(actor, "id", None)
    actor_rol = getattr(actor, "rol", None)
    if not actor_id or not actor_rol:
        raise ErrorCorreccion(
            f"{TIPO_EVENTO} {getattr(evento, 'evento_id', None)!r} sin actor con `rol`: una persona actua "
            "siempre con un perfil y el perfil ejercido es parte de la traza (A8, `ADR-006`)"
        )
    variable = payload.get(CLAVE_VARIABLE)
    if not isinstance(variable, str) or not variable.strip():
        raise ErrorCorreccion(f"{TIPO_EVENTO} sin `variable` en el payload")
    if CLAVE_VALOR not in payload or payload.get(CLAVE_VALOR) is None:
        raise ErrorCorreccion(f"la correccion de {variable!r} no trae `valor`")
    justificacion = payload.get(CLAVE_JUSTIFICACION)
    serie = payload.get(CLAVE_SERIE)
    return Correccion(
        variable=variable.strip(),
        valor=_texto_valor(payload.get(CLAVE_VALOR)),
        justificacion=justificacion if isinstance(justificacion, str) else "",
        actor_id=str(actor_id),
        actor_rol=str(actor_rol),
        evento_id=str(getattr(evento, "evento_id", "") or ""),
        instante=getattr(evento, "ocurrido_en", None),  # type: ignore[arg-type]
        num_serie_motor=None if serie is None else str(serie),
        origen=_origen(payload),
    )


def de_log(log: Any) -> tuple[Correccion, ...]:
    """Las correcciones del log, **en orden de secuencia** (`ADR-013` §2, C20).

    Devuelve todas, no solo la ultima de cada clave: las dos quedan en la traza y es la consolidacion la que
    aplica la ultima (regla 1). El log se consume por atributos; este modulo no importa `engine.eventos`.

    **Salvo las que el ciclo rechazo** (cerrado el 20/09/2026). `ADR-013` §4 decia que una correccion
    post-firma «no esta en el log», y **era falso**: `engine.estados` no levanta ante un cambio de datos
    posterior a la firma, lo **anota** en `Proyeccion.rechazos` y el evento queda sellado igual. Sin este
    filtro, reprocesar una actuacion firmada aplicaba una correccion que la inalterabilidad prohibe
    (`docs/02` §5.4), que es de las reglas que no se negocian.

    Se filtra **aqui**, no en quien llama: `de_log` tiene el log, asi que puede proyectarlo, y una guarda que
    depende de que el llamante se acuerde no es una guarda. Es el mismo criterio con el que se cerraron
    `R-REQ-02` y el alcance por tenant de `api/`.
    """
    por_tipo = getattr(log, "por_tipo", None)
    if callable(por_tipo):
        eventos = list(por_tipo(TIPO_EVENTO))
    else:
        eventos = [e for e in log if getattr(e, "tipo", None) == TIPO_EVENTO]
    eventos.sort(key=lambda e: getattr(e, "secuencia", 0))
    rechazados = _rechazados_por_el_ciclo(log)
    admitidos = [e for e in eventos if getattr(e, "evento_id", None) not in rechazados]
    return tuple(de_evento(evento) for evento in admitidos)


def _rechazados_por_el_ciclo(log: Any) -> frozenset[str]:
    """Los `evento_id` que la maquina de estados anoto como rechazo (inalterabilidad post-firma).

    Se importa aqui dentro y no arriba porque es el unico punto de este modulo que necesita la proyeccion, y
    un log que no se puede proyectar (uno de prueba, uno parcial) no debe impedir leer sus correcciones: en
    ese caso no se filtra nada y se dice por que en el propio codigo, no en un comentario lejano.
    """
    from engine.estados import ErrorEstado, proyectar

    try:
        proyeccion = proyectar(log)
    except (ErrorEstado, AttributeError, TypeError):
        return frozenset()
    rechazos = getattr(proyeccion, "rechazos", ())
    return frozenset(
        str(anotacion["evento_id"])
        for anotacion in rechazos
        if isinstance(anotacion, Mapping) and anotacion.get("evento_id")
    )


# ---------------------------------------------------------------------------
# Validacion contra la ficha (regla 4: la ficha dice que existe)
# ---------------------------------------------------------------------------


def _es_de_unidad(declaracion: Mapping[str, object]) -> bool:
    return declaracion.get("nivel") in NIVELES_VARIABLE_UNIDAD


def validar(correcciones: Sequence[Correccion], spec: Spec) -> tuple[Correccion, ...]:
    """Comprueba las correcciones contra la ficha y las devuelve tal cual (`ADR-013` §2 regla 4).

    Dos cosas, las dos dichas por la spec y ninguna por este modulo:

    1. La variable existe en `variables` de la ficha. Una correccion no inventa un dato: la ficha sigue
       siendo la que dice que existe (regla de oro 4).
    2. El ambito coincide con el `nivel` declarado. Una correccion de una variable de unidad sin
       `num_serie_motor` —o de una de actuacion con el— no la consumiria nadie: el motor la ignoraria en
       silencio, que es peor que rechazarla.
    """
    for correccion in correcciones:
        if not isinstance(correccion, Correccion):
            raise ErrorCorreccion(f"se esperaba una Correccion y llego {type(correccion).__name__}")
        declaracion = spec.variables.get(correccion.variable)
        if declaracion is None:
            raise ErrorCorreccion(
                f"la ficha {spec.codigo} v{spec.version_ficha} no declara la variable "
                f"{correccion.variable!r}: una correccion no inventa un dato (`ADR-013` §2 regla 4)"
            )
        if _es_de_unidad(declaracion) and correccion.num_serie_motor is None:
            raise ErrorCorreccion(
                f"{correccion.variable!r} es una variable de unidad en la ficha {spec.codigo}: la "
                "correccion tiene que decir de que unidad (`num_serie_motor`)"
            )
        if not _es_de_unidad(declaracion) and correccion.num_serie_motor is not None:
            raise ErrorCorreccion(
                f"{correccion.variable!r} es una variable de actuacion en la ficha {spec.codigo} y la "
                f"correccion la atribuye a la unidad {correccion.num_serie_motor!r}"
            )
    return tuple(correcciones)


__all__ = [
    "CONFIANZA",
    "METODO",
    "PAGINA",
    "TIPO_DOC",
    "TIPO_EVENTO",
    "TIPO_EVIDENCIA",
    "Correccion",
    "ErrorCorreccion",
    "a_evidencia",
    "a_evidencias",
    "de_evento",
    "de_log",
    "validar",
]
