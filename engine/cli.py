"""Linea de comandos del Engine (`docs/01` §3.3):

    python -m engine.cli <carpeta> [--md informe.md] [--json informe.json]
                         [--sin-ocr] [--fecha AAAA-MM-DD] [--ficha CODIGO] [--silencioso]

Sin `--md` ni `--json` escribe un resumen por la salida estandar. Con rutas, escribe los informes: una ruta
relativa se resuelve dentro de `informes/` (que esta en `.gitignore`, `docs/01` §3.10) y el directorio se
crea si falta; una ruta absoluta se respeta tal cual.

**Codigos de salida** (los consume `evaluar_casos.py` y cualquier automatismo):

| Codigo | Cuando |
|---|---|
| 0 | Veredicto `PREVALIDADO` o `SUBSANABLE`: la actuacion sigue su curso (con o sin subsanacion) |
| 1 | Veredicto `BLOQUEADO` o `NO_ELEGIBLE`: no se puede presentar tal cual |
| 2 | Error de carga o de lectura: la spec no carga, la carpeta no existe o no se puede leer |

Un veredicto desconocido (una spec futura con otros estados) tambien devuelve 1: el Engine nunca dice que
todo va bien ante algo que no sabe interpretar. `argparse` y `pathlib`; nada de `os.system`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from engine.informe import a_json, a_markdown, miles, motivo_sin_calculo, texto_decimal
from engine.ingesta import ErrorIngesta
from engine.motor import Actuacion, ErrorMotor, procesar_actuacion
from engine.reglas import (
    VEREDICTO_BLOQUEADO,
    VEREDICTO_NO_ELEGIBLE,
    VEREDICTO_PREVALIDADO,
    VEREDICTO_SUBSANABLE,
    ErrorReglas,
)
from engine.spec_registry import ErrorCargaSpec

#: Carpeta por defecto de los informes (relativa al directorio de trabajo; `docs/01` §3.10).
CARPETA_INFORMES = Path("informes")

CODIGO_OK = 0
CODIGO_VEREDICTO_NEGATIVO = 1
CODIGO_ERROR = 2

#: Veredictos que permiten seguir adelante. Cualquier otro devuelve `CODIGO_VEREDICTO_NEGATIVO`.
VEREDICTOS_OK = (VEREDICTO_PREVALIDADO, VEREDICTO_SUBSANABLE)
VEREDICTOS_NEGATIVOS = (VEREDICTO_BLOQUEADO, VEREDICTO_NO_ELEGIBLE)


def analizador() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m engine.cli",
        description="Prevalida la carpeta de una actuacion CAE y escribe su informe.",
    )
    parser.add_argument("carpeta", type=Path, help="carpeta con los documentos de la actuacion")
    parser.add_argument("--md", type=Path, default=None, help="ruta del informe markdown")
    parser.add_argument("--json", type=Path, default=None, dest="json_", help="ruta del informe JSON")
    parser.add_argument(
        "--sin-ocr",
        action="store_true",
        dest="sin_ocr",
        help="no reconocer texto en escaneos ni fotos (el veredicto no debe depender del OCR)",
    )
    parser.add_argument(
        "--fecha",
        default=None,
        help="fecha de evaluacion AAAA-MM-DD (por defecto, hoy); es tambien la fecha de solicitud",
    )
    parser.add_argument(
        "--ficha",
        default=None,
        help="codigo de la ficha CAE a aplicar (por defecto, la unica ficha activa)",
    )
    parser.add_argument("--silencioso", action="store_true", help="no escribir el resumen por pantalla")
    return parser


def leer_fecha(texto: str | None) -> date | None:
    if texto is None:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ErrorMotor(f"fecha invalida {texto!r}: se espera AAAA-MM-DD") from exc


def ruta_de_salida(ruta: Path, carpeta_informes: Path = CARPETA_INFORMES) -> Path:
    """Ruta absoluta tal cual; ruta relativa, dentro de `informes/`. El directorio se crea si falta."""
    destino = ruta if ruta.is_absolute() else carpeta_informes / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    return destino


def codigo_de_salida(veredicto: str) -> int:
    return CODIGO_OK if veredicto in VEREDICTOS_OK else CODIGO_VEREDICTO_NEGATIVO


def resumen(actuacion: Actuacion) -> str:
    """Resumen de una linea por dato, para quien ejecuta el comando sin pedir ficheros."""
    calculo = actuacion.calculo
    lineas = [
        f"Actuacion: {actuacion.id}  ({actuacion.carpeta})",
        f"Ficha: {actuacion.spec.codigo} v{actuacion.spec.version_ficha} "
        f"(version_spec {actuacion.spec.version_spec}, hash_reglas {actuacion.spec.hash_reglas[:12]}…)",
        f"Fecha de evaluacion: {actuacion.fecha_evaluacion.isoformat()}",
        f"Veredicto: {actuacion.veredicto}",
    ]
    if calculo is not None and calculo.total is not None:
        etiqueta = f"{actuacion.spec.plan.salida_total}: {texto_decimal(calculo.total)} kWh/año"
        if calculo.total_cae is not None:
            etiqueta += f"  (truncado: {miles(calculo.total_cae)} kWh)"
        if calculo.provisional:
            etiqueta += "  [provisional]"
        lineas.append(etiqueta)
    else:
        lineas.append(f"Sin ahorro publicable: {motivo_sin_calculo(actuacion)}")
    falladas = actuacion.evaluacion.falladas
    lineas.append(f"Reglas: {len(actuacion.evaluacion.resultados)} evaluadas, {len(falladas)} falladas")
    if falladas:
        lineas.append(f"Falladas: {', '.join(falladas)}")
    if actuacion.evaluacion.carencias:
        lineas.append("Carencias:")
        lineas += [f"  - [{c.get('id')}] {c.get('mensaje')}" for c in actuacion.evaluacion.carencias]
    if actuacion.avisos:
        lineas.append(f"Avisos: {len(actuacion.avisos)}")
    lineas.append(f"Tiempo total: {actuacion.tiempos.get('total', 0)} s")
    return "\n".join(lineas)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada. Devuelve el codigo de salida en lugar de terminar el proceso."""
    args = analizador().parse_args(argv)
    try:
        fecha = leer_fecha(args.fecha)
        actuacion = procesar_actuacion(
            args.carpeta,
            spec_id=args.ficha,
            fecha_evaluacion=fecha,
            ocr=not args.sin_ocr,
        )
    except (ErrorMotor, ErrorIngesta, ErrorCargaSpec, ErrorReglas, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return CODIGO_ERROR

    if args.md is not None:
        destino = ruta_de_salida(args.md)
        destino.write_text(a_markdown(actuacion), encoding="utf-8")
        if not args.silencioso:
            print(f"informe markdown: {destino}")
    if args.json_ is not None:
        destino = ruta_de_salida(args.json_)
        destino.write_text(
            json.dumps(a_json(actuacion), ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        if not args.silencioso:
            print(f"informe JSON: {destino}")
    if not args.silencioso:
        print(resumen(actuacion))
    return codigo_de_salida(actuacion.veredicto)


if __name__ == "__main__":  # pragma: no cover - punto de entrada
    sys.exit(main())
