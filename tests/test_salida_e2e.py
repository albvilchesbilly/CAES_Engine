"""Extremo a extremo de la salida (S3.4): el caso A por **handoff real -> simulador real**.

Las dos mitades de S3.4 se construyeron en paralelo y cada una se probo contra un sustituto de la otra:
`tests/test_handoff.py` entrega a una carpeta y no pasa por ninguna plataforma, y `tests/test_simulador.py`
arma el `Paquete` **a mano**, con un `MAPEO_ID` ficticio, porque el mapeo declarativo todavia no existia
cuando se escribio. La costura -- el paquete que sale del mapeo real, escrito por el handoff real, validado
por el simulador real y proyectado por la maquina de estados -- no la habia recorrido nadie. Este fichero es
ese recorrido, y lo que encontro por el camino:

1. **La costura completa**: `procesar_actuacion` -> `construir` con `mapping/IND240.handoff.yaml` ->
   `entregar` a una carpeta -> `Simulador.entregar` con credencial de perfil `Firma` -> aceptado, en el
   estado que la tabla marca `validacion_automatica`. Ni un literal de plataforma escrito a mano: todos se
   derivan de `engine.estados.tabla_plataforma()`.
2. **Integridad**: un byte cambiado en la raiz del paquete lo rechaza el simulador nombrando el fichero; el
   `hash_manifiesto` manipulado se rechaza con **otro** motivo; y un byte cambiado en la **carpeta ya
   entregada** no lo ve el simulador (valida la raiz del paquete, no la carpeta), asi que lo comprueba
   `AdaptadorHandoff.verificar_entrega`, que existe por este hallazgo.
3. **La firma**: actor `motor` no firma; humano con perfil `Modificacion` tampoco; humano con perfil `Firma`
   avanza al estado que la tabla marca `exige_firma`. El simulador no firma: comprueba que alguien firmo.
4. **El log cierra el circulo**: los eventos P8 del handoff y P9 del simulador se proyectan **sin
   traduccion** y dejan la actuacion en `EN_PLATAFORMA`, `firmada`, con `via_entrega` handoff.
5. **Regla de oro 4**: una ficha nueva en la salida es **solo YAML**. Se da de alta una ficha inventada en
   `tmp_path` y se aplica sin tocar una linea de `salida/`.
6. **Regla de oro 10 e higiene**: cada `TODO(API-xx)` de `salida/` y de `mapping/` esta en `docs/HUECOS.md`;
   `resolver` no llega a ningun atributo de Python; y `salida/` no evalua ni usa coma flotante.
7. **Determinismo**: con el reloj inyectado, dos entregas del caso A son **byte a byte** la misma carpeta.
8. **Modo degradado al reves**: con `salida/` importada de verdad (no la falsa de
   `tests/test_modo_degradado.py`), el nucleo sigue resolviendo los siete casos, y **ningun** modulo
   de `engine/` -- subpaquetes incluidos -- importa `salida`.
9. **Los casos que no son el A**: el C (contradictorio, `BLOQUEADO`), el D (fuera de ambito, `NO_ELEGIBLE`) y
   el G (desordenado, con partes de un PDF combinado) tambien recorren la costura. Ninguna de las dos
   mitades los habia visto: `tests/test_simulador.py` solo usa el A.

Sin OCR y sin `poppler`/`tesseract`: nada de aqui los necesita. Lo que un test altera es siempre una copia en
`tmp_path`; `expedientes/` no se toca nunca.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from engine.estados import proyectar, tabla_plataforma
from engine.eventos import grabar
from engine.eventos.log import Actor, LogEventos
from engine.modelo import ActuacionCanonica, desde_motor
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry
from salida.handoff import CLAVES_ARBOL, AdaptadorHandoff
from salida.mapeo import Mapeo, aplicar, cargar, resolver
from salida.puerto import ErrorSalida, Paquete
from salida.simulador import (
    PERFIL_FIRMA,
    PERFIL_MODIFICACION,
    Credencial,
    ErrorSimulador,
    Simulador,
    estado_creacion,
    estado_firmado,
    estado_validado,
)

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_GROUND_TRUTH = CARPETA_CASOS / "_resultados_esperados"
CARPETA_SALIDA = RAIZ / "salida"
CARPETA_MAPPING = RAIZ / "mapping"
PAQUETE_ENGINE = RAIZ / "engine"
HUECOS = RAIZ / "docs" / "HUECOS.md"

FECHA = date(2026, 9, 18)

#: Reloj congelado. El simulador ya lo exigia; el handoff lo admite desde este banco (ver el informe de QA).
INSTANTE = datetime(2026, 9, 19, 10, 40, tzinfo=UTC)

CASO_A = "EXP001-A_completo"
CASOS = (
    "EXP001-A_completo",
    "EXP001-B_falta_registro",
    "EXP001-C_contradictorio",
    "EXP001-D_fuera_ambito",
    "EXP001-E_dos_motores",
    "EXP001-F_tres_motores",
    "EXP001-G_desordenado",
)

#: Un adjunto del caso A que existe en disco y se puede alterar en una copia.
ADJUNTO = "03_factura.pdf"


# ---------------------------------------------------------------------------
# Utilidades: cada caso se procesa una sola vez por sesion
# ---------------------------------------------------------------------------


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


def ground_truth(caso: str) -> dict:
    return json.loads((CARPETA_GROUND_TRUTH / f"{caso}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mapeo() -> Mapeo:
    """El mapeo **real** de `mapping/`, no uno ficticio: la costura es justo lo que no se habia probado."""
    return cargar("IND240", "handoff")


def copia(caso: str, destino: Path) -> Path:
    carpeta = destino / caso
    shutil.copytree(CARPETA_CASOS / caso, carpeta)
    return carpeta


def log_revisado(caso: str) -> LogEventos:
    """El log del caso con la revision humana que exige `LISTA_PARA_ENVIO` (`docs/03` §7.3)."""
    log = grabar(procesado(caso))
    log.anadir(
        "ObservacionRegistrada",
        {"origen": "revision_humana", "texto": "revisado antes de empaquetar"},
        actor=("humano", "revisor@tenant"),
    )
    return log


def credencial(perfil: str = PERFIL_FIRMA) -> Credencial:
    return Credencial(usuario_id="u-001", perfil=perfil, tenant_id="tenant-001")


def ficheros(carpeta: Path) -> dict[str, bytes]:
    return {f.relative_to(carpeta).as_posix(): f.read_bytes() for f in carpeta.rglob("*") if f.is_file()}


def recorrido(tmp_path: Path, *, con_log: bool = True) -> tuple[AdaptadorHandoff, Paquete, Path, LogEventos]:
    """Caso A hasta la carpeta entregada: es el punto de partida de casi todo lo de abajo."""
    raiz = copia(CASO_A, tmp_path)
    log = log_revisado(CASO_A) if con_log else None
    adaptador = AdaptadorHandoff(instante=INSTANTE)
    mapeo_real = cargar("IND240", "handoff")
    paquete = adaptador.construir(procesado(CASO_A), mapeo_real, raiz=raiz, log=log)
    entrega = tmp_path / "entrega"
    acuse = adaptador.entregar(paquete, destino_carpeta=entrega, mapeo=mapeo_real, log=log)
    assert acuse.aceptado, acuse.motivos
    return adaptador, paquete, entrega, log


# ---------------------------------------------------------------------------
# 1. La costura: handoff real -> simulador real
# ---------------------------------------------------------------------------


def test_el_caso_a_recorre_el_handoff_y_lo_acepta_el_simulador(tmp_path: Path, mapeo: Mapeo) -> None:
    """El paquete que produce el mapeo real, escrito por el handoff real, lo valida el simulador real."""
    raiz = copia(CASO_A, tmp_path)
    log = log_revisado(CASO_A)
    adaptador = AdaptadorHandoff(instante=INSTANTE)

    paquete = adaptador.construir(procesado(CASO_A), mapeo, raiz=raiz, log=log)
    assert paquete.veredicto == "PREVALIDADO"
    assert paquete.carencias == ()
    assert (paquete.mapeo_id, paquete.mapeo_version) == (mapeo.id, mapeo.version)

    acuse_handoff = adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo, log=log)
    assert acuse_handoff.aceptado is True
    assert acuse_handoff.via == "handoff"
    assert acuse_handoff.estado_plataforma is None, "el handoff no es una plataforma y no fija estados"

    acuse = Simulador(instante=INSTANTE).entregar(
        paquete, credencial=credencial(), canonica=canonica(CASO_A), log=log
    )

    assert acuse.aceptado is True, acuse.motivos
    assert acuse.motivos == ()
    assert acuse.via == "simulador"
    assert acuse.hash_paquete == paquete.hash_paquete == paquete.manifiesto.hash_manifiesto
    # El literal se deriva de la tabla por su marca; escribirlo a mano seria escribirlo dos veces.
    assert acuse.estado_plataforma == estado_validado().literal
    assert tabla_plataforma()[acuse.estado_plataforma].validacion_automatica


def test_el_payload_entregado_lleva_el_ahorro_del_motor_sin_tocar(tmp_path: Path, mapeo: Mapeo) -> None:
    """El ahorro llega al tenant tal y como lo calculo el motor: ni redondeado, ni convertido, ni en float."""
    _, _, entrega, _ = recorrido(tmp_path)
    payload = json.loads((entrega / mapeo.fichero("payload")).read_text(encoding="utf-8"))
    detalle = payload["detalle"]["actuacion"]
    esperado = ground_truth(CASO_A)["aetotal_esperado"]

    assert isinstance(detalle["ahorro_total"], str), "un Decimal viaja como cadena, nunca como float"
    assert Decimal(detalle["ahorro_total"]) == Decimal(esperado["exacto"]) == Decimal("305829.6")
    assert detalle["ahorro_total_cae"] == esperado["cae"]
    assert json.dumps(payload).count("e+") == 0, "ninguna magnitud sale en notacion cientifica"


def test_la_carpeta_entregada_se_puede_comprobar_sin_nuestro_software(tmp_path: Path, mapeo: Mapeo) -> None:
    """Las huellas del `99_verificacion.txt` son las del manifiesto y cuadran con los bytes escritos."""
    _, paquete, entrega, _ = recorrido(tmp_path)
    texto = (entrega / mapeo.fichero("verificacion")).read_text(encoding="utf-8")
    declaradas = dict(
        (linea.split("  ", 1)[1], linea.split("  ", 1)[0])
        for linea in texto.splitlines()
        if re.fullmatch(r"[0-9a-f]{64}  \S.*", linea)
    )
    assert declaradas, "el 99_verificacion.txt no lista ninguna huella"
    escritos = ficheros(entrega)
    for ruta, huella in declaradas.items():
        assert ruta in escritos, ruta
        assert {a.sha256 for a in paquete.adjuntos if not a.es_parte} >= {huella}


# ---------------------------------------------------------------------------
# 2. Integridad: que ve cada mitad y que no ve ninguna
# ---------------------------------------------------------------------------


def test_un_byte_alterado_en_el_paquete_lo_rechaza_el_simulador_nombrando_el_fichero(
    tmp_path: Path, mapeo: Mapeo
) -> None:
    raiz = copia(CASO_A, tmp_path)
    adaptador = AdaptadorHandoff(instante=INSTANTE)
    paquete = adaptador.construir(procesado(CASO_A), mapeo, raiz=raiz)
    adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo)

    victima = raiz / ADJUNTO
    victima.write_bytes(victima.read_bytes() + b"\n")  # un byte de mas basta

    acuse = Simulador(instante=INSTANTE).entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A))

    assert acuse.aceptado is False
    assert any(ADJUNTO in motivo and "alterado" in motivo for motivo in acuse.motivos), acuse.motivos
    assert acuse.estado_plataforma == estado_creacion().literal, "un rechazo no valida nada"


def test_un_manifiesto_manipulado_se_rechaza_con_otro_motivo(tmp_path: Path, mapeo: Mapeo) -> None:
    """Manipular el sello del manifiesto no es lo mismo que manipular un adjunto, y no se dice igual."""
    raiz = copia(CASO_A, tmp_path)
    adaptador = AdaptadorHandoff(instante=INSTANTE)
    paquete = adaptador.construir(procesado(CASO_A), mapeo, raiz=raiz)

    manipulado = replace(paquete, manifiesto=replace(paquete.manifiesto, hash_manifiesto="0" * 64))
    acuse = Simulador(instante=INSTANTE).entregar(
        manipulado, credencial=credencial(), canonica=canonica(CASO_A)
    )

    assert acuse.aceptado is False
    assert any("altero despues de sellarse" in motivo for motivo in acuse.motivos), acuse.motivos
    assert not any(ADJUNTO in motivo for motivo in acuse.motivos), "el adjunto esta intacto: no se le culpa"
    assert acuse.hash_paquete == "0" * 64, "el hash del paquete es el del manifiesto, manipulado incluido"


def test_un_hash_de_fichero_manipulado_en_el_manifiesto_se_rechaza(tmp_path: Path, mapeo: Mapeo) -> None:
    raiz = copia(CASO_A, tmp_path)
    paquete = AdaptadorHandoff(instante=INSTANTE).construir(procesado(CASO_A), mapeo, raiz=raiz)
    ficheros_manifiesto = tuple(
        replace(f, sha256="0" * 64) if f.ruta == ADJUNTO else f for f in paquete.manifiesto.ficheros
    )
    manipulado = replace(paquete, manifiesto=replace(paquete.manifiesto, ficheros=ficheros_manifiesto))

    acuse = Simulador(instante=INSTANTE).entregar(
        manipulado, credencial=credencial(), canonica=canonica(CASO_A)
    )

    assert acuse.aceptado is False
    assert any("altero despues de sellarse" in motivo for motivo in acuse.motivos), acuse.motivos
    assert any(ADJUNTO in motivo for motivo in acuse.motivos), acuse.motivos


def test_un_byte_alterado_en_la_carpeta_entregada_se_detecta_y_se_nombra(
    tmp_path: Path, mapeo: Mapeo
) -> None:
    """La carpeta que recibe el tenant tambien se puede volver a comprobar, y dice **que** fichero cambio."""
    adaptador, paquete, entrega, _ = recorrido(tmp_path)
    assert adaptador.verificar_entrega(paquete, entrega, mapeo=mapeo) == ()

    victima = next(f for f in (entrega / "documentos").rglob("*") if f.is_file())
    victima.write_bytes(victima.read_bytes() + b"\n")

    motivos = adaptador.verificar_entrega(paquete, entrega, mapeo=mapeo)
    relativa = victima.relative_to(entrega).as_posix()
    assert any(relativa in motivo and "alterado" in motivo for motivo in motivos), motivos


def test_el_simulador_valida_la_raiz_del_paquete_y_no_la_carpeta_entregada(
    tmp_path: Path, mapeo: Mapeo
) -> None:
    """Costura declarada, no accidente: el `Paquete` apunta a la raiz de la que salieron los bytes.

    Alterar la carpeta **entregada** no cambia el veredicto del simulador, porque lo que el valida es el
    paquete (`paquete.raiz`), no la copia reordenada por tipo documental que abre el tenant. Quien mira esa
    copia es `AdaptadorHandoff.verificar_entrega` (test de arriba). Este test fija la frontera para que, el
    dia que el conector real de S3.7 la mueva, se sepa que se esta moviendo.
    """
    adaptador, paquete, entrega, _ = recorrido(tmp_path)
    victima = next(f for f in (entrega / "documentos").rglob("*") if f.is_file())
    victima.write_bytes(victima.read_bytes() + b"\n")

    acuse = Simulador(instante=INSTANTE).entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A))

    assert acuse.aceptado is True, "la raiz del paquete sigue intacta"
    assert adaptador.verificar_entrega(paquete, entrega, mapeo=mapeo), (
        "y la carpeta entregada, que no lo esta, tiene quien la mire"
    )


def test_volver_a_entregar_sobre_una_carpeta_alterada_no_la_pisa(tmp_path: Path, mapeo: Mapeo) -> None:
    """Nunca se borra nada del usuario: una carpeta que ya no es la nuestra es `ErrorSalida`."""
    adaptador, paquete, entrega, log = recorrido(tmp_path)
    victima = next(f for f in (entrega / "documentos").rglob("*") if f.is_file())
    alterado = victima.read_bytes() + b"\n"
    victima.write_bytes(alterado)

    with pytest.raises(ErrorSalida, match="entrega distinta"):
        adaptador.entregar(paquete, destino_carpeta=entrega, mapeo=mapeo, log=log)
    assert victima.read_bytes() == alterado, "lo que habia en la carpeta sigue ahi"


def test_el_log_de_la_carpeta_entregada_no_se_trunca(tmp_path: Path, mapeo: Mapeo) -> None:
    """El log es solo-anadir: se tolera que crezca, nunca que encoja.

    La excepcion de idempotencia del log acepta que lo que hay en disco sea **prefijo** de lo que traemos
    (el mismo log mas tarde). Al reves -- en disco hay mas eventos de los que traemos -- reescribir seria
    borrar eventos del usuario, y eso no se hace.
    """
    adaptador, paquete, entrega, log = recorrido(tmp_path)
    # Segunda entrega: deja en disco el log completo, con el evento de entrega ya dentro. Sin este paso lo
    # de disco y lo nuestro se diferencian en dos sitios y el test no aislaria la direccion de la tolerancia.
    adaptador.entregar(paquete, destino_carpeta=entrega, mapeo=mapeo, log=log)
    fichero_log = entrega / mapeo.fichero("log_eventos")
    completo = fichero_log.read_text(encoding="utf-8")
    assert completo == log.a_jsonl(), "en disco esta exactamente nuestro log"

    largo = completo + '{"otro":"un evento que el tenant anadio y nosotros no tenemos"}\n'
    fichero_log.write_text(largo, encoding="utf-8")

    with pytest.raises(ErrorSalida, match="entrega distinta"):
        adaptador.entregar(paquete, destino_carpeta=entrega, mapeo=mapeo, log=log)
    assert fichero_log.read_text(encoding="utf-8") == largo, "no se ha truncado el log del usuario"


def test_el_log_que_crece_si_se_reescribe(tmp_path: Path, mapeo: Mapeo) -> None:
    """La otra direccion si vale: el mismo log con mas eventos es el mismo log, mas tarde."""
    adaptador, paquete, entrega, log = recorrido(tmp_path)
    log.anadir("ObservacionRegistrada", {"texto": "una nota mas"}, actor=("humano", "revisor@tenant"))

    acuse = adaptador.entregar(paquete, destino_carpeta=entrega, mapeo=mapeo, log=log)

    assert acuse.aceptado is True
    assert (entrega / mapeo.fichero("log_eventos")).read_text(encoding="utf-8") == log.a_jsonl()


# ---------------------------------------------------------------------------
# 3. La firma: humana, con perfil Firma, y nunca nuestra
# ---------------------------------------------------------------------------


def _hasta_validado(tmp_path: Path) -> tuple[Simulador, str, LogEventos]:
    _, paquete, _, log = recorrido(tmp_path)
    simulador = Simulador(instante=INSTANTE)
    acuse = simulador.entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A), log=log)
    assert acuse.aceptado, acuse.motivos
    return simulador, acuse.referencia, log


def test_la_firma_de_un_actor_motor_se_rechaza(tmp_path: Path) -> None:
    simulador, referencia, _ = _hasta_validado(tmp_path)
    with pytest.raises(ErrorSimulador, match="acto humano"):
        simulador.registrar_firma(referencia, Actor("motor", "salida.handoff"), credencial=credencial())
    assert simulador.consultar_estado(referencia).literal == estado_validado().literal


def test_la_firma_de_un_humano_con_perfil_modificacion_se_rechaza(tmp_path: Path) -> None:
    simulador, referencia, _ = _hasta_validado(tmp_path)
    with pytest.raises(ErrorSimulador, match="no firma"):
        simulador.registrar_firma(
            referencia,
            Actor("humano", "representante@tenant"),
            credencial=credencial(PERFIL_MODIFICACION),
        )
    assert simulador.consultar_estado(referencia).literal == estado_validado().literal


def test_la_firma_humana_con_perfil_firma_avanza_al_estado_que_la_exige(tmp_path: Path) -> None:
    simulador, referencia, log = _hasta_validado(tmp_path)
    evento = log.anadir(
        "FirmaRegistrada",
        {"nota": "firmado por el representante del tenant, con su certificado"},
        actor=("humano", "representante@tenant"),
    )

    acuse = simulador.registrar_firma(referencia, evento, credencial=credencial())

    assert acuse.aceptado is True
    assert acuse.estado_plataforma == estado_firmado().literal
    assert tabla_plataforma()[acuse.estado_plataforma].exige_firma
    assert acuse.detalle["firmado_por"]["clase"] == "humano"
    assert "el simulador no firma" in str(acuse.detalle["nota"])


def test_ningun_componente_nuestro_firma_en_todo_el_recorrido() -> None:
    """La firma entra desde fuera o no entra: en `salida/` no hay quien la **produzca**.

    No basta con que no exista `salida/firma/`: lo que se comprueba es que ninguna llamada de `salida/`
    anade un `FirmaRegistrada` al log. El simulador lo **lee** como prueba de que una persona firmo; nadie
    aqui lo escribe (`CLAUDE.md` §2, `docs/02` §6.2).
    """
    assert not (CARPETA_SALIDA / "firma").exists()
    for fuente in sorted(CARPETA_SALIDA.rglob("*.py")):
        arbol = ast.parse(fuente.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            llamada = ast.unparse(nodo)
            if ".anadir(" not in llamada:
                continue
            assert "FirmaRegistrada" not in llamada and "TIPO_FIRMA" not in llamada, (
                f"{fuente.name} emite la firma: {llamada[:80]}"
            )


# ---------------------------------------------------------------------------
# 4. El log cierra el circulo: P8 + P9 proyectados sin traduccion
# ---------------------------------------------------------------------------


def test_el_recorrido_completo_deja_la_actuacion_en_plataforma_firmada_por_handoff(
    tmp_path: Path, mapeo: Mapeo
) -> None:
    """Lo que escriben las dos mitades lo entiende `engine.estados.proyectar` sin ninguna traduccion."""
    raiz = copia(CASO_A, tmp_path)
    log = log_revisado(CASO_A)
    adaptador = AdaptadorHandoff(instante=INSTANTE)
    paquete = adaptador.construir(procesado(CASO_A), mapeo, raiz=raiz, log=log)
    assert proyectar(log).estado_ciclo == "LISTA_PARA_ENVIO"

    adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo, log=log)
    entregada = proyectar(log)
    assert entregada.estado_ciclo == "ENTREGADA"
    assert entregada.via_entrega == "handoff"
    assert entregada.firmada is False

    simulador = Simulador(instante=INSTANTE)
    acuse = simulador.entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A), log=log)
    evento = log.anadir(
        "FirmaRegistrada", {"nota": "firma del tenant"}, actor=("humano", "representante@tenant")
    )
    simulador.registrar_firma(acuse.referencia, evento, credencial=credencial())
    simulador.eventos_en(log, acuse.referencia)

    final = proyectar(log)
    assert final.estado_ciclo == "EN_PLATAFORMA"
    assert final.firmada is True
    assert final.via_entrega == "handoff"
    assert final.estado_plataforma == estado_firmado().literal
    assert final.literales_desconocidos == (), "ningun literal del simulador es ajeno a la tabla"

    tipos = {e.tipo for e in log.eventos}
    assert {"PayloadConstruido", "ManifiestoGenerado", "EntregadoADelegado"} <= tipos  # P8
    assert {"EstadoPlataformaRecibido", "FirmaRegistrada"} <= tipos  # P9 + el acto humano


def test_el_log_entregado_es_el_log_menos_su_propia_entrega(tmp_path: Path, mapeo: Mapeo) -> None:
    """El `05_log_eventos.jsonl` no es un resumen: es el log entero **hasta el instante de escribirlo**.

    El evento `EntregadoADelegado` se anade despues de que la carpeta este escrita y verificada -- antes no
    hay entrega que registrar --, asi que el fichero entregado es siempre el log menos ese ultimo evento.
    Eso no es una perdida: es exactamente el prefijo que la excepcion de idempotencia del log tolera.
    """
    _, _, entrega, log = recorrido(tmp_path)
    lineas = (entrega / mapeo.fichero("log_eventos")).read_text(encoding="utf-8").splitlines()
    tipos = [json.loads(linea)["tipo"] for linea in lineas]

    assert tipos == [e.tipo for e in log.eventos][: len(tipos)], "el fichero es un prefijo del log"
    assert [e.tipo for e in log.eventos][len(tipos) :] == ["EntregadoADelegado"]
    assert log.a_jsonl().startswith("\n".join(lineas))


def test_la_actuacion_sin_revision_humana_no_se_entrega(tmp_path: Path, mapeo: Mapeo) -> None:
    """La maquina de estados manda: sin revision humana no hay `LISTA_PARA_ENVIO`, y el log queda intacto."""
    from engine.estados import ErrorEstado

    raiz = copia(CASO_A, tmp_path)
    log = grabar(procesado(CASO_A))  # sin la observacion humana
    eventos = len(log)
    with pytest.raises(ErrorEstado, match="revision humana"):
        AdaptadorHandoff(instante=INSTANTE).construir(procesado(CASO_A), mapeo, raiz=raiz, log=log)
    assert len(log) == eventos, "un evento ensayado y rechazado no se queda pegado al log del llamante"


# ---------------------------------------------------------------------------
# 5. Regla de oro 4: una ficha nueva en la salida es SOLO YAML
# ---------------------------------------------------------------------------

#: Una ficha que no existe, con variables que no son las de IND240. Si hiciera falta tocar `salida/` para
#: darla de alta, el marco estaria mal (regla de oro 4).
MAPEO_FICHA_INVENTADA = """
mapeo:
  id: LUM999.handoff
  ficha: LUM999
  destino: handoff
  version: "0.1"
