"""De lo que produce el motor a `ActuacionCanonica` (N7): el unico modelo que sale del nucleo.

`desde_motor` es una **traduccion, no una decision**. No calcula, no evalua, no elige valores y no llama al
reloj: toma la `Actuacion` que devolvio `engine.motor.procesar_actuacion` y la reordena en la forma que fija
`ADR-004` C1 / `docs/03` §5.2. Todo lo que ya sabe serializarse se reutiliza tal cual
(`DatoConsolidado.a_dict`, `Evaluacion.a_dict`, `engine.calculo.a_dict`): aqui no se duplica serializacion.

Lo que **no** se rellena, y por que (regla de oro 10: lo que no esta documentado no se inventa):

- `cabecera` sale `{}`. La spec transversal `cabecera_v1.yaml` es S3.2 y depende de la aprobacion de Billy
  (`ADR-004` §6.1). El campo existe en el modelo; su contenido no se adivina.
- `atributos_agrupacion.ccaa` sale `None`. TODO(API-07): ver docs/HUECOS.md.
- `ciclo.estado_plataforma`, `grupo_id` y `expediente_id` salen `None`: no hay envio, ni grupo, ni expediente.
- `subsanaciones` sale vacia: no hay ninguna hasta que la abre un requerimiento (S3.5).
- `partes` solo lleva las que tienen datos. El `instalador` sale del emisor de la factura **si la extraccion
  lo aporta**; hoy no lo aporta, asi que hoy no hay parte instalador. El `verificador` solo si se pasa uno.

`estado_ciclo` es `EVALUADA` y nada mas: es lo unico afirmable despues de procesar. Quien mueve el estado es
la maquina de estados (`engine/estados.py`, pieza posterior de S3.1) proyectando el log; este modulo no la
importa ni la anticipa.

Nada de `eval`, `exec`, `compile` ni `float`. No importa de `agentes/`, `salida/`, `generator/` ni `tests/`,
ni de `engine.motor` en tiempo de ejecucion (el motor pasara a construir el modelo canonico: la dependencia
va en ese sentido y no al reves).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING

from engine.calculo import a_dict as calculo_a_dict
from engine.evidencias import CLAVE_SECUNDARIA
from engine.modelo.entidades import (
    MODELO_VERSION,
    ROLES_PARTE,
    ActuacionCanonica,
    DocumentoRef,
    ErrorModelo,
    Parte,
    Tenant,
    Unidad,
    Verificador,
)

if TYPE_CHECKING:  # pragma: no cover - solo para el tipado; en ejecucion se usa duck typing
    from engine.motor import Actuacion

#: Estado de ciclo de una actuacion recien procesada. Es lo unico afirmable tras `procesar_actuacion`:
#: el nucleo la ha evaluado y nadie la ha revisado ni enviado todavia (`ADR-004` C3). Las transiciones son
#: de `engine/estados.py`; este modulo no las conoce.
ESTADO_CICLO_TRAS_EVALUAR = "EVALUADA"

#: Nombre de la variable consolidada de la que sale `anio_finalizacion`.
VARIABLE_FECHA_FIN = "fecha_fin_actuacion"

#: Rol de parte → (variable del NIF, variable de la razon social). Son nombres de la **cabecera comun**
#: (`docs/03` §5.2), no de ninguna ficha: el vocabulario transversal que S3.2 llevara a `cabecera_v1.yaml`
#: (`ADR-004` §6.1). Mientras tanto viven aqui, en un solo sitio y declarados, no repartidos por el codigo.
#: Del `instalador` no hay extractor hoy: la entrada existe para que el dia que lo haya no se toque este
#: modulo, y hasta entonces la parte sencillamente no se construye.
VARIABLES_POR_ROL: Mapping[str, tuple[str, str]] = {
    "propietario_inicial": ("titular_nif", "titular_razon_social"),
    "solicitante": ("titular_nif", "titular_razon_social"),
    "instalador": ("factura.emisor_nif", "factura.emisor_razon_social"),
}

#: Separador de metodos de lectura cuando un documento se leyo de varias maneras (nativo + OCR).
SEPARADOR_METODOS = "+"


def _texto(valor: object) -> str | None:
    """Texto no vacio, o `None`. No convierte nada que no sea ya texto: no inventa un valor."""
    if isinstance(valor, str):
        recortado = valor.strip()
        return recortado or None
    return None


def _consumido(datos: Mapping[str, object], variable: str) -> object:
    """`valor_consumido` de una variable consolidada, o `None` si no esta (o si hay conflicto)."""
    dato = datos.get(variable)
    return getattr(dato, "valor_consumido", None)


def metodo_lectura(documento: object) -> str:
    """Como se leyo el documento: los metodos de sus paginas, o su formato si no esta paginado (xlsx).

    Es trazabilidad de la capa 1 (`docs/03` §5.2), no una decision. Un documento leido de dos maneras
    (paginas nativas y paginas por OCR, caso G) declara las dos, en orden estable.
    """
    metodos: list[str] = []
    for pagina in getattr(documento, "paginas", ()) or ():
        metodo = _texto(getattr(pagina, "metodo", None))
        if metodo is not None and metodo not in metodos:
            metodos.append(metodo)
    if metodos:
        return SEPARADOR_METODOS.join(sorted(metodos))
    formato = _texto(getattr(documento, "formato", None))
    if formato is None:
        raise ErrorModelo(
            f"el documento {getattr(documento, 'doc_id', '?')} no dice como se leyo (ni paginas ni formato)"
        )
    return formato


def documento_ref(documento: object) -> DocumentoRef:
    """`DocumentoRef` de un documento de ingesta: su huella y como se leyo, nunca su nombre de fichero."""
    return DocumentoRef(
        doc_id=documento.doc_id,
        sha256=documento.sha256,
        bytes=documento.bytes,
        paginas=len(getattr(documento, "paginas", ()) or ()),
        metodo_lectura=metodo_lectura(documento),
        tipo=documento.tipo,
        confianza_tipo=documento.confianza_tipo,
        origen=documento.origen,
    )


def partes_de(variables: Mapping[str, object], verificador: Verificador | None = None) -> tuple[Parte, ...]:
    """Partes con datos, en el orden de `ROLES_PARTE`. Una parte sin NIF ni razon social no se construye."""
    partes: list[Parte] = []
    for rol in ROLES_PARTE:
        if rol == "verificador":
            if verificador is not None:
                partes.append(
                    Parte(
                        rol=rol,
                        nif=_texto(verificador.nif),
                        razon_social=_texto(verificador.razon_social),
                    )
                )
            continue
        nombres = VARIABLES_POR_ROL.get(rol)
        if nombres is None:  # pragma: no cover - ROLES_PARTE y VARIABLES_POR_ROL van juntos
            continue
        nif = _texto(_consumido(variables, nombres[0]))
        razon_social = _texto(_consumido(variables, nombres[1]))
        if nif is None and razon_social is None:
            continue
        partes.append(Parte(rol=rol, nif=nif, razon_social=razon_social))
    return tuple(partes)


def atributos_agrupacion_de(
    actuacion: Actuacion, verificador: Verificador | None = None
) -> dict[str, object]:
    """Lo que permite componer un expediente oficial (`docs/03` §5.2). Nada de esto se deduce ni se rellena.

    `sector` sale de la spec (`ficha.sector`), no del codigo; `anio_finalizacion`, de la fecha de fin
    consolidada si existe; `ccaa` se queda en `None` mientras la plataforma no documente como se determina.
    """
    ficha = actuacion.spec.datos.get("ficha")
    sector = _texto(ficha.get("sector")) if isinstance(ficha, Mapping) else None
    fin = _consumido(actuacion.consolidada.variables, VARIABLE_FECHA_FIN)
    return {
        # TODO(API-07): ver docs/HUECOS.md. No se deriva ni se declara hasta que la plataforma lo documente.
        "ccaa": None,
        "anio_finalizacion": fin.year if isinstance(fin, date) else None,
        "sector": sector,
        "verificador_id": verificador.id if verificador is not None else None,
    }


def unidades_de(actuacion: Actuacion) -> tuple[Unidad, ...]:
    """Unidades ordenadas por clave, con las **tres capas completas** de cada variable de la unidad."""
    unidades: list[Unidad] = []
    for clave in sorted(actuacion.consolidada.unidades):
        datos = actuacion.consolidada.unidades[clave]
        unidades.append(
            Unidad(
                clave=clave,
                num_serie_variador=_texto(_consumido(datos, CLAVE_SECUNDARIA)),
                variables={nombre: datos[nombre].a_dict() for nombre in sorted(datos)},
            )
        )
    return tuple(unidades)


def evaluacion_de(actuacion: Actuacion) -> dict[str, object]:
    """`Evaluacion.a_dict()` con el nombre que usa el modelo canonico (`reglas`) y la fecha de evaluacion.

    No se reserializa nada: se renombra la clave y se añade `evaluado_en`, que la `Evaluacion` no lleva
    porque la fecha es del motor (`INT-10`, `ADR-002` §2.3), no del motor de reglas.
    """
    datos = actuacion.evaluacion.a_dict()
    datos["reglas"] = datos.pop("resultados")
    datos["evaluado_en"] = actuacion.fecha_evaluacion
    return datos


def desde_motor(
    actuacion: Actuacion,
    *,
    tenant: Tenant | None = None,
    verificador: Verificador | None = None,
) -> ActuacionCanonica:
    """`ActuacionCanonica` a partir de la `Actuacion` que devolvio `engine.motor.procesar_actuacion`.

    `verificador` se usa para la parte `verificador` y para `atributos_agrupacion.verificador_id`; sin el,
    los dos quedan vacios (no se inventa un organismo de verificacion).

    `tenant` se acepta porque la firma la fija `ADR-004` C1, pero en el modelo 1.0 **no se guarda en la
    actuacion**: el tenant la contiene (`docs/03` §5.2), no al reves, y `actuacion-1.0.json` no tiene campo
    donde ponerlo. Se comprueba el tipo para que un uso equivocado falle aqui y no dentro de dos sprints.
    """
    if tenant is not None and not isinstance(tenant, Tenant):
        raise ErrorModelo(f"tenant debe ser un Tenant del modelo canonico, no {type(tenant).__name__}")
    if verificador is not None and not isinstance(verificador, Verificador):
        raise ErrorModelo(
            f"verificador debe ser un Verificador del modelo canonico, no {type(verificador).__name__}"
        )
    spec = getattr(actuacion, "spec", None)
    if spec is None or not hasattr(actuacion, "consolidada") or not hasattr(actuacion, "evaluacion"):
        raise ErrorModelo(f"desde_motor espera la Actuacion de engine.motor, no {type(actuacion).__name__}")

    variables = actuacion.consolidada.variables
    calculo = actuacion.calculo
    return ActuacionCanonica(
        id=actuacion.id,
        codigo_identificativo_propio=actuacion.codigo_identificativo_propio,
        modelo_version=MODELO_VERSION,
        # El motor no tiene fecha de creacion y este modulo no llama al reloj: dos conversiones de la misma
        # actuacion tienen que dar el mismo dict (ADR-003 H-08). La unica fecha del proceso es la evaluacion.
        creado_en=actuacion.fecha_evaluacion,
        ficha={
            "codigo": spec.codigo,
            "version_ficha": spec.version_ficha,
            "version_spec": spec.version_spec,
            "hash_spec": spec.hash_spec,
        },
        cabecera={},  # S3.2: spec transversal `cabecera_v1.yaml`, pendiente de Billy (ADR-004 §6.1)
        partes=partes_de(variables, verificador),
        atributos_agrupacion=atributos_agrupacion_de(actuacion, verificador),
        documentos=tuple(documento_ref(d) for d in actuacion.documentos),
        unidades=unidades_de(actuacion),
        variables_actuacion={nombre: variables[nombre].a_dict() for nombre in sorted(variables)},
        evaluacion=evaluacion_de(actuacion),
        calculo=calculo_a_dict(calculo) if calculo is not None else None,
        observaciones=tuple(actuacion.avisos),
        interpretaciones_aplicadas=tuple(actuacion.evaluacion.interpretaciones_aplicadas),
        subsanaciones=(),  # las abre un requerimiento (S3.5); recien procesada no hay ninguna
        ciclo={
            "estado_ciclo": ESTADO_CICLO_TRAS_EVALUAR,
            "estado_plataforma": None,  # solo se refleja lo que dice la plataforma; aun no se ha enviado
            "grupo_id": None,
            "expediente_id": None,
        },
    )


__all__ = [
    "ESTADO_CICLO_TRAS_EVALUAR",
    "SEPARADOR_METODOS",
    "VARIABLES_POR_ROL",
    "VARIABLE_FECHA_FIN",
    "atributos_agrupacion_de",
    "desde_motor",
    "documento_ref",
    "evaluacion_de",
    "metodo_lectura",
    "partes_de",
    "unidades_de",
]
