#!/usr/bin/env python
"""`python evaluar_casos.py`: la matriz esperado/obtenido de los siete casos A–G (`docs/05` §8.1).

Es la **vista humana** de la puerta de integracion (`CLAUDE.md` §4): recorre `expedientes/EXP001-*/`, ejecuta
`engine.motor.procesar_actuacion` sobre cada carpeta, lee el ground truth de
`expedientes/_resultados_esperados/` y escribe los informes en `informes/`. No sustituye a `pytest`: los
tests son la garantia modulo a modulo; esto es el tablero que se mira en cada sesion.

Que compara, y con que criterio (`docs/05` §8.1 y `ADR-002` §6.5):

| Campo | Criterio |
|---|---|
| `veredicto_esperado` | igualdad |
| `aetotal_esperado.exacto` | igualdad **exacta** como `Decimal` (no solo el truncado); `null` → sin total |
| `aetotal_esperado.cae` | igualdad del truncado (INT-06) |
| `aetotal_esperado.provisional` | igualdad (caso B) |
| `reglas_falladas_esperadas` | **igualdad de conjuntos**: sobra una o falta una y el caso falla, aunque
  el veredicto coincida |
| `reglas_no_evaluables_esperadas` | **subconjunto** de las obtenidas; los extras se anotan, no fallan |
| `interpretaciones_esperadas` | **subconjunto** de las aplicadas (`ADR-002` §6.5: hoy se citan las de
  toda regla evaluada) |

**Fecha de evaluacion**: la que declara el ground truth (`fecha_evaluacion`), no la del dia, para que la
matriz sea reproducible manana. Si el ground truth no la declara, se usa la de hoy.

**Codigos de salida**: `0` si todos los casos cuadran y el caso A da exactamente 305.829,6 kWh/año; `1` si
algun caso difiere o el caso A no da esa cifra; `2` si no se puede evaluar (falta ground truth, la spec no
carga, la carpeta no se lee).

Opciones: `--sin-ocr` (como un clon sin `tesseract`, `docs/05` §8.2) · `--caso A` (uno solo, por su id o por
el nombre de la carpeta) · `--json <ruta>` (el mismo resumen para una maquina) · `--informes` /
`--sin-informes`.

Solo depende de `engine/` y de la biblioteca estandar. **No importa `generator/`**: el ground truth se lee
del disco, como lo leeria cualquiera que clone el repositorio.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

from engine.informe import a_json, a_markdown, miles, texto_decimal
from engine.ingesta import ErrorIngesta
from engine.motor import Actuacion, ErrorMotor, procesar_actuacion, registro_cargado
from engine.reglas import ErrorReglas
from engine.spec_registry import ErrorCargaSpec

RAIZ = Path(__file__).resolve().parent
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_GROUND_TRUTH = CARPETA_CASOS / "_resultados_esperados"
CARPETA_INFORMES = RAIZ / "informes"
PATRON_CASOS = "EXP001-*"

#: Criterio de aceptacion de la Fase 0 (`CLAUDE.md` §5, `docs/05` §1 y §2.3). No es un valor calculado aqui:
#: es la cifra que el Engine 0.1 produjo y que la reconstruccion tiene que reproducir al ultimo decimal.
CASO_DE_REFERENCIA = "A"
AETOTAL_DE_REFERENCIA = Decimal("305829.6")

CODIGO_OK = 0
CODIGO_DIFERENCIAS = 1
CODIGO_ERROR = 2

SIN_DATO = "—"

COLUMNAS = (
    ("caso", "Caso"),
    ("esperado", "Esperado"),
    ("obtenido", "Obtenido"),
    ("cae", "CAE (kWh)"),
    ("documentos", "Docs"),
    ("datos_con_evidencia", "Datos ev."),
    ("extraccion", "Extraccion"),
    ("segundos", "Seg."),
)
#: Columnas que se alinean a la derecha por ser numericas.
DERECHA = {"cae", "documentos", "datos_con_evidencia", "extraccion", "segundos"}


class ErrorEvaluacion(Exception):
    """No se puede evaluar el banco (falta ground truth, la carpeta no existe, la spec no carga)."""


# ---------------------------------------------------------------------------
# Lectura del banco de pruebas
# ---------------------------------------------------------------------------


def carpetas_de_casos(patron: str = PATRON_CASOS) -> list[Path]:
    """Las carpetas de actuacion del banco, en orden alfabetico (A, B, … G)."""
    if not CARPETA_CASOS.is_dir():
        raise ErrorEvaluacion(f"no existe la carpeta de casos {CARPETA_CASOS}")
    return sorted(p for p in CARPETA_CASOS.glob(patron) if p.is_dir())


def leer_ground_truth(carpeta: Path) -> dict:
    ruta = CARPETA_GROUND_TRUTH / f"{carpeta.name}.json"
    if not ruta.is_file():
        raise ErrorEvaluacion(f"falta el ground truth de {carpeta.name}: {ruta}")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErrorEvaluacion(f"no se puede leer el ground truth {ruta}: {exc}") from exc
    if not isinstance(datos, Mapping):
        raise ErrorEvaluacion(f"el ground truth {ruta} no es un objeto JSON")
    return dict(datos)


def fecha_de(esperado: Mapping[str, object]) -> date:
    texto = esperado.get("fecha_evaluacion")
    if isinstance(texto, str) and texto:
        return date.fromisoformat(texto)
    return date.today()


def decimal_o_none(valor: object) -> Decimal | None:
    """El ground truth guarda los numeros como cadena para que `Decimal` los lea sin pasar por `float`."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, str) and valor.strip():
        return Decimal(valor)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return Decimal(valor)
    raise ErrorEvaluacion(f"valor no interpretable como Decimal: {valor!r}")


