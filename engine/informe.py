"""Informe de prevalidacion en markdown y en JSON (`docs/01` §3.3, `docs/05` §2.2).

Es la vista humana de lo que produjo `engine.motor.procesar_actuacion`: **no calcula ni decide nada**. Todo
lo que muestra sale de la spec (descargo, semaforos, interpretaciones, nombres de salida del calculo) o de
los resultados de los modulos (evaluacion, calculo, consolidacion, documentos). Por eso en este fichero no
hay ningun identificador de regla, ningun nombre de variable de la ficha y ninguna rama por ficha.

Secciones del markdown, en este orden (brief de F0.10 y `docs/05` §2.2):

0. Cabecera con la identidad de la actuacion, la de la spec y el descargo de la propia spec.
1. Veredicto con su semaforo y, si la spec lo declara, su mensaje.
2. Ahorro: valor exacto y truncado; "estimacion no acreditada" si es provisional; motivo y evidencias
   enfrentadas si no hay calculo. Nunca se publica un ahorro cuando el total es `None`.
3. Calculo por unidad: entradas, derivadas, controles fisicos, salida y la traza completa.
4. Reglas por fase, con las fases evaluadas y las saltadas.
5. Carencias: que falta y con que documentos se subsana.
6. Evidencias por variable, con las tres capas (documento → interpretacion → valor consumido).
7. Interpretaciones aplicadas y avisos.
8. Documentos con su huella.

`a_json` devuelve un `dict` serializable con `json.dumps` sin `default=`: `Decimal` y `date` como cadena,
apoyandose en los `a_dict()` que ya exponen los modulos del nucleo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal

from engine.calculo import ResultadoCalculo, ResultadoUnidad
from engine.calculo import a_dict as calculo_a_dict
from engine.evidencias import DatoConsolidado, Evidencia
from engine.expresiones import NO_EVALUABLE
from engine.ingesta import Documento
from engine.motor import Actuacion
from engine.reglas import (
    ALIAS_CONTEXTO,
    FASE_CALCULO,
    ORDEN_FASES,
    ORIGEN_FECHA_EVALUACION,
    Evaluacion,
    ResultadoRegla,
)

#: Longitud maxima del texto literal de una cita en el markdown (en el JSON va completo).
LARGO_CITA = 200

#: Rotulo obligatorio de un ahorro que no esta acreditado (`docs/05` §2.2, caso B). Es texto para
#: personas, no un identificador: por eso lleva tildes.
ROTULO_PROVISIONAL = "estimación no acreditada"

SIN_DATO = "—"


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------


def texto_decimal(valor: Decimal) -> str:
    """Decimal en su forma canonica, sin notacion exponencial y sin ceros de cola."""
    return format(valor.normalize(), "f")


def texto_es(valor: Decimal | int) -> str:
    """La misma cifra en la forma que lee una persona en español: 305829.6 → '305.829,6'.

    Va **junto** a la forma canonica, nunca en su lugar: quien compara o vuelve a operar usa
    `texto_decimal`, y esto es para leer. El formato se hace sobre el texto canonico del `Decimal`
    (agrupar digitos, cambiar el punto por una coma), asi que **el ahorro no pasa por coma flotante**
    en ningun punto (`CLAUDE.md` §2). `miles` es el caso entero de esta misma funcion.
    """
    canonico = texto_decimal(Decimal(valor))
    signo, sin_signo = ("-", canonico[1:]) if canonico.startswith("-") else ("", canonico)
    entera, _, decimales = sin_signo.partition(".")
    agrupada = f"{int(entera or 0):,}".replace(",", ".")
    return f"{signo}{agrupada},{decimales}" if decimales else f"{signo}{agrupada}"


def miles(entero: int) -> str:
    """Entero con separador de miles español (305829 → '305.829')."""
    return texto_es(entero)


def _valor(valor: object) -> str:
    if valor is None:
        return SIN_DATO
    if valor is NO_EVALUABLE:
        return "NO_EVALUABLE"
    if isinstance(valor, bool):
        return "si" if valor else "no"
    if isinstance(valor, Decimal):
        return texto_decimal(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, (list, tuple)):
        return ", ".join(_valor(v) for v in valor) or SIN_DATO
    return str(valor)


def _celda(valor: object, largo: int = LARGO_CITA) -> str:
    """Un valor listo para una celda de tabla markdown: sin saltos, sin barras, acotado."""
    texto = " ".join(_valor(valor).split())
    if len(texto) > largo:
        texto = texto[: largo - 1].rstrip() + "…"
    return texto.replace("|", "\\|")


def _tabla(cabecera: Sequence[str], filas: Iterable[Sequence[object]]) -> list[str]:
    lineas = ["| " + " | ".join(cabecera) + " |", "|" + "|".join(["---"] * len(cabecera)) + "|"]
    vacia = True
    for fila in filas:
        lineas.append("| " + " | ".join(_celda(c) for c in fila) + " |")
        vacia = False
    if vacia:
        lineas.append("| " + " | ".join([SIN_DATO] * len(cabecera)) + " |")
    return lineas


def _lista(elementos: Iterable[object]) -> list[str]:
    lineas = [f"- {_valor(e)}" for e in elementos]
    return lineas or [f"- {SIN_DATO}"]


# ---------------------------------------------------------------------------
# Lectura de la spec (nada de esto se escribe en codigo)
# ---------------------------------------------------------------------------


def _estado(actuacion: Actuacion, clave: str) -> Mapping[str, object]:
    estados = actuacion.spec.estados
    valor = estados.get(clave) if isinstance(estados, Mapping) else None
    return valor if isinstance(valor, Mapping) else {}


def semaforo_de(actuacion: Actuacion) -> str:
    return str(_estado(actuacion, actuacion.veredicto).get("semaforo") or "").strip()


def mensaje_de(actuacion: Actuacion) -> str:
    return str(_estado(actuacion, actuacion.veredicto).get("mensaje") or "").strip()


def descargo_de(actuacion: Actuacion) -> str:
    estados = actuacion.spec.estados
    descargo = estados.get("descargo") if isinstance(estados, Mapping) else None
    return " ".join(str(descargo or "").split())


def _criterios_de_fecha(actuacion: Actuacion) -> list[str]:
    """Nombres de la `logica` que el motor de reglas resuelve con la fecha de evaluacion, con su nota."""
    criterios: list[str] = []
    for nombre, alias in ALIAS_CONTEXTO.items():
        if alias.get("origen") != ORIGEN_FECHA_EVALUACION:
            continue
        interpretacion = str(alias.get("interpretacion") or "").strip()
        nota = " ".join(str(alias.get("nota") or "").split())
        etiqueta = f"`{nombre}` = fecha de evaluacion"
        if interpretacion:
            etiqueta += f" ({interpretacion})"
        criterios.append(f"{etiqueta}: {nota}" if nota else etiqueta)
    return criterios


def interpretacion_declarada(actuacion: Actuacion, id_interpretacion: str) -> dict[str, str]:
    """Tema y criterio de una interpretacion, leidos de la spec; si no los declara, de donde salga."""
    try:
        declarada = actuacion.spec.interpretacion(id_interpretacion)
    except KeyError:
        declarada = {}
    tema = str(declarada.get("tema") or "").strip()
    criterio = str(declarada.get("criterio_poc") or declarada.get("criterio") or "").strip()
    if not tema and not criterio:
        for alias in ALIAS_CONTEXTO.values():
            if str(alias.get("interpretacion") or "") == id_interpretacion:
                tema = "criterio del motor de reglas, no declarado en la spec"
                criterio = " ".join(str(alias.get("nota") or "").split())
                break
    return {
        "id": id_interpretacion,
        "tema": tema or SIN_DATO,
        "criterio": criterio or SIN_DATO,
        "alternativa": str(declarada.get("alternativa") or "").strip(),
        "impacto": str(declarada.get("impacto") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Lectura de los resultados
# ---------------------------------------------------------------------------


def _documentos_por_id(actuacion: Actuacion) -> dict[str, Documento]:
    indice: dict[str, Documento] = {}
    for doc in actuacion.documentos:
        indice.setdefault(doc.doc_id, doc)
        indice.setdefault(doc.sha256, doc)
    return indice


def _nombre_documento(indice: Mapping[str, Documento], doc_id: str) -> str:
    doc = indice.get(doc_id)
    return doc.nombre if doc is not None else f"doc {doc_id[:12]}…"


def motivo_sin_calculo(actuacion: Actuacion) -> str:
    """Por que no hay ahorro publicable. Se compone de lo que ya decidieron reglas y calculo."""
    evaluacion = actuacion.evaluacion
    calculo = actuacion.calculo
    if calculo is not None and calculo.motivo_no_calculo:
        return str(calculo.motivo_no_calculo)
    if evaluacion.bloqueo_por_conflicto:
        return (
            "conflicto entre fuentes fiables en "
            f"{', '.join(evaluacion.bloqueo_por_conflicto)}: el motor no elige valor ni calcula"
        )
    bloqueantes = [r.id for r in evaluacion.resultados if r.falla and r.bloqueante]
    if bloqueantes:
        return f"reglas bloqueantes falladas: {', '.join(bloqueantes)}"
    if calculo is None:
        return "no se calculo (ver fases saltadas)"
    if calculo.total is None:
        return "el resultado se retiro tras los controles fisicos"
    return ""


def datos_en_conflicto(actuacion: Actuacion) -> list[DatoConsolidado]:
    variables = set(actuacion.evaluacion.bloqueo_por_conflicto)
    if not variables:
        return list(actuacion.consolidada.conflictos)
    return [d for d in actuacion.consolidada.conflictos if d.variable in variables]


def datos_consolidados(actuacion: Actuacion) -> list[tuple[str | None, DatoConsolidado]]:
    """Todos los datos consolidados: primero los de la actuacion, despues los de cada unidad."""
    filas: list[tuple[str | None, DatoConsolidado]] = [
        (None, dato) for _, dato in sorted(actuacion.consolidada.variables.items())
    ]
    for serie, datos in sorted(actuacion.consolidada.unidades.items()):
        filas.extend((serie, dato) for _, dato in sorted(datos.items()))
    return filas


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _cabecera(actuacion: Actuacion) -> list[str]:
    identidad = actuacion.identidad_spec
    lineas = [f"# Informe de prevalidacion — {actuacion.id}", ""]
    lineas += _tabla(
        ["Campo", "Valor"],
        [
            ["Actuacion", actuacion.id],
            ["Codigo identificativo propio", actuacion.codigo_identificativo_propio],
            ["Carpeta", actuacion.carpeta],
            ["Ficha", f"{identidad.codigo} v{identidad.version_ficha}"],
            ["version_spec", identidad.version_spec],
            ["hash_spec", identidad.hash_spec],
            ["hash_reglas", identidad.hash_reglas],
            ["Fecha de evaluacion", actuacion.fecha_evaluacion],
            ["Version del Engine", actuacion.version_engine],
            ["Documentos", len(actuacion.documentos)],
            ["Unidades", actuacion.consolidada.n_unidades],
        ],
    )
    criterios = _criterios_de_fecha(actuacion)
    if criterios:
        lineas += ["", "Criterio de fecha (no es un dato leido de ningun documento):"]
        lineas += [f"- {c}" for c in criterios]
    descargo = descargo_de(actuacion)
    if descargo:
        lineas += ["", f"> {descargo}"]
    return lineas


def _veredicto(actuacion: Actuacion) -> list[str]:
    semaforo = semaforo_de(actuacion)
    titulo = f"{semaforo} **{actuacion.veredicto}**" if semaforo else f"**{actuacion.veredicto}**"
    lineas = ["", "## 1. Veredicto", "", titulo]
    mensaje = mensaje_de(actuacion)
    if mensaje:
        lineas += ["", mensaje]
    condicion = str(_estado(actuacion, actuacion.veredicto).get("condicion") or "").strip()
    if condicion:
        lineas += ["", f"Condicion declarada en la spec: {condicion}."]
    return lineas


def _evidencias_enfrentadas(actuacion: Actuacion) -> list[str]:
    indice = _documentos_por_id(actuacion)
    lineas: list[str] = []
    for dato in datos_en_conflicto(actuacion):
        serie = dato.num_serie_motor
        titulo = dato.variable if serie is None else f"{dato.variable} ({serie})"
        lineas += ["", f"Conflicto en **{titulo}** — `valor_consumido` = null; se conservan las evidencias:"]
        lineas += _tabla(
            ["Valor", "Documento", "Tipo", "Pag.", "Texto literal", "Metodo", "Confianza"],
            [
                [
                    ev.valor,
                    _nombre_documento(indice, ev.doc_id),
                    ev.tipo_doc,
                    ev.pagina,
                    ev.texto_literal,
                    ev.metodo,
                    ev.confianza,
                ]
                for ev in dato.evidencias
            ],
        )
    return lineas


def _ahorro(actuacion: Actuacion) -> list[str]:
    plan = actuacion.spec.plan
    calculo = actuacion.calculo
    lineas = ["", "## 2. Ahorro", ""]
    if calculo is None or calculo.total is None:
        lineas += [
            f"**Sin ahorro publicable**: no se emite ningun valor de `{plan.salida_total}`.",
            "",
            f"Motivo: {motivo_sin_calculo(actuacion)}.",
        ]
        lineas += _evidencias_enfrentadas(actuacion)
        return lineas
    redondeo = plan.criterio_redondeo
    clave_cae = redondeo.clave if redondeo is not None else f"{plan.salida_total}_cae"
    criterio = redondeo.criterio if redondeo is not None else SIN_DATO
    interpretacion = redondeo.interpretacion if redondeo is not None else None
    filas: list[Sequence[object]] = [
        [f"`{plan.salida_total}` (exacto)", f"{texto_decimal(calculo.total)} kWh/año"],
    ]
    if calculo.total_cae is not None:
        detalle = f"{miles(calculo.total_cae)} kWh ({criterio}"
        detalle += f"; {interpretacion})" if interpretacion else ")"
        filas.append([f"`{clave_cae}`", detalle])
    lineas += _tabla(["Magnitud", "Valor"], filas)
    if calculo.provisional:
        lineas += [
            "",
            f"**{ROTULO_PROVISIONAL.upper()}**: el calculo es provisional; el valor anterior es una "
            f"{ROTULO_PROVISIONAL} y no puede presentarse como ahorro acreditado.",
        ]
    lineas += _evidencias_enfrentadas(actuacion)
    return lineas


def _unidad(actuacion: Actuacion, unidad: ResultadoUnidad) -> list[str]:
    plan = actuacion.spec.plan
    lineas = ["", f"### Unidad {unidad.num_serie_motor}", ""]
    lineas += _tabla(
        ["Entrada", "Valor", "Interpretacion"],
        [
            [nombre, valor, plan.interpretaciones_por_entrada.get(nombre, "")]
            for nombre, valor in sorted(unidad.entradas.items())
        ],
    )
    lineas += ["", "Derivadas:"]
    lineas += _tabla(
        ["Derivada", "Valor", "Origen"],
        [
            [nombre, valor, unidad.fuentes.get(nombre, "")]
            for nombre, valor in sorted(unidad.derivadas.items())
        ],
    )
    lineas += ["", "Controles fisicos y precondiciones:"]
    lineas += _tabla(
        ["Control", "Resultado"],
        [[nombre, valor] for nombre, valor in sorted(unidad.controles.items())]
        + [[f"precondicion {texto}", valor] for texto, valor in sorted(unidad.precondiciones.items())],
    )
    salida = f"**`{plan.salida_unidad}` = {_valor(unidad.salida)}**"
    if unidad.salida is not None:
        salida += " kWh/año"
    lineas += ["", salida]
    if unidad.motivo_no_calculo:
        lineas += ["", f"No se calculo: {unidad.motivo_no_calculo}."]
    if unidad.avisos:
        lineas += ["", "Avisos de la unidad:"] + _lista(unidad.avisos)
    return lineas


def _calculo(actuacion: Actuacion) -> list[str]:
    calculo = actuacion.calculo
    lineas = ["", "## 3. Calculo por unidad", ""]
    if calculo is None:
        lineas += [f"No hubo calculo: {motivo_sin_calculo(actuacion)}."]
        return lineas
    for unidad in calculo.por_unidad:
        lineas += _unidad(actuacion, unidad)
    lineas += ["", "### Traza", "", "```"]
    lineas += list(calculo.traza) or ["(sin traza)"]
    lineas += ["```"]
    return lineas


def _reglas(actuacion: Actuacion) -> list[str]:
    evaluacion = actuacion.evaluacion
    lineas = ["", "## 4. Reglas", ""]
    lineas += _tabla(
        ["Fases evaluadas", "Fases saltadas"],
        [[", ".join(evaluacion.fases_evaluadas), ", ".join(evaluacion.fases_saltadas) or SIN_DATO]],
    )
    por_fase: dict[str, list[ResultadoRegla]] = {}
    for resultado in evaluacion.resultados:
        por_fase.setdefault(resultado.fase, []).append(resultado)
    conocidas = set(por_fase) | set(evaluacion.fases_evaluadas) | set(evaluacion.fases_saltadas)
    fases = [f for f in ORDEN_FASES if f in conocidas]
    fases += [f for f in por_fase if f not in ORDEN_FASES]
    for fase in fases:
        resultados = por_fase.get(fase, [])
        saltada = fase in evaluacion.fases_saltadas
        lineas += ["", f"### Fase {fase}" + (" (saltada)" if saltada else ""), ""]
        if saltada:
            motivos = [r.motivo for r in resultados if r.motivo] or [motivo_sin_calculo(actuacion)]
            lineas += [f"No se evaluo: {motivos[0]}.", ""]
        if not resultados:
            nota = "Esta fase no tiene reglas en esta spec."
            if fase == FASE_CALCULO:
                nota += " Es el paso de calculo: su resultado esta en la seccion 3."
            lineas += [nota]
            continue
        lineas += _tabla(
            ["Id", "Severidad", "Resultado", "Descripcion", "Motivo"],
            [[r.id, r.severidad, r.resultado.value, r.descripcion, r.motivo or ""] for r in resultados],
        )
    return lineas


def _carencias(evaluacion: Evaluacion) -> list[str]:
    lineas = ["", "## 5. Carencias (que falta)", ""]
    if not evaluacion.carencias:
        lineas += ["No hay carencias: ninguna regla falla."]
        return lineas
    lineas += _tabla(
        ["Regla", "Severidad", "Que falta", "Documentos con los que se subsana"],
        [
            [c.get("id"), c.get("severidad"), c.get("mensaje"), ", ".join(c.get("documentos") or [])]
            for c in evaluacion.carencias
        ],
    )
    return lineas


def _fila_evidencia(indice: Mapping[str, Documento], serie: str | None, ev: Evidencia) -> list[object]:
    return [
        ev.variable,
        serie or SIN_DATO,
        _nombre_documento(indice, ev.doc_id),
        ev.tipo_doc,
        ev.pagina,
        ev.texto_literal,
        ev.metodo,
        ev.confianza,
        ev.tipo_evidencia,
        ev.valor,
    ]


def _evidencias(actuacion: Actuacion) -> list[str]:
    indice = _documentos_por_id(actuacion)
    lineas = [
        "",
        "## 6. Evidencias por variable",
        "",
        "Tres capas por dato: documento (cita literal) → interpretacion (valor normalizado, tipo de "
        "evidencia) → calculo (valor consumido).",
        "",
    ]
    for serie, dato in datos_consolidados(actuacion):
        titulo = dato.variable if serie is None else f"{dato.variable} · {serie}"
        estado = "conflicto: valor_consumido = null" if dato.conflicto else _celda(dato.valor_consumido)
        lineas += [
            "",
            f"**{titulo}** — valor consumido: {estado}"
            + (f" {dato.unidad}" if dato.unidad and not dato.conflicto else ""),
            "",
            f"- Capa 2 (interpretacion): normalizado `{_celda(dato.valor_normalizado, 120)}`, tipo de "
            f"evidencia `{dato.tipo_evidencia or SIN_DATO}`, fuente primaria "
            f"`{dato.fuente_primaria or SIN_DATO}`"
            + (f", interpretacion `{dato.interpretacion}`" if dato.interpretacion else ""),
        ]
        if dato.valores_por_fuente:
            valores = ", ".join(f"{k} = {v}" for k, v in dato.valores_por_fuente.items())
            lineas += [f"- Valores por fuente: {_celda(valores, 400)}"]
        lineas += [""]
        lineas += _tabla(
            [
                "Variable",
                "Unidad",
                "Documento",
                "Tipo",
                "Pag.",
                "Texto literal",
                "Metodo",
                "Confianza",
                "Tipo evid.",
                "Valor",
            ],
            [_fila_evidencia(indice, serie, ev) for ev in dato.evidencias],
        )
        if dato.posibles_errores_ocr:
            lineas += ["", "Posibles errores de OCR (no bloquean):"]
            lineas += _tabla(
                ["Documento", "Pag.", "Texto literal", "Confianza", "Valor"],
                [
                    [
                        _nombre_documento(indice, ev.doc_id),
                        ev.pagina,
                        ev.texto_literal,
                        ev.confianza,
                        ev.valor,
                    ]
                    for ev in dato.posibles_errores_ocr
                ],
            )
        if dato.avisos:
            lineas += ["", "Avisos del dato:"] + _lista(dato.avisos)
    return lineas


def _interpretaciones(actuacion: Actuacion) -> list[str]:
    lineas = ["", "## 7. Interpretaciones aplicadas y avisos", ""]
    lineas += _tabla(
        ["Id", "Tema", "Criterio aplicado", "Alternativa", "Impacto"],
        [
            [i["id"], i["tema"], i["criterio"], i["alternativa"], i["impacto"]]
            for i in (
                interpretacion_declarada(actuacion, id_int)
                for id_int in actuacion.evaluacion.interpretaciones_aplicadas
            )
        ],
    )
    lineas += ["", "### Avisos", ""]
    lineas += _lista(actuacion.avisos)
    return lineas


def _documentos(actuacion: Actuacion) -> list[str]:
    lineas = ["", "## 8. Documentos", ""]
    lineas += _tabla(
        ["Fichero", "Tipo", "Confianza", "Formato", "Pag.", "SHA-256", "Origen (parte de)"],
        [
            [
                doc.nombre,
                doc.tipo or SIN_DATO,
                doc.confianza_tipo,
                doc.formato,
                len(doc.paginas),
                doc.sha256,
                f"{doc.origen[:12]}… p{doc.rango_paginas[0]}-{doc.rango_paginas[1]}"
                if doc.origen and doc.rango_paginas
                else (doc.origen or SIN_DATO),
            ]
            for doc in actuacion.documentos
        ],
    )
    return lineas


def a_markdown(actuacion: Actuacion) -> str:
    """Informe de prevalidacion completo en markdown (ver cabecera del modulo)."""
    lineas: list[str] = []
    lineas += _cabecera(actuacion)
    lineas += _veredicto(actuacion)
    lineas += _ahorro(actuacion)
    lineas += _calculo(actuacion)
    lineas += _reglas(actuacion)
    lineas += _carencias(actuacion.evaluacion)
    lineas += _evidencias(actuacion)
    lineas += _interpretaciones(actuacion)
    lineas += _documentos(actuacion)
    lineas += ["", f"_Tiempos (s): {actuacion.tiempos}_", ""]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _ahorro_json(actuacion: Actuacion) -> dict[str, object]:
    plan = actuacion.spec.plan
    calculo: ResultadoCalculo | None = actuacion.calculo
    redondeo = plan.criterio_redondeo
    salida: dict[str, object] = {
        "salida_total": plan.salida_total,
        "salida_unidad": plan.salida_unidad,
        "clave_truncada": redondeo.clave if redondeo is not None else None,
        "criterio_redondeo": redondeo.criterio if redondeo is not None else None,
        "interpretacion_redondeo": redondeo.interpretacion if redondeo is not None else None,
        "exacto": None,
        "truncado": None,
        "provisional": bool(calculo.provisional) if calculo is not None else False,
        "rotulo": None,
        "motivo_no_calculo": None,
        "bloqueo_por_conflicto": list(actuacion.evaluacion.bloqueo_por_conflicto),
    }
    if calculo is not None and calculo.total is not None:
        salida["exacto"] = texto_decimal(calculo.total)
        salida["truncado"] = calculo.total_cae
        if calculo.provisional:
            salida["rotulo"] = ROTULO_PROVISIONAL
    else:
        salida["motivo_no_calculo"] = motivo_sin_calculo(actuacion)
    return salida


def _conflictos_json(actuacion: Actuacion) -> list[dict[str, object]]:
    return [
        {
            "variable": dato.variable,
            "num_serie_motor": dato.num_serie_motor,
            "valor_consumido": None,
            "evidencias": [ev.a_dict() for ev in dato.evidencias],
        }
        for dato in datos_en_conflicto(actuacion)
    ]


def a_json(actuacion: Actuacion) -> dict:
    """El mismo informe como `dict` serializable con `json.dumps` (Decimal y date como cadena)."""
    calculo = actuacion.calculo
    return {
        "version_engine": actuacion.version_engine,
        "actuacion": actuacion.a_dict(),
        "spec": actuacion.identidad_spec.a_dict(),
        "descargo": descargo_de(actuacion),
        "veredicto": {
            "valor": actuacion.veredicto,
            "semaforo": semaforo_de(actuacion),
            "mensaje": mensaje_de(actuacion),
        },
        "ahorro": _ahorro_json(actuacion),
        "calculo": calculo_a_dict(calculo) if calculo is not None else None,
        "evaluacion": actuacion.evaluacion.a_dict(),
        "carencias": [dict(c) for c in actuacion.evaluacion.carencias],
        "interpretaciones_aplicadas": [
            interpretacion_declarada(actuacion, id_int)
            for id_int in actuacion.evaluacion.interpretaciones_aplicadas
        ],
        "conflictos": _conflictos_json(actuacion),
        "consolidada": actuacion.consolidada.a_dict(),
        "documentos": [doc.a_dict() for doc in actuacion.documentos],
        "avisos": list(actuacion.avisos),
        "tiempos": dict(actuacion.tiempos),
    }


__all__ = [
    "LARGO_CITA",
    "ROTULO_PROVISIONAL",
    "a_json",
    "a_markdown",
    "datos_consolidados",
    "datos_en_conflicto",
    "descargo_de",
    "interpretacion_declarada",
    "mensaje_de",
    "miles",
    "motivo_sin_calculo",
    "semaforo_de",
    "texto_decimal",
    "texto_es",
]
