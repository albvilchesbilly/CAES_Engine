"""El lazo «se corrige un dato y el motor recalcula», cerrado de extremo a extremo (`ADR-014` §3 y §5).

Hasta hoy el lazo estaba entero dentro de `engine/` y **sin ningun consumidor**: `procesar_actuacion`
aceptaba `correcciones`, `de_log` las leia del log y la consolidacion les daba precedencia, pero `api/` no
importaba nada de eso. `CAP-05` sellaba el evento y devolvia. Lo que se prueba aqui es el otro extremo.

1. **C23 + C24**: una correccion sobre el caso C lo lleva de `BLOQUEADO` a `PREVALIDADO` **a traves de
   `api/`**. Ningun test llama al motor por su cuenta: quien procesa y quien reprocesa es el puerto.
2. **C24, la otra mitad**: si el reproceso falla, el comando **no** falla. La correccion queda sellada y la
   salida dice que el veredicto esta pendiente de recalculo (`CA-REV-09`). Perder el evento seria perder el
   acto humano; ocultar el fallo, peor que la latencia.
3. **C25**: corregir despues de firmar emite `CorreccionRechazadaPostFirma`, que estaba en el catalogo y no
   lo emitia nadie. Quien corrige post-firma se entera de que se ignoro.
4. **C26**: un log cuyo ciclo no se puede leer ya no aplica todas las correcciones. `de_log` levanta.

El caso C **es** el caso A con una errata de 90 kW en el certificado del instalador, y su ground truth
guarda 305829.6 como `referencia_no_publicada`: por eso corregir a 110 kW tiene que dar exactamente el
ahorro del caso A, en `Decimal` y sin pasar por `float` en ningun punto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from api.comandos import ejecutar
from api.contrato import Peticion
from api.lecturas import leer
from api.permisos import Contexto, ErrorApi, Principal
from api.repositorio import RepositorioMemoria
from api.servicios import Repositorio, RepositorioAusente, Servicios
from engine.correcciones import ErrorCorreccion, de_log, rechazos_post_firma
from engine.eventos.log import LogEventos

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_CASOS = RAIZ / "expedientes"
CASO_C = "EXP001-C_contradictorio"
AETOTAL_A = Decimal("305829.6")

TENANT = "T-001"
INSTANTE = datetime(2026, 9, 23, 10, 30, tzinfo=UTC)
SERIE = "MTR-SYN-0001"
JUSTIFICACION = (
    "La ficha tecnica del motor y la placa de caracteristicas dicen 110 kW; el certificado del instalador "
    "arrastra una errata de tecleo."
)


def fecha_de_caso(caso: str) -> date:
    datos = json.loads((CARPETA_CASOS / "_resultados_esperados" / f"{caso}.json").read_text("utf-8"))
    return date.fromisoformat(datos["fecha_evaluacion"])


@dataclass(frozen=True)
class SinProcesar:
    """Lo minimo que el puerto necesita para poder procesar una actuacion por primera vez.

    No es un doble del motor: no trae veredicto, ni consolidacion, ni evaluacion. Trae de que carpeta salen
    los documentos y con que fecha se evalua, que es lo que en produccion sabra la maquina de estados y hoy
    no sabe nadie (`engine/motor.py`: en la Fase 0 la identidad es la carpeta). Existe para que **este test
    no llame al motor**: la primera pasada tambien la hace `Repositorio.reprocesar`.
    """

    carpeta: Path
    fecha_evaluacion: date


def peticion(capacidad: str, perfil: str, actuacion: str, **datos: object) -> Peticion:
    return Peticion(
        capacidad,
        Principal("ana@tenant", (perfil,), TENANT),
        Contexto("workspace", TENANT, actuacion),
        datos,
    )


def correccion(actuacion: str, valor: str = "110", *, variable: str = "PM") -> Peticion:
    """La peticion que escribiria el revisor en la pantalla de revision: valor, unidad y por que."""
    return peticion(
        "CAP-05",
        "T-REV",
        actuacion,
        variable=variable,
        valor=valor,
        num_serie_motor=SERIE,
        justificacion=JUSTIFICACION,
    )


@pytest.fixture
def repositorio_caso_c() -> tuple[RepositorioMemoria, str]:
    """El caso C procesado **por el puerto**, sin OCR, tal como estaria antes de que nadie lo mire."""
    repositorio = RepositorioMemoria()
    identificador = CASO_C
    repositorio.anadir(
        identificador,
        TENANT,
        actuacion=SinProcesar(CARPETA_CASOS / CASO_C, fecha_de_caso(CASO_C)),
        ocr=False,
    )
    repositorio.reprocesar(identificador)
    return repositorio, identificador


def veredicto_leido(servicios: Servicios, actuacion: str) -> object:
    """El veredicto **como lo sirve `api/`**, que es lo que vera la pantalla en la siguiente lectura."""
    respuesta = leer(peticion("CAP-03", "T-REV", actuacion), servicios=servicios)
    return respuesta.datos["veredicto"]["valor"]  # type: ignore[index]


# ---------------------------------------------------------------------------
# 1 · El lazo: corregir lleva el caso C de BLOQUEADO a PREVALIDADO, por `api/`
# ---------------------------------------------------------------------------


def test_corregir_un_dato_recalcula_el_veredicto_a_traves_de_la_api(
    repositorio_caso_c: tuple[RepositorioMemoria, str],
) -> None:
    """C23 y C24 juntos: el criterio de aceptacion de `FR1.b`.

    Ni el test ni `api/` deciden nada: el revisor dice que la potencia es 110 kW y **por que**, y el nucleo
    vuelve a evaluar sus reglas con esa evidencia mas. El veredicto no se fija: se recalcula.
    """
    repositorio, actuacion = repositorio_caso_c
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)

    antes = repositorio.actuacion(actuacion)
    assert antes.veredicto == "BLOQUEADO", "el caso C parte con dos potencias en conflicto"
    assert antes.calculo is None or antes.calculo.total is None, "sin dato consolidado no hay ahorro"
    assert veredicto_leido(servicios, actuacion) == "BLOQUEADO"

    respuesta = ejecutar(correccion(actuacion), servicios=servicios)

    assert respuesta.datos["recalculada"] is True
    assert respuesta.datos["rechazos_post_firma"] == []
    assert len(respuesta.eventos) == 1, "el comando escribe la correccion y nada mas en nombre de la persona"

    despues = repositorio.actuacion(actuacion)
    assert despues is not antes, "`reprocesar` **sustituye** la actuacion guardada, no la deja al lado"
    assert despues.veredicto == "PREVALIDADO"
    assert despues.calculo is not None
    assert despues.calculo.total == AETOTAL_A, "el caso C es el caso A con una errata"
    assert isinstance(despues.calculo.total, Decimal), "toda magnitud del ahorro es Decimal"
    assert veredicto_leido(servicios, actuacion) == "PREVALIDADO", "la siguiente lectura ve el nuevo"


def test_la_correccion_viaja_al_nuevo_calculo_con_su_cita(
    repositorio_caso_c: tuple[RepositorioMemoria, str],
) -> None:
    """`R-UI-04` deja de ser burocracia: la justificacion escrita es la cita de la evidencia."""
    repositorio, actuacion = repositorio_caso_c
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)
    ejecutar(correccion(actuacion), servicios=servicios)

    dato = repositorio.actuacion(actuacion).consolidada.unidades[SERIE]["PM"]
    citas = [e.texto_literal for e in dato.evidencias if e.metodo == "correccion_humana"]
    assert citas == [JUSTIFICACION]


def test_el_reproceso_no_lo_dispara_una_lectura(
    repositorio_caso_c: tuple[RepositorioMemoria, str],
) -> None:
    """Leer no recalcula. El reproceso cuelga de `CAP-05`, que es un acto de una persona (`ADR-014` §3)."""
    repositorio, actuacion = repositorio_caso_c
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)
    antes = repositorio.actuacion(actuacion)
    veredicto_leido(servicios, actuacion)
    assert repositorio.actuacion(actuacion) is antes


# ---------------------------------------------------------------------------
# 2 · El reproceso que falla: la correccion queda, y se dice
# ---------------------------------------------------------------------------


class RepositorioQueNoReprocesa(RepositorioMemoria):
    """Un repositorio al que el motor se le cae. Es el unico metodo que cambia."""

    def reprocesar(self, actuacion_id: str) -> object:
        raise RuntimeError("el fichero de la ficha tecnica esta corrupto")


def test_si_el_reproceso_falla_la_correccion_sigue_sellada_y_se_avisa() -> None:
    """C24: el comando no falla. Perder el evento seria perder el acto humano.

    Y no se calla: `Salida.datos` dice que **no** se recalculo, para que la pantalla no presente como
    actualizado un veredicto que no lo esta (`CA-REV-09`).
    """
    repositorio = RepositorioQueNoReprocesa()
    repositorio.anadir("A-1", TENANT)
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)

    respuesta = ejecutar(correccion("A-1"), servicios=servicios)

    assert respuesta.datos["recalculada"] is False
    assert len(respuesta.eventos) == 1
    evento = repositorio.log("A-1").ultimo("DatoCorregidoPorHumano")
    assert evento.datos["valor"] == "110"
    assert evento.datos["justificacion"] == JUSTIFICACION
    assert any("pendiente de recalculo" in aviso for aviso in respuesta.avisos)
    assert any("ficha tecnica esta corrupto" in aviso for aviso in respuesta.avisos), (
        "el motivo real se sirve tal cual: un aviso que no dice que paso no sirve para decidir"
    )


def test_un_repositorio_sin_la_actuacion_procesada_dice_que_no_puede_reprocesar() -> None:
    """El caso realista del fallo: se abrio la actuacion y todavia no la ha procesado nadie."""
    repositorio = RepositorioMemoria()
    repositorio.anadir("A-1", TENANT)
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)

    respuesta = ejecutar(correccion("A-1"), servicios=servicios)

    assert respuesta.datos["recalculada"] is False
    assert any("carpeta de documentos" in aviso for aviso in respuesta.avisos)
    with pytest.raises(ErrorApi, match="carpeta de documentos"):
        repositorio.reprocesar("A-1")


def test_el_puerto_declara_reprocesar_y_el_ausente_dice_que_falta() -> None:
    """C23 sobre el `Protocol`: si no esta declarado, no es un contrato (el fleco 1 de `GAP-REV-03`)."""
    assert hasattr(Repositorio, "reprocesar")
    assert hasattr(Repositorio, "guardar_documento"), "lo que `CAP-02` pide, el puerto lo declara"
    for operacion in ("reprocesar", "guardar_documento"):
        assert callable(getattr(RepositorioMemoria, operacion))
    with pytest.raises(ErrorApi, match="no hay repositorio configurado"):
        RepositorioAusente().reprocesar("A-1")


# ---------------------------------------------------------------------------
# 3 · C25: corregir tras la firma deja de descartarse en silencio
# ---------------------------------------------------------------------------


def log_firmado(repositorio: RepositorioMemoria, actuacion_id: str) -> LogEventos:
    """Una actuacion prevalidada, revisada, entregada y firmada: desde aqui rige la inalterabilidad."""
    log = repositorio.log(actuacion_id)
    motor = ("motor", "engine@test")
    for tipo, payload, actor in (
        ("ActuacionAbierta", {}, motor),
        ("DocumentoRegistrado", {}, motor),
        ("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, motor),
        ("RevisionAprobada", {}, ("humano", "ana@tenant", "T-REV")),
        ("PayloadConstruido", {}, motor),
        ("EntregadoADelegado", {}, motor),
        ("FirmaRegistrada", {}, ("humano", "bob@tenant", "T-RES")),
    ):
        log.anadir(tipo, payload, actor=actor, ocurrido_en=INSTANTE)
    return log


def test_corregir_tras_la_firma_emite_correccion_rechazada_post_firma(
    repositorio_caso_c: tuple[RepositorioMemoria, str],
) -> None:
    """C25: el evento estaba en el catalogo y no lo emitia nadie.

    `de_log` descartaba la correccion post-firma **en silencio**, asi que quien corregia despues de firmar
    no se enteraba de que se habia ignorado. Ahora el disparo del reproceso compara lo que se aplica con lo
    que hay en el log y deja constancia de la diferencia.
    """
    repositorio, actuacion = repositorio_caso_c
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)
    log = log_firmado(repositorio, actuacion)

    respuesta = ejecutar(correccion(actuacion), servicios=servicios)

    sellada = log.ultimo("DatoCorregidoPorHumano")
    assert sellada is not None, "el evento se sella igual: el log es solo-anadir y el intento es un hecho"
    rechazos = log.por_tipo("CorreccionRechazadaPostFirma")
    assert len(rechazos) == 1, "y ahora si hay quien lo emita"
    assert rechazos[0].actor.clase == "motor", "lo sella el ciclo, no la persona"
    assert rechazos[0].actor.rol is None
    assert rechazos[0].datos["evento_id"] == sellada.evento_id
    assert "inalterabilidad" in str(rechazos[0].datos["motivo"])

    assert respuesta.datos["rechazos_post_firma"] == [sellada.evento_id]
    assert any("posterior a la firma" in aviso for aviso in respuesta.avisos)
    assert respuesta.datos["recalculada"] is True, "se reproceso; lo que no entro fue la correccion"
    assert repositorio.actuacion(actuacion).veredicto == "BLOQUEADO", (
        "la inalterabilidad se sostiene: el veredicto no se mueve con una correccion post-firma"
    )


def test_el_evento_de_rechazo_no_se_duplica_al_repetir_la_peticion(
    repositorio_caso_c: tuple[RepositorioMemoria, str],
) -> None:
    """La misma peticion dos veces no duplica el hecho, ni el humano ni el del ciclo."""
    repositorio, actuacion = repositorio_caso_c
    servicios = Servicios(repositorio=repositorio, instante=INSTANTE)
    log = log_firmado(repositorio, actuacion)

    ejecutar(correccion(actuacion), servicios=servicios)
    ejecutar(correccion(actuacion), servicios=servicios)

    assert len(log.por_tipo("DatoCorregidoPorHumano")) == 1
    assert len(log.por_tipo("CorreccionRechazadaPostFirma")) == 1


def test_ninguna_capacidad_concede_el_evento_de_rechazo_a_un_perfil() -> None:
    """Por eso lo sella un actor motor y **no** viaja en `Salida.eventos` (`ADR-014` C25).

    Si alguna capacidad lo concediera, una persona podria escribir a mano que su propia correccion fue
    rechazada —o que no lo fue—, y el control de inalterabilidad se volveria decorativo.
    """
    from engine.capacidades import matriz_capacidades, perfiles_que_pueden_emitir

    assert perfiles_que_pueden_emitir("CorreccionRechazadaPostFirma") == frozenset()
    for capacidad in matriz_capacidades().capacidades.values():
        assert "CorreccionRechazadaPostFirma" not in capacidad.eventos, capacidad.id


# ---------------------------------------------------------------------------
# 4 · C26: el control de inalterabilidad deja de fallar abierto
# ---------------------------------------------------------------------------


class EventoIlegible:
    """Un evento que la maquina de estados no sabe aplicar: no es un `Evento` del nucleo."""

    tipo = "DatoCorregidoPorHumano"
    secuencia = 1
    evento_id = "00000000-0000-0000-0000-000000000001"
    ocurrido_en = INSTANTE
    datos = {
        "variable": "PM",
        "valor": "90",
        "justificacion": "colada por un log que nadie puede proyectar",
        "num_serie_motor": SERIE,
    }

    class actor:  # noqa: N801 - es un doble minimo, no una clase de dominio
        id = "ana@tenant"
        rol = "T-REV"


class LogIlegible:
    """Un log que trae correcciones y **no se puede proyectar**. El caso que fallaba abierto."""

    actuacion_id = "A-ILEGIBLE"
    eventos = (EventoIlegible(),)

    def por_tipo(self, tipo: str) -> list[object]:
        return [e for e in self.eventos if e.tipo == tipo]


def test_un_log_que_no_se_puede_proyectar_no_aplica_ninguna_correccion() -> None:
    """C26: hasta hoy esto devolvia la correccion. Un control que se desactiva cuando algo va mal no es un
    control (misma familia que H3 y que `api.contrato.comprobar_alcance`, cerrada el 20/09/2026).

    **Este es el test de mutacion**: volver al `except (ErrorEstado, AttributeError, TypeError): return
    frozenset()` de `_proyeccion_del_ciclo` hace que `de_log` devuelva una correccion en vez de levantar, y
    este test falla. Comprobado por mutacion el 23/09/2026.
    """
    with pytest.raises(ErrorCorreccion, match="no se ha podido proyectar el ciclo"):
        de_log(LogIlegible())
    with pytest.raises(ErrorCorreccion, match="no se ha podido proyectar el ciclo"):
        rechazos_post_firma(LogIlegible())


def test_un_log_sin_correcciones_no_necesita_proyectarse() -> None:
    """La otra mitad de C26, y lo que el docstring viejo queria proteger: el log vacio o parcial.

    Sin correcciones no hay nada que filtrar, asi que no se lee el ciclo y no se levanta. La proteccion se
    mantiene **sin** que un log ilegible abra la puerta a las correcciones prohibidas.
    """

    class LogVacio:
        actuacion_id = "A-VACIA"
        eventos = ()

        def por_tipo(self, tipo: str) -> list[object]:
            return []

    assert de_log(LogVacio()) == ()
    assert rechazos_post_firma(LogVacio()) == ()
    assert de_log(LogEventos("A-NUEVA")) == ()


def test_el_reproceso_de_un_log_ilegible_deja_la_correccion_pendiente() -> None:
    """Y el llamante decide, que es lo que C26 pide: aqui, avisar en vez de aplicar a ciegas."""
    repositorio = RepositorioMemoria()
    repositorio.anadir(
        "A-1",
        TENANT,
        actuacion=SinProcesar(CARPETA_CASOS / CASO_C, fecha_de_caso(CASO_C)),
        log=LogIlegible(),  # type: ignore[arg-type]
        ocr=False,
    )

    with pytest.raises(ErrorCorreccion, match="no se ha podido proyectar el ciclo"):
        repositorio.reprocesar("A-1")
    assert isinstance(repositorio.actuacion("A-1"), SinProcesar), (
        "no se guarda nada: antes de aplicar correcciones hay que poder leer el ciclo"
    )
