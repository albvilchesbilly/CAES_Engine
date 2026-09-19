"""Tests del simulador de la plataforma (S3.4, `ADR-009` §5): `salida/simulador/`.

Lo que se protege aqui, en el orden de las ocho reglas del contrato C7:

1. **Regla 1, la que sostiene todo lo demas**: ni un literal de plataforma en el fuente del simulador. El
   test recorre `salida/simulador/*.py` y comprueba que ninguno de `ESTADOS_PLATAFORMA` aparece escrito.
2. **Caso A**: el paquete se acepta y queda en el estado posterior a la validacion; un adjunto alterado se
   rechaza **nombrando el fichero**; un `hash_manifiesto` manipulado se rechaza.
3. **La firma**: actor no humano se rechaza, perfil `Modificacion` se rechaza, firmar antes de la
   validacion se rechaza, y la firma correcta (humano + perfil `Firma`) avanza al estado que la exige.
4. **Permisos**: `Consulta` ni crea ni firma.
5. **Estados**: un literal desconocido se rechaza; los de fases 2-4 salen con `oficial: False`; un
   requerimiento del GA alcanza al expediente entero (contagio) y deja tarea pendiente.
6. **P9**: `eventos_en` escribe `EstadoPlataformaRecibido` y `TareaPendienteRecibida` con actor de clase
   `plataforma`, y lo que escribe lo entiende `engine.estados` sin traduccion.
7. **Determinismo**: dos corridas con el mismo instante dan el mismo acuse byte a byte.

El paquete se arma **a mano** (mapeo ficticio, ver `MAPEO_ID`): la mitad A de S3.4 (`salida/mapeo.py` y
`salida/handoff/`) va en paralelo y este banco no la espera. Los casos se procesan una sola vez por sesion
y sin OCR; lo que un test altera es siempre una **copia** en `tmp_path`, nunca `expedientes/`.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path

import pytest

from engine.estados import (
    ESTADOS_PLATAFORMA,
    Proyeccion,
    aplicar,
    propagar_requerimiento,
    tabla_plataforma,
)
from engine.eventos import Actor, LogEventos, grabar
from engine.modelo import ActuacionCanonica, a_dict, desde_motor
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry
from salida.constructor import Manifiesto, construir
from salida.puerto import Acuse, ErrorSalida, EstadoPlataforma, Paquete, PuertoSalida, adjuntos_de
from salida.simulador import (
    PERFIL_CONSULTA,
    PERFIL_FIRMA,
    PERFIL_MODIFICACION,
    PREFIJO_REFERENCIA,
    Credencial,
    ErrorSimulador,
    Simulador,
    estado_creacion,
    estado_firmado,
    estado_validado,
    referencia_de,
)

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_SIMULADOR = RAIZ / "salida" / "simulador"
FECHA = date(2026, 9, 18)

#: Instante fijo: sin el, los acuses llevarian la hora del reloj y no serian comparables.
INSTANTE = datetime(2026, 9, 19, 10, 40, tzinfo=UTC)

CASO_A = "EXP001-A_completo"

#: Identificadores del mapeo: **FICTICIOS**. El mapeo declarativo de verdad (`salida/mapeo.py`,
#: `mapping/IND240.handoff.yaml`) es la mitad A de S3.4 y este banco no depende de ella.
MAPEO_ID = "FICTICIO-test-simulador"
MAPEO_VERSION = "0.0-ficticio"

ADJUNTO_ALTERABLE = "03_factura.pdf"


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


@cache
def procesado(caso: str):
    return procesar_actuacion(CARPETA_CASOS / caso, fecha_evaluacion=FECHA, ocr=False, registro=_registro())


@cache
def canonica(caso: str) -> ActuacionCanonica:
    return desde_motor(procesado(caso))


def copia(caso: str, destino: Path) -> Path:
    """Copia del paquete del caso en `tmp_path`: lo que se altera nunca es `expedientes/`."""
    carpeta = destino / caso
    shutil.copytree(CARPETA_CASOS / caso, carpeta)
    return carpeta


def paquete_de(caso: str, raiz: Path, *, manifiesto: Manifiesto | None = None) -> Paquete:
    """Un `Paquete` armado a mano sobre el manifiesto real del caso (payload minimo, mapeo ficticio)."""
    actuacion = canonica(caso)
    documento = a_dict(actuacion)
    man = manifiesto or construir(actuacion, generado_en=INSTANTE, raiz=raiz)
    evaluacion = documento.get("evaluacion") or {}
    return Paquete(
        actuacion_id=actuacion.id,
        codigo_identificativo_propio=actuacion.codigo_identificativo_propio,
        destino="handoff",
        mapeo_id=MAPEO_ID,
        mapeo_version=MAPEO_VERSION,
        generado_en=INSTANTE,
        payload={"cabecera": {}, "detalle": {"ficha": dict(actuacion.ficha)}},
        manifiesto=man,
        adjuntos=adjuntos_de(man),
        raiz=str(raiz),
        veredicto=evaluacion.get("veredicto"),
    )


def credencial(perfil: str = PERFIL_FIRMA) -> Credencial:
    return Credencial(usuario_id="u-001", perfil=perfil, tenant_id="tenant-001")


def simulador() -> Simulador:
    """Siempre con el reloj congelado: el determinismo es parte del contrato, no una casualidad."""
    return Simulador(instante=INSTANTE)


def fila_de_origen(origen: str):
    """La fila de la tabla cuyo requerimiento tiene ese origen (`verificador`, `GA`, `CN`)."""
    for fila in tabla_plataforma().values():
        if fila.origen_subsanacion == origen:
            return fila
    raise AssertionError(f"la tabla no declara ningun estado con origen de subsanacion {origen!r}")


def primera_fila_de_expediente():
    """El primer estado de nivel expediente (fases 2-4): nombre nuestro, `oficial: False`."""
    for fila in tabla_plataforma().values():
        if fila.nivel == "expediente":
            return fila
    raise AssertionError("la tabla no declara estados de expediente")


def fuentes_del_simulador() -> dict[str, str]:
    return {ruta.name: ruta.read_text(encoding="utf-8") for ruta in sorted(CARPETA_SIMULADOR.rglob("*.py"))}


# ---------------------------------------------------------------------------
# 1. Regla 1: ni un literal de plataforma en el codigo del simulador
# ---------------------------------------------------------------------------


def test_ni_un_literal_de_plataforma_en_el_fuente_del_simulador():
    """Si el diccionario renombra un estado, cambia el YAML y este paquete no se toca (`ADR-009` §5.1)."""
    fuentes = fuentes_del_simulador()
    assert fuentes, "no hay fuentes que revisar en salida/simulador/"
    encontrados = {
        f"{nombre}:{literal}"
        for nombre, texto in fuentes.items()
        for literal in ESTADOS_PLATAFORMA
        if literal in texto
    }
    assert not encontrados, f"literales de plataforma escritos en el fuente: {sorted(encontrados)}"


def test_los_tres_estados_que_usa_el_simulador_se_derivan_de_la_tabla():
    """Creacion, validado y firmado salen de la tabla por sus atributos, no por su nombre."""
    tabla = tabla_plataforma()
    for fila in (estado_creacion(), estado_validado(), estado_firmado()):
        assert tabla[fila.literal] is fila
        assert fila.nivel == "actuacion"
        assert fila.oficial, "los tres son de los 8 confirmados de docs/02 §5.1"
    assert estado_creacion().literal != estado_validado().literal
    assert estado_firmado().exige_firma
    assert not estado_creacion().exige_firma and not estado_validado().exige_firma
    assert estado_creacion().modificable and estado_validado().modificable


def test_el_fuente_del_simulador_no_usa_eval_ni_coma_flotante_ni_uuid4():
    """Higiene: nada de `eval`, nada de `float`, y ningun identificador que no sea reproducible."""
    prohibidos = (r"\beval\(", r"\bexec\(", r"\bcompile\(", r"\bfloat\(", r"uuid4", r"datetime\.now\(")
    for nombre, texto in fuentes_del_simulador().items():
        for patron in prohibidos:
            assert not re.search(patron, texto), f"{nombre} usa {patron}"


# ---------------------------------------------------------------------------
# 2. Caso A: se acepta; alterado, se rechaza nombrando el fichero
# ---------------------------------------------------------------------------


def test_el_paquete_del_caso_a_se_acepta_y_queda_validado(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    acuse = simulador().entregar(paquete_de(CASO_A, raiz), credencial=credencial(), canonica=canonica(CASO_A))
    assert isinstance(acuse, Acuse)
    assert acuse.aceptado and not acuse.motivos
    assert acuse.estado_plataforma == estado_validado().literal
    assert acuse.via == "simulador"
    assert acuse.instante == INSTANTE


def test_la_referencia_es_nuestra_y_se_deriva_del_codigo_y_del_hash(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    paquete = paquete_de(CASO_A, raiz)
    acuse = simulador().entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A))
    assert acuse.referencia == referencia_de(paquete)
    assert acuse.referencia.startswith(f"{PREFIJO_REFERENCIA}-")
    assert paquete.codigo_identificativo_propio in acuse.referencia
    assert paquete.hash_paquete[:12] in acuse.referencia


def test_un_adjunto_alterado_se_rechaza_nombrando_el_fichero(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    paquete = paquete_de(CASO_A, raiz)  # el manifiesto se construye ANTES de tocar el fichero
    fichero = raiz / ADJUNTO_ALTERABLE
    fichero.write_bytes(fichero.read_bytes() + b"\n")  # un byte de mas: eso basta

    acuse = simulador().entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A))

    assert not acuse.aceptado
    assert any(ADJUNTO_ALTERABLE in motivo for motivo in acuse.motivos), acuse.motivos
    assert acuse.estado_plataforma == estado_creacion().literal, "un rechazo no valida nada"


def test_un_hash_de_manifiesto_manipulado_se_rechaza(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    manifiesto = construir(canonica(CASO_A), generado_en=INSTANTE, raiz=raiz)
    manipulado = replace(manifiesto, hash_manifiesto="0" * 64)
    paquete = paquete_de(CASO_A, raiz, manifiesto=manipulado)

    acuse = simulador().entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A))

    assert not acuse.aceptado
    assert any("altero despues de sellarse" in motivo for motivo in acuse.motivos), acuse.motivos
    assert acuse.hash_paquete == manipulado.hash_manifiesto


def test_sin_modelo_canonico_no_se_puede_demostrar_el_esquema(tmp_path):
    """Declarado no es demostrado: sin el modelo canonico, la validacion de esquema no se da por hecha."""
    raiz = copia(CASO_A, tmp_path)
    acuse = simulador().entregar(paquete_de(CASO_A, raiz), credencial=credencial())
    assert not acuse.aceptado
    assert any("modelo canonico" in motivo for motivo in acuse.motivos), acuse.motivos


# ---------------------------------------------------------------------------
# 3. La firma: humana, con perfil Firma, y despues de la validacion
# ---------------------------------------------------------------------------


def _validado(tmp_path) -> tuple[Simulador, str]:
    raiz = copia(CASO_A, tmp_path)
    sim = simulador()
    acuse = sim.entregar(paquete_de(CASO_A, raiz), credencial=credencial(), canonica=canonica(CASO_A))
    assert acuse.aceptado
    return sim, acuse.referencia


@pytest.mark.parametrize("clase", ["motor", "agente", "plataforma"])
def test_la_firma_con_actor_no_humano_se_rechaza(tmp_path, clase):
    """Ningun componente nuestro firma actos administrativos (`CLAUDE.md` §2, `docs/02` §6.2)."""
    sim, referencia = _validado(tmp_path)
    with pytest.raises(ErrorSimulador, match="acto humano"):
        sim.registrar_firma(referencia, Actor(clase, "componente"), credencial=credencial())
    assert sim.consultar_estado(referencia).literal == estado_validado().literal


def test_la_firma_con_perfil_modificacion_se_rechaza(tmp_path):
    """`docs/02` §2.2: `Modificacion` crea y carga, pero no firma."""
    sim, referencia = _validado(tmp_path)
    with pytest.raises(ErrorSimulador, match="no firma"):
        sim.registrar_firma(
            referencia, Actor("humano", "persona"), credencial=credencial(PERFIL_MODIFICACION)
        )


def test_la_firma_correcta_avanza_al_estado_que_la_exige(tmp_path):
    sim, referencia = _validado(tmp_path)
    acuse = sim.registrar_firma(referencia, Actor("humano", "responsable"), credencial=credencial())
    assert acuse.aceptado
    assert acuse.estado_plataforma == estado_firmado().literal
    assert sim.consultar_estado(referencia).literal == estado_firmado().literal
    assert acuse.detalle["firmado_por"] == {"clase": "humano", "id": "responsable"}


def test_la_firma_acepta_el_evento_del_log_como_prueba(tmp_path):
    """La prueba natural es el `FirmaRegistrada` del log, que ya exige actor humano."""
    sim, referencia = _validado(tmp_path)
    log = grabar(procesado(CASO_A), instante=INSTANTE)
    evento = log.anadir("FirmaRegistrada", {"referencia": referencia}, actor=Actor("humano", "responsable"))
    acuse = sim.registrar_firma(referencia, evento, credencial=credencial())
    assert acuse.estado_plataforma == estado_firmado().literal


def test_firmar_antes_de_la_validacion_se_rechaza(tmp_path):
    """La automatizacion termina en el estado validado; la firma viene despues (`docs/02` §6.2)."""
    raiz = copia(CASO_A, tmp_path)
    sim = simulador()
    acuse = sim.crear_borrador(paquete_de(CASO_A, raiz), credencial(), canonica=canonica(CASO_A))
    with pytest.raises(ErrorSimulador, match="despues de la validacion"):
        sim.registrar_firma(acuse.referencia, Actor("humano", "responsable"), credencial=credencial())


def test_el_simulador_no_avanza_solo_mas_alla_del_estado_validado(tmp_path):
    """Regla 3: entregar deja la referencia validada y ni un paso mas."""
    raiz = copia(CASO_A, tmp_path)
    sim = simulador()
    acuse = sim.entregar(paquete_de(CASO_A, raiz), credencial=credencial(), canonica=canonica(CASO_A))
    assert sim.consultar_estado(acuse.referencia).literal == estado_validado().literal
    with pytest.raises(ErrorSimulador, match="no esta firmada"):
        sim.avanzar(acuse.referencia, estado_firmado().literal)


# ---------------------------------------------------------------------------
# 4. Permisos por perfil (`docs/02` §2.2)
# ---------------------------------------------------------------------------


def test_el_perfil_consulta_ni_crea_ni_firma(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    sim = simulador()
    with pytest.raises(ErrorSimulador, match="no crea ni carga"):
        sim.crear_borrador(paquete_de(CASO_A, raiz), credencial(PERFIL_CONSULTA))


def test_un_perfil_desconocido_no_existe():
    with pytest.raises(ErrorSimulador, match="perfil desconocido"):
        Credencial(usuario_id="u", perfil="Administrador", tenant_id="t")


def test_entregar_sin_credencial_se_niega(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    with pytest.raises(ErrorSimulador, match="exige credencial"):
        simulador().entregar(paquete_de(CASO_A, raiz))


# ---------------------------------------------------------------------------
# 5. Estados: desconocido, provisionales y contagio
# ---------------------------------------------------------------------------


def test_un_literal_desconocido_se_rechaza(tmp_path):
    sim, referencia = _validado(tmp_path)
    with pytest.raises(ErrorSimulador, match="no conoce el literal"):
        sim.avanzar(referencia, "PENDIENTE_DE_INVENTAR")


def test_los_estados_de_fases_2_a_4_salen_como_no_oficiales(tmp_path):
    """Regla 6: son nombres nuestros. Ningun test afirma que la plataforma devuelva estos literales."""
    sim, referencia = _validado(tmp_path)
    fila = primera_fila_de_expediente()
    estado = sim.avanzar(referencia, fila.literal)
    assert isinstance(estado, EstadoPlataforma)
    assert estado.oficial is False
    assert estado.nivel == "expediente"


def test_un_requerimiento_del_ga_deja_tarea_y_contagia_al_expediente(tmp_path):
    """`docs/02` §5.6: el requerimiento del GA alcanza a TODAS las actuaciones del expediente."""
    sim, referencia = _validado(tmp_path)
    fila = fila_de_origen("GA")
    estado = sim.avanzar(referencia, fila.literal, motivos=("falta el convenio",))

    assert estado.literal == fila.literal and estado.oficial is False
    assert estado.motivos == ("falta el convenio",)
    tareas = sim.consultar_tareas("tenant-001")
    assert len(tareas) == 1 and tareas[0].referencia == referencia
    assert tareas[0].vence_en is None, "la plataforma no publica plazos (API-10)"

    log = LogEventos(actuacion_id=canonica(CASO_A).id)
    eventos = sim.eventos_en(log, referencia)
    evento_ga = [e for e in eventos if e.payload.get("literal") == fila.literal][0]
    hermanas = (
        Proyeccion(actuacion_id=canonica(CASO_A).id, estado_ciclo="EVALUADA"),
        Proyeccion(actuacion_id="ACT-hermana", estado_ciclo="EVALUADA"),
    )
    propagadas = propagar_requerimiento(hermanas, evento_ga)
    assert [p.estado_ciclo for p in propagadas] == ["PENDIENTE_SUBSANACION"] * 2
    assert [p.origen_subsanacion for p in propagadas] == ["GA", "GA"]
    assert [p.afectada_directamente for p in propagadas] == [True, False]


def test_el_estado_que_exige_desistimiento_pide_un_acto_humano(tmp_path):
    """`docs/02` §5.5: el desistimiento es del sujeto, y tampoco lo hace el simulador."""
    sim, referencia = _validado(tmp_path)
    fila = next(f for f in tabla_plataforma().values() if f.exige_desistimiento)
    with pytest.raises(ErrorSimulador, match="DesistimientoRegistrado"):
        sim.avanzar(referencia, fila.literal)
    with pytest.raises(ErrorSimulador, match="actor humano"):
        sim.avanzar(referencia, fila.literal, evidencia=Actor("motor", "engine"))
    estado = sim.avanzar(referencia, fila.literal, evidencia=Actor("humano", "sujeto"))
    assert estado.literal == fila.literal


def test_consultar_una_referencia_desconocida_se_niega():
    with pytest.raises(ErrorSimulador, match="no conoce la referencia"):
        simulador().consultar_estado("SIM-lo-que-sea")


# ---------------------------------------------------------------------------
# 6. P9: lo que la plataforma dijo, como eventos del log
# ---------------------------------------------------------------------------


def test_eventos_en_escribe_p9_con_actor_plataforma(tmp_path):
    sim, referencia = _validado(tmp_path)
    sim.registrar_firma(referencia, Actor("humano", "responsable"), credencial=credencial())
    sim.avanzar(referencia, fila_de_origen("verificador").literal)

    log = LogEventos(actuacion_id=canonica(CASO_A).id)
    eventos = sim.eventos_en(log, referencia)

    tipos = [e.tipo for e in eventos]
    assert tipos.count("EstadoPlataformaRecibido") == len(sim.historia(referencia))
    assert "TareaPendienteRecibida" in tipos
    assert {e.actor.clase for e in eventos} == {"plataforma"}
    log.verificar()


def test_eventos_en_es_idempotente(tmp_path):
    sim, referencia = _validado(tmp_path)
    log = LogEventos(actuacion_id=canonica(CASO_A).id)
    primeros = sim.eventos_en(log, referencia)
    assert primeros and not sim.eventos_en(log, referencia)


def test_eventos_en_no_mezcla_actuaciones(tmp_path):
    sim, referencia = _validado(tmp_path)
    with pytest.raises(ErrorSimulador, match="no se mezclan"):
        sim.eventos_en(LogEventos(actuacion_id="OTRA"), referencia)


def test_lo_que_escribe_el_simulador_lo_entiende_la_maquina_de_estados(tmp_path):
    """El literal viaja en el payload tal y como `engine.estados` lo espera: sin traduccion por el camino."""
    sim, referencia = _validado(tmp_path)
    log = LogEventos(actuacion_id=canonica(CASO_A).id)
    eventos = sim.eventos_en(log, referencia)
    proyeccion = Proyeccion(actuacion_id=canonica(CASO_A).id, estado_ciclo="LISTA_PARA_ENVIO")
    for evento in eventos:
        proyeccion = aplicar(proyeccion, evento)
    assert proyeccion.estado_plataforma == estado_validado().literal
    assert proyeccion.estado_ciclo == "ENTREGADA"


# ---------------------------------------------------------------------------
# 7. Determinismo y contrato del puerto
# ---------------------------------------------------------------------------


def test_dos_corridas_iguales_dan_el_mismo_resultado(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    paquete = paquete_de(CASO_A, raiz)
    acuses = [
        simulador().entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A)).a_dict()
        for _ in range(2)
    ]
    assert acuses[0] == acuses[1]


def test_no_se_admiten_los_dos_relojes_a_la_vez():
    with pytest.raises(ErrorSimulador, match="no los dos"):
        Simulador(instante=INSTANTE, reloj=lambda: INSTANTE)


def test_un_instante_sin_zona_se_rechaza():
    with pytest.raises(ErrorSimulador, match="instante invalido"):
        Simulador(instante=datetime(2026, 9, 19, 10, 40))


def test_el_simulador_cumple_el_puerto_y_se_niega_a_construir():
    sim = simulador()
    assert isinstance(sim, PuertoSalida)
    assert sim.nombre == "simulador"
    with pytest.raises(ErrorSalida, match="no construye paquetes"):
        sim.construir(object(), object())


def test_crear_dos_veces_el_mismo_paquete_es_idempotente(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    paquete = paquete_de(CASO_A, raiz)
    sim = simulador()
    primero = sim.crear_borrador(paquete, credencial(), canonica=canonica(CASO_A))
    segundo = sim.crear_borrador(paquete, credencial(), canonica=canonica(CASO_A))
    assert primero.referencia == segundo.referencia
    assert segundo.detalle["idempotente"] is True
    assert len(sim.historia(primero.referencia)) == 1


def test_una_actuacion_firmada_no_se_vuelve_a_cargar(tmp_path):
    """Inalterabilidad (`docs/02` §5.4): tras la firma, solo por requerimiento oficial."""
    raiz = copia(CASO_A, tmp_path)
    paquete = paquete_de(CASO_A, raiz)
    sim = simulador()
    acuse = sim.entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A))
    sim.registrar_firma(acuse.referencia, Actor("humano", "responsable"), credencial=credencial())
    with pytest.raises(ErrorSimulador, match="inalterabilidad"):
        sim.crear_borrador(paquete, credencial(), canonica=canonica(CASO_A))
