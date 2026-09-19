"""Contrato C15 (`ADR-011` §4): la forma de una peticion y de una respuesta, y la puerta comun.

`api/` **no calcula nada**. Un comando valida, delega en `engine/` y traduce lo que paso; una lectura
valida, pide el material a `engine/` y proyecta lo que el ambito del rol admite. Un calculo, una evaluacion
de regla o una decision de transicion dentro de `api/` es un defecto, no una optimizacion (`R-UI-11` aguas
arriba).

El orden de la puerta, que es el mismo para comandos y lecturas, y no se altera:

1. **La capacidad existe y es del tipo que se esta invocando.** Un comando no se atiende con `leer`.
2. **`exigir`**: capacidad concedida al perfil, rol resuelto y tenant del principal (`R-UI-01`).
3. **Alcance**: la actuacion es de su tenant y, si el perfil es externo, es parte en ella. Una actuacion de
   otro tenant no llega ni a construirse.
4. **Implementacion**: si la capacidad no tiene manejador, se dice **que falta**, con nombre y apellidos.
   Va despues del permiso a proposito: a quien no tiene la capacidad no se le cuenta que hay detras.
5. **Entrada**: `R-UI-04` (una correccion sin justificacion no se ejecuta) y la prohibicion de coma
   flotante en cualquier magnitud que entre por la API.

**El rol ejercido se calcula aqui y se persiste.** Con A8 aprobada, `engine.eventos.log` exige `actor.rol`
en todo evento humano, y el `autorizador` de `engine.capacidades` comprueba contra la misma matriz que ese
perfil puede producir ese evento. Es la misma regla por los dos lados: la puerta no se rodea escribiendo el
evento a mano. El rol viaja ademas en `Respuesta.rol`, para que el front muestre "actuando como…" sin
volver a deducirlo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from api.permisos import (
    Capacidad,
    Contexto,
    ErrorApi,
    ErrorPermiso,
    Matriz,
    Principal,
    ambito_de,
    capacidad_de,
    exigir,
    matriz,
)
from api.servicios import Servicios, servicios_de
from engine.eventos.log import Actor

#: Clase de actor de todo lo que entra por esta API: detras siempre hay una persona autenticada.
CLASE_ACTOR = "humano"


@dataclass(frozen=True)
class Peticion:
    """Lo que llega: que capacidad, quien, desde donde y con que datos."""

    capacidad: str
    principal: Principal
    contexto: Contexto
    datos: Mapping[str, object] = field(default_factory=dict)

    def exige(self, clave: str) -> object:
        """Un dato obligatorio de la peticion, o `ErrorApi` diciendo cual falta."""
        valor = self.datos.get(clave)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            raise ErrorApi(f"{self.capacidad}: falta el dato {clave!r} en la peticion")
        return valor

    def texto(self, clave: str, por_defecto: str | None = None) -> str | None:
        valor = self.datos.get(clave, por_defecto)
        return None if valor is None else str(valor)

    @property
    def actuacion_id(self) -> str:
        """La actuacion sobre la que se actua: la del contexto o, si no, la de los datos."""
        identificador = self.contexto.actuacion_id or self.datos.get("actuacion_id")
        if identificador is None or not str(identificador).strip():
            raise ErrorApi(f"{self.capacidad}: la peticion no dice sobre que actuacion se actua")
        return str(identificador)


@dataclass(frozen=True)
class Respuesta:
    """Lo que sale: que paso, con que rol, que eventos se escribieron y que datos se proyectaron."""

    capacidad: str
    rol: str
    eventos: tuple[str, ...]
    datos: Mapping[str, object]
    avisos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Salida:
    """Lo que devuelve el manejador de un comando: lo que hizo, sin decidir como se presenta."""

    datos: Mapping[str, object] = field(default_factory=dict)
    eventos: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()


def actor_de(principal: Principal, rol: str) -> Actor:
    """El actor que firma los eventos de esta peticion.

    `rol` es el perfil con el que se esta actuando, ya resuelto por `rol_para`, y **se persiste**: con A8
    aprobada, `engine.eventos.log` exige `actor.rol` en todo evento humano y se niega a sellar uno que ese
    perfil no pueda producir. El mismo valor viaja en `Respuesta.rol` para que el front pueda mostrar
    "actuando como…" sin volver a deducirlo.
    """
    return Actor(clase=CLASE_ACTOR, id=principal.usuario_id, rol=rol)


def _sin_coma_flotante(peticion: Peticion) -> None:
    """Ninguna magnitud entra como `float`: se pierde exactitud antes de llegar al motor (`CLAUDE.md` §2)."""
    flotantes = sorted(clave for clave, valor in peticion.datos.items() if isinstance(valor, float))
    if flotantes:
        raise ErrorApi(
            f"{peticion.capacidad}: {flotantes} llegan como coma flotante. Toda magnitud entra como "
            "cadena o entero y se convierte a Decimal; el ahorro no se calcula con float"
        )


def _comprobar_justificacion(peticion: Peticion, capacidad: Capacidad) -> None:
    """`R-UI-04`: una correccion sin justificacion no se ejecuta, y la justificacion va al log."""
    if not capacidad.exige_justificacion:
        return
    justificacion = peticion.datos.get("justificacion")
    if not isinstance(justificacion, str) or not justificacion.strip():
        raise ErrorApi(
            f"{capacidad.id} ({capacidad.nombre}): exige `justificacion` no vacia. Una correccion sin "
            "justificacion no se ejecuta (`R-UI-04`); lo que se escribe queda en el log"
        )


def comprobar_alcance(matriz_actual: Matriz, rol: str, peticion: Peticion, servicios: Servicios) -> None:
    """Aislamiento: la actuacion es de su tenant y, si el perfil es externo, es parte en ella.

    Si el repositorio no conoce la actuacion, no hay nada que comprobar aqui: el manejador que la necesite
    fallara al pedirla. Lo que no puede pasar, y esto lo impide, es tocar una actuacion **de otro**.
    """
    ambito = ambito_de(matriz_actual, rol)
    identificador = peticion.contexto.actuacion_id or peticion.datos.get("actuacion_id")
    if identificador is None or not ambito.exige_tenant:
        if ambito.solo_actuaciones_propias and identificador is None:
            raise ErrorPermiso(
                f"{peticion.capacidad}: {rol} solo ve las actuaciones en las que es parte, asi que la "
                "peticion tiene que decir cual"
            )
        return
    identificador = str(identificador)
    propietario = servicios.repositorio.tenant_de(identificador)
    if propietario is None:
        return
    if propietario != peticion.principal.tenant_id:
        raise ErrorPermiso(
            f"cruce de tenant: la actuacion {identificador!r} es del tenant {propietario!r} y el "
            f"principal {peticion.principal.usuario_id!r} es de {peticion.principal.tenant_id!r}"
        )
    if ambito.solo_actuaciones_propias:
        partes = servicios.repositorio.partes_de(identificador)
        if peticion.principal.usuario_id not in partes:
            raise ErrorPermiso(
                f"{peticion.capacidad}: {peticion.principal.usuario_id!r} no es parte en la actuacion "
                f"{identificador!r}; {rol} solo ve las suyas"
            )


def preparar(
    peticion: Peticion,
    tipo_esperado: str,
    *,
    servicios: Servicios | None = None,
    matriz_actual: Matriz | None = None,
) -> tuple[Matriz, Capacidad, str, Servicios]:
    """La puerta comun de comandos y lecturas, en el orden de la cabecera. Devuelve el rol ejercido."""
    activa = matriz_actual if matriz_actual is not None else matriz()
    capacidad = capacidad_de(activa, peticion.capacidad)
    if capacidad.tipo != tipo_esperado:
        raise ErrorApi(
            f"{capacidad.id} ({capacidad.nombre}) es de tipo {capacidad.tipo!r} y se esta invocando como "
            f"{tipo_esperado!r}"
        )
    rol = exigir(activa, capacidad.id, peticion.principal, peticion.contexto)
    recursos = servicios_de(servicios)
    comprobar_alcance(activa, rol, peticion, recursos)
    if not capacidad.implementada:
        raise ErrorApi(
            f"{capacidad.id} ({capacidad.nombre}): el contrato existe y la implementacion no. "
            f"Falta: {capacidad.falta}"
        )
    _sin_coma_flotante(peticion)
    _comprobar_justificacion(peticion, capacidad)
    return activa, capacidad, rol, recursos


def manejador_de(registro: Mapping[str, object], capacidad: Capacidad) -> object:
    """El manejador que declara la capacidad. Que no este registrado es un error de arranque."""
    manejador = registro.get(str(capacidad.manejador))
    if manejador is None:
        raise ErrorApi(
            f"{capacidad.id}: la matriz declara el manejador {capacidad.manejador!r} y no hay ninguna "
            "funcion registrada con ese nombre"
        )
    return manejador


__all__ = [
    "CLASE_ACTOR",
    "Contexto",
    "ErrorApi",
    "ErrorPermiso",
    "Peticion",
    "Principal",
    "Respuesta",
    "Salida",
    "actor_de",
    "comprobar_alcance",
    "manejador_de",
    "preparar",
]
