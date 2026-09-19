"""Salida (S5): lo que convierte una actuacion evaluada en algo entregable (`docs/03` §10, `docs/01` §3.8).

Aqui empieza el unico paquete que mira hacia fuera. Tres reglas lo gobiernan desde el primer modulo:

1. **Nada en `salida/` inventa un campo de la API oficial.** Lo que la plataforma (OMIE/MIBGAS) no ha
   publicado es un hueco enumerado, `TODO(API-xx)` con su fila en `docs/HUECOS.md`, nunca una suposicion.
2. **Dependencias hacia dentro.** `salida/` puede importar de `engine/`; `engine/` nunca importa de
   `salida/`. Con `salida/` entera borrada, el Engine sigue dando veredicto.
3. **La firma es un acto humano.** No existe `salida/firma/`: solo se registra el evento `FirmaRegistrada`
   de actor humano. Ningun componente nuestro firma actos administrativos ni custodia certificados de
   representante (`docs/02` §6.2, `docs/03` §10.3).

Lo que hay hoy (S3.3): `constructor/manifiesto.py`, el manifiesto interno y su verificacion de integridad.
El puerto (`puerto.py`), el handoff, el simulador, el transporte y el conector real son S3.4 y siguientes.
"""

from __future__ import annotations

__all__: list[str] = []
