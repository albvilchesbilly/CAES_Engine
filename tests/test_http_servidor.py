"""`FR-HTTP` de extremo a extremo, **por HTTP de verdad** (`ADR-015` §5, contratos C27 y C30).

No hay transporte simulado ni cliente ASGI en proceso: se levanta uvicorn en un puerto del bucle local y
se le pregunta con `httpx`, como lo haria un navegador. Lo que se comprueba son las palabras que devuelve
el servidor de verdad, no las que creemos que devolveria.

El test que mas importa esta en `TestTenantCruzado`: un principal del tenant A **no puede** leer una
actuacion del tenant B, ni declarando el tenant de B en el contexto ni declarando el suyo. Son dos
barreras distintas y deliberadamente redundantes —C30 en el servidor y `comprobar_alcance` en `api/`— y se
prueban las dos por separado, porque una barrera que solo se ejerce cuando la otra falla no esta probada.

`starlette`, `uvicorn` y `httpx` son un extra (`pip install -e ".[http]"`): sin ellos este fichero se
salta entero y el resto del banco de pruebas sigue corriendo. Esa es la mitad de la regla de dependencias
que le toca a `FR-HTTP`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from collections.abc import Iterator
from datetime import date
from functools import cache
from pathlib import Path

import pytest

pytest.importorskip("starlette", reason="`FR-HTTP` es un extra: pip install -e '.[http]'")
pytest.importorskip("uvicorn", reason="`FR-HTTP` es un extra: pip install -e '.[http]'")
httpx = pytest.importorskip("httpx", reason="`FR-HTTP` es un extra: pip install -e '.[http]'")

import uvicorn  # noqa: E402  (despues del importorskip, a proposito)

from api.http import (  # noqa: E402
    CABECERA_PRINCIPAL,
    CONFIRMACION_DESARROLLO,
    AutenticadorDeDesarrollo,
    crear_app,
)
from api.repositorio import RepositorioMemoria  # noqa: E402
from api.servicios import Servicios  # noqa: E402
from engine.motor import procesar_actuacion  # noqa: E402
from engine.spec_registry import SpecRegistry  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CASO = "EXP001-A_completo"
#: El caso del conflicto de `PM`: `BLOQUEADO`, con motivo, y por eso el unico que puebla la cola.
CASO_CONFLICTO = "EXP001-C_contradictorio"
FECHA = date(2026, 9, 18)

TENANT_PROPIO = "T-001"
TENANT_AJENO = "T-002"
PROPIA = "A-PROPIA"
AJENA = "A-AJENA"
CONFLICTO = "C-PROPIA"

REVISOR = {"usuario_id": "u-rev", "perfiles": ["T-REV"], "tenant_id": TENANT_PROPIO}
OPERADOR = {"usuario_id": "u-ope", "perfiles": ["T-OPE"], "tenant_id": TENANT_PROPIO}
COLA = "cola_revision"
REVISION = "vista_revision"
BANDEJA = "bandeja_actuaciones"


@cache
def _procesada(caso: str) -> object:
    """Un caso sintetico procesado una vez por sesion, sin OCR (la cadena entera tarda entre 1 y 4 s)."""
    registro = SpecRegistry()
    registro.cargar_todas()
    return procesar_actuacion(
        RAIZ / "expedientes" / caso, fecha_evaluacion=FECHA, ocr=False, registro=registro
    )


def _repositorio() -> RepositorioMemoria:
    """Dos tenants y la misma actuacion en los dos: acertar un identificador no da acceso a nada."""
    repositorio = RepositorioMemoria()
    repositorio.anadir(PROPIA, TENANT_PROPIO, actuacion=_procesada(CASO), ocr=False)
    repositorio.anadir(AJENA, TENANT_AJENO, actuacion=_procesada(CASO), ocr=False)
    repositorio.anadir(CONFLICTO, TENANT_PROPIO, actuacion=_procesada(CASO_CONFLICTO), ocr=False)
    return repositorio


def _servir(app) -> Iterator[str]:
    """Levanta uvicorn en un puerto libre del bucle local y devuelve su base. Sockets de verdad."""
    configuracion = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    servidor = uvicorn.Server(configuracion)
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    limite = time.monotonic() + 15
    while not servidor.started:
        if time.monotonic() > limite:  # pragma: no cover - solo si el arranque se cuelga
            servidor.should_exit = True
            raise AssertionError("uvicorn no ha arrancado en 15 s")
        time.sleep(0.01)
    puerto = servidor.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.should_exit = True
        hilo.join(timeout=10)


@pytest.fixture(scope="module")
def base() -> Iterator[str]:
    """El servidor con el autenticador de desarrollo y dos actuaciones de dos tenants distintos."""
    app = crear_app(
        autenticador=AutenticadorDeDesarrollo(confirmacion=CONFIRMACION_DESARROLLO, anfitrion="127.0.0.1"),
        servicios=Servicios(repositorio=_repositorio()),
    )
    yield from _servir(app)


@pytest.fixture
def base_mutable() -> Iterator[str]:
    """Un servidor propio para el test que escribe: lo que corrige no lo ve el resto del fichero.

    El caso C corregido deja de tener motivos y sale de la cola, asi que compartir el repositorio haria
    que un test dependiera del orden en que corre otro. Los casos estan cacheados; montar otro servidor
    cuesta milisegundos.
    """
    app = crear_app(
        autenticador=AutenticadorDeDesarrollo(confirmacion=CONFIRMACION_DESARROLLO, anfitrion="127.0.0.1"),
        servicios=Servicios(repositorio=_repositorio()),
    )
    yield from _servir(app)


@pytest.fixture(scope="module")
def base_sin_autenticador() -> Iterator[str]:
    """El servidor tal y como sale de fabrica: sin autenticador configurado (C28)."""
    yield from _servir(crear_app(servicios=Servicios(repositorio=_repositorio())))


def pedir(
    base: str,
    ruta: str,
    *,
    quien: dict | None = None,
    superficie: str = REVISION,
    tenant_id: str | None = TENANT_PROPIO,
    actuacion_id: str | None = None,
    datos: dict | None = None,
) -> httpx.Response:
    """Una peticion tal y como la manda `front/compartido/api/transporte.ts`."""
    contexto: dict[str, object] = {"superficie": superficie, "tenant_id": tenant_id}
    if actuacion_id is not None:
        contexto["actuacion_id"] = actuacion_id
    cabeceras = {"content-type": "application/json", "accept": "application/json"}
    if quien is not None:
        cabeceras[CABECERA_PRINCIPAL] = json.dumps(quien)
    return httpx.post(
        f"{base}{ruta}",
        content=json.dumps({"contexto": contexto, "datos": datos or {}}),
        headers=cabeceras,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# El sobre: una lectura, un comando y un documento, por la red
# ---------------------------------------------------------------------------


class TestElSobre:
    """Lo que devuelve el servidor es lo que describe `front/compartido/api/transporte.ts`."""

    def test_una_lectura_trae_el_sobre_entero(self, base: str) -> None:
        respuesta = pedir(base, "/lecturas/CAP-17", quien=REVISOR, superficie=COLA)

        assert respuesta.status_code == 200
        sobre = respuesta.json()
        assert set(sobre) == {"capacidad", "rol", "rol_nombre", "eventos", "datos", "avisos"}
        assert sobre["capacidad"] == "CAP-17"
        assert sobre["rol"] == "T-REV"
        # El nombre sale de la matriz, no se compone en la pantalla (`ADR-012` §3, regla 1).
        assert sobre["rol_nombre"] == "Revisor tecnico"
        # Una lectura nunca escribe eventos.
        assert sobre["eventos"] == []
        assert isinstance(sobre["datos"], dict)
        # La cola la decide el servidor: entra el caso del conflicto, y no el caso A, que no tiene
        # ningun motivo por el que estar ahi (hueco conocido de `ADR-014`, no de esta capa).
        assert [fila["identificacion"]["actuacion_id"] for fila in sobre["datos"]["cola"]] == [CONFLICTO]

    def test_la_respuesta_no_se_cachea_ni_se_adivina_su_tipo(self, base: str) -> None:
        respuesta = pedir(base, "/lecturas/CAP-17", quien=REVISOR, superficie=COLA)

        assert respuesta.headers["content-type"].startswith("application/json")
        assert respuesta.headers["cache-control"] == "no-store"
        assert respuesta.headers["x-content-type-options"] == "nosniff"

    def test_un_comando_corrige_un_dato_y_el_motor_recalcula(self, base_mutable: str) -> None:
        """El lazo del producto entero, por la red: el caso C pasa de `BLOQUEADO` a `PREVALIDADO`.

        Es el mismo camino que `FR1` verifico con un transporte de pruebas (`ADR-014` §3), ahora con
        sockets de por medio. El veredicto lo decide el motor; aqui solo se mira lo que sirve el servidor.
        """
        base = base_mutable
        antes = pedir(base, "/lecturas/CAP-03", quien=REVISOR, actuacion_id=CONFLICTO).json()
        assert antes["datos"]["veredicto"]["valor"] == "BLOQUEADO"

        respuesta = pedir(
            base,
            "/comandos/CAP-05",
            quien=REVISOR,
            actuacion_id=CONFLICTO,
            datos={
                "variable": "PM",
                "num_serie_motor": "MTR-SYN-0001",
                # Como cadena: un `float` en `datos` lo rechaza `api.contrato` (`CLAUDE.md` §2).
                "valor": "110",
                "justificacion": (
                    "La ficha tecnica del motor, la ficha cumplimentada y la placa dicen 110 kW; el "
                    "certificado del instalador arrastra una errata al transcribirla."
                ),
            },
        )

        assert respuesta.status_code == 200, respuesta.text
        sobre = respuesta.json()
        assert sobre["capacidad"] == "CAP-05"
        assert sobre["rol"] == "T-REV"
        # Un comando si escribe eventos, y devuelve sus identificadores.
        assert len(sobre["eventos"]) == 1
        assert sobre["datos"]["recalculada"] is True

        despues = pedir(base, "/lecturas/CAP-03", quien=REVISOR, actuacion_id=CONFLICTO).json()
        assert despues["datos"]["veredicto"]["valor"] == "PREVALIDADO"

    def test_un_documento_llega_entero_y_con_su_huella(self, base: str) -> None:
        completa = pedir(base, "/lecturas/CAP-03", quien=REVISOR, actuacion_id=PROPIA).json()
        doc_id = str(completa["datos"]["documentos"][0]["doc_id"])

        respuesta = pedir(base, "/documentos", quien=REVISOR, actuacion_id=PROPIA, datos={"doc_id": doc_id})

        assert respuesta.status_code == 200, respuesta.text
        sobre = respuesta.json()
        # La capacidad no viaja en el sobre de `/documentos`: la deriva el servidor de la matriz.
        assert sobre["capacidad"] == "CAP-03"
        documento = sobre["datos"]["documento"]
        contenido = base64.b64decode(documento["contenido_base64"])
        # Lo que entro en ingesta es lo que sale: ni un byte de diferencia.
        assert len(contenido) == documento["bytes"]
        assert hashlib.sha256(contenido).hexdigest() == doc_id

    def test_una_huella_que_la_actuacion_no_tiene_no_se_sirve(self, base: str) -> None:
        respuesta = pedir(base, "/documentos", quien=REVISOR, actuacion_id=PROPIA, datos={"doc_id": "f" * 64})

        assert respuesta.status_code == 400
        sobre = respuesta.json()
        assert sobre["error"] == "api"
        assert "huella" in sobre["motivo"]

    def test_un_documento_no_se_pide_por_ruta(self, base: str) -> None:
        """La via que `ADR-012` §1 cierra: por la red tampoco hay por donde colar un camino."""
        respuesta = pedir(
            base,
            "/documentos",
            quien=REVISOR,
            actuacion_id=PROPIA,
            datos={"ruta": "/etc/passwd", "doc_id": "f" * 64},
        )

        assert respuesta.status_code == 400
        assert "nunca por ruta" in respuesta.json()["motivo"]


# ---------------------------------------------------------------------------
# Denegaciones
# ---------------------------------------------------------------------------


class TestDenegaciones:
    def test_una_capacidad_que_el_perfil_no_tiene_es_403_con_su_motivo(self, base: str) -> None:
        respuesta = pedir(
            base,
            "/comandos/CAP-05",
            quien=OPERADOR,
            actuacion_id=PROPIA,
            datos={"variable": "PM", "valor": "110", "justificacion": "prueba"},
        )

        assert respuesta.status_code == 403
        sobre = respuesta.json()
        assert sobre["error"] == "permiso"
        # Regla 4 de `ADR-011` §3: la denegacion dice que capacidad y por que.
        assert "CAP-05" in sobre["motivo"]
        assert "no concedida" in sobre["motivo"]
        assert "datos" not in sobre

    def test_sin_cabecera_de_principal_no_se_atiende_nada(self, base: str) -> None:
        respuesta = pedir(base, "/lecturas/CAP-17", superficie=COLA)

        assert respuesta.status_code == 403
        sobre = respuesta.json()
        assert sobre["error"] == "permiso"
        assert sobre["codigo"] == "autenticacion"
        assert CABECERA_PRINCIPAL in sobre["motivo"]

    def test_el_servidor_sin_autenticador_deniega_todo(self, base_sin_autenticador: str) -> None:
        """C28: el valor por defecto es `AutenticadorAusente`, y no autentica a nadie."""
        respuesta = pedir(base_sin_autenticador, "/lecturas/CAP-03", quien=REVISOR, actuacion_id=PROPIA)

        assert respuesta.status_code == 403
        sobre = respuesta.json()
        assert sobre["error"] == "permiso"
        assert "no hay autenticador configurado" in sobre["motivo"]
        assert "ADR-015" in sobre["motivo"]

    def test_un_perfil_que_la_matriz_no_conoce_no_pasa(self, base: str) -> None:
        respuesta = pedir(
            base,
            "/lecturas/CAP-03",
            quien={"usuario_id": "u-x", "perfiles": ["ROOT"], "tenant_id": TENANT_PROPIO},
            actuacion_id=PROPIA,
        )

        assert respuesta.status_code == 400
        assert "ROOT" in respuesta.json()["motivo"]


# ---------------------------------------------------------------------------
# El test que mas importa: el aislamiento por tenant, por sus dos vias
# ---------------------------------------------------------------------------


class TestTenantCruzado:
    """Un principal del tenant A no lee una actuacion del tenant B. Por ninguna de las dos vias."""

    def test_declarando_el_tenant_ajeno_lo_para_el_servidor(self, base: str) -> None:
        respuesta = pedir(base, "/lecturas/CAP-03", quien=REVISOR, tenant_id=TENANT_AJENO, actuacion_id=AJENA)

        assert respuesta.status_code == 403
        sobre = respuesta.json()
        assert sobre["error"] == "permiso"
        # C30: lo para el servidor, antes de llegar a `api/`, y lo dice.
        assert "cruce de tenant" in sobre["motivo"]
        assert "ADR-015" in sobre["motivo"]
        assert "datos" not in sobre

    def test_declarando_el_propio_lo_para_el_alcance_de_api(self, base: str) -> None:
        respuesta = pedir(
            base, "/lecturas/CAP-03", quien=REVISOR, tenant_id=TENANT_PROPIO, actuacion_id=AJENA
        )

        assert respuesta.status_code == 403
        sobre = respuesta.json()
        assert sobre["error"] == "permiso"
        # La segunda barrera: `api.contrato.comprobar_alcance`, que nombra la actuacion y su tenant.
        assert "cruce de tenant" in sobre["motivo"]
        assert AJENA in sobre["motivo"]
        assert TENANT_AJENO in sobre["motivo"]
        assert "ADR-015" not in sobre["motivo"]
        assert "datos" not in sobre

    def test_tampoco_un_documento_de_la_actuacion_ajena(self, base: str) -> None:
        completa = pedir(base, "/lecturas/CAP-03", quien=REVISOR, actuacion_id=PROPIA).json()
        # La misma huella existe en las dos actuaciones (es la misma actuacion procesada, en dos
        # tenants): acertar el `doc_id` no sirve de nada si la actuacion es de otro.
        doc_id = str(completa["datos"]["documentos"][0]["doc_id"])

        respuesta = pedir(base, "/documentos", quien=REVISOR, actuacion_id=AJENA, datos={"doc_id": doc_id})

        assert respuesta.status_code == 403
        assert "cruce de tenant" in respuesta.json()["motivo"]

    def test_un_principal_sin_tenant_no_entra_por_una_pantalla_de_tenant(self, base: str) -> None:
        respuesta = pedir(
            base,
            "/lecturas/CAP-03",
            quien={"usuario_id": "u-glob", "perfiles": ["T-REV"], "tenant_id": None},
            actuacion_id=PROPIA,
        )

        assert respuesta.status_code == 403
        assert "cruce de tenant" in respuesta.json()["motivo"]


# ---------------------------------------------------------------------------
# El envoltorio: lo que no es el contrato
# ---------------------------------------------------------------------------


class TestElEnvoltorio:
    def test_el_aviso_de_la_autenticacion_de_desarrollo_va_en_cada_respuesta(self, base: str) -> None:
        """C29: que se vea en la pantalla que esta autenticacion no es de verdad."""
        lectura = pedir(base, "/lecturas/CAP-17", quien=REVISOR, superficie=COLA).json()
        # Tambien en una negativa se dice: el sobre del 403 no lleva `avisos`, asi que la unica forma
        # de que se vea es que la peticion que si se atiende lo traiga siempre.
        documento = pedir(base, "/lecturas/CAP-03", quien=REVISOR, actuacion_id=PROPIA).json()

        for sobre in (lectura, documento):
            assert any("autenticacion de desarrollo" in aviso for aviso in sobre["avisos"]), sobre

    def test_un_cuerpo_que_no_es_json_se_dice(self, base: str) -> None:
        respuesta = httpx.post(
            f"{base}/lecturas/CAP-17",
            content="{esto no es json",
            headers={"content-type": "application/json", CABECERA_PRINCIPAL: json.dumps(REVISOR)},
            timeout=30,
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "sobre"

    def test_un_cuerpo_demasiado_grande_no_se_acumula(self, base: str) -> None:
        enorme = json.dumps(
            {"contexto": {"superficie": COLA, "tenant_id": TENANT_PROPIO}, "datos": {"x": "a" * 9_000_000}}
        )

        respuesta = httpx.post(
            f"{base}/lecturas/CAP-17",
            content=enorme,
            headers={"content-type": "application/json", CABECERA_PRINCIPAL: json.dumps(REVISOR)},
            timeout=60,
        )

        assert respuesta.status_code == 413
        assert respuesta.json()["codigo"] == "cuerpo_demasiado_grande"

    def test_a_quien_no_se_identifica_no_se_le_lee_el_cuerpo(self, base: str) -> None:
        """El orden importa: primero quien pide, y despues lo que pide.

        Un cuerpo de nueve megas sin cabecera de principal sale con la denegacion, no con el 413: antes
        de saber quien pregunta el servidor no reserva memoria por el.
        """
        enorme = json.dumps(
            {"contexto": {"superficie": COLA, "tenant_id": TENANT_PROPIO}, "datos": {"x": "a" * 9_000_000}}
        )

        respuesta = httpx.post(
            f"{base}/lecturas/CAP-17",
            content=enorme,
            headers={"content-type": "application/json"},
            timeout=60,
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "autenticacion"

    def test_un_campo_de_contexto_mal_escrito_no_se_ignora(self, base: str) -> None:
        respuesta = httpx.post(
            f"{base}/lecturas/CAP-17",
            content=json.dumps({"contexto": {"superficie": COLA, "tenant": TENANT_PROPIO}, "datos": {}}),
            headers={"content-type": "application/json", CABECERA_PRINCIPAL: json.dumps(REVISOR)},
            timeout=30,
        )

        # Un `tenant` por `tenant_id` viajaria como "sin tenant" y lo pararia C30, pero diciendo otra
        # cosa. Se dice lo que pasa: el contexto trae un campo que no existe.
        assert respuesta.status_code == 400
        assert "tenant" in respuesta.json()["motivo"]

    def test_una_ruta_que_no_existe_tambien_sale_en_el_sobre(self, base: str) -> None:
        respuesta = httpx.post(f"{base}/lo-que-sea", content="{}", timeout=30)

        assert respuesta.status_code == 404
        assert respuesta.json()["error"] == "api"

    def test_un_metodo_que_no_es_post_tambien(self, base: str) -> None:
        respuesta = httpx.get(f"{base}/lecturas/CAP-17", timeout=30)

        assert respuesta.status_code == 405
        assert respuesta.json()["error"] == "api"
