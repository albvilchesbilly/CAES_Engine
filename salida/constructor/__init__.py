"""Constructor (S5): payload y manifiesto de una actuacion, sin firmar (`docs/03` §10.3, `ADR-008`).

Es **nuestro** artefacto, en nuestra infraestructura: describe exactamente que se entrega y permite demostrar,
byte a byte, que nadie lo altero despues. No firma nada y no habla con ninguna plataforma.

S3.3 trae solo el manifiesto interno. El payload de cabecera + detalle espera dos cosas que no son nuestras:
la spec transversal `cabecera_v1.yaml` (S3.2, aprobacion de Billy) y el diccionario de la API
(`TODO(API-01)`: ver docs/HUECOS.md).
"""

from __future__ import annotations

from salida.constructor.manifiesto import (
    MANIFIESTO_VERSION,
    ErrorManifiesto,
    FicheroManifiesto,
    Manifiesto,
    ResultadoVerificacion,
    construir,
    verificar,
)

__all__ = [
    "MANIFIESTO_VERSION",
    "ErrorManifiesto",
    "FicheroManifiesto",
    "Manifiesto",
    "ResultadoVerificacion",
    "construir",
    "verificar",
]
