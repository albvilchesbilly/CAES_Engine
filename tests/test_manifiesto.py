"""Tests del manifiesto interno e integridad total (S3.3, `ADR-008`): `salida/constructor/manifiesto.py`.

Lo que se protege aqui, en este orden:

1. **Caso A**: el manifiesto se construye, `verificar` lo da integro y lleva los cuatro hashes del
   `ADR-008`; los 11 ficheros figuran con la huella que calculo la ingesta y su tamano.
2. **Integridad**: alterar un byte de cualquier adjunto lo detecta y **nombra el fichero**; quitar uno,
   anadir uno de mas y alterar uno se distinguen entre si; manipular el propio manifiesto lo invalida.
3. **Determinismo**: dos construcciones con el mismo `generado_en` dan el mismo JSON canonico byte a byte.
4. **Cabecera vacia**: `hash_cabecera` es hoy el hash de `{}` y **cambiara con S3.2**.
5. **Caso G**: las partes de un PDF combinado figuran con su `origen`; el combinado tambien, porque es el
   fichero que entrego el cliente.
6. **Casos C y B**: el manifiesto describe lo que hay, no juzga; un conflicto o una carencia no lo impiden.
7. **Higiene del fuente**: sin `eval`, sin coma flotante, sin importar hacia fuera, y `engine/` sigue sin
   importar de `salida/`.

Los casos se procesan **una sola vez por sesion** y sin OCR (como en `tests/test_modelo.py`); lo que cada
test modifica es siempre una **copia** en `tmp_path`, nunca `expedientes/`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path

import pytest

from engine.eventos import grabar
from engine.ingesta import sha256_texto
from engine.modelo import ActuacionCanonica, a_dict, desde_motor
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry
from salida.constructor import (
    MANIFIESTO_VERSION,
    ErrorManifiesto,
    FicheroManifiesto,
    Manifiesto,
    ResultadoVerificacion,
    construir,
    verificar,
)
from salida.constructor.manifiesto import (
    CLAVES_DETALLE,
    SEPARADOR_PARTE,
    hash_canonico,
    hash_de_manifiesto,
    huellas_del_paquete,
)

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CARPETA_SALIDA = RAIZ / "salida"
CARPETA_ENGINE = RAIZ / "engine"
HUECOS = RAIZ / "docs" / "HUECOS.md"
FECHA = date(2026, 9, 18)

#: Instante fijo de generacion: sin el, el manifiesto llevaria la hora del reloj y no seria comparable.
INSTANTE = datetime(2026, 9, 19, 10, 40, tzinfo=UTC)

CASO_A = "EXP001-A_completo"
CASO_B = "EXP001-B_falta_registro"
CASO_C = "EXP001-C_contradictorio"
CASO_G = "EXP001-G_desordenado"

#: Ficheros del caso A (los 11 que entrego el cliente) y cuatro de ellos para las pruebas de alteracion.
FICHEROS_A = 11
ADJUNTOS_ALTERABLES = (
    "01_ficha_IND240_cumplimentada.pdf",
    "03_factura.pdf",
    "06_registro_funcionamiento_MTR-SYN-0001.xlsx",
    "11_convenio_cae.pdf",
)

#: `hash_cabecera` hoy: el hash del JSON canonico de `{}`. **Cambiara cuando S3.2 llene la cabecera**
#: (`cabecera_v1.yaml`, pendiente de aprobacion de Billy); entonces se actualiza esta constante y se deja
#: dicho en el `ADR-008`. Que este escrito es lo que hace visible el cambio el dia que ocurra.
HASH_CABECERA_VACIA = sha256_texto("{}")


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


@cache
def procesado(caso: str):
    """Un caso procesado una sola vez por sesion (la cadena completa tarda entre 1 y 4 s por caso)."""
    return procesar_actuacion(CARPETA_CASOS / caso, fecha_evaluacion=FECHA, ocr=False, registro=_registro())


@cache
def canonica(caso: str) -> ActuacionCanonica:
    return desde_motor(procesado(caso))


@cache
def log_de(caso: str):
    return grabar(procesado(caso), instante=INSTANTE)


def copia(caso: str, destino: Path) -> Path:
    """Copia del paquete del caso en `tmp_path`: lo que se altera en los tests nunca es `expedientes/`."""
    carpeta = destino / caso
    shutil.copytree(CARPETA_CASOS / caso, carpeta)
    return carpeta


def manifiesto_de(caso: str, raiz: Path, *, con_log: bool = False) -> Manifiesto:
    """El manifiesto del caso sobre `raiz` (la copia), con el instante fijo: comparable entre tests."""
    return construir(
        canonica(caso),
        log=log_de(caso) if con_log else None,
        generado_en=INSTANTE,
        raiz=raiz,
    )


def fuentes_salida() -> dict[str, str]:
    return {
        str(ruta.relative_to(RAIZ)): ruta.read_text(encoding="utf-8")
        for ruta in sorted(CARPETA_SALIDA.rglob("*.py"))
    }


ES_SHA256 = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# 1. Caso A: el manifiesto se construye y se verifica
# ---------------------------------------------------------------------------


def test_el_manifiesto_del_caso_a_es_verificable(tmp_path):
    """El criterio de `docs/06` S3.3: el manifiesto del caso A se genera y `verificar` lo da integro."""
    raiz = copia(CASO_A, tmp_path)
    resultado = verificar(manifiesto_de(CASO_A, raiz, con_log=True), raiz=raiz)
    assert isinstance(resultado, ResultadoVerificacion)
    assert resultado == ResultadoVerificacion(integro=True)


def test_el_manifiesto_lleva_los_cuatro_hashes(tmp_path):
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path), con_log=True)
    for nombre in ("hash_cabecera", "hash_detalle", "hash_log_eventos", "hash_manifiesto"):
        valor = getattr(manifiesto, nombre)
        assert isinstance(valor, str) and ES_SHA256.match(valor), f"{nombre} no es un sha256: {valor!r}"


def test_los_once_ficheros_figuran_con_su_huella_y_su_tamano(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    assert len(manifiesto.ficheros) == FICHEROS_A
    huellas = huellas_del_paquete(raiz)
    assert {f.ruta for f in manifiesto.ficheros} == set(huellas)
    for fichero in manifiesto.ficheros:
        assert fichero.sha256 == huellas[fichero.ruta]
        assert fichero.bytes == (raiz / fichero.ruta).stat().st_size
        assert fichero.origen is None  # en el caso A no hay ningun PDF combinado


def test_las_huellas_son_las_que_calculo_la_ingesta_y_no_se_recalculan(tmp_path):
    """`ADR-008`: el `sha256` de cada fichero sale de `DocumentoRef.sha256`, no de releer el disco."""
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path))
    de_ingesta = {(d.sha256, d.bytes, d.tipo) for d in canonica(CASO_A).documentos}
    assert {(f.sha256, f.bytes, f.tipo) for f in manifiesto.ficheros} == de_ingesta


def test_la_identidad_y_la_ficha_son_las_de_la_actuacion(tmp_path):
    entidad = canonica(CASO_A)
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path))
    assert manifiesto.actuacion_id == entidad.id == CASO_A
    assert manifiesto.codigo_identificativo_propio == entidad.codigo_identificativo_propio
    assert manifiesto.modelo_version == entidad.modelo_version
    assert manifiesto.manifiesto_version == MANIFIESTO_VERSION
    assert dict(manifiesto.ficha) == dict(entidad.ficha)


def test_el_manifiesto_es_json_puro_sin_default(tmp_path):
    documento = manifiesto_de(CASO_A, copia(CASO_A, tmp_path), con_log=True).a_dict()
    texto = json.dumps(documento, ensure_ascii=False)  # sin `default=`: si algo no es JSON, revienta aqui
    assert json.loads(texto) == documento
    assert documento["generado_en"] == "2026-09-19T10:40:00Z"  # UTC explicito, con Z


def test_las_rutas_son_relativas_ordenadas_y_sin_el_nombre_de_la_carpeta(tmp_path):
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path))
    rutas = [f.ruta for f in manifiesto.ficheros]
    assert rutas == sorted(rutas)  # orden estable por ruta (`ADR-008`)
    assert all(not ruta.startswith(("/", CASO_A)) for ruta in rutas)


def test_el_hash_del_log_es_el_del_ultimo_evento(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    log = log_de(CASO_A)
    assert manifiesto_de(CASO_A, raiz, con_log=True).hash_log_eventos == log.hash_actual
    assert log.hash_actual == log.eventos[-1].hash


def test_sin_log_el_hash_del_log_es_nulo_y_el_manifiesto_se_construye_igual(tmp_path):
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path))
    assert manifiesto.hash_log_eventos is None
    assert manifiesto.hash_manifiesto


def test_un_log_de_otra_actuacion_no_se_mezcla(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    with pytest.raises(ErrorManifiesto) as error:
        construir(canonica(CASO_A), log=log_de(CASO_C), generado_en=INSTANTE, raiz=raiz)
    assert CASO_C in str(error.value)


# ---------------------------------------------------------------------------
# 2. Integridad: alterar, quitar, anadir, manipular
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("adjunto", ADJUNTOS_ALTERABLES)
def test_alterar_un_byte_de_cualquier_adjunto_se_detecta_y_se_nombra(tmp_path, adjunto):
    """El criterio de `docs/06` S3.3: un byte cambiado en **cualquier** adjunto invalida el paquete."""
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    fichero = raiz / adjunto
    datos = bytearray(fichero.read_bytes())
    datos[-1] = (datos[-1] + 1) % 256  # un solo byte, el ultimo
    fichero.write_bytes(bytes(datos))

    resultado = verificar(manifiesto, raiz=raiz)
    assert resultado.integro is False
    assert resultado.alterados == (adjunto,)
    assert resultado.ausentes == () and resultado.sobrantes == ()
    assert resultado.motivo is None  # el manifiesto esta intacto: lo que cambio es el paquete


def test_alterar_dos_adjuntos_los_nombra_a_los_dos(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    for adjunto in ADJUNTOS_ALTERABLES[:2]:
        (raiz / adjunto).write_bytes((raiz / adjunto).read_bytes() + b" ")
    resultado = verificar(manifiesto, raiz=raiz)
    assert resultado.alterados == tuple(sorted(ADJUNTOS_ALTERABLES[:2]))


def test_quitar_un_adjunto_lo_da_por_ausente(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    (raiz / "03_factura.pdf").unlink()
    resultado = verificar(manifiesto, raiz=raiz)
    assert resultado.integro is False
    assert resultado.ausentes == ("03_factura.pdf",)
    assert resultado.alterados == () and resultado.sobrantes == ()


def test_anadir_un_fichero_de_mas_lo_da_por_sobrante(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    (raiz / "12_anexo_no_declarado.pdf").write_bytes(b"DOCUMENTO SINTETICO - SOLO PRUEBAS")
    resultado = verificar(manifiesto, raiz=raiz)
    assert resultado.integro is False
    assert resultado.sobrantes == ("12_anexo_no_declarado.pdf",)
    assert resultado.alterados == () and resultado.ausentes == ()


def test_los_tres_casos_se_distinguen_entre_si(tmp_path):
    """Alterado, ausente y sobrante a la vez: cada uno en su lista y ninguno en la del otro."""
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    (raiz / "03_factura.pdf").unlink()
    (raiz / "11_convenio_cae.pdf").write_bytes((raiz / "11_convenio_cae.pdf").read_bytes() + b"x")
    (raiz / "99_de_mas.pdf").write_bytes(b"DOCUMENTO SINTETICO - SOLO PRUEBAS")

    resultado = verificar(manifiesto, raiz=raiz)
    assert resultado.integro is False
    assert resultado.alterados == ("11_convenio_cae.pdf",)
    assert resultado.ausentes == ("03_factura.pdf",)
    assert resultado.sobrantes == ("99_de_mas.pdf",)


def test_renombrar_un_adjunto_es_un_ausente_y_un_sobrante(tmp_path):
    """La vinculacion es por huella y por ruta declarada, nunca por nombre: renombrar rompe el paquete."""
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    (raiz / "03_factura.pdf").rename(raiz / "03_factura_v2.pdf")
    resultado = verificar(manifiesto, raiz=raiz)
    assert resultado.ausentes == ("03_factura.pdf",)
    assert resultado.sobrantes == ("03_factura_v2.pdf",)


def test_manipular_el_manifiesto_lo_invalida_con_motivo(tmp_path):
    """Cambiar un `sha256` del manifiesto sin recalcular `hash_manifiesto`: el sello no cuadra."""
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    primero = manifiesto.ficheros[0]
    falsificado = replace(
        manifiesto,
        ficheros=(replace(primero, sha256="0" * 64), *manifiesto.ficheros[1:]),
    )
    resultado = verificar(falsificado, raiz=raiz)
    assert resultado.integro is False
    assert resultado.motivo is not None and "altero" in resultado.motivo
    assert resultado.alterados == (primero.ruta,)  # y ademas se ve cual dejo de cuadrar


def test_manipular_cualquier_campo_del_manifiesto_rompe_su_hash(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz, con_log=True)
    cambios = (
        {"actuacion_id": "OTRA"},
        {"hash_cabecera": "0" * 64},
        {"hash_detalle": "0" * 64},
        {"hash_log_eventos": None},
        {"generado_en": datetime(2027, 1, 1, tzinfo=UTC)},
        {"ficheros": manifiesto.ficheros[:-1]},
    )
    for cambio in cambios:
        falsificado = replace(manifiesto, **cambio)
        assert hash_de_manifiesto(falsificado) != falsificado.hash_manifiesto, cambio
        assert verificar(falsificado, raiz=raiz).motivo is not None


def test_el_hash_del_manifiesto_se_calcula_sin_ese_campo(tmp_path):
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path), con_log=True)
    assert "hash_manifiesto" not in manifiesto.contenido()
    assert manifiesto.hash_manifiesto == hash_canonico(manifiesto.contenido())
    assert manifiesto.hash_manifiesto == hash_de_manifiesto(manifiesto)


def test_un_paquete_que_ya_no_es_el_evaluado_no_produce_manifiesto(tmp_path):
    """Si un adjunto se altero **antes** de construir, no hay manifiesto: se dice, no se sella la mentira."""
    raiz = copia(CASO_A, tmp_path)
    (raiz / "03_factura.pdf").write_bytes(b"otra cosa")
    with pytest.raises(ErrorManifiesto) as error:
        manifiesto_de(CASO_A, raiz)
    assert "huella" in str(error.value)


def test_un_fichero_oculto_no_cuenta_como_sobrante(tmp_path):
    """El universo de ficheros es el de la ingesta (`ficheros_de`): lo que ella ignora, no se declara."""
    raiz = copia(CASO_A, tmp_path)
    manifiesto = manifiesto_de(CASO_A, raiz)
    (raiz / ".DS_Store").write_bytes(b"ruido del sistema de ficheros")
    assert verificar(manifiesto, raiz=raiz) == ResultadoVerificacion(integro=True)


# ---------------------------------------------------------------------------
# 3. Determinismo y `generado_en`
# ---------------------------------------------------------------------------


def test_dos_construcciones_con_el_mismo_instante_son_identicas_byte_a_byte(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    uno = manifiesto_de(CASO_A, raiz, con_log=True)
    otro = manifiesto_de(CASO_A, raiz, con_log=True)
    assert uno.a_json() == otro.a_json()
    assert uno.hash_manifiesto == otro.hash_manifiesto
    assert uno == otro


def test_el_instante_cambia_el_manifiesto(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    otro = construir(canonica(CASO_A), generado_en=datetime(2026, 9, 20, tzinfo=UTC), raiz=raiz)
    assert otro.hash_manifiesto != manifiesto_de(CASO_A, raiz).hash_manifiesto


def test_sin_instante_se_usa_el_reloj_en_utc(tmp_path):
    manifiesto = construir(canonica(CASO_A), raiz=copia(CASO_A, tmp_path))
    assert manifiesto.generado_en.tzinfo is not None
    assert manifiesto.generado_en.utcoffset() == UTC.utcoffset(None)


def test_un_instante_sin_zona_es_un_error(tmp_path):
    with pytest.raises(ErrorManifiesto) as error:
        construir(canonica(CASO_A), generado_en=datetime(2026, 9, 19, 10, 40), raiz=copia(CASO_A, tmp_path))
    assert "zona" in str(error.value)


def test_un_instante_en_otro_huso_se_normaliza_a_utc(tmp_path):
    raiz = copia(CASO_A, tmp_path)
    madrid = datetime.fromisoformat("2026-09-19T12:40:00+02:00")  # el mismo instante que INSTANTE
    assert construir(canonica(CASO_A), generado_en=madrid, raiz=raiz).a_json() == (
        manifiesto_de(CASO_A, raiz).a_json()
    )


def test_construir_sin_raiz_lo_dice_en_vez_de_inventarse_las_rutas():
    with pytest.raises(ErrorManifiesto) as error:
        construir(canonica(CASO_A), generado_en=INSTANTE)
    assert "raiz" in str(error.value)


def test_una_raiz_que_no_es_carpeta_es_un_error(tmp_path):
    fichero = tmp_path / "no_soy_una_carpeta.txt"
    fichero.write_text("x", encoding="utf-8")
    with pytest.raises(ErrorManifiesto):
        construir(canonica(CASO_A), generado_en=INSTANTE, raiz=fichero)
    with pytest.raises(ErrorManifiesto):
        verificar(manifiesto_de(CASO_A, copia(CASO_A, tmp_path)), raiz=fichero)


@pytest.mark.parametrize(
    ("argumento", "valor"),
    [("actuacion_canonica", object()), ("log", object())],
)
def test_construir_rechaza_lo_que_no_es_del_modelo(tmp_path, argumento, valor):
    raiz = copia(CASO_A, tmp_path)
    parametros = {"actuacion_canonica": canonica(CASO_A), "generado_en": INSTANTE, "raiz": raiz}
    parametros[argumento] = valor
    with pytest.raises(ErrorManifiesto):
        construir(**parametros)


def test_verificar_rechaza_lo_que_no_es_un_manifiesto(tmp_path):
    with pytest.raises(ErrorManifiesto):
        verificar({"hash_manifiesto": "0" * 64}, raiz=copia(CASO_A, tmp_path))


# ---------------------------------------------------------------------------
# 4. Cabecera vacia (S3.2 pendiente de Billy)
# ---------------------------------------------------------------------------


def test_hash_cabecera_es_hoy_el_hash_de_la_cabecera_vacia(tmp_path):
    """**Este test cambia con S3.2.**

    La cabecera de una `ActuacionCanonica` es hoy `{}` porque la spec transversal `cabecera_v1.yaml` espera
    la aprobacion de Billy (`ADR-004` §6.1, `ADR-008` §5.1). El hash se calcula igualmente: es el hash real
    de un contenido real, no un hueco. Cuando la cabecera se llene, `HASH_CABECERA_VACIA` dejara de coincidir
    y **hay que actualizar este test y el `ADR-008`**, no relajarlo: los manifiestos ya emitidos seguiran
    siendo verificables contra su propio contenido.
    """
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path))
    assert canonica(CASO_A).cabecera == {}
    assert manifiesto.hash_cabecera == HASH_CABECERA_VACIA
    assert manifiesto.hash_cabecera == hash_canonico({})


def test_hash_cabecera_y_hash_detalle_son_distintos_y_reproducibles(tmp_path):
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path))
    documento = a_dict(canonica(CASO_A))
    assert manifiesto.hash_detalle == hash_canonico({c: documento.get(c) for c in CLAVES_DETALLE})
    assert manifiesto.hash_detalle != manifiesto.hash_cabecera


def test_el_detalle_distingue_dos_actuaciones_distintas(tmp_path):
    """El hash del detalle es del contenido: dos casos distintos no pueden compartirlo."""
    hashes = {
        caso: manifiesto_de(caso, copia(caso, tmp_path)).hash_detalle for caso in (CASO_A, CASO_B, CASO_C)
    }
    assert len(set(hashes.values())) == 3
    assert len({manifiesto_de(c, tmp_path / c).hash_cabecera for c in hashes}) == 1  # todas vacias


# ---------------------------------------------------------------------------
# 5. Caso G: PDF combinado y sus partes
# ---------------------------------------------------------------------------


def test_el_caso_g_declara_el_combinado_y_sus_partes(tmp_path):
    """El combinado figura (es el fichero que entrego el cliente) y cada parte lleva su `origen`."""
    raiz = copia(CASO_G, tmp_path)
    manifiesto = manifiesto_de(CASO_G, raiz)
    del_cliente = huellas_del_paquete(raiz)
    reales = [f for f in manifiesto.ficheros if not f.es_parte]
    partes = [f for f in manifiesto.ficheros if f.es_parte]

    assert {f.ruta for f in reales} == set(del_cliente)  # ni un fichero de mas ni uno de menos
    assert len(manifiesto.ficheros) == len(del_cliente) + len(partes)
    assert partes, "el caso G trae un PDF combinado; sus partes tienen que figurar"
    for parte in partes:
        combinado = manifiesto.fichero(parte.ruta.split(SEPARADOR_PARTE)[0])
        assert combinado is not None and combinado.origen is None
        assert parte.origen == combinado.sha256  # el sha256 del combinado del que se separo
        assert not (raiz / parte.ruta).exists()  # una parte no es un fichero en disco


def test_el_caso_g_se_verifica_integro(tmp_path):
    raiz = copia(CASO_G, tmp_path)
    assert verificar(manifiesto_de(CASO_G, raiz), raiz=raiz) == ResultadoVerificacion(integro=True)


def test_alterar_el_combinado_arrastra_a_sus_partes(tmp_path):
    raiz = copia(CASO_G, tmp_path)
    manifiesto = manifiesto_de(CASO_G, raiz)
    parte = next(f for f in manifiesto.ficheros if f.es_parte)
    ruta_combinado = parte.ruta.split(SEPARADOR_PARTE)[0]
    (raiz / ruta_combinado).write_bytes((raiz / ruta_combinado).read_bytes() + b"%")

    resultado = verificar(manifiesto, raiz=raiz)
    assert resultado.integro is False
    assert ruta_combinado in resultado.alterados
    assert parte.ruta in resultado.alterados  # la parte ya no es demostrable
    assert resultado.ausentes == () and resultado.sobrantes == ()


def test_quitar_el_combinado_deja_ausentes_al_combinado_y_a_sus_partes(tmp_path):
    raiz = copia(CASO_G, tmp_path)
    manifiesto = manifiesto_de(CASO_G, raiz)
    parte = next(f for f in manifiesto.ficheros if f.es_parte)
    ruta_combinado = parte.ruta.split(SEPARADOR_PARTE)[0]
    (raiz / ruta_combinado).unlink()

    resultado = verificar(manifiesto, raiz=raiz)
    assert ruta_combinado in resultado.ausentes
    assert parte.ruta in resultado.ausentes


def test_una_parte_sin_su_combinado_no_se_declara(tmp_path):
    """Una parte huerfana (su combinado no esta en el paquete) es un error de construccion, no un fichero."""
    entidad = canonica(CASO_G)
    parte = next(d for d in entidad.documentos if d.origen is not None)
    sin_combinado = replace(
        entidad, documentos=tuple(d for d in entidad.documentos if d.sha256 != parte.origen or d is parte)
    )
    with pytest.raises(ErrorManifiesto) as error:
        construir(sin_combinado, generado_en=INSTANTE, raiz=copia(CASO_G, tmp_path))
    assert "combinado" in str(error.value)


# ---------------------------------------------------------------------------
# 6. El manifiesto describe, no juzga (casos C y B)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", [CASO_B, CASO_C])
def test_un_caso_con_conflicto_o_con_carencia_produce_manifiesto_igual(tmp_path, caso):
    raiz = copia(caso, tmp_path)
    manifiesto = manifiesto_de(caso, raiz, con_log=True)
    assert verificar(manifiesto, raiz=raiz) == ResultadoVerificacion(integro=True)
    assert len(manifiesto.ficheros) == len(huellas_del_paquete(raiz))
    assert manifiesto.hash_detalle and manifiesto.hash_cabecera


@pytest.mark.parametrize("caso", [CASO_A, CASO_B, CASO_C, CASO_G])
def test_el_manifiesto_no_lleva_veredicto_ni_juicio(tmp_path, caso):
    """El veredicto es del Rules Engine y viaja en el detalle; el manifiesto dice **que** hay, no si vale."""
    documento = manifiesto_de(caso, copia(caso, tmp_path)).a_dict()
    assert set(documento) == {
        "actuacion_id",
        "codigo_identificativo_propio",
        "modelo_version",
        "manifiesto_version",
        "generado_en",
        "ficha",
        "ficheros",
        "hash_cabecera",
        "hash_detalle",
        "hash_log_eventos",
        "hash_manifiesto",
    }
    assert "veredicto" not in json.dumps(documento)


def test_el_caso_b_declara_los_diez_ficheros_que_hay_no_los_once_que_pedia_la_ficha(tmp_path):
    """Al caso B le falta el registro de funcionamiento: el manifiesto lo refleja, no lo suple."""
    raiz = copia(CASO_B, tmp_path)
    manifiesto = manifiesto_de(CASO_B, raiz)
    assert len(manifiesto.ficheros) == FICHEROS_A - 1
    assert not any(f.tipo == "registro_funcionamiento" for f in manifiesto.ficheros)


# ---------------------------------------------------------------------------
# 7. Higiene del fuente y dependencias
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prohibido", ["eval(", "exec(", "compile(", "float(", "__import__("])
def test_la_salida_no_ejecuta_texto_ni_usa_coma_flotante(prohibido):
    for nombre, fuente in fuentes_salida().items():
        assert prohibido not in fuente, f"{nombre} usa {prohibido}"


@pytest.mark.parametrize("paquete", ["agentes", "generator", "tests"])
def test_la_salida_no_importa_hacia_donde_no_debe(paquete):
    for nombre, fuente in fuentes_salida().items():
        assert f"import {paquete}" not in fuente, f"{nombre} importa {paquete}"
        assert f"from {paquete}" not in fuente


def test_la_salida_puede_importar_de_engine_y_lo_hace():
    fuente = (CARPETA_SALIDA / "constructor" / "manifiesto.py").read_text(encoding="utf-8")
    assert "from engine.eventos import" in fuente  # una sola canonicalizacion: la del log
    assert "json_canonico" in fuente


def test_el_engine_sigue_sin_importar_de_la_salida():
    """Dependencias hacia dentro (`CLAUDE.md` §2): `engine/` no sabe que `salida/` existe."""
    for ruta in sorted(CARPETA_ENGINE.rglob("*.py")):
        fuente = ruta.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+salida\b", fuente, re.MULTILINE), ruta


def test_importar_la_salida_no_arrastra_el_motor():
    codigo = "import sys, salida.constructor; print('engine.motor' in sys.modules)"
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, check=True
    )
    assert resultado.stdout.strip() == "False", resultado.stdout


def test_ninguna_ficha_se_nombra_en_la_salida():
    """Regla de oro 4: lo especifico de la ficha vive en su YAML y en `mapping/`, nunca en el codigo."""
    for nombre, fuente in fuentes_salida().items():
        codigo = fuente.split('"""', 2)[-1]
        assert "IND240" not in codigo, f"{nombre} nombra una ficha"


