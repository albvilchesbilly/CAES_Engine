"""Banco de pruebas del log de eventos (N8): `engine/eventos/**` (S3.1 pieza B, `ADR-004` C2).

Que cubre, en el orden del contrato:

- **JSON canonico**: claves ordenadas, `Decimal` como cadena, instantes en UTC con `Z`, sin `float`.
- **Cadena de hash**: 100 eventos encadenados; alterar payload, tipo, secuencia u `ocurrido_en` de uno
  cualquiera rompe `verificar()` y el mensaje dice **que eslabon**.
- **Catalogo cerrado** y clases de actor cerradas; los tres eventos que solo son validos con actor humano y
  la confirmacion de A9; el contrato de los eventos de agente (`modelo`, `version_prompt`, `coste`,
  `latencia`), que se fija antes de que exista ningun agente.
- **Solo-anadir**: no hay API publica para borrar ni editar, `eventos` es inmutable y `Evento` es frozen.
- **JSONL**: `a_jsonl` → `desde_jsonl` reproduce el log exacto y `verificar()` sigue pasando.
- **Grabacion**: los eventos que produce una ejecucion del motor, `DocumentoRegistrado` **siempre** con su
  `sha256`, un solo instante por ejecucion y el mismo log byte a byte en dos grabaciones iguales; y que
  `motor.py` no la llama (el enganche es de la oleada siguiente, `ADR-004`).
- **Replay de los 7 casos**: `grabar` sobre `procesar_actuacion(..., ocr=False)` y `reproducir` dan la misma
  evaluacion comparada por `json_canonico`, con el caso A en `Decimal("305829.6")`. El replay no abre ningun
  fichero: `open` esta cortado durante la reproduccion.
- **Higiene**: sin `eval`/`exec`/`compile`/`float`, sin importar hacia fuera, sin nombres de ficha.

Los siete casos se procesan **una vez** por sesion (fixture `casos_procesados`, `ocr=False` como exige
`docs/05` §8.2) y los tests de replay reutilizan ese resultado.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from engine.eventos import (
    CAMPOS_AGENTE,
    CLASES_ACTOR,
    PROCESO_DE_TIPO,
    TIPOS,
    TIPOS_ADMINISTRACION,
    TIPOS_POR_PROCESO,
    TIPOS_SOLO_HUMANO,
    Actor,
    ErrorEvento,
    Evento,
    LogEventos,
    calcular_hash,
    codificar,
    decodificar,
    divergencias,
    grabar,
    json_canonico,
    reproducir,
)
from engine.eventos.canonico import instante_desde_texto, texto_instante
from engine.eventos.catalogo import GRUPOS_ADMINISTRACION
from engine.eventos.replay import consolidada_de, identidad_spec_de, verificar_replay
from tests.apoyo_permisos import humano_para

RAIZ = Path(__file__).resolve().parents[1]
FUENTES_EVENTOS = sorted((RAIZ / "engine" / "eventos").rglob("*.py"))
CARPETA_CASOS = RAIZ / "expedientes"

CASOS = (
    "EXP001-A_completo",
    "EXP001-B_falta_registro",
    "EXP001-C_contradictorio",
    "EXP001-D_fuera_ambito",
    "EXP001-E_dos_motores",
    "EXP001-F_tres_motores",
    "EXP001-G_desordenado",
)
CASO_A = "EXP001-A_completo"
AETOTAL_A = Decimal("305829.6")

#: Instante fijo de las grabaciones de prueba: el log no debe depender del reloj.
INSTANTE = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
ACTOR_MOTOR = Actor("motor", "engine@pruebas")
#: El revisor tecnico (`T-REV`): es quien corrige datos (CAP-05/06) y quien confirma una interpretacion de
#: A9 (CAP-15), que son los dos actos humanos que prueba este fichero con un actor fijo. Desde A8 un actor
#: humano sin `rol` no puede escribir: los tests parametrizados sacan el suyo de la matriz (`humano_para`).
ACTOR_HUMANO = Actor("humano", "revisor@cae", rol="T-REV")
ACTOR_AGENTE = Actor("agente", "lector@prompt-v3")
PAYLOAD_AGENTE = {
    "modelo": "modelo-x",
    "version_prompt": "v3",
    "coste": Decimal("0.0021"),
    "latencia": Decimal("1.35"),
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def casos_procesados() -> dict[str, object]:
    """Los 7 casos procesados una sola vez, sin OCR (`docs/05` §8.2)."""
    from engine.motor import procesar_actuacion
    from engine.spec_registry import SpecRegistry

    registro = SpecRegistry()
    registro.cargar_todas()
    return {caso: procesar_actuacion(CARPETA_CASOS / caso, ocr=False, registro=registro) for caso in CASOS}


@pytest.fixture(scope="session")
def logs_de_casos(casos_procesados: dict[str, object]) -> dict[str, LogEventos]:
    return {caso: grabar(actuacion, instante=INSTANTE) for caso, actuacion in casos_procesados.items()}


def log_corto(n: int = 3, actuacion_id: str = "ACT-001") -> LogEventos:
    log = LogEventos(actuacion_id)
    for i in range(n):
        log.anadir(
            "ObservacionRegistrada",
            {"texto": f"observacion {i}", "importe": Decimal(f"{i}.50")},
            actor=ACTOR_MOTOR,
            ocurrido_en=INSTANTE + timedelta(seconds=i),
        )
    return log


# ---------------------------------------------------------------------------
# JSON canonico
# ---------------------------------------------------------------------------


def test_json_canonico_no_depende_del_orden_de_las_claves() -> None:
    uno = {"b": 1, "a": {"z": [1, 2], "y": "ñ"}}
    otro = {"a": {"y": "ñ", "z": [1, 2]}, "b": 1}
    assert json_canonico(uno) == json_canonico(otro)
    assert json_canonico(uno) == '{"a":{"y":"ñ","z":[1,2]},"b":1}'


def test_json_canonico_sin_espacios_y_en_utf8() -> None:
    texto = json_canonico({"razon_social": "Cañería S.L.", "n": 2})
    assert ", " not in texto and '": ' not in texto
    assert "Cañería" in texto  # ensure_ascii=False


def test_json_canonico_decimal_como_cadena() -> None:
    assert json_canonico(Decimal("305829.6")) == '"305829.6"'
    assert json_canonico({"aetotal": Decimal("305829.6")}) == '{"aetotal":"305829.6"}'


def test_json_canonico_fechas_e_instantes() -> None:
    assert json_canonico(date(2026, 3, 2)) == '"2026-03-02"'
    # Decision documentada: el instante se escribe en UTC con `Z` (`docs/03` §6.1).
    assert json_canonico(datetime(2026, 9, 19, 8, 0, tzinfo=UTC)) == '"2026-09-19T08:00:00Z"'
    otra_zona = datetime(2026, 9, 19, 10, 0, tzinfo=timezone(timedelta(hours=2)))
    assert json_canonico(otra_zona) == '"2026-09-19T08:00:00Z"'


def test_json_canonico_rechaza_float_y_tipos_opacos() -> None:
    with pytest.raises(ErrorEvento, match="float"):
        json_canonico({"segundos": 1.25})
    with pytest.raises(ErrorEvento, match="no serializable"):
        json_canonico({"ruta": Path("/tmp")})


def test_json_canonico_instante_naive_es_error() -> None:
    with pytest.raises(ErrorEvento, match="sin zona"):
        json_canonico(datetime(2026, 9, 19, 8, 0))


def test_codificar_y_decodificar_conservan_los_tipos() -> None:
    original = {
        "ahorro": Decimal("305829.6"),
        "escala": Decimal("110.00"),
        "fecha": date(2026, 3, 2),
        "instante": INSTANTE,
        "lista": [Decimal("1"), None, True, "texto", 7],
        "anidado": {"x": {"y": Decimal("0.75")}},
    }
    codificado = codificar(original)
    assert json.loads(json.dumps(codificado)) == codificado  # JSON puro
    vuelto = decodificar(codificado)
    assert vuelto == original
    assert str(vuelto["escala"]) == "110.00"  # la escala del Decimal no se pierde


def test_codificar_rechaza_float() -> None:
    with pytest.raises(ErrorEvento, match="float"):
        codificar({"latencia": 0.5})


def test_texto_instante_y_su_inverso() -> None:
    assert texto_instante(INSTANTE) == "2026-09-19T08:00:00Z"
    assert instante_desde_texto("2026-09-19T08:00:00Z") == INSTANTE
    assert instante_desde_texto("2026-09-19T08:00:00+00:00") == INSTANTE
    with pytest.raises(ErrorEvento):
        instante_desde_texto("2026-09-19 08:00 (sin zona)")


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------


def test_calcular_hash_es_reproducible_y_depende_del_previo() -> None:
    sobre = {"tipo": "ObservacionRegistrada", "payload": {"a": 1}}
    assert calcular_hash(sobre, "") == calcular_hash({"payload": {"a": 1}, "tipo": sobre["tipo"]}, "")
    assert calcular_hash(sobre, "") != calcular_hash(sobre, "abc")
    assert len(calcular_hash(sobre, "")) == 64


def test_calcular_hash_ignora_la_clave_hash() -> None:
    sobre = {"tipo": "ObservacionRegistrada", "payload": {}}
    assert calcular_hash(sobre, "") == calcular_hash({**sobre, "hash": "loquesea"}, "")


def test_primer_hash_previo_es_la_cadena_vacia() -> None:
    log = log_corto(1)
    assert log.eventos[0].hash_previo == ""


def test_cadena_de_cien_eventos_verifica() -> None:
    log = LogEventos("ACT-100")
    for i in range(100):
        log.anadir("ObservacionRegistrada", {"i": i}, actor=ACTOR_MOTOR, ocurrido_en=INSTANTE)
    assert len(log) == 100
    assert [e.secuencia for e in log.eventos] == list(range(1, 101))
    assert [e.hash_previo for e in log.eventos][1:] == [e.hash for e in log.eventos][:-1]
    log.verificar()


def _log_alterado(posicion: int, **cambios: object) -> LogEventos:
    log = LogEventos("ACT-100")
    for i in range(100):
        log.anadir("ObservacionRegistrada", {"i": i}, actor=ACTOR_MOTOR, ocurrido_en=INSTANTE)
    eventos = list(log.eventos)
    eventos[posicion - 1] = dataclasses.replace(eventos[posicion - 1], **cambios)
    return LogEventos("ACT-100", eventos)


@pytest.mark.parametrize(
    ("cambios", "senal"),
    [
        ({"payload": {"i": 999}}, "no corresponde a su contenido"),
        ({"tipo": "ConflictoDetectado"}, "no corresponde a su contenido"),
        ({"ocurrido_en": INSTANTE + timedelta(hours=1)}, "no corresponde a su contenido"),
        ({"secuencia": 99}, "secuencia"),
        ({"hash": "0" * 64}, "no corresponde a su contenido"),
        ({"actor": Actor("humano", "impostor", rol="T-RES")}, "no corresponde a su contenido"),
    ],
    ids=["payload", "tipo", "ocurrido_en", "secuencia", "hash", "actor"],
)
def test_alterar_un_eslabon_rompe_verificar(cambios: dict, senal: str) -> None:
    log = _log_alterado(37, **cambios)
    with pytest.raises(ErrorEvento) as fallo:
        log.verificar()
    mensaje = str(fallo.value)
    assert "eslabon 37" in mensaje, mensaje
    assert senal in mensaje, mensaje


def test_verificar_senala_el_primer_eslabon_roto() -> None:
    log = LogEventos("ACT-100")
    for i in range(10):
        log.anadir("ObservacionRegistrada", {"i": i}, actor=ACTOR_MOTOR, ocurrido_en=INSTANTE)
    eventos = list(log.eventos)
    eventos[2] = dataclasses.replace(eventos[2], payload={"i": "x"})
    eventos[6] = dataclasses.replace(eventos[6], payload={"i": "y"})
    with pytest.raises(ErrorEvento, match="eslabon 3"):
        LogEventos("ACT-100", eventos).verificar()


def test_eliminar_un_evento_rompe_la_cadena() -> None:
    log = log_corto(5)
    sin_el_tercero = [e for e in log.eventos if e.secuencia != 3]
    with pytest.raises(ErrorEvento, match="eslabon 3"):
        LogEventos("ACT-001", sin_el_tercero).verificar()


def test_evento_de_otra_actuacion_rompe_la_cadena() -> None:
    otro = log_corto(1, actuacion_id="ACT-OTRA").eventos[0]
    with pytest.raises(ErrorEvento, match="actuacion"):
        LogEventos("ACT-001", [otro]).verificar()


# ---------------------------------------------------------------------------
# Catalogo, actores y contratos de payload
# ---------------------------------------------------------------------------


def test_catalogo_cerrado_cubre_los_procesos_de_docs_03() -> None:
    procesos = {clave.split(" ", 1)[0] for clave in TIPOS_POR_PROCESO}
    # P0-P10 son los procesos del Engine; G1-G3 son los grupos de gobierno que anade `ADR-006` con A8
    # (S3.1b): no los produce ninguna ejecucion del motor, los escribe una persona con un perfil.
    assert procesos == {f"P{n}" for n in range(11)} | {"G1", "G2", "G3"}
    assert set(GRUPOS_ADMINISTRACION) <= set(TIPOS_POR_PROCESO)
    assert TIPOS == frozenset(PROCESO_DE_TIPO)
    for imprescindible in (
        "ActuacionAbierta",
        "DocumentoRegistrado",
        "DocumentoClasificado",
        "PdfSeparado",
        "EvidenciaPropuesta",
        "FichaAsignada",
        "DatoConsolidado",
        "ConflictoDetectado",
        "CalculoRealizado",
        "VeredictoEmitido",
        "FirmaRegistrada",
        "DesistimientoRegistrado",
        "DatoCorregidoPorHumano",
    ):
        assert imprescindible in TIPOS


def test_tipo_desconocido_es_error_al_anadir() -> None:
    log = LogEventos("ACT-001")
    with pytest.raises(ErrorEvento, match="no declarado"):
        log.anadir("ActuacionInventada", {}, actor=ACTOR_MOTOR, ocurrido_en=INSTANTE)
    assert len(log) == 0


def test_tipo_desconocido_se_puede_leer_pero_no_escribir() -> None:
    log = log_corto(2)
    assert log.por_tipo("TipoQueYaNoExiste") == ()
    assert log.ultimo("TipoQueYaNoExiste") is None


def test_clase_de_actor_desconocida_es_error() -> None:
    with pytest.raises(ErrorEvento, match="clase de actor desconocida"):
        Actor("robot", "x")
    log = LogEventos("ACT-001")
    with pytest.raises(ErrorEvento, match="clase de actor desconocida"):
        log.anadir("ObservacionRegistrada", {}, actor={"clase": "robot", "id": "x"}, ocurrido_en=INSTANTE)
    assert CLASES_ACTOR == ("humano", "motor", "agente", "plataforma")


def test_los_actos_humanos_se_declaran_en_un_solo_sitio() -> None:
    """`TIPOS_SOLO_HUMANO` (y la confirmacion de A9) viven en `catalogo.py` y en ningun otro fuente."""
    # Los tres de S3.1 y, desde S3.1b (A8, `ADR-006`), los de las capacidades que ejerce una persona.
    # La lista se escribe entera a mano: es un contrato, y que crezca tiene que costar una linea aqui.
    assert set(TIPOS_SOLO_HUMANO) == {
        "DatoCorregidoPorHumano",
        "DesistimientoRegistrado",
        "FirmaRegistrada",
        "ObservacionRevisada",
        "ActuacionDescartada",
        "RevisionAprobada",
        "DiscrepanciaResuelta",
        "ExpedienteAprobado",
        "UsuarioAlta",
        "UsuarioBaja",
        "RolAsignado",
        "ActuacionReasignada",
        "PoliticaTenantCambiada",
        "AccesoSoporteAutorizado",
        "AccesoSoporteDenegado",
        "SpecActivada",
        "AgenteActivado",
        "AgenteDesactivado",
        "PromptActivado",
        "UmbralCambiado",
        "TenantAlta",
        "TenantBaja",
        "TenantSuspendido",
        "CapacidadActualizada",
        "AccesoSoporteSolicitado",
        "AccesoSoporteUsado",
    }
    assert set(TIPOS_SOLO_HUMANO) <= TIPOS
    # Todo evento de administracion es un acto humano: es lo que hace cierto el criterio de `docs/06`
    # S3.1b "ningun evento de administracion carece de `actor.rol`".
    assert TIPOS_ADMINISTRACION <= set(TIPOS_SOLO_HUMANO)
    catalogo = RAIZ / "engine" / "eventos" / "catalogo.py"
    for fuente in FUENTES_EVENTOS:
        if fuente == catalogo:
            continue
        codigo = fuente.read_text(encoding="utf-8")
        for tipo in TIPOS_SOLO_HUMANO:
            assert f'"{tipo}"' not in codigo, f"{fuente.name} repite el acto humano {tipo}"


@pytest.mark.parametrize("tipo", TIPOS_SOLO_HUMANO)
@pytest.mark.parametrize("clase", ["motor", "agente", "plataforma"])
def test_eventos_de_acto_humano_rechazan_a_la_maquina(tipo: str, clase: str) -> None:
    log = LogEventos("ACT-001")
    actor = Actor(clase, "quien-sea")
    payload = dict(PAYLOAD_AGENTE) if clase == "agente" else {}
    with pytest.raises(ErrorEvento, match="actor humano"):
        log.anadir(tipo, payload, actor=actor, ocurrido_en=INSTANTE)
    assert len(log) == 0


@pytest.mark.parametrize("tipo", TIPOS_SOLO_HUMANO)
def test_eventos_de_acto_humano_con_actor_humano_se_anaden(tipo: str) -> None:
    log = LogEventos("ACT-001")
    # El rol sale de la matriz, no de un valor comodo: cada acto lo ejerce el perfil que `ADR-006` le da.
    actor = humano_para(tipo)
    evento = log.anadir(tipo, {"nota": "firmado en persona"}, actor=actor, ocurrido_en=INSTANTE)
    assert evento.actor.clase == "humano"
    assert evento.actor.rol == actor.rol
    assert log.ultimo(tipo) is evento
    log.verificar()


def test_confirmacion_de_interpretacion_de_a9_exige_humano() -> None:
    log = LogEventos("ACT-001")
    # A9 propone: es un agente y lleva su ficha de coste.
    log.anadir(
        "RequerimientoInterpretado",
        {**PAYLOAD_AGENTE, "confirmada": False, "resumen": "falta el registro"},
        actor=ACTOR_AGENTE,
        ocurrido_en=INSTANTE,
    )
    # La confirmacion es un acto humano.
    with pytest.raises(ErrorEvento, match="actor humano"):
        log.anadir(
            "RequerimientoInterpretado",
            {**PAYLOAD_AGENTE, "confirmada": True},
            actor=ACTOR_AGENTE,
            ocurrido_en=INSTANTE,
        )
    log.anadir(
        "RequerimientoInterpretado",
        {"confirmada": True},
        actor=ACTOR_HUMANO,
        ocurrido_en=INSTANTE,
    )
    log.verificar()
    assert len(log) == 2


@pytest.mark.parametrize("campo", CAMPOS_AGENTE)
def test_evento_de_agente_sin_la_ficha_del_modelo_es_error(campo: str) -> None:
    log = LogEventos("ACT-001")
    payload = {k: v for k, v in PAYLOAD_AGENTE.items() if k != campo}
    with pytest.raises(ErrorEvento, match=campo):
        log.anadir("EvidenciaPropuesta", payload, actor=ACTOR_AGENTE, ocurrido_en=INSTANTE)
    assert len(log) == 0


def test_evento_de_agente_completo_se_anade() -> None:
    log = LogEventos("ACT-001")
    evento = log.anadir("EvidenciaPropuesta", dict(PAYLOAD_AGENTE), actor=ACTOR_AGENTE, ocurrido_en=INSTANTE)
    assert evento.datos["coste"] == Decimal("0.0021")
    log.verificar()


def test_ocurrido_en_naive_es_error() -> None:
    log = LogEventos("ACT-001")
    with pytest.raises(ErrorEvento, match="sin zona"):
        log.anadir("ObservacionRegistrada", {}, actor=ACTOR_MOTOR, ocurrido_en=datetime(2026, 9, 19, 8, 0))
    assert len(log) == 0


def test_ocurrido_en_de_otra_zona_se_guarda_en_utc() -> None:
    log = LogEventos("ACT-001")
    evento = log.anadir(
        "ObservacionRegistrada",
        {},
        actor=ACTOR_MOTOR,
        ocurrido_en=datetime(2026, 9, 19, 10, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    assert evento.ocurrido_en == INSTANTE
    assert evento.ocurrido_en.tzinfo is UTC
    assert evento.a_dict()["ocurrido_en"] == "2026-09-19T08:00:00Z"


def test_ocurrido_en_por_defecto_es_utc_con_zona() -> None:
    evento = LogEventos("ACT-001").anadir("ObservacionRegistrada", {}, actor=ACTOR_MOTOR)
    assert evento.ocurrido_en.tzinfo is not None
    assert evento.ocurrido_en.utcoffset() == timedelta(0)


def test_payload_no_serializable_no_entra_en_el_log() -> None:
    log = LogEventos("ACT-001")
    with pytest.raises(ErrorEvento):
        log.anadir("ObservacionRegistrada", {"ruta": Path("/tmp")}, actor=ACTOR_MOTOR)
    with pytest.raises(ErrorEvento, match="float"):
        log.anadir("ObservacionRegistrada", {"segundos": 0.12}, actor=ACTOR_MOTOR)
    assert len(log) == 0


# ---------------------------------------------------------------------------
# Solo-anadir
# ---------------------------------------------------------------------------


def test_eventos_es_inmutable() -> None:
    log = log_corto(3)
    eventos = log.eventos
    assert isinstance(eventos, tuple)
    with pytest.raises(AttributeError):
        eventos.append(eventos[0])  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        eventos[0] = eventos[1]  # type: ignore[index]
    assert log.eventos == eventos  # nada cambio


def test_un_evento_no_se_puede_modificar() -> None:
    evento = log_corto(1).eventos[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        evento.tipo = "VeredictoEmitido"  # type: ignore[misc]
    with pytest.raises(TypeError):
        evento.payload["texto"] = "otro"  # type: ignore[index]


def test_no_hay_api_publica_para_borrar_ni_editar() -> None:
    prohibidos = {
        "borrar",
        "eliminar",
        "editar",
        "modificar",
        "actualizar",
        "reemplazar",
        "insertar",
        "limpiar",
        "pop",
        "remove",
        "clear",
        "sort",
        "reverse",
        "extend",
        "append",
    }
    publicos = {nombre for nombre in dir(LogEventos) if not nombre.startswith("_")}
    assert not (publicos & prohibidos), sorted(publicos & prohibidos)
    assert publicos == {
        "anadir",
        "a_jsonl",
        "desde_jsonl",
        "eventos",
        "hash_actual",
        "por_tipo",
        "ultimo",
        "verificar",
    }
    # Ni por la puerta de atras: el log no es una secuencia que se pueda asignar ni recortar.
    assert not hasattr(LogEventos, "__setitem__")
    assert not hasattr(LogEventos, "__delitem__")


def test_la_correccion_es_un_evento_nuevo() -> None:
    log = log_corto(1)
    original = log.eventos[0]
    log.anadir(
        "DatoCorregidoPorHumano",
        {"variable": "PM", "valor_anterior": Decimal("110"), "valor": Decimal("112")},
        actor=ACTOR_HUMANO,
        ocurrido_en=INSTANTE,
    )
    assert log.eventos[0] == original  # el pasado no se toca
    assert len(log) == 2
    log.verificar()


# ---------------------------------------------------------------------------
# JSONL
# ---------------------------------------------------------------------------


def test_jsonl_ida_y_vuelta() -> None:
    log = log_corto(12)
    texto = log.a_jsonl()
    assert texto.count("\n") == 12
    vuelto = LogEventos.desde_jsonl(texto)
    assert vuelto.actuacion_id == log.actuacion_id
    assert vuelto.eventos == log.eventos
    vuelto.verificar()
    assert vuelto.a_jsonl() == texto


def test_cada_linea_del_jsonl_es_un_evento_en_orden_de_secuencia() -> None:
    log = log_corto(5)
    lineas = [json.loads(linea) for linea in log.a_jsonl().splitlines()]
    assert [linea["secuencia"] for linea in lineas] == [1, 2, 3, 4, 5]
    assert all(linea["hash"] for linea in lineas)


def test_jsonl_alterado_a_mano_no_verifica() -> None:
    log = log_corto(4)
    texto = log.a_jsonl().replace("observacion 2", "observacion 2 (retocada)")
    with pytest.raises(ErrorEvento, match="eslabon 3"):
        LogEventos.desde_jsonl(texto).verificar()


def test_desde_jsonl_rechaza_una_linea_ilegible() -> None:
    with pytest.raises(ErrorEvento, match="linea 1"):
        LogEventos.desde_jsonl("{esto no es json}\n")


def test_evento_desde_dict_incompleto() -> None:
    with pytest.raises(ErrorEvento, match="incompleto"):
        Evento.desde_dict({"tipo": "ObservacionRegistrada"})


# ---------------------------------------------------------------------------
# Grabacion de una ejecucion del motor
# ---------------------------------------------------------------------------


def test_grabar_produce_los_eventos_del_proceso(logs_de_casos: dict[str, LogEventos]) -> None:
    log = logs_de_casos[CASO_A]
    log.verificar()
    tipos = [e.tipo for e in log.eventos]
    assert tipos[0] == "ActuacionAbierta"
    assert tipos[1] == "FichaAsignada"
    assert tipos[-1] == "VeredictoEmitido"
    for esperado in (
        "DocumentoRegistrado",
        "DocumentoClasificado",
        "EvidenciaPropuesta",
        "DatoConsolidado",
        "CalculoRealizado",
    ):
        assert esperado in tipos, esperado
    assert all(e.actor.clase == "motor" for e in log.eventos)
    assert all(e.tipo in TIPOS for e in log.eventos)


def test_todo_documento_registrado_lleva_su_sha256(
    logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    for caso, log in logs_de_casos.items():
        registrados = log.por_tipo("DocumentoRegistrado")
        assert len(registrados) == len(casos_procesados[caso].documentos)  # type: ignore[attr-defined]
        for evento in registrados:
            assert len(str(evento.datos["sha256"])) == 64, caso
            assert evento.datos["doc_id"]


def test_el_conflicto_del_caso_c_queda_en_el_log(logs_de_casos: dict[str, LogEventos]) -> None:
    log = logs_de_casos["EXP001-C_contradictorio"]
    conflictos = log.por_tipo("ConflictoDetectado")
    assert conflictos, "el caso C tiene un conflicto entre fuentes fiables"
    for evento in conflictos:
        datos = evento.datos
        assert len(datos["valores_por_fuente"]) >= 2  # las dos evidencias se conservan
        assert len(datos["evidencias"]) >= 2


def test_el_veredicto_emitido_lleva_veredicto_y_reglas(
    logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    for caso, log in logs_de_casos.items():
        emitido = log.ultimo("VeredictoEmitido")
        assert emitido is not None
        datos = emitido.datos
        assert datos["veredicto"] == casos_procesados[caso].veredicto  # type: ignore[attr-defined]
        assert datos["hash_reglas"]
        assert datos["resultados"]


def test_el_calculo_del_caso_a_va_en_el_log(logs_de_casos: dict[str, LogEventos]) -> None:
    calculo = logs_de_casos[CASO_A].ultimo("CalculoRealizado")
    assert calculo is not None
    assert calculo.datos["total"] == AETOTAL_A
    assert calculo.datos["total_cae"] == 305829


def test_grabar_dos_veces_da_el_mismo_log(casos_procesados: dict[str, object]) -> None:
    """El log no depende del reloj ni de la telemetria: con el mismo instante es el mismo artefacto."""
    uno = grabar(casos_procesados[CASO_A], instante=INSTANTE)
    otro = grabar(casos_procesados[CASO_A], instante=INSTANTE)
    assert uno.a_jsonl() == otro.a_jsonl()


def test_grabar_mira_el_reloj_una_sola_vez(casos_procesados: dict[str, object]) -> None:
    """Una ejecucion sincrona del motor es un acto: todos sus eventos comparten `ocurrido_en` en UTC."""
    log = grabar(casos_procesados[CASO_A])
    instantes = {e.ocurrido_en for e in log.eventos}
    assert len(instantes) == 1
    unico = instantes.pop()
    assert unico.tzinfo is not None and unico.utcoffset() == timedelta(0)


def test_grabar_rechaza_algo_que_no_es_una_actuacion() -> None:
    with pytest.raises(ErrorEvento, match="Actuacion"):
        grabar(object())


def test_un_documento_sin_huella_no_se_registra(casos_procesados: dict[str, object]) -> None:
    """`sha256` no es opcional: sin huella el documento no es trazable y la grabacion se detiene."""
    from engine.eventos.grabacion import _documento_a_payload

    doc = dataclasses.replace(casos_procesados[CASO_A].documentos[0], sha256="")  # type: ignore[attr-defined]
    with pytest.raises(ErrorEvento, match="sha256"):
        _documento_a_payload(doc)


def test_el_motor_no_llama_a_la_grabacion() -> None:
    """El enganche es de la oleada siguiente (`ADR-004`): hoy `grabar` se invoca desde fuera del motor."""
    codigo = (RAIZ / "engine" / "motor.py").read_text(encoding="utf-8")
    assert "engine.eventos" not in codigo
    assert "grabar(" not in codigo


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_replay_reproduce_la_evaluacion_bit_a_bit(
    caso: str, logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    actuacion = casos_procesados[caso]
    log = logs_de_casos[caso]
    reproducida = reproducir(log, actuacion.spec)  # type: ignore[attr-defined]
    esperado = json_canonico(actuacion.evaluacion.a_dict())  # type: ignore[attr-defined]
    # La comparacion es por `json_canonico`, no por `==` de objetos (`ADR-004` C2).
    assert json_canonico(reproducida.a_dict()) == esperado
    assert divergencias(log, reproducida) == ()
    # Y se reprodujo con **la misma** ficha: el log guarda su identidad, no la ficha.
    assert identidad_spec_de(log) == actuacion.identidad_spec.a_dict()  # type: ignore[attr-defined]
    verificar_replay(log, actuacion.spec)  # type: ignore[attr-defined]


@pytest.mark.parametrize("caso", CASOS)
def test_replay_desde_jsonl_reproduce_veredicto_y_ahorro(
    caso: str, logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    """El replay se hace con el log serializado: nada se lee de `expedientes/`."""
    actuacion = casos_procesados[caso]
    log = LogEventos.desde_jsonl(logs_de_casos[caso].a_jsonl())
    reproducida = reproducir(log, actuacion.spec)  # type: ignore[attr-defined]
    assert reproducida.veredicto == actuacion.veredicto  # type: ignore[attr-defined]
    original = actuacion.calculo  # type: ignore[attr-defined]
    if original is None or original.total is None:
        assert reproducida.calculo is None or reproducida.calculo.total is None
    else:
        assert reproducida.calculo is not None
        assert reproducida.calculo.total == original.total
        assert reproducida.calculo.total_cae == original.total_cae


def test_replay_del_caso_a_da_el_ahorro_exacto(
    logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    spec = casos_procesados[CASO_A].spec  # type: ignore[attr-defined]
    reproducida = reproducir(LogEventos.desde_jsonl(logs_de_casos[CASO_A].a_jsonl()), spec)
    assert reproducida.veredicto == "PREVALIDADO"
    assert reproducida.calculo is not None
    assert reproducida.calculo.total == AETOTAL_A
    assert reproducida.calculo.total_cae == 305829


def test_el_replay_no_toca_el_disco(
    monkeypatch: pytest.MonkeyPatch,
    logs_de_casos: dict[str, LogEventos],
    casos_procesados: dict[str, object],
) -> None:
    """Si el replay leyera un documento, este test lo veria: `open` esta cortado durante la reproduccion."""
    import builtins

    log = LogEventos.desde_jsonl(logs_de_casos[CASO_A].a_jsonl())
    spec = casos_procesados[CASO_A].spec  # type: ignore[attr-defined]

    def sin_disco(*args: object, **kwargs: object):
        raise AssertionError(f"el replay no puede abrir ficheros: {args!r}")

    monkeypatch.setattr(builtins, "open", sin_disco)
    monkeypatch.setattr(Path, "open", sin_disco)
    assert reproducir(log, spec).veredicto == "PREVALIDADO"


def test_la_consolidacion_reconstruida_conserva_las_tres_capas(
    logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    for caso, log in logs_de_casos.items():
        reconstruida = consolidada_de(log)
        original = casos_procesados[caso].consolidada  # type: ignore[attr-defined]
        # Incluye documentos, unidades, variables, conflictos, vinculos por huella y avisos.
        assert json_canonico(reconstruida.a_dict()) == json_canonico(original.a_dict()), caso
    consolidada = consolidada_de(logs_de_casos[CASO_A])
    for datos in consolidada.unidades.values():
        for dato in datos.values():
            assert dato.evidencias, f"{dato.variable} sin evidencia: sin cita no entra"
            for evidencia in dato.evidencias:
                assert evidencia.texto_literal
                assert isinstance(evidencia.confianza, Decimal)


def test_el_replay_verifica_la_cadena_antes_de_reproducir(
    logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    eventos = list(logs_de_casos[CASO_A].eventos)
    eventos[5] = dataclasses.replace(eventos[5], payload={"manipulado": True})
    roto = LogEventos(logs_de_casos[CASO_A].actuacion_id, eventos)
    with pytest.raises(ErrorEvento, match="eslabon 6"):
        reproducir(roto, casos_procesados[CASO_A].spec)  # type: ignore[attr-defined]


def test_replay_sin_los_eventos_necesarios() -> None:
    log = log_corto(1)
    with pytest.raises(ErrorEvento, match="ActuacionAbierta"):
        reproducir(log, None)


def test_verificar_replay_falla_si_el_log_no_cuadra(
    logs_de_casos: dict[str, LogEventos], casos_procesados: dict[str, object]
) -> None:
    """Un log cuyo `VeredictoEmitido` no es el que produce el nucleo no es fiel: el replay lo dice."""
    eventos = list(logs_de_casos[CASO_A].eventos)
    ultimo = eventos[-1]
    mentira = dict(ultimo.payload) | {"veredicto": "NO_ELEGIBLE"}
    log = LogEventos(logs_de_casos[CASO_A].actuacion_id, eventos[:-1])
    log.anadir(
        ultimo.tipo,
        {clave: valor for clave, valor in mentira.items()},
        actor=ultimo.actor,
        ocurrido_en=ultimo.ocurrido_en,
    )
    spec = casos_procesados[CASO_A].spec  # type: ignore[attr-defined]
    reproducida = reproducir(log, spec)
    diferencias = divergencias(log, reproducida)
    assert diferencias
    assert any("veredicto" in d for d in diferencias)
    with pytest.raises(ErrorEvento, match="no reproduce lo grabado"):
        verificar_replay(log, spec)


# ---------------------------------------------------------------------------
# Higiene del paquete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fuente", FUENTES_EVENTOS, ids=lambda p: p.name)
def test_sin_eval_exec_compile_ni_float(fuente: Path) -> None:
    codigo = fuente.read_text(encoding="utf-8")
    for prohibido in ("eval(", "exec(", "compile(", "float(", "import ast", "from ast"):
        assert prohibido not in codigo, f"{fuente.name} usa {prohibido}"


@pytest.mark.parametrize("fuente", FUENTES_EVENTOS, ids=lambda p: p.name)
def test_no_importa_hacia_fuera(fuente: Path) -> None:
    codigo = fuente.read_text(encoding="utf-8")
    for paquete in ("agentes", "salida", "generator", "tests"):
        assert f"import {paquete}" not in codigo, f"{fuente.name} importa {paquete}"
        assert f"from {paquete}" not in codigo, f"{fuente.name} importa de {paquete}"


@pytest.mark.parametrize("fuente", FUENTES_EVENTOS, ids=lambda p: p.name)
def test_sin_ramas_por_ficha(fuente: Path) -> None:
    codigo = fuente.read_text(encoding="utf-8")
    assert "if ficha ==" not in codigo
    assert "IND240" not in codigo, f"{fuente.name} nombra una ficha"


@pytest.mark.parametrize("fuente", FUENTES_EVENTOS, ids=lambda p: p.name)
def test_ningun_reloj_sin_zona(fuente: Path) -> None:
    """Ni un `datetime.now()` a secas en el paquete (`ADR-004` C2, `ADR-003` H-08)."""
    # Se descuentan las menciones entre acentos graves: en la prosa de las cabeceras se cita la regla.
    codigo = fuente.read_text(encoding="utf-8").replace("`datetime.now()`", "")
    assert "datetime.now()" not in codigo
    assert "utcnow(" not in codigo
    for linea in codigo.splitlines():
        if "now(" in linea and "ahora_utc" not in linea:
            assert "UTC" in linea or "timezone.utc" in linea, f"{fuente.name}: {linea.strip()}"
