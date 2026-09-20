"""Aislamiento: ni datos de otro tenant, ni campos fuera del ambito del perfil (`ADR-011` §6, punto 2).

Lo que se comprueba, **sobre la respuesta de la API y no sobre una pantalla**:

1. Ninguna lectura de un perfil de tenant devuelve nada de otro tenant, y el cruce se deniega con un error
   que lo dice. El `tenant_id` que manda es el del principal autenticado.
2. `R-UI-12`: un perfil externo **no construye** los campos fuera de su ambito. No es que no se pinten:
   el constructor del bloque **no se llama**. El test lo demuestra sustituyendo esos constructores por uno
   que estalla; si la proyeccion los llamara, el test se enteraria.
3. Un externo solo llega a las actuaciones en las que es parte.

El punto 2 se prueba con una matriz de prueba en la que las celdas `(?)` estan decididas (A1 y A2), porque
con la matriz real el portal externo esta **denegado entero** y no habria respuesta que mirar. Es, ademas,
el escenario que importa: el dia que Billy decida A1 y A2, esto tiene que seguir siendo verdad.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path

import pytest

from api.contrato import Peticion
from api.lecturas import leer
from api.permisos import Contexto, ErrorPermiso, Principal, matriz
from api.proyeccion import CONSTRUCTORES, Vista, bloques_a_construir, proyectar_vista
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[1]
CASO = "EXP001-A_completo"
FECHA = date(2026, 9, 18)
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
RUTA_YAML = RAIZ / "engine" / "capacidades.yaml"

TENANT_PROPIO = "T-001"
TENANT_AJENO = "T-002"
INSTALADOR = "inst-1"


@cache
def _actuacion_procesada():
    """El caso A procesado una vez por sesion, sin OCR (la cadena entera tarda entre 1 y 4 s)."""
    registro = SpecRegistry()
    registro.cargar_todas()
    return procesar_actuacion(
        RAIZ / "expedientes" / CASO, fecha_evaluacion=FECHA, ocr=False, registro=registro
    )


@pytest.fixture
def repositorio() -> RepositorioMemoria:
    repo = RepositorioMemoria()
    repo.anadir("A-PROPIA", TENANT_PROPIO, actuacion=_actuacion_procesada(), partes=(INSTALADOR,))
    repo.anadir("A-AJENA", TENANT_AJENO, actuacion=_actuacion_procesada())
    repo.anadir("A-SIN-PARTE", TENANT_PROPIO, actuacion=_actuacion_procesada())
    return repo


@pytest.fixture
def servicios(repositorio: RepositorioMemoria) -> Servicios:
    return Servicios(repositorio=repositorio, instante=INSTANTE)


@pytest.fixture
def matriz_con_externos_decididos(tmp_path: Path):
    """La matriz con A1 y A2 decididas a favor, y con un externo al que se le concede CAP-03.

    Lo segundo es deliberadamente exagerado: es el escenario en el que `R-UI-12` tiene que salvar la
    situacion, porque la capacidad proyecta bloques que el ambito externo no admite.
    """
    texto = RUTA_YAML.read_text(encoding="utf-8")
    texto = texto.replace(
        """    concede: [T-RES, T-OPE, T-REV]
    condicionada:""",
        """    concede: [T-RES, T-OPE, T-REV, EXT-INS]
    condicionada:""",
    )
    texto = texto.replace(
        """    concede: []
    pendiente: [EXT-INS, EXT-CLI]
    decide: "A1 y A2\"""",
        """    concede: [EXT-INS, EXT-CLI]""",
    )
    destino = tmp_path / "capacidades.yaml"
    destino.write_text(texto, encoding="utf-8")
    return matriz(destino)


# ---------------------------------------------------------------------------
# 1. Ni un dato de otro tenant
# ---------------------------------------------------------------------------


