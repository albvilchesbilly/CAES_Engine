"""Tests de la maquina de estados (N6, S3.1 pieza C): `engine/estados.py` y su tabla de mapeo YAML.

Lo que se protege aqui, en este orden:

1. **Los cuatro niveles no se mezclan**: `ESTADOS_CICLO` coincide con el enumerado del modelo canonico, los
   8 estados de actuacion son los de `docs/02` §5.1 y los de expediente son provisionales.
2. **El grafo** de `docs/03` §7.2: solo las transiciones declaradas pasan, y una invalida dice el par.
3. **El estado es una proyeccion del log**: `proyectar` reproduce el ciclo completo, y `aplicar` es pura.
4. **Los cinco invariantes** de `ADR-004` C3: firma humana, `LISTA_PARA_ENVIO` con dos condiciones,
   inalterabilidad post-firma, contagio de GA/CN y literal desconocido.
5. **La tabla YAML** es exactamente la de `docs/02` §5.6, y cada provisional lleva su `TODO(API-03)`.
6. Higiene del fuente.

Las listas esperadas (estados de ciclo, los 8 literales confirmados, el grafo, la tabla de proyeccion) se
**escriben aqui**, leidas de los documentos; no se importan del modulo que se prueba. Los logs se construyen
a mano: esta pieza no necesita ejecutar el motor.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from engine.estados import (
    ESTADOS_CICLO,
    ESTADOS_PLATAFORMA_ACTUACION,
    ESTADOS_PLATAFORMA_EXPEDIENTE,
    ESTADOS_TERMINALES,
    ORIGEN_DESCARTE,
    ORIGEN_ESCALADO,
    ORIGEN_REVISION,
    RUTA_TABLA,
    ErrorEstado,
    Proyeccion,
    aplicar,
    es_transicion_valida,
    inicial,
    propagar_requerimiento,
    proyectar,
    proyectar_estado_plataforma,
    tabla_plataforma,
    transiciones_validas,
)
from engine.eventos import Actor, Evento, LogEventos, codificar

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "engine" / "estados.py"
ESQUEMA_ACTUACION = RAIZ / "engine" / "modelo" / "esquemas" / "actuacion-1.0.json"

ACT = "ACT-0001"
INSTANTE = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)

HUMANO = Actor("humano", "billy@cae")
MOTOR = Actor("motor", "engine@test")
AGENTE = Actor("agente", "lector@prompt-v3")
PLATAFORMA = Actor("plataforma", "omie")

#: Lo que un evento de agente tiene que traer siempre (`docs/03` §11.2 punto 6).
PAYLOAD_AGENTE = {"modelo": "m", "version_prompt": "v1", "coste": 1, "latencia": 2}


def suceso(
    tipo: str,
    payload: dict | None = None,
    *,
    actor: Actor = MOTOR,
    actuacion: str = ACT,
    secuencia: int = 1,
) -> Evento:
    """Un sobre de evento construido a mano: se salta `LogEventos.anadir` a proposito.

    Asi se puede intentar una `FirmaRegistrada` de actor `motor` y comprobar que **la maquina de estados**
    la rechaza, no solo el log.
    """
    return Evento(
        evento_id=f"ev-{secuencia}",
        actuacion_id=actuacion,
        secuencia=secuencia,
        tipo=tipo,
        ocurrido_en=INSTANTE,
        actor=actor,
        payload=codificar(dict(payload or {})),  # type: ignore[arg-type]
        hash_previo="",
        hash="",
    )


def en_estado(estado: str, **campos: object) -> Proyeccion:
    """Una proyeccion colocada en un estado concreto, sin tener que llegar hasta el por el log."""
    return replace(inicial(ACT), estado_ciclo=estado, **campos)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Los cuatro niveles no se mezclan
# ---------------------------------------------------------------------------

#: `ADR-004` C3. Se escriben aqui; el test compara contra el modulo y contra el esquema.
CICLO_ESPERADO = (
    "ABIERTA",
    "EN_PROCESO",
    "EVALUADA",
    "PENDIENTE_SUBSANACION",
    "EN_REVISION_HUMANA",
    "LISTA_PARA_ENVIO",
    "ENTREGADA",
    "EN_PLATAFORMA",
    "CERRADA",
    "DESCARTADA",
)

#: `docs/02` §5.1: los 8 confirmados en la presentacion (pag. 26).
ACTUACION_ESPERADOS = (
    "BORRADOR",
    "COMPLETA",
    "ENVIADA_A_VERIFICACION",
    "PDTE_RECTIFICACION_VER",
    "VERIFICACION_EN_PROCESO",
    "VERIFICADA_FAVORABLE",
    "VERIFICADA_DESFAVORABLE",
    "NO_PUEDE_EMITIR_DICTAMEN",
)

#: `docs/02` §5.2 y `docs/HUECOS.md` API-03: nombres nuestros, NO OFICIALES.
EXPEDIENTE_ESPERADOS = (
    "BORRADOR_SOLICITUD",
    "PRESENTADO",
    "EN_VALIDACION_TECNICA",
    "REQUERIDO_GA",
    "VALIDADO_GA",
    "EN_REVISION_FORMAL",
    "REQUERIDO_CN",
    "RESUELTO_FAVORABLE",
    "RESUELTO_DESFAVORABLE",
    "INSCRITO",
    "DESISTIDO",
)


def test_los_diez_estados_de_ciclo_son_los_del_adr() -> None:
    assert ESTADOS_CICLO == CICLO_ESPERADO
    assert len(set(ESTADOS_CICLO)) == 10


def test_estados_de_ciclo_coinciden_con_el_esquema_del_modelo_canonico() -> None:
    """Si el modelo canonico y la maquina de estados no dicen lo mismo, uno de los dos esta mal."""
    esquema = json.loads(ESQUEMA_ACTUACION.read_text(encoding="utf-8"))
    enumerado = esquema["properties"]["ciclo"]["properties"]["estado_ciclo"]["enum"]
    assert tuple(enumerado) == ESTADOS_CICLO


def test_los_ocho_estados_de_actuacion_son_los_confirmados() -> None:
    assert ESTADOS_PLATAFORMA_ACTUACION == ACTUACION_ESPERADOS


def test_los_estados_de_expediente_son_los_provisionales_de_api_03() -> None:
    assert ESTADOS_PLATAFORMA_EXPEDIENTE == EXPEDIENTE_ESPERADOS
    texto_huecos = (RAIZ / "docs" / "HUECOS.md").read_text(encoding="utf-8")
    assert "| API-03 |" in texto_huecos
    for literal in EXPEDIENTE_ESPERADOS:
        assert literal in texto_huecos, f"{literal} no esta enumerado en docs/HUECOS.md"


def test_ningun_literal_de_plataforma_vive_en_el_codigo() -> None:
    """Cuando llegue el diccionario oficial, cambiar nombres tiene que ser cambiar YAML (`docs/03` §7.1).

    Se descuentan las menciones entre acentos graves: la prosa de las cabeceras cita ejemplos para explicar
    de donde sale una regla; lo que no puede haber es un literal en una expresion.
    """
    codigo = re.sub(r"`[^`]*`", "", FUENTE.read_text(encoding="utf-8"))
    for literal in ACTUACION_ESPERADOS + EXPEDIENTE_ESPERADOS:
        assert literal not in codigo, f"{literal} esta escrito en engine/estados.py"


# ---------------------------------------------------------------------------
# 2. El grafo de docs/03 §7.2
# ---------------------------------------------------------------------------

#: `docs/03` §7.2 y §7.3, mas las dos lecturas de `docs/02` §5.6 (entrega modificable, literal desconocido).
GRAFO_ESPERADO: dict[str, set[str]] = {
    "ABIERTA": {"EN_PROCESO", "EN_REVISION_HUMANA"},
    "EN_PROCESO": {"EVALUADA", "EN_REVISION_HUMANA"},
    "EVALUADA": {
        "EN_PROCESO",
        "PENDIENTE_SUBSANACION",
        "EN_REVISION_HUMANA",
        "LISTA_PARA_ENVIO",
        "DESCARTADA",
    },
    "PENDIENTE_SUBSANACION": {"EN_PROCESO", "EN_REVISION_HUMANA", "CERRADA"},
    "EN_REVISION_HUMANA": {"EN_PROCESO", "EVALUADA", "PENDIENTE_SUBSANACION", "CERRADA"},
    "LISTA_PARA_ENVIO": {"EN_PROCESO", "ENTREGADA", "EN_REVISION_HUMANA"},
    "ENTREGADA": {"EN_PROCESO", "EN_PLATAFORMA", "EN_REVISION_HUMANA"},
    "EN_PLATAFORMA": {"PENDIENTE_SUBSANACION", "EN_REVISION_HUMANA", "CERRADA"},
    "CERRADA": set(),
    "DESCARTADA": set(),
}


def test_el_grafo_es_el_de_la_documentacion() -> None:
    for estado in ESTADOS_CICLO:
        assert set(transiciones_validas(estado)) == GRAFO_ESPERADO[estado], estado


def test_solo_las_transiciones_declaradas_pasan() -> None:
    """Producto de estados: cualquier par que no este en el grafo es invalido (quedarse quieto no cuenta)."""
    for origen in ESTADOS_CICLO:
        for destino in ESTADOS_CICLO:
            esperado = destino == origen or destino in GRAFO_ESPERADO[origen]
            assert es_transicion_valida(origen, destino) is esperado, f"{origen} -> {destino}"


def test_los_estados_terminales_no_tienen_salida() -> None:
    for estado in ESTADOS_TERMINALES:
        assert transiciones_validas(estado) == frozenset()


def test_un_estado_desconocido_es_error() -> None:
    with pytest.raises(ErrorEstado, match="desconocido"):
        transiciones_validas("EN_TRAMITE")
    with pytest.raises(ErrorEstado, match="desconocido"):
        es_transicion_valida("ABIERTA", "EN_TRAMITE")


LISTA = {"veredicto": "PREVALIDADO", "revisada_por_humano": True}

INTENTOS_INVALIDOS = [
    ("ABIERTA", {}, "VeredictoEmitido", {"veredicto": "PREVALIDADO"}, MOTOR, "EVALUADA"),
    ("ABIERTA", LISTA, "PayloadConstruido", {}, MOTOR, "LISTA_PARA_ENVIO"),
    ("EN_PROCESO", {}, "EntregadoADelegado", {}, MOTOR, "ENTREGADA"),
    ("EVALUADA", {}, "EnviadoAPI", {}, MOTOR, "ENTREGADA"),
    ("PENDIENTE_SUBSANACION", LISTA, "ManifiestoGenerado", {}, MOTOR, "LISTA_PARA_ENVIO"),
    ("EN_PLATAFORMA", {}, "EntregadoADelegado", {}, MOTOR, "ENTREGADA"),
    ("CERRADA", {}, "DocumentoRegistrado", {}, MOTOR, "EN_PROCESO"),
    ("DESCARTADA", {}, "VeredictoEmitido", {"veredicto": "SUBSANABLE"}, MOTOR, "EVALUADA"),
    ("CERRADA", {}, "ObservacionRegistrada", {"origen": ORIGEN_ESCALADO}, MOTOR, "EN_REVISION_HUMANA"),
]


@pytest.mark.parametrize(("origen", "campos", "tipo", "payload", "actor", "destino"), INTENTOS_INVALIDOS)
def test_una_transicion_invalida_dice_el_par_origen_destino(
    origen: str, campos: dict, tipo: str, payload: dict, actor: Actor, destino: str
) -> None:
    with pytest.raises(ErrorEstado) as error:
        aplicar(en_estado(origen, **campos), suceso(tipo, payload, actor=actor))
    assert f"{origen} -> {destino}" in str(error.value)


def test_quedarse_en_el_mismo_estado_no_es_una_transicion() -> None:
    """Veinte documentos seguidos dejan la actuacion en EN_PROCESO sin que EN_PROCESO -> EN_PROCESO exista."""
    assert "EN_PROCESO" not in GRAFO_ESPERADO["EN_PROCESO"]
    proyeccion = en_estado("EN_PROCESO")
    for numero in range(1, 21):
        proyeccion = aplicar(proyeccion, suceso("DocumentoRegistrado", secuencia=numero))
    assert proyeccion.estado_ciclo == "EN_PROCESO"
    assert proyeccion.secuencia == 20


# ---------------------------------------------------------------------------
# 3. El estado es una proyeccion del log
# ---------------------------------------------------------------------------


def log_ciclo_completo() -> LogEventos:
    """El camino feliz de `docs/03` §7.2, evento a evento, con los actores que exige cada uno."""
    log = LogEventos(actuacion_id=ACT)
    log.anadir("ActuacionAbierta", {"actuacion_id": ACT}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("FichaAsignada", {"codigo": "FIC"}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("DocumentoRegistrado", {"sha256": "a" * 64}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("DatoConsolidado", {"variable": "P"}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("CalculoRealizado", {"unidades": 1}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("ObservacionRegistrada", {"origen": ORIGEN_REVISION}, actor=HUMANO, ocurrido_en=INSTANTE)
    log.anadir("PayloadConstruido", {"hash_cabecera": "b" * 64}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("EntregadoADelegado", {"tenant": "T1"}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("FirmaRegistrada", {"firmante": "billy"}, actor=HUMANO, ocurrido_en=INSTANTE)
    log.anadir(
        "EstadoPlataformaRecibido",
        {"estado": "ENVIADA_A_VERIFICACION"},
        actor=PLATAFORMA,
        ocurrido_en=INSTANTE,
    )
    log.anadir(
        "EstadoPlataformaRecibido",
        {"estado": "VERIFICADA_DESFAVORABLE"},
        actor=PLATAFORMA,
        ocurrido_en=INSTANTE,
    )
    return log


def test_proyectar_reproduce_el_ciclo_completo() -> None:
    log = log_ciclo_completo()
    log.verificar()
    recorrido = []
    proyeccion = inicial(ACT)
    for evento in log.eventos:
        proyeccion = aplicar(proyeccion, evento)
        if not recorrido or recorrido[-1] != proyeccion.estado_ciclo:
            recorrido.append(proyeccion.estado_ciclo)
    assert recorrido == [
        "ABIERTA",
        "EN_PROCESO",
        "EVALUADA",
        "LISTA_PARA_ENVIO",
        "ENTREGADA",
        "EN_PLATAFORMA",
        "CERRADA",
    ]
    final = proyectar(log)
    assert final == proyeccion
    assert final.estado_ciclo == "CERRADA"
    assert final.resultado == "verificada_desfavorable"
    assert final.estado_plataforma == "VERIFICADA_DESFAVORABLE"
    assert final.veredicto == "PREVALIDADO"
    assert final.firmada is True
    assert final.secuencia == len(log)


def test_proyectar_es_determinista_y_no_depende_del_orden_de_iteracion() -> None:
    log = log_ciclo_completo()
    revuelto = LogEventos(ACT, sorted(log.eventos, key=lambda e: -e.secuencia))
    assert proyectar(revuelto).a_dict() == proyectar(log).a_dict()


def test_proyectar_exige_que_el_log_sea_de_la_misma_actuacion() -> None:
    with pytest.raises(ErrorEstado, match="proyeccion de partida"):
        proyectar(log_ciclo_completo(), desde=inicial("ACT-OTRA"))
    with pytest.raises(ErrorEstado, match="es de la actuacion"):
        aplicar(inicial(ACT), suceso("DocumentoRegistrado", actuacion="ACT-OTRA"))


def test_aplicar_no_muta_la_proyeccion_de_entrada() -> None:
    antes = en_estado("EVALUADA", veredicto="PREVALIDADO", revisada_por_humano=True)
    copia = antes.a_dict()
    despues = aplicar(antes, suceso("PayloadConstruido"))
    assert antes.a_dict() == copia
    assert antes.estado_ciclo == "EVALUADA"
    assert despues.estado_ciclo == "LISTA_PARA_ENVIO"
    assert despues is not antes


def test_aplicar_es_pura_mismo_par_mismo_resultado() -> None:
    partida = en_estado("EN_PLATAFORMA", firmada=True)
    evento = suceso("EstadoPlataformaRecibido", {"estado": "PDTE_RECTIFICACION_VER"}, actor=PLATAFORMA)
    primero = aplicar(partida, evento)
    segundo = aplicar(partida, evento)
    assert primero == segundo
    assert primero.a_dict() == segundo.a_dict()


def test_un_tipo_de_evento_fuera_del_catalogo_es_error() -> None:
    with pytest.raises(ErrorEstado, match="no declarado"):
        aplicar(inicial(ACT), suceso("ActuacionBendecida"))


# ---------------------------------------------------------------------------
# 4. Invariante 1: la firma es humana
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor", [MOTOR, AGENTE, PLATAFORMA], ids=lambda a: a.clase)
def test_ningun_actor_no_humano_mueve_entregada_a_en_plataforma(actor: Actor) -> None:
    payload = dict(PAYLOAD_AGENTE) if actor.clase == "agente" else {}
    with pytest.raises(ErrorEstado, match="actor humano"):
        aplicar(en_estado("ENTREGADA"), suceso("FirmaRegistrada", payload, actor=actor))


def test_solo_el_actor_humano_mueve_entregada_a_en_plataforma() -> None:
    despues = aplicar(en_estado("ENTREGADA"), suceso("FirmaRegistrada", {}, actor=HUMANO))
    assert despues.estado_ciclo == "EN_PLATAFORMA"
    assert despues.firmada is True


@pytest.mark.parametrize("actor", [HUMANO, MOTOR, AGENTE, PLATAFORMA], ids=lambda a: a.clase)
def test_ningun_otro_evento_mueve_entregada_a_en_plataforma(actor: Actor) -> None:
    """Las cuatro clases de actor, con el evento que mas se parece a una entrada en plataforma."""
    payload = dict(PAYLOAD_AGENTE) if actor.clase == "agente" else {}
    with pytest.raises(ErrorEstado, match="ENVIADA_A_VERIFICACION exige"):
        aplicar(
            en_estado("ENTREGADA"),
            suceso("EstadoPlataformaRecibido", {**payload, "estado": "ENVIADA_A_VERIFICACION"}, actor=actor),
        )


def test_el_log_tampoco_deja_escribir_una_firma_de_maquina() -> None:
    """Doble cinturon: el log rechaza el evento (`docs/03` §6.1) y la maquina la transicion."""
    log = LogEventos(actuacion_id=ACT)
    with pytest.raises(Exception, match="actor humano"):
        log.anadir("FirmaRegistrada", {}, actor=MOTOR, ocurrido_en=INSTANTE)


# ---------------------------------------------------------------------------
# 5. Invariante 2: LISTA_PARA_ENVIO exige las dos condiciones
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("veredicto", ["SUBSANABLE", "BLOQUEADO", "NO_ELEGIBLE", None])
def test_sin_veredicto_prevalidado_no_hay_lista_para_envio(veredicto: str | None) -> None:
    partida = en_estado("EVALUADA", veredicto=veredicto, revisada_por_humano=True)
    with pytest.raises(ErrorEstado, match="exige veredicto PREVALIDADO"):
        aplicar(partida, suceso("PayloadConstruido"))


def test_sin_revision_humana_no_hay_lista_para_envio() -> None:
    partida = en_estado("EVALUADA", veredicto="PREVALIDADO")
    with pytest.raises(ErrorEstado, match="revisado"):
        aplicar(partida, suceso("ManifiestoGenerado"))


def test_prevalidado_y_revisada_por_un_humano_si_llega_a_lista_para_envio() -> None:
    partida = en_estado("EVALUADA", veredicto="PREVALIDADO")
    revisada = aplicar(partida, suceso("ObservacionRegistrada", {"origen": ORIGEN_REVISION}, actor=HUMANO))
    assert revisada.revisada_por_humano is True
    assert aplicar(revisada, suceso("PayloadConstruido")).estado_ciclo == "LISTA_PARA_ENVIO"


@pytest.mark.parametrize("actor", [MOTOR, AGENTE, PLATAFORMA], ids=lambda a: a.clase)
def test_una_maquina_no_puede_declarar_que_un_humano_reviso(actor: Actor) -> None:
    payload = dict(PAYLOAD_AGENTE) if actor.clase == "agente" else {}
    with pytest.raises(ErrorEstado, match="actor humano"):
        aplicar(
            en_estado("EVALUADA", veredicto="PREVALIDADO"),
            suceso("ObservacionRegistrada", {**payload, "origen": ORIGEN_REVISION}, actor=actor),
        )


def test_una_observacion_cualquiera_no_mueve_el_ciclo() -> None:
    partida = en_estado("EN_PROCESO")
    despues = aplicar(partida, suceso("ObservacionRegistrada", {"origen": "consolidacion"}))
    assert despues.estado_ciclo == "EN_PROCESO"
    assert despues.revisada_por_humano is False


def test_escalado_lleva_a_revision_humana_y_la_revision_devuelve_a_evaluada() -> None:
    escalada = aplicar(
        en_estado("EVALUADA", veredicto="PREVALIDADO"),
        suceso("ObservacionRegistrada", {"origen": ORIGEN_ESCALADO}),
    )
    assert escalada.estado_ciclo == "EN_REVISION_HUMANA"
    vuelta = aplicar(escalada, suceso("ObservacionRegistrada", {"origen": ORIGEN_REVISION}, actor=HUMANO))
    assert vuelta.estado_ciclo == "EVALUADA"
    assert vuelta.revisada_por_humano is True


def test_descartada_exige_no_elegible_confirmado_por_un_humano() -> None:
    descarte = suceso("ObservacionRegistrada", {"origen": ORIGEN_DESCARTE}, actor=HUMANO)
    with pytest.raises(ErrorEstado, match="NO_ELEGIBLE"):
        aplicar(en_estado("EVALUADA", veredicto="SUBSANABLE"), descarte)
    final = aplicar(en_estado("EVALUADA", veredicto="NO_ELEGIBLE"), descarte)
    assert final.estado_ciclo == "DESCARTADA"


# ---------------------------------------------------------------------------
# 6. Invariante 3: inalterabilidad post-firma (docs/02 §5.4)
# ---------------------------------------------------------------------------

CAMBIOS_DE_DATOS = [
    ("DocumentoRegistrado", {"sha256": "c" * 64}, MOTOR),
    ("DatoConsolidado", {"variable": "P"}, MOTOR),
    ("DatoCorregidoPorHumano", {"variable": "P"}, HUMANO),
    ("CalculoRealizado", {"unidades": 1}, MOTOR),
    ("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, MOTOR),
]


@pytest.mark.parametrize(("tipo", "payload", "actor"), CAMBIOS_DE_DATOS, ids=lambda v: str(v)[:24])
def test_tras_en_plataforma_un_cambio_de_datos_se_rechaza(tipo: str, payload: dict, actor: Actor) -> None:
    partida = en_estado("EN_PLATAFORMA", firmada=True, estado_plataforma="ENVIADA_A_VERIFICACION")
    despues = aplicar(partida, suceso(tipo, payload, actor=actor))
    assert despues.estado_ciclo == "EN_PLATAFORMA", "un cambio post-firma no mueve el ciclo"
    assert len(despues.rechazos) == 1
    rechazo = despues.rechazos[0]
    assert rechazo["tipo"] == tipo
    assert "inalterabilidad" in str(rechazo["motivo"])


def test_el_rechazo_post_firma_alimenta_correccion_rechazada_post_firma() -> None:
    """El rechazo no se pierde: es el payload del evento `CorreccionRechazadaPostFirma` (`docs/02` §5.4)."""
    partida = en_estado("EN_PLATAFORMA", firmada=True)
    despues = aplicar(partida, suceso("DatoCorregidoPorHumano", {"variable": "P"}, actor=HUMANO))
    log = LogEventos(actuacion_id=ACT)
    evento = log.anadir(
        "CorreccionRechazadaPostFirma", dict(despues.rechazos[0]), actor=MOTOR, ocurrido_en=INSTANTE
    )
    assert evento.datos["tipo"] == "DatoCorregidoPorHumano"
    # Y el propio evento de rechazo no mueve nada.
    assert aplicar(despues, evento).estado_ciclo == "EN_PLATAFORMA"


def test_con_un_requerimiento_abierto_la_correccion_si_se_admite() -> None:
    """Solo el sujeto modifica, y solo via requerimiento oficial (`docs/02` §5.4)."""
    firmada = en_estado("EN_PLATAFORMA", firmada=True)
    requerida = aplicar(
        firmada, suceso("EstadoPlataformaRecibido", {"estado": "PDTE_RECTIFICACION_VER"}, actor=PLATAFORMA)
    )
    assert requerida.estado_ciclo == "PENDIENTE_SUBSANACION"
    assert requerida.origen_subsanacion == "verificador"
    corregida = aplicar(requerida, suceso("DatoCorregidoPorHumano", {"variable": "P"}, actor=HUMANO))
    assert corregida.estado_ciclo == "EN_PROCESO"
    assert corregida.rechazos == ()
    cerrada = aplicar(corregida, suceso("SubsanacionCerrada", {"origen": "verificador"}))
    assert cerrada.requerimiento_abierto is None
    # Cerrada la subsanacion, vuelve a regir la inalterabilidad.
    assert aplicar(cerrada, suceso("DocumentoRegistrado", {"sha256": "d" * 64})).rechazos


def test_antes_de_la_firma_no_hay_inalterabilidad() -> None:
    entregada = en_estado("ENTREGADA", via_entrega="API", estado_plataforma="COMPLETA")
    despues = aplicar(entregada, suceso("DocumentoRegistrado", {"sha256": "e" * 64}))
    assert despues.estado_ciclo == "EN_PROCESO"
    assert despues.rechazos == ()


# ---------------------------------------------------------------------------
# 7. Invariante 4: contagio de un requerimiento de GA o CN
# ---------------------------------------------------------------------------


def expediente_de_tres() -> tuple[Proyeccion, ...]:
    return tuple(
        replace(inicial(f"ACT-{n}"), estado_ciclo="EN_PLATAFORMA", firmada=True, expediente_id="EXP-1")
        for n in (1, 2, 3)
    )


@pytest.mark.parametrize("literal", ["REQUERIDO_GA", "REQUERIDO_CN"])
def test_un_requerimiento_de_ga_o_cn_contagia_a_todo_el_expediente(literal: str) -> None:
    evento = suceso(
        "EstadoPlataformaRecibido",
        {"estado": literal, "expediente_id": "EXP-1"},
        actor=PLATAFORMA,
        actuacion="ACT-2",
        secuencia=9,
    )
    contagiadas = propagar_requerimiento(expediente_de_tres(), evento)
    assert [p.estado_ciclo for p in contagiadas] == ["PENDIENTE_SUBSANACION"] * 3
    assert {p.origen_subsanacion for p in contagiadas} == {literal.removeprefix("REQUERIDO_")}
    directas = {p.actuacion_id: p.afectada_directamente for p in contagiadas}
    assert directas == {"ACT-1": False, "ACT-2": True, "ACT-3": False}
    assert all(p.requerimiento_abierto for p in contagiadas)
    assert all(p.secuencia == 9 for p in contagiadas)


def test_el_contagio_no_toca_el_estado_de_plataforma_de_cada_actuacion() -> None:
    """`REQUERIDO_GA` es un estado del **expediente**: no es el estado de plataforma de cada actuacion."""
    evento = suceso(
        "EstadoPlataformaRecibido", {"estado": "REQUERIDO_GA"}, actor=PLATAFORMA, actuacion="ACT-1"
    )
    contagiadas = propagar_requerimiento(expediente_de_tres(), evento)
    assert all(p.estado_plataforma is None for p in contagiadas)


def test_el_contagio_respeta_las_actuaciones_terminales() -> None:
    cerrada = replace(inicial("ACT-9"), estado_ciclo="CERRADA", resultado="inscrita")
    evento = suceso("RequerimientoRecibido", {"origen": "CN"}, actor=PLATAFORMA, actuacion="ACT-1")
    contagiadas = propagar_requerimiento((*expediente_de_tres(), cerrada), evento)
    assert contagiadas[-1] == cerrada
    assert [p.estado_ciclo for p in contagiadas[:-1]] == ["PENDIENTE_SUBSANACION"] * 3


def test_las_actuaciones_senaladas_se_pueden_dar_explicitas() -> None:
    evento = suceso("RequerimientoRecibido", {"origen": "GA"}, actor=PLATAFORMA, actuacion="ACT-1")
    contagiadas = propagar_requerimiento(expediente_de_tres(), evento, directas=("ACT-1", "ACT-3"))
    assert [p.afectada_directamente for p in contagiadas] == [True, False, True]


@pytest.mark.parametrize("origen", ["interno", "verificador"])
def test_un_requerimiento_interno_o_del_verificador_no_contagia_al_expediente(origen: str) -> None:
    evento = suceso("RequerimientoRecibido", {"origen": origen}, actor=PLATAFORMA, actuacion="ACT-1")
    with pytest.raises(ErrorEstado, match="no contagia"):
        propagar_requerimiento(expediente_de_tres(), evento)


def test_un_literal_sin_alcance_de_expediente_no_contagia() -> None:
    evento = suceso(
        "EstadoPlataformaRecibido", {"estado": "PDTE_RECTIFICACION_VER"}, actor=PLATAFORMA, actuacion="ACT-1"
    )
    with pytest.raises(ErrorEstado, match="alcance"):
        propagar_requerimiento(expediente_de_tres(), evento)


def test_solo_un_requerimiento_abre_un_contagio() -> None:
    with pytest.raises(ErrorEstado, match="no es un requerimiento"):
        propagar_requerimiento(expediente_de_tres(), suceso("VeredictoEmitido", {"veredicto": "PREVALIDADO"}))


def test_un_origen_de_subsanacion_inventado_es_error() -> None:
    with pytest.raises(ErrorEstado, match="origen"):
        aplicar(en_estado("EVALUADA"), suceso("SubsanacionSolicitada", {"origen": "jefatura"}))


def test_una_subsanacion_interna_deja_el_origen_registrado() -> None:
    despues = aplicar(en_estado("EVALUADA"), suceso("SubsanacionSolicitada", {"origen": "interno"}))
    assert despues.estado_ciclo == "PENDIENTE_SUBSANACION"
    assert despues.origen_subsanacion == "interno"


# ---------------------------------------------------------------------------
# 8. Invariante 5: un literal desconocido no se descarta
# ---------------------------------------------------------------------------


def test_un_literal_desconocido_escala_a_revision_humana_y_queda_registrado() -> None:
    partida = en_estado("EN_PLATAFORMA", firmada=True)
    despues = aplicar(
        partida, suceso("EstadoPlataformaRecibido", {"estado": "EN_TRAMITE_AUTONOMICO"}, actor=PLATAFORMA)
    )
    assert despues.estado_ciclo == "EN_REVISION_HUMANA"
    assert despues.estado_plataforma == "EN_TRAMITE_AUTONOMICO"
    assert despues.literales_desconocidos == ("EN_TRAMITE_AUTONOMICO",)


def test_un_literal_desconocido_no_se_anota_dos_veces() -> None:
    evento = suceso("EstadoPlataformaRecibido", {"estado": "EN_TRAMITE_AUTONOMICO"}, actor=PLATAFORMA)
    una = aplicar(en_estado("EN_PLATAFORMA", firmada=True), evento)
    dos = aplicar(una, evento)
    assert dos.literales_desconocidos == ("EN_TRAMITE_AUTONOMICO",)


def test_un_literal_desconocido_sobre_una_actuacion_cerrada_se_registra_sin_moverla() -> None:
    cerrada = en_estado("CERRADA", resultado="inscrita")
    despues = aplicar(cerrada, suceso("EstadoPlataformaRecibido", {"estado": "REABIERTO"}, actor=PLATAFORMA))
    assert despues.estado_ciclo == "CERRADA"
    assert despues.literales_desconocidos == ("REABIERTO",)


def test_un_estado_plataforma_sin_literal_es_error() -> None:
    with pytest.raises(ErrorEstado, match="no trae el literal"):
        aplicar(
            en_estado("EN_PLATAFORMA", firmada=True),
            suceso("EstadoPlataformaRecibido", {}, actor=PLATAFORMA),
        )


# ---------------------------------------------------------------------------
# 9. Desistimiento (docs/02 §5.5)
# ---------------------------------------------------------------------------


def test_el_desistimiento_humano_cierra_la_actuacion_como_desistida() -> None:
    requerida = en_estado(
        "PENDIENTE_SUBSANACION", firmada=True, origen_subsanacion="GA", requerimiento_abierto="GA"
    )
    desistida = aplicar(requerida, suceso("DesistimientoRegistrado", {"motivo": "coste"}, actor=HUMANO))
    assert desistida.estado_ciclo == "CERRADA"
    assert desistida.resultado == "desistida"
    assert desistida.desistimiento_registrado is True
    literal = suceso("EstadoPlataformaRecibido", {"estado": "DESISTIDO"}, actor=PLATAFORMA)
    reflejo = aplicar(desistida, literal)
    assert reflejo.estado_ciclo == "CERRADA"
    assert reflejo.estado_plataforma == "DESISTIDO"
    assert reflejo.resultado == "desistida"


@pytest.mark.parametrize("actor", [MOTOR, AGENTE, PLATAFORMA], ids=lambda a: a.clase)
def test_ninguna_maquina_desiste(actor: Actor) -> None:
    payload = dict(PAYLOAD_AGENTE) if actor.clase == "agente" else {}
    with pytest.raises(ErrorEstado, match="actor humano"):
        aplicar(
            en_estado("EN_PLATAFORMA", firmada=True),
            suceso("DesistimientoRegistrado", payload, actor=actor),
        )


def test_el_literal_desistido_exige_el_desistimiento_previo() -> None:
    with pytest.raises(ErrorEstado, match="DesistimientoRegistrado"):
        aplicar(
            en_estado("EN_PLATAFORMA", firmada=True),
            suceso("EstadoPlataformaRecibido", {"estado": "DESISTIDO"}, actor=PLATAFORMA),
        )


def test_el_literal_inscrito_cierra_como_inscrita() -> None:
    despues = aplicar(
        en_estado("EN_PLATAFORMA", firmada=True),
        suceso("EstadoPlataformaRecibido", {"estado": "INSCRITO"}, actor=PLATAFORMA),
    )
    assert despues.estado_ciclo == "CERRADA"
    assert despues.resultado == "inscrita"


# ---------------------------------------------------------------------------
# 10. La tabla YAML es la de docs/02 §5.6
# ---------------------------------------------------------------------------

#: `docs/02` §5.6, fila a fila: literal -> (estado de ciclo | None, origen de subsanacion | None).
PROYECCION_ESPERADA: dict[str, tuple[str | None, str | None]] = {
    "BORRADOR": ("ENTREGADA", None),
    "COMPLETA": ("ENTREGADA", None),
    "ENVIADA_A_VERIFICACION": ("EN_PLATAFORMA", None),
    "PDTE_RECTIFICACION_VER": ("PENDIENTE_SUBSANACION", "verificador"),
    "VERIFICACION_EN_PROCESO": (None, None),
    "VERIFICADA_FAVORABLE": (None, None),
    "VERIFICADA_DESFAVORABLE": ("CERRADA", None),
    "NO_PUEDE_EMITIR_DICTAMEN": ("CERRADA", None),
    "REQUERIDO_GA": ("PENDIENTE_SUBSANACION", "GA"),
    "REQUERIDO_CN": ("PENDIENTE_SUBSANACION", "CN"),
    "DESISTIDO": ("CERRADA", None),
    "INSCRITO": ("CERRADA", None),
    "BORRADOR_SOLICITUD": (None, None),
    "PRESENTADO": (None, None),
    "EN_VALIDACION_TECNICA": (None, None),
    "VALIDADO_GA": (None, None),
    "EN_REVISION_FORMAL": (None, None),
    "RESUELTO_FAVORABLE": (None, None),
    "RESUELTO_DESFAVORABLE": (None, None),
}


def test_la_tabla_de_proyeccion_es_la_de_la_documentacion() -> None:
    tabla = tabla_plataforma()
    assert set(tabla) == set(PROYECCION_ESPERADA)
    for literal, (ciclo, origen) in PROYECCION_ESPERADA.items():
        assert tabla[literal].ciclo == ciclo, literal
        assert tabla[literal].origen_subsanacion == origen, literal
        assert proyectar_estado_plataforma(literal) == ciclo, literal


def test_proyectar_estado_plataforma_no_inventa_nada_para_un_literal_desconocido() -> None:
    assert proyectar_estado_plataforma("EN_TRAMITE_AUTONOMICO") is None


def bloques_del_yaml() -> dict[str, list[str]]:
    """Las lineas crudas de cada fila, para poder mirar los comentarios (que YAML descarta)."""
    bloques: dict[str, list[str]] = {}
    actual: str | None = None
    for linea in RUTA_TABLA.read_text(encoding="utf-8").splitlines():
        if linea.strip().startswith("- literal:"):
            actual = linea.split(":", 1)[1].strip()
            bloques[actual] = [linea]
        elif actual is not None and linea.strip():
            bloques[actual].append(linea)
    return bloques


def test_cada_estado_provisional_lleva_su_todo_api_03() -> None:
    bloques = bloques_del_yaml()
    for literal in EXPEDIENTE_ESPERADOS:
        texto = "\n".join(bloques[literal])
        assert "oficial: false" in texto, f"{literal} deberia ser provisional"
        assert "TODO(API-03)" in texto, f"{literal} no lleva su TODO(API-03)"
        assert tabla_plataforma()[literal].oficial is False


def test_los_ocho_confirmados_no_llevan_todo_ni_oficial_false() -> None:
    bloques = bloques_del_yaml()
    for literal in ACTUACION_ESPERADOS:
        texto = "\n".join(bloques[literal])
        assert "oficial: true" in texto, f"{literal} es un estado confirmado"
        assert "TODO(API-03)" not in texto, f"{literal} esta confirmado: no es un hueco"
        assert tabla_plataforma()[literal].oficial is True


def test_la_tabla_declara_todos_los_estados_en_los_dos_niveles() -> None:
    tabla = tabla_plataforma()
    assert {f.nivel for f in tabla.values()} == {"actuacion", "expediente"}
    assert all(f.nota for f in tabla.values()), "cada fila dice de donde sale"


TABLAS_MALAS = [
    ("- literal: X\n  nivel: actuacion\n  fase: '1A'\n  oficial: true\n  ciclo: EN_TRAMITE\n", "inexistente"),
    ("- literal: X\n  nivel: expediente\n  fase: '2'\n  oficial: true\n  ciclo: null\n", "nunca"),
    ("- literal: X\n  nivel: sector\n  fase: '2'\n  oficial: false\n  ciclo: null\n", "nivel"),
    ("- literal: X\n  nivel: actuacion\n  fase: '1A'\n  oficial: true\n", "faltan"),
    (
        "- literal: X\n  nivel: actuacion\n  fase: '1A'\n  oficial: true\n  ciclo: null\n  color: azul\n",
        "no admitidas",
    ),
    (
        "- literal: X\n  nivel: actuacion\n  fase: '1A'\n  oficial: true\n  ciclo: null\n"
        "- literal: X\n  nivel: actuacion\n  fase: '1A'\n  oficial: true\n  ciclo: null\n",
        "dos veces",
    ),
]


@pytest.mark.parametrize(("filas", "mensaje"), TABLAS_MALAS, ids=lambda v: str(v)[:20])
def test_una_tabla_mal_formada_es_un_error_de_carga(filas: str, mensaje: str, tmp_path: Path) -> None:
    ruta = tmp_path / "tabla.yaml"
    ruta.write_text("version_tabla: '1.0'\nestados:\n" + filas, encoding="utf-8")
    tabla_plataforma.cache_clear()
    try:
        with pytest.raises(ErrorEstado, match=mensaje):
            tabla_plataforma(ruta)
    finally:
        tabla_plataforma.cache_clear()


def test_una_tabla_que_no_existe_lo_dice(tmp_path: Path) -> None:
    tabla_plataforma.cache_clear()
    try:
        with pytest.raises(ErrorEstado, match="no encuentro"):
            tabla_plataforma(tmp_path / "no-esta.yaml")
    finally:
        tabla_plataforma.cache_clear()


def test_el_yaml_es_valido_y_declara_sus_fuentes() -> None:
    datos = yaml.safe_load(RUTA_TABLA.read_text(encoding="utf-8"))
    assert datos["version_tabla"] == "1.0"
    assert any("§5.6" in f for f in datos["fuentes"])
    assert len(datos["estados"]) == len(ACTUACION_ESPERADOS) + len(EXPEDIENTE_ESPERADOS)


# ---------------------------------------------------------------------------
# 11. Higiene del fuente
# ---------------------------------------------------------------------------


def test_sin_eval_exec_compile_ni_float() -> None:
    codigo = FUENTE.read_text(encoding="utf-8")
    for prohibido in ("eval(", "exec(", "compile(", "float(", "import ast", "from ast"):
        assert prohibido not in codigo, f"engine/estados.py usa {prohibido}"


def test_no_importa_hacia_fuera() -> None:
    codigo = FUENTE.read_text(encoding="utf-8")
    for paquete in ("agentes", "salida", "generator", "tests"):
        assert f"import {paquete}" not in codigo
        assert f"from {paquete}" not in codigo


def test_sin_ramas_por_ficha() -> None:
    codigo = FUENTE.read_text(encoding="utf-8")
    assert "if ficha ==" not in codigo
    assert "IND240" not in codigo


def test_ningun_reloj_en_la_maquina_de_estados() -> None:
    """`aplicar` es pura: el instante lo trae el evento, no el reloj de la maquina."""
    codigo = FUENTE.read_text(encoding="utf-8")
    assert "now(" not in codigo
    assert "ahora_utc" not in codigo
