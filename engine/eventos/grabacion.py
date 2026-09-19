"""Grabacion de una ejecucion del motor como log de eventos (`docs/03` §6.2, `ADR-004` C2 punto 8).

`grabar(actuacion)` toma lo que devuelve `engine.motor.procesar_actuacion` y produce el log de **esa**
ejecucion: los eventos de P1 (ingesta), P2 (evidencias), P4 (cruce), P5 (calculo) y P3 (veredicto) en el
orden en que el motor los produjo.

**No la llama `motor.py`**: el enganche es de la oleada siguiente (`ADR-004`). Aqui se invoca desde fuera,
lo que mantiene el motor tal cual esta y hace que la grabacion se pueda probar sola.

Decisiones de esta pieza (todas ellas para el ADR):

- **El log se basta a si mismo.** Cada `DatoConsolidado` va entero al payload (las tres capas: evidencias con
  cita, interpretacion y valor consumido), porque el replay reconstruye la consolidacion **solo** con el log:
  no vuelve a leer `expedientes/` ni los PDF. El coste es un log grande; la alternativa (guardar solo el
  valor) haria el replay dependiente de los ficheros originales, que es justo lo que no queremos.
- **Un instante para toda la grabacion.** Una ejecucion sincrona del motor es un acto: todos sus eventos
  comparten `ocurrido_en` y se ordenan por `secuencia`. Con `instante` fijo, dos ejecuciones identicas dan
  el mismo log byte a byte (prueba de regresion F-22).
- **La telemetria no entra** (`Actuacion.tiempos` son segundos de reloj, `float`): un log que cambia entre
  dos ejecuciones identicas no sirve de prueba. El `float` esta prohibido en el payload por construccion.
- **`carpeta` se guarda por su nombre**, no por su ruta absoluta: la ruta es del entorno, no de la actuacion.
- **`ObservacionRegistrada` cierra la consolidacion.** El catalogo de `docs/03` §6.2 no tiene un evento de
  "consolidacion terminada" y hay dos cosas que solo existen ahi: los avisos acumulados (ingesta +
  consolidacion, que entran en la evaluacion) y `vinculos_por_huella` (que documento se vinculo a que unidad
  por SHA-256). Se registran como `ObservacionRegistrada` con `origen: "consolidacion"`. Propuesta para el
  ADR: un tipo propio `ConsolidacionCompletada`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from engine.calculo import a_dict as calculo_a_dict
from engine.eventos.canonico import ErrorEvento, ahora_utc
from engine.eventos.log import Actor, LogEventos

#: Actor por defecto de una grabacion: el motor determinista, con su version.
CLASE_MOTOR = "motor"

#: Origen de la observacion que cierra la consolidacion (ver cabecera).
ORIGEN_CONSOLIDACION = "consolidacion"


def _actor_motor(actuacion: Any) -> Actor:
    version = getattr(actuacion, "version_engine", None) or "desconocida"
    return Actor(clase=CLASE_MOTOR, id=f"engine@{version}")


def _campos(objeto: Any) -> dict[str, object]:
    if not is_dataclass(objeto) or isinstance(objeto, type):
        raise ErrorEvento(f"se esperaba una dataclass y llego {type(objeto).__name__}")
    return {campo.name: getattr(objeto, campo.name) for campo in fields(objeto)}


def evidencia_a_payload(evidencia: Any) -> dict[str, object]:
    """Una `Evidencia` como payload: todos sus campos, tal cual (`Decimal` y fechas se codifican solas)."""
    return _campos(evidencia)


def dato_a_payload(dato: Any) -> dict[str, object]:
    """Un `DatoConsolidado` entero, con sus evidencias (las tres capas de `docs/03` §5.3)."""
    campos = _campos(dato)
    for clave in ("evidencias", "posibles_errores_ocr"):
        campos[clave] = [evidencia_a_payload(ev) for ev in campos.get(clave) or ()]
    return campos


def _documento_a_payload(doc: Any) -> dict[str, object]:
    """Un documento registrado. **Siempre con `sha256`**: la huella se calcula en ingesta, antes de
    cualquier transformacion, y la vinculacion es por huella, nunca por nombre de fichero (`CLAUDE.md` §2).
    Un documento sin huella no se registra: se avisa, porque el log dejaria de ser trazable."""
    rango = getattr(doc, "rango_paginas", None)
    if not getattr(doc, "sha256", None):
        raise ErrorEvento(
            f"el documento {getattr(doc, 'doc_id', None)!r} llega sin `sha256`: un DocumentoRegistrado "
            "sin huella no es trazable (`docs/03` §6.2)"
        )
    return {
        "doc_id": doc.doc_id,
        "sha256": doc.sha256,
        "nombre": getattr(doc, "nombre", None),
        "bytes": getattr(doc, "bytes", None),
        "formato": getattr(doc, "formato", None),
        "paginas": len(getattr(doc, "paginas", ()) or ()),
        "origen": getattr(doc, "origen", None),
        "rango_paginas": list(rango) if rango else None,
    }


def _datos_en_orden(consolidada: Any) -> list[tuple[str, str | None, Any]]:
    """Los datos consolidados en el orden en que los construyo `evidencias.consolidar`: unidades y luego
    variables de actuacion. Ese orden es el que hace que `conflictos` se reconstruya igual."""
    orden: list[tuple[str, str | None, Any]] = []
    for serie, datos in consolidada.unidades.items():
        for nombre, dato in datos.items():
            orden.append((nombre, serie, dato))
    for nombre, dato in consolidada.variables.items():
        orden.append((nombre, None, dato))
    return orden


def _evidencias_de(datos: Iterable[tuple[str, str | None, Any]]) -> list[tuple[Any, bool]]:
    vistas: set[int] = set()
    salida: list[tuple[Any, bool]] = []
    for _nombre, _serie, dato in datos:
        for ev in list(dato.evidencias) + list(dato.posibles_errores_ocr):
            if id(ev) in vistas:
                continue
            vistas.add(id(ev))
            salida.append((ev, True))
    return salida


def grabar(actuacion: Any, *, instante: datetime | None = None, log: LogEventos | None = None) -> LogEventos:
    """El log de una ejecucion del motor (ver cabecera). `instante` fija `ocurrido_en` de **todos** sus
    eventos: una ejecucion sincrona del motor es un acto, no una sucesion de instantes. Por defecto se
    mira el reloj **una sola vez**, al empezar; pasandolo explicito, dos grabaciones de la misma
    ejecucion dan el mismo log byte a byte (prueba de regresion F-22).

    `actuacion` es lo que devuelve `engine.motor.procesar_actuacion`; se consume por atributos (este paquete
    no importa `motor`, que arrastraria la ingesta entera).
    """
    for atributo in ("id", "consolidada", "evaluacion", "documentos", "fecha_evaluacion"):
        if not hasattr(actuacion, atributo):
            raise ErrorEvento(f"no parece una Actuacion del motor: le falta {atributo!r}")

    consolidada = actuacion.consolidada
    evaluacion = actuacion.evaluacion
    actor = _actor_motor(actuacion)
    instante = instante if instante is not None else ahora_utc()
    log = log if log is not None else LogEventos(actuacion_id=str(actuacion.id))

    def anadir(tipo: str, payload: Mapping[str, object]) -> None:
        log.anadir(tipo, payload, actor=actor, ocurrido_en=instante)

    # --- P0 admision / P3 ficha -----------------------------------------------------------------
    anadir(
        "ActuacionAbierta",
        {
            "actuacion_id": str(actuacion.id),
            "codigo_identificativo_propio": str(
                getattr(actuacion, "codigo_identificativo_propio", actuacion.id)
            ),
            "carpeta": getattr(getattr(actuacion, "carpeta", None), "name", None),
            "fecha_evaluacion": actuacion.fecha_evaluacion,
            "version_engine": getattr(actuacion, "version_engine", None),
        },
    )
    identidad = getattr(actuacion, "identidad_spec", None)
    anadir("FichaAsignada", identidad.a_dict() if identidad is not None else {})

    # --- P1 ingesta -----------------------------------------------------------------------------
    for doc in actuacion.documentos:
        anadir("DocumentoRegistrado", _documento_a_payload(doc))
    for doc in actuacion.documentos:
        if getattr(doc, "partes", ()):
            anadir(
                "PdfSeparado",
                {"doc_id": doc.doc_id, "sha256": doc.sha256, "partes": list(doc.partes)},
            )
    for doc in actuacion.documentos:
        if getattr(doc, "tipo", None):
            anadir(
                "DocumentoClasificado",
                {
                    "doc_id": doc.doc_id,
                    "tipo": doc.tipo,
                    "confianza_tipo": getattr(doc, "confianza_tipo", None),
                    "subtipo": getattr(doc, "subtipo", None),
                },
            )

    # --- P2 evidencias --------------------------------------------------------------------------
    datos = _datos_en_orden(consolidada)
    for evidencia, asignada in _evidencias_de(datos):
        anadir("EvidenciaPropuesta", {"asignada": asignada, "evidencia": evidencia_a_payload(evidencia)})
    for evidencia in consolidada.evidencias_no_asignadas:
        anadir("EvidenciaPropuesta", {"asignada": False, "evidencia": evidencia_a_payload(evidencia)})

    # --- P4 cruce -------------------------------------------------------------------------------
    for nombre, serie, dato in datos:
        anadir(
            "DatoConsolidado",
            {"variable": nombre, "num_serie_motor": serie, "nivel": dato.nivel, "dato": dato_a_payload(dato)},
        )
    for dato in consolidada.conflictos:
        anadir(
            "ConflictoDetectado",
            {
                "variable": dato.variable,
                "num_serie_motor": dato.num_serie_motor,
                "nivel": dato.nivel,
                "valores_por_fuente": dict(dato.valores_por_fuente),
                "evidencias": [evidencia_a_payload(ev) for ev in dato.evidencias],
            },
        )
    anadir(
        "ObservacionRegistrada",
        {
            "origen": ORIGEN_CONSOLIDACION,
            "avisos": list(consolidada.avisos),
            "vinculos_por_huella": dict(consolidada.vinculos_por_huella),
        },
    )

    # --- P5 calculo -----------------------------------------------------------------------------
    calculo = getattr(evaluacion, "calculo", None)
    if calculo is not None:
        anadir(
            "CalculoRealizado",
            {
                "total": calculo.total,
                "total_cae": calculo.total_cae,
                "provisional": bool(calculo.provisional),
                "detalle": calculo_a_dict(calculo),
            },
        )

    # --- P3 veredicto ---------------------------------------------------------------------------
    anadir("VeredictoEmitido", evaluacion.a_dict())
    return log


__all__ = ["CLASE_MOTOR", "ORIGEN_CONSOLIDACION", "dato_a_payload", "evidencia_a_payload", "grabar"]
