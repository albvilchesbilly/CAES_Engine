"""La costura de S3.5: el interprete determinista contra los requerimientos sinteticos del banco.

Cada mitad de S3.5 se construyo por separado —el nucleo (`engine/requerimientos.py`) y el material de prueba
(`generator/requerimientos.py`, `expedientes/_requerimientos/`)— y cada una se valido contra un doble de la
otra. Aqui se juntan por primera vez, que es donde aparecen los fallos de integracion.

**La decision de diseño que este fichero fija** (`ADR-010` §5 quater): el acierto se mide como *"lo esperado
esta entre lo propuesto"*, **no** como *"lo esperado es lo primero"*. El interprete propone hasta tres
candidatos a proposito y quien elige es un humano (`R-REQ-02`); exigir que acierte el primero seria disenar
para un sistema que decide solo, que es justo lo que no queremos. Lo que si se mide y se deja escrito es la
**posicion**, porque si lo esperado empieza a caer al tercer puesto, el lexico se esta degradando y eso hay
que verlo venir.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.estados import proyectar
from engine.eventos import LogEventos
from engine.requerimientos import (
    InterpreteLexico,
    Requerimiento,
    confirmar,
    escalar,
    reabrir,
)

RAIZ = Path(__file__).resolve().parents[1]
GROUND_TRUTH = RAIZ / "expedientes" / "_requerimientos" / "requerimientos.json"

#: Cuantos candidatos propone el interprete por motivo. Mas alla de esto, no es una propuesta: es ruido.
MAXIMO_PROPUESTAS = 3


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    assert GROUND_TRUTH.is_file(), f"falta el material de S3.5 en {GROUND_TRUTH}; genera con generator"
    return json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))


def requerimiento_de(datos: dict) -> Requerimiento:
    """El `Requerimiento` del nucleo a partir de la fila del ground truth. Sin interpretar nada."""
    return Requerimiento(
        id=datos["id"],
        origen=datos["origen"],
        actuacion_id=datos["actuacion_id"],
        recibido_en=datetime.fromisoformat(datos["recibido_en"]).replace(tzinfo=UTC),
        expediente_id=datos.get("expediente_id"),
        grupo_id=datos.get("grupo_id"),
        motivos=tuple(m["texto"] for m in datos["motivos"]),
        informe_sha256=datos["informe_sha256"],
        literal_plataforma=datos.get("literal_plataforma"),
        ronda=datos.get("ronda", 1),
    )


def esperado_de(motivo: dict) -> tuple[str, str] | None:
    """`(familia, clave)` que el motivo debe producir, o `None` si no debe producir nada."""
    for familia, campo in (
        ("regla", "regla_esperada"),
        ("documento", "documento_esperado"),
        ("variable", "variable_esperada"),
    ):
        if motivo.get(campo):
            return familia, motivo[campo]
    return None


def items_de(interpretacion, texto_motivo: str) -> list:
    """Los items que salieron de ese motivo.

    **Por prefijo, no por igualdad**: la cita de un item es el motivo recortado a `LONGITUD_CITA`, asi que un
    motivo largo nunca coincidiria exacto y el test se creeria que el interprete no propuso nada. Es el
    error que cometio la primera version de este fichero.
    """
    return [i for i in interpretacion.items if texto_motivo.startswith(i.texto_literal[:80])]


def propuestas_de(items, familia: str) -> list[str]:
    """Las claves propuestas de esa familia, en el orden en que las propone el interprete."""
    campo = {"regla": "regla_id", "documento": "documento", "variable": "variable"}[familia]
    return [getattr(item, campo) for item in items if getattr(item, campo)]


# ---------------------------------------------------------------------------
# 1. El material esta donde dice el contrato y lleva su marca
# ---------------------------------------------------------------------------


def test_el_banco_de_requerimientos_cubre_los_tres_origenes(ground_truth: dict) -> None:
    origenes = {r["origen"] for r in ground_truth["requerimientos"]}
    assert origenes == {"verificador", "GA", "CN"}


def test_los_tres_traen_informe_que_es_la_premisa_de_r_req_01(ground_truth: dict) -> None:
    for datos in ground_truth["requerimientos"]:
        assert datos["informe_sha256"], f"{datos['id']} sin informe: R-REQ-01 no lo dejaria reabrir"


def test_el_banco_declara_su_marca_de_sintetico(ground_truth: dict) -> None:
    assert "SINTÉTICO" in ground_truth["marca"].upper()


# ---------------------------------------------------------------------------
# 2. Lo esperado esta entre lo propuesto (la decision de diseño de la cabecera)
# ---------------------------------------------------------------------------


def casos_mapeables(gt: dict):
    for datos in gt["requerimientos"]:
        for motivo in datos["motivos"]:
            if esperado_de(motivo) is not None:
                yield pytest.param(datos, motivo, id=f"{datos['id']}#{motivo['numero']}")


CASOS_MAPEABLES = list(casos_mapeables(json.loads(GROUND_TRUTH.read_text("utf-8"))))


@pytest.mark.parametrize(("datos", "motivo"), CASOS_MAPEABLES)
def test_lo_esperado_esta_entre_lo_propuesto(datos: dict, motivo: dict, spec_ind240) -> None:
    familia, clave = esperado_de(motivo)
    interpretacion = InterpreteLexico().interpretar(requerimiento_de(datos), spec=spec_ind240)
    items = items_de(interpretacion, motivo["texto"])
    assert items, f"el motivo {motivo['numero']} no produjo ningun item"

    propuestas = propuestas_de(items, familia)
    assert clave in propuestas, (
        f"{familia} {clave!r} no esta entre lo propuesto para el motivo {motivo['numero']}: {propuestas}"
    )
    assert len(items) <= MAXIMO_PROPUESTAS, f"{len(items)} propuestas es ruido, no una propuesta"


def test_un_motivo_que_cita_su_regla_la_propone_la_primera(spec_ind240, ground_truth: dict) -> None:
    """Cuando el requerimiento **cita** el identificador, no hay margen: es exactamente esa regla."""
    datos = next(r for r in ground_truth["requerimientos"] if r["origen"] == "verificador")
    motivo = next(m for m in datos["motivos"] if m["dificultad"] == "explicita")
    interpretacion = InterpreteLexico().interpretar(requerimiento_de(datos), spec=spec_ind240)
    items = items_de(interpretacion, motivo["texto"])
    assert propuestas_de(items, "regla")[0] == motivo["regla_esperada"]
    assert items[0].confianza == 1, "una cita explicita no es una conjetura: es esa regla"


# ---------------------------------------------------------------------------
# 3. El motivo que nadie puede mapear: escala, no inventa
# ---------------------------------------------------------------------------


def test_el_motivo_de_prosa_administrativa_no_produce_nada_y_escala(spec_ind240, ground_truth: dict) -> None:
    """El motivo del CN esta redactado a proposito para que un lexico perezoso pique. No debe picar."""
    datos = next(r for r in ground_truth["requerimientos"] if r["origen"] == "CN")
    motivo = datos["motivos"][0]
    assert esperado_de(motivo) is None, "este test asume que el motivo del CN no es mapeable"

    interpretacion = InterpreteLexico().interpretar(requerimiento_de(datos), spec=spec_ind240)
    items = items_de(interpretacion, motivo["texto"])
    assert items == [], f"el lexico se invento algo: {[(i.regla_id, i.documento) for i in items]}"
    assert interpretacion.escala_a_humano is True


def test_lo_que_escala_se_anota_en_el_log_y_no_reabre_nada(spec_ind240, ground_truth: dict) -> None:
    datos = next(r for r in ground_truth["requerimientos"] if r["origen"] == "CN")
    req = requerimiento_de(datos)
    interpretacion = InterpreteLexico().interpretar(req, spec=spec_ind240)

    log = log_firmado(req.actuacion_id)
    estado_previo = proyectar(log).estado_ciclo
    escalar(log, req, interpretacion, actor=("humano", "revisor@tenant", "T-REV"))

    assert log.por_tipo("RequerimientoRecibido") == (), "escalar no reabre: eso lo decide un humano"
    assert estado_previo == "EN_PLATAFORMA"  # de donde salia
    log.verificar()


# ---------------------------------------------------------------------------
# 4. El circuito completo sobre el expediente de tres actuaciones
# ---------------------------------------------------------------------------


def log_firmado(actuacion_id: str, expediente_id: str = "EXPD-SYN-2026-001") -> LogEventos:
    log = LogEventos(actuacion_id)
    motor = ("motor", "engine@test")
    # Dos perfiles: el revisor aprueba la revision (CAP-10) y el responsable firma (CAP-22). A8.
    revisor = ("humano", "revisor@tenant", "T-REV")
    responsable = ("humano", "responsable@tenant", "T-RES")
    instante = datetime(2026, 6, 30, 9, 0, tzinfo=UTC)
    for tipo, payload, actor in (
        ("ActuacionAbierta", {"expediente_id": expediente_id}, motor),
        ("DocumentoRegistrado", {}, motor),
        ("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, motor),
        ("ObservacionRegistrada", {"origen": "revision_humana", "texto": "ok"}, revisor),
        ("PayloadConstruido", {}, motor),
        ("EntregadoADelegado", {}, motor),
        ("FirmaRegistrada", {}, responsable),
    ):
        log.anadir(tipo, payload, actor=actor, ocurrido_en=instante)
    return log


def test_el_verificador_reabre_con_la_regla_que_dice_el_banco(spec_ind240, ground_truth) -> None:
    """El criterio de `docs/06` S3.5, con el material real: reabre **con la regla correcta**."""
    datos = next(r for r in ground_truth["requerimientos"] if r["origen"] == "verificador")
    esperada = next(m["regla_esperada"] for m in datos["motivos"] if m.get("regla_esperada"))
    req = requerimiento_de(datos)
    log = log_firmado(req.actuacion_id)

    propuesta = InterpreteLexico().interpretar(req, spec=spec_ind240)
    interpretacion = confirmar(propuesta, actor=("humano", "billy", "T-REV"))
    reabrir(log, req, interpretacion, actor=("humano", "billy", "T-REV"))

    proyeccion = proyectar(log)
    assert proyeccion.estado_ciclo == "PENDIENTE_SUBSANACION"
    assert proyeccion.origen_subsanacion == "verificador"
    assert esperada in log.ultimo("RequerimientoInterpretado").datos["reglas"]
    log.verificar()


def test_el_contagio_del_banco_coincide_con_lo_que_hace_el_motor(spec_ind240, ground_truth) -> None:
    """El `contagio_esperado` del ground truth, contrastado contra lo que de verdad proyecta el motor."""
    from engine.estados import propagar_requerimiento

    datos = next(r for r in ground_truth["requerimientos"] if r["origen"] == "GA")
    esperado = {a["actuacion_id"] for a in datos["contagio_esperado"]}
    senalada_esperada = [a["actuacion_id"] for a in datos["contagio_esperado"] if a["afectada_directamente"]]
    actuaciones = [a["actuacion_id"] for a in ground_truth["expediente"]["actuaciones"]]
    assert esperado == set(actuaciones), "un requerimiento de GA alcanza al expediente entero"

    req = requerimiento_de(datos)
    logs = {identificador: log_firmado(identificador) for identificador in actuaciones}
    propuesta = InterpreteLexico().interpretar(req, spec=spec_ind240)
    interpretacion = confirmar(propuesta, actor=("humano", "billy", "T-REV"))
    reabrir(logs[req.actuacion_id], req, interpretacion, actor=("humano", "billy", "T-REV"))

    evento = logs[req.actuacion_id].ultimo("RequerimientoRecibido")
    proyecciones = propagar_requerimiento([proyectar(log) for log in logs.values()], evento)

    assert {p.actuacion_id for p in proyecciones} == esperado
    assert all(p.estado_ciclo == "PENDIENTE_SUBSANACION" for p in proyecciones)
    senaladas = [p.actuacion_id for p in proyecciones if p.afectada_directamente]
    assert senaladas == senalada_esperada, "solo la requerida esta señalada; las demas son contagio"
