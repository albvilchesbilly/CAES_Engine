"""Recalculo tras correccion humana (S3.8, `ADR-013`): los siete puntos de verificacion de §5.

Lo que este fichero prueba, en el orden en que importa:

1. **Los 7 casos sin correcciones dan exactamente lo mismo** y el caso A sigue en 305.829,6 kWh/año. Es la
   primera comprobacion: un parametro nuevo con valor por defecto que cambiase un solo veredicto haria
   inutil todo lo demas.
2. **El caso C**: sin correccion sigue `BLOQUEADO` sin ahorro; con la correccion que elige 110 kW el
   conflicto se resuelve, `valor_consumido` deja de ser `null`, el veredicto pasa a `PREVALIDADO` y aparece
   un ahorro que antes no existia — el mismo del caso A, porque el caso C **es** el caso A con una errata
   de 90 kW en el certificado del instalador (`expedientes/_resultados_esperados/EXP001-C…json`, que
   guarda 305829.6 como `referencia_no_publicada`).
3. **El replay** reproduce el veredicto corregido solo con el log, bit a bit.
4. Dos correcciones de la misma variable: manda la ultima y **las dos quedan en la traza**.
5. Sin justificacion no entra (regla de oro 2). Variable que la spec no declara: error (regla de oro 4).
6. La correccion sale en el informe con su cita **sin tocar `engine/informe.py`**.

Las correcciones se construyen aqui de las dos formas que existen: a mano (lo que hace quien llama al
motor) y desde un log real con su evento `DatoCorregidoPorHumano` sellado por una persona con rol (A8).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from engine.correcciones import (
    METODO,
    TIPO_EVENTO,
    Correccion,
    ErrorCorreccion,
    a_evidencia,
    de_evento,
    de_log,
    validar,
)
from engine.estados import proyectar
from engine.eventos.grabacion import grabar
from engine.eventos.log import LogEventos
from engine.eventos.replay import divergencias, reproducir, verificar_replay
from engine.informe import a_json, a_markdown
from engine.motor import Actuacion, procesar_actuacion
from engine.reglas import Resultado
from engine.spec_registry import SpecRegistry
from tests.apoyo_permisos import humano_para

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_GROUND_TRUTH = CARPETA_CASOS / "_resultados_esperados"

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
CASO_C = "EXP001-C_contradictorio"
AETOTAL_A = Decimal("305829.6")

SERIE = "MTR-SYN-0001"
ACTOR = "ana@tenant"
INSTANTE = datetime(2026, 9, 19, 10, 30, tzinfo=UTC)
INSTANTE_2 = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
JUSTIFICACION = (
    "La ficha tecnica del motor y la placa de caracteristicas dicen 110 kW; el certificado del instalador "
    "arrastra una errata de tecleo."
)


def ground_truth(caso: str) -> dict:
    return json.loads((CARPETA_GROUND_TRUTH / f"{caso}.json").read_text(encoding="utf-8"))


def fecha_de_caso(caso: str) -> date:
    return date.fromisoformat(ground_truth(caso)["fecha_evaluacion"])


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


def correccion(
    valor: str = "110",
    *,
    variable: str = "PM",
    justificacion: str = JUSTIFICACION,
    serie: str | None = SERIE,
    instante: datetime = INSTANTE,
    evento_id: str = "11111111-2222-3333-4444-555555555555",
    rol: str = "T-REV",
    origen: str | None = "conflicto",
) -> Correccion:
    return Correccion(
        variable=variable,
        valor=valor,
        justificacion=justificacion,
        actor_id=ACTOR,
        actor_rol=rol,
        evento_id=evento_id,
        instante=instante,
        num_serie_motor=serie,
        origen=origen,
    )


@cache
def procesado(caso: str) -> Actuacion:
    return procesar_actuacion(
        CARPETA_CASOS / caso, fecha_evaluacion=fecha_de_caso(caso), ocr=False, registro=_registro()
    )


@cache
def caso_c_corregido() -> Actuacion:
    """El caso C con la correccion que elige 110 kW (la que escribiria el revisor en `FR1`)."""
    return procesar_actuacion(
        CARPETA_CASOS / CASO_C,
        fecha_evaluacion=fecha_de_caso(CASO_C),
        ocr=False,
        registro=_registro(),
        correcciones=(correccion(),),
    )


def sin_telemetria(actuacion: Actuacion) -> str:
    """El informe JSON sin lo que cambia entre dos ejecuciones identicas (los segundos de reloj)."""
    datos = a_json(actuacion)
    datos["tiempos"] = {}
    datos["actuacion"]["tiempos"] = {}  # type: ignore[index]
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)


def log_con_correccion(actuacion: Actuacion, *payloads: dict) -> LogEventos:
    """El log de una ejecucion mas los `DatoCorregidoPorHumano` que una persona sello despues."""
    log = grabar(actuacion, instante=INSTANTE)
    for payload in payloads:
        log.anadir(
            TIPO_EVENTO,
            payload,
            actor=humano_para(TIPO_EVENTO, ACTOR),
            ocurrido_en=INSTANTE,
        )
    return log


def payload(valor: str = "110", *, justificacion: str = JUSTIFICACION, variable: str = "PM") -> dict:
    return {
        "capacidad": "CAP-05",
        "variable": variable,
        "num_serie_motor": SERIE,
        "valor": valor,
        "justificacion": justificacion,
        "motivo": "conflicto o correccion",
    }


# ---------------------------------------------------------------------------
# 1 · Primero: sin correcciones no cambia nada
# ---------------------------------------------------------------------------


def test_los_siete_casos_sin_correcciones_dan_el_mismo_veredicto():
    """`correcciones=()` por defecto: la firma publica no cambia para quien no corrige (`ADR-013` §3)."""
    obtenidos = {caso: procesado(caso).veredicto for caso in CASOS}
    assert obtenidos == {caso: ground_truth(caso)["veredicto_esperado"] for caso in CASOS}


def test_el_caso_a_sigue_dando_el_criterio_de_aceptacion_de_la_fase():
    calculo = procesado(CASO_A).calculo
    assert calculo is not None
    assert calculo.total == AETOTAL_A
    assert calculo.total_cae == 305829


def test_pasar_una_secuencia_vacia_es_identico_a_no_pasar_nada():
    """Byte a byte: el informe de una ejecucion con `correcciones=()` es el de siempre."""
    con_parametro = procesar_actuacion(
        CARPETA_CASOS / CASO_C,
        fecha_evaluacion=fecha_de_caso(CASO_C),
        ocr=False,
        registro=_registro(),
        correcciones=(),
    )
    assert sin_telemetria(con_parametro) == sin_telemetria(procesado(CASO_C))


# ---------------------------------------------------------------------------
# 2 · Contrato C20: la correccion es una evidencia, con sus tres capas
# ---------------------------------------------------------------------------


def test_sin_justificacion_no_entra():
    """Sin justificacion no hay cita, y sin cita no entra (regla de oro 2; `ADR-013` §2 regla 5)."""
    with pytest.raises(ErrorCorreccion, match="justificacion"):
        correccion(justificacion="   ")
    evento = log_con_correccion(procesado(CASO_C), payload(justificacion="")).por_tipo(TIPO_EVENTO)[0]
    with pytest.raises(ErrorCorreccion, match="justificacion"):
        de_evento(evento)


def test_una_correccion_sin_rol_no_entra():
    """A8: una persona actua siempre con un perfil, y el perfil ejercido es parte de la traza."""
    with pytest.raises(ErrorCorreccion, match="actor_rol"):
        correccion(rol="")


def test_un_instante_sin_zona_no_entra():
    with pytest.raises(ErrorCorreccion, match="zona horaria"):
        correccion(instante=datetime(2026, 9, 19, 10, 30))


class _EventoFalso:
    """Un sobre con lo justo que `de_evento` mira. El log de verdad ya no deja sellar un `float`, asi que
    la unica forma de probar la guarda del nucleo es entrarle por donde entraria un log de otro sitio."""

    tipo = TIPO_EVENTO
    evento_id = "ffff-1"
    secuencia = 1
    ocurrido_en = INSTANTE

    def __init__(self, datos: dict) -> None:
        self.datos = datos
        self.actor = humano_para(TIPO_EVENTO, ACTOR)


def test_un_valor_float_es_un_defecto():
    """`CLAUDE.md` §2: ningun `float` toca una magnitud. El valor viaja como texto."""
    with pytest.raises(ErrorCorreccion, match="float"):
        de_evento(_EventoFalso({**payload(), "valor": 110.0}))


def test_el_valor_llega_como_texto_canonico_sea_cual_sea_su_tipo():
    """`Decimal` del payload → texto sin exponente ni ceros de mas; a `Decimal` lo vuelve la consolidacion."""
    assert de_evento(_EventoFalso({**payload(), "valor": Decimal("110.00")})).valor == "110"
    assert de_evento(_EventoFalso({**payload(), "valor": 110})).valor == "110"
    assert de_evento(_EventoFalso({**payload(), "valor": True})).valor == "true"


def test_la_correccion_como_evidencia_lleva_las_tres_capas():
    evidencia = a_evidencia(correccion())
    assert evidencia.variable == "PM" and evidencia.valor == "110"
    assert evidencia.doc_id == "11111111-2222-3333-4444-555555555555"  # capa 1: el evento
    assert evidencia.texto_literal == JUSTIFICACION  # capa 1: la cita es la justificacion
    assert evidencia.metodo == METODO and evidencia.confianza == Decimal("1")
    assert evidencia.fiable is True
    assert f"{ACTOR}/T-REV@{INSTANTE.isoformat()}" in evidencia.extractor_version
    assert evidencia.num_serie_motor == SERIE
    assert evidencia.interpretacion is None, "`interpretacion` es de los INT-xx, no de la firma"


def test_de_log_devuelve_todas_las_correcciones_en_orden_y_solo_esas():
    log = log_con_correccion(procesado(CASO_C), payload("110"), payload("100"))
    correcciones = de_log(log)
    assert [c.valor for c in correcciones] == ["110", "100"]
    assert {c.actor_id for c in correcciones} == {ACTOR}
    assert {c.actor_rol for c in correcciones} == {"T-REV"}
    assert all(c.variable == "PM" and c.num_serie_motor == SERIE for c in correcciones)
    assert all(c.origen == "conflicto o correccion" for c in correcciones)
    assert len(log) > len(correcciones), "el log trae muchos mas eventos y solo se leen los del tipo"


def test_una_variable_que_la_spec_no_declara_es_un_error(spec_ind240):
    """Una correccion no inventa un dato: la ficha sigue diciendo que existe (regla de oro 4)."""
    with pytest.raises(ErrorCorreccion, match="no declara la variable"):
        validar((correccion(variable="PM_inventada"),), spec_ind240)
    with pytest.raises(ErrorCorreccion, match="no declara la variable"):
        procesar_actuacion(
            CARPETA_CASOS / CASO_C,
            fecha_evaluacion=fecha_de_caso(CASO_C),
            ocr=False,
            registro=_registro(),
            correcciones=(correccion(variable="PM_inventada"),),
        )


def test_una_correccion_que_el_motor_ignoraria_en_silencio_es_un_error(spec_ind240):
    """El ambito lo dice el `nivel` de la spec: ni se adivina la unidad ni se acepta una que sobra."""
    with pytest.raises(ErrorCorreccion, match="variable de unidad"):
        validar((correccion(serie=None),), spec_ind240)
    with pytest.raises(ErrorCorreccion, match="variable de actuacion"):
        validar((correccion(variable="titular_nif", valor="B99001018"),), spec_ind240)


# ---------------------------------------------------------------------------
# 3 · El caso C: el conflicto se resuelve y aparece un ahorro que antes no existia
# ---------------------------------------------------------------------------


def test_el_caso_c_sin_correccion_sigue_bloqueado_y_sin_ahorro():
    actuacion = procesado(CASO_C)
    assert actuacion.veredicto == "BLOQUEADO"
    assert actuacion.calculo is None or actuacion.calculo.total is None
    assert actuacion.evaluacion.bloqueo_por_conflicto == ("PM",)
    assert actuacion.consolidada.dato("PM", SERIE).valor_consumido is None


def test_el_caso_c_corregido_cambia_el_veredicto_y_publica_el_ahorro():
    """110 kW elegidos por una persona: el caso C es el caso A con una errata, asi que da lo mismo que A."""
    actuacion = caso_c_corregido()
    assert actuacion.veredicto == "PREVALIDADO"
    calculo = actuacion.calculo
    assert calculo is not None
    assert calculo.total == AETOTAL_A  # p = 5,55/110 = 5,0455 % sobre el mismo h, N1, N2 y P_prom
    assert calculo.total_cae == 305829
    assert calculo.provisional is False
    referencia = ground_truth(CASO_C)["aetotal_esperado"]["referencia_no_publicada"]
    assert calculo.total == Decimal(referencia), "el ground truth del caso C ya decia cual era el ahorro"


def test_el_caso_c_corregido_resuelve_el_conflicto_sin_borrarlo():
    """El conflicto no se borra: se resuelve. Las evidencias enfrentadas siguen ahi (`ADR-013` §2 regla 3)."""
    dato = caso_c_corregido().consolidada.dato("PM", SERIE)
    assert dato.valor_consumido == Decimal("110")
    assert dato.conflicto is False
    assert caso_c_corregido().evaluacion.bloqueo_por_conflicto == ()
    assert caso_c_corregido().consolidada.conflictos == []
    fuentes = {(ev.tipo_doc, ev.valor) for ev in dato.evidencias}
    assert ("certificado_instalador", "90") in fuentes, "la evidencia desplazada se conserva con su cita"
    assert ("ficha_tecnica_motor", "110") in fuentes
    assert (METODO, "110") in fuentes
    assert any("certificado_instalador=90" in aviso for aviso in dato.avisos)
    assert dato.valores_por_fuente == {METODO: "110"}, "lo que el motor leyo fue la correccion"


def test_el_caso_c_corregido_hace_cumplir_la_regla_que_fallaba():
    resultados = {r.id: r.resultado for r in caso_c_corregido().evaluacion.resultados}
    assert resultados["R-CON-01"] is Resultado.CUMPLE
    assert [r.id for r in caso_c_corregido().evaluacion.resultados if r.resultado is Resultado.FALLA] == []


def test_una_correccion_distinta_da_un_ahorro_distinto():
    """El motor no busca 110: consume lo que la persona decidio. Con 90 kW el ahorro es otro."""
    actuacion = procesar_actuacion(
        CARPETA_CASOS / CASO_C,
        fecha_evaluacion=fecha_de_caso(CASO_C),
        ocr=False,
        registro=_registro(),
        correcciones=(correccion("90"),),
    )
    assert actuacion.consolidada.dato("PM", SERIE).valor_consumido == Decimal("90")
    assert actuacion.veredicto in ("PREVALIDADO", "SUBSANABLE")
    calculo = actuacion.calculo
    assert calculo is not None and calculo.total is not None
    assert calculo.total != AETOTAL_A


# ---------------------------------------------------------------------------
# 4 · Dos correcciones de la misma variable: manda la ultima, las dos quedan
# ---------------------------------------------------------------------------


def test_manda_la_ultima_correccion_y_las_dos_quedan_en_la_traza():
    """El log es solo-anadir: corregir dos veces no es un conflicto, es cambiar de opinion (regla 1)."""
    actuacion = procesar_actuacion(
        CARPETA_CASOS / CASO_C,
        fecha_evaluacion=fecha_de_caso(CASO_C),
        ocr=False,
        registro=_registro(),
        correcciones=(
            correccion("90", evento_id="aaaa-1", justificacion="Me quedo con el certificado."),
            correccion("110", evento_id="aaaa-2", instante=INSTANTE_2),
        ),
    )
    dato = actuacion.consolidada.dato("PM", SERIE)
    assert dato.valor_consumido == Decimal("110")
    assert dato.conflicto is False
    correcciones = [ev for ev in dato.evidencias if ev.metodo == METODO]
    assert [ev.valor for ev in correcciones] == ["90", "110"], "las dos quedan, en orden"
    assert [ev.doc_id for ev in correcciones] == ["aaaa-1", "aaaa-2"]
    assert any("Me quedo con el certificado." == ev.texto_literal for ev in correcciones)


# ---------------------------------------------------------------------------
# 5 · El informe la enseña sola, sin tocar `engine/informe.py`
# ---------------------------------------------------------------------------


def test_la_correccion_sale_en_el_informe_markdown_con_su_cita():
    markdown = a_markdown(caso_c_corregido())
    assert JUSTIFICACION in markdown, "la cita literal es la justificacion que escribio la persona"
    assert METODO in markdown
    assert f"{ACTOR}/T-REV@{INSTANTE.isoformat()}" in markdown, "quien, con que rol y cuando"
    assert "certificado_instalador=90" in markdown, "y que habia antes"


def test_la_correccion_sale_en_el_informe_json():
    datos = a_json(caso_c_corregido())
    pm = datos["consolidada"]["unidades"][SERIE]["PM"]  # type: ignore[index]
    assert pm["valor_consumido"] == "110"
    assert pm["conflicto"] is False
    corregida = [ev for ev in pm["evidencias"] if ev["metodo"] == METODO]
    assert len(corregida) == 1
    assert corregida[0]["texto_literal"] == JUSTIFICACION
    assert corregida[0]["extractor_version"] == f"{ACTOR}/T-REV@{INSTANTE.isoformat()}#conflicto"
    assert corregida[0]["confianza"] == "1"
    assert any(ev["valor"] == "90" for ev in pm["evidencias"]), "las dos evidencias siguen en el informe"


# ---------------------------------------------------------------------------
# 6 · El replay: el veredicto corregido se reproduce solo con el log
# ---------------------------------------------------------------------------


def test_el_replay_reproduce_el_veredicto_corregido_bit_a_bit(spec_ind240):
    """El circuito entero: se graba, una persona corrige en el log, se recalcula y se vuelve a grabar."""
    log = log_con_correccion(procesado(CASO_C), payload("110"))
    correcciones = de_log(log)
    assert len(correcciones) == 1
    recalculada = procesar_actuacion(
        CARPETA_CASOS / CASO_C,
        fecha_evaluacion=fecha_de_caso(CASO_C),
        ocr=False,
        registro=_registro(),
        correcciones=correcciones,
    )
    assert recalculada.veredicto == "PREVALIDADO"

    log_recalculo = grabar(recalculada, instante=INSTANTE_2)
    evaluacion = verificar_replay(log_recalculo, spec_ind240)
    assert evaluacion.veredicto == "PREVALIDADO"
    assert evaluacion.calculo is not None and evaluacion.calculo.total == AETOTAL_A
    assert divergencias(log_recalculo, evaluacion) == ()

    dato = next(
        evento.datos["dato"]
        for evento in log_recalculo.por_tipo("DatoConsolidado")
        if evento.datos.get("variable") == "PM"
    )
    assert any(ev["metodo"] == METODO for ev in dato["evidencias"]), "la correccion viaja en el log"


def test_el_replay_del_mismo_log_regrabado_tambien_reproduce_el_veredicto_corregido(spec_ind240):
    """El caso realista: un solo log por actuacion, con la ejecucion vieja, la correccion y la nueva.

    Un `ConflictoDetectado` de la ejecucion anterior es historia, no un conflicto de hoy: lo que vale es el
    `DatoConsolidado` reconstruido (ver `engine.eventos.replay.consolidada_de`).
    """
    log = log_con_correccion(procesado(CASO_C), payload("110"))
    recalculada = procesar_actuacion(
        CARPETA_CASOS / CASO_C,
        fecha_evaluacion=fecha_de_caso(CASO_C),
        ocr=False,
        registro=_registro(),
        correcciones=de_log(log),
    )
    completo = grabar(recalculada, instante=INSTANTE_2, log=log)
    assert len(completo.por_tipo("ConflictoDetectado")) == 1, "el conflicto viejo sigue en el log"
    evaluacion = reproducir(completo, spec_ind240)
    assert evaluacion.veredicto == "PREVALIDADO"
    assert divergencias(completo, evaluacion) == ()


# ---------------------------------------------------------------------------
# 7 · Higiene: el motor no sabe donde viven los eventos
# ---------------------------------------------------------------------------


def test_correcciones_no_importa_el_paquete_de_eventos():
    """`de_log` consume el log por atributos: el nucleo no adquiere una dependencia del log (`ADR-013` §3)."""
    fuente = (RAIZ / "engine" / "correcciones.py").read_text(encoding="utf-8")
    assert "import engine.eventos" not in fuente
    assert "from engine.eventos" not in fuente
    motor = (RAIZ / "engine" / "motor.py").read_text(encoding="utf-8")
    assert "from engine.eventos" not in motor and "import engine.eventos" not in motor


def test_corregir_a_mano_un_dato_que_la_ficha_exige_derivado_lo_marca_como_no_derivado():
    """Consecuencia buscada de `tipo_evidencia = "demostrado"` (ver la cabecera de `engine.correcciones`).

    `N2` sale del registro de funcionamiento (`derivado`) y `R-EVD-04` lo exige. Una persona que lo fija a
    mano deja de tenerlo derivado, y el motor lo dice: `R-EVD-04` falla (`SUBSANABLE`), el ahorro sale
    provisional y `R-CON-03` —el cruce declarado ↔ derivado— se queda sin las dos mitades que comparaba.
    Que un dato corregido pierda el sello de derivado no es un efecto colateral: es la verdad.
    """
    actuacion = procesar_actuacion(
        CARPETA_CASOS / CASO_A,
        fecha_evaluacion=fecha_de_caso(CASO_A),
        ocr=False,
        registro=_registro(),
        correcciones=(
            correccion(
                "1200",
                variable="N2",
                justificacion="El registro trae dos filas corruptas; la velocidad real es 1200 rpm.",
                origen=None,
            ),
        ),
    )
    dato = actuacion.consolidada.dato("N2", SERIE)
    assert dato.valor_consumido == Decimal("1200")
    assert dato.tipo_evidencia == "demostrado"
    resultados = {r.id: r.resultado for r in actuacion.evaluacion.resultados}
    assert resultados["R-EVD-04"] is Resultado.FALLA
    assert resultados["R-CON-03"] is Resultado.NO_EVALUABLE
    assert actuacion.veredicto == "SUBSANABLE"
    assert actuacion.calculo is not None and actuacion.calculo.provisional is True


# ---------------------------------------------------------------------------
# Inalterabilidad: una correccion que el ciclo rechazo no se aplica
# ---------------------------------------------------------------------------


def _log_firmado(actuacion_id: str = "ACT-FIRMADA") -> LogEventos:
    """Una actuacion prevalidada, revisada, entregada y firmada: desde aqui rige la inalterabilidad."""
    log = LogEventos(actuacion_id)
    motor = ("motor", "engine@test")
    revisor = ("humano", "ana@tenant", "T-REV")
    responsable = ("humano", "bob@tenant", "T-RES")
    for tipo, payload, actor in (
        ("ActuacionAbierta", {}, motor),
        ("DocumentoRegistrado", {}, motor),
        ("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, motor),
        ("RevisionAprobada", {}, revisor),
        ("PayloadConstruido", {}, motor),
        ("EntregadoADelegado", {}, motor),
        ("FirmaRegistrada", {}, responsable),
    ):
        log.anadir(tipo, payload, actor=actor)
    return log


def test_una_correccion_post_firma_queda_en_el_log_pero_no_se_aplica() -> None:
    """`ADR-013` §4 decia que «si el evento no debio escribirse, no esta en el log». **Era falso.**

    `engine.estados` no levanta ante un cambio de datos posterior a la firma: lo **anota** en
    `Proyeccion.rechazos` y el evento queda sellado igual. Sin filtro, reprocesar una actuacion firmada
    aplicaba una correccion que la inalterabilidad prohibe (`docs/02` §5.4). Cerrado el 20/09/2026.
    """
    log = _log_firmado()
    log.anadir(
        "DatoCorregidoPorHumano",
        {
            "variable": "PM",
            "valor": "90",
            "justificacion": "intento de colar un cambio despues de firmar",
            "num_serie_motor": "MTR-SYN-0001",
        },
        actor=("humano", "ana@tenant", "T-REV"),
    )

    proyeccion = proyectar(log)
    assert proyeccion.estado_ciclo == "EN_PLATAFORMA", "la firma no se mueve"
    assert len(proyeccion.rechazos) == 1, "el intento queda anotado: no se pierde ni se silencia"
    assert log.por_tipo("DatoCorregidoPorHumano"), "el evento sigue en el log: es solo-anadir"

    assert de_log(log) == (), "pero no se aplica: la inalterabilidad no depende de quien llame"


def test_una_correccion_antes_de_la_firma_si_se_aplica() -> None:
    """La otra mitad: el filtro no puede tragarse las correcciones legitimas."""
    log = LogEventos("ACT-ABIERTA")
    log.anadir("ActuacionAbierta", {}, actor=("motor", "engine@test"))
    log.anadir("DocumentoRegistrado", {}, actor=("motor", "engine@test"))
    log.anadir(
        "DatoCorregidoPorHumano",
        {
            "variable": "PM",
            "valor": "110",
            "justificacion": "la ficha del fabricante manda sobre la errata de la factura",
            "num_serie_motor": "MTR-SYN-0001",
        },
        actor=("humano", "ana@tenant", "T-REV"),
    )
    assert len(de_log(log)) == 1
