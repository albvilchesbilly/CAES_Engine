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

`evidencias` se recorta a las tres primeras de cada actuacion: una sola de ellas ocupa 750 KB (el texto
literal de un PDF entero) y la cola **no pinta ningun valor extraido** (`R-UI-09`). Se deja algo, y no
cero, para que el test que comprueba que ese bloque llega y no se pinta siga teniendo algo que mirar.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from api.contrato import Peticion, Respuesta
from api.lecturas import leer
from api.permisos import Contexto, ErrorPermiso, Principal
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.eventos.log import Actor
from engine.motor import procesar_actuacion
from engine.seguimiento import TareaRecibida, registrar_tarea
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parents[4]
SALIDA = Path(__file__).resolve().parent
FECHA = date(2026, 9, 18)
INSTANTE = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
TENANT = "T-001"
PANTALLA = "cola_revision"

#: Cuantas evidencias se conservan de cada actuacion (ver la cabecera).
EVIDENCIAS_CONSERVADAS = 3

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
    return {
        "capacidad": respuesta.capacidad,
        "rol": respuesta.rol,
        "eventos": list(respuesta.eventos),
        "datos": respuesta.datos,
        "avisos": list(respuesta.avisos),
    }


def recortar(respuesta: dict[str, object]) -> dict[str, object]:
    datos = dict(respuesta["datos"])  # type: ignore[arg-type]
    evidencias = datos.get("evidencias")
    if isinstance(evidencias, list):
        datos["evidencias"] = evidencias[:EVIDENCIAS_CONSERVADAS]
    return {**respuesta, "datos": datos}


def escribir(nombre: str, contenido: object) -> None:
    ruta = SALIDA / nombre
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{ruta.name}: {ruta.stat().st_size // 1024} KB")


def poblar(registro: SpecRegistry) -> RepositorioMemoria:
    repositorio = RepositorioMemoria()
    for clave in CASOS:
        repositorio.anadir(clave, TENANT, actuacion=procesada(registro, clave))

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


def main() -> None:
    registro = SpecRegistry()
    registro.cargar_todas()
    servicios = Servicios(repositorio=poblar(registro), instante=INSTANTE)
    quien = Principal("u-rev", ("T-REV",), TENANT)

    cola = leer(Peticion("CAP-17", quien, Contexto(PANTALLA, TENANT)), servicios=servicios)
    escribir("cola.json", a_dict(cola))

    detalle: dict[str, dict[str, object]] = {}
    for fila in cola.datos["cola"]:  # type: ignore[union-attr]
        actuacion_id = fila["identificacion"]["actuacion_id"]
        detalle[actuacion_id] = {
            capacidad: recortar(
                a_dict(
                    leer(
                        Peticion(capacidad, quien, Contexto(PANTALLA, TENANT, actuacion_id)),
                        servicios=servicios,
                    )
                )
            )
            for capacidad in ("CAP-03", "CAP-04", "CAP-14")
        }
    escribir("detalle.json", detalle)

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


if __name__ == "__main__":
    main()
