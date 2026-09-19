"""Lecturas sobre una actuacion. Cada una **trae material**; quien decide que se serializa es la proyeccion.

El reparto es deliberado: el manejador va a `engine/` a por lo que hay (la actuacion procesada, su log) y
no elige campos; `api/proyeccion.py` construye solo los bloques que el ambito del rol admite. Asi `R-UI-12`
se cumple en un unico sitio y no depende de que cada lectura se acuerde de filtrar.

Ninguna de estas funciones calcula ni evalua nada: el veredicto, el ahorro y las carencias ya estan
decididos por el motor cuando llegan aqui.
"""

from __future__ import annotations

from api.contrato import Peticion
from api.permisos import Capacidad, ErrorApi
from api.proyeccion import Vista
from api.servicios import Servicios


def _actuacion(peticion: Peticion, servicios: Servicios) -> object:
    actuacion = servicios.repositorio.actuacion(peticion.actuacion_id)
    if actuacion is None:
        raise ErrorApi(
            f"{peticion.capacidad}: la actuacion {peticion.actuacion_id!r} no esta procesada todavia; "
            "no hay nada que leer"
        )
    return actuacion


def _log(peticion: Peticion, servicios: Servicios) -> object:
    log = servicios.repositorio.log(peticion.actuacion_id)
    if log is None:
        raise ErrorApi(f"{peticion.capacidad}: la actuacion {peticion.actuacion_id!r} no tiene log")
    return log


def actuacion_completa(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """Documentos, evidencias, conflictos, calculo, veredicto e historial de una actuacion."""
    del capacidad, rol  # el ambito del rol lo aplica la proyeccion, no el manejador
    return Vista(actuacion=_actuacion(peticion, servicios), log=_log(peticion, servicios))


def que_te_falta(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """El "que te falta" (F-10) y el estado en lenguaje no tecnico, para su destinatario (F-17)."""
    del capacidad, rol
    return Vista(actuacion=_actuacion(peticion, servicios))


def estados_y_tareas(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """Lo que el log sabe del ciclo y del estado de plataforma (P9). Se refleja, no se decide."""
    del capacidad, rol
    return Vista(actuacion=_actuacion(peticion, servicios), log=_log(peticion, servicios))


def estado_simplificado(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Vista:
    """Lo minimo para quien esta fuera: en que va lo suyo. Sin veredicto tecnico ni cabecera economica."""
    del capacidad, rol
    return Vista(actuacion=_actuacion(peticion, servicios))


#: Nombre declarado en `engine/capacidades.yaml` → funcion que lo atiende.
MANEJADORES = {
    "actuacion_completa": actuacion_completa,
    "que_te_falta": que_te_falta,
    "estados_y_tareas": estados_y_tareas,
    "estado_simplificado": estado_simplificado,
}

__all__ = ["MANEJADORES"]
