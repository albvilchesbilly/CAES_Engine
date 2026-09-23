"""Lo que `api/` dejaba de servir teniendolo delante (`ADR-014` §6, bloque `FR1.a`).

Seis huecos de las dos specs de pantalla —los cinco de `FR1.a` y el que destapo `FR1.c` al pintar la
cola—, y ninguno necesitaba inventar nada: el material ya estaba en `engine/` y la proyeccion no lo
sacaba.

- `GAP-REV-02`: las reglas con su descripcion, su severidad y su fase, no solo el identificador.
- `GAP-REV-05`: el nombre legible de cada variable, leido de la spec. **Nunca** una tabla de etiquetas por
  ficha: eso seria un `if ficha == ...` disfrazado (regla de oro 4).
- `GAP-REV-09`: la traza del calculo y los controles por unidad, con `NO_EVALUABLE` serializado como lo
  hace el nucleo (es un centinela, no un booleano).
- `GAP-COLA-02`: las tareas pendientes de la plataforma y las dos marcas de tiempo del log.
- `GAP-COLA-04` / `GAP-REV-08`: la cifra en español **junto** a la exacta, nunca en su lugar.
- `GAP-COLA-05` / `GAP-REV-10`: la unidad en la que la ficha expresa el ahorro, leida de la spec. Sin
  ella la pantalla tendria que escribir la unidad a mano, que es una etiqueta por ficha cableada en la
  interfaz y la desmentiria la segunda ficha (regla de oro 4, la misma razon que `GAP-REV-05`).

Todo lo de aqui es proyeccion: ningun bloque calcula, evalua una regla ni decide una transicion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from api.contrato import Peticion
from api.lecturas import leer
from api.permisos import Contexto, Principal
from api.proyeccion import CONSTRUCTORES, Vista
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.calculo import ResultadoCalculo, ResultadoUnidad
from engine.eventos.log import Actor
from engine.expresiones import NO_EVALUABLE
from engine.motor import procesar_actuacion
from engine.seguimiento import TareaRecibida, registrar_tarea
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[1]
CASO_A = "EXP001-A_completo"
CASO_C = "EXP001-C_contradictorio"
FECHA = date(2026, 9, 18)
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
TENANT = "T-001"

#: El ahorro del caso A, que es el criterio de aceptacion del repositorio entero (`CLAUDE.md` §5).
EXACTO_A = "305829.6"
PRESENTABLE_A = "305.829,6"

#: La unidad en la que IND240 expresa el ahorro. Esta aqui, en el test, y **no** en `api/`: es el valor
#: esperado de esta ficha, no una constante del motor de proyeccion.
UNIDAD_A = "kWh/año"


@cache
def _procesada(caso: str):
    registro = SpecRegistry()
    registro.cargar_todas()
    return procesar_actuacion(
        RAIZ / "expedientes" / caso, fecha_evaluacion=FECHA, ocr=False, registro=registro
    )


@pytest.fixture
def servicios() -> Servicios:
    repositorio = RepositorioMemoria()
    repositorio.anadir("A", TENANT, actuacion=_procesada(CASO_A))
    repositorio.anadir("C", TENANT, actuacion=_procesada(CASO_C))
    return Servicios(repositorio=repositorio, instante=INSTANTE)


def _completa(servicios: Servicios, identificador: str):
    peticion = Peticion(
        "CAP-03", Principal("u-rev", ("T-REV",), TENANT), Contexto("vista_revision", TENANT, identificador)
    )
    return leer(peticion, servicios=servicios).datos


def _estados(servicios: Servicios, identificador: str):
    peticion = Peticion(
        "CAP-14", Principal("u-rev", ("T-REV",), TENANT), Contexto("vista_revision", TENANT, identificador)
    )
    return leer(peticion, servicios=servicios).datos["estados_plataforma"]


# ---------------------------------------------------------------------------
# GAP-REV-02: las reglas, no solo sus identificadores
# ---------------------------------------------------------------------------


def test_el_veredicto_trae_cada_regla_con_lo_que_dice_de_si_misma(servicios: Servicios) -> None:
    veredicto = _completa(servicios, "A")["veredicto"]
    reglas = veredicto["reglas"]
    assert reglas
    for regla in reglas:
        assert set(regla) == {
            "id",
            "resultado",
            "severidad",
            "fase",
            "nivel",
            "descripcion",
            "referencia",
            "interpretacion",
            "por_unidad",
            "motivo",
        }
        assert regla["descripcion"], regla["id"]


def test_las_reglas_incluyen_las_que_cumplen_para_poder_contarlas(servicios: Servicios) -> None:
    """`CA-REV-19`: "24 de 24 comprobaciones conformes" no se puede escribir si solo llegan las falladas."""
    reglas = _completa(servicios, "A")["veredicto"]["reglas"]
    resultados = {regla["resultado"] for regla in reglas}
    assert "CUMPLE" in resultados
    assert len(reglas) > len(_completa(servicios, "A")["veredicto"]["reglas_falladas"])


def test_los_identificadores_siguen_estando_y_apuntan_a_las_mismas_reglas(servicios: Servicios) -> None:
    veredicto = _completa(servicios, "C")["veredicto"]
    por_id = {regla["id"]: regla for regla in veredicto["reglas"]}
    assert veredicto["reglas_falladas"]
    for identificador in veredicto["reglas_falladas"]:
        assert por_id[identificador]["resultado"] == "FALLA"
        assert por_id[identificador]["severidad"]
    for identificador in veredicto["reglas_no_evaluables"]:
        assert por_id[identificador]["resultado"] == "NO_EVALUABLE"


# ---------------------------------------------------------------------------
# GAP-REV-05: el nombre legible de una variable sale de la spec
# ---------------------------------------------------------------------------


def test_cada_dato_trae_la_descripcion_que_declara_la_spec(servicios: Servicios) -> None:
    datos = _completa(servicios, "A")
    pm = next(e for e in datos["evidencias"] if e["variable"] == "PM")
    declarada = _procesada(CASO_A).spec.variables["PM"]
    assert pm["descripcion"] == declarada["descripcion"]
    assert pm["referencia"] == declarada.get("referencia")
    assert pm["unidad"] == "kW"


def test_una_variable_que_la_spec_no_describe_sale_a_nulo_y_no_se_inventa(servicios: Servicios) -> None:
    datos = _completa(servicios, "A")
    sin_descripcion = [e for e in datos["evidencias"] if e["descripcion"] is None]
    assert sin_descripcion, "el caso A tiene variables sin `descripcion` en la spec: sirven de control"
    assert all("descripcion" in e for e in datos["evidencias"])


def test_las_entradas_del_calculo_tienen_donde_mirar_su_nombre(servicios: Servicios) -> None:
    calculo = _completa(servicios, "A")["calculo"]
    unidad = calculo["por_unidad"][0]
    assert set(unidad["entradas"]) <= set(calculo["variables"])
    assert set(unidad["derivadas"]) <= set(calculo["variables"])
    assert calculo["variables"]["PM"]["descripcion"].startswith("Potencia nominal")


def test_no_hay_ninguna_tabla_de_etiquetas_por_ficha_en_api() -> None:
    """Regla de oro 4: el dia que se anada una ficha, sus nombres vienen en su YAML y nada mas."""
    for fuente in sorted((RAIZ / "api").rglob("*.py")):
        texto = fuente.read_text(encoding="utf-8")
        assert "Potencia nominal" not in texto, fuente.name
        assert '"PM"' not in texto and "'PM'" not in texto, fuente.name


# ---------------------------------------------------------------------------
# GAP-REV-09: traza y controles por unidad
# ---------------------------------------------------------------------------


def test_el_calculo_sirve_la_traza_tal_cual_la_escribe_el_motor(servicios: Servicios) -> None:
    calculo = _completa(servicios, "A")["calculo"]
    assert calculo["traza"] == list(_procesada(CASO_A).calculo.traza)
    assert all(isinstance(linea, str) for linea in calculo["traza"])


def test_cada_unidad_trae_sus_controles_precondiciones_e_interpretaciones(servicios: Servicios) -> None:
    unidad = _completa(servicios, "A")["calculo"]["por_unidad"][0]
    assert unidad["controles"] == {"FIS-01": True, "FIS-02": True}
    assert unidad["precondiciones"]
    assert unidad["interpretaciones"] == ["INT-03", "INT-04", "INT-01"]
    assert "avisos" in unidad


@dataclass(frozen=True)
class ActuacionConCalculo:
    """Lo justo para proyectar un calculo: la proyeccion no necesita nada mas de una actuacion."""

    calculo: object
    spec: object = None


def test_un_control_no_evaluable_se_serializa_como_texto_y_no_como_booleano() -> None:
    """`NO_EVALUABLE` es un centinela de `engine.expresiones`: `bool(NO_EVALUABLE)` mentiria en el JSON."""
    unidad = ResultadoUnidad(
        num_serie_motor="M1",
        entradas={"PM": Decimal("110")},
        derivadas={},
        salida=Decimal("100"),
        controles={"FIS-01": True, "FIS-02": NO_EVALUABLE},
        precondiciones={"N2 < N1": NO_EVALUABLE},
        interpretaciones=[],
        avisos=[],
        motivo_no_calculo=None,
        fuentes={},
    )
    calculo = ResultadoCalculo(
        por_unidad=[unidad],
        total=Decimal("100"),
        total_cae=100,
        traza=["linea"],
        provisional=False,
        motivo_no_calculo=None,
        interpretaciones=[],
        avisos=[],
        controles_ok=NO_EVALUABLE,
        precondiciones_ok=NO_EVALUABLE,
    )
    proyectada = CONSTRUCTORES["calculo"](Vista(actuacion=ActuacionConCalculo(calculo=calculo)))
    servida = proyectada["por_unidad"][0]
    assert servida["controles"] == {"FIS-01": True, "FIS-02": "NO_EVALUABLE"}
    assert servida["precondiciones"] == {"N2 < N1": "NO_EVALUABLE"}
    json.dumps(proyectada)


# ---------------------------------------------------------------------------
# GAP-COLA-04 / GAP-REV-08: la cifra presentable, junto a la exacta
# ---------------------------------------------------------------------------


def test_el_ahorro_sale_en_las_dos_formas_y_la_exacta_no_desaparece(servicios: Servicios) -> None:
    calculo = _completa(servicios, "A")["calculo"]
    assert calculo["total_exacto"] == EXACTO_A
    assert calculo["total_exacto_presentable"] == PRESENTABLE_A
    assert calculo["total_cae"] == 305829
    assert calculo["total_cae_presentable"] == "305.829"


def test_las_entradas_y_la_salida_tambien_llegan_legibles(servicios: Servicios) -> None:
    """Si no llegaran, la pantalla tendria que pasarlas por `Number` para pintarlas, y eso no se hace."""
    unidad = _completa(servicios, "A")["calculo"]["por_unidad"][0]
    assert unidad["entradas"]["N1"] == "1485"
    assert unidad["entradas_presentables"]["N1"] == "1.485"
    assert unidad["salida"] == EXACTO_A
    assert unidad["salida_presentable"] == PRESENTABLE_A
    assert set(unidad["derivadas"]) == set(unidad["derivadas_presentables"])


def test_ninguna_cifra_del_bloque_de_calculo_viaja_como_coma_flotante(servicios: Servicios) -> None:
    calculo = _completa(servicios, "A")["calculo"]

    def sin_flotantes(valor: object, ruta: str) -> None:
        assert not isinstance(valor, float), ruta
        if isinstance(valor, dict):
            for clave, hijo in valor.items():
                sin_flotantes(hijo, f"{ruta}.{clave}")
        elif isinstance(valor, list):
            for indice, hijo in enumerate(valor):
                sin_flotantes(hijo, f"{ruta}[{indice}]")

    sin_flotantes(calculo, "calculo")
    assert "e+" not in json.dumps(calculo).lower()


def test_sin_calculo_no_hay_cifra_ni_presentable_ni_exacta_sino_el_motivo(servicios: Servicios) -> None:
    """Caso C: el motor no elige entre fuentes fiables. `SIN DATO` con motivo, **nunca 0** (`R-UI-07`)."""
    calculo = _completa(servicios, "C")["calculo"]
    assert calculo["total_exacto"] is None
    assert calculo["total_exacto_presentable"] is None
    assert calculo["total_cae"] is None
    assert calculo["total_cae_presentable"] is None
    assert "PM" in calculo["motivo_no_calculo"]


# ---------------------------------------------------------------------------
# GAP-COLA-05 / GAP-REV-10: la unidad del ahorro, leida de la spec
# ---------------------------------------------------------------------------


def _resultado_minimo() -> ResultadoCalculo:
    """Un calculo cualquiera con una unidad y un total. Lo que se mira aqui es el rotulo, no la cifra."""
    unidad = ResultadoUnidad(
        num_serie_motor="M1",
        entradas={},
        derivadas={},
        salida=Decimal("100"),
        controles={},
        precondiciones={},
        interpretaciones=[],
        avisos=[],
        motivo_no_calculo=None,
        fuentes={},
    )
    return ResultadoCalculo(
        por_unidad=[unidad],
        total=Decimal("100"),
        total_cae=100,
        traza=[],
        provisional=False,
        motivo_no_calculo=None,
        interpretaciones=[],
        avisos=[],
        controles_ok=True,
        precondiciones_ok=True,
    )


@dataclass(frozen=True)
class SpecInventada:
    """Otra ficha: de ella la proyeccion solo necesita lo que declara de su calculo."""

    calculo: object


def test_el_ahorro_llega_con_la_unidad_que_declara_la_spec(servicios: Servicios) -> None:
    """`305.829,6` a secas no se puede pintar: la cifra y su unidad salen las dos del servidor."""
    calculo = _completa(servicios, "A")["calculo"]
    declarado = _procesada(CASO_A).spec.calculo
    assert calculo["total_unidad"] == declarado["total"]["unidad"] == UNIDAD_A
    assert calculo["por_unidad"]
    for unidad in calculo["por_unidad"]:
        assert unidad["salida_unidad"] == declarado["motor"]["unidad"]


def test_la_unidad_sigue_a_la_spec_y_no_a_una_constante_de_api() -> None:
    """La segunda ficha traera otra unidad. Si `api/` la llevara escrita, el front mentiria (regla 4)."""
    spec = SpecInventada(calculo={"motor": {"unidad": "MWh/quincena"}, "total": {"unidad": "GWh/decada"}})
    proyectada = CONSTRUCTORES["calculo"](
        Vista(actuacion=ActuacionConCalculo(calculo=_resultado_minimo(), spec=spec))
    )
    assert proyectada["total_unidad"] == "GWh/decada"
    assert proyectada["por_unidad"][0]["salida_unidad"] == "MWh/quincena"


def test_una_spec_que_no_declara_la_unidad_no_recibe_una_inventada() -> None:
    """`R-UI-07`: lo que la ficha no dice se sirve como nulo, y la pantalla pinta `SIN DATO`."""
    proyectada = CONSTRUCTORES["calculo"](Vista(actuacion=ActuacionConCalculo(calculo=_resultado_minimo())))
    assert proyectada["total_unidad"] is None
    assert proyectada["por_unidad"][0]["salida_unidad"] is None


def test_ninguna_unidad_de_ficha_esta_escrita_en_api() -> None:
    """Hermano del test de las etiquetas: ni el nombre de una variable ni su unidad viven en `api/`."""
    declarado = _procesada(CASO_A).spec.calculo
    unidades = {str(declarado["motor"]["unidad"]), str(declarado["total"]["unidad"]), "kWh"}
    for fuente in sorted((RAIZ / "api").rglob("*.py")):
        texto = fuente.read_text(encoding="utf-8")
        for unidad in unidades:
            assert unidad not in texto, f"{fuente.name}: la unidad {unidad!r} sale de la spec"


def test_la_unidad_no_convierte_nada_ni_toca_la_cifra(servicios: Servicios) -> None:
    """Es un rotulo: el ahorro sigue siendo el del nucleo y no pasa por coma flotante en ningun punto."""
    calculo = _completa(servicios, "A")["calculo"]
    assert calculo["total_exacto"] == EXACTO_A
    assert calculo["total_exacto_presentable"] == PRESENTABLE_A
    assert isinstance(calculo["total_unidad"], str)
    assert not isinstance(calculo["total_cae"], float)
    json.dumps(calculo)


# ---------------------------------------------------------------------------
# GAP-COLA-02: tareas pendientes y marcas de tiempo
# ---------------------------------------------------------------------------


def test_los_estados_traen_las_tareas_pendientes_de_la_plataforma(servicios: Servicios) -> None:
    registrar_tarea(
        servicios.repositorio.log("A"),
        TareaRecibida(
            id="TAR-1",
            tenant_id=TENANT,
            asunto="Aportar documentacion adicional",
            instante=INSTANTE,
            referencia="REF-1",
            vence_en=date(2026, 10, 1),
        ),
    )
    estados = _estados(servicios, "A")
    assert estados["tareas_pendientes"] == [
        {
            "tarea_id": "TAR-1",
            "asunto": "Aportar documentacion adicional",
            "referencia": "REF-1",
            "vence_en": "2026-10-01",
            "recibida_en": INSTANTE.isoformat(),
        }
    ]
    json.dumps(estados)


def test_los_estados_traen_la_apertura_y_el_ultimo_movimiento(servicios: Servicios) -> None:
    log = servicios.repositorio.log("A")
    motor = Actor("motor", "engine")
    primero = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    log.anadir("DocumentoRegistrado", {"sha256": "0" * 64}, actor=motor, ocurrido_en=primero)
    log.anadir("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, actor=motor, ocurrido_en=INSTANTE)
    estados = _estados(servicios, "A")
    assert estados["abierta_en"] == primero.isoformat()
    assert estados["ultimo_movimiento_en"] == INSTANTE.isoformat()


def test_un_log_vacio_no_inventa_una_fecha_ni_una_tarea(servicios: Servicios) -> None:
    """`R-UI-07`: sin eventos es `SIN DATO`, y `SIN DATO` se sirve como nulo, no como "hace 0 dias"."""
    estados = _estados(servicios, "A")
    assert estados["abierta_en"] is None
    assert estados["ultimo_movimiento_en"] is None
    assert estados["tareas_pendientes"] == []


def test_los_estados_siguen_trayendo_lo_que_proyecta_el_ciclo(servicios: Servicios) -> None:
    """Se anade, no se sustituye: la proyeccion de `engine.estados` sigue entera y es quien decide."""
    from engine.estados import proyectar

    estados = _estados(servicios, "A")
    del estados["tareas_pendientes"], estados["abierta_en"], estados["ultimo_movimiento_en"]
    assert estados == proyectar(servicios.repositorio.log("A")).a_dict()
