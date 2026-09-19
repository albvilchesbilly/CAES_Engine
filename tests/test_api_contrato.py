"""El contrato C15 y sus limites (`ADR-011` §6, punto 4).

Lo que se comprueba:

1. **`R-UI-02` y `R-UI-03` por ausencia**: no existe comando que fije un veredicto, y el de la firma se
   llama registrar la firma, nunca firmar. Se recorre el catalogo entero, no un caso.
2. Ningun comando declara un evento fuera del catalogo cerrado, y ninguno **escribe** un evento que su
   capacidad no declare (esto ultimo se comprueba en ejecucion, con un manejador saboteado).
3. **Hay una entrada por capacidad**: las 46 se invocan, y la que no tiene implementacion dice que falta.
4. Dependencias: `api/` no importa de `front/`, `salida/`, `agentes/`, `generator/` ni `tests/`; y ningun
   modulo de `engine/` importa de `api/`, recorriendo **todo** el arbol.
5. `api/` no calcula: nada de coma flotante entrando por la API, y una lectura nunca escribe un evento.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from api.comandos import MANEJADORES as MANEJADORES_COMANDO
from api.comandos import ejecutar
from api.contrato import Peticion, Salida
from api.lecturas import MANEJADORES as MANEJADORES_LECTURA
from api.lecturas import leer
from api.permisos import Contexto, ErrorApi, ErrorPermiso, Principal, matriz
from api.repositorio import RepositorioMemoria
from api.servicios import RepositorioAusente, Servicios
from engine.capacidades import TIPO_COMANDO, TIPO_LECTURA
from engine.eventos.catalogo import TIPOS

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_API = RAIZ / "api"
CARPETA_ENGINE = RAIZ / "engine"
TENANT = "T-001"
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

#: Lo que `api/` no puede importar (`ADR-050`, regla de dependencias). `salida/` incluida: la API oficial
#: de la plataforma es otra cosa y no se mezcla con la nuestra.
PROHIBIDOS_EN_API = ("front", "salida", "agentes", "generator", "tests")


@pytest.fixture
def servicios() -> Servicios:
    repositorio = RepositorioMemoria()
    repositorio.anadir("A-1", TENANT)
    return Servicios(repositorio=repositorio, instante=INSTANTE)


def principal_de(perfil: str) -> Principal:
    ambito = matriz().ambitos[matriz().perfil(perfil).ambito]
    return Principal("u", (perfil,), TENANT if ambito.exige_tenant else None)


def contexto_de(perfil: str, actuacion: str | None = "A-1") -> Contexto:
    declarado = matriz().perfil(perfil)
    ambito = matriz().ambitos[declarado.ambito]
    return Contexto(declarado.superficie, TENANT if ambito.exige_tenant else None, actuacion)


# ---------------------------------------------------------------------------
# 1. R-UI-02 y R-UI-03: lo que no existe
# ---------------------------------------------------------------------------


def test_ningun_comando_fija_un_veredicto() -> None:
    """El veredicto lo emite el motor. Si tiene que cambiar, se corrige el dato y se recalcula."""
    for capacidad in matriz().capacidades.values():
        assert "VeredictoEmitido" not in capacidad.eventos, capacidad.id
        nombre = capacidad.nombre.lower()
        assert not any(
            verbo in nombre for verbo in ("fijar el veredicto", "forzar", "cambiar el veredicto")
        ), capacidad.id


def test_ningun_comando_se_llama_firmar() -> None:
    """`R-UI-03`: la firma se registra. Ningun nombre de capacidad ni de manejador dice "firmar"."""
    for capacidad in matriz().capacidades.values():
        nombre = capacidad.nombre.lower()
        # El verbo de la capacidad. `ADR-006` usa "antes de firmar" describiendo cuando ocurre otra cosa;
        # lo que no puede existir es una capacidad **cuya accion** sea firmar.
        assert not nombre.startswith("firmar"), f"{capacidad.id}: {capacidad.nombre}"
        if "FirmaRegistrada" in capacidad.eventos:
            assert "registrar" in nombre, f"{capacidad.id}: {capacidad.nombre}"
    for nombre in (*MANEJADORES_COMANDO, *MANEJADORES_LECTURA):
        assert not re.search(r"(^|_)firmar($|_)", nombre), nombre


def test_la_capacidad_de_la_firma_registra_quien_firmo_y_no_supone_que_es_el_usuario(
    servicios: Servicios,
) -> None:
    from engine.eventos.log import Actor

    log = servicios.repositorio.log("A-1")
    motor = Actor("motor", "engine")
    log.anadir("DocumentoRegistrado", {"sha256": "0" * 64}, actor=motor, ocurrido_en=INSTANTE)
    log.anadir("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, actor=motor, ocurrido_en=INSTANTE)
    log.anadir("ObservacionRegistrada", {"origen": "escalado"}, actor=motor, ocurrido_en=INSTANTE)
    ejecutar(
        Peticion("CAP-10", principal_de("T-REV"), contexto_de("T-REV"), {"comentario": "conforme"}),
        servicios=servicios,
    )
    log.anadir("ManifiestoGenerado", {}, actor=motor, ocurrido_en=INSTANTE)
    log.anadir("EntregadoADelegado", {}, actor=motor, ocurrido_en=INSTANTE)

    respuesta = ejecutar(
        Peticion(
            "CAP-22",
            principal_de("T-RES"),
            contexto_de("T-RES"),
            {"firmante": "Ana Notaria", "referencia": "REF-1"},
        ),
        servicios=servicios,
    )
    evento = servicios.repositorio.log("A-1").ultimo("FirmaRegistrada")
    assert respuesta.rol == "T-RES"
    assert evento.payload["firmante"] == "Ana Notaria"
    assert evento.payload["anotado_por"] == "u"


# ---------------------------------------------------------------------------
# 2. Los eventos: los del catalogo y los que la capacidad declara
# ---------------------------------------------------------------------------


def test_ningun_comando_declara_un_evento_fuera_del_catalogo_cerrado() -> None:
    for capacidad in matriz().capacidades.values():
        fuera = sorted(set(capacidad.eventos) - TIPOS)
        assert not fuera, f"{capacidad.id}: {fuera}"


def test_un_manejador_que_escribe_un_evento_no_declarado_falla(
    servicios: Servicios, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La matriz manda en los dos sentidos: lo escrito tiene que ser lo declarado."""
    from api.comandos import actuaciones

    def saboteado(peticion, recursos, capacidad, rol):
        evento = actuaciones.escribir(
            actuaciones.log_de(peticion, recursos),
            "ExpedienteAprobado",
            {"expediente_id": "EXP-1"},
            peticion=peticion,
            servicios=recursos,
            rol=rol,
        )
        return Salida(datos={}, eventos=(evento,))

    monkeypatch.setitem(MANEJADORES_COMANDO, "asignar_verificador", saboteado)
    with pytest.raises(ErrorApi, match="no estan entre los eventos que declara"):
        ejecutar(
            Peticion("CAP-20", principal_de("T-RES"), contexto_de("T-RES"), {"verificador": "V"}),
            servicios=servicios,
        )


