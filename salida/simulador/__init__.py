"""Simulador de la plataforma oficial (S5, contrato C7 de `ADR-009` §5).

Reproduce **solo lo publicado** de la plataforma (OMIE/MIBGAS, presentacion 30/06/2026): los estados de
actuacion de la fase 1, la validacion de esquema, el manifiesto de ficheros con hash, la firma humana y las
tareas pendientes. Lo demas es un hueco, nunca una suposicion (TODO(API-01): ver docs/HUECOS.md).

    from salida.simulador import Credencial, Simulador

    simulador = Simulador(instante=instante)                     # determinista: reloj inyectado
    acuse = simulador.entregar(paquete, credencial=credencial, canonica=canonica)
    simulador.registrar_firma(acuse.referencia, actor_humano, credencial=credencial)

El detalle, las ocho reglas y por que aqui no se escribe ni un literal de plataforma estan en
`salida/simulador/plataforma.py`.
"""

from __future__ import annotations

from salida.simulador.plataforma import (
    NOMBRE,
    PERFIL_CONSULTA,
    PERFIL_FIRMA,
    PERFIL_MODIFICACION,
    PERFILES,
    PERFILES_QUE_CARGAN,
    PREFIJO_REFERENCIA,
    VIA_SIMULADOR,
    Credencial,
    ErrorSimulador,
    Simulador,
    estado_creacion,
    estado_firmado,
    estado_validado,
    filas_de_actuacion,
    referencia_de,
)

__all__ = [
    "NOMBRE",
    "PERFILES",
    "PERFILES_QUE_CARGAN",
    "PERFIL_CONSULTA",
    "PERFIL_FIRMA",
    "PERFIL_MODIFICACION",
    "PREFIJO_REFERENCIA",
    "VIA_SIMULADOR",
    "Credencial",
    "ErrorSimulador",
    "Simulador",
    "estado_creacion",
    "estado_firmado",
    "estado_validado",
    "filas_de_actuacion",
    "referencia_de",
]