def test_una_lectura_del_propio_tenant_devuelve_su_actuacion(servicios: Servicios) -> None:
    revisor = Principal("u-rev", ("T-REV",), TENANT_PROPIO)
    respuesta = leer(
        Peticion("CAP-03", revisor, Contexto("cola_revision", TENANT_PROPIO, "A-PROPIA")),
        servicios=servicios,
    )
    assert respuesta.rol == "T-REV"
    assert respuesta.eventos == ()
    assert respuesta.datos["identificacion"]["actuacion_id"]
    assert respuesta.datos["veredicto"]["valor"]


def test_una_lectura_sobre_una_actuacion_de_otro_tenant_se_deniega(servicios: Servicios) -> None:
    revisor = Principal("u-rev", ("T-REV",), TENANT_PROPIO)
    with pytest.raises(ErrorPermiso, match="cruce de tenant"):
        leer(
            Peticion("CAP-03", revisor, Contexto("cola_revision", TENANT_PROPIO, "A-AJENA")),
            servicios=servicios,
        )


def test_un_contexto_que_dice_otro_tenant_que_el_del_principal_se_deniega(servicios: Servicios) -> None:
    """El tenant viene de la autenticacion, no del cliente: si no coinciden, no se elige, se deniega."""
    revisor = Principal("u-rev", ("T-REV",), TENANT_PROPIO)
    with pytest.raises(ErrorPermiso, match="cruce de tenant"):
        leer(
            Peticion("CAP-03", revisor, Contexto("cola_revision", TENANT_AJENO, "A-AJENA")),
            servicios=servicios,
        )


def test_la_actividad_del_tenant_no_incluye_eventos_de_otro(servicios: Servicios) -> None:
    from api.comandos import ejecutar

    responsable = Principal("u-res", ("T-RES",), TENANT_PROPIO)
    ejecutar(
        Peticion(
            "CAP-20",
            responsable,
            Contexto("pendiente_de_mi", TENANT_PROPIO, "A-PROPIA"),
            {"verificador": "VER-1"},
        ),
        servicios=servicios,
    )
    ejecutar(
        Peticion(
            "CAP-20",
            Principal("u-ajeno", ("T-RES",), TENANT_AJENO),
            Contexto("pendiente_de_mi", TENANT_AJENO, "A-AJENA"),
            {"verificador": "VER-2"},
        ),
        servicios=servicios,
    )
    respuesta = leer(
        Peticion("CAP-31", responsable, Contexto("pendiente_de_mi", TENANT_PROPIO)), servicios=servicios
    )
    actuaciones = {fila["actuacion_id"] for fila in respuesta.datos["actividad_usuarios"]}
    assert "A-AJENA" not in actuaciones
    assert actuaciones <= {"A-PROPIA", "A-SIN-PARTE"}


def test_la_actividad_del_tenant_no_lleva_payloads(servicios: Servicios) -> None:
    """Supervisar la actividad del equipo no es leer lo que escribieron dentro de cada evento."""
    from api.comandos import ejecutar

    responsable = Principal("u-res", ("T-RES",), TENANT_PROPIO)
    ejecutar(
        Peticion(
            "CAP-20",
            responsable,
            Contexto("pendiente_de_mi", TENANT_PROPIO, "A-PROPIA"),
            {"verificador": "VER-1"},
        ),
        servicios=servicios,
    )
    respuesta = leer(
        Peticion("CAP-31", responsable, Contexto("pendiente_de_mi", TENANT_PROPIO)), servicios=servicios
    )
    filas = respuesta.datos["actividad_usuarios"]
    assert filas
    assert all("payload" not in fila for fila in filas)
    assert all(fila["actor"]["rol"] == "T-RES" for fila in filas)


