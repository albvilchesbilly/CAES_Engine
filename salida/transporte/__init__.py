"""Transporte (S5, contrato C8 de `ADR-009` §5 bis): **una frontera declarada, no funcionalidad**.

Aqui vivira lo unico que habla con la plataforma real: firmar peticiones de API con el certificado de
**usuario** (perfil `Modificacion` o `Firma`) y enviarlas. Hoy no hay nada que enviar y no hay a donde:

- **TODO(API-01)**: no hay diccionario de endpoints, autenticacion, peticiones ni respuestas.
- **TODO(API-09)**: no se sabe si el perfil `Modificacion` admite personas ajenas a la plantilla del agente
  ni si su certificado puede usarse desde infraestructura de un tercero. De eso depende **donde vive** este
  componente (`UBICACIONES`), y es una decision de Billy tras la respuesta del gestor de la plataforma.

Ver `docs/HUECOS.md` §1 para las dos filas.

Por que existe el paquete estando vacio: porque la frontera es la decision. El constructor y el manifiesto
no cambian viva donde viva el transporte (`docs/03` §10.3), y tener el modulo declarado con una unica
implementacion que **se niega citando los huecos** es lo que impide que alguien improvise un cliente HTTP
con campos inventados el dia que haga falta una demo.

**Tres certificados, y este modulo solo toca uno** (`docs/02` §2.3 y §6.2):

| Certificado | Para que | Nuestro papel |
|---|---|---|
| De **usuario** (Consulta / Modificacion / Firma) | Firmar peticiones de API | El unico que tocaria |
| De **representante** (FNMT) | Actos administrativos | **Ninguno**: ni se usa ni se custodia |
| De empleado publico | Actos del GA y de la CN | Ninguno |

**No existe `salida/firma/` como codigo y no lo habra** (`docs/01` §3.8, `docs/03` §10.3, `CLAUDE.md` §2).
La firma de un acto administrativo es un acto humano con certificado de representante, en casa del tenant;
de ella solo registramos el evento `FirmaRegistrada` de actor humano. Ningun componente nuestro firma actos
administrativos ni custodia certificados de representante. Un test lo comprueba **sobre el arbol de
ficheros**, no sobre este comentario.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from salida.puerto import Acuse, ErrorSalida


class ErrorTransporte(ErrorSalida):
    """No se puede firmar ni enviar una peticion: hoy, siempre, porque no hay a donde ni con que."""


#: Donde puede vivir este componente. Cual de las dos es **decision de Billy** tras la respuesta del gestor
#: de la plataforma; el backend queda preparado para ambas y el constructor no cambia en ningun caso.
#: TODO(API-09): ver docs/HUECOS.md
UBICACIONES = ("nuestra_infraestructura", "casa_del_tenant")

#: El unico certificado que este modulo usaria: el de **usuario**, el que firma peticiones de API. El de
#: representante (FNMT) firma actos administrativos, es humano y nunca pasa por aqui (`docs/02` §6.2).
CERTIFICADO_USUARIO = "usuario"


@dataclass(frozen=True)
class PeticionFirmada:
    """Una peticion lista para salir, firmada con un certificado de **usuario**.

    Se declara lo unico que hoy se puede afirmar sin inventar: de quien es el certificado, que se firmo y
    desde donde. La forma real (endpoint, metodo, cabeceras, algoritmo y codificacion de la firma, formato
    de la respuesta) es TODO(API-01): ver docs/HUECOS.md. Ningun campo de aqui pretende ser un campo de la
    API oficial; el conector de S3.7 traducira, no heredara (`ADR-009` §2).
    """

    usuario_id: str
    peticion: Mapping[str, object] = field(default_factory=dict)
    tipo_certificado: str = CERTIFICADO_USUARIO
    ubicacion: str | None = None

    def __post_init__(self) -> None:
        if self.tipo_certificado != CERTIFICADO_USUARIO:
            raise ErrorTransporte(
                f"el transporte firma peticiones con certificado de {CERTIFICADO_USUARIO!r} y solo con ese "
                f"(`docs/02` §6.2); llego {self.tipo_certificado!r}. Nunca con el de representante: ese "
                "firma actos administrativos, es humano y no lo custodiamos"
            )
        if not isinstance(self.usuario_id, str) or not self.usuario_id.strip():
            raise ErrorTransporte("una peticion firmada necesita el `usuario_id` del certificado de usuario")
        if self.ubicacion is not None and self.ubicacion not in UBICACIONES:
            raise ErrorTransporte(
                f"ubicacion desconocida: {self.ubicacion!r}; las declaradas son {list(UBICACIONES)} "
                "(TODO(API-09): decide Billy)"
            )

    def a_dict(self) -> dict[str, object]:
        return {
            "usuario_id": self.usuario_id,
            "peticion": dict(self.peticion),
            "tipo_certificado": self.tipo_certificado,
            "ubicacion": self.ubicacion,
        }


@runtime_checkable
class Transporte(Protocol):
    """Lo que hara el transporte cuando exista diccionario: firmar con certificado de usuario y enviar."""

    nombre: str

    def firmar_peticion(self, peticion: Mapping[str, object], credencial: object) -> PeticionFirmada:
        """Firma la peticion con el certificado de **usuario** de esa credencial. Nunca con otro."""
        ...

    def enviar(self, peticion_firmada: PeticionFirmada) -> Acuse:
        """Envia la peticion firmada a la plataforma y devuelve su acuse."""
        ...


class TransporteNoDisponible:
    """La unica implementacion de hoy: se niega, y dice exactamente por que y donde esta escrito.

    No es un `NotImplementedError` ni un cliente a medio hacer: es la forma de que el hueco se note en
    tiempo de ejecucion con su identificador, para que nadie lo tape con una suposicion.
    """

    nombre = "transporte_no_disponible"

    #: Los huecos que hay que cerrar, con documentacion oficial, antes de que esto pueda hacer algo.
    HUECOS = ("API-01", "API-09")

    def __init__(self, *, ubicacion: str | None = None) -> None:
        """`ubicacion` es informativa y opcional: mientras API-09 siga abierto, no hay respuesta correcta."""
        if ubicacion is not None and ubicacion not in UBICACIONES:
            raise ErrorTransporte(
                f"ubicacion desconocida: {ubicacion!r}; las declaradas son {list(UBICACIONES)} "
                "(TODO(API-09): decide Billy)"
            )
        self.ubicacion = ubicacion

    def _negarse(self, que: str) -> ErrorTransporte:
        return ErrorTransporte(
            f"{que}: no hay transporte. Faltan {' y '.join(self.HUECOS)} (ver docs/HUECOS.md): sin "
            "diccionario de API no hay endpoint ni formato de peticion, y sin la respuesta del gestor no "
            "esta decidido donde vive este componente. No se inventa ninguno de los dos"
        )

    def firmar_peticion(self, peticion: Mapping[str, object], credencial: object) -> PeticionFirmada:
        """Se niega. El certificado que firmaria seria de usuario; el de representante no pasa por aqui."""
        raise self._negarse("no se puede firmar la peticion")

    def enviar(self, peticion_firmada: PeticionFirmada) -> Acuse:
        """Se niega. La via que funciona hoy es el handoff: la carpeta que el tenant presenta el mismo."""
        raise self._negarse("no se puede enviar la peticion")


__all__ = [
    "CERTIFICADO_USUARIO",
    "UBICACIONES",
    "ErrorTransporte",
    "PeticionFirmada",
    "Transporte",
    "TransporteNoDisponible",
]