# ---------------------------------------------------------------------------
# Metricas de la fila (las columnas de `docs/05` §1)
# ---------------------------------------------------------------------------


def datos_consolidados(actuacion: Actuacion) -> list:
    """Todos los datos consolidados: los de nivel actuacion y los de cada unidad."""
    consolidada = actuacion.consolidada
    de_unidades = [dato for datos in consolidada.unidades.values() for dato in datos.values()]
    return list(consolidada.variables.values()) + de_unidades


def n_datos_con_evidencia(actuacion: Actuacion) -> int:
    """Datos consolidados con al menos una evidencia con cita literal (`docs/05` §1, columna 'Datos')."""
    return sum(
        1
        for dato in datos_consolidados(actuacion)
        if any(getattr(e, "texto_literal", None) for e in dato.evidencias)
    )


def variables_de_calculo(actuacion: Actuacion) -> list[str]:
    """Las entradas que la spec exige al consolidador (`Plan.entradas_requeridas`), en orden estable.

    En IND240 v1.1 son seis por motor —PM, N1, N2, h_antes, h_despues, P_prom—, la lista que `docs/05` §1
    deducia y que `ADR-002` §3 fija. No hay ningun nombre de la ficha escrito aqui: sale del plan de calculo.
    """
    return sorted(actuacion.spec.plan.entradas_requeridas)


def extraccion(actuacion: Actuacion) -> tuple[int, int]:
    """(variables de calculo con evidencia y valor consumido, variables de calculo esperadas)."""
    variables = variables_de_calculo(actuacion)
    unidades = actuacion.consolidada.unidades
    esperadas = len(variables) * len(unidades)
    con_evidencia = 0
    for datos in unidades.values():
        for nombre in variables:
            dato = datos.get(nombre)
            if dato is not None and dato.evidencias and dato.valor_consumido is not None:
                con_evidencia += 1
    return con_evidencia, esperadas


def n_ficheros(actuacion: Actuacion) -> int:
    """Ficheros entregados: las partes de un PDF combinado no cuentan como documentos aparte."""
    return sum(1 for doc in actuacion.documentos if not doc.es_parte)


# ---------------------------------------------------------------------------
# Comparacion con el ground truth
# ---------------------------------------------------------------------------


def _lista_de_ids(valor: object, campo: str) -> list[str]:
    if valor is None:
        return []
    if not isinstance(valor, Sequence) or isinstance(valor, str):
        raise ErrorEvaluacion(f"{campo} deberia ser una lista de ids, y es {valor!r}")
    return [str(v) for v in valor]


#: Maximo de ids que se listan en una nota antes de resumir (el caso D deja 23 reglas NO_EVALUABLE).
MAXIMO_EN_NOTA = 6


def _texto_conjunto(ids: Iterable[str], maximo: int | None = None) -> str:
    ordenados = sorted(ids)
    if not ordenados:
        return "(ninguna)"
    if maximo is not None and len(ordenados) > maximo:
        return ", ".join(ordenados[:maximo]) + f", … (+{len(ordenados) - maximo})"
    return ", ".join(ordenados)


