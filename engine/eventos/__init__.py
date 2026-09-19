"""Log de eventos de una actuacion (N8): solo-anadir, hash encadenado, estado como proyeccion del log.

Cuatro piezas:

- `catalogo` — que eventos existen y que clases de actor hay. Catalogo cerrado.
- `canonico` — `json_canonico`, la codificacion tipada de los payloads y el hash encadenado.
- `log` — el sobre (`Evento`), el log solo-anadir (`LogEventos`) y sus invariantes.
- `grabacion` / `replay` — `grabar(actuacion)` escribe el log de una ejecucion del motor y
  `reproducir(log, spec)` vuelve a emitir veredicto y ahorro **con el log y solo con el log**.

`engine/eventos/` no importa de `agentes/`, `salida/`, `generator/` ni `tests/`, y `motor.py` no lo importa:
el enganche de la grabacion al motor es de la oleada siguiente (`ADR-004`). Hoy se invoca desde fuera.
"""

from __future__ import annotations

from engine.eventos.canonico import (
    ErrorEvento,
    ahora_utc,
    calcular_hash,
    codificar,
    decodificar,
    json_canonico,
    normalizar_instante,
    texto_instante,
)
from engine.eventos.catalogo import (
    CAMPOS_AGENTE,
    CLASES_ACTOR,
    CONFIRMACIONES_SOLO_HUMANO,
    PROCESO_DE_TIPO,
    TIPOS,
    TIPOS_POR_PROCESO,
    TIPOS_SOLO_HUMANO,
)
from engine.eventos.grabacion import grabar
from engine.eventos.log import Actor, Evento, LogEventos
from engine.eventos.replay import consolidada_de, divergencias, reproducir, verificar_replay

__all__ = [
    "CAMPOS_AGENTE",
    "CLASES_ACTOR",
    "CONFIRMACIONES_SOLO_HUMANO",
    "PROCESO_DE_TIPO",
    "TIPOS",
    "TIPOS_POR_PROCESO",
    "TIPOS_SOLO_HUMANO",
    "Actor",
    "ErrorEvento",
    "Evento",
    "LogEventos",
    "ahora_utc",
    "calcular_hash",
    "codificar",
    "consolidada_de",
    "decodificar",
    "divergencias",
    "grabar",
    "json_canonico",
    "normalizar_instante",
    "reproducir",
    "texto_instante",
    "verificar_replay",
]
