"""`python -m generator.generar [--solo A] [--salida expedientes/]`: regenera los 7 casos y su ground truth.

Determinista: PDF con `invariant=1`, imágenes con fuente incluida y sin metadatos variables, xlsx con fechas
fijas. Dos ejecuciones producen los mismos bytes (lo comprueba `tests/test_generator.py`).

Ficheros por caso (A–F; los "por motor" se repiten con el nº de serie en el nombre):

    01_ficha_IND240_cumplimentada.pdf          05_certificado_instalador.pdf
    02_declaracion_responsable.pdf             06_registro_funcionamiento_<MTR>.xlsx   (por motor; no en B)
    03_factura.pdf                             07_registro_horas_previo_<MTR>.pdf      (por motor)
    04_informe_fotografico.pdf                 08_ficha_tecnica_motor_<MTR>.pdf        (por motor)
    11_convenio_cae.pdf                        09_ficha_tecnica_variador_<VSD>.pdf     (por motor)
                                               10_ficha_tecnica_equipo_accionado_<MTR>.pdf (por motor)

    A, C, D: 11 · B: 10 · E: 6 + 5×2 = 16 · F: 6 + 5×3 = 21

Caso G (mismos datos que A, 13 ficheros): `doc1.pdf` (ficha + declaración + convenio combinados), `doc2.pdf`
(factura), `doc3.pdf` (certificado), `doc4.pdf` (registro de horas previo), `doc5.pdf` (ficha técnica del
motor), `doc6.pdf` (ficha técnica del equipo), `scan.pdf` (ficha del variador escaneada y girada, sin texto),
`datos.xlsx` (registro renombrado), `foto1.jpg`..`foto4.jpg` (ANTES, DESPUÉS, placa, irrelevante) y
`notas.pdf` (acta de reunión irrelevante).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from engine.calculo import ResultadoCalculo
from engine.spec_registry import Spec
from generator import ground_truth
from generator.calculo_caso import calcular_caso, cargar_spec_activa
from generator.casos import todos_los_casos
from generator.documentos import (
    certificado_instalador,
    convenio_cae,
    declaracion_responsable,
    escaneo,
    factura,
    ficha_cumplimentada,
    ficha_tecnica_equipo,
    ficha_tecnica_motor,
    ficha_tecnica_variador,
    informe_fotografico,
    irrelevantes,
    registro,
    registro_horas_previo,
)
from generator.documentos.base import Seccion, construir_pdf
from generator.documentos.imagenes import foto_irrelevante, foto_motor, foto_placa
from generator.modelo_caso import Caso

RAIZ = Path(__file__).resolve().parents[1]
SALIDA_POR_DEFECTO = RAIZ / "expedientes"
CARPETA_RESULTADOS = "_resultados_esperados"


@dataclass
class Fichero:
    """Un fichero del paquete: bytes, tipo esperado y las secciones (con sus páginas) que contiene."""

    nombre: str
    contenido: bytes
    formato: str  # pdf | xlsx | imagen
    tipo: str | None  # tipo de documento de la spec; None si irrelevante; "combinado" si varios
    secciones: list[Seccion] = field(default_factory=list)
    subtipo: str | None = None  # fotos sueltas: foto_antes | foto_despues | placa | irrelevante
    num_serie_motor: str | None = None
    num_serie_variador: str | None = None
    irrelevante: bool = False
    descripcion_exif: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.contenido).hexdigest()

    @property
    def partes(self) -> list[dict[str, object]]:
        return [
            {"tipo": s.tipo, "pagina_inicio": s.pagina_inicio, "pagina_fin": s.pagina_fin}
            for s in self.secciones
        ]


@dataclass
class CasoGenerado:
    caso: Caso
    ficheros: list[Fichero]
    registros: dict[str, registro.RegistroGenerado]
    calculo: ResultadoCalculo
    ground_truth: dict

    def fichero(self, nombre: str) -> Fichero:
        for f in self.ficheros:
            if f.nombre == nombre:
                return f
        raise KeyError(nombre)

    def ficheros_de_tipo(self, tipo: str) -> list[Fichero]:
        return [f for f in self.ficheros if f.tipo == tipo or any(s.tipo == tipo for s in f.secciones)]


def _pdf(nombre: str, *secciones: Seccion, **kwargs: object) -> Fichero:
    contenido = construir_pdf(list(secciones))
    tipo = secciones[0].tipo if len(secciones) == 1 else "combinado"
    return Fichero(nombre, contenido, "pdf", tipo, list(secciones), **kwargs)  # type: ignore[arg-type]


def _secciones_comunes(caso: Caso, ahorro_cae: int, huellas: dict[str, str]) -> dict[str, Seccion]:
    ahorro_ficha = ahorro_cae if caso.variaciones.ficha_declara_ahorro else None
    return {
        "ficha": ficha_cumplimentada.seccion(caso, ahorro_ficha),
        "declaracion": declaracion_responsable.seccion(caso),
        "factura": factura.seccion(caso),
        "informe": informe_fotografico.seccion(caso),
        "certificado": certificado_instalador.seccion(caso, huellas),
        "convenio": convenio_cae.seccion(caso, ahorro_cae),
    }


def _ficheros_ordenados(
    caso: Caso, ahorro_cae: int, registros: dict[str, registro.RegistroGenerado]
) -> list[Fichero]:
    huellas = {serie: r.sha256_canonico for serie, r in registros.items()}
    s = _secciones_comunes(caso, ahorro_cae, huellas)
    ficheros = [
        _pdf("01_ficha_IND240_cumplimentada.pdf", s["ficha"]),
        _pdf("02_declaracion_responsable.pdf", s["declaracion"]),
        _pdf("03_factura.pdf", s["factura"]),
        _pdf("04_informe_fotografico.pdf", s["informe"]),
        _pdf("05_certificado_instalador.pdf", s["certificado"]),
    ]
    for m in caso.motores:
        serie = m.num_serie_motor
        if serie in registros:
            ficheros.append(
                Fichero(
                    caso.nombre_registro(m),
                    registros[serie].xlsx,
                    "xlsx",
                    registro_tipo(),
                    num_serie_motor=serie,
                    num_serie_variador=m.num_serie_variador,
                )
            )
        ficheros.append(
            _pdf(
                f"07_registro_horas_previo_{serie}.pdf",
                registro_horas_previo.seccion(caso, m),
                num_serie_motor=serie,
            )
        )
        ficheros.append(
            _pdf(f"08_ficha_tecnica_motor_{serie}.pdf", ficha_tecnica_motor.seccion(m), num_serie_motor=serie)
        )
        ficheros.append(
            _pdf(
                f"09_ficha_tecnica_variador_{m.num_serie_variador}.pdf",
                ficha_tecnica_variador.seccion(m),
                num_serie_motor=serie,
                num_serie_variador=m.num_serie_variador,
            )
        )
        ficheros.append(
            _pdf(
                f"10_ficha_tecnica_equipo_accionado_{serie}.pdf",
                ficha_tecnica_equipo.seccion(m),
                num_serie_motor=serie,
            )
        )
    ficheros.append(_pdf("11_convenio_cae.pdf", s["convenio"]))
    return ficheros


def registro_tipo() -> str:
    return "registro_funcionamiento"


def _ficheros_desordenados(
    caso: Caso, ahorro_cae: int, registros: dict[str, registro.RegistroGenerado]
) -> list[Fichero]:
    """Caso G: la misma información que A con nombres genéricos, PDF combinado, escaneo, fotos sueltas e
    irrelevantes."""
    if caso.n_motores != 1:
        raise ValueError("el caso desordenado está definido para un solo motor")
    m = caso.motores[0]
    serie = m.num_serie_motor
    huellas = {s: r.sha256_canonico for s, r in registros.items()}
    s = _secciones_comunes(caso, ahorro_cae, huellas)
    escaneado = escaneo.imagen_ficha_variador(m)
    fotos = (
        ("foto1.jpg", foto_motor(m, "ANTES"), "foto_antes", False),
        ("foto2.jpg", foto_motor(m, "DESPUES"), "foto_despues", False),
        ("foto3.jpg", foto_placa(m), "placa", False),
        ("foto4.jpg", foto_irrelevante(), "irrelevante", True),
    )
    ficheros = [
        _pdf("doc1.pdf", s["ficha"], s["declaracion"], s["convenio"]),
        _pdf("doc2.pdf", s["factura"]),
        _pdf("doc3.pdf", s["certificado"]),
        _pdf("doc4.pdf", registro_horas_previo.seccion(caso, m), num_serie_motor=serie),
        _pdf("doc5.pdf", ficha_tecnica_motor.seccion(m), num_serie_motor=serie),
        _pdf("doc6.pdf", ficha_tecnica_equipo.seccion(m), num_serie_motor=serie),
        Fichero(
            "scan.pdf",
            escaneo.pdf_escaneo(escaneado),
            "pdf",
            ficha_tecnica_variador.TIPO,
            subtipo="escaneo_girado",
            num_serie_motor=serie,
            num_serie_variador=m.num_serie_variador,
        ),
        Fichero(
            "datos.xlsx",
            registros[serie].xlsx,
            "xlsx",
            registro_tipo(),
            num_serie_motor=serie,
            num_serie_variador=m.num_serie_variador,
        ),
    ]
    for nombre, contenido, subtipo, irrelevante in fotos:
        ficheros.append(
            Fichero(
                nombre,
                contenido,
                "imagen",
                None if irrelevante else informe_fotografico.TIPO,
                subtipo=subtipo,
                num_serie_motor=None if irrelevante else serie,
                num_serie_variador=m.num_serie_variador if subtipo == "foto_despues" else None,
                irrelevante=irrelevante,
            )
        )
    ficheros.append(_pdf("notas.pdf", irrelevantes.seccion_notas(), irrelevante=True))
    return ficheros


def generar_caso(caso: Caso, spec: Spec | None = None) -> CasoGenerado:
    """Genera en memoria todos los ficheros y el ground truth de un caso a partir del modelo."""
    spec = spec or cargar_spec_activa()
    calculo = calcular_caso(caso, spec)
    if calculo.total_cae is None:
        raise RuntimeError(f"caso {caso.id}: el cálculo de referencia falló ({calculo.motivo_no_calculo})")
    registros: dict[str, registro.RegistroGenerado] = {}
    if not caso.variaciones.sin_registro:
        registros = {m.num_serie_motor: registro.generar_registro(caso, m) for m in caso.motores}
    if caso.variaciones.desordenado:
        ficheros = _ficheros_desordenados(caso, calculo.total_cae, registros)
    else:
        ficheros = _ficheros_ordenados(caso, calculo.total_cae, registros)
    nombres = [f.nombre for f in ficheros]
    if len(set(nombres)) != len(nombres):
        raise RuntimeError(f"caso {caso.id}: nombres de fichero repetidos")
    generado = CasoGenerado(caso, ficheros, registros, calculo, {})
    generado.ground_truth = ground_truth.construir(generado, spec)
    return generado


def escribir_caso(generado: CasoGenerado, salida: Path) -> Path:
    carpeta = salida / generado.caso.carpeta
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    for f in generado.ficheros:
        (carpeta / f.nombre).write_bytes(f.contenido)
    resultados = salida / CARPETA_RESULTADOS
    resultados.mkdir(parents=True, exist_ok=True)
    ruta_json = resultados / f"{generado.caso.carpeta}.json"
    ruta_json.write_text(
        json.dumps(generado.ground_truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return carpeta


def generar_todos(salida: Path = SALIDA_POR_DEFECTO, solo: str | None = None) -> list[CasoGenerado]:
    spec = cargar_spec_activa()
    generados = []
    for caso in todos_los_casos():
        if solo and caso.id != solo.upper():
            continue
        generado = generar_caso(caso, spec)
        escribir_caso(generado, salida)
        generados.append(generado)
    return generados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenera los casos sintéticos y su ground truth.")
    parser.add_argument("--solo", help="Genera solo el caso indicado (A..G)")
    parser.add_argument(
        "--salida", type=Path, default=SALIDA_POR_DEFECTO, help="Carpeta de salida (expedientes/)"
    )
    args = parser.parse_args(argv)
    generados = generar_todos(args.salida, args.solo)
    for g in generados:
        gt = g.ground_truth["aetotal_esperado"]
        print(
            f"{g.caso.carpeta}: {len(g.ficheros)} ficheros, veredicto {g.caso.veredicto_esperado}, "
            f"AETOTAL {gt['exacto']} (cae {gt['cae']}{', provisional' if gt['provisional'] else ''})"
        )
    return 0 if generados else 1


if __name__ == "__main__":
    sys.exit(main())
