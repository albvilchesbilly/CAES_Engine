"""`api/`: el contrato de comandos y lecturas por capacidad entre el Engine y el front (`FR0`).

Lo que hay aqui, y lo que no:

- **Hay** una entrada por cada capacidad de `ADR-006`, autorizacion en el servidor (`R-UI-01`), inferencia
  del rol ejercido, aislamiento por tenant y proyeccion filtrada por ambito (`R-UI-12`).
- **No hay** ni un calculo, ni una evaluacion de regla, ni una decision de transicion: eso es `engine/`
  (`R-UI-11` aguas arriba). `api/` valida, delega y traduce.
- **No hay** ningun campo de la API oficial de la plataforma. Eso es `salida/`, y no se mezcla: `api/` es
  **nuestra**, interna, para el front. Lo que la plataforma no ha documentado es un hueco de `salida/`.

Dependencias: `api/` lee de `engine/`; `front/` habla con `api/`; nadie importa de `api/` hacia dentro.
Con `api/` apagado el Engine sigue produciendo veredicto, igual que con `salida/` apagado.

Quien puede hacer que vive en `engine/capacidades.yaml`, no en este codigo: el log tambien lo necesita
(A8), y una segunda copia de la matriz seria una segunda verdad.
"""

from __future__ import annotations

from api.comandos import ejecutar
from api.contrato import Peticion, Respuesta
from api.lecturas import leer
from api.lecturas.documentos import Documento, ErrorIntegridad, documento_a_transporte, leer_documento
from api.permisos import (
    Contexto,
    ErrorApi,
    ErrorMatriz,
    ErrorPermiso,
    Principal,
    concede,
    exigir,
    matriz,
    rol_para,
)
from api.repositorio import RepositorioMemoria
from api.servicios import Repositorio, Servicios

__all__ = [
    "Contexto",
    "Documento",
    "ErrorApi",
    "ErrorIntegridad",
    "ErrorMatriz",
    "ErrorPermiso",
    "Peticion",
    "Principal",
    "Repositorio",
    "RepositorioMemoria",
    "Respuesta",
    "Servicios",
    "concede",
    "documento_a_transporte",
    "ejecutar",
    "exigir",
    "leer",
    "leer_documento",
    "matriz",
    "rol_para",
]
