"""Puente con `engine/calculo.py`: el ground truth se calcula con el motor de cálculo, nunca a mano."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from engine.calculo import ResultadoCalculo, calcular
from engine.spec_registry import Spec, cargar_spec
from generator.modelo_caso import Caso, Motor

RAIZ = Path(__file__).resolve().parents[1]
SPEC_ACTIVA = RAIZ / "spec" / "IND240_v1.1.yaml"

VARIABLES_ENTRADA = ("PM", "N1", "N2", "h_antes", "h_despues", "P_prom")


def cargar_spec_activa() -> Spec:
    return cargar_spec(SPEC_ACTIVA)


def entradas_motor(motor: Motor, h_despues: Decimal | None = None) -> dict[str, Decimal]:
    valores = {nombre: getattr(motor, nombre) for nombre in VARIABLES_ENTRADA}
    if h_despues is not None:
        valores["h_despues"] = h_despues
    return valores


def calcular_caso(caso: Caso, spec: Spec) -> ResultadoCalculo:
    """Cálculo con los valores del modelo. En B (sin registro) no hay `h_despues` derivable: se pasa
    `h_despues = h_antes` para reproducir el cálculo provisional (`h = h_antes`) y se marca `provisional`."""
    provisional = caso.variaciones.sin_registro
    unidades = {
        m.num_serie_motor: entradas_motor(m, h_despues=m.h_antes if provisional else None)
        for m in caso.motores
    }
    return calcular(spec.datos, unidades, spec.tablas, provisional=provisional, fecha=caso.fechas.evaluacion)


def aetotal_cae(caso: Caso, spec: Spec) -> int:
    resultado = calcular_caso(caso, spec)
    if resultado.total_cae is None:
        raise RuntimeError(
            f"caso {caso.id}: el cálculo de referencia no produjo total ({resultado.motivo_no_calculo})"
        )
    return resultado.total_cae
