"""Contrato C14 (`ADR-011` §3): permisos e inferencia de rol sobre la matriz del nucleo.

**Aqui no hay ni un `if perfil == ...` ni un identificador de capacidad.** Todo lo que este modulo decide
sale de `engine/capacidades.yaml`, cargado y validado por `engine.capacidades` (regla de oro 4 aplicada a
los permisos). Hay un test que lee este fuente y lo comprueba. Cambiar quien puede hacer que es cambiar el
YAML, y se cambia en un solo sitio: la matriz vive en `engine/` porque el log tambien la necesita (A8), y
`api/` **la consume**, no la copia.

Cuatro reglas, las de `ADR-011` §3:

1. **`R-UI-01`: la autorizacion ocurre en el servidor.** Ocultar un control no autoriza nada. Todo comando
   y toda lectura pasan por `exigir` antes de tocar `engine/`.
2. **Aislamiento por tenant, siempre.** Una capacidad de tenant sobre otro tenant es `ErrorPermiso`, aunque
   el perfil la conceda. El `tenant_id` que manda es el del principal autenticado, no el del contexto: si
   no coinciden, no se elige uno, se deniega.
3. **Inferencia del rol.** Si la capacidad la concede un solo perfil del usuario, ese es el rol. Si la
   conceden varios, desempata la pantalla del contexto (dos perfiles de la misma superficie solo se
   distinguen por la pantalla: es justo el caso de las dos capacidades compartidas del workspace) y, en su
   defecto, la superficie. Si sigue sin resolverse es `ErrorApi`: **no se elige uno al azar**.
4. **Denegacion silenciosa, nunca.** `ErrorPermiso` dice que capacidad y por que: no concedida, pendiente
   de una decision de Billy, condicionada a algo que no se puede comprobar, o cruce de tenant.

**Las celdas `(?)` de `ADR-006` estan en `pendiente` y se deniegan**, y el error nombra la decision que las
cerraria. Conceder por defecto lo que nadie ha decidido es como se abren los agujeros de permisos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.capacidades import (
    Ambito,
    Capacidad,
    Condicion,
    ErrorCapacidades,
    Matriz,
    Pantalla,
    Perfil,
    Superficie,
    matriz_capacidades,
)


class ErrorApi(Exception):
    """La peticion no se puede atender: mal formada, sin implementacion o con un rol que no se resuelve."""


class ErrorPermiso(Exception):
    """Denegacion. Nunca devuelve datos parciales: o se concede entera, o no se hace nada."""


class ErrorMatriz(ErrorApi):
    """La matriz del nucleo no carga. Error de arranque del proceso, no de una peticion (`ADR-011` §2)."""


# ---------------------------------------------------------------------------
# Quien pide y desde donde
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    """El usuario autenticado. `perfiles` son los que acumula (un delegado pequeño suele tener tres)."""

    usuario_id: str
    perfiles: tuple[str, ...]
    tenant_id: str | None

    def __post_init__(self) -> None:
        if not str(self.usuario_id).strip():
            raise ErrorApi("un principal necesita `usuario_id`")
        if not isinstance(self.perfiles, tuple) or not self.perfiles:
            raise ErrorApi(f"el principal {self.usuario_id!r} necesita al menos un perfil, en una tupla")
        if len(set(self.perfiles)) != len(self.perfiles):
            raise ErrorApi(f"el principal {self.usuario_id!r} repite perfiles: {list(self.perfiles)}")


@dataclass(frozen=True)
class Contexto:
    """De donde viene la accion. La superficie o la pantalla desempatan los roles compartidos."""

    superficie: str
    tenant_id: str | None
    actuacion_id: str | None = None

    def __post_init__(self) -> None:
        if not str(self.superficie).strip():
            raise ErrorApi("el contexto necesita `superficie` (una superficie o una pantalla declarada)")


# ---------------------------------------------------------------------------
# La matriz: la del nucleo, traducida a errores de esta API
# ---------------------------------------------------------------------------


def matriz(ruta: Path | str | None = None) -> Matriz:
    """La matriz de `engine/capacidades.yaml`, cargada una vez. Si no carga, no arranca la API."""
    try:
        return matriz_capacidades(Path(ruta) if ruta is not None else None)
    except ErrorCapacidades as exc:
        raise ErrorMatriz(str(exc)) from exc


def capacidad_de(matriz_actual: Matriz, identificador: str) -> Capacidad:
    """La capacidad declarada en la matriz, o `ErrorApi` si nadie la declara."""
    try:
        return matriz_actual.capacidad(identificador)
    except ErrorCapacidades as exc:
        raise ErrorApi(str(exc)) from exc


def _perfil(matriz_actual: Matriz, identificador: str) -> Perfil:
    try:
        return matriz_actual.perfil(identificador)
    except ErrorCapacidades as exc:  # pragma: no cover - los perfiles se comprueban antes
        raise ErrorApi(str(exc)) from exc


def ambito_de(matriz_actual: Matriz, rol: str) -> Ambito:
    """El ambito de datos del rol ejercido: lo que decide que bloques puede construir una lectura."""
    return matriz_actual.ambitos[_perfil(matriz_actual, rol).ambito]


def nombre_de(matriz_actual: Matriz, rol: str) -> str:
    """El nombre legible del rol ejercido (`T-REV` -> `Revisor tecnico`), **leido de la matriz**.

    La matriz es la unica fuente de quien es quien, la misma que decide los permisos. Componer el nombre
    en el front exigiria una tabla perfil -> nombre en la interfaz, que es una segunda copia de esa fuente
    y envejece sola: justo lo que `ADR-012` §3 regla 1 evita.

    Un rol que la matriz no declara es `ErrorApi`, exactamente igual que un rol que no se resuelve
    (`rol_para`): no se devuelve un nombre por defecto ni se repite el codigo haciendolo pasar por nombre.
    """
    return _perfil(matriz_actual, rol).nombre


def _comprobar_perfiles(matriz_actual: Matriz, principal: Principal) -> tuple[str, ...]:
    desconocidos = [p for p in principal.perfiles if p not in matriz_actual.perfiles]
    if desconocidos:
        raise ErrorApi(
            f"el principal {principal.usuario_id!r} declara perfiles que la matriz no conoce: {desconocidos}"
        )
    return principal.perfiles


# ---------------------------------------------------------------------------
# Autorizacion
# ---------------------------------------------------------------------------


def concede(matriz_actual: Matriz, capacidad: str, principal: Principal) -> bool:
    """`True` si alguno de los perfiles del principal tiene la capacidad concedida en la matriz.

    No mira el tenant ni el contexto: eso es `exigir`. Una celda `pendiente` o `condicionada` devuelve
    `False`, que es exactamente lo que significan "no decidido" y "no comprobable".
    """
    declarada = capacidad_de(matriz_actual, capacidad)
    return any(perfil in declarada.concede for perfil in principal.perfiles)


def _motivo_denegacion(capacidad: Capacidad, principal: Principal) -> str:
    """El porque. Regla 4: un permiso que falla sin explicacion es un permiso que nadie arregla."""
    pendientes = sorted(p for p in principal.perfiles if p in capacidad.pendiente)
    if pendientes:
        return (
            f"{capacidad.id} ({capacidad.nombre}): {pendientes} tienen la celda pendiente de decision. "
            f"Se deniega hasta que se cierre {capacidad.decide}; no se concede provisionalmente"
        )
    for perfil in principal.perfiles:
        condicion: Condicion | None = capacidad.condicion_de(perfil)
        if condicion is not None:
            return (
                f"{capacidad.id} ({capacidad.nombre}): {perfil} solo la tiene con "
                f"{condicion.requiere!r}, que hoy no se puede comprobar. {condicion.nota}"
            )
    return (
        f"{capacidad.id} ({capacidad.nombre}): no concedida a {list(principal.perfiles)}; "
        f"la tienen {sorted(capacidad.concede) or 'ningun perfil todavia'}"
    )


def rol_para(matriz_actual: Matriz, capacidad: str, principal: Principal, contexto: Contexto) -> str:
    """El perfil con el que el principal ejerce la capacidad (el futuro `actor.rol`).

    Un solo perfil que la conceda, ese. Varios, desempata la pantalla del contexto y luego la superficie.
    Si siguen quedando dos, `ErrorApi`: elegir uno al azar es falsear la trazabilidad del log.
    """
    declarada = capacidad_de(matriz_actual, capacidad)
    candidatos = [p for p in _comprobar_perfiles(matriz_actual, principal) if p in declarada.concede]
    if not candidatos:
        raise ErrorPermiso(_motivo_denegacion(declarada, principal))
    if len(candidatos) == 1:
        return candidatos[0]

    pantalla: Pantalla | None = matriz_actual.pantallas.get(contexto.superficie)
    superficie = pantalla.superficie if pantalla is not None else contexto.superficie
    if superficie not in matriz_actual.superficies:
        raise ErrorApi(
            f"{declarada.id}: la peticion llega desde {contexto.superficie!r}, que no es ninguna "
            "superficie ni pantalla declarada en la matriz"
        )
    if pantalla is not None and pantalla.perfil in candidatos:
        return str(pantalla.perfil)
    por_superficie = [p for p in candidatos if _perfil(matriz_actual, p).superficie == superficie]
    if len(por_superficie) == 1:
        return por_superficie[0]
    raise ErrorApi(
        f"{declarada.id}: el usuario {principal.usuario_id!r} la ejerce con mas de un perfil "
        f"({sorted(por_superficie or candidatos)}) y {contexto.superficie!r} no desempata. Hace falta "
        "venir de una pantalla que declare perfil, o cambiar de rol explicitamente"
    )


def _comprobar_tenant(ambito: Ambito, rol: str, principal: Principal, contexto: Contexto) -> None:
    if not ambito.exige_tenant:
        return
    if principal.tenant_id is None:
        raise ErrorPermiso(
            f"{rol} actua sobre el ambito {ambito.id!r} y el principal {principal.usuario_id!r} no tiene "
            "tenant: sin tenant no hay nada que leer ni que escribir"
        )
    if contexto.tenant_id != principal.tenant_id:
        raise ErrorPermiso(
            f"cruce de tenant: el principal {principal.usuario_id!r} pertenece a "
            f"{principal.tenant_id!r} y la peticion llega con {contexto.tenant_id!r}. El tenant lo fija "
            "la autenticacion, no el cliente"
        )


def exigir(matriz_actual: Matriz, capacidad: str, principal: Principal, contexto: Contexto) -> str:
    """Autoriza y devuelve el rol ejercido, o levanta `ErrorPermiso` diciendo exactamente por que no.

    Es la unica puerta: todo comando y toda lectura pasan por aqui antes de tocar `engine/` (`R-UI-01`).
    """
    declarada = capacidad_de(matriz_actual, capacidad)
    _comprobar_perfiles(matriz_actual, principal)
    if not concede(matriz_actual, capacidad, principal):
        raise ErrorPermiso(_motivo_denegacion(declarada, principal))
    rol = rol_para(matriz_actual, capacidad, principal, contexto)
    _comprobar_tenant(ambito_de(matriz_actual, rol), rol, principal, contexto)
    return rol


__all__ = [
    "Ambito",
    "Capacidad",
    "Condicion",
    "Contexto",
    "ErrorApi",
    "ErrorMatriz",
    "ErrorPermiso",
    "Matriz",
    "Pantalla",
    "Perfil",
    "Principal",
    "Superficie",
    "ambito_de",
    "capacidad_de",
    "concede",
    "exigir",
    "matriz",
    "nombre_de",
    "rol_para",
]
