#!/usr/bin/env python
"""Genera los datos de prueba de la cola llamando a `api/` de verdad. **No es un test.**

Se ejecuta a mano desde la raiz del repositorio (`python front/workspace/tests/datos/generar.py`) y
vuelca en JSON lo que responden `CAP-17`, `CAP-03`, `CAP-04` y `CAP-14` sobre los casos sinteticos.
Los tests de `front/workspace/` se verifican asi contra el contrato cerrado en `FR1.a` (`ADR-014` §2)
y no contra un payload escrito a mano, que es la forma barata de probar una pantalla contra una idea
equivocada de lo que sirve el servidor.

Lo que monta, y por que cada pieza:

- Los **siete casos** en un mismo tenant. Quien decide cuales estan en la cola es el servidor: A, E y F
  estan `PREVALIDADO` y sin nada que esperar, y solo entran si la plataforma les pide algo.
- Una **tarea de la plataforma** sobre A, para que el caso del ahorro de referencia (305.829,6 kWh/año)
  tenga un motivo por el que estar en la cola (`CA-COLA-03`).
- El **ciclo completo** sobre G hasta `EN_PLATAFORMA` sin requerimiento abierto: es la fila que la
  pantalla marca "solo lectura" (`R-UI-05` anticipado, `CA-COLA-12`).

**Lo unico que este script decide es que deja fuera, y lo deja escrito.** Los tres recortes van
declarados en `recortes.json` —con su limite y con el nombre de lo omitido— porque una pantalla que se
prueba contra un fichero recortado en silencio se prueba contra otra cosa:

- `evidencias`: se conservan todas menos las que superan `EVIDENCIA_MAXIMA_BYTES`. Hoy solo cae una,
  `registro.datos_canonicos`, cuyo `texto_literal` es el CSV canonico entero del registro (750 KB). La
  vista de revision **pinta todos los datos con su cita** (`R-UI-09`, `CA-REV-05`), asi que el recorte de
  "las tres primeras" que valia para la cola aqui habria dejado el fichero sin `PM` ni el resto del
  calculo, que es justo lo que hay que mirar.
- `documentos`: se sirven los que pesan menos de `DOCUMENTO_MAXIMO_BYTES` (el informe fotografico son
  213 KB y el registro 70 KB). Son los bytes **tal cual los sirve `leer_documento`**, en base64: no se
  recorta ninguno a medias, o entra entero o no entra.
- La correccion del caso C se ejecuta de verdad (`CAP-05`) y se vuelcan las tres lecturas **de antes y de
  despues**, que es el lazo de `ADR-014` §3 visto desde la pantalla.

`detalle.json` lo comparten las dos pantallas. La respuesta de una lectura **no depende de la superficie
desde la que se pide** —la superficie solo desempata el rol, y aqui solo hay un perfil en juego—, y este
script lo comprueba en vez de darlo por bueno (`_misma_respuesta_en_las_dos_pantallas`).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

# Este fichero se ejecuta como script desde la raiz del repositorio, y entonces `sys.path[0]` es esta
# carpeta y no la raiz: sin esto, `import api` falla. Por eso lo de `api/` y `engine/` no esta pegado al
# resto de los imports, y por eso la excepcion se declara para todo el fichero (`E402`) en vez de
# repetirla en cada linea.
# ruff: noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from api.comandos import ejecutar
from api.contrato import Peticion, Respuesta
from api.lecturas import leer
from api.lecturas.documentos import CLAVE_DOCUMENTO, documento_a_transporte, leer_documento
from api.permisos import Contexto, ErrorApi, ErrorPermiso, Principal
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.eventos.log import Actor
from engine.motor import procesar_actuacion
from engine.requerimientos import Interpretacion, Item, Requerimiento, confirmar, reabrir
from engine.seguimiento import TareaRecibida, registrar_tarea
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[4]
SALIDA = Path(__file__).resolve().parent
FECHA = date(2026, 9, 18)
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
TENANT = "T-001"
PANTALLA = "cola_revision"
PANTALLA_REVISION = "vista_revision"

#: Las tres lecturas que consumen las dos pantallas por actuacion (`T-REV-revision.md` §5).
LECTURAS = ("CAP-03", "CAP-04", "CAP-14")

#: Una evidencia mas grande que esto no entra en el fichero de pruebas (ver la cabecera). Hoy solo hay
#: una: el `texto_literal` de `registro.datos_canonicos` es el CSV entero del registro, 750 KB.
EVIDENCIA_MAXIMA_BYTES = 20_000

#: Un documento mas grande que esto no se vuelca. Entero o nada: servir medio documento seria servir
#: otro documento, y la huella dejaria de casar (`CA-REV-16`). El limite deja dentro el PDF combinado
#: del caso G (10.590 bytes) **y sus tres partes**, que es el unico material con el que se puede probar
#: el aviso de `CA-REV-17`: una parte no es un fichero y se sirve el combinado entero, sin recortar.
DOCUMENTO_MAXIMO_BYTES = 12_288

#: La correccion del caso C, tal y como la escribiria una persona en el formulario de `CAP-05`.
#: El `valor` viaja **como cadena**: un `float` en `datos` lo rechaza `api.contrato._sin_coma_flotante`.
CORRECCION_C = {
    "variable": "PM",
    "num_serie_motor": "MTR-SYN-0001",
    "valor": "110",
    "justificacion": (
        "La ficha tecnica del motor (fuente primaria), la ficha cumplimentada y la placa dicen 110 kW. "
        "El certificado del instalador arrastra una errata al transcribir la ficha tecnica."
    ),
}

MOTOR = Actor("motor", "engine")
REVISOR = Actor("humano", "u-rev", rol="T-REV")
RESPONSABLE = Actor("humano", "u-res", rol="T-RES")

CASOS = {
    "A": "EXP001-A_completo",
    "B": "EXP001-B_falta_registro",
    "C": "EXP001-C_contradictorio",
    "D": "EXP001-D_fuera_ambito",
    "E": "EXP001-E_dos_motores",
    "F": "EXP001-F_tres_motores",
    "G": "EXP001-G_desordenado",
}

#: El camino feliz de `docs/03` §7.2 hasta `EN_PLATAFORMA`, con el actor que exige cada paso.
CICLO_COMPLETO = (
    ("ActuacionAbierta", {"actuacion_id": "G"}, MOTOR),
    ("FichaAsignada", {"codigo": "IND240"}, MOTOR),
    ("DocumentoRegistrado", {"sha256": "a" * 64}, MOTOR),
    ("DatoConsolidado", {"variable": "PM"}, MOTOR),
    ("CalculoRealizado", {"unidades": 1}, MOTOR),
    ("VeredictoEmitido", {"veredicto": "PREVALIDADO"}, MOTOR),
    ("RevisionAprobada", {"conforme": True}, REVISOR),
    ("PayloadConstruido", {"hash_cabecera": "b" * 64}, MOTOR),
    ("EntregadoADelegado", {"tenant": TENANT}, MOTOR),
    ("FirmaRegistrada", {"firmante": "responsable"}, RESPONSABLE),
)


def procesada(registro: SpecRegistry, caso: str) -> object:
    return procesar_actuacion(
        RAIZ / "expedientes" / CASOS[caso], fecha_evaluacion=FECHA, ocr=False, registro=registro
    )


def a_dict(respuesta: Respuesta) -> dict[str, object]:
    """La respuesta en la forma que viaja al front, con **todos** los campos del sobre.

    `rol_nombre` esta aqui desde que `api/` lo sirve (`GAP-REV-11`/`GAP-COLA-06`, cerrado el 23/09/2026):
    enumerar los campos a mano es comodo y tiene este precio, asi que cuando el contrato crece, esta
    funcion crece con el. Lo que el sobre traiga y aqui no se copie, la pantalla no lo vera nunca.
    """
    return {
        "capacidad": respuesta.capacidad,
        "rol": respuesta.rol,
        "rol_nombre": respuesta.rol_nombre,
        "eventos": list(respuesta.eventos),
        "datos": respuesta.datos,
        "avisos": list(respuesta.avisos),
    }


def _pesa(valor: object) -> int:
    return len(json.dumps(valor, ensure_ascii=False, default=str))


def recortar(respuesta: dict[str, object], omitidas: list[str]) -> dict[str, object]:
    """Quita los datos cuya evidencia no cabe en un fichero de pruebas, y **apunta cuales**.

    No se recorta el contenido de ninguna evidencia: un `texto_literal` a medias es un texto literal
    falso, y la pantalla lo pintaria como si fuera la cita entera. O entra el dato completo o no entra, y
    lo que no entra se declara en `recortes.json` para que un test pueda contrastar lo que se pinta con
    lo que llego, en vez de con lo que deberia haber llegado.
    """
    datos = dict(respuesta["datos"])  # type: ignore[arg-type]
    evidencias = datos.get("evidencias")
    if isinstance(evidencias, list):
        conservadas = []
        for dato in evidencias:
            if _pesa(dato) <= EVIDENCIA_MAXIMA_BYTES:
                conservadas.append(dato)
            else:
                omitidas.append(str(dato.get("variable")))
        datos["evidencias"] = conservadas
    return {**respuesta, "datos": datos}


def escribir(nombre: str, contenido: object) -> None:
    ruta = SALIDA / nombre
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{ruta.name}: {ruta.stat().st_size // 1024} KB")


def poblar(registro: SpecRegistry) -> RepositorioMemoria:
    repositorio = RepositorioMemoria()
    for clave in CASOS:
        # `ocr=False` es **con que opciones se proceso**, y lo usa `reprocesar` para rehacer el mismo
        # trabajo con una entrada mas (`ADR-014` C23). Sin esto, la correccion del caso C se recalcularia
        # con OCR y el veredicto podria cambiar por algo que nadie corrigio.
        repositorio.anadir(clave, TENANT, actuacion=procesada(registro, clave), ocr=False)

    registrar_tarea(
        repositorio.log("A"),
        TareaRecibida(
            id="TAR-A-1",
            tenant_id=TENANT,
            asunto="Aportar documentacion adicional",
            instante=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            referencia="REF-A-1",
            vence_en=date(2026, 10, 1),
        ),
    )
    for clave, instante in (
        ("B", datetime(2026, 9, 16, 17, 40, tzinfo=UTC)),
        ("C", datetime(2026, 9, 17, 9, 12, tzinfo=UTC)),
        ("D", datetime(2026, 9, 16, 11, 5, tzinfo=UTC)),
    ):
        repositorio.log(clave).anadir(
            "DocumentoRegistrado", {"sha256": "1" * 64}, actor=MOTOR, ocurrido_en=instante
        )

    for tipo, payload, actor in CICLO_COMPLETO:
        repositorio.log("G").anadir(
            tipo, payload, actor=actor, ocurrido_en=datetime(2026, 9, 12, 8, 30, tzinfo=UTC)
        )
    registrar_tarea(
        repositorio.log("G"),
        TareaRecibida(
            id="TAR-G-1",
            tenant_id=TENANT,
            asunto="Revisar la documentacion aportada",
            instante=datetime(2026, 9, 13, 8, 30, tzinfo=UTC),
            referencia="REF-G-1",
        ),
    )
    return repositorio


def _lecturas(servicios: Servicios, quien: Principal, actuacion_id: str, pantalla: str) -> dict:
    """Las tres lecturas por actuacion, tal cual las sirve `api/`."""
    return {
        capacidad: a_dict(
            leer(
                Peticion(capacidad, quien, Contexto(pantalla, TENANT, actuacion_id)),
                servicios=servicios,
            )
        )
        for capacidad in LECTURAS
    }


def _misma_respuesta_en_las_dos_pantallas(servicios: Servicios, quien: Principal, actuacion_id: str) -> None:
    """`detalle.json` lo comparten la cola y la vista de revision: aqui se comprueba que puede.

    La superficie del contexto solo desempata el rol cuando dos perfiles de la misma superficie comparten
    la capacidad (`ADR-050`), y ninguna de estas tres lo hace. Si algun dia una respuesta dependiera de
    la pantalla desde la que se pide, este fichero dejaria de poder compartirse y hay que enterarse aqui,
    no en un test de front que falla sin explicar por que.
    """
    desde_cola = _lecturas(servicios, quien, actuacion_id, PANTALLA)
    desde_revision = _lecturas(servicios, quien, actuacion_id, PANTALLA_REVISION)
    if desde_cola != desde_revision:
        raise SystemExit(
            f"las lecturas de {actuacion_id!r} ya no son iguales desde {PANTALLA!r} y desde "
            f"{PANTALLA_REVISION!r}: `detalle.json` no se puede compartir entre las dos pantallas"
        )


def _documentos(
    servicios: Servicios, quien: Principal, actuacion_id: str, fichas: object, omitidos: list[str]
) -> dict[str, object]:
    """Los documentos de la actuacion que caben, **servidos por `leer_documento`** (contrato C17).

    Se piden por su `doc_id`, que es lo unico que la pantalla puede usar (`R-UI-12`), y se guardan en la
    misma forma en la que viajan: el sobre de `documento_a_transporte`, con los bytes en base64. Nadie
    recorta ni convierte nada; lo que no cabe, no se vuelca y se dice cual.
    """
    servidos: dict[str, object] = {}
    for ficha in fichas or ():
        doc_id = str(ficha.get("doc_id"))
        if int(ficha.get("bytes") or 0) > DOCUMENTO_MAXIMO_BYTES:
            omitidos.append(f"{actuacion_id}:{ficha.get('nombre')}")
            continue
        respuesta = leer_documento(
            Peticion(
                "CAP-03",
                quien,
                Contexto(PANTALLA_REVISION, TENANT, actuacion_id),
                {"doc_id": doc_id},
            ),
            servicios=servicios,
        )
        sobre = a_dict(respuesta)
        sobre["datos"] = {CLAVE_DOCUMENTO: documento_a_transporte(respuesta.datos[CLAVE_DOCUMENTO])}
        servidos[doc_id] = sobre
    return servidos


def _correccion(servicios: Servicios, quien: Principal, antes: dict) -> dict[str, object]:
    """El lazo de `ADR-014` §3 sobre el caso C: se corrige `PM` con justificacion y el motor recalcula.

    Se ejecuta **de verdad**. Lo que sale de aqui es lo que la pantalla va a ver en el unico camino que
    mide el valor del producto (`T-REV-revision.md` §6): el conflicto, la correccion con su justificacion
    y el veredicto de despues. `recalculada` lo decide el servidor; la pantalla solo lo lee (`CA-REV-09`).
    """
    contexto = Contexto(PANTALLA_REVISION, TENANT, "C")
    respuesta = ejecutar(Peticion("CAP-05", quien, contexto, dict(CORRECCION_C)), servicios=servicios)
    omitidas: list[str] = []
    despues = {
        capacidad: recortar(lectura, omitidas)
        for capacidad, lectura in _lecturas(servicios, quien, "C", PANTALLA_REVISION).items()
    }
    veredicto = despues["CAP-03"]["datos"]["veredicto"]["valor"]
    print("correccion del caso C:", antes["CAP-03"]["datos"]["veredicto"]["valor"], "→", veredicto)
    return {
        "capacidad": "CAP-05",
        "actuacion_id": "C",
        "datos_enviados": dict(CORRECCION_C),
        "respuesta": a_dict(respuesta),
        "despues": despues,
    }


#: El requerimiento oficial que se le mete al caso G al final de todo (ver `_requerimiento`).
REQUERIMIENTO_G = Requerimiento(
    id="REQ-2026-014",
    origen="verificador",
    actuacion_id="G",
    recibido_en=datetime(2026, 9, 18, 10, 0, tzinfo=UTC),
    motivos=("Falta el registro de funcionamiento que acredite N2.",),
    informe_sha256="c" * 64,
    literal_plataforma="REQUERIMIENTO DE SUBSANACION",
)


def _requerimiento(servicios: Servicios, quien: Principal) -> dict[str, object]:
    """El caso G con un requerimiento oficial abierto: la otra mitad de `R-UI-05` (`CA-REV-04`).

    Se hace **al final y con `engine.requerimientos`**, no tocando un payload: `reabrir` sella el hecho
    (`RequerimientoRecibido`) y la lectura confirmada (`RequerimientoInterpretado`), y es la maquina de
    estados la que decide que pasa con el ciclo.

    Lo que esto destapa, y que la spec no previo: al reabrir, el ciclo deja de ser `EN_PLATAFORMA` y pasa
    a `PENDIENTE_SUBSANACION`. La condicion literal de `T-REV-revision.md` §9 —`EN_PLATAFORMA` **y**
    requerimiento abierto— no se puede dar nunca, asi que la pantalla no puede apoyar el candado solo en
    el estado de ciclo: lo apoya en `firmada`, que es la marca que el nucleo usa para rechazar una
    correccion posterior a la firma (`docs/02` §5.4, `CorreccionRechazadaPostFirma`).
    """
    log = servicios.repositorio.log("G")
    interpretacion = Interpretacion(
        requerimiento_id=REQUERIMIENTO_G.id,
        version_interprete="lexico-0.1.0",
        items=(
            Item(
                texto_literal=REQUERIMIENTO_G.motivos[0],
                regla_id="R-EVD-04",
                documento="registro_funcionamiento",
                variable="N2",
                confianza=Decimal("0.8"),
            ),
        ),
    )
    eventos = reabrir(
        log,
        REQUERIMIENTO_G,
        confirmar(interpretacion, actor=REVISOR),
        actor=REVISOR,
        confirmado_en=datetime(2026, 9, 18, 11, 0, tzinfo=UTC),
    )
    omitidas: list[str] = []
    lecturas = {
        capacidad: recortar(lectura, omitidas)
        for capacidad, lectura in _lecturas(servicios, quien, "G", PANTALLA_REVISION).items()
    }
    estado = lecturas["CAP-14"]["datos"]["estados_plataforma"]
    print("requerimiento en G:", estado["estado_ciclo"], "·", estado["requerimiento_abierto"])
    return {
        "actuacion_id": "G",
        "eventos": [evento.tipo for evento in eventos],
        "lecturas": lecturas,
    }


def _sobre_del_error(exc: Exception, clase: str) -> dict[str, object]:
    """El sobre que el transporte entregaria al front, con el motivo **literal** del servidor."""
    estado = 403 if clase == "permiso" else 400
    return {"estado": estado, "cuerpo": {"error": clase, "motivo": str(exc)}}


def _rechazos(servicios: Servicios, quien: Principal) -> dict[str, object]:
    """Las tres negativas de `api/` que la pantalla tiene que ensenar literales, ejercidas de verdad.

    Ninguna se escribe a mano: se pide lo que no se debe pedir y se guarda lo que el servidor contesta.

    - **Sin justificacion** (`CA-REV-02`, segunda mitad): `R-UI-04` no es solo un boton inhabilitado. El
      front pone una barrera para explicar; la que cuenta es la del servidor, y aqui esta su respuesta.
    - **Con coma flotante** (`CA-REV-08`): una magnitud que entra como `float` ya ha perdido exactitud
      antes de llegar al motor. Viaja como cadena o no viaja.
    - **De otro tenant** (`CA-REV-18`): una denegacion se ensena con su motivo, no se traga.

    Se ejecutan **antes** de la correccion buena: las tres fallan en la puerta y no tocan el log, pero el
    orden deja claro que lo que se vuelca despues no depende de ellas.
    """
    contexto = Contexto(PANTALLA_REVISION, TENANT, "C")
    rechazos: dict[str, object] = {}

    sin_justificacion = {k: v for k, v in CORRECCION_C.items() if k != "justificacion"}
    try:
        ejecutar(Peticion("CAP-05", quien, contexto, sin_justificacion), servicios=servicios)
    except ErrorApi as exc:
        rechazos["sin_justificacion"] = {
            "datos_enviados": sin_justificacion,
            **_sobre_del_error(exc, "api"),
        }
    else:  # pragma: no cover - si esto deja de fallar, `R-UI-04` ha dejado de valer en el servidor
        raise SystemExit("CAP-05 ya admite una correccion sin justificacion: mira `R-UI-04`")

    con_float = {**CORRECCION_C, "valor": 110.0}
    try:
        ejecutar(Peticion("CAP-05", quien, contexto, con_float), servicios=servicios)
    except ErrorApi as exc:
        rechazos["coma_flotante"] = {
            "datos_enviados": {**con_float, "valor": "110.0 (float en la peticion)"},
            **_sobre_del_error(exc, "api"),
        }
    else:  # pragma: no cover - si esto deja de fallar, el ahorro puede entrar por coma flotante
        raise SystemExit("CAP-05 ya admite una magnitud como float: mira `_sin_coma_flotante`")

    # El documento alterado: se cambian los bytes guardados **debajo** de la huella que declaro la
    # ingesta, que es exactamente lo que el control de integridad existe para detectar. Se hace sobre una
    # copia del contenido y se deja como estaba: lo que se guarda aqui es el mensaje del servidor.
    registro = servicios.repositorio._registro("C")  # noqa: SLF001 - script de pruebas, no produccion
    documentos = servicios.repositorio.actuacion("C").documentos
    ficha = next(d for d in documentos if d.tipo == "ficha_cumplimentada")
    huella = str(ficha.sha256)
    anterior = registro.contenidos.get(huella)
    registro.contenidos[huella] = b"esto no es el documento que se ingesto"
    try:
        leer_documento(Peticion("CAP-03", quien, contexto, {"doc_id": ficha.doc_id}), servicios=servicios)
    except ErrorApi as exc:
        rechazos["documento_alterado"] = {"doc_id": ficha.doc_id, **_sobre_del_error(exc, "api")}
    else:  # pragma: no cover - si esto deja de fallar, el control de integridad ha caido
        raise SystemExit("leer_documento sirve un documento alterado: mira `ErrorIntegridad`")
    finally:
        if anterior is None:
            registro.contenidos.pop(huella, None)
        else:
            registro.contenidos[huella] = anterior

    ajeno = Principal("u-otro", ("T-REV",), "T-999")
    try:
        leer(Peticion("CAP-03", ajeno, Contexto(PANTALLA_REVISION, "T-999", "C")), servicios=servicios)
    except ErrorPermiso as exc:
        rechazos["otro_tenant"] = _sobre_del_error(exc, "permiso")
    else:  # pragma: no cover - si esto deja de denegarse, el aislamiento por tenant ha caido
        raise SystemExit("CAP-03 sirve una actuacion de otro tenant: mira `comprobar_alcance`")

    return rechazos


def main() -> None:
    registro = SpecRegistry()
    registro.cargar_todas()
    servicios = Servicios(repositorio=poblar(registro), instante=INSTANTE)
    quien = Principal("u-rev", ("T-REV",), TENANT)

    cola = leer(Peticion("CAP-17", quien, Contexto(PANTALLA, TENANT)), servicios=servicios)
    escribir("cola.json", a_dict(cola))

    evidencias_omitidas: dict[str, list[str]] = {}
    documentos_omitidos: list[str] = []
    detalle: dict[str, dict[str, object]] = {}
    documentos: dict[str, dict[str, object]] = {}
    for fila in cola.datos["cola"]:  # type: ignore[union-attr]
        actuacion_id = fila["identificacion"]["actuacion_id"]
        omitidas: list[str] = []
        lecturas = _lecturas(servicios, quien, actuacion_id, PANTALLA)
        detalle[actuacion_id] = {
            capacidad: recortar(respuesta, omitidas) for capacidad, respuesta in lecturas.items()
        }
        evidencias_omitidas[actuacion_id] = omitidas
        documentos[actuacion_id] = _documentos(
            servicios,
            quien,
            actuacion_id,
            lecturas["CAP-03"]["datos"].get("documentos"),
            documentos_omitidos,
        )
    _misma_respuesta_en_las_dos_pantallas(servicios, quien, "C")
    escribir("detalle.json", detalle)
    escribir("documentos.json", documentos)

    escribir("rechazos.json", _rechazos(servicios, quien))

    # El lazo va **el ultimo**: corrige el caso C de verdad y deja el repositorio con el veredicto nuevo,
    # asi que todo lo que se vuelque despues de esta linea ya no seria el caso C contradictorio.
    escribir("correccion.json", _correccion(servicios, quien, detalle["C"]))
    escribir("requerimiento.json", _requerimiento(servicios, quien))

    escribir(
        "recortes.json",
        {
            "evidencia_maxima_bytes": EVIDENCIA_MAXIMA_BYTES,
            "documento_maximo_bytes": DOCUMENTO_MAXIMO_BYTES,
            "evidencias_omitidas": evidencias_omitidas,
            "documentos_omitidos": sorted(documentos_omitidos),
        },
    )

    # La denegacion, con las palabras exactas del servidor: `CA-COLA-08` exige que se vean literales,
    # y un motivo inventado aqui probaria la pantalla contra un mensaje que nadie manda.
    quien_no_puede = Principal("u-ope", ("T-OPE",), TENANT)
    try:
        leer(Peticion("CAP-17", quien_no_puede, Contexto(PANTALLA, TENANT)), servicios=servicios)
    except ErrorPermiso as denegacion:
        sobre = {"error": "permiso", "motivo": str(denegacion)}
        escribir("denegacion.json", {"estado": 403, "cuerpo": sobre})
    else:  # pragma: no cover - si esto deja de denegarse, la matriz ha cambiado y hay que mirarla
        raise SystemExit("CAP-17 ya no se deniega a T-OPE: revisa la matriz antes de seguir")

    print("cola:", [f["identificacion"]["actuacion_id"] for f in cola.datos["cola"]])  # type: ignore[union-attr]
    print("fuera de la cola:", sorted(set(CASOS) - set(detalle)))
    print("evidencias omitidas:", evidencias_omitidas)
    print("documentos omitidos:", sorted(documentos_omitidos))


if __name__ == "__main__":
    main()
