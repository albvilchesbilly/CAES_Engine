"""De donde saca `api/` lo que lee y donde escribe lo que pasa: el puerto de datos del contrato C15.

`api/` **no persiste nada**: recibe un `Repositorio` y le pide la actuacion ya procesada por `engine/` y su
log de eventos. Tenerlo como protocolo, y no como una clase concreta, es lo que permite que el contrato de
`FR0` se pruebe hoy contra memoria y funcione mañana contra lo que S3.1 decida, sin tocar ni un comando.

Por que un puerto y no un acceso directo al motor: `procesar_actuacion` recorre una carpeta y tarda
segundos; una API que lo llamara en cada lectura seria inservible, y ademas el ciclo de vida de una
actuacion (quien es su tenant, quien es parte en ella) no lo sabe el motor, que solo procesa lo que hay en
una carpeta. Esas dos cosas las sabe el repositorio.

Con una excepcion declarada, y solo una: **`reprocesar`** (contrato C23, `ADR-014` §3). Corregir un dato
recalcula en el acto (Billy, 23/09/2026), asi que hay un camino —uno— en el que la latencia de segundos se
paga dentro de un comando. Sigue siendo el repositorio quien llama al motor, no `api/`: el comando pide
"rehaz tu trabajo con esta entrada mas" y no toca ni una decision. Si algun dia hay que reprocesar en lote,
esa decision se revisa.

`RepositorioAusente` es el valor por defecto: **falla diciendo que falta**, en vez de devolver vacio. Una
lectura que devuelve "no hay datos" cuando lo que pasa es que nadie ha configurado el repositorio es la
forma mas barata de que un error de despliegue parezca un expediente vacio.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from api.permisos import ErrorApi
from engine.eventos.log import LogEventos


@runtime_checkable
class Repositorio(Protocol):
    """Lo que `api/` necesita saber de fuera del nucleo. Ninguna de estas operaciones calcula nada."""

    def actuacion(self, actuacion_id: str) -> object | None:
        """La actuacion ya procesada por `engine.motor`, o `None` si no existe."""
        ...

    def log(self, actuacion_id: str) -> LogEventos | None:
        """El log de eventos de la actuacion, o `None` si todavia no tiene."""
        ...

    def abrir(self, actuacion_id: str, tenant_id: str) -> LogEventos:
        """Crea el log de una actuacion nueva y la adscribe al tenant. Error si ya existia."""
        ...

    def tenant_de(self, actuacion_id: str) -> str | None:
        """El tenant de la actuacion, o `None` si el repositorio no la conoce (todavia no existe).

        No levanta error con una actuacion desconocida a proposito: es la comprobacion de aislamiento, y
        tiene que poder responder "no la conozco" para que una alta (que aun no existe) siga su camino.
        Lo que no puede es decir que una actuacion ajena es propia.
        """
        ...

    def partes_de(self, actuacion_id: str) -> tuple[str, ...]:
        """Usuarios externos que son parte en la actuacion (instalador, cliente)."""
        ...

    def actuaciones_de(self, tenant_id: str) -> tuple[str, ...]:
        """Las actuaciones de un tenant, en orden estable."""
        ...

    def todas(self) -> tuple[str, ...]:
        """Todas las actuaciones, para las lecturas globales. En orden estable."""
        ...

    def requerimiento(self, actuacion_id: str, requerimiento_id: str) -> tuple[object, object] | None:
        """El requerimiento y la interpretacion **propuesta** de un agente, para que un humano la confirme."""
        ...

    def reprocesar(self, actuacion_id: str) -> object:
        """Vuelve a procesar la actuacion aplicando las correcciones humanas de su log, y guarda el resultado.

        Contrato C23 (`ADR-014` §3). Es la unica operacion del puerto que hace trabajar al motor, y por eso
        es la unica que tarda segundos: se acepto esa latencia dentro de `CAP-05` para que corregir un dato
        y recalcular sean, de cara a la persona, un solo acto.

        **Aqui no se decide nada.** Quien llama no elige valores, no evalua reglas y no fija veredicto: le
        pide al nucleo que rehaga su trabajo con una entrada mas —las correcciones que ya estan selladas en
        el log— y el nucleo vuelve a decidir. La regla de oro 1 se mantiene entera.

        Por dentro es `procesar_actuacion(carpeta, correcciones=engine.correcciones.de_log(log))`, y
        **sustituye** la actuacion guardada: la siguiente lectura ve el veredicto nuevo, no el viejo.

        Levanta si no puede hacerlo (no conoce la carpeta, el ciclo del log no se puede leer, el motor
        falla). Fallar diciendolo es lo correcto: quien dispara el reproceso tiene que poder avisar de que
        el veredicto esta **pendiente de recalculo**, en vez de presentar el anterior como actualizado.
        """
        ...

    def registrar_documento(self, actuacion_id: str, ruta: str) -> Mapping[str, object]:
        """Registra un fichero **que ya esta del lado del servidor** y devuelve su huella y metadatos.

        La `ruta` no viene nunca de una peticion: `CAP-02` rechaza `ruta`, `nombre_fichero` y `path`
        (`ADR-012` §1 y su espejo). Esta operacion es para lo que ya esta en disco —la carpeta que ingesto
        el nucleo, el arranque de desarrollo—; lo que sube una persona entra por `guardar_documento`.

        La huella la calcula el nucleo sobre los bytes, nunca la trae el cliente: vinculamos por hash, y un
        hash que envia quien sube el fichero no vincula nada.
        """
        ...

    def guardar_documento(self, actuacion_id: str, contenido: bytes) -> str:
        """Guarda los bytes de un documento aportado y devuelve su huella, calculada sobre el contenido.

        **Esta en el puerto porque `CAP-02` la pide** (`ADR-014` §1, fleco 1 de `GAP-REV-03`): hasta el
        23/09/2026 el comando la sondeaba con `getattr` y el `Protocol` no la declaraba. Un puerto que no
        declara lo que se le pide no es un contrato: la implementacion que no la tenga esta incompleta, y
        se entera al arrancar, no cuando alguien intente subir un fichero.
        """
        ...

    def bytes_de_documento(self, actuacion_id: str, sha256: str) -> bytes | None:
        """Los bytes de un documento de esa actuacion, **resueltos por su huella** (`ADR-012` §1).

        El contrato de esta operacion, que es lo que impide leer un fichero cualquiera del servidor:

        - **Entra una huella, nunca una ruta.** Quien sabe donde estan los bytes es el repositorio; el
          llamante solo sabe huellas. Una ruta que viniera de fuera seria un camino a `/etc/passwd`.
        - **Entra tambien la actuacion**, y el repositorio solo mira dentro de ella: aunque el llamante
          acertara una huella ajena, no la encontraria aqui. Es la segunda barrera despues del tenant.
        - **Devuelve los bytes tal cual se ingestaron**, sin recortar, rotar ni comprimir. Quien comprueba
          que siguen casando con la huella es `api.lecturas.documentos`, al servir.
        - `None` si no los tiene. No se devuelve un sustituto ni un fichero "parecido".
        """
        ...


class RepositorioAusente:
    """El repositorio por defecto: no hay ninguno configurado y se dice, en vez de fingir que esta vacio."""

    _MOTIVO = (
        "no hay repositorio configurado: pasa `Servicios(repositorio=...)`. La persistencia de "
        "actuaciones y logs es S3.1; `FR0` es el contrato"
    )

    def actuacion(self, actuacion_id: str) -> object | None:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def log(self, actuacion_id: str) -> LogEventos | None:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def abrir(self, actuacion_id: str, tenant_id: str) -> LogEventos:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def tenant_de(self, actuacion_id: str) -> str | None:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def partes_de(self, actuacion_id: str) -> tuple[str, ...]:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def actuaciones_de(self, tenant_id: str) -> tuple[str, ...]:
        raise ErrorApi(f"{tenant_id}: {self._MOTIVO}")

    def todas(self) -> tuple[str, ...]:
        raise ErrorApi(self._MOTIVO)

    def requerimiento(self, actuacion_id: str, requerimiento_id: str) -> tuple[object, object] | None:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def reprocesar(self, actuacion_id: str) -> object:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def registrar_documento(self, actuacion_id: str, ruta: str) -> Mapping[str, object]:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def guardar_documento(self, actuacion_id: str, contenido: bytes) -> str:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")

    def bytes_de_documento(self, actuacion_id: str, sha256: str) -> bytes | None:
        raise ErrorApi(f"{actuacion_id}: {self._MOTIVO}")


@dataclass(frozen=True)
class Servicios:
    """Lo que un comando o una lectura necesitan de fuera de si mismos. Se inyecta; no se busca solo.

    `instante` fija el reloj de los eventos que se escriban. Se inyecta por la misma razon que en
    `salida/`: sin el, dos ejecuciones de la misma peticion no serian comparables en un test.
    """

    repositorio: Repositorio = field(default_factory=RepositorioAusente)
    instante: datetime | None = None


def servicios_de(servicios: Servicios | None) -> Servicios:
    """Los servicios que llegan, o los de por defecto (que fallan diciendo que falta el repositorio)."""
    return servicios if servicios is not None else Servicios()


__all__ = ["Repositorio", "RepositorioAusente", "Servicios", "servicios_de"]
