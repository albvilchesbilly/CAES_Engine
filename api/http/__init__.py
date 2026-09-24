"""`FR-HTTP` (`ADR-015`): la capa que publica `api/` por red, y de donde sale el principal.

Dos modulos y ninguna sorpresa:

- `servidor.py` — contrato C27: traduce el sobre de `front/compartido/api/transporte.ts` a
  `api.contrato.Peticion` y de vuelta. No decide permisos, no proyecta, no valida el contrato dos veces
  y no importa nada de `engine/`.
- `autenticacion.py` — contratos C28, C29 y el puerto del que sale el `Principal`, que es de lo que
  depende todo el aislamiento por tenant.

Quien compone las piezas concretas (repositorio, casos, autenticador) es un arranque, y vive **fuera** de
aqui: `servidor_desarrollo.py`, en la raiz, al lado de `evaluar_casos.py`. Asi este paquete se queda sin
saber de donde salen los datos, que es justo lo que le permite no conocer `engine/`.

`starlette` y `uvicorn` son un **extra** de `pyproject.toml` (`pip install -e ".[http]"`): el motor, el
CLI y el banco de pruebas siguen corriendo sin ellos. Importar `api.http` sin el extra falla al importar,
y por eso nada del nucleo lo importa.
"""

from __future__ import annotations

from api.http.autenticacion import (
    CABECERA_PRINCIPAL,
    CONFIRMACION_DESARROLLO,
    Autenticador,
    AutenticadorAusente,
    AutenticadorDeDesarrollo,
    ErrorArranque,
    ErrorAutenticacion,
)
from api.http.servidor import TAMANO_MAXIMO_CUERPO, crear_app

__all__ = [
    "CABECERA_PRINCIPAL",
    "CONFIRMACION_DESARROLLO",
    "TAMANO_MAXIMO_CUERPO",
    "Autenticador",
    "AutenticadorAusente",
    "AutenticadorDeDesarrollo",
    "ErrorArranque",
    "ErrorAutenticacion",
    "crear_app",
]