def comparar(actuacion: Actuacion, esperado: Mapping[str, object]) -> list[str]:
    """Las diferencias del caso, una por linea. Lista vacia = el caso cuadra."""
    diferencias: list[str] = []

    veredicto_esperado = str(esperado.get("veredicto_esperado", ""))
    if actuacion.veredicto != veredicto_esperado:
        diferencias.append(f"veredicto: esperado {veredicto_esperado}, obtenido {actuacion.veredicto}")

    ahorro = esperado.get("aetotal_esperado") or {}
    if not isinstance(ahorro, Mapping):
        raise ErrorEvaluacion(f"aetotal_esperado deberia ser un objeto, y es {ahorro!r}")
    diferencias += _comparar_ahorro(actuacion, ahorro)
    diferencias += _comparar_reglas(actuacion, esperado)

    esperadas_int = _lista_de_ids(esperado.get("interpretaciones_esperadas"), "interpretaciones_esperadas")
    aplicadas = set(actuacion.evaluacion.interpretaciones_aplicadas)
    faltan_int = sorted(set(esperadas_int) - aplicadas)
    if faltan_int:
        diferencias.append(f"interpretaciones esperadas que no se aplicaron: {_texto_conjunto(faltan_int)}")
    return diferencias


def _comparar_ahorro(actuacion: Actuacion, ahorro: Mapping[str, object]) -> list[str]:
    diferencias: list[str] = []
    calculo = actuacion.calculo
    total = calculo.total if calculo is not None else None
    total_cae = calculo.total_cae if calculo is not None else None
    provisional = bool(calculo.provisional) if calculo is not None else False

    exacto = decimal_o_none(ahorro.get("exacto"))
    if exacto is None and total is not None:
        diferencias.append(f"AETOTAL: no debia publicarse ninguno y se obtuvo {texto_decimal(total)}")
    elif exacto is not None and total is None:
        diferencias.append(f"AETOTAL: esperado {texto_decimal(exacto)} y no se calculo ninguno")
    elif exacto is not None and total is not None and total != exacto:
        diferencias.append(
            f"AETOTAL exacto: esperado {texto_decimal(exacto)}, obtenido {texto_decimal(total)}"
        )

    cae_esperado = ahorro.get("cae")
    if cae_esperado != total_cae:
        diferencias.append(f"AETOTAL truncado: esperado {cae_esperado}, obtenido {total_cae}")

    if bool(ahorro.get("provisional", False)) != provisional:
        diferencias.append(
            f"provisional: esperado {bool(ahorro.get('provisional', False))}, obtenido {provisional}"
        )
    return diferencias


def _comparar_reglas(actuacion: Actuacion, esperado: Mapping[str, object]) -> list[str]:
    diferencias: list[str] = []
    falladas = set(actuacion.evaluacion.falladas)
    falladas_esperadas = set(_lista_de_ids(esperado.get("reglas_falladas_esperadas"), "reglas_falladas"))
    if falladas != falladas_esperadas:
        sobran = sorted(falladas - falladas_esperadas)
        faltan = sorted(falladas_esperadas - falladas)
        diferencias.append(
            f"reglas FALLA: esperadas {_texto_conjunto(falladas_esperadas)}, "
            f"obtenidas {_texto_conjunto(falladas)}"
        )
        for id_regla in sobran:
            regla = actuacion.evaluacion.resultado(id_regla)
            motivo = regla.motivo or regla.descripcion
            diferencias.append(f"  falla de mas {id_regla} ({regla.severidad}, fase {regla.fase}): {motivo}")
        for id_regla in faltan:
            obtenido = _resultado_de(actuacion, id_regla)
            diferencias.append(f"  no falla {id_regla}: se obtuvo {obtenido}")

    no_evaluables = set(actuacion.evaluacion.no_evaluables)
    esperadas_ne = set(_lista_de_ids(esperado.get("reglas_no_evaluables_esperadas"), "reglas_no_evaluables"))
    faltan_ne = sorted(esperadas_ne - no_evaluables)
    if faltan_ne:
        for id_regla in faltan_ne:
            diferencias.append(
                f"NO_EVALUABLE esperada {id_regla}: se obtuvo {_resultado_de(actuacion, id_regla)}"
            )
    return diferencias


