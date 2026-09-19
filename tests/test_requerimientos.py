"""Tests de requerimientos e interprete (P7 con origen, A9 sin LLM, S3.5 pieza C10).

Lo que se protege aqui, en este orden:

1. **La puerta humana (`R-REQ-02`)**, que es la regla que impide que un error de lectura mueva una actuacion
   firmada: sin confirmacion no se reabre, y sin actor humano tampoco. Las dos condiciones, no una.
2. **`R-REQ-01`**: un requerimiento externo sin informe es un rumor y no reabre nada.
3. **`R-REQ-03`**: tras la firma, un cambio de dato fuera de un requerimiento abierto se anota como rechazo
   y no mueve el estado. Se prueba de extremo a extremo contra `engine/estados.py`, que es quien lo hace.
4. **El interprete determinista**: sin cita no hay item, `no_lo_se` es una salida legitima y dos
   interpretaciones del mismo requerimiento son identicas.
5. **El lexico no conoce la ficha**: lo que puede reconocer sale de la spec que se le pasa. Se prueba con la
   spec activa y con una spec inventada en el propio test.
6. Higiene del fuente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from engine.estados import proyectar, tabla_plataforma
from engine.eventos import Actor, ErrorEvento, LogEventos
from engine.reglas import VEREDICTO_PREVALIDADO
from engine.requerimientos import (
    ALCANCE_DE_ORIGEN,
    ORIGENES,
    VERSION_INTERPRETE,
    ErrorRequerimiento,
    Interpretacion,
    Interprete,
    InterpreteLexico,
    Item,
    Requerimiento,
    candidatos_de,
    cita_verbatim,
    confirmar,
    escalar,
    reabrir,
)

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "engine" / "requerimientos.py"

HUMANO = Actor("humano", "billy@cae")
MOTOR = Actor("motor", "engine@test")
AGENTE = Actor("agente", "a9@prompt-v3")

T0 = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 19, 9, 0, tzinfo=UTC)
SHA_INFORME = "b" * 64

MOTIVO_REGLA = "No se acredita que el equipo accionado sea rotodinamico e incluido en el ambito."
MOTIVO_DOCUMENTO = "Falta el certificado de la empresa instaladora con la fecha de puesta en marcha."
MOTIVO_OSCURO = "Rogamos aporten aclaracion sobre el particular indicado en nuestro escrito de referencia."


def log_firmado(actuacion_id: str = "ACT-0001") -> LogEventos:
    """Una actuacion firmada y en plataforma: desde aqui rige la inalterabilidad (`docs/02` §5.4)."""
    log = LogEventos(actuacion_id)
    log.anadir("ActuacionAbierta", {"expediente_id": "EXP-1"}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("DocumentoRegistrado", {"doc_id": "d1"}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("VeredictoEmitido", {"veredicto": VEREDICTO_PREVALIDADO}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("ObservacionRegistrada", {"origen": "revision_humana"}, actor=HUMANO, ocurrido_en=T0)
    log.anadir("ManifiestoGenerado", {"hash_paquete": "0" * 64}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("EntregadoADelegado", {"referencia": "SIM-EXP001-A-abcd1234"}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("FirmaRegistrada", {"referencia": "SIM-EXP001-A-abcd1234"}, actor=HUMANO, ocurrido_en=T0)
    return log


def requerimiento(
    *,
    origen: str = "verificador",
    motivos: tuple[str, ...] = (MOTIVO_REGLA,),
    informe: str | None = SHA_INFORME,
    actuacion_id: str = "ACT-0001",
) -> Requerimiento:
    return Requerimiento(
        id="REQ-0001",
        origen=origen,
        actuacion_id=actuacion_id,
        recibido_en=T1,
        expediente_id="EXP-1",
        motivos=motivos,
        informe_sha256=informe,
        literal_plataforma="PDTE_RECTIFICACION_VER" if origen == "verificador" else None,
    )


# ---------------------------------------------------------------------------
# 1. R-REQ-02: la interpretacion es una propuesta, nunca reabre sola
# ---------------------------------------------------------------------------


def test_sin_confirmacion_humana_no_se_reabre(spec_ind240):
    log = log_firmado()
    req = requerimiento()
    interpretacion = InterpreteLexico().interpretar(req, spec=spec_ind240)
    assert interpretacion.confirmada_por_humano is False
    with pytest.raises(ErrorRequerimiento, match="no esta confirmada por un humano"):
        reabrir(log, req, interpretacion, actor=HUMANO)
    assert proyectar(log).estado_ciclo == "EN_PLATAFORMA"


def test_confirmada_pero_con_actor_agente_tampoco_reabre(spec_ind240):
    log = log_firmado()
    req = requerimiento()
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    with pytest.raises(ErrorRequerimiento, match="acto humano"):
        reabrir(log, req, interpretacion, actor=AGENTE)
    assert proyectar(log).estado_ciclo == "EN_PLATAFORMA"
    assert log.por_tipo("RequerimientoRecibido") == ()


def test_confirmar_lo_hace_un_humano_y_no_un_agente(spec_ind240):
    interpretacion = InterpreteLexico().interpretar(requerimiento(), spec=spec_ind240)
    with pytest.raises(ErrorRequerimiento, match="acto humano"):
        confirmar(interpretacion, actor=AGENTE)
    confirmada = confirmar(interpretacion, actor=HUMANO)
    assert confirmada.confirmada_por_humano is True
    assert confirmada.confirmada_por == HUMANO.id
    assert interpretacion.confirmada_por_humano is False  # la propuesta original no se toca


def test_con_confirmacion_y_actor_humano_se_reabre_con_la_regla_correcta(spec_ind240):
    log = log_firmado()
    req = requerimiento()
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    eventos = reabrir(log, req, interpretacion, actor=HUMANO)

    assert [evento.tipo for evento in eventos] == ["RequerimientoRecibido", "RequerimientoInterpretado"]
    proyeccion = proyectar(log)
    assert proyeccion.estado_ciclo == "PENDIENTE_SUBSANACION"
    assert proyeccion.origen_subsanacion == "verificador"
    assert proyeccion.requerimiento_abierto == "verificador"
    assert proyeccion.afectada_directamente is True
    assert eventos[1].datos["confirmada"] is True
    assert eventos[1].datos["reglas"] == ["R-AMB-01"]
    assert eventos[0].ocurrido_en == T1  # sin reloj propio: el instante es el del requerimiento
    log.verificar()


def test_el_log_exige_actor_humano_en_una_interpretacion_confirmada():
    """Segunda barrera, en el propio log (`CONFIRMACIONES_SOLO_HUMANO`), no solo en `reabrir`."""
    from engine.eventos.canonico import ErrorEvento

    log = log_firmado()
    with pytest.raises(ErrorEvento, match="actor humano"):
        log.anadir(
            "RequerimientoInterpretado",
            {"confirmada": True, "modelo": "m", "version_prompt": "v1", "coste": 1, "latencia": 2},
            actor=AGENTE,
            ocurrido_en=T1,
        )


# ---------------------------------------------------------------------------
# 2. R-REQ-01: un requerimiento sin documento es un rumor
# ---------------------------------------------------------------------------


def test_requerimiento_externo_sin_informe_no_reabre(spec_ind240):
    log = log_firmado()
    req = requerimiento(informe=None)
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    with pytest.raises(ErrorRequerimiento, match="informe_sha256"):
        reabrir(log, req, interpretacion, actor=HUMANO)
    assert proyectar(log).estado_ciclo == "EN_PLATAFORMA"


@pytest.mark.parametrize("origen", ["verificador", "GA", "CN"])
def test_todos_los_origenes_externos_exigen_informe(origen, spec_ind240):
    log = log_firmado()
    req = requerimiento(origen=origen, informe=None)
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    with pytest.raises(ErrorRequerimiento, match="R-REQ-01"):
        reabrir(log, req, interpretacion, actor=HUMANO)


def test_un_requerimiento_interno_no_necesita_informe(spec_ind240):
    log = log_firmado()
    req = requerimiento(origen="interno", informe=None)
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    eventos = reabrir(log, req, interpretacion, actor=HUMANO)
    assert proyectar(log).origen_subsanacion == "interno"
    assert len(eventos) == 2


# ---------------------------------------------------------------------------
# 3. R-REQ-03: inalterabilidad post-firma, de extremo a extremo
# ---------------------------------------------------------------------------


def test_post_firma_un_cambio_de_dato_fuera_de_requerimiento_se_rechaza():
    log = log_firmado()
    log.anadir("DatoConsolidado", {"variable": "h_antes", "valor": 6000}, actor=MOTOR, ocurrido_en=T1)
    proyeccion = proyectar(log)
    assert proyeccion.estado_ciclo == "EN_PLATAFORMA"
    assert len(proyeccion.rechazos) == 1
    assert "inalterabilidad" in str(proyeccion.rechazos[0]["motivo"])


def test_con_un_requerimiento_abierto_el_dato_si_se_puede_corregir(spec_ind240):
    log = log_firmado()
    req = requerimiento()
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    reabrir(log, req, interpretacion, actor=HUMANO)
    log.anadir("DatoConsolidado", {"variable": "h_antes", "valor": 6000}, actor=MOTOR, ocurrido_en=T1)
    proyeccion = proyectar(log)
    assert proyeccion.estado_ciclo == "EN_PROCESO"
    assert proyeccion.rechazos == ()


# ---------------------------------------------------------------------------
# 4. El interprete: sin cita no hay item, `no_lo_se` es legitimo, es determinista
# ---------------------------------------------------------------------------


def test_un_item_sin_cita_no_existe():
    with pytest.raises(ErrorRequerimiento, match="sin cita no existe"):
        Item(texto_literal="   ", regla_id="R-AMB-01", confianza=Decimal("0.9"))


def test_un_motivo_en_blanco_no_produce_item(spec_ind240):
    con_motivo_vacio = InterpreteLexico().interpretar(
        requerimiento(motivos=("   ", MOTIVO_REGLA)), spec=spec_ind240
    )
    solo_el_motivo = InterpreteLexico().interpretar(requerimiento(motivos=(MOTIVO_REGLA,)), spec=spec_ind240)
    assert con_motivo_vacio.items == solo_el_motivo.items
    assert con_motivo_vacio.reglas == ("R-AMB-01",)


def test_la_cita_de_cada_item_esta_en_el_requerimiento_palabra_por_palabra(spec_ind240):
    req = requerimiento(motivos=(MOTIVO_REGLA, MOTIVO_DOCUMENTO))
    interpretacion = InterpreteLexico().interpretar(req, spec=spec_ind240)
    assert interpretacion.items
    for item in interpretacion.items:
        assert cita_verbatim(item, req)


def test_reabrir_rechaza_un_item_cuya_cita_no_esta_en_el_requerimiento():
    log = log_firmado()
    req = requerimiento()
    inventada = Interpretacion(
        requerimiento_id=req.id,
        version_interprete="mano-0.0.0",
        items=(Item(texto_literal="esto no lo dijo nadie", regla_id="R-AMB-01", confianza=Decimal("0.9")),),
        confirmada_por_humano=True,
        confirmada_por=HUMANO.id,
    )
    with pytest.raises(ErrorRequerimiento, match="sin cita no hay item"):
        reabrir(log, req, inventada, actor=HUMANO)
    assert proyectar(log).estado_ciclo == "EN_PLATAFORMA"


def test_lo_que_el_lexico_no_entiende_da_cero_items_y_escala(spec_ind240):
    log = log_firmado()
    req = requerimiento(motivos=(MOTIVO_OSCURO,))
    interpretacion = InterpreteLexico().interpretar(req, spec=spec_ind240)
    assert interpretacion.items == ()
    assert interpretacion.escala_a_humano is True

    evento = escalar(log, req, interpretacion, actor=MOTOR)
    assert evento.tipo == "ObservacionRegistrada"
    assert proyectar(log).estado_ciclo == "EN_REVISION_HUMANA"
    log.verificar()


def test_dos_interpretaciones_del_mismo_requerimiento_son_identicas(spec_ind240):
    req = requerimiento(motivos=(MOTIVO_REGLA, MOTIVO_DOCUMENTO, MOTIVO_OSCURO))
    primera = InterpreteLexico().interpretar(req, spec=spec_ind240)
    segunda = InterpreteLexico().interpretar(req, spec=spec_ind240)
    assert primera == segunda
    assert primera.version_interprete == VERSION_INTERPRETE


def test_un_motivo_que_senala_un_documento_que_falta_lo_reconoce(spec_ind240):
    req = requerimiento(motivos=(MOTIVO_DOCUMENTO,))
    interpretacion = InterpreteLexico().interpretar(req, spec=spec_ind240)
    assert [item.documento for item in interpretacion.items] == ["certificado_instalador"]
    assert interpretacion.items[0].metodo == "lexico"
    assert isinstance(interpretacion.items[0].confianza, Decimal)


def test_una_cita_explicita_de_regla_se_lee_no_se_interpreta(spec_ind240):
    req = requerimiento(motivos=("El expediente incumple la regla R-DOC-01 del catalogo.",))
    interpretacion = InterpreteLexico().interpretar(req, spec=spec_ind240)
    # `DOC-01` es el id de un documento y esta dentro de `R-DOC-01`: no se da por citado
    assert [(item.regla_id, item.documento) for item in interpretacion.items] == [("R-DOC-01", None)]
    assert interpretacion.items[0].confianza == Decimal("1")


def test_un_motivo_puede_senalar_la_regla_y_el_documento_que_la_arregla(spec_ind240):
    """El lexico propone las dos lecturas y ordena por confianza; quien elige es el humano (R-REQ-02)."""
    motivo = (
        "No consta aportada la ficha tecnica del equipo accionado, necesaria para acreditar que el equipo "
        "accionado es rotodinamico y que la actuacion queda incluida en el ambito de la ficha."
    )
    interpretacion = InterpreteLexico().interpretar(requerimiento(motivos=(motivo,)), spec=spec_ind240)
    assert interpretacion.reglas == ("R-AMB-01",)
    assert "ficha_tecnica_equipo_accionado" in interpretacion.documentos
    assert len(interpretacion.items) <= 3
    confianzas = [item.confianza for item in interpretacion.items]
    assert confianzas == sorted(confianzas, reverse=True) or len(confianzas) == 1
    for item in interpretacion.items:
        assert item.texto_literal == " ".join(motivo.split())


def test_el_interprete_lexico_cumple_la_interfaz():
    assert isinstance(InterpreteLexico(), Interprete)


# ---------------------------------------------------------------------------
# 5. El lexico no conoce la ficha: reconoce lo que la spec declara
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReglaFalsa:
    id: str
    descripcion: str
    subsanacion: dict
    equivalente_plataforma: str | None = None


@dataclass(frozen=True)
class SpecFalsa:
    """Una ficha que no existe, inventada en el test: si el lexico la entiende, no conoce ninguna."""

    reglas: tuple
    documentacion: tuple
    variables: dict


SPEC_FALSA = SpecFalsa(
    reglas=(
        ReglaFalsa(
            id="X-LUM-01",
            descripcion="La luminaria sustituida es de vapor de sodio en alumbrado exterior",
            subsanacion={"mensaje": "Aporte el inventario de luminarias sustituidas"},
        ),
        ReglaFalsa(
            id="X-LUM-02",
            descripcion="El flujo luminoso instalado se mantiene o mejora",
            subsanacion={"mensaje": "Aporte la medicion fotometrica"},
        ),
    ),
    documentacion=({"id": "D-01", "tipo": "acta_replanteo", "nombre": "Acta de replanteo firmada"},),
    variables={"potencia_luminaria": {"definicion": "Potencia electrica de la luminaria instalada"}},
)


def test_el_lexico_reconoce_las_reglas_de_la_spec_que_se_le_pasa():
    req = Requerimiento(
        id="REQ-X",
        origen="GA",
        actuacion_id="ACT-X",
        recibido_en=T1,
        motivos=(
            "No se acredita que la luminaria sustituida fuera de vapor de sodio en alumbrado exterior.",
            "Falta el acta de replanteo firmada por las partes.",
        ),
        informe_sha256=SHA_INFORME,
    )
    interpretacion = InterpreteLexico().interpretar(req, spec=SPEC_FALSA)
    assert [(item.regla_id, item.documento) for item in interpretacion.items] == [
        ("X-LUM-01", None),
        (None, "acta_replanteo"),
    ]


def test_los_candidatos_salen_de_la_spec_y_no_de_una_lista_en_el_codigo(spec_ind240):
    claves = {candidato.clave for candidato in candidatos_de(spec_ind240)}
    assert {regla.id for regla in spec_ind240.reglas} <= claves
    assert {str(doc["tipo"]) for doc in spec_ind240.documentacion} <= claves
    assert claves & set(spec_ind240.variables)
    assert {candidato.clave for candidato in candidatos_de(SPEC_FALSA)} == {
        "X-LUM-01",
        "X-LUM-02",
        "acta_replanteo",
        "potencia_luminaria",
    }


def test_sin_spec_no_hay_interpretacion():
    with pytest.raises(ErrorRequerimiento, match="necesita la spec activa"):
        InterpreteLexico().interpretar(requerimiento(), spec=None)


# ---------------------------------------------------------------------------
# 6. Alcances y contratos
# ---------------------------------------------------------------------------


def test_los_origenes_son_los_del_catalogo_de_eventos():
    from engine.eventos.catalogo import ORIGENES_SUBSANACION

    assert tuple(ORIGENES) == ORIGENES_SUBSANACION
    assert set(ALCANCE_DE_ORIGEN) == set(ORIGENES)


def test_ga_y_cn_alcanzan_al_expediente_entero():
    assert ALCANCE_DE_ORIGEN["GA"] == "expediente"
    assert ALCANCE_DE_ORIGEN["CN"] == "expediente"
    assert ALCANCE_DE_ORIGEN["verificador"] == "grupo"
    assert ALCANCE_DE_ORIGEN["interno"] == "actuacion"


def test_el_alcance_coincide_con_el_de_la_tabla_de_plataforma():
    """Los dos sitios donde vive el alcance dicen lo mismo (`docs/03` §10.5, `estados_plataforma.yaml`)."""
    for fila in tabla_plataforma().values():
        if fila.origen_subsanacion is None:
            continue
        assert fila.alcance == ALCANCE_DE_ORIGEN[fila.origen_subsanacion], fila.literal


def test_un_origen_desconocido_no_se_admite():
    with pytest.raises(ErrorRequerimiento, match="origen de requerimiento desconocido"):
        Requerimiento(id="REQ-1", origen="inspector", actuacion_id="ACT-1", recibido_en=T1)


def test_el_requerimiento_exige_instante_con_zona():
    with pytest.raises(ErrorRequerimiento, match="zona explicita"):
        Requerimiento(
            id="REQ-1",
            origen="GA",
            actuacion_id="ACT-1",
            recibido_en=datetime(2026, 9, 19, 9, 0),  # noqa: DTZ001 - es justo lo que se prueba
        )


def test_la_segunda_ronda_de_cn_se_modela_y_no_se_acota(spec_ind240):
    log = log_firmado()
    req = replace(requerimiento(origen="CN"), ronda=2)
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    eventos = reabrir(log, req, interpretacion, actor=HUMANO)
    assert eventos[0].datos["ronda"] == 2
    assert eventos[0].datos["alcance"] == "expediente"


def test_reabrir_dos_veces_el_mismo_requerimiento_no_duplica_eventos(spec_ind240):
    log = log_firmado()
    req = requerimiento()
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    primeros = reabrir(log, req, interpretacion, actor=HUMANO)
    segundos = reabrir(log, req, interpretacion, actor=HUMANO)
    assert len(primeros) == 2
    assert segundos == ()
    assert len(log.por_tipo("RequerimientoRecibido")) == 1


def test_no_se_reabre_una_actuacion_que_no_es_la_del_requerimiento(spec_ind240):
    log = log_firmado("ACT-0002")
    req = requerimiento(actuacion_id="ACT-0001")
    interpretacion = confirmar(InterpreteLexico().interpretar(req, spec=spec_ind240), actor=HUMANO)
    with pytest.raises(ErrorRequerimiento, match="el log es de la actuacion"):
        reabrir(log, req, interpretacion, actor=HUMANO)


# ---------------------------------------------------------------------------
# 7. Higiene del fuente
# ---------------------------------------------------------------------------


def codigo_de(fuente: str) -> str:
    """El fuente sin docstrings ni comentarios: lo que el modulo **hace**, no lo que explica."""
    sin_docstrings = re.sub(r'""".*?"""', "", fuente, flags=re.DOTALL)
    return "\n".join(linea for linea in sin_docstrings.splitlines() if not linea.lstrip().startswith("#"))


def test_el_modulo_no_usa_eval_ni_float_ni_conoce_fichas():
    fuente = FUENTE.read_text(encoding="utf-8")
    codigo = codigo_de(fuente)
    for prohibido in ("eval(", "exec(", "compile(", "float(", "datetime.now("):
        assert prohibido not in fuente, f"{prohibido} en engine/requerimientos.py"
    assert not re.search(r"\bIND\d{3}\b", fuente), "el interprete no conoce ninguna ficha"
    assert not re.search(r"^\s*if\s+ficha\s*==", codigo, re.MULTILINE)
    assert not re.search(r"\bR-(?!REQ)[A-Z]{3}-\d{2}\b", codigo), (
        "ninguna regla de una ficha concreta esta cableada en el interprete"
    )


def test_el_modulo_no_importa_la_periferia():
    fuente = FUENTE.read_text(encoding="utf-8")
    for paquete in ("agentes", "salida", "generator", "tests"):
        assert not re.search(rf"^\s*(from|import)\s+{paquete}\b", fuente, re.MULTILINE)


# ---------------------------------------------------------------------------
# R-REQ-02 en el catalogo: la puerta no se rodea escribiendo el evento a mano
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clase", ["motor", "agente"])
def test_ningun_componente_automatico_nuestro_reabre_una_actuacion(clase: str) -> None:
    """El agujero que encontro la revision de S3.5 (`ADR-010` §5 quater, hallazgo 1).

    `reabrir` exige confirmacion humana, pero un `RequerimientoRecibido` escrito **directamente** al log
    movia la actuacion a `PENDIENTE_SUBSANACION` sin interpretacion ni confirmacion. La puerta estaba en la
    funcion, no en el catalogo, asi que se rodeaba saltandose la funcion.
    """
    log = LogEventos("ACT-99")
    payload: dict[str, object] = {"origen": "GA", "requerimiento_ref": "REQ-9"}
    if clase == "agente":  # un evento de agente declara ademas su traza (`docs/03` §11.2)
        payload |= {"coste": "0", "latencia": "0", "modelo": "x", "version_prompt": "v1"}
    with pytest.raises(ErrorEvento, match="ningun componente automatico"):
        log.anadir("RequerimientoRecibido", payload, actor=(clase, f"{clase}@test"))


@pytest.mark.parametrize("clase", ["humano", "plataforma"])
def test_quien_si_puede_escribir_un_requerimiento(clase: str) -> None:
    """Un humano (tras confirmar) y la plataforma (el contagio de GA/CN): nadie mas."""
    log = LogEventos("ACT-99")
    log.anadir("ActuacionAbierta", {}, actor=("motor", "engine@test"))
    evento = log.anadir(
        "RequerimientoRecibido",
        {"origen": "GA", "requerimiento_ref": "REQ-9"},
        actor=(clase, f"{clase}@test"),
    )
    assert evento.actor.clase == clase
    log.verificar()