cabecera: []
detalle_actuacion:
  - clave: titular
    etiqueta: "Titular"
    origen: variables_actuacion.titular_nif.valor_consumido
    obligatorio: true
  - clave: veredicto
    etiqueta: "Veredicto"
    origen: evaluacion.veredicto
    obligatorio: true
  - clave: ahorro_total
    etiqueta: "Ahorro anual total"
    origen: calculo.total
    unidad: "kWh/año"
  - clave: lo_que_no_sabemos_pedir
    etiqueta: "Campo del formulario oficial"
    hueco: API-08
detalle_unidad:
  - clave: potencia_luminaria
    etiqueta: "Potencia de la luminaria"
    origen: variables.potencia_luminaria.valor_consumido
    unidad: W
    obligatorio: true
  - clave: horas
    etiqueta: "Horas anuales"
    origen: variables.horas.valor_consumido
    obligatorio: true
  - clave: ahorro_unidad
    etiqueta: "Ahorro de esta luminaria"
    origen: calculo.salida
documentos:
  carpeta: documentos
  sin_tipo: 99_sin_clasificar
  por_tipo:
    factura: 01_facturas
ficheros:
  leeme: 00_LEEME.md
  payload: 02_payload.json
  informe_markdown: 03_informe.md
  informe_json: 04_informe.json
  log_eventos: 05_log.jsonl
  verificacion: 99_verificacion.txt