def _resultado_de(actuacion: Actuacion, id_regla: str) -> str:
    try:
        regla = actuacion.evaluacion.resultado(id_regla)
    except KeyError:
        return "no evaluada (la spec no la contiene)"
    return regla.resultado.value


def notas(actuacion: Actuacion, esperado: Mapping[str, object]) -> list[str]:
    """Observaciones que **no** hacen fallar el caso: extras de lo que se compara por inclusion."""
    salida: list[str] = []
    esperadas_ne = set(_lista_de_ids(esperado.get("reglas_no_evaluables_esperadas"), "reglas_no_evaluables"))
    extras_ne = sorted(set(actuacion.evaluacion.no_evaluables) - esperadas_ne)
    if extras_ne:
        salida.append(f"NO_EVALUABLE ademas de las esperadas: {_texto_conjunto(extras_ne, MAXIMO_EN_NOTA)}")
    esperadas_int = set(_lista_de_ids(esperado.get("interpretaciones_esperadas"), "interpretaciones"))
    extras_int = sorted(set(actuacion.evaluacion.interpretaciones_aplicadas) - esperadas_int)
    if extras_int:
        salida.append(
            "interpretaciones citadas ademas de las esperadas: "
            f"{_texto_conjunto(extras_int, MAXIMO_EN_NOTA)} "
            "(ADR-002 §6.5: se comparan como subconjunto)"
        )
    return salida


# ---------------------------------------------------------------------------
# Evaluacion de un caso
# ---------------------------------------------------------------------------


def texto_cae(actuacion: Actuacion) -> str:
    calculo = actuacion.calculo
    if calculo is None or calculo.total_cae is None:
        return SIN_DATO
    texto = miles(calculo.total_cae)
    return f"{texto} (prov.)" if calculo.provisional else texto


def evaluar_caso(
    carpeta: Path, *, ocr: bool = True, registro=None, escribir_informes: bool = True
) -> dict[str, object]:
    """Procesa una carpeta, la compara con su ground truth y devuelve la fila mas el detalle."""
    esperado = leer_ground_truth(carpeta)
    inicio = time.perf_counter()
    actuacion = procesar_actuacion(carpeta, fecha_evaluacion=fecha_de(esperado), ocr=ocr, registro=registro)
    segundos = time.perf_counter() - inicio

    diferencias = comparar(actuacion, esperado)
    con_evidencia, esperadas = extraccion(actuacion)
    calculo = actuacion.calculo
    informes = escribir_informes_de(actuacion) if escribir_informes else {}

    return {
        "caso": str(esperado.get("id") or carpeta.name),
        "carpeta": carpeta.name,
        "esperado": str(esperado.get("veredicto_esperado", "")),
        "obtenido": actuacion.veredicto,
        "veredicto_ok": actuacion.veredicto == str(esperado.get("veredicto_esperado", "")),
        "cae": texto_cae(actuacion),
        "aetotal_exacto": texto_decimal(calculo.total) if calculo and calculo.total is not None else None,
        "aetotal_cae": calculo.total_cae if calculo is not None else None,
        "provisional": bool(calculo.provisional) if calculo is not None else False,
        "documentos": n_ficheros(actuacion),
        "datos_con_evidencia": n_datos_con_evidencia(actuacion),
        "extraccion": f"{con_evidencia}/{esperadas}",
        "segundos": round(segundos, 1),
        "reglas_falladas": sorted(actuacion.evaluacion.falladas),
        "diferencias": diferencias,
        "notas": notas(actuacion, esperado),
        "ok": not diferencias,
        "informes": informes,
    }


