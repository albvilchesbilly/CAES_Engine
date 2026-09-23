"""Lecturas que miran mas de una actuacion: cola de revision, actividad del tenant, auditoria y avisos.

Las tres traen logs, no contenido documental. Que se ve de esos logs lo decide el ambito del rol:

- El ambito de tenant admite `actividad_usuarios`: quien hizo que y cuando, **sin payload**. `R-UI-10`
  obliga ademas a que el usuario de tenant sepa que su actividad se registra, y la revision juridica de
  esa monitorizacion sigue pendiente antes del primer cliente.
- El ambito global admite `metadatos_auditoria` y `agregados`, y nada mas: ni documentos, ni evidencias, ni
  calculos de ningun tenant. La separacion entre quien ve agregados y quien ve metadatos la hace la matriz,
  porque ninguna de las dos capacidades la tiene el mismo perfil.

La cola de revision (`ADR-014` §2) es la unica de este fichero que trae tambien las actuaciones
procesadas, porque una fila de cola dice su veredicto y sus conflictos ademas de lo que sabe el log.

Los dashboards (`ADR-007`) **no estan aqui**: no existen, y sus capacidades lo dicen en `falta`.
"""

from __future__ import annotations

from api.contrato import Peticion
from api.permisos import Capacidad, ErrorApi
from api.proyeccion import Caso, Vista
from api.servicios import Servicios

#: El evento que `ADR-006` CAP-58 quiere vigilar: el motor no cuadra con el calculo de la plataforma.
TIPO_DISCREPANCIA = "DiscrepanciaCalculoPlataforma"


def _logs(servicios: Servicios, identificadores: tuple[str, ...]) -> tuple[object, ...]:
    logs = []
    for identificador in identificadores:
        log = servicios.repositorio.log(identificador)
        if log is not None:
            logs.append(log)
    return tuple(logs)


def actividad_del_tenant(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """La actividad de todos los usuarios del tenant del principal. Nunca la de otro tenant."""
    del capacidad, rol
    tenant = peticion.principal.tenant_id
    if tenant is None:  # pragma: no cover - el ambito de tenant ya lo exige en `exigir`
        raise ErrorApi(f"{peticion.capacidad}: hace falta un principal con tenant")
    return _vista_de_tenant(servicios, tenant)


def _vista_de_tenant(servicios: Servicios, tenant: str) -> Vista:
    return Vista(logs=_logs(servicios, servicios.repositorio.actuaciones_de(tenant)))


def cola_de_revision(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """La cola de revision del tenant: **varias** actuaciones, no una (`ADR-014` §2, C22).

    Enumerar la cartera del tenant es un alcance propio, y por eso cuelga de una capacidad propia y no de
    un modo lista de la consulta de una actuacion: quien tuviera aquella concedida para un caso pasaria a
    poder listar todo el tenant sin que la matriz lo dijera.

    Este manejador **trae material y no elige nada**: quien decide que actuaciones tienen algo que esperar,
    y en que orden se sirven, es la proyeccion, en un solo sitio y verificable.
    """
    del capacidad, rol
    tenant = peticion.principal.tenant_id
    if tenant is None:  # pragma: no cover - el ambito de tenant ya lo exige en `exigir`
        raise ErrorApi(f"{peticion.capacidad}: hace falta un principal con tenant")
    return Vista(casos=_casos_de(servicios, servicios.repositorio.actuaciones_de(tenant)))


def _casos_de(servicios: Servicios, identificadores: tuple[str, ...]) -> tuple[Caso, ...]:
    return tuple(
        Caso(
            actuacion_id=identificador,
            actuacion=servicios.repositorio.actuacion(identificador),
            log=servicios.repositorio.log(identificador),
        )
        for identificador in identificadores
    )


def auditoria_global(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """La auditoria de toda la plataforma, en metadatos. El contenido de un tenant no entra aqui."""
    del peticion, capacidad, rol
    return Vista(logs=_logs(servicios, servicios.repositorio.todas()))


def avisos_de_discrepancia(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """Los avisos de discrepancia entre nuestro calculo y el de la plataforma, agregados.

    `ADR-006` anota CAP-58 como "Notificacion". Mientras no haya canal de notificacion, la capacidad es la
    consulta de esos mismos avisos: el hecho ya esta en el log y no hace falta inventarse nada.
    """
    del peticion, capacidad, rol
    return Vista(
        logs=_logs(servicios, servicios.repositorio.todas()),
        tipos=(TIPO_DISCREPANCIA,),
    )


#: Nombre declarado en `engine/capacidades.yaml` → funcion que lo atiende.
MANEJADORES = {
    "actividad_del_tenant": actividad_del_tenant,
    "cola_de_revision": cola_de_revision,
    "auditoria_global": auditoria_global,
    "avisos_de_discrepancia": avisos_de_discrepancia,
}

__all__ = ["MANEJADORES", "TIPO_DISCREPANCIA"]
