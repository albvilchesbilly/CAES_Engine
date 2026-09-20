"""Replay: volver a ejecutar el nucleo determinista con el log y solo con el log (`ADR-004` C2).

`reproducir(log, spec)` toma el log que escribio `engine.eventos.grabacion.grabar` y vuelve a emitir el
veredicto y el ahorro **sin abrir un solo fichero de `expedientes/`**. Es el criterio de aceptacion de S3.1
en `docs/06`: si el log no basta para reproducir el resultado, el log no es la fuente de verdad del ciclo,
es un adorno.

Que se reconstruye y de donde (todo sale del log; nada del disco):

| Pieza de `ActuacionConsolidada` | Evento del que sale |
|---|---|
| `documentos` (los legibles) | `DocumentoRegistrado` menos los que `PdfSeparado` declara combinados |
| `tipo` / `subtipo` de cada documento | `DocumentoClasificado` |
| `documentos_por_tipo` | derivado de los legibles, en su orden (igual que `evidencias.consolidar`) |
| `unidades` / `variables` | `DatoConsolidado` (payload entero: las tres capas de `docs/03` §5.3) |
| `conflictos` | `ConflictoDetectado`, resuelto contra el dato ya reconstruido (misma identidad) y vigente |
| `avisos`, `vinculos_por_huella` | `ObservacionRegistrada{origen: "consolidacion"}` |
| `evidencias_no_asignadas` | `EvidenciaPropuesta{asignada: false}` |
| `fecha_evaluacion` | `ActuacionAbierta` |

Lo que el replay **no** reconstruye, a proposito:

- La ingesta, la clasificacion y la extraccion. El replay arranca en la consolidacion porque las tres capas
  ya estan en el log con su cita; volver a abrir los PDF seria volver al disco, que es justo lo que este
  criterio prohibe. El bit a bit se comprueba de la consolidacion hacia delante (reglas y calculo), que es
  donde vive la decision.
- La telemetria (`Actuacion.tiempos`, segundos de reloj en `float`): no es log (`docs/03` §6.1).

Decisiones de esta pieza (para el ADR):

- **`reproducir` devuelve una `Evaluacion`**, como fija `ADR-004` C2. La consolidacion reconstruida se
  obtiene aparte con `consolidada_de(log)` y la comparacion con lo grabado, con `divergencias(...)`. Asi el
  replay tiene el mismo tipo de retorno que `engine.reglas.evaluar_actuacion` y se puede pasar al informe.
- **La spec se pasa por fuera.** El log guarda la identidad de la ficha (`FichaAsignada`) pero no la ficha:
  reproducir contra una spec nueva es precisamente lo que `ADR-004` pide poder hacer. Una identidad distinta
  no es error; `identidad_spec_de(log)` deja verlo.
- **La comparacion es por `json_canonico`, nunca por `==` de objetos.** Dos evaluaciones pueden ser iguales
  para `==` y diferir en la escala de un `Decimal`, o al reves.
- **`reproducir` no falla si diverge**: devuelve la evaluacion y `divergencias` explica en que. Quien quiera
  fallo duro llama a `verificar_replay`. Un replay que revienta no deja comparar nada.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any

from engine.calculo import a_dict as calculo_a_dict
from engine.eventos.canonico import ErrorEvento, json_canonico
from engine.eventos.log import Evento, LogEventos
from engine.evidencias import ActuacionConsolidada, DatoConsolidado, Evidencia
from engine.reglas import Evaluacion, evaluar_actuacion
from engine.spec_registry import Spec

#: Origen de la `ObservacionRegistrada` que cierra la consolidacion (el mismo que escribe `grabacion`).
ORIGEN_CONSOLIDACION = "consolidacion"

#: Tipos de evento sin los cuales un log no se puede reproducir.
TIPOS_NECESARIOS = ("ActuacionAbierta", "DatoConsolidado", "VeredictoEmitido")

_CAMPOS_EVIDENCIA = tuple(campo.name for campo in fields(Evidencia))
_CAMPOS_DATO = tuple(campo.name for campo in fields(DatoConsolidado))


@dataclass(frozen=True)
class DocumentoReproducido:
    """Un documento tal como el log lo conserva. Cumple `evidencias.DocumentoLike` y nada mas: el replay no
    vuelve a leer bytes, asi que de un documento solo quedan su huella, su nombre y su clasificacion."""

    doc_id: str
    sha256: str
    nombre: str
    tipo: str | None = None
    subtipo: str | None = None
    origen: str | None = None
    formato: str | None = None
    bytes: int | None = None
    paginas: int = 0
    rango_paginas: tuple[int, ...] | None = None
    partes: tuple[str, ...] = ()

    @property
    def es_combinado(self) -> bool:
        return bool(self.partes)


# ---------------------------------------------------------------------------
# Lectura del log
# ---------------------------------------------------------------------------


def _primero(log: LogEventos, tipo: str) -> Evento:
    eventos = log.por_tipo(tipo)
    if not eventos:
        raise ErrorEvento(f"el log no se puede reproducir: no contiene ningun {tipo}")
    return eventos[0]


def _texto(valor: object) -> str | None:
    return None if valor is None else str(valor)


def documentos_de(log: LogEventos) -> list[DocumentoReproducido]:
    """Los documentos que el log conserva, en orden de registro y ya clasificados (ver la cabecera)."""
    combinados: dict[str, tuple[str, ...]] = {}
    for evento in log.por_tipo("PdfSeparado"):
        datos = evento.datos
        combinados[str(datos.get("doc_id"))] = tuple(str(p) for p in datos.get("partes") or ())
    clasificacion: dict[str, dict[str, object]] = {}
    for evento in log.por_tipo("DocumentoClasificado"):
        datos = evento.datos
        clasificacion[str(datos.get("doc_id"))] = datos

    documentos: list[DocumentoReproducido] = []
    for evento in log.por_tipo("DocumentoRegistrado"):
        datos = evento.datos
        doc_id = str(datos.get("doc_id"))
        clase = clasificacion.get(doc_id, {})
        rango = datos.get("rango_paginas")
        paginas = datos.get("paginas")
        tamano = datos.get("bytes")
        documentos.append(
            DocumentoReproducido(
                doc_id=doc_id,
                sha256=str(datos.get("sha256") or ""),
                nombre=str(datos.get("nombre") or ""),
                tipo=_texto(clase.get("tipo")),
                subtipo=_texto(clase.get("subtipo")),
                origen=_texto(datos.get("origen")),
                formato=_texto(datos.get("formato")),
                bytes=tamano if isinstance(tamano, int) else None,
                paginas=paginas if isinstance(paginas, int) else 0,
                rango_paginas=tuple(int(v) for v in rango) if isinstance(rango, list) else None,
                partes=combinados.get(doc_id, ()),
            )
        )
    return documentos


def _evidencia_desde(payload: Mapping[str, object]) -> Evidencia:
    campos = {clave: payload.get(clave) for clave in _CAMPOS_EVIDENCIA if clave in payload}
    faltan = [c for c in ("variable", "valor", "doc_id", "tipo_evidencia") if c not in campos]
    if faltan:
        raise ErrorEvento(f"evidencia del log incompleta: faltan {faltan}")
    return Evidencia(**campos)  # type: ignore[arg-type]


def _dato_desde(payload: Mapping[str, object]) -> DatoConsolidado:
    campos: dict[str, Any] = {clave: payload.get(clave) for clave in _CAMPOS_DATO if clave in payload}
    for clave in ("evidencias", "posibles_errores_ocr"):
        crudas = campos.get(clave) or []
        if not isinstance(crudas, list):
            raise ErrorEvento(f"`{clave}` de un DatoConsolidado del log no es una lista")
        campos[clave] = [_evidencia_desde(ev) for ev in crudas]
    if "variable" not in campos:
        raise ErrorEvento("DatoConsolidado del log sin `variable`")
    return DatoConsolidado(**campos)


def consolidada_de(log: LogEventos) -> ActuacionConsolidada:
    """Reconstruye la `ActuacionConsolidada` con lo que el log guarda, sin tocar `expedientes/`."""
    documentos = [doc for doc in documentos_de(log) if not doc.es_combinado]
    documentos_por_tipo: dict[str, list[Any]] = {}
    for doc in documentos:
        if doc.tipo:
            documentos_por_tipo.setdefault(doc.tipo, []).append(doc)

    unidades: dict[str, dict[str, DatoConsolidado]] = {}
    variables: dict[str, DatoConsolidado] = {}
    for evento in log.por_tipo("DatoConsolidado"):
        datos = evento.datos
        cuerpo = datos.get("dato")
        if not isinstance(cuerpo, Mapping):
            raise ErrorEvento("un DatoConsolidado del log no trae su `dato`")
        dato = _dato_desde(cuerpo)
        serie = datos.get("num_serie_motor")
        nombre = str(datos.get("variable") or dato.variable)
        if serie is None:
            variables[nombre] = dato
        else:
            unidades.setdefault(str(serie), {})[nombre] = dato

    # Un conflicto no es una copia del dato: es **el mismo** dato, como en `evidencias.consolidar`.
    # Y es el dato quien dice si sigue habiendo conflicto: un log solo-anadir con un recalculo posterior
    # (S3.8, correccion humana) conserva el `ConflictoDetectado` de la ejecucion vieja, que es historia y
    # no un conflicto de hoy. Sin esta comprobacion el replay bloquearia un veredicto ya resuelto.
    conflictos: list[DatoConsolidado] = []
    for evento in log.por_tipo("ConflictoDetectado"):
        datos = evento.datos
        serie = datos.get("num_serie_motor")
        nombre = str(datos.get("variable"))
        dato_conflicto = variables.get(nombre) if serie is None else unidades.get(str(serie), {}).get(nombre)
        if dato_conflicto is None:
            raise ErrorEvento(
                f"el log declara un conflicto en {nombre!r} (unidad {serie!r}) sin su DatoConsolidado"
            )
        if dato_conflicto.conflicto and not any(d is dato_conflicto for d in conflictos):
            conflictos.append(dato_conflicto)

    avisos: list[str] = []
    vinculos: dict[str, str] = {}
    for evento in log.por_tipo("ObservacionRegistrada"):
        datos = evento.datos
        if datos.get("origen") != ORIGEN_CONSOLIDACION:
            continue
        avisos = [str(a) for a in datos.get("avisos") or []]
        crudos = datos.get("vinculos_por_huella") or {}
        vinculos = {str(k): str(v) for k, v in crudos.items()} if isinstance(crudos, Mapping) else {}

    no_asignadas: list[Evidencia] = []
    for evento in log.por_tipo("EvidenciaPropuesta"):
        datos = evento.datos
        if datos.get("asignada") is not False:
            continue
        cuerpo = datos.get("evidencia")
        if isinstance(cuerpo, Mapping):
            no_asignadas.append(_evidencia_desde(cuerpo))

    return ActuacionConsolidada(
        documentos=documentos,
        unidades=unidades,
        variables=variables,
        conflictos=conflictos,
        avisos=avisos,
        documentos_por_tipo=documentos_por_tipo,
        vinculos_por_huella=vinculos,
        evidencias_no_asignadas=no_asignadas,
    )


def fecha_de(log: LogEventos) -> date:
    """`fecha_evaluacion` de la ejecucion grabada (INT-10; va en `ActuacionAbierta`)."""
    fecha = _primero(log, "ActuacionAbierta").datos.get("fecha_evaluacion")
    if not isinstance(fecha, date) or isinstance(fecha, datetime):
        raise ErrorEvento(f"`fecha_evaluacion` del log no es una fecha (sin hora): {fecha!r}")
    return fecha


def identidad_spec_de(log: LogEventos) -> dict[str, object]:
    """La ficha con la que se evaluo (`FichaAsignada`); `{}` si el log no la trae."""
    evento = log.ultimo("FichaAsignada")
    return dict(evento.datos) if evento is not None else {}


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def reproducir(log: LogEventos, spec: Spec, *, fecha_evaluacion: date | None = None) -> Evaluacion:
    """Vuelve a ejecutar reglas y calculo con el log y solo con el log (ver la cabecera).

    Verifica primero la cadena de hash: reproducir un log alterado no demuestra nada. `fecha_evaluacion`
    solo se pasa para reproducir a otra fecha; por defecto es la que el log guarda.
    """
    if not isinstance(log, LogEventos):
        raise ErrorEvento(f"se reproduce un LogEventos, no {type(log).__name__}")
    log.verificar()
    faltan = [tipo for tipo in TIPOS_NECESARIOS if not log.por_tipo(tipo)]
    if faltan:
        raise ErrorEvento(f"el log no se puede reproducir: le faltan eventos {faltan}")
    consolidada = consolidada_de(log)
    fecha = fecha_evaluacion or fecha_de(log)
    return evaluar_actuacion(consolidada, spec, fecha_evaluacion=fecha)


def _diferencia(que: str, grabado: object, reproducido: object) -> str | None:
    izquierda, derecha = json_canonico(grabado), json_canonico(reproducido)
    if izquierda == derecha:
        return None
    return f"{que}: el log dice {izquierda[:200]} y el replay {derecha[:200]}"


def divergencias(log: LogEventos, evaluacion: Evaluacion) -> tuple[str, ...]:
    """En que difiere el replay de lo grabado, comparado **por `json_canonico`** (`ADR-004` C2).

    Vacia = el replay reprodujo veredicto, ahorro y traza de reglas bit a bit.
    """
    encontradas: list[str | None] = []
    veredicto = log.ultimo("VeredictoEmitido")
    if veredicto is not None:
        grabado = veredicto.datos
        encontradas.append(_diferencia("veredicto", grabado.get("veredicto"), evaluacion.veredicto))
        encontradas.append(_diferencia("evaluacion", grabado, evaluacion.a_dict()))
    evento_calculo = log.ultimo("CalculoRealizado")
    calculo = evaluacion.calculo
    if evento_calculo is None and calculo is not None:
        encontradas.append("calculo: el log no grabo ningun CalculoRealizado y el replay si calculo")
    elif evento_calculo is not None:
        grabado = evento_calculo.datos
        if calculo is None:
            encontradas.append("calculo: el log grabo un CalculoRealizado y el replay no calculo")
        else:
            encontradas.append(_diferencia("AETOTAL", grabado.get("total"), calculo.total))
            encontradas.append(_diferencia("AETOTAL kWh", grabado.get("total_cae"), calculo.total_cae))
            encontradas.append(
                _diferencia("detalle del calculo", grabado.get("detalle"), calculo_a_dict(calculo))
            )
    return tuple(d for d in encontradas if d)


def verificar_replay(log: LogEventos, spec: Spec) -> Evaluacion:
    """`reproducir` con fallo duro: `ErrorEvento` si el replay no da lo mismo bit a bit."""
    evaluacion = reproducir(log, spec)
    diferencias = divergencias(log, evaluacion)
    if diferencias:
        detalle = "; ".join(diferencias)
        raise ErrorEvento(f"el replay de {log.actuacion_id} no reproduce lo grabado: {detalle}")
    return evaluacion


__all__ = [
    "ORIGEN_CONSOLIDACION",
    "TIPOS_NECESARIOS",
    "DocumentoReproducido",
    "consolidada_de",
    "divergencias",
    "documentos_de",
    "fecha_de",
    "identidad_spec_de",
    "reproducir",
    "verificar_replay",
]