def escribir_informes_de(actuacion: Actuacion, carpeta: Path = CARPETA_INFORMES) -> dict[str, str]:
    """Informe markdown y JSON del caso en `informes/` (`docs/01` §3.10: la carpeta esta en `.gitignore`)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_md = carpeta / f"{actuacion.id}.md"
    ruta_json = carpeta / f"{actuacion.id}.json"
    ruta_md.write_text(a_markdown(actuacion), encoding="utf-8")
    ruta_json.write_text(json.dumps(a_json(actuacion), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"markdown": str(ruta_md), "json": str(ruta_json)}


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------


def tabla(filas: Sequence[Mapping[str, object]]) -> str:
    """La matriz de `docs/05` §1, alineada, en texto plano."""
    cabecera = [titulo for _, titulo in COLUMNAS]
    cuerpo = [[str(fila.get(clave, SIN_DATO)) for clave, _ in COLUMNAS] for fila in filas]
    anchos = [
        max(len(cabecera[i]), *(len(c[i]) for c in cuerpo)) if cuerpo else len(cabecera[i])
        for i in range(len(COLUMNAS))
    ]

    def linea(celdas: Sequence[str]) -> str:
        partes = []
        for i, (clave, _) in enumerate(COLUMNAS):
            partes.append(celdas[i].rjust(anchos[i]) if clave in DERECHA else celdas[i].ljust(anchos[i]))
        return "  ".join(partes).rstrip()

    lineas = [linea(cabecera), "  ".join("-" * a for a in anchos)]
    for i, celdas in enumerate(cuerpo):
        marca = "" if filas[i].get("ok") else "   <-- DIFIERE"
        lineas.append(linea(celdas) + marca)
    return "\n".join(lineas)


def detalle(filas: Sequence[Mapping[str, object]]) -> list[str]:
    """Las diferencias de cada caso que falla, regla a regla, para que sirva de diagnostico."""
    lineas: list[str] = []
    for fila in filas:
        diferencias = fila.get("diferencias") or []
        if not diferencias:
            continue
        lineas.append("")
        lineas.append(f"Caso {fila['caso']} ({fila['carpeta']}): {len(diferencias)} diferencia(s)")
        lineas += [f"  - {d}" if not d.startswith("  ") else f"  {d}" for d in diferencias]
    return lineas


def resumen(filas: Sequence[Mapping[str, object]]) -> list[str]:
    """Las lineas finales: la cuenta de veredictos, la de casos y el criterio de aceptacion del caso A."""
    total = len(filas)
    veredictos = sum(1 for f in filas if f.get("veredicto_ok"))
    completos = sum(1 for f in filas if f.get("ok"))
    lineas = [
        f"{veredictos}/{total} veredictos correctos",
        f"{completos}/{total} casos sin diferencias (veredicto, AETOTAL exacto y reglas falladas)",
    ]
    referencia = next((f for f in filas if f["caso"] == CASO_DE_REFERENCIA), None)
    if referencia is None:
        lineas.append(
            f"caso {CASO_DE_REFERENCIA} no evaluado: no se comprueba el criterio de aceptacion de la Fase 0"
        )
    else:
        obtenido = referencia.get("aetotal_exacto")
        cumple = obtenido is not None and Decimal(str(obtenido)) == AETOTAL_DE_REFERENCIA
        estado = "OK" if cumple else "NO CUMPLE"
        lineas.append(
            f"caso {CASO_DE_REFERENCIA} = {obtenido or SIN_DATO} kWh/año "
            f"(criterio de la Fase 0: {texto_decimal(AETOTAL_DE_REFERENCIA)}) → {estado}"
        )
    return lineas


def referencia_cumple(filas: Sequence[Mapping[str, object]]) -> bool:
    """`True` si el caso A da exactamente 305.829,6 (o si no se ha evaluado el caso A)."""
    referencia = next((f for f in filas if f["caso"] == CASO_DE_REFERENCIA), None)
    if referencia is None:
        return True
    obtenido = referencia.get("aetotal_exacto")
    return obtenido is not None and Decimal(str(obtenido)) == AETOTAL_DE_REFERENCIA


def avisos_de_carga(registro: object) -> list[str]:
    """Los avisos de carga de las specs activas, a la vista.

    Un aviso de carga es el Spec Registry diciendo que hay algo que **no puede comprobar solo**: una regla
    bloqueante cuya carencia no sabe que este recogida, una precondicion en prosa que delega en el motor.
    Hasta la auditoria del 20/09/2026 no los imprimia nadie, y los dos defectos mas serios que encontro
    (H1 y H3) estaban senalados ahi desde F0.4. Quien rompe la puerta es
    `tests/test_avisos_carga.py`, que compara la lista contra una linea base declarada; esto solo los pone
    donde se leen.
    """
    lineas: list[str] = []
    for codigo in getattr(registro, "codigos", list)():
        for version in registro.versiones(codigo):
            spec = registro.obtener(codigo, version)
            for aviso in spec.avisos_carga:
                lineas.append(f"  aviso de carga [{codigo} v{version}]: {aviso}")
    if lineas:
        lineas.insert(
            0,
            f"{len(lineas)} aviso(s) de carga de las specs activas (declarados en "
            f"tests/test_avisos_carga.py; uno nuevo rompe la puerta):",
        )
    return lineas


def codigo_de_salida(filas: Sequence[Mapping[str, object]]) -> int:
    if not filas:
        return CODIGO_ERROR
    if any(not f.get("ok") for f in filas) or not referencia_cumple(filas):
        return CODIGO_DIFERENCIAS
    return CODIGO_OK


def resumen_json(filas: Sequence[Mapping[str, object]], *, ocr: bool) -> dict[str, object]:
    return {
        "generado": date.today().isoformat(),
        "ocr": ocr,
        "casos": [{k: v for k, v in fila.items() if k != "informes"} for fila in filas],
        "veredictos_correctos": sum(1 for f in filas if f.get("veredicto_ok")),
        "casos_sin_diferencias": sum(1 for f in filas if f.get("ok")),
        "total": len(filas),
        "caso_de_referencia": CASO_DE_REFERENCIA,
        "aetotal_de_referencia": texto_decimal(AETOTAL_DE_REFERENCIA),
        "referencia_cumple": referencia_cumple(filas),
        "codigo_de_salida": codigo_de_salida(filas),
    }


# ---------------------------------------------------------------------------
# Linea de ordenes
# ---------------------------------------------------------------------------


def seleccionar(carpetas: Sequence[Path], caso: str | None) -> list[Path]:
    """Filtra por id de caso (`A`) o por nombre de carpeta (`EXP001-A_completo`)."""
    if not caso:
        return list(carpetas)
    aguja = caso.strip().lower()
    elegidas = [
        c for c in carpetas if c.name.lower() == aguja or c.name.lower().startswith(f"exp001-{aguja}_")
    ]
    if not elegidas:
        disponibles = ", ".join(c.name for c in carpetas)
        raise ErrorEvaluacion(f"no hay ningun caso {caso!r}; hay: {disponibles}")
    return elegidas


def analizador() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python evaluar_casos.py",
        description="Matriz esperado/obtenido de los casos A-G (docs/05 §8.1).",
    )
    parser.add_argument(
        "--sin-ocr",
        action="store_true",
        dest="sin_ocr",
        help="no reconocer texto en escaneos ni fotos (como un clon sin tesseract)",
    )
    parser.add_argument("--caso", default=None, help="evalua solo este caso (A..G o nombre de carpeta)")
    parser.add_argument("--json", type=Path, default=None, dest="json_", help="escribe el resumen en JSON")
    informes = parser.add_mutually_exclusive_group()
    informes.add_argument(
        "--informes",
        action="store_true",
        default=True,
        dest="informes",
        help="escribe el informe markdown y JSON de cada caso en informes/ (por defecto)",
    )
    informes.add_argument(
        "--sin-informes",
        action="store_false",
        dest="informes",
        help="no escribe ningun informe (solo la matriz por pantalla)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = analizador().parse_args(argv)
    ocr = not args.sin_ocr
    try:
        carpetas = seleccionar(carpetas_de_casos(), args.caso)
        registro = registro_cargado()
        filas = [
            evaluar_caso(c, ocr=ocr, registro=registro, escribir_informes=args.informes) for c in carpetas
        ]
    except (ErrorEvaluacion, ErrorMotor, ErrorIngesta, ErrorCargaSpec, ErrorReglas, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return CODIGO_ERROR

    print(f"Banco de pruebas CAE Engine — {len(filas)} caso(s), OCR {'activado' if ocr else 'desactivado'}")
    print()
    print(tabla(filas))
    print()
    print(
        "Datos ev. = datos consolidados con cita literal · "
        "Extraccion = variables de calculo con evidencia / esperadas (entradas del plan x unidades)"
    )
    for fila in filas:
        for nota in fila.get("notas") or []:
            print(f"  nota [{fila['caso']}]: {nota}")
    for linea in detalle(filas):
        print(linea)
    print()
    for linea in resumen(filas):
        print(linea)
    for linea in avisos_de_carga(registro_cargado()):
        print(linea)
    if args.informes and filas:
        print(f"informes en {CARPETA_INFORMES}")

    if args.json_ is not None:
        destino = Path(args.json_)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(resumen_json(filas, ocr=ocr), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"resumen JSON: {destino}")
    return codigo_de_salida(filas)


if __name__ == "__main__":  # pragma: no cover - punto de entrada
    sys.exit(main())
