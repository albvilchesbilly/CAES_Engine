"""Actos del sujeto delegado: verificador, firma y desistimiento.

Tres avisos que no son decoracion:

- **`R-UI-03`: aqui nadie firma.** La capacidad se llama registrar la firma y eso es lo que hace: anota
  quien firmo, cuando y con que referencia. La firma de un acto administrativo es humana, con certificado
  de representante, y ningun componente nuestro la ejecuta ni custodia el certificado.
- **`R-UI-02` por ausencia**: no hay comando que fije, fuerce o cambie un veredicto. Si el veredicto tiene
  que cambiar, se corrige el dato y el motor recalcula.
- Quien firma puede no ser quien lo anota (`ADR-006`), asi que `firmante` es un dato de la peticion y no
  se deduce del usuario autenticado.
"""

from __future__ import annotations

from api.comandos.actuaciones import escribir, log_de
from api.contrato import Peticion, Salida
from api.permisos import Capacidad
from api.servicios import Servicios


def _marca(capacidad: Capacidad) -> dict[str, object]:
    return {"capacidad": capacidad.id}


def asignar_verificador(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Elige o valida el verificador de la actuacion (P0)."""
    verificador = str(peticion.exige("verificador"))
    evento = escribir(
        log_de(peticion, servicios),
        "VerificadorAsignado",
        {**_marca(capacidad), "verificador": verificador},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"verificador": verificador}, eventos=(evento,))


def registrar_firma(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Registra que la firma **ya ocurrio**: quien, cuando y con que referencia (`R-UI-03`)."""
    firmante = str(peticion.exige("firmante"))
    referencia = str(peticion.exige("referencia"))
    evento = escribir(
        log_de(peticion, servicios),
        "FirmaRegistrada",
        {
            **_marca(capacidad),
            "firmante": firmante,
            "referencia": referencia,
            "firmado_en": peticion.texto("firmado_en"),
            "anotado_por": peticion.principal.usuario_id,
        },
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"firmante": firmante, "referencia": referencia}, eventos=(evento,))


def registrar_desistimiento(
    peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str
) -> Salida:
    """Anota el desistimiento del sujeto, que cierra la actuacion (`docs/02` §5.5)."""
    motivo = str(peticion.exige("motivo"))
    evento = escribir(
        log_de(peticion, servicios),
        "DesistimientoRegistrado",
        {**_marca(capacidad), "motivo": motivo},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"motivo": motivo}, eventos=(evento,))


#: Nombre declarado en `engine/capacidades.yaml` → funcion que lo atiende.
MANEJADORES = {
    "asignar_verificador": asignar_verificador,
    "registrar_firma": registrar_firma,
    "registrar_desistimiento": registrar_desistimiento,
}

__all__ = ["MANEJADORES"]
