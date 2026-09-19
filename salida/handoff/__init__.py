"""Handoff (S5): la carpeta ordenada con la que el tenant presenta hoy (`docs/03` §10.2, `ADR-009` §4).

Es el primer adaptador del puerto de salida y el unico que entrega algo de verdad mientras no haya
diccionario de API (`TODO(API-01)`: ver docs/HUECOS.md). El handoff **no imita ningun formato oficial**:
es nuestro, y por eso es el sitio de `salida/` donde no hay riesgo de inventar un campo de la plataforma.

    from salida.handoff import AdaptadorHandoff
    from salida.mapeo import cargar

    mapeo = cargar("IND240", "handoff")
    adaptador = AdaptadorHandoff()
    paquete = adaptador.construir(actuacion, mapeo, log=log)
    acuse = adaptador.entregar(paquete, destino_carpeta=carpeta, mapeo=mapeo, log=log)

Aqui no se firma nada: la firma es un acto humano del tenant con su certificado de representante y nosotros
solo registramos que ocurrio (`CLAUDE.md` §2, `docs/02` §6.2).
"""

from __future__ import annotations

from salida.handoff.adaptador import (
    ACTOR,
    AVISO_FIRMA,
    CLAVES_ARBOL,
    DESTINO,
    EVENTO_ENTREGA,
    EVENTO_MANIFIESTO,
    EVENTO_PAYLOAD,
    NOMBRE,
    AdaptadorHandoff,
)

__all__ = [
    "ACTOR",
    "AVISO_FIRMA",
    "CLAVES_ARBOL",
    "DESTINO",
    "EVENTO_ENTREGA",
    "EVENTO_MANIFIESTO",
    "EVENTO_PAYLOAD",
    "NOMBRE",
    "AdaptadorHandoff",
]