def test_un_comando_que_el_ciclo_no_admite_no_envenena_el_log(servicios: Servicios) -> None:
    """Se ensaya contra la maquina de estados antes de sellar: si no cabe, el log se queda como estaba."""
    antes = len(servicios.repositorio.log("A-1"))
    with pytest.raises(ErrorApi, match="el log no se toca"):
        ejecutar(
            Peticion("CAP-09", principal_de("T-REV"), contexto_de("T-REV"), {"texto": "falta la factura"}),
            servicios=servicios,
        )
    assert len(servicios.repositorio.log("A-1")) == antes


def test_repetir_el_mismo_comando_no_duplica_el_hecho(servicios: Servicios) -> None:
    peticion = Peticion("CAP-20", principal_de("T-RES"), contexto_de("T-RES"), {"verificador": "VER-1"})
    primera = ejecutar(peticion, servicios=servicios)
    segunda = ejecutar(peticion, servicios=servicios)
    assert primera.eventos == segunda.eventos
    assert len(servicios.repositorio.log("A-1").por_tipo("VerificadorAsignado")) == 1


# ---------------------------------------------------------------------------
# 3. Una entrada por capacidad, tenga implementacion o no
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("identificador", sorted(matriz().capacidades))
def test_toda_capacidad_tiene_entrada_en_el_contrato(identificador: str, servicios: Servicios) -> None:
    """Se invocan las 46. La que no tiene implementacion **dice que falta**; ninguna se queda muda."""
    capacidad = matriz().capacidad(identificador)
    puerta = ejecutar if capacidad.es_comando else leer
    if not capacidad.concede:
        perfil = sorted(capacidad.pendiente)[0]
        with pytest.raises(ErrorPermiso, match="pendiente"):
            puerta(Peticion(identificador, principal_de(perfil), contexto_de(perfil)), servicios=servicios)
        return
    perfil = sorted(capacidad.concede)[0]
    peticion = Peticion(identificador, principal_de(perfil), contexto_de(perfil))
    if capacidad.implementada:
        try:
            respuesta = puerta(peticion, servicios=servicios)
        except (ErrorApi, ErrorPermiso) as fallo:
            # Sin los datos que pide, falla por el dato o por el estado, nunca por "no se que es esto".
            assert identificador in str(fallo) or "A-1" in str(fallo)
            return
        # Las lecturas que no necesitan datos de entrada responden directamente.
        assert respuesta.capacidad == identificador
        return
    with pytest.raises(ErrorApi) as fallo:
        puerta(peticion, servicios=servicios)
    mensaje = str(fallo.value)
    assert "la implementacion no" in mensaje
    assert capacidad.falta in mensaje


def test_un_comando_no_se_atiende_como_lectura(servicios: Servicios) -> None:
    with pytest.raises(ErrorApi, match="se esta invocando como"):
        leer(Peticion("CAP-20", principal_de("T-RES"), contexto_de("T-RES")), servicios=servicios)


