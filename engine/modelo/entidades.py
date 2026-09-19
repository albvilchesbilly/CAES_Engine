"""Entidades del modelo canonico (N7): el contrato C1 de `ADR-004`, tal cual (`docs/03` §5.2).

Son dataclasses **inmutables y tontas**: no validan, no derivan nada y no llaman al reloj. Quien decide si
una instancia es valida es `engine.modelo.validacion.validar` contra el JSON Schema versionado; quien la
construye a partir de lo que produjo el motor es `engine.modelo.conversion.desde_motor`. Separar las tres
cosas es lo que permite escribir un test que construye una entidad mal formada a proposito.

Lo que **no** llevan estas entidades, y por que:

- `ActuacionCanonica.cabecera` es un `dict` vacio en S3.1: la spec transversal `cabecera_v1.yaml` es S3.2 y
  depende de la aprobacion de Billy (`ADR-004` §6.1). El campo existe; no se rellena ni se inventa.
- `atributos_agrupacion.ccaa`, `Tenant.capacidad_delegacion_disponible` y `Verificador.ccaa_operativas` son
  opcionales y sin semantica propia: la plataforma no ha documentado como se obtienen (`docs/HUECOS.md`).
- Ninguna entidad conoce ninguna ficha: lo especifico vive en el YAML de la spec (regla de oro 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

#: Version del modelo canonico. Es el sufijo de los esquemas (`actuacion-1.0.json`) y viaja en cada
#: `ActuacionCanonica.modelo_version`: un consumidor sabe contra que esquema validar sin preguntar.
MODELO_VERSION = "1.0"

#: Tipos de tenant (`docs/03` §5.2 y §12): sujeto delegado o sujeto obligado que opera directamente.
TIPOS_TENANT = ("delegado", "obligado_directo")

#: Roles de parte (`docs/03` §5.2). El verificador solo aparece cuando se conoce; no se inventa.
ROLES_PARTE = ("propietario_inicial", "solicitante", "instalador", "verificador")


class ErrorModelo(Exception):
    """El objeto no cumple el modelo canonico: no se puede serializar o no valida contra su esquema."""


@dataclass(frozen=True)
class Tenant:
    """Sujeto delegado u obligado directo (`docs/03` §5.2, §12). Es el titular del aislamiento por tenant."""

    id: str
    tipo: str  # uno de TIPOS_TENANT
    razon_social: str
    nif: str
    # NO DOCUMENTADO como se consulta en la plataforma. Atributo informativo, sin semantica propia.
    # TODO(API-11): ver docs/HUECOS.md
    capacidad_delegacion_disponible: Decimal | None = None


@dataclass(frozen=True)
class Verificador:
    """Organismo de verificacion. `ccaa_operativas` es NO DOCUMENTADO: no se sabe si la plataforma lo expone.

    No tiene hueco `API-xx` propio en `docs/HUECOS.md`; se modela opcional y vacio hasta que lo tenga
    (no se abre un hueco desde el codigo, ver `docs/HUECOS.md` §3).
    """

    id: str
    razon_social: str
    nif: str
    acreditacion_enac_ref: str | None = None
    ccaa_operativas: tuple[str, ...] | None = None  # NO DOCUMENTADO


@dataclass(frozen=True)
class Parte:
    """Interviniente de la actuacion. `rol` es uno de ROLES_PARTE; una parte sin datos no se construye."""

    rol: str
    nif: str | None = None
    razon_social: str | None = None


@dataclass(frozen=True)
class DocumentoRef:
    """Referencia a un documento por su huella (`docs/03` §5.2). Nunca por nombre de fichero.

    `doc_id` es el sha256 del fichero o el de la parte separada de un PDF combinado; `origen` es el sha256
    del combinado del que salio, o `None`. `metodo_lectura` dice como se leyo (nativo, OCR, xlsx...): es
    trazabilidad de la capa 1, no una decision.
    """

    doc_id: str
    sha256: str
    bytes: int
    paginas: int
    metodo_lectura: str
    tipo: str | None = None
    confianza_tipo: Decimal | None = None
    origen: str | None = None


@dataclass(frozen=True)
class Unidad:
    """Una unidad de la actuacion (en la ficha de variadores, un motor). `clave` es su numero de serie.

    `variables` son los `DatoConsolidado.a_dict()` de la unidad: las tres capas completas por dato
    (evidencias con cita → interpretacion → valor consumido, `docs/03` §5.3).
    """

    clave: str
    num_serie_variador: str | None = None
    variables: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class ActuacionCanonica:
    """La actuacion como la consumen los adaptadores de salida: el unico modelo que sale del nucleo.

    Los bloques `ficha`, `atributos_agrupacion`, `evaluacion`, `calculo` y `ciclo` son diccionarios ya
    serializables, reutilizando los `a_dict()` que exponen los modulos del nucleo (no se duplica ninguna
    serializacion). Su forma la fija el esquema `actuacion-1.0.json`.
    """

    id: str
    codigo_identificativo_propio: str
    modelo_version: str
    creado_en: date
    ficha: dict[str, object]
    cabecera: dict[str, object]  # vacio en S3.1: es S3.2 (spec transversal, aprobacion de Billy)
    partes: tuple[Parte, ...]
    atributos_agrupacion: dict[str, object]
    documentos: tuple[DocumentoRef, ...]
    unidades: tuple[Unidad, ...]
    variables_actuacion: dict[str, dict]
    evaluacion: dict[str, object]
    calculo: dict[str, object] | None
    observaciones: tuple[str, ...]
    interpretaciones_aplicadas: tuple[str, ...]
    subsanaciones: tuple[dict, ...]
    ciclo: dict[str, object]


@dataclass(frozen=True)
class GrupoActuaciones:
    """Actuaciones que se verifican juntas, con dictamen unico (`docs/03` §5.2).

    S3.1 modela la **estructura**, no la composicion: que actuaciones pueden agruparse es `R-GRP` (S4) y
    es diseño pendiente de Billy (`ADR-001` §3). Aqui no hay ninguna regla.
    """

    id: str
    tenant_id: str
    verificador_id: str | None = None
    actuaciones: tuple[str, ...] = ()
    estado_plataforma: str | None = None  # los 8 de docs/02 §5.1; lo fija la plataforma, se refleja


@dataclass(frozen=True)
class Expediente:
    """Agregacion oficial de actuaciones VERIFICADA_FAVORABLE (misma CCAA + año + sector + verificador).

    Igual que el grupo: estructura sin reglas de composicion (`R-EXP` es S4). `estado_expediente` es un
    nombre provisional NO OFICIAL. TODO(API-03): ver docs/HUECOS.md.
    """

    id: str
    tenant_id: str
    ccaa: str | None = None  # TODO(API-07): ver docs/HUECOS.md
    anio: int | None = None
    sector: str | None = None
    verificador_id: str | None = None
    actuaciones: tuple[str, ...] = ()
    grupo_id: str | None = None
    estado_expediente: str | None = None  # TODO(API-03): ver docs/HUECOS.md
    requerimientos: tuple[dict, ...] = ()


__all__ = [
    "MODELO_VERSION",
    "ROLES_PARTE",
    "TIPOS_TENANT",
    "ActuacionCanonica",
    "DocumentoRef",
    "ErrorModelo",
    "Expediente",
    "GrupoActuaciones",
    "Parte",
    "Tenant",
    "Unidad",
    "Verificador",
]