def test_la_auditoria_global_ve_metadatos_y_no_contenido(servicios: Servicios) -> None:
    from api.comandos import ejecutar

    ejecutar(
        Peticion(
            "CAP-20",
            Principal("u-res", ("T-RES",), TENANT_PROPIO),
            Contexto("pendiente_de_mi", TENANT_PROPIO, "A-PROPIA"),
            {"verificador": "VER-1"},
        ),
        servicios=servicios,
    )
    operacion = Principal("adm", ("ADM-OPS",), None)
    respuesta = leer(Peticion("CAP-65", operacion, Contexto("consola_tenants", None)), servicios=servicios)
    assert set(respuesta.datos) == {"metadatos_auditoria"}
    assert all("payload" not in fila for fila in respuesta.datos["metadatos_auditoria"])


# ---------------------------------------------------------------------------
# 2. R-UI-12: el filtrado es de serializacion
# ---------------------------------------------------------------------------


def test_un_externo_no_recibe_los_campos_fuera_de_su_ambito(
    servicios: Servicios, matriz_con_externos_decididos
) -> None:
    instalador = Principal(INSTALADOR, ("EXT-INS",), TENANT_PROPIO)
    respuesta = leer(
        Peticion("CAP-03", instalador, Contexto("enlace_actuacion", TENANT_PROPIO, "A-PROPIA")),
        servicios=servicios,
        matriz_actual=matriz_con_externos_decididos,
    )
    assert set(respuesta.datos) == {"identificacion"}
    for prohibido in ("veredicto", "calculo", "documentos", "evidencias", "conflictos", "historial"):
        assert prohibido not in respuesta.datos


