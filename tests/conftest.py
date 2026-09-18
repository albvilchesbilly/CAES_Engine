"""Fixtures compartidas del banco de pruebas. Se amplían en F0.1 y siguientes."""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SPEC_ACTIVA = RAIZ / "spec" / "IND240_v1.1.yaml"


@pytest.fixture(scope="session")
def spec_ind240():
    """Spec activa cargada y validada por el Spec Registry (F0.4); la reutilizan calculo, reglas y motor."""
    from engine.spec_registry import cargar_spec

    return cargar_spec(SPEC_ACTIVA)
