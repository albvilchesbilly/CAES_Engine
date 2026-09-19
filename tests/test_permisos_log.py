"""Tests de `actor.rol` y de los eventos de `ADR-006` en el log (S3.1b, A8 aprobada el 19/09/2026).

Los tres criterios de "hecho cuando" de `docs/06` S3.1b, en este orden:

1. **Un `ADM-OPS` no puede generar `SpecActivada` ni un `ADM-MOD` un `TenantAlta`.** La comprobacion no
   copia la matriz: consume `engine/capacidades.yaml` a traves de `tests/apoyo_permisos.py`, que es el
   mismo gancho (`LogEventos(autorizador=...)`) que instalara `engine/capacidades.py` al integrar.
2. **Ningun evento de administracion carece de `actor.rol`.** Se comprueba de dos maneras: por el catalogo
   (todo evento de administracion es un acto humano) y en ejecucion (el log rechaza el evento sin rol).
3. **CAP-10 y CAP-22 son los unicos disparadores humanos de sus transiciones.** Se recorre el catalogo
   entero y se comprueba que ningun otro tipo pone `revisada_por_humano` ni mueve `ENTREGADA` ->
   `EN_PLATAFORMA`.

Y ademas:

- **Leer un log antiguo sigue funcionando.** Un log sellado antes de A8 tiene actores humanos sin rol; se
  lee, se reproduce por JSONL y **verifica**, porque el log es solo-anadir y no se reescribe. Lo unico
  prohibido es escribir hoy uno nuevo asi.
- **Los dos caminos de la revision y del descarte llevan al mismo sitio**: el tipo propio de `ADR-006` y el
  `ObservacionRegistrada{origen}` anterior producen la misma proyeccion.
- **Las dos mitades del puente coinciden**: lo que el catalogo dice que produce cada capacidad y lo que la
  matriz dice que produce cada capacidad son lo mismo.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from engine.estados import (
    ORIGEN_DESCARTE,
    ORIGEN_REVISION,
    TIPO_ACTUACION_DESCARTADA,
    TIPO_REVISION_APROBADA,
    ErrorEstado,
    aplicar,
    inicial,
)
from engine.eventos import (
    TIPOS,
    TIPOS_ADMINISTRACION,
    TIPOS_SOLO_HUMANO,
    Actor,
    ErrorEvento,
    Evento,
    LogEventos,
    calcular_hash,
    codificar,
    json_canonico,
    texto_instante,
)
from engine.eventos.catalogo import GRUPOS_ADMINISTRACION, TIPOS_POR_PROCESO
from engine.eventos.log import NAMESPACE_EVENTOS
from engine.reglas import VEREDICTO_NO_ELEGIBLE, VEREDICTO_PREVALIDADO
from tests import apoyo_permisos
from tests.apoyo_permisos import autorizador_de_matriz, humano_para, rol_para

ACT = "ACT-0001"
INSTANTE = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)

MOTOR = Actor("motor", "engine@test")
PLATAFORMA = Actor("plataforma", "omie")
REVISOR = Actor("humano", "revisor@tenant", rol="T-REV")
RESPONSABLE = Actor("humano", "responsable@tenant", rol="T-RES")

PAYLOAD_AGENTE = {"modelo": "m", "version_prompt": "v1", "coste": 1, "latencia": 2}

#: Los 23 eventos que `ADR-006` marca "(nuevo)". Se escriben aqui, leidos del ADR, no se importan.
EVENTOS_NUEVOS_ADR006 = (
    "ObservacionRevisada",  # CAP-07
    "ActuacionDescartada",  # CAP-08
    "RevisionAprobada",  # CAP-10
    "DiscrepanciaResuelta",  # CAP-16
    "ExpedienteAprobado",  # CAP-21
    "UsuarioAlta",  # CAP-30
    "UsuarioBaja",  # CAP-30
    "RolAsignado",  # CAP-30
    "ActuacionReasignada",  # CAP-32
    "PoliticaTenantCambiada",  # CAP-33
    "AccesoSoporteAutorizado",  # CAP-34
    "AccesoSoporteDenegado",  # CAP-34
    "SpecActivada",  # CAP-50 / CAP-51 / CAP-56
    "AgenteActivado",  # CAP-52
    "AgenteDesactivado",  # CAP-52
    "PromptActivado",  # CAP-53
    "UmbralCambiado",  # CAP-54
    "TenantAlta",  # CAP-60
    "TenantBaja",  # CAP-60
    "TenantSuspendido",  # CAP-60
    "CapacidadActualizada",  # CAP-61
    "AccesoSoporteSolicitado",  # CAP-62
    "AccesoSoporteUsado",  # CAP-63
)

sin_matriz = pytest.mark.skipif(
    not apoyo_permisos.hay_matriz(), reason="falta engine/capacidades.yaml (la matriz de ADR-006)"
)


def suceso(tipo: str, payload: Mapping[str, object] | None = None, *, actor: Actor = MOTOR) -> Evento:
    """Un sobre construido a mano: se salta `anadir` para probar la maquina de estados por separado."""
    return Evento(
        evento_id=f"ev-{tipo}",
        actuacion_id=ACT,
        secuencia=1,
        tipo=tipo,
        ocurrido_en=INSTANTE,
        actor=actor,
        payload=codificar(dict(payload or {})),  # type: ignore[arg-type]
        hash_previo="",
        hash="",
    )


def en_estado(estado: str, **campos: object) -> object:
    return replace(inicial(ACT), estado_ciclo=estado, **campos)  # type: ignore[arg-type]


def sellar_sin_rol(filas: tuple[tuple[str, dict, Actor], ...]) -> LogEventos:
    """Un log **sellado antes de A8**: actores humanos sin rol y hashes calculados sobre ese sobre.

    Se fabrica a mano porque es la unica forma: `anadir` ya no deja escribir un evento humano sin rol. Es
    exactamente lo que hay en un fichero JSONL escrito ayer, y tiene que seguir leyendose y verificando.
    """
    eventos: list[Evento] = []
    previo = ""
    for secuencia, (tipo, payload, actor) in enumerate(filas, start=1):
        base: dict[str, object] = {
            "actuacion_id": ACT,
            "secuencia": secuencia,
            "tipo": tipo,
            "ocurrido_en": texto_instante(INSTANTE),
            "actor": actor.a_dict(),
            "payload": codificar(dict(payload)),
        }
        sobre = {
            "evento_id": str(uuid.uuid5(NAMESPACE_EVENTOS, json_canonico(base))),
            **base,
            "hash_previo": previo,
        }
        previo = calcular_hash(sobre, previo)
        eventos.append(Evento.desde_dict({**sobre, "hash": previo}))
    return LogEventos(ACT, eventos)


# ---------------------------------------------------------------------------
# actor.rol: obligatorio al escribir, opcional al leer
# ---------------------------------------------------------------------------


def test_un_actor_humano_sin_rol_no_puede_escribir() -> None:
    log = LogEventos(ACT)
    with pytest.raises(ErrorEvento, match="no declara `rol`"):
        log.anadir("ObservacionRegistrada", {"texto": "ok"}, actor=Actor("humano", "ana"))
    assert len(log) == 0


@pytest.mark.parametrize("clase", ["motor", "agente", "plataforma"])
def test_las_maquinas_no_necesitan_rol(clase: str) -> None:
    """El rol es del perfil de una persona. Una maquina no ejerce ningun perfil y no se le inventa uno."""
    log = LogEventos(ACT)
    payload = dict(PAYLOAD_AGENTE) if clase == "agente" else {}
    evento = log.anadir("ObservacionRegistrada", payload, actor=(clase, f"{clase}@test"))
    assert evento.actor.rol is None
    assert "rol" not in evento.actor.a_dict()
    log.verificar()


def test_el_rol_viaja_en_el_sobre_y_entra_en_el_hash() -> None:
    uno = LogEventos(ACT)
    otro = LogEventos(ACT)
    primero = uno.anadir("ObservacionRegistrada", {}, actor=REVISOR, ocurrido_en=INSTANTE)
    otro_rol = Actor("humano", "revisor@tenant", rol="T-RES")
    segundo = otro.anadir("ObservacionRegistrada", {}, actor=otro_rol, ocurrido_en=INSTANTE)
    assert primero.actor.a_dict() == {"clase": "humano", "id": "revisor@tenant", "rol": "T-REV"}
    assert primero.hash != segundo.hash, "cambiar el rol tiene que cambiar el hash: es parte de la traza"


def test_un_rol_vacio_no_es_un_rol() -> None:
    """Ni cadena vacia ni espacios: es la puerta trasera por la que entraria el "rol por defecto"."""
    for rol in ("", "   "):
        with pytest.raises(ErrorEvento, match="codigo de perfil"):
            Actor("humano", "ana", rol=rol)


def test_el_actor_se_puede_dar_como_terna_o_como_mapa() -> None:
    log = LogEventos(ACT)
    por_terna = log.anadir("ObservacionRegistrada", {}, actor=("humano", "ana", "T-REV"))
    por_mapa = log.anadir("ObservacionRegistrada", {}, actor={"clase": "humano", "id": "ana", "rol": "T-REV"})
    assert por_terna.actor == por_mapa.actor == Actor("humano", "ana", rol="T-REV")


def test_un_log_sellado_antes_de_a8_se_lee_y_verifica() -> None:
    """La excepcion explicita: el log es solo-anadir y no se reescribe (misma regla que el catalogo)."""
    viejo = sellar_sin_rol(
        (
            ("ActuacionAbierta", {}, MOTOR),
            ("ObservacionRegistrada", {"origen": ORIGEN_REVISION}, Actor("humano", "billy@cae")),
            ("FirmaRegistrada", {"referencia": "R-1"}, Actor("humano", "billy@cae")),
        )
    )
    viejo.verificar()
    assert viejo.ultimo("FirmaRegistrada").actor.rol is None
    # Y sobrevive a la ida y vuelta por JSONL, con los mismos hashes.
    releido = LogEventos.desde_jsonl(viejo.a_jsonl())
    releido.verificar()
    assert [e.hash for e in releido] == [e.hash for e in viejo]
    assert releido.a_jsonl() == viejo.a_jsonl()


def test_a_ese_log_antiguo_no_se_le_puede_anadir_hoy_un_evento_humano_sin_rol() -> None:
    """Leerlo, si. Seguir escribiendolo mal, no: la restriccion es de escritura y es de hoy en adelante."""
    viejo = sellar_sin_rol((("ActuacionAbierta", {}, MOTOR),))
    with pytest.raises(ErrorEvento, match="no declara `rol`"):
        viejo.anadir("ObservacionRegistrada", {}, actor=Actor("humano", "billy@cae"))
    viejo.anadir("ObservacionRegistrada", {}, actor=REVISOR, ocurrido_en=INSTANTE)
    viejo.verificar()


# ---------------------------------------------------------------------------
# Los eventos nuevos de ADR-006
# ---------------------------------------------------------------------------


def test_los_23_eventos_nuevos_del_adr_estan_en_el_catalogo() -> None:
    faltan = [tipo for tipo in EVENTOS_NUEVOS_ADR006 if tipo not in TIPOS]
    assert not faltan, f"faltan en el catalogo cerrado: {faltan}"
    assert len(set(EVENTOS_NUEVOS_ADR006)) == 23


def test_los_grupos_de_gobierno_son_los_tres_del_adr() -> None:
    assert GRUPOS_ADMINISTRACION == (
        "G1 Gobierno del tenant",
        "G2 Gobierno del modelo",
        "G3 Operacion interna",
    )
    assert TIPOS_ADMINISTRACION == frozenset(
        tipo for grupo in GRUPOS_ADMINISTRACION for tipo in TIPOS_POR_PROCESO[grupo]
    )
    assert TIPOS_ADMINISTRACION <= TIPOS


def test_ningun_evento_de_administracion_carece_de_actor_rol() -> None:
    """Criterio 2 de `docs/06` S3.1b, por el catalogo: todos son actos humanos, y un humano trae rol."""
    sin_exigir_humano = sorted(TIPOS_ADMINISTRACION - set(TIPOS_SOLO_HUMANO))
    assert not sin_exigir_humano, f"estos admitirian una maquina: {sin_exigir_humano}"


@pytest.mark.parametrize("tipo", sorted(TIPOS_ADMINISTRACION))
def test_ningun_evento_de_administracion_se_escribe_sin_rol(tipo: str) -> None:
    """Criterio 2, en ejecucion: el log lo rechaza, y lo rechaza tambien a una maquina."""
    log = LogEventos(ACT)
    with pytest.raises(ErrorEvento, match="no declara `rol`"):
        log.anadir(tipo, {}, actor=Actor("humano", "ana"))
    with pytest.raises(ErrorEvento, match="actor humano"):
        log.anadir(tipo, {}, actor=MOTOR)
    evento = log.anadir(tipo, {}, actor=humano_para(tipo), ocurrido_en=INSTANTE)
    assert evento.actor.rol is not None
    log.verificar()


@pytest.mark.parametrize("tipo", sorted(TIPOS_ADMINISTRACION))
def test_un_evento_de_administracion_no_mueve_el_ciclo_de_la_actuacion(tipo: str) -> None:
    """Dar de alta un tenant o activar una spec no cambia en que estado esta una actuacion."""
    partida = en_estado("EVALUADA", veredicto=VEREDICTO_PREVALIDADO)
    despues = aplicar(partida, suceso(tipo, actor=humano_para(tipo)))
    assert despues.estado_ciclo == partida.estado_ciclo
    assert despues.revisada_por_humano is partida.revisada_por_humano
    assert despues.firmada is partida.firmada


# ---------------------------------------------------------------------------
# Criterio 1: la matriz manda (ADM-OPS / ADM-MOD)
# ---------------------------------------------------------------------------


@sin_matriz
@pytest.mark.parametrize(
    ("tipo", "rol_denegado", "rol_concedido"),
    [("SpecActivada", "ADM-OPS", "ADM-MOD"), ("TenantAlta", "ADM-MOD", "ADM-OPS")],
)
def test_los_dos_planos_de_administracion_no_se_solapan(
    tipo: str, rol_denegado: str, rol_concedido: str
) -> None:
    """Criterio 1 de `docs/06` S3.1b y la verificacion de `ADR-005`: dos planos, permisos sin solapamiento.

    El log no lleva la matriz dentro: se le instala el gancho, que es lo que hara `engine/capacidades.py`.
    """
    log = LogEventos(ACT, autorizador=autorizador_de_matriz())
    with pytest.raises(ErrorEvento, match=f"{rol_denegado!r} no puede producir"):
        log.anadir(tipo, {}, actor=Actor("humano", "billy", rol=rol_denegado))
    assert len(log) == 0
    evento = log.anadir(tipo, {}, actor=Actor("humano", "billy", rol=rol_concedido), ocurrido_en=INSTANTE)
    assert evento.actor.rol == rol_concedido
    log.verificar()


@sin_matriz
def test_sin_gancho_el_log_no_autoriza_por_rol() -> None:
    """Y se dice en voz alta: hasta que alguien instale la matriz, el log solo exige que **haya** rol.

    Es deliberado: el log no puede depender de un fichero de configuracion para sellar un evento. Quien
    autoriza es quien compone el sistema (`api/permisos.py` hoy, `engine/capacidades.py` al integrar).
    """
    log = LogEventos(ACT)
    evento = log.anadir("SpecActivada", {}, actor=Actor("humano", "billy", rol="ADM-OPS"))
    assert evento.actor.rol == "ADM-OPS"


@sin_matriz
@pytest.mark.parametrize("tipo", sorted(TIPOS_ADMINISTRACION))
def test_cada_evento_de_administracion_tiene_un_rol_que_lo_concede_y_otros_que_no(tipo: str) -> None:
    """Para cada uno, un caso concedido y otro denegado, como pide la verificacion de `ADR-006`."""
    autorizar = autorizador_de_matriz()
    concedidos = apoyo_permisos.perfiles_que_conceden(tipo)
    pendientes = apoyo_permisos.perfiles_pendientes(tipo)
    if not concedidos:
        # CAP-32 (`ActuacionReasignada`) espera la decision A3: la celda `(?)` se **deniega**.
        assert pendientes, f"{tipo} no lo concede nadie y tampoco esta pendiente de una decision"
        with pytest.raises(ErrorEvento):
            autorizar(tipo, Actor("humano", "x", rol=pendientes[0]))
        return
    for rol in concedidos:
        autorizar(tipo, Actor("humano", "x", rol=rol))
    for rol in apoyo_permisos.perfiles():
        if rol not in concedidos:
            with pytest.raises(ErrorEvento, match="no puede producir"):
                autorizar(tipo, Actor("humano", "x", rol=rol))


def test_el_catalogo_no_declara_quien_produce_cada_evento() -> None:
    """Una sola fuente de verdad: `engine/capacidades.yaml`.

    El catalogo tuvo un `CAPACIDADES_DE_TIPO` en paralelo a la matriz durante unas horas el 19/09/2026, y
    las dos declaraciones coincidian. Se quito igualmente: dos fuentes de la misma verdad no se separan el
    dia que nacen, se separan el dia que alguien cambia una. Este test existe para que no vuelva.
    """
    import engine.eventos as eventos
    import engine.eventos.catalogo as catalogo

    for modulo in (catalogo, eventos):
        publicos = {nombre for nombre in dir(modulo) if not nombre.startswith("_")}
        assert "CAPACIDADES_DE_TIPO" not in publicos, (
            f"{modulo.__name__} vuelve a declarar que capacidad produce que evento; eso lo dice la matriz "
            "(`engine.capacidades.capacidades_que_producen`)"
        )


@sin_matriz
def test_la_matriz_es_quien_dice_que_capacidad_produce_cada_evento() -> None:
    """Y lo que dice tiene que poder consultarse desde el nucleo, que es lo que usa el autorizador."""
    from engine.capacidades import capacidades_que_producen

    desde_matriz: dict[str, set[str]] = {}
    for capacidad_id, fila in apoyo_permisos.capacidades().items():
        for tipo in apoyo_permisos.eventos_de(fila):
            desde_matriz.setdefault(tipo, set()).add(capacidad_id)
    assert desde_matriz, "la matriz no declara ningun evento"
    for tipo, esperadas in sorted(desde_matriz.items()):
        obtenidas = {capacidad.id for capacidad in capacidades_que_producen(tipo)}
        assert obtenidas == esperadas, (
            f"{tipo}: la consulta da {sorted(obtenidas)} y la matriz {sorted(esperadas)}"
        )


@sin_matriz
def test_la_matriz_no_declara_ningun_evento_fuera_del_catalogo_cerrado() -> None:
    """Regla 2 de `ADR-011` §2. Desde S3.1b tampoco en `eventos_propuestos`: ya existen todos."""
    inventados = sorted(
        {
            tipo
            for fila in apoyo_permisos.capacidades().values()
            for tipo in apoyo_permisos.eventos_de(fila)
            if tipo not in TIPOS
        }
    )
    assert not inventados, f"la matriz declara eventos que no existen: {inventados}"


@sin_matriz
@pytest.mark.parametrize("tipo", sorted(apoyo_permisos.ROLES_LEGADO))
def test_los_roles_de_apoyo_coinciden_con_la_matriz(tipo: str) -> None:
    """`ROLES_LEGADO` es la red de seguridad del banco de pruebas: que no se despegue de la matriz."""
    assert apoyo_permisos.ROLES_LEGADO[tipo] in apoyo_permisos.perfiles_que_conceden(tipo)


# ---------------------------------------------------------------------------
# Criterio 3: CAP-10 y CAP-22, unicos disparadores humanos de sus transiciones
# ---------------------------------------------------------------------------


def _actor_para(tipo: str) -> Actor:
    if tipo in TIPOS_SOLO_HUMANO:
        return humano_para(tipo)
    return Actor("humano", "cualquiera@tenant", rol="T-RES")


def test_cap_10_es_el_unico_disparador_humano_de_la_revision() -> None:
    """`RevisionAprobada` (CAP-10) y su equivalente antiguo. Ningun otro tipo pone `revisada_por_humano`."""
    partida = en_estado("EN_REVISION_HUMANA", veredicto=VEREDICTO_PREVALIDADO)
    disparan = []
    for tipo in sorted(TIPOS):
        evento = suceso(tipo, {"origen": ORIGEN_REVISION}, actor=_actor_para(tipo))
        try:
            despues = aplicar(partida, evento)
        except ErrorEstado:
            continue
        if despues.revisada_por_humano:
            disparan.append(tipo)
    assert disparan == sorted([TIPO_REVISION_APROBADA, "ObservacionRegistrada"]), disparan


def test_cap_22_es_el_unico_disparador_humano_de_la_entrada_en_plataforma() -> None:
    """`FirmaRegistrada` (CAP-22) y nada mas mueve `ENTREGADA` -> `EN_PLATAFORMA`."""
    partida = en_estado("ENTREGADA", veredicto=VEREDICTO_PREVALIDADO, revisada_por_humano=True)
    disparan = []
    for tipo in sorted(TIPOS):
        evento = suceso(tipo, {"origen": ORIGEN_REVISION}, actor=_actor_para(tipo))
        try:
            despues = aplicar(partida, evento)
        except ErrorEstado:
            continue
        if despues.estado_ciclo == "EN_PLATAFORMA" or despues.firmada:
            disparan.append(tipo)
    assert disparan == ["FirmaRegistrada"], disparan


@pytest.mark.parametrize("clase", ["motor", "agente", "plataforma"])
def test_ninguna_maquina_aprueba_una_revision_ni_descarta(clase: str) -> None:
    payload = dict(PAYLOAD_AGENTE) if clase == "agente" else {}
    maquina = Actor(clase, f"{clase}@test")
    with pytest.raises(ErrorEstado, match="actor humano"):
        aplicar(en_estado("EN_REVISION_HUMANA"), suceso(TIPO_REVISION_APROBADA, payload, actor=maquina))
    with pytest.raises(ErrorEstado, match="actor humano"):
        aplicar(
            en_estado("EVALUADA", veredicto=VEREDICTO_NO_ELEGIBLE),
            suceso(TIPO_ACTUACION_DESCARTADA, payload, actor=maquina),
        )
    # Y el log no deja ni siquiera sellarlos.
    log = LogEventos(ACT)
    for tipo in (TIPO_REVISION_APROBADA, TIPO_ACTUACION_DESCARTADA):
        with pytest.raises(ErrorEvento, match="actor humano"):
            log.anadir(tipo, payload, actor=maquina)


# ---------------------------------------------------------------------------
# Los dos caminos: tipo propio y el apano anterior
# ---------------------------------------------------------------------------


def test_revision_aprobada_y_el_apano_anterior_llevan_al_mismo_sitio() -> None:
    partida = en_estado("EN_REVISION_HUMANA", veredicto=VEREDICTO_PREVALIDADO)
    por_tipo = aplicar(partida, suceso(TIPO_REVISION_APROBADA, {"nota": "ok"}, actor=REVISOR))
    por_origen = aplicar(partida, suceso("ObservacionRegistrada", {"origen": ORIGEN_REVISION}, actor=REVISOR))
    assert por_tipo.estado_ciclo == por_origen.estado_ciclo == "EVALUADA"
    assert por_tipo.revisada_por_humano is por_origen.revisada_por_humano is True


def test_actuacion_descartada_y_el_apano_anterior_llevan_al_mismo_sitio() -> None:
    partida = en_estado("EVALUADA", veredicto=VEREDICTO_NO_ELEGIBLE)
    por_tipo = aplicar(partida, suceso(TIPO_ACTUACION_DESCARTADA, {"motivo": "fuera"}, actor=REVISOR))
    por_origen = aplicar(partida, suceso("ObservacionRegistrada", {"origen": ORIGEN_DESCARTE}, actor=REVISOR))
    assert por_tipo.estado_ciclo == por_origen.estado_ciclo == "DESCARTADA"
    assert por_tipo.resultado == por_origen.resultado == "descartada"


def test_descartar_sigue_exigiendo_no_elegible_por_el_camino_nuevo() -> None:
    """El tipo propio no relaja la guarda: las dos condiciones, veredicto y humano (`docs/03` §7.2)."""
    partida = en_estado("EVALUADA", veredicto=VEREDICTO_PREVALIDADO)
    with pytest.raises(ErrorEstado, match=VEREDICTO_NO_ELEGIBLE):
        aplicar(partida, suceso(TIPO_ACTUACION_DESCARTADA, {}, actor=REVISOR))


def test_el_ciclo_completo_con_los_tipos_propios() -> None:
    """De `ABIERTA` a `EN_PLATAFORMA` escribiendo lo bueno: `RevisionAprobada` y `FirmaRegistrada`."""
    from engine.estados import proyectar

    log = LogEventos(ACT)
    log.anadir("ActuacionAbierta", {}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("DocumentoRegistrado", {"doc_id": "d1"}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("VeredictoEmitido", {"veredicto": VEREDICTO_PREVALIDADO}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("RevisionAprobada", {"nota": "revisada"}, actor=REVISOR, ocurrido_en=INSTANTE)
    log.anadir("ManifiestoGenerado", {}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("EntregadoADelegado", {}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("FirmaRegistrada", {"referencia": "R-1"}, actor=RESPONSABLE, ocurrido_en=INSTANTE)
    proyeccion = proyectar(log)
    assert proyeccion.estado_ciclo == "EN_PLATAFORMA"
    assert proyeccion.revisada_por_humano is True
    assert proyeccion.firmada is True
    log.verificar()
    # Y la traza dice con que perfil se hizo cada acto, que es justo lo que A8 anade.
    assert log.ultimo("RevisionAprobada").actor.rol == "T-REV"
    assert log.ultimo("FirmaRegistrada").actor.rol == "T-RES"


def test_reasignar_no_reescribe_el_actor_de_los_eventos_anteriores() -> None:
    """Metamorfica de `ADR-006`: `ActuacionReasignada` nunca sobrescribe quien hizo lo de antes."""
    log = LogEventos(ACT)
    log.anadir("ActuacionAbierta", {}, actor=MOTOR, ocurrido_en=INSTANTE)
    log.anadir("DocumentoRegistrado", {"doc_id": "d1"}, actor=MOTOR, ocurrido_en=INSTANTE)
    corregido = log.anadir(
        "DatoCorregidoPorHumano",
        {"variable": "P", "justificacion": "placa"},
        actor=humano_para("DatoCorregidoPorHumano", "ana@tenant"),
        ocurrido_en=INSTANTE,
    )
    antes = [(e.evento_id, e.actor) for e in log]
    log.anadir(
        "ActuacionReasignada",
        {"de": "ana@tenant", "a": "luis@tenant"},
        actor=Actor("humano", "jefa@tenant", rol=rol_para("ActuacionReasignada")),
        ocurrido_en=INSTANTE,
    )
    assert [(e.evento_id, e.actor) for e in log][: len(antes)] == antes
    assert corregido.actor.id == "ana@tenant"
    log.verificar()
