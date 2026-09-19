"""Tests del seguimiento post-envio (P9, S3.5 pieza C9): `engine/seguimiento.py`.

Lo que se protege aqui, en este orden:

1. **La reconciliacion es por `codigo_identificativo_propio`**: ni por posicion, ni por nombre, ni "el
   primero que suene". Una referencia que no cuadra falla; una ambigua tambien.
2. **El contagio**, que es el riesgo de negocio mas caro del modelo (`ADR-010`): un `REQUERIDO_GA` sobre un
   expediente de tres actuaciones deja las tres en `PENDIENTE_SUBSANACION`, una senalada y dos por contagio,
   y **no** toca a la que ya estaba cerrada.
3. **Un literal desconocido no se pierde**: se registra, escala a `EN_REVISION_HUMANA`, sale en
   `desconocidos` y la cadena de hashes del log sigue entera.
4. **Idempotencia y ausencia de reloj**: sincronizar dos veces no duplica eventos ni vuelve a contagiar, y
   dos pasadas iguales producen el mismo log byte a byte.
5. Higiene del fuente: nada de `eval`, nada de `float`, ninguna ficha nombrada, ninguna importacion de la
   periferia.

Los logs se construyen a mano con `LogEventos.anadir`: esta pieza no necesita ejecutar el motor.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from engine.estados import propagar_requerimiento, proyectar
from engine.eventos import Actor, LogEventos
from engine.reglas import VEREDICTO_PREVALIDADO
from engine.seguimiento import (
    ACTOR_PLATAFORMA,
    ErrorSeguimiento,
    EstadoRecibido,
    TareaRecibida,
    actuacion_de,
    indexar,
    registrar_estado,
    registrar_tarea,
    sincronizar,
)

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "engine" / "seguimiento.py"

# Dos perfiles, dos actos (A8, `ADR-006`): `T-REV` revisa y corrige (CAP-05/06/10); `T-RES` hace los
# actos del sujeto, firma y desistimiento (CAP-22, CAP-23). Desde S3.1b el rol es obligatorio.
REVISOR = Actor("humano", "revisor@tenant", rol="T-REV")
RESPONSABLE = Actor("humano", "billy@cae", rol="T-RES")
MOTOR = Actor("motor", "engine@test")
AGENTE = Actor("agente", "lector@prompt-v3")

EXPEDIENTE = "EXP-2026-CVA-IND"
T0 = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 19, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)


def log_en_plataforma(actuacion_id: str, *, expediente_id: str | None = EXPEDIENTE) -> LogEventos:
    """Una actuacion entregada, firmada y en plataforma: el punto de partida de todo el post-envio."""
    log = LogEventos(actuacion_id)
    log.anadir("ActuacionAbierta", {"expediente_id": expediente_id}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("DocumentoRegistrado", {"doc_id": "d1"}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("VeredictoEmitido", {"veredicto": VEREDICTO_PREVALIDADO}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("ObservacionRegistrada", {"origen": "revision_humana"}, actor=REVISOR, ocurrido_en=T0)
    log.anadir("PayloadConstruido", {"hash_paquete": "0" * 64}, actor=MOTOR, ocurrido_en=T0)
    log.anadir("EnviadoAPI", {"referencia": f"SIM-{actuacion_id}-abcd1234"}, actor=MOTOR, ocurrido_en=T0)
    firma = {"referencia": f"SIM-{actuacion_id}-abcd1234"}
    log.anadir("FirmaRegistrada", firma, actor=RESPONSABLE, ocurrido_en=T0)
    return log


def expediente_de_tres() -> tuple[dict[str, LogEventos], dict[str, str]]:
    """Tres actuaciones del mismo expediente. Con una sola, el contagio no se distinguiria de no contagiar."""
    logs = {f"ACT-000{n}": log_en_plataforma(f"ACT-000{n}") for n in (1, 2, 3)}
    indice = {f"EXP001-{letra}": f"ACT-000{n}" for n, letra in ((1, "A"), (2, "B"), (3, "C"))}
    return logs, indice


def estado(
    referencia: str,
    literal: str,
    *,
    nivel: str = "actuacion",
    oficial: bool = True,
    instante: datetime = T1,
    motivos: tuple[str, ...] = (),
) -> EstadoRecibido:
    return EstadoRecibido(
        referencia=referencia,
        literal=literal,
        nivel=nivel,
        oficial=oficial,
        instante=instante,
        motivos=motivos,
    )


# ---------------------------------------------------------------------------
# 1. Reconciliacion por codigo identificativo propio
# ---------------------------------------------------------------------------


def test_indexar_usa_el_codigo_propio_y_no_la_posicion():
    actuaciones = [
        {"id": "ACT-0001", "codigo_identificativo_propio": "EXP001-A"},
        {"id": "ACT-0002", "codigo_identificativo_propio": "EXP001-B"},
    ]
    assert indexar(actuaciones) == {"EXP001-A": "ACT-0001", "EXP001-B": "ACT-0002"}


def test_indexar_rechaza_dos_actuaciones_con_el_mismo_codigo_propio():
    actuaciones = [
        {"id": "ACT-0001", "codigo_identificativo_propio": "EXP001-A"},
        {"id": "ACT-0002", "codigo_identificativo_propio": "EXP001-A"},
    ]
    with pytest.raises(ErrorSeguimiento, match="clave de reconciliacion"):
        indexar(actuaciones)


def test_actuacion_de_reconcilia_la_referencia_compuesta_del_destino():
    _, indice = expediente_de_tres()
    # El simulador compone SIM-<codigo>-<huella>; la reconciliacion sigue siendo por codigo propio
    assert actuacion_de(estado("SIM-EXP001-B-abcd1234", "COMPLETA"), indice) == "ACT-0002"
    assert actuacion_de(estado("EXP001-C", "COMPLETA"), indice) == "ACT-0003"


def test_actuacion_de_falla_si_la_referencia_no_cuadra():
    _, indice = expediente_de_tres()
    with pytest.raises(ErrorSeguimiento, match="no cuadra con ninguna actuacion"):
        actuacion_de(estado("SIM-OTRA-COSA-99", "COMPLETA"), indice)


def test_actuacion_de_falla_si_la_referencia_es_ambigua():
    indice = {"EXP001-A": "ACT-0001", "EXP001": "ACT-0009"}
    with pytest.raises(ErrorSeguimiento, match="ambigua"):
        actuacion_de(estado("SIM-EXP001-EXP001-A-ff", "COMPLETA"), indice)


def test_una_tarea_sin_referencia_no_se_adivina():
    _, indice = expediente_de_tres()
    tarea = TareaRecibida(id="T-1", tenant_id="tenant", asunto="revisar", instante=T1)
    with pytest.raises(ErrorSeguimiento, match="no trae referencia"):
        actuacion_de(tarea, indice)


# ---------------------------------------------------------------------------
# 2. Del verificador: PDTE_RECTIFICACION_VER reabre subsanacion con su origen
# ---------------------------------------------------------------------------


def test_pdte_rectificacion_reabre_subsanacion_con_origen_verificador():
    logs, indice = expediente_de_tres()
    recibido = estado(
        "SIM-EXP001-A-abcd1234",
        "PDTE_RECTIFICACION_VER",
        motivos=("Falta el certificado de la empresa instaladora.",),
    )
    resultado = sincronizar(logs, [recibido], indice=indice)

    proyeccion = resultado.proyecciones["ACT-0001"]
    assert proyeccion.estado_ciclo == "PENDIENTE_SUBSANACION"
    assert proyeccion.estado_plataforma == "PDTE_RECTIFICACION_VER"
    assert proyeccion.origen_subsanacion == "verificador"
    assert proyeccion.requerimiento_abierto == "verificador"
    assert proyeccion.afectada_directamente is True
    assert len(resultado.eventos) == 1
    assert resultado.eventos[0].tipo == "EstadoPlataformaRecibido"
    assert resultado.eventos[0].actor.clase == "plataforma"
    # Alcance `grupo`: no contagia al expediente (eso es R-GRP, S4.1)
    assert resultado.contagiadas == {}
    assert resultado.proyecciones["ACT-0002"].estado_ciclo == "EN_PLATAFORMA"


def test_el_motivo_del_verificador_se_conserva_palabra_por_palabra():
    logs, indice = expediente_de_tres()
    motivos = ("No consta la declaracion responsable sobre ayudas publicas.",)
    resultado = sincronizar(
        logs, [estado("SIM-EXP001-A-abcd1234", "PDTE_RECTIFICACION_VER", motivos=motivos)], indice=indice
    )
    assert resultado.eventos[0].datos["motivos"] == list(motivos)


# ---------------------------------------------------------------------------
# 3. Contagio de expediente: el riesgo mas caro del modelo
# ---------------------------------------------------------------------------


def test_requerido_ga_deja_las_tres_actuaciones_en_pendiente_subsanacion():
    logs, indice = expediente_de_tres()
    recibido = estado(
        "SIM-EXP001-B-abcd1234",
        "REQUERIDO_GA",
        nivel="expediente",
        oficial=False,
        motivos=("El expediente no acredita el ambito de una de sus actuaciones.",),
    )
    resultado = sincronizar(logs, [recibido], indice=indice)

    for identificador in ("ACT-0001", "ACT-0002", "ACT-0003"):
        proyeccion = resultado.proyecciones[identificador]
        assert proyeccion.estado_ciclo == "PENDIENTE_SUBSANACION", identificador
        assert proyeccion.origen_subsanacion == "GA", identificador
    senaladas = {
        identificador: resultado.proyecciones[identificador].afectada_directamente
        for identificador in ("ACT-0001", "ACT-0002", "ACT-0003")
    }
    assert senaladas == {"ACT-0001": False, "ACT-0002": True, "ACT-0003": False}
    assert resultado.contagiadas == {EXPEDIENTE: ("ACT-0001", "ACT-0002", "ACT-0003")}
    # Un evento del estado en la senalada y un RequerimientoRecibido en cada companera
    tipos = sorted(evento.tipo for evento in resultado.eventos)
    assert tipos == ["EstadoPlataformaRecibido", "RequerimientoRecibido", "RequerimientoRecibido"]


def test_el_contagio_sobrevive_a_reproyectar_el_log_de_la_companera():
    """El estado es una proyeccion del log (`docs/03` §6): el contagio se persiste, no solo se devuelve."""
    logs, indice = expediente_de_tres()
    sincronizar(
        logs,
        [estado("SIM-EXP001-B-abcd1234", "REQUERIDO_GA", nivel="expediente", oficial=False)],
        indice=indice,
    )
    proyeccion = proyectar(logs["ACT-0003"])
    assert proyeccion.estado_ciclo == "PENDIENTE_SUBSANACION"
    assert proyeccion.afectada_directamente is False
    logs["ACT-0003"].verificar()


def test_lo_persistido_coincide_con_lo_que_decide_propagar_requerimiento():
    """Dos caminos, una sola decision: la tabla y `propagar_requerimiento`, nunca un criterio propio."""
    logs, indice = expediente_de_tres()
    antes = [proyectar(log) for log in logs.values()]
    recibido = estado("SIM-EXP001-B-abcd1234", "REQUERIDO_GA", nivel="expediente", oficial=False)
    resultado = sincronizar(logs, [recibido], indice=indice)
    esperadas = propagar_requerimiento(antes, resultado.eventos[0], directas={"ACT-0002"})
    for esperada in esperadas:
        obtenida = resultado.proyecciones[esperada.actuacion_id]
        assert obtenida.estado_ciclo == esperada.estado_ciclo
        assert obtenida.origen_subsanacion == esperada.origen_subsanacion
        assert obtenida.afectada_directamente == esperada.afectada_directamente


def test_una_actuacion_cerrada_del_expediente_no_se_contagia():
    logs, indice = expediente_de_tres()
    # ACT-0003 cierra con dictamen desfavorable antes del requerimiento del GA
    sincronizar(
        logs, [estado("SIM-EXP001-C-abcd1234", "VERIFICADA_DESFAVORABLE", instante=T1)], indice=indice
    )
    assert proyectar(logs["ACT-0003"]).estado_ciclo == "CERRADA"

    resultado = sincronizar(
        logs,
        [estado("SIM-EXP001-A-abcd1234", "REQUERIDO_GA", nivel="expediente", oficial=False, instante=T2)],
        indice=indice,
    )
    cerrada = resultado.proyecciones["ACT-0003"]
    assert cerrada.estado_ciclo == "CERRADA"
    assert cerrada.resultado == "verificada_desfavorable"
    assert cerrada.origen_subsanacion is None
    assert "ACT-0003" not in resultado.contagiadas[EXPEDIENTE]
    assert resultado.contagiadas == {EXPEDIENTE: ("ACT-0001", "ACT-0002")}


def test_una_actuacion_sin_expediente_no_contagia_a_nadie():
    logs = {"ACT-0001": log_en_plataforma("ACT-0001", expediente_id=None)}
    indice = {"EXP001-A": "ACT-0001"}
    resultado = sincronizar(
        logs,
        [estado("SIM-EXP001-A-abcd1234", "REQUERIDO_GA", nivel="expediente", oficial=False)],
        indice=indice,
    )
    assert resultado.contagiadas == {}
    assert resultado.proyecciones["ACT-0001"].estado_ciclo == "PENDIENTE_SUBSANACION"


# ---------------------------------------------------------------------------
# 4. Un literal desconocido se refleja, escala y se senala
# ---------------------------------------------------------------------------


def test_literal_desconocido_se_registra_escala_y_se_senala():
    logs, indice = expediente_de_tres()
    recibido = estado(
        "SIM-EXP001-A-abcd1234", "REQUERIDO_SEGUNDA_RONDA_CN", nivel="expediente", oficial=False
    )
    resultado = sincronizar(logs, [recibido], indice=indice)

    proyeccion = resultado.proyecciones["ACT-0001"]
    assert proyeccion.estado_ciclo == "EN_REVISION_HUMANA"
    assert proyeccion.estado_plataforma == "REQUERIDO_SEGUNDA_RONDA_CN"
    assert proyeccion.literales_desconocidos == ("REQUERIDO_SEGUNDA_RONDA_CN",)
    assert resultado.desconocidos == ("REQUERIDO_SEGUNDA_RONDA_CN",)
    assert len(resultado.eventos) == 1
    logs["ACT-0001"].verificar()  # la cadena de hashes sigue entera
    assert logs["ACT-0001"].eventos[-1].hash_previo == logs["ACT-0001"].eventos[-2].hash


def test_un_literal_desconocido_no_contagia_aunque_suene_a_expediente():
    logs, indice = expediente_de_tres()
    resultado = sincronizar(
        logs,
        [estado("SIM-EXP001-A-abcd1234", "REQUERIDO_XX", nivel="expediente", oficial=False)],
        indice=indice,
    )
    assert resultado.contagiadas == {}
    assert resultado.proyecciones["ACT-0002"].estado_ciclo == "EN_PLATAFORMA"


# ---------------------------------------------------------------------------
# 5. Idempotencia, orden y ausencia de reloj propio
# ---------------------------------------------------------------------------


def test_sincronizar_dos_veces_no_duplica_eventos_ni_vuelve_a_contagiar():
    logs, indice = expediente_de_tres()
    recibido = estado("SIM-EXP001-B-abcd1234", "REQUERIDO_GA", nivel="expediente", oficial=False)

    primera = sincronizar(logs, [recibido], indice=indice)
    longitudes = {identificador: len(log) for identificador, log in logs.items()}
    segunda = sincronizar(logs, [recibido], indice=indice)

    assert len(primera.eventos) == 3
    assert segunda.eventos == ()
    assert segunda.contagiadas == {}
    assert {identificador: len(log) for identificador, log in logs.items()} == longitudes
    assert segunda.proyecciones["ACT-0003"].estado_ciclo == "PENDIENTE_SUBSANACION"


def test_dos_pasadas_iguales_producen_el_mismo_log_byte_a_byte():
    recibidos = [
        estado("SIM-EXP001-A-abcd1234", "PDTE_RECTIFICACION_VER", motivos=("falta el certificado",)),
        estado("SIM-EXP001-B-abcd1234", "VERIFICADA_FAVORABLE", instante=T2),
    ]
    primeros, indice = expediente_de_tres()
    segundos, _ = expediente_de_tres()
    sincronizar(primeros, recibidos, indice=indice)
    sincronizar(segundos, list(reversed(recibidos)), indice=indice)
    for identificador in primeros:
        assert primeros[identificador].a_jsonl() == segundos[identificador].a_jsonl()


def test_el_instante_del_evento_es_el_del_dato_recibido():
    logs, indice = expediente_de_tres()
    resultado = sincronizar(
        logs, [estado("SIM-EXP001-A-abcd1234", "VERIFICADA_FAVORABLE", instante=T2)], indice=indice
    )
    assert resultado.eventos[0].ocurrido_en == T2


def test_un_estado_sin_zona_horaria_no_es_un_instante():
    with pytest.raises(ErrorSeguimiento, match="zona horaria"):
        EstadoRecibido(
            referencia="EXP001-A",
            literal="COMPLETA",
            nivel="actuacion",
            oficial=True,
            instante=datetime(2026, 9, 19, 8, 0),  # noqa: DTZ001 - es justo lo que se prueba
        )


# ---------------------------------------------------------------------------
# 6. Guardas: nada se anade a un log que no lo admita
# ---------------------------------------------------------------------------


def test_un_estado_que_el_ciclo_no_admite_no_envenena_el_log():
    log = LogEventos("ACT-0001")
    log.anadir("ActuacionAbierta", {"expediente_id": EXPEDIENTE}, actor=MOTOR, ocurrido_en=T0)
    indice = {"EXP001-A": "ACT-0001"}
    antes = log.a_jsonl()
    with pytest.raises(ErrorSeguimiento, match="el log no se toca"):
        sincronizar({"ACT-0001": log}, [estado("EXP001-A", "ENVIADA_A_VERIFICACION")], indice=indice)
    assert log.a_jsonl() == antes
    assert proyectar(log).estado_ciclo == "ABIERTA"


def test_un_estado_de_una_actuacion_sin_log_es_un_error_ruidoso():
    _, indice = expediente_de_tres()
    with pytest.raises(ErrorSeguimiento, match="no hay log"):
        sincronizar({}, [estado("EXP001-A", "COMPLETA")], indice=indice)


def test_el_seguimiento_solo_consume_estados_y_tareas():
    logs, indice = expediente_de_tres()
    with pytest.raises(ErrorSeguimiento, match="EstadoRecibido y TareaRecibida"):
        sincronizar(logs, ["PDTE_RECTIFICACION_VER"], indice=indice)


def test_el_estado_de_plataforma_solo_lo_escribe_un_actor_plataforma():
    logs, _ = expediente_de_tres()
    with pytest.raises(ErrorSeguimiento, match="lo reflejamos"):
        registrar_estado(logs["ACT-0001"], estado("EXP001-A", "VERIFICADA_FAVORABLE"), actor=RESPONSABLE)


# ---------------------------------------------------------------------------
# 7. Tareas pendientes
# ---------------------------------------------------------------------------


def test_una_tarea_se_registra_y_no_mueve_el_ciclo():
    logs, indice = expediente_de_tres()
    tarea = TareaRecibida(
        id="T-1",
        tenant_id="tenant-1",
        asunto="Aportar documentacion",
        instante=T1,
        referencia="SIM-EXP001-A-abcd1234",
        vence_en=date(2026, 10, 1),
    )
    resultado = sincronizar(logs, [tarea], indice=indice)
    assert resultado.eventos[0].tipo == "TareaPendienteRecibida"
    assert resultado.eventos[0].datos["vence_en"] == date(2026, 10, 1)
    assert resultado.proyecciones["ACT-0001"].estado_ciclo == "EN_PLATAFORMA"


def test_registrar_tarea_es_idempotente():
    logs, _ = expediente_de_tres()
    tarea = TareaRecibida(id="T-1", tenant_id="tenant-1", asunto="revisar", instante=T1)
    primero = registrar_tarea(logs["ACT-0001"], tarea)
    segundo = registrar_tarea(logs["ACT-0001"], tarea)
    assert primero.evento_id == segundo.evento_id
    assert len(logs["ACT-0001"].por_tipo("TareaPendienteRecibida")) == 1


def test_el_actor_por_defecto_es_la_plataforma():
    logs, _ = expediente_de_tres()
    evento = registrar_estado(logs["ACT-0001"], estado("EXP001-A", "VERIFICADA_FAVORABLE"))
    assert evento.actor == ACTOR_PLATAFORMA


# ---------------------------------------------------------------------------
# 8. Higiene del fuente
# ---------------------------------------------------------------------------


def test_el_modulo_no_usa_eval_ni_float_ni_conoce_fichas():
    fuente = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("eval(", "exec(", "compile(", "float(", "datetime.now("):
        assert prohibido not in fuente, f"{prohibido} en engine/seguimiento.py"
    assert not re.search(r"\bIND\d{3}\b", fuente), "el seguimiento no conoce ninguna ficha"
    assert "if ficha ==" not in fuente


def test_el_modulo_no_importa_la_periferia():
    fuente = FUENTE.read_text(encoding="utf-8")
    for paquete in ("agentes", "salida", "generator", "tests"):
        assert not re.search(rf"^\s*(from|import)\s+{paquete}\b", fuente, re.MULTILINE)


def test_todo_literal_de_plataforma_sale_de_la_tabla_no_del_codigo():
    """Ni un literal de plataforma escrito en el .py: los de fases 2-4 son nombres nuestros (`API-03`)."""
    fuente = FUENTE.read_text(encoding="utf-8")
    codigo = "\n".join(
        linea for linea in fuente.splitlines() if not linea.lstrip().startswith(("#", "-", "*"))
    )
    for literal in ("PDTE_RECTIFICACION_VER", "VERIFICADA_FAVORABLE", "INSCRITO", "BORRADOR"):
        assert literal not in codigo, f"{literal} esta cableado en engine/seguimiento.py"