"""

#: Un modelo canonico sintetico de esa ficha: ni una variable de IND240.
ACTUACION_INVENTADA = {
    "codigo_identificativo_propio": "LUM999-0001",
    "ficha": {"codigo": "LUM999"},
    "variables_actuacion": {"titular_nif": {"valor_consumido": "B00000000"}},
    "evaluacion": {"veredicto": "PREVALIDADO"},
    "calculo": {
        "total": "1234.5",
        # A PROPOSITO en orden inverso al de `unidades`: si el emparejamiento fuera por posicion en vez
        # de por identidad, cada luminaria se llevaria el ahorro de la otra y el test lo veria.
        "por_unidad": [
            {"num_serie_motor": "LUM-2", "salida": "234.5"},
            {"num_serie_motor": "LUM-1", "salida": "1000.0"},
        ],
    },
    "unidades": [
        {
            "clave": "LUM-1",
            "variables": {
                "potencia_luminaria": {"valor_consumido": "36"},
                "horas": {"valor_consumido": "4000"},
            },
        },
        {"clave": "LUM-2", "variables": {"potencia_luminaria": {"valor_consumido": "18"}}},
    ],
}


def test_una_ficha_nueva_se_da_de_alta_solo_con_yaml(tmp_path: Path) -> None:
    """Se carga y se aplica un mapeo de una ficha que no existe, sin tocar una linea de `salida/`."""
    (tmp_path / "LUM999.handoff.yaml").write_text(MAPEO_FICHA_INVENTADA, encoding="utf-8")
    nuevo = cargar("LUM999", "handoff", carpeta=tmp_path)
    assert (nuevo.ficha, nuevo.destino) == ("LUM999", "handoff")

    payload, carencias = aplicar(nuevo, ACTUACION_INVENTADA)

    assert payload["detalle"]["actuacion"]["titular"] == "B00000000"
    assert payload["detalle"]["actuacion"]["ahorro_total"] == "1234.5"
    assert payload["detalle"]["actuacion"]["lo_que_no_sabemos_pedir"] is None  # hueco: existe y va vacio
    unidades = {u["clave"]: u["campos"] for u in payload["detalle"]["unidades"]}
    assert unidades["LUM-1"]["potencia_luminaria"] == "36"
    assert unidades["LUM-1"]["ahorro_unidad"] == "1000.0", "cada unidad ve SU calculo, no el de la vecina"
    assert unidades["LUM-2"]["ahorro_unidad"] == "234.5"
    # A LUM-2 le falta un obligatorio y se dice de que unidad es; a LUM-1 no le falta nada.
    assert carencias == ("detalle.unidades[LUM-2].horas",)
    assert nuevo.carpeta_de_tipo("factura") == "01_facturas"
    assert nuevo.carpeta_de_tipo("un_tipo_que_no_declara") == "99_sin_clasificar"


def test_el_mapeo_de_una_ficha_no_se_aplica_a_otra(tmp_path: Path, mapeo: Mapeo) -> None:
    (tmp_path / "LUM999.handoff.yaml").write_text(MAPEO_FICHA_INVENTADA, encoding="utf-8")
    ajeno = cargar("LUM999", "handoff", carpeta=tmp_path)
    with pytest.raises(ErrorSalida, match="no se aplica a otra ficha"):
        AdaptadorHandoff(instante=INSTANTE).construir(procesado(CASO_A), ajeno, raiz=CARPETA_CASOS / CASO_A)


def test_un_campo_inventado_de_la_plataforma_no_carga(tmp_path: Path) -> None:
    """Regla de oro 10: un campo sin `origen` y sin `hueco` es un campo inventado y no entra."""
    texto = MAPEO_FICHA_INVENTADA.replace("    hueco: API-08\n", "")
    (tmp_path / "LUM999.handoff.yaml").write_text(texto, encoding="utf-8")
    with pytest.raises(ErrorSalida, match="campo inventado"):
        cargar("LUM999", "handoff", carpeta=tmp_path)


def _cadenas_de_codigo(arbol: ast.AST) -> list[str]:
    """Las cadenas del **codigo**, sin docstrings: un ejemplo de uso en la cabecera no es una decision."""
    docstrings = {
        id(nodo.body[0].value)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and nodo.body
        and isinstance(nodo.body[0], ast.Expr)
        and isinstance(nodo.body[0].value, ast.Constant)
        and isinstance(nodo.body[0].value.value, str)
    }
    return [
        nodo.value
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in docstrings
    ]


def test_ningun_fuente_de_salida_decide_por_el_nombre_de_una_ficha() -> None:
    """Ni un `if ficha == ...` ni un identificador de ficha en el codigo (los docstrings pueden citarla)."""
    for fuente in sorted(CARPETA_SALIDA.rglob("*.py")):
        arbol = ast.parse(fuente.read_text(encoding="utf-8"))
        for cadena in _cadenas_de_codigo(arbol):
            assert not re.search(r"\b[A-Z]{3}\d{3}\b", cadena), f"{fuente.name}: {cadena[:60]}"
        assert "ficha ==" not in ast.unparse(arbol), fuente.name


# ---------------------------------------------------------------------------
# 6. Regla de oro 10 e higiene del codigo de salida
# ---------------------------------------------------------------------------


def test_cada_hueco_citado_en_salida_y_en_mapping_esta_enumerado_en_huecos_md() -> None:
    texto_huecos = HUECOS.read_text(encoding="utf-8")
    enumerados = set(re.findall(r"\| (API-\d{2}) \|", texto_huecos))
    assert enumerados, "no se han encontrado filas de huecos en docs/HUECOS.md §1"
    citados = set()
    for fuente in [*CARPETA_SALIDA.rglob("*.py"), *CARPETA_MAPPING.rglob("*.yaml")]:
        citados |= set(re.findall(r"API-\d{2}", fuente.read_text(encoding="utf-8")))
    assert citados - enumerados == set(), f"huecos citados y no enumerados: {sorted(citados - enumerados)}"


def test_salida_no_evalua_nada_ni_usa_coma_flotante() -> None:
    prohibidos = (r"(?<![\w.])eval\(", r"(?<![\w.])exec\(", r"(?<![\w.])compile\(", r"(?<![\w.])float\(")
    for fuente in sorted(CARPETA_SALIDA.rglob("*.py")):
        codigo = ast.unparse(ast.parse(fuente.read_text(encoding="utf-8")))
        for patron in prohibidos:
            assert not re.search(patron, codigo), f"{fuente.name} usa {patron}"


@pytest.mark.parametrize(
    "ruta",
    [
        "__class__",
        "__dict__",
        "__init__",
        "items",
        "keys",
        "0.__class__",
        "variables.__class__.__name__",
        "unidades.-1",
        "unidades.0.variables.__len__",
    ],
)
def test_resolver_no_llega_a_ningun_atributo_de_python(ruta: str) -> None:
    """El parser de rutas solo conoce claves de mapa e indices de lista: ni atributos, ni metodos."""
    assert resolver(ACTUACION_INVENTADA, ruta) is None


def test_resolver_no_indexa_una_cadena_como_si_fuera_una_lista() -> None:
    assert resolver({"texto": "abcdef"}, "texto.0") is None


def test_resolver_no_sale_del_documento_que_se_le_da() -> None:
    """Un objeto que no sea mapa ni lista corta la ruta: no se le piden atributos."""

    class Opaco:
        secreto = "no se ve"

    assert resolver({"cosa": Opaco()}, "cosa.secreto") is None


def test_el_payload_no_contiene_ningun_numero_en_coma_flotante(tmp_path: Path, mapeo: Mapeo) -> None:
    """`aplicar` selecciona; si en algun sitio se hubiera convertido, aqui saldria un `float`."""
    payload, _ = aplicar(mapeo, canonica(CASO_A))

    def sin_floats(valor: object, camino: str = "") -> None:
        assert not isinstance(valor, float), f"{camino} es un float: {valor!r}"
        if isinstance(valor, dict):
            for clave, hijo in valor.items():
                sin_floats(hijo, f"{camino}.{clave}")
        elif isinstance(valor, list):
            for indice, hijo in enumerate(valor):
                sin_floats(hijo, f"{camino}[{indice}]")

    sin_floats(payload)


def test_aplicar_no_inventa_ni_pierde_campos(mapeo: Mapeo) -> None:
    """El payload tiene exactamente las claves del mapeo: ni una de mas (inventada) ni una de menos."""
    payload, _ = aplicar(mapeo, canonica(CASO_A))
    assert set(payload["detalle"]["actuacion"]) == {c.clave for c in mapeo.detalle_actuacion}
    assert set(payload["cabecera"]) == {c.clave for c in mapeo.cabecera}
    for unidad in payload["detalle"]["unidades"]:
        assert set(unidad["campos"]) == {c.clave for c in mapeo.detalle_unidad}


# ---------------------------------------------------------------------------
# 7. Determinismo: dos corridas iguales, la misma carpeta byte a byte
# ---------------------------------------------------------------------------


def test_dos_entregas_con_el_mismo_instante_son_la_misma_carpeta_byte_a_byte(
    tmp_path: Path, mapeo: Mapeo
) -> None:
    """Sin reloj inyectado no habria forma de comprobarlo: el manifiesto sella su `generado_en`."""
    raiz = copia(CASO_A, tmp_path)
    salidas = []
    for numero in (1, 2):
        adaptador = AdaptadorHandoff(instante=INSTANTE)
        paquete = adaptador.construir(procesado(CASO_A), mapeo, raiz=raiz)
        destino = tmp_path / f"entrega{numero}"
        adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
        salidas.append((paquete.hash_paquete, ficheros(destino)))

    assert salidas[0][0] == salidas[1][0], "el mismo paquete tiene que tener la misma huella"
    assert salidas[0][1] == salidas[1][1]


def test_el_acuse_del_simulador_es_el_mismo_en_dos_corridas(tmp_path: Path, mapeo: Mapeo) -> None:
    raiz = copia(CASO_A, tmp_path)
    paquete = AdaptadorHandoff(instante=INSTANTE).construir(procesado(CASO_A), mapeo, raiz=raiz)
    acuses = [
        Simulador(instante=INSTANTE)
        .entregar(paquete, credencial=credencial(), canonica=canonica(CASO_A))
        .a_dict()
        for _ in (1, 2)
    ]
    assert acuses[0] == acuses[1]


def test_ninguna_mitad_mira_el_reloj_a_escondidas() -> None:
    """`datetime.now()`, `uuid4` y `random` no aparecen en `salida/`: el instante se inyecta o es UTC."""
    for fuente in sorted(CARPETA_SALIDA.rglob("*.py")):
        codigo = ast.unparse(ast.parse(fuente.read_text(encoding="utf-8")))
        for prohibido in ("datetime.now(", "uuid4", "random.", "time.time("):
            assert prohibido not in codigo, f"{fuente.name} usa {prohibido}"


# ---------------------------------------------------------------------------
# 8. Modo degradado al reves: con `salida/` presente de verdad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS)
def test_el_nucleo_resuelve_los_siete_casos_con_salida_importada(caso: str) -> None:
    """`tests/test_modo_degradado.py` prueba `salida/` ausente, vacia o rota; esto la prueba **real**."""
    import salida.handoff  # noqa: F401  - importada a proposito: es lo que se esta comprobando
    import salida.mapeo  # noqa: F401
    import salida.simulador  # noqa: F401

    esperado = ground_truth(caso)
    actuacion = procesado(caso)
    assert actuacion.veredicto == esperado["veredicto_esperado"]
    assert set(actuacion.evaluacion.falladas) == set(esperado["reglas_falladas_esperadas"])
    exacto = esperado["aetotal_esperado"]["exacto"]
    total = None if actuacion.calculo is None else actuacion.calculo.total
    cae = None if actuacion.calculo is None else actuacion.calculo.total_cae
    assert total == (None if exacto is None else Decimal(exacto))
    assert cae == esperado["aetotal_esperado"]["cae"]


def test_ningun_modulo_de_engine_importa_salida_ni_sus_subpaquetes() -> None:
    """Como `tests/test_modo_degradado.py`, pero sobre **todo** el arbol.

    Aquel recorre solo `engine/*.py`: sus subpaquetes (`engine/eventos/`, `engine/modelo/`) se le escapan.
    """
    modulos = sorted(PAQUETE_ENGINE.rglob("*.py"))
    assert len(modulos) > len(list(PAQUETE_ENGINE.glob("*.py"))), "hay subpaquetes que revisar"
    for modulo in modulos:
        arbol = ast.parse(modulo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    assert not alias.name.split(".")[0] == "salida", f"{modulo}: import {alias.name}"
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                assert nodo.module.split(".")[0] != "salida", f"{modulo}: from {nodo.module}"
            elif isinstance(nodo, ast.Call) and ast.unparse(nodo).startswith("importlib.import_module"):
                assert "salida" not in ast.unparse(nodo), f"{modulo}: {ast.unparse(nodo)}"


# ---------------------------------------------------------------------------
# 9. Los otros casos: el veredicto se transporta, no se juzga
# ---------------------------------------------------------------------------

CASO_C = "EXP001-C_contradictorio"
CASO_D = "EXP001-D_fuera_ambito"
CASO_G = "EXP001-G_desordenado"


@pytest.mark.parametrize(("caso", "veredicto"), [(CASO_C, "BLOQUEADO"), (CASO_D, "NO_ELEGIBLE")])
def test_un_caso_que_no_es_prevalidado_viaja_igual_y_lo_para_la_maquina_de_estados(
    tmp_path: Path, mapeo: Mapeo, caso: str, veredicto: str
) -> None:
    """La plataforma simulada **no** juzga nuestro veredicto: no lo conoce. Quien para la entrega es el log.

    `ADR-009` §2 punto 1: el puerto describe. Un paquete `NO_ELEGIBLE` se construye, se escribe y el
    simulador lo valida (su esquema esta bien), porque la plataforma no sabe nada de nuestra prevalidacion.
    Lo que impide entregarlo de verdad es `engine.estados`: sin `PREVALIDADO` no hay `LISTA_PARA_ENVIO`.
    """
    raiz = copia(caso, tmp_path)
    adaptador = AdaptadorHandoff(instante=INSTANTE)

    paquete = adaptador.construir(procesado(caso), mapeo, raiz=raiz)  # sin log: no hay estado que mover
    assert paquete.veredicto == veredicto
    assert paquete.carencias, "un caso sin ahorro deja sus carencias a la vista del tenant"

    acuse = adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo)
    assert acuse.aceptado is True
    assert acuse.detalle["veredicto"] == veredicto
    leeme = (tmp_path / "entrega" / mapeo.fichero("leeme")).read_text(encoding="utf-8")
    assert veredicto in leeme and "Qué falta" in leeme

    del_simulador = Simulador(instante=INSTANTE).entregar(
        paquete, credencial=credencial(), canonica=canonica(caso)
    )
    assert del_simulador.aceptado is True, "la plataforma no conoce nuestro veredicto y no lo juzga"

    from engine.estados import ErrorEstado

    log = log_revisado(caso)
    with pytest.raises(ErrorEstado, match="LISTA_PARA_ENVIO exige veredicto PREVALIDADO"):
        adaptador.construir(procesado(caso), mapeo, raiz=raiz, log=log)


def test_el_caso_g_recorre_la_costura_con_las_partes_de_su_pdf_combinado(
    tmp_path: Path, mapeo: Mapeo
) -> None:
    """Las partes no son ficheros: no se copian, se listan, y no se cuentan como adjunto ausente."""
    raiz = copia(CASO_G, tmp_path)
    adaptador = AdaptadorHandoff(instante=INSTANTE)
    log = log_revisado(CASO_G)
    paquete = adaptador.construir(procesado(CASO_G), mapeo, raiz=raiz, log=log)
    partes = [a for a in paquete.adjuntos if a.es_parte]
    assert partes, "el caso G existe justamente por esto"

    entrega = tmp_path / "entrega"
    acuse = adaptador.entregar(paquete, destino_carpeta=entrega, mapeo=mapeo, log=log)
    assert acuse.aceptado is True
    assert acuse.detalle["partes_no_copiadas"] == len(partes)
    assert adaptador.verificar_entrega(paquete, entrega, mapeo=mapeo) == ()

    del_simulador = Simulador(instante=INSTANTE).entregar(
        paquete, credencial=credencial(), canonica=canonica(CASO_G), log=log
    )
    assert del_simulador.aceptado is True, del_simulador.motivos
    assert not any("ausente" in motivo for motivo in del_simulador.motivos)
    assert proyectar(log).estado_ciclo == "ENTREGADA"


def test_la_regla_de_la_clave_mas_larga_es_estable_y_esta_declarada(mapeo: Mapeo) -> None:
    """`resolver` prueba la clave mas larga primero. Es seleccion, pero **precede** a la ruta anidada.

    Hoy el modelo canonico no tiene ningun mapa con una clave `a` y otra `a.b` a la vez, asi que la regla
    nunca decide nada; este test la fija por si manana lo tuviera, para que el cambio de significado se vea
    en un test y no en una carpeta entregada.
    """
    documento = {"a": {"b": "anidado"}, "a.b": "plano"}
    assert resolver(documento, "a.b") == "plano"
    assert resolver({"a": {"b": "anidado"}}, "a.b") == "anidado"

    del_modelo = canonica(CASO_A)
    variables = dict(del_modelo.variables_actuacion)
    ambiguas = [c for c in variables if any(otra != c and otra.startswith(f"{c}.") for otra in variables)]
    assert ambiguas == [], f"el modelo canonico tiene claves que se solapan: {ambiguas}"


def test_el_leeme_no_afirma_una_causa_que_no_conoce(tmp_path: Path, mapeo: Mapeo) -> None:
    """El informe vive en el adaptador que construyo el paquete (`ADR-009` §5 ter punto 6), no en el paquete.

    Si lo entrega otro adaptador, el informe no viaja. Lo que el `00_LEEME.md` **no** puede hacer es decir
    que el paquete "se construyo desde el modelo canonico": eso es otra cosa, y en este caso seria falso.
    """
    raiz = copia(CASO_A, tmp_path)
    constructor = AdaptadorHandoff(instante=INSTANTE)
    paquete = constructor.construir(procesado(CASO_A), mapeo, raiz=raiz)  # desde la Actuacion del motor

    otro = AdaptadorHandoff(instante=INSTANTE)
    entrega = tmp_path / "entrega"
    assert otro.entregar(paquete, destino_carpeta=entrega, mapeo=mapeo).aceptado is True

    leeme = (entrega / mapeo.fichero("leeme")).read_text(encoding="utf-8")
    assert not (entrega / mapeo.fichero("informe_markdown")).exists()
    assert "no lo construyó quien lo entrega" in leeme
    assert "se construyó desde el modelo canónico" not in leeme, "eso seria falso: salio del motor"

    # Y el que si lo construyo lo entrega con su informe.
    completa = tmp_path / "entrega_completa"
    constructor.entregar(paquete, destino_carpeta=completa, mapeo=mapeo)
    assert (completa / mapeo.fichero("informe_markdown")).is_file()
    assert "Sin informe de prevalidación" not in (completa / mapeo.fichero("leeme")).read_text(
        encoding="utf-8"
    )


def test_un_mapeo_que_no_declara_el_arbol_se_rechaza_antes_de_tocar_el_disco(
    tmp_path: Path, mapeo: Mapeo
) -> None:
    """Un mapeo incompleto se ve al entrar, no a mitad de una entrega al tenant.

    `salida/mapeo.py` promete que un mapeo con una errata falla **al cargarlo**. El cargador no puede saber
    que nombres de fichero necesita cada destino, asi que quien lo comprueba es el adaptador, y lo hace
    antes de construir nada.
    """
    texto = (CARPETA_MAPPING / "IND240.handoff.yaml").read_text(encoding="utf-8")
    incompleto = texto.replace("  verificacion: 99_verificacion.txt\n", "")
    assert incompleto != texto
    (tmp_path / "IND240.handoff.yaml").write_text(incompleto, encoding="utf-8")
    cojo = cargar("IND240", "handoff", carpeta=tmp_path)

    with pytest.raises(ErrorSalida, match="no declara los nombres del arbol"):
        AdaptadorHandoff(instante=INSTANTE).construir(procesado(CASO_A), cojo, raiz=CARPETA_CASOS / CASO_A)
    assert list(ficheros(tmp_path)) == ["IND240.handoff.yaml"], "no se ha escrito nada"


def test_el_mapeo_real_declara_todo_el_arbol_que_el_handoff_necesita(mapeo: Mapeo) -> None:
    assert set(CLAVES_ARBOL) <= set(mapeo.ficheros)


def test_cada_unidad_real_se_lleva_su_propio_ahorro_y_no_el_de_la_vecina(mapeo: Mapeo) -> None:
    """Caso E, dos motores: el emparejamiento unidad <-> calculo es por identidad, no por posicion.

    `tests/test_mapeo.py::test_cada_unidad_ve_su_propio_calculo` comprueba que las dos unidades tienen
    ahorro y que sus claves son distintas, pero no **cual** le toca a cada una: con un emparejamiento
    posicional tambien pasaria. Esto lo contrasta contra `calculo.por_unidad` del modelo canonico.
    """
    caso = "EXP001-E_dos_motores"
    del_motor = procesado(caso)
    payload, _ = aplicar(mapeo, canonica(caso))
    unidades = {u["clave"]: u["campos"] for u in payload["detalle"]["unidades"]}
    assert len(unidades) == 2

    esperado = {u.num_serie_motor: u.salida for u in del_motor.calculo.por_unidad}
    assert set(unidades) == set(esperado)
    for clave, campos in unidades.items():
        # El valor viaja como cadena canonica (`engine.modelo.decimal_a_texto`); se compara como Decimal
        # para no atar el test a la forma del texto, que es cosa del modelo y no del mapeo.
        assert Decimal(campos["ahorro_unidad"]) == esperado[clave], clave
        assert campos["num_serie_motor"] == clave
