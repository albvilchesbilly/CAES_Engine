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
- Ninguna entidad de perfiles conoce la matriz de permisos: `Perfil.capacidades` es un campo que alguien
  rellena desde `engine/capacidades.yaml`, no una tabla escrita aqui (S3.1b, `ADR-006` opcion C).
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
#:
#: **No confundir con `actor.rol`**: `Parte.rol` dice que pinta una empresa en la actuacion (quien instalo,
#: quien es el propietario inicial); `actor.rol` es el perfil de `ADR-006` con el que una persona de nuestra
#: plataforma ejecuta un acto. Son dos cosas distintas y no se cruzan.
ROLES_PARTE = ("propietario_inicial", "solicitante", "instalador", "verificador")

#: Ambitos de datos de un perfil (`ADR-006`, tabla de perfiles). Aqui solo el enumerado: que bloques ve cada
#: ambito lo dice la matriz (`engine/capacidades.yaml`), que es configuracion y no se copia en el modelo.
AMBITOS_PERFIL = ("tenant", "externo", "global", "sistema")

#: Tipos de capacidad (`ADR-011` §2): un comando escribe eventos, una lectura no escribe nada.
TIPOS_CAPACIDAD = ("comando", "lectura")


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
    # `ADR-006`: el tenant referencia a sus usuarios. Solo los `id`: el `Usuario` entero vive aparte, para
    # que copiar un tenant a un informe no arrastre datos personales que ese informe no necesita.
    usuarios: tuple[str, ...] = ()


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


# ---------------------------------------------------------------------------
# Perfiles y capacidades (S3.1b, `ADR-006` con la decision A8 de Billy)
# ---------------------------------------------------------------------------
#
# Cinco entidades igual de tontas que las de arriba. La regla que las gobierna: **describen quien hay y que
# se le ha asignado; no deciden nada**. Que perfil concede que capacidad es la matriz
# (`engine/capacidades.yaml`), que es configuracion; si esa tabla se copiase aqui habria dos fuentes y una
# de las dos se quedaria vieja. Por eso `Perfil.capacidades` y `Capacidad.eventos` existen como campos pero
# el modelo no los rellena solo: los rellena quien carga la matriz.


@dataclass(frozen=True)
class Usuario:
    """Persona que usa la plataforma. `tenant_id` es `None` solo en los perfiles globales (`ADM-*`).

    No guarda credenciales ni segundo factor: eso es de la capa de autenticacion, no del modelo canonico.
    `activo` es el estado corriente y `baja` la fecha en que se dio de baja (`UsuarioBaja`); el historico
    de altas y bajas esta en el log, no aqui.
    """

    id: str
    nombre: str
    email: str
    tenant_id: str | None = None
    activo: bool = True
    alta: date | None = None
    baja: date | None = None


@dataclass(frozen=True)
class Perfil:
    """Un perfil de `ADR-006` (`T-RES`, `T-REV`, `ADM-MOD`…) como paquete de capacidades (opcion C).

    `id` no se valida contra ningun enumerado del nucleo a proposito: los perfiles son configuracion y la
    lista vive en la matriz. `ambito` si es un enumerado (`AMBITOS_PERFIL`) porque marca el aislamiento.
    """

    id: str
    nombre: str
    ambito: str  # uno de AMBITOS_PERFIL
    capacidades: tuple[str, ...] = ()  # ids `CAP-nn`; los rellena quien carga la matriz
    superficie: str | None = None  # `SYS-API` no tiene ninguna (`ADR-011` §2 regla 4)


@dataclass(frozen=True)
class Capacidad:
    """Una capacidad atomica de `ADR-006` (`CAP-nn`). `eventos` son los del catalogo cerrado que produce.

    Una `lectura` no produce ninguno; un `comando` produce al menos uno (o declara un efecto fuera del log,
    como un commit). Esa regla la comprueba el cargador de la matriz, no esta dataclass.
    """

    id: str
    nombre: str
    tipo: str  # uno de TIPOS_CAPACIDAD
    eventos: tuple[str, ...] = ()
    proceso: str | None = None  # P0-P10 cuando la capacidad pertenece a un proceso del Engine


@dataclass(frozen=True)
class AsignacionPerfil:
    """Que perfil tiene un usuario, desde cuando y quien se lo dio (`ADR-006`, CAP-30).

    `asignado_por` igual a `usuario_id` es una **autoasignacion**: `ADR-006` no la prohibe, pide que se vea.
    Aqui solo se guarda el dato; quien la senala en la auditoria es la vista, y quien la registra en el log
    es `RolAsignado`.
    """

    usuario_id: str
    perfil_id: str
    desde: date
    tenant_id: str | None = None
    hasta: date | None = None
    asignado_por: str | None = None


@dataclass(frozen=True)
class PoliticaTenant:
    """Lo que un tenant configura sobre si mismo (`ADR-006`, CAP-33).

    Los valores por defecto son las **recomendaciones** de `ADR-006`, no decisiones cerradas:

    - `quien_prepara_puede_aprobar`: recomendacion A6, "por defecto permitido y senalado". Es de Billy.
    - `minimo_responsables`: la regla de continuidad pide dos `T-RES` o un procedimiento de recuperacion
      por `ADM-OPS`; se modela el numero, no el procedimiento.
    - `acceso_soporte_permitido`: `T-RES` autoriza cada acceso (CAP-34); esto es el interruptor general.

    Ninguno de estos campos decide nada por si mismo: los lee quien autoriza, que es `api/permisos.py`.
    """

    tenant_id: str
    quien_prepara_puede_aprobar: bool = True  # A6 (recomendacion de `ADR-006`, pendiente de Billy)
    minimo_responsables: int = 2
    acceso_soporte_permitido: bool = True
    vigencia_acceso_soporte_horas: int | None = None
    version: str = "1.0"


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
    "AMBITOS_PERFIL",
    "MODELO_VERSION",
    "ROLES_PARTE",
    "TIPOS_CAPACIDAD",
    "TIPOS_TENANT",
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
]
