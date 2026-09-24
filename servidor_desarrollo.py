#!/usr/bin/env python
"""`python servidor_desarrollo.py --desarrollo`: levanta `api/` en local contra los casos sinteticos.

Es la **composicion** de `FR-HTTP` (`ADR-015` §5): lo unico que sabe a la vez de `engine/`, de `api/` y de
uvicorn. Por eso vive aqui, en la raiz y al lado de `evaluar_casos.py`, y no dentro de `api/http/`: el
servidor no importa nada de `engine/` (contrato C27) y este fichero es quien le pone delante un
repositorio con actuaciones de verdad procesadas por el motor.

Lo que monta:

- Los **siete casos sinteticos** (`expedientes/EXP001-*`) procesados con `engine.motor`, en un mismo
  tenant, dentro de un `RepositorioMemoria`. No persiste nada: al parar el proceso no queda rastro.
- El **autenticador de desarrollo** (`ADR-015` C29), que lee el principal de una cabecera. Hace falta
  `--desarrollo` **escrito a mano**: no hay valor por defecto, y el autenticador ademas se niega a
  construirse si el anfitrion no es el bucle local. Cada respuesta lo dice en `avisos`.

Lo que **no** es: un despliegue. No hay TLS, ni dominio, ni sesion, ni limite de peticiones por cliente, y
el principal lo declara quien pregunta. Eso es `FR-DESPLIEGUE` (`ADR-015` §5), que depende de `API-09`.

Ejemplo de uso, y el mismo que imprime al arrancar:

```bash
python servidor_desarrollo.py --desarrollo                 # 127.0.0.1:8000, los 7 casos, sin OCR
curl -s localhost:8000/lecturas/CAP-17 \
  -H 'content-type: application/json' \
  -H 'x-cae-principal-desarrollo: {"usuario_id":"u-rev","perfiles":["T-REV"],"tenant_id":"T-001"}' \
  -d '{"contexto":{"superficie":"cola_revision","tenant_id":"T-001"},"datos":{}}'
```

Las pantallas de `FR1` viven en `front/workspace/` y **se abren en un navegador contra este servidor**
desde el 24/09/2026 (`GAP-HTTP-03`, `ADR-015` §7.2). En otra terminal:

```bash
cd front
VITE_CAE_PRINCIPAL='{"usuario_id":"u-rev","perfiles":["T-REV"],"tenant_id":"T-001"}' npm run dev
```

y la cola queda en <http://127.0.0.1:5173/>. El empaquetador reenvia `/api` aqui, asi que no hace falta
abrir CORS. Tambien se puede seguir hablando con el contrato a pelo, con `curl`.

Una advertencia de la primera demo: los casos entran en el repositorio **sin log**, asi que la cola sale
sin antiguedades y con la secuencia a 0 (`GAP-HTTP-04`). Y el repositorio es de memoria: una correccion
hecha desde el navegador cambia lo que se ve en la siguiente recarga y dura lo que dure el proceso.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from api.http import CABECERA_PRINCIPAL, CONFIRMACION_DESARROLLO, AutenticadorDeDesarrollo, crear_app
from api.repositorio import RepositorioMemoria
from api.servicios import Servicios
from engine.motor import procesar_actuacion
from engine.spec_registry import SpecRegistry

RAIZ = Path(__file__).resolve().parent
CARPETA_CASOS = RAIZ / "expedientes"
PATRON_CASOS = "EXP001-*"

#: El tenant al que se adscriben los casos sinteticos. Es de desarrollo, como todo lo de aqui.
TENANT_DESARROLLO = "T-001"

#: La fecha de evaluacion con la que se procesan, para que el veredicto sea el mismo que el del banco de
#: pruebas (el caso A, 305.829,6 kWh/año) y no dependa del dia en que se levante el servidor.
FECHA = date(2026, 9, 18)


def cargar_casos(
    repositorio: RepositorioMemoria,
    *,
    tenant_id: str = TENANT_DESARROLLO,
    ocr: bool = False,
    casos: Sequence[str] = (),
) -> tuple[str, ...]:
    """Procesa los casos sinteticos con el motor y los mete en el repositorio. Devuelve sus ids."""
    registro = SpecRegistry()
    registro.cargar_todas()
    cargados: list[str] = []
    for carpeta in sorted(CARPETA_CASOS.glob(PATRON_CASOS)):
        if not carpeta.is_dir() or (casos and carpeta.name not in casos):
            continue
        actuacion = procesar_actuacion(carpeta, fecha_evaluacion=FECHA, ocr=ocr, registro=registro)
        # `ocr` es **con que opciones se proceso**: `reprocesar` rehace el mismo trabajo con una entrada
        # mas (la correccion humana), no lo hace de otra manera (`ADR-014` C23).
        repositorio.anadir(carpeta.name, tenant_id, actuacion=actuacion, ocr=ocr)
        cargados.append(carpeta.name)
    return tuple(cargados)


def construir(
    *,
    anfitrion: str,
    tenant_id: str = TENANT_DESARROLLO,
    ocr: bool = False,
    casos: Sequence[str] = (),
    origenes_cors: Sequence[str] = (),
):
    """La aplicacion de desarrollo, con los casos cargados. Devuelve `(app, ids cargados)`."""
    repositorio = RepositorioMemoria()
    cargados = cargar_casos(repositorio, tenant_id=tenant_id, ocr=ocr, casos=casos)
    app = crear_app(
        # La senal va escrita aqui, en el unico fichero del repositorio que la escribe, y ademas detras
        # de `--desarrollo`: dos barreras para la pieza que en produccion regala el sistema entero.
        autenticador=AutenticadorDeDesarrollo(confirmacion=CONFIRMACION_DESARROLLO, anfitrion=anfitrion),
        servicios=Servicios(repositorio=repositorio),
        origenes_cors=origenes_cors,
    )
    return app, cargados


def _argumentos(argv: Sequence[str] | None = None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    analizador.add_argument(
        "--desarrollo",
        action="store_true",
        help="obligatorio: reconoce que este servidor no autentica a nadie y solo sirve datos sinteticos",
    )
    analizador.add_argument(
        "--anfitrion", default="127.0.0.1", help="solo el bucle local (por defecto 127.0.0.1)"
    )
    analizador.add_argument("--puerto", type=int, default=8000)
    analizador.add_argument("--tenant", default=TENANT_DESARROLLO)
    analizador.add_argument("--con-ocr", action="store_true", help="procesa los casos con OCR (lento)")
    analizador.add_argument("--caso", action="append", default=[], help="carpeta concreta; repetible")
    analizador.add_argument(
        "--origen",
        action="append",
        default=[],
        help="origen al que se permite CORS (p. ej. http://localhost:5173). Sin comodines",
    )
    return analizador.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    opciones = _argumentos(argv)
    if not opciones.desarrollo:
        print(
            "este servidor lee el principal de una cabecera y no comprueba ninguna credencial: hay que\n"
            "decirlo a mano con `--desarrollo`. No hay valor por defecto (`ADR-015` C29).",
            file=sys.stderr,
        )
        return 2
    import uvicorn

    app, cargados = construir(
        anfitrion=opciones.anfitrion,
        tenant_id=opciones.tenant,
        ocr=opciones.con_ocr,
        casos=tuple(opciones.caso),
        origenes_cors=tuple(opciones.origen),
    )
    principal = '{"usuario_id":"u-rev","perfiles":["T-REV"],"tenant_id":"' + opciones.tenant + '"}'
    base = f"http://{opciones.anfitrion}:{opciones.puerto}"
    print(f"casos cargados en el tenant {opciones.tenant}: {', '.join(cargados) or 'ninguno'}")
    print(f"AUTENTICACION DE DESARROLLO: el principal lo declara la cabecera {CABECERA_PRINCIPAL}")
    print("no hay credenciales, no hay sesion y no hay TLS: solo datos sinteticos, solo en local\n")
    print(f"  curl -s {base}/lecturas/CAP-17 \\")
    print("    -H 'content-type: application/json' \\")
    print(f"    -H '{CABECERA_PRINCIPAL}: {principal}' \\")
    print(
        '    -d \'{"contexto":{"superficie":"cola_revision","tenant_id":"'
        + opciones.tenant
        + '"},"datos":{}}\'\n'
    )
    uvicorn.run(app, host=opciones.anfitrion, port=opciones.puerto, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
