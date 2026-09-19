"""Modelo canonico (N7): lo unico que sale del nucleo hacia los adaptadores de salida.

Cuatro piezas, separadas a proposito (`ADR-004` C1):

- `entidades`: dataclasses inmutables y tontas. No validan ni derivan nada. Desde S3.1b incluyen las cinco
  de perfiles y capacidades (`Usuario`, `Perfil`, `Capacidad`, `AsignacionPerfil`, `PoliticaTenant`), que
  describen quien hay y que se le ha asignado; **quien concede que** es la matriz, no el modelo.
- `conversion.desde_motor`: traduce la `Actuacion` del motor a `ActuacionCanonica`. No decide nada.
- `serializacion.a_dict`: JSON compatible sin `default=` (`Decimal` y `date` como cadena).
- `validacion.validar`: contra el JSON Schema versionado del paquete; `ErrorModelo` con la ruta del campo.

Separarlas es lo que permite construir una entidad mal formada a proposito en un test y comprobar que el
validador la señala. `MODELO_VERSION` es el sufijo de los esquemas y viaja en cada actuacion convertida.

Lo que S3.1 **no** hace: no toca el veredicto ni el calculo, no construye payload, no implementa `R-GRP` ni
`R-EXP` (son S4 y diseño pendiente de Billy) y no inventa ningun campo de la API oficial. `GrupoActuaciones`
y `Expediente` estan aqui como estructura, sin reglas de composicion.

    from engine.modelo import a_dict, desde_motor, validar

    canonica = desde_motor(actuacion)     # actuacion = engine.motor.procesar_actuacion(...)
    validar(canonica)                     # ErrorModelo con la ruta del campo que falla
    json.dumps(a_dict(canonica))          # sin default=
"""

from __future__ import annotations

from engine.modelo.conversion import (
    ESTADO_CICLO_TRAS_EVALUAR,
    VARIABLE_FECHA_FIN,
    VARIABLES_POR_ROL,
    desde_motor,
)
from engine.modelo.entidades import (
    AMBITOS_PERFIL,
    MODELO_VERSION,
    ROLES_PARTE,
    TIPOS_CAPACIDAD,
    TIPOS_TENANT,
    ActuacionCanonica,
    AsignacionPerfil,
    Capacidad,
    DocumentoRef,
    ErrorModelo,
    Expediente,
    GrupoActuaciones,
    Parte,
    Perfil,
    PoliticaTenant,
    Tenant,
    Unidad,
    Usuario,
    Verificador,
)
from engine.modelo.serializacion import a_dict, decimal_a_texto
from engine.modelo.validacion import (
    CARPETA_ESQUEMAS,
    ESQUEMA_POR_ENTIDAD,
    ESQUEMAS,
    esquema,
    validar,
    validar_documento,
)

__all__ = [
    "AMBITOS_PERFIL",
    "CARPETA_ESQUEMAS",
    "ESQUEMAS",
    "ESQUEMA_POR_ENTIDAD",
    "ESTADO_CICLO_TRAS_EVALUAR",
    "MODELO_VERSION",
    "ROLES_PARTE",
    "TIPOS_CAPACIDAD",
    "TIPOS_TENANT",
    "VARIABLES_POR_ROL",
    "VARIABLE_FECHA_FIN",
    "ActuacionCanonica",
    "AsignacionPerfil",
    "Capacidad",
    "DocumentoRef",
    "ErrorModelo",
    "Expediente",
    "GrupoActuaciones",
    "Parte",
    "Perfil",
    "PoliticaTenant",
    "Tenant",
    "Unidad",
    "Usuario",
    "Verificador",
    "a_dict",
    "decimal_a_texto",
    "desde_motor",
    "esquema",
    "validar",
    "validar_documento",
]
