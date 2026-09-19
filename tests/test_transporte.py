"""Tests del transporte (S3.4, `ADR-009` §5 bis): `salida/transporte/`.

El transporte es una **frontera declarada, no funcionalidad**. Lo que se protege aqui es precisamente eso:

1. `TransporteNoDisponible` se niega a firmar y a enviar, y lo hace **citando los dos huecos** (API-01 y
   API-09) que hay que cerrar con documentacion oficial antes de que pueda hacer nada.
2. Los dos huecos que cita existen en `docs/HUECOS.md` §1: la lista de `TODO(API-xx)` del codigo y la tabla
   de huecos tienen que coincidir (`/contrastar`).
3. El unico certificado que este modulo toca es el de **usuario**; el de representante se rechaza.
4. **No existe `salida/firma/` como codigo** (`docs/01` §3.8, `docs/03` §10.3, `CLAUDE.md` §2). Se comprueba
   sobre el **arbol de ficheros**, no sobre un comentario.
5. Donde vive el componente sigue sin decidirse: `UBICACIONES` las declara y ninguna es la de por defecto.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from salida.puerto import ErrorSalida
from salida.transporte import (
    CERTIFICADO_USUARIO,
    UBICACIONES,
    ErrorTransporte,
    PeticionFirmada,
    Transporte,
    TransporteNoDisponible,
)

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_SALIDA = RAIZ / "salida"
HUECOS = RAIZ / "docs" / "HUECOS.md"


# ---------------------------------------------------------------------------
# 1 y 2. La unica implementacion de hoy se niega, citando los huecos
# ---------------------------------------------------------------------------


def test_no_se_puede_firmar_ninguna_peticion():
    with pytest.raises(ErrorTransporte) as exc:
        TransporteNoDisponible().firmar_peticion({"lo": "que sea"}, credencial=None)
    assert "API-01" in str(exc.value) and "API-09" in str(exc.value)
    assert "docs/HUECOS.md" in str(exc.value)


def test_no_se_puede_enviar_ninguna_peticion():
    firmada = PeticionFirmada(usuario_id="u-001", peticion={"lo": "que sea"})
    with pytest.raises(ErrorTransporte) as exc:
        TransporteNoDisponible().enviar(firmada)
    assert "API-01" in str(exc.value) and "API-09" in str(exc.value)


def test_error_transporte_es_un_error_de_salida():
    """Quien maneje la salida no necesita conocer este modulo para capturar su fallo."""
    assert issubclass(ErrorTransporte, ErrorSalida)


def test_los_huecos_que_cita_existen_en_la_tabla():
    texto = HUECOS.read_text(encoding="utf-8")
    for hueco in TransporteNoDisponible.HUECOS:
        assert f"| {hueco} |" in texto, f"{hueco} no esta en docs/HUECOS.md §1"


def test_los_todo_del_transporte_estan_en_la_tabla_de_huecos():
    """Regla de oro 10: cada `TODO(API-xx)` del fuente tiene su fila en `docs/HUECOS.md`."""
    fuente = (CARPETA_SALIDA / "transporte" / "__init__.py").read_text(encoding="utf-8")
    texto = HUECOS.read_text(encoding="utf-8")
    citados = set(re.findall(r"API-\d\d", fuente))
    assert citados, "el transporte tiene que declarar de que huecos depende"
    for hueco in sorted(citados):
        assert f"| {hueco} |" in texto, f"{hueco} citado en el codigo y ausente de docs/HUECOS.md §1"


def test_cumple_el_protocolo_del_transporte():
    assert isinstance(TransporteNoDisponible(), Transporte)


# ---------------------------------------------------------------------------
# 3. Certificado de usuario, jamas el de representante
# ---------------------------------------------------------------------------


def test_solo_se_firma_con_certificado_de_usuario():
    firmada = PeticionFirmada(usuario_id="u-001")
    assert firmada.tipo_certificado == CERTIFICADO_USUARIO
    with pytest.raises(ErrorTransporte, match="representante"):
        PeticionFirmada(usuario_id="u-001", tipo_certificado="representante")


def test_una_peticion_firmada_necesita_de_quien_es_el_certificado():
    with pytest.raises(ErrorTransporte, match="usuario_id"):
        PeticionFirmada(usuario_id="  ")


# ---------------------------------------------------------------------------
# 4. No existe `salida/firma/`, y no lo comprobamos leyendo un comentario
# ---------------------------------------------------------------------------


def test_no_existe_salida_firma_en_el_arbol():
    """La firma es un acto humano con certificado de representante: no es software nuestro."""
    assert not (CARPETA_SALIDA / "firma").exists()
    carpetas = {p.name for p in CARPETA_SALIDA.rglob("*") if p.is_dir()}
    assert "firma" not in carpetas
    modulos = {p.stem for p in CARPETA_SALIDA.rglob("*.py")}
    assert "firma" not in modulos and "firmante" not in modulos


def test_nada_en_salida_firma_actos_administrativos():
    """Ni una funcion que firme: lo unico que existe es registrar que una persona firmo."""
    for ruta in sorted(CARPETA_SALIDA.rglob("*.py")):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*def firmar\b", linea):
                assert "firmar_peticion" in linea, f"{ruta.name}: {linea.strip()}"


# ---------------------------------------------------------------------------
# 5. Donde vive: declarado y sin decidir (TODO(API-09), decide Billy)
# ---------------------------------------------------------------------------


def test_las_dos_ubicaciones_estan_declaradas_y_ninguna_es_la_de_por_defecto():
    assert set(UBICACIONES) == {"nuestra_infraestructura", "casa_del_tenant"}
    assert TransporteNoDisponible().ubicacion is None


def test_una_ubicacion_inventada_se_rechaza():
    with pytest.raises(ErrorTransporte, match="ubicacion desconocida"):
        TransporteNoDisponible(ubicacion="la_nube_de_alguien")
    with pytest.raises(ErrorTransporte, match="ubicacion desconocida"):
        PeticionFirmada(usuario_id="u-001", ubicacion="la_nube_de_alguien")


def test_una_ubicacion_declarada_se_admite_sin_decidir_nada():
    for ubicacion in UBICACIONES:
        assert TransporteNoDisponible(ubicacion=ubicacion).ubicacion == ubicacion