def test_todo_hueco_citado_en_la_salida_existe_en_docs_huecos():
    """Regla de oro 10: un `TODO(API-xx)` en el codigo tiene que tener su fila en `docs/HUECOS.md`."""
    texto = HUECOS.read_text(encoding="utf-8")
    citados = set()
    for fuente in fuentes_salida().values():
        citados |= set(re.findall(r"TODO\(API-(\d+)\)", fuente))
    assert "02" in citados, "el manifiesto oficial es API-02 y tiene que citarse"
    for hueco in sorted(citados):
        assert f"| API-{hueco} |" in texto, f"API-{hueco} no esta enumerado en docs/HUECOS.md"


def test_la_salida_no_inventa_campos_de_la_api_oficial():
    """Nada en `salida/` habla de endpoints ni de esquemas de la plataforma: no hay diccionario (API-01)."""
    for nombre, fuente in fuentes_salida().items():
        assert "http://" not in fuente and "https://" not in fuente, nombre
        assert "requests" not in fuente and "urllib" not in fuente, nombre


def test_las_entidades_del_manifiesto_son_inmutables(tmp_path):
    manifiesto = manifiesto_de(CASO_A, copia(CASO_A, tmp_path))
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError es un `Exception` corriente
        manifiesto.hash_manifiesto = "0" * 64
    with pytest.raises(Exception):  # noqa: B017
        manifiesto.ficheros[0].sha256 = "0" * 64
    assert isinstance(manifiesto.ficheros[0], FicheroManifiesto)