def test_los_bloques_fuera_de_ambito_ni_siquiera_se_construyen(
    servicios: Servicios, matriz_con_externos_decididos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`R-UI-12` literal: no se construye y se borra, **no se construye**."""

    def estalla(vista: Vista) -> object:
        raise AssertionError("este bloque no deberia construirse para un perfil externo")

    for bloque in ("veredicto", "calculo", "documentos", "evidencias", "conflictos", "historial"):
        monkeypatch.setitem(CONSTRUCTORES, bloque, estalla)

    instalador = Principal(INSTALADOR, ("EXT-INS",), TENANT_PROPIO)
    respuesta = leer(
        Peticion("CAP-03", instalador, Contexto("enlace_actuacion", TENANT_PROPIO, "A-PROPIA")),
        servicios=servicios,
        matriz_actual=matriz_con_externos_decididos,
    )
    assert set(respuesta.datos) == {"identificacion"}


def test_el_mismo_perfil_de_tenant_si_recibe_esos_campos(servicios: Servicios) -> None:
    """Control del control: si nadie filtrara, el test anterior no probaria nada."""
    revisor = Principal("u-rev", ("T-REV",), TENANT_PROPIO)
    respuesta = leer(
        Peticion("CAP-03", revisor, Contexto("cola_revision", TENANT_PROPIO, "A-PROPIA")),
        servicios=servicios,
    )
    assert {"veredicto", "calculo", "documentos", "evidencias", "conflictos", "historial"} <= set(
        respuesta.datos
    )


def test_el_estado_simplificado_de_un_externo_no_lleva_veredicto_tecnico(
    servicios: Servicios, matriz_con_externos_decididos
) -> None:
    instalador = Principal(INSTALADOR, ("EXT-INS",), TENANT_PROPIO)
    respuesta = leer(
        Peticion("CAP-40", instalador, Contexto("enlace_actuacion", TENANT_PROPIO, "A-PROPIA")),
        servicios=servicios,
        matriz_actual=matriz_con_externos_decididos,
    )
    assert set(respuesta.datos) == {"identificacion", "estado_simplificado"}
    plano = repr(respuesta.datos)
    assert "PREVALIDADO" not in plano and "reglas_falladas" not in plano


def test_bloques_a_construir_es_la_interseccion_y_respeta_el_orden() -> None:
    assert bloques_a_construir(("a", "b", "c"), frozenset({"c", "a"})) == ("a", "c")
    assert bloques_a_construir(("a",), frozenset()) == ()


def test_un_bloque_declarado_sin_constructor_es_error_y_no_un_hueco() -> None:
    from api.permisos import ErrorApi

    with pytest.raises(ErrorApi, match="constructor"):
        proyectar_vista(("inventado",), frozenset({"inventado"}), Vista())


def test_todo_bloque_de_la_matriz_tiene_constructor_y_al_reves() -> None:
    declarados: set[str] = set()
    for ambito in matriz().ambitos.values():
        declarados |= set(ambito.bloques)
    assert declarados == set(CONSTRUCTORES), "la matriz y los constructores tienen que cuadrar"


# ---------------------------------------------------------------------------
# 3. Un externo solo ve lo suyo
# ---------------------------------------------------------------------------


def test_un_externo_no_ve_una_actuacion_de_su_tenant_en_la_que_no_es_parte(
    servicios: Servicios, matriz_con_externos_decididos
) -> None:
    instalador = Principal(INSTALADOR, ("EXT-INS",), TENANT_PROPIO)
    with pytest.raises(ErrorPermiso, match="no es parte"):
        leer(
            Peticion("CAP-40", instalador, Contexto("enlace_actuacion", TENANT_PROPIO, "A-SIN-PARTE")),
            servicios=servicios,
            matriz_actual=matriz_con_externos_decididos,
        )


def test_un_externo_tiene_que_decir_de_que_actuacion_habla(
    servicios: Servicios, matriz_con_externos_decididos
) -> None:
    instalador = Principal(INSTALADOR, ("EXT-INS",), TENANT_PROPIO)
    with pytest.raises(ErrorPermiso, match="parte"):
        leer(
            Peticion("CAP-40", instalador, Contexto("enlace_actuacion", TENANT_PROPIO)),
            servicios=servicios,
            matriz_actual=matriz_con_externos_decididos,
        )


def test_con_la_matriz_de_verdad_el_portal_externo_esta_cerrado(servicios: Servicios) -> None:
    """Hoy, sin A1 ni A2, ningun externo lee nada. El test anterior describe el dia que se decidan."""
    instalador = Principal(INSTALADOR, ("EXT-INS",), TENANT_PROPIO)
    with pytest.raises(ErrorPermiso, match="pendiente"):
        leer(
            Peticion("CAP-40", instalador, Contexto("enlace_actuacion", TENANT_PROPIO, "A-PROPIA")),
            servicios=servicios,
        )


# ---------------------------------------------------------------------------
# Falla cerrado: un tenant que no se puede comprobar no se da por bueno
# ---------------------------------------------------------------------------


def test_si_no_se_sabe_de_que_tenant_es_la_actuacion_no_se_sirve(servicios: Servicios) -> None:
    """Cerrado el 20/09/2026. Antes se dejaba pasar y el manejador fallaba luego al pedir la actuacion.

    Eso es cierto con el repositorio en memoria y **falso** con uno real que conozca la actuacion y no su
    tenant: serviria datos sin control. Un permiso que depende de que otro componente falle no es un permiso.
    """
    revisor = Principal("u-rev", ("T-REV",), TENANT_PROPIO)
    peticion = Peticion("CAP-03", revisor, Contexto("cola_revision", TENANT_PROPIO, "A-DESCONOCIDA"))
    with pytest.raises(ErrorPermiso, match="no se puede comprobar de que tenant"):
        leer(peticion, servicios=servicios)


def test_abrir_una_actuacion_nueva_no_pasa_por_el_alcance(servicios: Servicios) -> None:
    """La otra mitad de la regla: sin actuacion nombrada no hay nada de nadie que proteger."""
    from api.contrato import comprobar_alcance

    operador = Principal("u-ope", ("T-OPE",), TENANT_PROPIO)
    peticion = Peticion("CAP-01", operador, Contexto("bandeja", TENANT_PROPIO))
    comprobar_alcance(matriz(), "T-OPE", peticion, servicios)
