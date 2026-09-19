"""Tests del adaptador handoff (S3.4, C6 de `ADR-009` §4): `salida/handoff/`.

Lo que se protege aqui, en este orden:

1. **Caso A**: se construye y se entrega, la carpeta sale completa con el arbol de `ADR-009` §4 y el acuse
   es `aceptado: True` por la via `handoff`, sin estado de plataforma (el handoff no es una plataforma).
2. **Integridad**: un adjunto alterado entre `construir` y `entregar` se detecta al releer la carpeta
   escrita, se nombra el fichero y la entrega **no** se declara hecha.
3. **Idempotencia**: entregar dos veces el mismo paquete en la misma carpeta da el mismo resultado; una
   carpeta con contenido distinto es `ErrorSalida` y **nunca** se borra nada del usuario.
4. **Caso G**: las partes de un PDF combinado se listan bajo su combinado y no se copian como fichero.
5. **El veredicto se transporta, no se juzga**: un caso no `PREVALIDADO` construye su paquete igual; con
   `log`, quien lo rechaza es la maquina de estados, y el log del llamante se queda intacto.
6. **Lo que esta via no hace**: no consulta estados ni tareas, y lo dice; no firma nada y el `00_LEEME.md`
   deja claro que la firma es un acto humano del tenant.
7. **Higiene**: sin `eval`, sin coma flotante, `engine/` sin importar de `salida/` y sin `salida/firma/`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from engine.estados import ErrorEstado, proyectar
from engine.eventos import grabar
from engine.eventos.log import LogEventos
from engine.modelo import desde_motor
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry
from salida.constructor.manifiesto import SEPARADOR_PARTE
from salida.handoff import AVISO_FIRMA, AdaptadorHandoff
from salida.mapeo import Mapeo, cargar
from salida.puerto import ErrorSalida, Paquete, PuertoSalida

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_SALIDA = RAIZ / "salida"
FECHA = date(2026, 9, 18)

CASO_A = "EXP001-A_completo"
CASO_B = "EXP001-B_falta_registro"
CASO_D = "EXP001-D_fuera_ambito"
CASO_G = "EXP001-G_desordenado"

#: El arbol de `ADR-009` §4 que tiene que salir del caso A (con informe, sin log).
ARBOL_MINIMO = (
    "00_LEEME.md",
    "01_manifiesto.json",
    "02_payload.json",
    "03_informe_prevalidacion.md",
    "04_informe_prevalidacion.json",
    "99_verificacion.txt",
)


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


@cache
def procesado(caso: str):
    """Un caso procesado una sola vez por sesion (la cadena completa tarda entre 1 y 4 s por caso)."""
    return procesar_actuacion(CARPETA_CASOS / caso, fecha_evaluacion=FECHA, ocr=False, registro=_registro())


@pytest.fixture(scope="module")
def mapeo() -> Mapeo:
    return cargar("IND240", "handoff")


@pytest.fixture
def adaptador() -> AdaptadorHandoff:
    return AdaptadorHandoff()


def copia(caso: str, destino: Path) -> Path:
    """Copia del paquete del caso: lo que un test altera nunca es `expedientes/`."""
    carpeta = destino / caso
    shutil.copytree(CARPETA_CASOS / caso, carpeta)
    return carpeta


def log_revisado(caso: str) -> LogEventos:
    """El log del caso con la revision humana que exige el invariante 2 de la maquina de estados."""
    log = grabar(procesado(caso))
    log.anadir(
        "ObservacionRegistrada",
        {"origen": "revision_humana", "texto": "revisado antes de empaquetar"},
        actor=("humano", "revisor@tenant", "T-REV"),
    )
    return log


def ficheros(carpeta: Path) -> set[str]:
    return {f.relative_to(carpeta).as_posix() for f in carpeta.rglob("*") if f.is_file()}


# ---------------------------------------------------------------------------
# 1. Caso A: la carpeta completa
# ---------------------------------------------------------------------------


def test_el_adaptador_cumple_el_puerto_de_salida(adaptador: AdaptadorHandoff) -> None:
    assert isinstance(adaptador, PuertoSalida)
    assert adaptador.nombre == "handoff"


def test_el_caso_a_se_construye_con_su_veredicto_y_sin_carencias(
    adaptador: AdaptadorHandoff, mapeo: Mapeo
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    assert isinstance(paquete, Paquete)
    assert paquete.veredicto == "PREVALIDADO"
    assert paquete.carencias == ()
    assert paquete.destino == "handoff"
    assert (paquete.mapeo_id, paquete.mapeo_version) == (mapeo.id, mapeo.version)
    assert paquete.hash_paquete == paquete.manifiesto.hash_manifiesto  # no hay una segunda huella


def test_el_caso_a_se_entrega_con_la_carpeta_completa(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    acuse = adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo)

    assert acuse.aceptado is True
    assert acuse.motivos == ()
    assert acuse.via == "handoff"
    assert acuse.estado_plataforma is None  # el handoff no fija ningun estado oficial
    assert acuse.hash_paquete == paquete.hash_paquete

    escritos = ficheros(tmp_path / "entrega")
    assert set(ARBOL_MINIMO) <= escritos
    documentos = {ruta for ruta in escritos if ruta.startswith("documentos/")}
    assert len(documentos) == len([a for a in paquete.adjuntos if not a.es_parte])
    assert all(len(Path(ruta).parts) == 3 for ruta in documentos)  # documentos/<tipo>/<fichero>


def test_los_bytes_de_los_adjuntos_se_copian_tal_cual(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    destino = tmp_path / "entrega"
    adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    originales = {f.read_bytes() for f in (CARPETA_CASOS / CASO_A).iterdir() if f.is_file()}
    copiados = {(destino / ruta).read_bytes() for ruta in ficheros(destino) if ruta.startswith("documentos/")}
    assert copiados == originales


def test_el_payload_entregado_es_el_del_mapeo_y_lleva_su_version(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    destino = tmp_path / "entrega"
    adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    payload = json.loads((destino / "02_payload.json").read_text(encoding="utf-8"))
    assert payload["mapeo"] == {"id": mapeo.id, "version": mapeo.version, "destino": "handoff"}
    assert payload["detalle"]["actuacion"]["ahorro_total_cae"] == 305829
    assert payload["cabecera"] == {}


def test_el_manifiesto_se_escribe_tal_cual_lo_hizo_el_constructor(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    destino = tmp_path / "entrega"
    adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    escrito = json.loads((destino / "01_manifiesto.json").read_text(encoding="utf-8"))
    assert escrito == paquete.manifiesto.a_dict()


def test_la_verificacion_se_puede_comprobar_con_sha256sum(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    """El `99_verificacion.txt` sirve sin nuestro software: es lo que promete `ADR-009` §4."""
    if shutil.which("sha256sum") is None:  # pragma: no cover - depende del sistema
        pytest.skip("sha256sum no esta instalado")
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    destino = tmp_path / "entrega"
    adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    comprobacion = subprocess.run(
        "grep -E '^[0-9a-f]{64}  ' 99_verificacion.txt | sha256sum -c -",
        shell=True,
        cwd=destino,
        capture_output=True,
        text=True,
    )
    assert comprobacion.returncode == 0, comprobacion.stdout + comprobacion.stderr


# ---------------------------------------------------------------------------
# 2. Integridad: un adjunto alterado se detecta
# ---------------------------------------------------------------------------


def test_un_adjunto_alterado_se_detecta_y_nombra_el_fichero(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    """Se altera un byte del paquete origen **despues** de construir: lo copiado ya no es lo evaluado."""
    origen = copia(CASO_A, tmp_path)
    paquete = adaptador.construir(desde_motor(procesado(CASO_A)), mapeo, raiz=origen)
    victima = origen / "03_factura.pdf"
    victima.write_bytes(victima.read_bytes() + b"%% alterado")

    acuse = adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo)
    assert acuse.aceptado is False
    assert any("adjunto alterado" in motivo and "03_factura.pdf" in motivo for motivo in acuse.motivos)


def test_un_adjunto_que_desaparece_impide_la_entrega(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    origen = copia(CASO_A, tmp_path)
    paquete = adaptador.construir(desde_motor(procesado(CASO_A)), mapeo, raiz=origen)
    (origen / "03_factura.pdf").unlink()
    with pytest.raises(ErrorSalida, match="bytes han desaparecido"):
        adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo)


def test_una_entrega_no_aceptada_no_deja_evento_de_entrega(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    origen = copia(CASO_A, tmp_path)
    log = log_revisado(CASO_A)
    paquete = adaptador.construir(procesado(CASO_A), mapeo, raiz=origen, log=log)
    victima = origen / "11_convenio_cae.pdf"
    victima.write_bytes(b"otra cosa")

    acuse = adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo, log=log)
    assert acuse.aceptado is False
    assert log.por_tipo("EntregadoADelegado") == ()
    assert proyectar(log).estado_ciclo == "LISTA_PARA_ENVIO"  # empaquetada, no entregada


# ---------------------------------------------------------------------------
# 3. Idempotencia y respeto por la carpeta del usuario
# ---------------------------------------------------------------------------


def test_entregar_dos_veces_el_mismo_paquete_da_el_mismo_resultado(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    destino = tmp_path / "entrega"
    primera = adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    huellas = {ruta: (destino / ruta).read_bytes() for ruta in ficheros(destino)}
    segunda = adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)

    assert segunda.aceptado is True
    assert segunda.referencia == primera.referencia
    assert {ruta: (destino / ruta).read_bytes() for ruta in ficheros(destino)} == huellas


def test_entregar_dos_veces_con_log_no_registra_dos_entregas(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    log = log_revisado(CASO_A)
    paquete = adaptador.construir(procesado(CASO_A), mapeo, log=log)
    destino = tmp_path / "entrega"
    adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo, log=log)
    eventos = len(log)
    segunda = adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo, log=log)

    assert segunda.aceptado is True
    assert len(log) == eventos  # entregar dos veces no son dos entregas
    assert len(log.por_tipo("EntregadoADelegado")) == 1


def test_una_carpeta_con_otro_contenido_es_error_y_no_se_borra_nada(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    destino = tmp_path / "entrega"
    destino.mkdir()
    ajeno = destino / "contabilidad_del_tenant.xlsx"
    ajeno.write_bytes(b"algo del usuario que no es nuestro")

    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    with pytest.raises(ErrorSalida, match="no se borra"):
        adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    assert ajeno.read_bytes() == b"algo del usuario que no es nuestro"


def test_una_entrega_distinta_en_la_misma_carpeta_es_error(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    destino = tmp_path / "entrega"
    adaptador.entregar(adaptador.construir(procesado(CASO_A), mapeo), destino_carpeta=destino, mapeo=mapeo)
    otro = adaptador.construir(procesado(CASO_B), mapeo)
    with pytest.raises(ErrorSalida, match="no produce|entrega distinta"):
        adaptador.entregar(otro, destino_carpeta=destino, mapeo=mapeo)


# ---------------------------------------------------------------------------
# 4. Caso G: un PDF con varios documentos dentro
# ---------------------------------------------------------------------------


def test_las_partes_de_un_pdf_combinado_no_se_copian_pero_se_listan(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_G), mapeo)
    partes = [a for a in paquete.adjuntos if a.es_parte]
    assert partes, "el caso G tiene un PDF combinado con partes"

    destino = tmp_path / "entrega"
    acuse = adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    assert acuse.aceptado is True
    assert acuse.detalle["partes_no_copiadas"] == len(partes)

    escritos = ficheros(destino)
    assert not any(SEPARADOR_PARTE in ruta for ruta in escritos)  # una parte no es un fichero
    leeme = (destino / "00_LEEME.md").read_text(encoding="utf-8")
    combinado = partes[0].ruta.split(SEPARADOR_PARTE)[0]
    assert Path(combinado).name in leeme
    for parte in partes:
        assert parte.ruta.split(SEPARADOR_PARTE)[1] in leeme


# ---------------------------------------------------------------------------
# 5. El veredicto se transporta; quien juzga es la maquina de estados
# ---------------------------------------------------------------------------


def test_un_caso_no_prevalidado_construye_su_paquete_igual(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_D), mapeo)
    assert paquete.veredicto == "NO_ELEGIBLE"
    assert paquete.carencias  # sin calculo, los obligatorios del ahorro faltan
    acuse = adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=mapeo)
    assert acuse.aceptado is True
    assert acuse.detalle["veredicto"] == "NO_ELEGIBLE"


def test_con_log_la_maquina_de_estados_rechaza_lo_que_no_esta_listo(
    adaptador: AdaptadorHandoff, mapeo: Mapeo
) -> None:
    """Invariante 2 de `engine/estados.py`, no una comprobacion duplicada en el adaptador."""
    log = log_revisado(CASO_D)
    antes = len(log)
    with pytest.raises(ErrorEstado, match="LISTA_PARA_ENVIO exige veredicto PREVALIDADO"):
        adaptador.construir(procesado(CASO_D), mapeo, log=log)
    assert len(log) == antes  # el log del llamante se queda intacto


def test_sin_revision_humana_tampoco_se_empaqueta(adaptador: AdaptadorHandoff, mapeo: Mapeo) -> None:
    log = grabar(procesado(CASO_A))
    with pytest.raises(ErrorEstado, match="revision humana"):
        adaptador.construir(procesado(CASO_A), mapeo, log=log)


def test_con_log_quedan_los_eventos_p8_y_la_proyeccion_avanza(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    log = log_revisado(CASO_A)
    paquete = adaptador.construir(procesado(CASO_A), mapeo, log=log)
    assert proyectar(log).estado_ciclo == "LISTA_PARA_ENVIO"
    assert [e.tipo for e in log.eventos[-2:]] == ["PayloadConstruido", "ManifiestoGenerado"]
    assert all(e.actor.clase == "motor" for e in log.eventos[-2:])

    destino = tmp_path / "entrega"
    adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo, log=log)
    proyeccion = proyectar(log)
    assert proyeccion.estado_ciclo == "ENTREGADA"
    assert proyeccion.via_entrega == "handoff"
    assert proyeccion.firmada is False  # aqui no firma nadie
    assert (destino / "05_log_eventos.jsonl").is_file()


def test_sin_log_no_hay_transicion_y_se_entrega_igual(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    destino = tmp_path / "entrega"
    acuse = adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    assert acuse.aceptado is True
    assert not (destino / "05_log_eventos.jsonl").exists()


# ---------------------------------------------------------------------------
# 6. Lo que esta via no hace
# ---------------------------------------------------------------------------


def test_consultar_estado_se_niega_con_un_mensaje_que_lo_explica(adaptador: AdaptadorHandoff) -> None:
    with pytest.raises(ErrorSalida, match="no consulta la plataforma") as error:
        adaptador.consultar_estado("handoff:EXP001-A:abc")
    assert "tenant" in str(error.value)


def test_consultar_tareas_se_niega_en_vez_de_devolver_una_lista_vacia(adaptador: AdaptadorHandoff) -> None:
    with pytest.raises(ErrorSalida, match="no hay tareas"):
        adaptador.consultar_tareas("tenant-1")


def test_el_leeme_dice_que_la_firma_es_humana_y_que_no_custodiamos_nada(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    destino = tmp_path / "entrega"
    adaptador.entregar(adaptador.construir(procesado(CASO_A), mapeo), destino_carpeta=destino, mapeo=mapeo)
    leeme = (destino / "00_LEEME.md").read_text(encoding="utf-8")
    assert AVISO_FIRMA in leeme
    assert "certificado de representante" in leeme
    assert "no firmamos" in leeme


def test_ningun_texto_de_la_carpeta_promete_un_cae(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    """`CLAUDE.md` §2: ningun texto de producto dice 'CAE garantizado'."""
    destino = tmp_path / "entrega"
    adaptador.entregar(adaptador.construir(procesado(CASO_A), mapeo), destino_carpeta=destino, mapeo=mapeo)
    for nombre in ("00_LEEME.md", "99_verificacion.txt"):
        texto = (destino / nombre).read_text(encoding="utf-8").lower()
        assert "garantizado" not in texto
        assert "garantiza" not in texto


def test_el_leeme_enumera_las_carencias_que_le_faltan_al_tenant(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_D), mapeo)
    destino = tmp_path / "entrega"
    adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    leeme = (destino / "00_LEEME.md").read_text(encoding="utf-8")
    for carencia in paquete.carencias:
        assert carencia in leeme


def test_desde_el_modelo_canonico_no_hay_informe_y_la_carpeta_lo_dice(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    """El informe se renderiza desde la `Actuacion` del motor; no se reconstruye uno que nadie produjo."""
    paquete = adaptador.construir(desde_motor(procesado(CASO_A)), mapeo, raiz=CARPETA_CASOS / CASO_A)
    destino = tmp_path / "entrega"
    acuse = adaptador.entregar(paquete, destino_carpeta=destino, mapeo=mapeo)
    assert acuse.aceptado is True
    assert not (destino / "03_informe_prevalidacion.md").exists()
    assert "Sin informe de prevalidación" in (destino / "00_LEEME.md").read_text(encoding="utf-8")


def test_construir_sin_raiz_desde_el_modelo_canonico_es_un_error(
    adaptador: AdaptadorHandoff, mapeo: Mapeo
) -> None:
    with pytest.raises(ErrorSalida, match="necesita la `raiz`"):
        adaptador.construir(desde_motor(procesado(CASO_A)), mapeo)


def test_un_mapeo_de_otra_ficha_o_de_otro_destino_no_se_aplica(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    from dataclasses import replace

    with pytest.raises(ErrorSalida, match="no se aplica a otra ficha"):
        adaptador.construir(procesado(CASO_A), replace(mapeo, ficha="XXX999"))
    with pytest.raises(ErrorSalida, match="este adaptador es"):
        adaptador.construir(procesado(CASO_A), replace(mapeo, destino="api"))


def test_entregar_con_un_mapeo_distinto_del_que_construyo_es_un_error(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    from dataclasses import replace

    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    with pytest.raises(ErrorSalida, match="dos mapeos distintos"):
        adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega", mapeo=replace(mapeo, version="9.9"))


def test_entregar_sin_pasar_el_mapeo_lo_recarga_por_la_ficha_del_paquete(
    adaptador: AdaptadorHandoff, mapeo: Mapeo, tmp_path: Path
) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    acuse = adaptador.entregar(paquete, destino_carpeta=tmp_path / "entrega")
    assert acuse.aceptado is True


# ---------------------------------------------------------------------------
# 7. Higiene
# ---------------------------------------------------------------------------


def test_el_handoff_no_evalua_nada_ni_usa_coma_flotante() -> None:
    for fuente in sorted((CARPETA_SALIDA / "handoff").rglob("*.py")):
        texto = fuente.read_text(encoding="utf-8")
        for prohibido in ("eval", "exec", "compile", "float"):
            assert not re.search(rf"(?<![\w.]){prohibido}\(", texto), f"{fuente.name}: {prohibido}"


def test_no_existe_salida_firma_como_codigo() -> None:
    """`docs/01` §3.8: la firma no es software nuestro, y esto se comprueba sobre el arbol de ficheros."""
    assert not (CARPETA_SALIDA / "firma").exists()


def test_engine_sigue_sin_importar_de_salida() -> None:
    for fuente in sorted((RAIZ / "engine").rglob("*.py")):
        texto = fuente.read_text(encoding="utf-8")
        assert "from salida" not in texto and "import salida" not in texto, fuente.name


# ---------------------------------------------------------------------------
# 8. El destino en el constructor: lo que hace que `entregar` cumpla el puerto
# ---------------------------------------------------------------------------


def test_el_destino_puede_ir_en_el_constructor(mapeo: Mapeo, tmp_path: Path) -> None:
    """Un llamante generico del puerto entrega sin saber que la via escribe en una carpeta."""
    carpeta = tmp_path / "entrega"
    adaptador = AdaptadorHandoff(destino_carpeta=carpeta)
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    acuse = adaptador.entregar(paquete)
    assert acuse.aceptado is True
    assert acuse.detalle["carpeta"] == str(carpeta)


def test_el_destino_de_la_llamada_manda_sobre_el_del_constructor(mapeo: Mapeo, tmp_path: Path) -> None:
    adaptador = AdaptadorHandoff(destino_carpeta=tmp_path / "por_defecto")
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    acuse = adaptador.entregar(paquete, destino_carpeta=tmp_path / "otra")
    assert acuse.aceptado is True
    assert acuse.detalle["carpeta"] == str(tmp_path / "otra")
    assert not (tmp_path / "por_defecto").exists()


def test_sin_carpeta_en_ninguno_de_los_dos_sitios_es_error(adaptador: AdaptadorHandoff, mapeo: Mapeo) -> None:
    paquete = adaptador.construir(procesado(CASO_A), mapeo)
    with pytest.raises(ErrorSalida, match="no hay adonde entregar"):
        adaptador.entregar(paquete)
