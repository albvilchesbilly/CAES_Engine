"""Orquestador lineal y sincrono de la Fase 0 (S3 de `docs/03` §3.2, `docs/01` §3.3).

Lleva la carpeta de documentos de una actuacion al veredicto, en un solo hilo y sin ningun LLM:

    ingesta → clasificacion → extraccion → consolidacion → reglas (que disparan el calculo por dentro)

Este modulo **no decide nada**: no calcula, no ordena fases, no elige valores. Encadena los modulos que ya
toman esas decisiones y agrega el resultado en una `Actuacion` (el vocabulario de la plataforma oficial,
`docs/03` §5.1; `Expediente` queda reservado para la agregacion oficial). En el Sprint 3 pasara a emitir
eventos sin cambiar esta interfaz publica (`docs/06` §1).

Decisiones de este paso (F0.10):

- **Una sola llamada al motor de reglas.** `evaluar_actuacion` dispara el calculo por dentro cuando procede
  (fases de `docs/04` §5.1, calculo provisional incluido). `motor.py` nunca llama a `calcular`.
- **`fecha_evaluacion` es `solicitud.fecha`** (INT-10, propuesta; `ADR-002` §2.3): en prevalidacion no hay
  solicitud presentada. Por defecto, la fecha del dia. El informe lo dice como criterio, no como dato leido.
- **La extraccion recorre los documentos legibles**, es decir, las partes de un PDF combinado y no el
  combinado (`ingesta.documentos_legibles`); el combinado se conserva en `Actuacion.documentos` con su huella.
- **`id` = nombre de la carpeta de la actuacion** (`codigo_identificativo_propio` es el mismo valor, `docs/03`
  §5.2: clave de reconciliacion con la plataforma). En la Fase 0 no hay alta de actuacion (P0) ni tenant, asi
  que la unica identidad estable disponible es la carpeta. En el Sprint 3 lo fija la maquina de estados.
- **Ninguna ficha se nombra aqui.** `spec_id=None` significa "la unica ficha activa del registro"; con varias
  cargadas hay que decir cual. Un codigo de ficha escrito en `engine/` seria un defecto del marco (regla de
  oro 4; lo comprueba `tests/test_ingesta.py::test_engine_sin_ramas_por_ficha`).
- **`tiempos` es telemetria**, en segundos, con `float` de `time.perf_counter`. No toca ninguna magnitud del
  ahorro: todo lo que entra en la formula es `Decimal` y lo produce `engine/calculo.py`.

Nada de `eval`, `exec` ni `compile`. No importa de `agentes/`, `salida/`, `generator/` ni `tests/`.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from engine.calculo import ResultadoCalculo
from engine.clasificacion import clasificar_todos
from engine.correcciones import Correccion, a_evidencias
from engine.correcciones import validar as validar_correcciones
from engine.evidencias import ActuacionConsolidada, consolidar
from engine.extraccion import extraer_todos
from engine.ingesta import Documento, avisos_de, documentos_legibles, ingestar
from engine.reglas import Evaluacion, evaluar_actuacion
from engine.spec_registry import Spec, SpecRegistry

#: Version del Engine que produjo el resultado (la del paquete instalado; respaldo para un clon sin instalar).
VERSION_ENGINE_RESPALDO = "0.1.0"

try:  # pragma: no cover - depende del entorno, no del comportamiento
    VERSION_ENGINE = version("cae-engine")
except PackageNotFoundError:  # pragma: no cover
    VERSION_ENGINE = VERSION_ENGINE_RESPALDO


#: Etapas cronometradas, en el orden en que se ejecutan.
ETAPAS = ("spec", "ingesta", "clasificacion", "extraccion", "consolidacion", "evaluacion", "total")


class ErrorMotor(Exception):
    """El motor no puede procesar la carpeta (no existe, no es carpeta, o la spec no carga)."""


@dataclass(frozen=True)
class IdentidadSpec:
    """Ficha de identidad de la spec con la que se evaluo: lo que hace reproducible un informe."""

    codigo: str
    version_ficha: str
    version_spec: str
    hash_spec: str
    hash_reglas: str

    @classmethod
    def de(cls, spec: Spec) -> IdentidadSpec:
        return cls(
            codigo=spec.codigo,
            version_ficha=spec.version_ficha,
            version_spec=spec.version_spec,
            hash_spec=spec.hash_spec,
            hash_reglas=spec.hash_reglas,
        )

    def a_dict(self) -> dict[str, object]:
        return {
            "codigo": self.codigo,
            "version_ficha": self.version_ficha,
            "version_spec": self.version_spec,
            "hash_spec": self.hash_spec,
            "hash_reglas": self.hash_reglas,
        }


@dataclass
class Actuacion:
    """La unidad de trabajo procesada de extremo a extremo (`docs/03` §5.1).

    Agrega lo que produjo cada etapa: los documentos con su huella, la consolidacion (tres capas por dato),
    la evaluacion (reglas, veredicto y calculo) y la telemetria. No añade ningun criterio propio.
    """

    id: str
    codigo_identificativo_propio: str
    carpeta: Path
    fecha_evaluacion: date
    spec: Spec
    documentos: list[Documento]
    consolidada: ActuacionConsolidada
    evaluacion: Evaluacion
    avisos: list[str] = field(default_factory=list)
    tiempos: dict[str, float] = field(default_factory=dict)
    version_engine: str = VERSION_ENGINE

    @property
    def veredicto(self) -> str:
        return self.evaluacion.veredicto

    @property
    def calculo(self) -> ResultadoCalculo | None:
        return self.evaluacion.calculo

    @property
    def identidad_spec(self) -> IdentidadSpec:
        return IdentidadSpec.de(self.spec)

    @property
    def unidades(self) -> Mapping[str, object]:
        return self.consolidada.unidades

    def a_dict(self) -> dict[str, object]:
        """Cabecera serializable de la actuacion; el informe completo lo compone `engine.informe`."""
        return {
            "id": self.id,
            "codigo_identificativo_propio": self.codigo_identificativo_propio,
            "carpeta": str(self.carpeta),
            "fecha_evaluacion": self.fecha_evaluacion.isoformat(),
            "version_engine": self.version_engine,
            "spec": self.identidad_spec.a_dict(),
            "veredicto": self.veredicto,
            "n_documentos": len(self.documentos),
            "n_unidades": self.consolidada.n_unidades,
            "tiempos": dict(self.tiempos),
        }


def identidad_de_carpeta(carpeta: Path) -> str:
    """Identidad de la actuacion a partir de la carpeta (ver cabecera: en la Fase 0 no hay alta de P0)."""
    nombre = Path(carpeta).resolve().name
    if not nombre:
        raise ErrorMotor(f"no se puede derivar la identidad de la actuacion de {carpeta}")
    return nombre


def ficha_unica(registro: SpecRegistry) -> str:
    """La unica ficha activa del registro. Con varias, el llamante tiene que decir cual (sin adivinar)."""
    codigos = registro.codigos()
    if len(codigos) == 1:
        return codigos[0]
    if not codigos:
        raise ErrorMotor("no hay ninguna ficha activa en la carpeta de specs")
    raise ErrorMotor(f"hay varias fichas activas {codigos}: indica cual con spec_id")


def registro_cargado(registro: SpecRegistry | None = None) -> SpecRegistry:
    """El registro que se le pasa, o uno nuevo con las specs activas cargadas (nunca `spec/propuestas/`)."""
    registro = registro if registro is not None else SpecRegistry()
    if not registro.codigos():
        registro.cargar_todas()
    return registro


def procesar_actuacion(
    carpeta: Path,
    *,
    spec_id: str | None = None,
    fecha_evaluacion: date | None = None,
    ocr: bool = True,
    registro: SpecRegistry | None = None,
    correcciones: Sequence[Correccion] = (),
) -> Actuacion:
    """Procesa la carpeta de una actuacion y devuelve la `Actuacion` con su veredicto (ver cabecera).

    `spec_id` es el codigo de la ficha a aplicar; `None` toma la unica activa. `fecha_evaluacion` es tambien
    `solicitud.fecha` (INT-10). `ocr=False` desactiva el reconocimiento optico: el veredicto no debe depender
    de el (`docs/05` §8.2).

    `correcciones` son las decisiones humanas que se aplican a esta ejecucion (contrato C21 de `ADR-013`
    §3). **El motor no lee el log**: las recibe ya leidas, como datos planos, igual que `engine.seguimiento`
    recibe los estados de plataforma; quien tiene el log llama
    `procesar_actuacion(carpeta, correcciones=engine.correcciones.de_log(log))`. Vacio —lo normal— la
    ejecucion es identica a la de siempre, byte a byte.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise ErrorMotor(f"no es una carpeta de actuacion: {carpeta}")
    fecha = fecha_evaluacion or date.today()
    if not isinstance(fecha, date):
        raise ErrorMotor("fecha_evaluacion debe ser un datetime.date")

    tiempos: dict[str, float] = {}
    inicio_total = time.perf_counter()

    reloj = time.perf_counter()
    registro = registro_cargado(registro)
    spec = registro.obtener(spec_id or ficha_unica(registro), fecha=fecha)
    tiempos["spec"] = time.perf_counter() - reloj

    reloj = time.perf_counter()
    documentos = ingestar(carpeta, ocr=ocr)
    tiempos["ingesta"] = time.perf_counter() - reloj

    reloj = time.perf_counter()
    documentos = clasificar_todos(documentos, spec)
    tiempos["clasificacion"] = time.perf_counter() - reloj

    reloj = time.perf_counter()
    evidencias = extraer_todos(documentos, spec)
    if correcciones:
        # Una correccion humana es una evidencia mas (`ADR-013` §1): entra en el mismo monton, en orden, y
        # la consolidacion le da la precedencia. Aqui no se decide nada; solo se comprueba contra la ficha.
        evidencias = list(evidencias) + a_evidencias(validar_correcciones(correcciones, spec))
    tiempos["extraccion"] = time.perf_counter() - reloj

    reloj = time.perf_counter()
    consolidada = consolidar(evidencias, documentos_legibles(documentos), spec)
    consolidada.avisos = avisos_de(documentos) + consolidada.avisos
    tiempos["consolidacion"] = time.perf_counter() - reloj

    reloj = time.perf_counter()
    evaluacion = evaluar_actuacion(consolidada, spec, fecha_evaluacion=fecha)
    tiempos["evaluacion"] = time.perf_counter() - reloj

    tiempos["total"] = time.perf_counter() - inicio_total
    identidad = identidad_de_carpeta(carpeta)
    return Actuacion(
        id=identidad,
        codigo_identificativo_propio=identidad,
        carpeta=carpeta,
        fecha_evaluacion=fecha,
        spec=spec,
        documentos=documentos,
        consolidada=consolidada,
        evaluacion=evaluacion,
        avisos=list(evaluacion.avisos),
        tiempos={etapa: round(tiempos[etapa], 3) for etapa in ETAPAS if etapa in tiempos},
        version_engine=VERSION_ENGINE,
    )


__all__ = [
    "ETAPAS",
    "VERSION_ENGINE",
    "Actuacion",
    "ErrorMotor",
    "IdentidadSpec",
    "ficha_unica",
    "identidad_de_carpeta",
    "procesar_actuacion",
    "registro_cargado",
]