def test_una_lectura_no_se_atiende_como_comando(servicios: Servicios) -> None:
    with pytest.raises(ErrorApi, match="se esta invocando como"):
        ejecutar(Peticion("CAP-14", principal_de("T-REV"), contexto_de("T-REV")), servicios=servicios)


def test_cada_manejador_declarado_en_la_matriz_existe() -> None:
    registrados = {**MANEJADORES_COMANDO, **MANEJADORES_LECTURA}
    declarados = {c.manejador for c in matriz().capacidades.values() if c.manejador}
    assert declarados == set(registrados), "la matriz y los manejadores registrados tienen que cuadrar"
    for capacidad in matriz().capacidades.values():
        if capacidad.manejador is None:
            continue
        esperados = MANEJADORES_COMANDO if capacidad.es_comando else MANEJADORES_LECTURA
        assert capacidad.manejador in esperados, capacidad.id


def test_sin_repositorio_configurado_se_dice_en_vez_de_devolver_vacio() -> None:
    assert isinstance(Servicios().repositorio, RepositorioAusente)
    with pytest.raises(ErrorApi, match="no hay repositorio configurado"):
        leer(Peticion("CAP-03", principal_de("T-REV"), contexto_de("T-REV")))


# ---------------------------------------------------------------------------
# 4. Dependencias hacia dentro
# ---------------------------------------------------------------------------


def importaciones_de(ruta: Path) -> set[str]:
    """Paquetes de primer nivel que el modulo importa de verdad (`ast`, no busqueda de texto)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    paquetes: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            paquetes |= {alias.name.split(".")[0] for alias in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            paquetes.add(nodo.module.split(".")[0])
    return paquetes


MODULOS_API = sorted(CARPETA_API.rglob("*.py"))
MODULOS_ENGINE = sorted(CARPETA_ENGINE.rglob("*.py"))


@pytest.mark.parametrize("modulo", MODULOS_API, ids=lambda p: p.name)
def test_api_no_importa_hacia_fuera(modulo: Path) -> None:
    prohibidas = importaciones_de(modulo) & set(PROHIBIDOS_EN_API)
    assert not prohibidas, f"api/{modulo.name} importa {sorted(prohibidas)}"


def test_hay_modulos_de_engine_que_revisar() -> None:
    assert len(MODULOS_ENGINE) > len(list(CARPETA_ENGINE.glob("*.py"))), "faltan los subpaquetes"


@pytest.mark.parametrize("modulo", MODULOS_ENGINE, ids=lambda p: p.name)
def test_ningun_modulo_de_engine_importa_api(modulo: Path) -> None:
    assert "api" not in importaciones_de(modulo), f"{modulo}: el nucleo no importa de la periferia"


def test_api_si_importa_de_engine_y_lo_hace() -> None:
    importados = set()
    for modulo in MODULOS_API:
        importados |= importaciones_de(modulo)
    assert "engine" in importados


# ---------------------------------------------------------------------------
# 5. api/ no calcula
# ---------------------------------------------------------------------------


def test_una_magnitud_en_coma_flotante_no_entra(servicios: Servicios) -> None:
    with pytest.raises(ErrorApi, match="coma flotante"):
        ejecutar(
            Peticion(
                "CAP-05",
                principal_de("T-REV"),
                contexto_de("T-REV"),
                {"variable": "potencia", "valor": 110.0, "justificacion": "placa"},
            ),
            servicios=servicios,
        )


def test_una_correccion_sin_justificacion_no_se_ejecuta(servicios: Servicios) -> None:
    """`R-UI-04`, sobre la respuesta: no se escribe nada y se dice por que."""
    antes = len(servicios.repositorio.log("A-1"))
    with pytest.raises(ErrorApi, match="R-UI-04"):
        ejecutar(
            Peticion(
                "CAP-05",
                principal_de("T-REV"),
                contexto_de("T-REV"),
                {"variable": "potencia", "valor": "110"},
            ),
            servicios=servicios,
        )
    assert len(servicios.repositorio.log("A-1")) == antes


def test_toda_correccion_de_un_dato_exige_justificacion() -> None:
    """`R-UI-04`: el que corrige un dato lo motiva. Otras capacidades pueden exigirlo tambien."""
    for capacidad in matriz().capacidades.values():
        if "DatoCorregidoPorHumano" in capacidad.eventos:
            assert capacidad.exige_justificacion, capacidad.id
        if capacidad.exige_justificacion:
            assert capacidad.es_comando, capacidad.id


def test_una_lectura_nunca_devuelve_eventos(servicios: Servicios) -> None:
    for capacidad in matriz().capacidades.values():
        if capacidad.tipo == TIPO_LECTURA:
            assert capacidad.eventos == ()


def test_los_dos_tipos_de_capacidad_son_los_del_contrato() -> None:
    assert {c.tipo for c in matriz().capacidades.values()} == {TIPO_COMANDO, TIPO_LECTURA}
