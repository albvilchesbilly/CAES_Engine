"""Las seis propiedades metamorficas minimas de `docs/05` §6.1 (F0.11).

Una propiedad metamorfica no necesita ground truth: dice **como debe cambiar (o no cambiar) el resultado**
cuando la entrada se transforma de una forma conocida. Por eso son la cuarta fuente de verdad de `docs/05`
§5: valen para cualquier actuacion, no solo para las siete que sabemos resolver.

| # | Transformacion | Propiedad |
|---|---|---|
| M-01 | Renombrar, reordenar, girar o combinar | Veredicto y AETOTAL no cambian; solo avisos |
| M-02 | Alterar `PM` en un documento fiable | `BLOQUEADO`, `R-CON-01` `FALLA`, `PM` sin valor |
| M-03 | Quitar un documento obligatorio | El veredicto **nunca mejora** |
| M-04 | `tipo_equipo_accionado` excluido | `NO_ELEGIBLE` con `R-AMB-01` `FALLA`, aunque se declare ahorro |
| M-05 | Añadir un documento irrelevante | Nada cambia salvo un aviso de documento no clasificado |
| M-06 | Duplicar un documento | Nada cambia; el duplicado se reconoce por SHA-256 |

**Como se construyen las entradas.** `expedientes/` **no se toca**: cada test copia el caso A en `tmp_path` y
transforma la copia. Las transformaciones que no pueden hacerse sobre el PDF ya generado (alterar un valor,
girar un escaneo, cambiar el tipo de equipo en todas sus fuentes a la vez) se hacen sobre el **modelo de
datos** con `generator/`, que es lo que `docs/05` §2.2 exige ("toda variacion es un cambio en el modelo de
datos del caso, nunca una edicion manual del documento generado"). Los tests si pueden importar `generator`;
`engine/` no (`tests/test_modo_degradado.py`).

**OCR.** Ninguna de las seis lo necesita para cumplirse: el escaneo girado de M-01 sustituye a la ficha
tecnica del variador (EVD-04, no obligatorio), asi que sin `tesseract` el documento queda sin clasificar, se
avisa y el veredicto y el ahorro siguen siendo los mismos. Lo que si necesita OCR es comprobar que el
escaneo **se recupera** (se clasifica y vuelve a aportar sus datos): eso va en `@pytest.mark.ocr`.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from engine.ingesta import hay_tesseract
from engine.motor import Actuacion, procesar_actuacion
from engine.reglas import Resultado
from engine.spec_registry import SpecRegistry
from generator.casos import caso_base
from generator.documentos import escaneo, ficha_tecnica_equipo, ficha_tecnica_motor
from generator.documentos.base import construir_pdf
from generator.generar import escribir_caso, generar_caso
from generator.modelo_caso import EquipoAccionado, Variaciones

RAIZ = Path(__file__).resolve().parents[1]
CASO_A = RAIZ / "expedientes" / "EXP001-A_completo"
FECHA = date(2026, 9, 18)
AETOTAL_A = Decimal("305829.6")

#: Orden de severidad del veredicto (`CLAUDE.md` §3): a la izquierda el peor. "Mejorar" es subir de indice.
ORDEN_VEREDICTOS = ("NO_ELEGIBLE", "BLOQUEADO", "SUBSANABLE", "PREVALIDADO")

FICHA_MOTOR = "08_ficha_tecnica_motor_MTR-SYN-0001.pdf"
FICHA_EQUIPO = "10_ficha_tecnica_equipo_accionado_MTR-SYN-0001.pdf"
FICHA_VARIADOR = "09_ficha_tecnica_variador_VSD-SYN-0001.pdf"

requiere_ocr = pytest.mark.skipif(not hay_tesseract(), reason="tesseract no esta instalado")


@cache
def _registro() -> SpecRegistry:
    registro = SpecRegistry()
    registro.cargar_todas()
    return registro


def evaluar(carpeta: Path, *, ocr: bool = False) -> Actuacion:
    return procesar_actuacion(carpeta, fecha_evaluacion=FECHA, ocr=ocr, registro=_registro())


@cache
def base() -> Actuacion:
    """El caso A sin transformar, procesado una sola vez: es el termino de comparacion de todas."""
    return evaluar(CASO_A)


def copia(tmp_path: Path, nombre: str = "actuacion") -> Path:
    """Copia del caso A en `tmp_path`. `expedientes/` nunca se modifica."""
    destino = tmp_path / nombre
    shutil.copytree(CASO_A, destino)
    return destino


def motor_del_caso_base():
    return caso_base().motores[0]


def total_de(actuacion: Actuacion) -> Decimal | None:
    return actuacion.calculo.total if actuacion.calculo is not None else None


def avisos_nuevos(actuacion: Actuacion) -> list[str]:
    return [a for a in actuacion.avisos if a not in base().avisos]


def mismo_resultado(actuacion: Actuacion) -> None:
    """Veredicto, AETOTAL exacto, truncado y reglas falladas identicos a los del caso A sin transformar."""
    referencia = base()
    assert actuacion.veredicto == referencia.veredicto
    assert total_de(actuacion) == total_de(referencia) == AETOTAL_A
    assert actuacion.calculo.total_cae == referencia.calculo.total_cae
    assert set(actuacion.evaluacion.falladas) == set(referencia.evaluacion.falladas) == set()


# ---------------------------------------------------------------------------
# M-01 · Renombrar, reordenar, girar o combinar
# ---------------------------------------------------------------------------


def test_m01_renombrar_todos_los_ficheros_no_cambia_nada(tmp_path):
    """La clasificacion es lexica sobre el contenido; el registro se vincula por huella, no por nombre."""
    carpeta = copia(tmp_path)
    for indice, fichero in enumerate(sorted(carpeta.iterdir())):
        fichero.rename(carpeta / f"documento_{indice:02d}{fichero.suffix}")
    actuacion = evaluar(carpeta)
    mismo_resultado(actuacion)
    assert {d.nombre for d in actuacion.documentos} == {
        f"documento_{i:02d}{s}" for i, s in enumerate([".pdf"] * 5 + [".xlsx"] + [".pdf"] * 5)
    }
    assert any("vinculado_por_hash" in a for a in avisos_nuevos(actuacion))


def test_m01_reordenar_los_prefijos_no_cambia_nada(tmp_path):
    """Los prefijos numericos invertidos: el orden de lectura no puede decidir el veredicto."""
    carpeta = copia(tmp_path)
    ficheros = sorted(carpeta.iterdir())
    for indice, fichero in enumerate(reversed(ficheros)):
        sufijo = fichero.name.split("_", 1)[1]
        fichero.rename(carpeta / f"{90 + indice:02d}_{sufijo}")
    mismo_resultado(evaluar(carpeta))


def test_m01_combinar_dos_documentos_en_un_solo_pdf_no_cambia_nada(tmp_path):
    """El combinado se separa en partes y cada parte conserva su pagina y la huella del fichero entregado."""
    carpeta = copia(tmp_path)
    motor = motor_del_caso_base()
    (carpeta / FICHA_MOTOR).unlink()
    (carpeta / FICHA_EQUIPO).unlink()
    (carpeta / "08_dos_fichas_en_un_pdf.pdf").write_bytes(
        construir_pdf([ficha_tecnica_motor.seccion(motor), ficha_tecnica_equipo.seccion(motor)])
    )
    actuacion = evaluar(carpeta)
    mismo_resultado(actuacion)
    combinados = [d for d in actuacion.documentos if d.es_combinado]
    assert len(combinados) == 1 and len(combinados[0].partes) == 2
    tipos = {d.tipo for d in actuacion.documentos if d.es_parte}
    assert tipos == {"ficha_tecnica_motor", "ficha_tecnica_equipo_accionado"}


def test_m01_girar_un_escaneo_no_cambia_el_veredicto_ni_el_ahorro(tmp_path):
    """Sin `tesseract` el escaneo no se lee: el resultado sigue siendo el mismo y se avisa."""
    carpeta = copia(tmp_path)
    (carpeta / FICHA_VARIADOR).unlink()
    (carpeta / "09_scan.pdf").write_bytes(
        escaneo.pdf_escaneo(escaneo.imagen_ficha_variador(motor_del_caso_base()))
    )
    actuacion = evaluar(carpeta, ocr=False)
    mismo_resultado(actuacion)


@pytest.mark.ocr
@requiere_ocr
def test_m01_girar_un_escaneo_con_ocr_lo_recupera(tmp_path):
    """Con OCR el escaneo girado vuelve a clasificarse como lo que es, sin mover veredicto ni ahorro."""
    carpeta = copia(tmp_path)
    (carpeta / FICHA_VARIADOR).unlink()
    (carpeta / "09_scan.pdf").write_bytes(
        escaneo.pdf_escaneo(escaneo.imagen_ficha_variador(motor_del_caso_base()))
    )
    actuacion = evaluar(carpeta, ocr=True)
    mismo_resultado(actuacion)
    tipos = {d.nombre: d.tipo for d in actuacion.documentos}
    assert tipos["09_scan.pdf"] == "ficha_tecnica_variador"


# ---------------------------------------------------------------------------
# M-02 · Alterar PM en un solo documento fiable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pm_alterado", ["75", "132"])
def test_m02_alterar_pm_en_la_ficha_tecnica_del_motor_bloquea(tmp_path, pm_alterado):
    """Regla de oro 6: el motor no elige entre dos fuentes fiables, se detiene y muestra las dos.

    La ficha tecnica del motor es la **fuente primaria** de `PM`; se reescribe desde el modelo de datos con
    otro valor y el resto de documentos siguen diciendo 110 kW. Dos valores distintos (75 y 132) para que la
    propiedad no dependa del 90 kW concreto del caso C.
    """
    carpeta = copia(tmp_path)
    motor = motor_del_caso_base()
    alterado = replace(motor, PM=Decimal(pm_alterado))
    (carpeta / FICHA_MOTOR).write_bytes(construir_pdf([ficha_tecnica_motor.seccion(alterado)]))

    actuacion = evaluar(carpeta)
    assert actuacion.veredicto == "BLOQUEADO"
    assert actuacion.evaluacion.resultado("R-CON-01").resultado is Resultado.FALLA
    dato = actuacion.consolidada.dato("PM", motor.num_serie_motor)
    assert dato is not None
    assert dato.valor_consumido is None
    assert dato.conflicto is True
    assert set(dato.valores_por_fuente.values()) == {"110", pm_alterado}
    assert total_de(actuacion) is None


def test_m02_el_conflicto_conserva_las_dos_evidencias_con_su_cita(tmp_path):
    carpeta = copia(tmp_path)
    motor = motor_del_caso_base()
    (carpeta / FICHA_MOTOR).write_bytes(
        construir_pdf([ficha_tecnica_motor.seccion(replace(motor, PM=Decimal("75")))])
    )
    dato = evaluar(carpeta).consolidada.dato("PM", motor.num_serie_motor)
    fiables = [e for e in dato.evidencias if e.metodo != "ocr"]
    assert {e.valor for e in fiables} == {"110", "75"}
    assert all(e.texto_literal.strip() and e.pagina >= 1 for e in fiables)


# ---------------------------------------------------------------------------
# M-03 · Quitar un documento obligatorio
# ---------------------------------------------------------------------------


def documentos_obligatorios() -> dict[str, str]:
    """tipo de documento obligatorio → fichero del caso A que lo aporta (sale de la spec, no de una lista)."""
    spec = _registro().obtener("IND240", fecha=FECHA)
    obligatorios = {d["tipo"] for d in spec.documentacion if d.get("obligatorio") is True}
    por_tipo = {d.tipo: d.nombre for d in base().documentos if d.tipo in obligatorios}
    faltan = obligatorios - set(por_tipo)
    assert not faltan, f"el caso A deberia aportar todos los obligatorios; faltan {sorted(faltan)}"
    return por_tipo


def test_m03_el_caso_a_aporta_todos_los_documentos_obligatorios():
    assert len(documentos_obligatorios()) >= 10


@pytest.mark.parametrize("tipo", sorted(documentos_obligatorios()))
def test_m03_quitar_un_obligatorio_nunca_mejora_el_veredicto(tmp_path, tipo):
    """Orden `NO_ELEGIBLE` > `BLOQUEADO` > `SUBSANABLE` > `PREVALIDADO`: quitar prueba nunca puede subir."""
    carpeta = copia(tmp_path)
    (carpeta / documentos_obligatorios()[tipo]).unlink()
    actuacion = evaluar(carpeta)
    assert ORDEN_VEREDICTOS.index(actuacion.veredicto) <= ORDEN_VEREDICTOS.index(base().veredicto)
    assert actuacion.evaluacion.falladas, f"quitar {tipo} deberia hacer fallar alguna regla"


def test_m03_quitar_un_obligatorio_pide_la_subsanacion_con_documentos_concretos(tmp_path):
    carpeta = copia(tmp_path)
    (carpeta / documentos_obligatorios()["declaracion_responsable"]).unlink()
    actuacion = evaluar(carpeta)
    assert actuacion.veredicto == "SUBSANABLE"
    carencias = actuacion.evaluacion.carencias
    assert carencias and any(c.get("documentos") for c in carencias)


# ---------------------------------------------------------------------------
# M-04 · Tipo de equipo accionado excluido
# ---------------------------------------------------------------------------


EQUIPO_EXCLUIDO = EquipoAccionado(
    tipo="compresor_desplazamiento_positivo",
    fabricante="Compresores Ficticios del Sur, S.A.",
    modelo="CDP-110-T",
    num_serie="CMP-SYN-0099",
    descripcion="Compresor de tornillo (desplazamiento positivo) para aire comprimido",
)


@cache
def _actuacion_excluida_en(raiz: str) -> Path:
    """Genera en disco una actuacion identica al caso A salvo el tipo de equipo, que esta excluido.

    Se cambia en el **modelo de datos** para que todas las fuentes (ficha del equipo y certificado) digan lo
    mismo: si solo se editara un documento habria conflicto (`BLOQUEADO`) y no estariamos probando M-04.
    `ficha_declara_ahorro=True` hace que la ficha cumplimentada y el convenio declaren ahorro, que es
    justamente lo que el motor debe ignorar.
    """
    caso = caso_base()
    motor = replace(caso.motores[0], tipo_equipo_accionado=EQUIPO_EXCLUIDO.tipo, equipo=EQUIPO_EXCLUIDO)
    excluido = replace(
        caso,
        id="M04",
        carpeta="M04_equipo_excluido",
        descripcion="Metamorfica M-04: compresor de desplazamiento positivo (EXC-03)",
        motores=(motor,),
        variaciones=Variaciones(ficha_declara_ahorro=True),
        veredicto_esperado="NO_ELEGIBLE",
        reglas_falladas_esperadas=("R-AMB-01",),
    )
    spec = _registro().obtener("IND240", fecha=FECHA)
    return escribir_caso(generar_caso(excluido, spec), Path(raiz))


def test_m04_un_equipo_excluido_da_no_elegible_aunque_se_declare_ahorro(tmp_path):
    carpeta = _actuacion_excluida_en(str(tmp_path))
    actuacion = evaluar(carpeta)
    assert actuacion.veredicto == "NO_ELEGIBLE"
    assert actuacion.evaluacion.resultado("R-AMB-01").resultado is Resultado.FALLA
    assert total_de(actuacion) is None

    declarado = actuacion.consolidada.variables.get("convenio.ahorro_kwh")
    assert declarado is not None and declarado.valor_consumido is not None, (
        "el convenio deberia declarar un ahorro que el motor ignora"
    )


def test_m04_con_equipo_excluido_no_se_evaluan_las_fases_posteriores(tmp_path):
    actuacion = evaluar(_actuacion_excluida_en(str(tmp_path)))
    assert set(actuacion.evaluacion.fases_saltadas) == {
        "consistencia",
        "calculo",
        "post_calculo",
        "resto",
    }
    assert actuacion.evaluacion.falladas == ["R-AMB-01"]


# ---------------------------------------------------------------------------
# M-05 · Documento irrelevante
# ---------------------------------------------------------------------------


def test_m05_anadir_un_documento_irrelevante_solo_anade_un_aviso(tmp_path):
    carpeta = copia(tmp_path)
    irrelevante = RAIZ / "expedientes" / "EXP001-G_desordenado" / "notas.pdf"
    shutil.copy(irrelevante, carpeta / "99_acta_de_reunion.pdf")
    actuacion = evaluar(carpeta)
    mismo_resultado(actuacion)
    nuevos = avisos_nuevos(actuacion)
    assert len(nuevos) == 1
    assert "no_clasificado" in nuevos[0] and "99_acta_de_reunion.pdf" in nuevos[0]
    sin_tipo = [d.nombre for d in actuacion.documentos if d.tipo is None]
    assert sin_tipo == ["99_acta_de_reunion.pdf"]


# ---------------------------------------------------------------------------
# M-06 · Documento duplicado
# ---------------------------------------------------------------------------


#: Avisos que un duplicado si puede añadir: son informativos y no mueven el veredicto. Al duplicar el xlsx
#: del registro, la copia se vincula igualmente por huella y el motor avisa de que su nombre no es el que
#: declara el certificado. Es ruido menor del informe (hallazgo de estilo de la revision de F0.11), no un
#: cambio de resultado: se deja escrito aqui en lugar de relajar la comprobacion en silencio.
AVISOS_INFORMATIVOS_ADMITIDOS = ("registro_vinculado_por_hash",)


@pytest.mark.parametrize("original", sorted(p.name for p in CASO_A.iterdir()))
def test_m06_duplicar_cualquier_documento_no_cambia_nada(tmp_path, original):
    carpeta = copia(tmp_path)
    copia_duplicada = carpeta / f"99_copia_de_{original}"
    shutil.copy(carpeta / original, copia_duplicada)
    actuacion = evaluar(carpeta)
    mismo_resultado(actuacion)
    inesperados = [a for a in avisos_nuevos(actuacion) if not a.startswith(AVISOS_INFORMATIVOS_ADMITIDOS)]
    assert inesperados == []


def test_m06_duplicar_un_pdf_no_anade_ni_un_aviso(tmp_path):
    carpeta = copia(tmp_path)
    shutil.copy(carpeta / FICHA_MOTOR, carpeta / "99_copia_de_la_ficha_del_motor.pdf")
    assert avisos_nuevos(evaluar(carpeta)) == []


def test_m06_el_duplicado_se_reconoce_por_sha256(tmp_path):
    """Mismo contenido, distinto nombre: misma huella y mismo `doc_id`, aunque sean dos ficheros."""
    carpeta = copia(tmp_path)
    shutil.copy(carpeta / FICHA_MOTOR, carpeta / "99_la_misma_ficha_con_otro_nombre.pdf")
    actuacion = evaluar(carpeta)
    ficheros = [d for d in actuacion.documentos if not d.es_parte]
    assert len(ficheros) == len(base().documentos) + 1
    assert len({d.sha256 for d in ficheros}) == len(ficheros) - 1
    assert len({d.doc_id for d in ficheros}) == len(ficheros) - 1
    del_tipo = [d for d in ficheros if d.tipo == "ficha_tecnica_motor"]
    assert len(del_tipo) == 2 and del_tipo[0].sha256 == del_tipo[1].sha256
