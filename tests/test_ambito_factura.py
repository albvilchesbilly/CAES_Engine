"""H1 (`/contrastar` 20/09/2026): que `R-AMB-02` dispare de verdad con una factura, de punta a punta.

El defecto que cierra este fichero no estaba en la regla ni en la spec, sino en el escalon anterior:
`engine.extraccion.categoria_de_linea` clasificaba «Suministro e instalacion de motor nuevo 110 kW» como
`instalacion`, de modo que `R-AMB-02` —`BLOQUEANTE_AMBITO`, la que sostiene EXC-01 y EXC-02— **cumplia** con
una factura que compra el motor: una actuacion que la ficha excluye salia `PREVALIDADO` con ahorro publicado.

`tests/test_extraccion.py` fija la funcion; esto fija el **circuito**: PDF → ingesta → clasificacion →
extraccion → consolidacion → reglas → veredicto, en los dos sentidos.

- **Sentido negativo**: la factura del caso A con una linea de compra de motor mas → `NO_ELEGIBLE` por
  `R-AMB-02` y **sin ahorro publicado**. La factura se regenera con el propio `generator` sobre una copia de
  la carpeta del caso A: cambia una linea y nada mas, para que el veredicto solo pueda deberse a ella.
- **Sentido positivo**: el caso A intacto sigue `PREVALIDADO` en 305.829,6 kWh/ano con `R-AMB-02` en
  `CUMPLE`. Es el falso positivo que el arreglo no podia crear: instalar un variador sobre un motor
  **existente** es el caso de uso central del producto, y la factura real lo dice con las palabras
  «instalacion sobre motor existente» y «no incluye suministro de motor».

Sin OCR (`docs/05` §8.2): el veredicto no depende de el.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.motor import Actuacion, procesar_actuacion
from engine.reglas import VEREDICTO_NO_ELEGIBLE, VEREDICTO_PREVALIDADO, Resultado
from engine.spec_registry import SpecRegistry
from generator.casos import caso as caso_sintetico
from generator.documentos import factura as doc_factura
from generator.documentos.base import construir_pdf

RAIZ = Path(__file__).resolve().parents[1]
CASO_A = "EXP001-A_completo"
CARPETA_A = RAIZ / "expedientes" / CASO_A
GROUND_TRUTH_A = RAIZ / "expedientes" / "_resultados_esperados" / f"{CASO_A}.json"
FICHERO_FACTURA = "03_factura.pdf"
CATEGORIAS_QUE_EXCLUYEN = ("motor", "bomba", "ventilador", "compresor", "equipo_completo")
LINEA_COMPRA_DE_MOTOR = ("Suministro e instalación de motor nuevo 110 kW", 1, Decimal("4250.00"))
AHORRO_CASO_A = Decimal("305829.6")


def _ground_truth() -> dict:
    return json.loads(GROUND_TRUTH_A.read_text(encoding="utf-8"))


def _fecha() -> date:
    return date.fromisoformat(_ground_truth()["fecha_evaluacion"])


def _procesar(carpeta: Path) -> Actuacion:
    registro = SpecRegistry()
    registro.cargar_todas()
    return procesar_actuacion(carpeta, fecha_evaluacion=_fecha(), ocr=False, registro=registro)


def _categorias(actuacion: Actuacion) -> list[str]:
    lineas = actuacion.consolidada.variables["factura.lineas"].valor_consumido
    return [linea["categoria"] for linea in lineas]


@pytest.fixture
def carpeta_con_compra_de_motor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copia del caso A con una linea mas en la factura: la compra de un motor nuevo."""
    carpeta = shutil.copytree(CARPETA_A, tmp_path / CASO_A)
    originales = doc_factura.lineas
    monkeypatch.setattr(doc_factura, "lineas", lambda caso: [*originales(caso), LINEA_COMPRA_DE_MOTOR])
    seccion = doc_factura.seccion(caso_sintetico("A"))
    (carpeta / FICHERO_FACTURA).write_bytes(construir_pdf([seccion]))
    return carpeta


def test_una_factura_que_compra_un_motor_deja_la_actuacion_no_elegible(
    carpeta_con_compra_de_motor: Path,
) -> None:
    """El sentido que fallaba: la exclusion de ambito llega hasta el veredicto y retira el ahorro."""
    actuacion = _procesar(carpeta_con_compra_de_motor)
    categorias = _categorias(actuacion)
    assert "motor" in categorias, f"la linea de compra no se leyo como motor: {categorias}"
    amb02 = actuacion.evaluacion.resultado("R-AMB-02")
    assert amb02.resultado is Resultado.FALLA
    assert actuacion.veredicto == VEREDICTO_NO_ELEGIBLE
    assert actuacion.calculo is None, "una actuacion excluida por la ficha no publica ahorro"


def test_el_caso_a_intacto_sigue_prevalidado_con_su_ahorro(tmp_path: Path) -> None:
    """El sentido contrario, que es el que un reordenamiento del lexico habria roto."""
    actuacion = _procesar(shutil.copytree(CARPETA_A, tmp_path / CASO_A))
    assert _categorias(actuacion) == ["variador", "instalacion"]
    assert actuacion.evaluacion.resultado("R-AMB-02").resultado is Resultado.CUMPLE
    assert actuacion.veredicto == VEREDICTO_PREVALIDADO
    assert actuacion.calculo is not None
    assert actuacion.calculo.total == AHORRO_CASO_A


def test_la_regla_de_ambito_mira_las_cinco_categorias_de_equipo(spec_ind240) -> None:
    """Si la spec añade una categoria de equipo, este fichero se entera: el lexico tiene que cubrirla."""
    logica = spec_ind240.regla("R-AMB-02").logica
    for categoria in CATEGORIAS_QUE_EXCLUYEN:
        assert categoria in logica
