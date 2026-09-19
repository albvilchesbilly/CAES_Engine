"""Repositorio en memoria: el `Repositorio` de `api/servicios.py` sin persistencia (desarrollo y pruebas).

Es el equivalente de `salida/simulador/` para el puerto de datos: una implementacion honesta y completa
contra la que se puede probar el contrato entero **hoy**, sin esperar a que S3.1 decida como se guardan las
actuaciones. No guarda en disco, no tiene reloj y no calcula nada: lo que le dan es lo que devuelve.

La huella de un documento (`registrar_documento`) la calcula `engine.ingesta.sha256_bytes` sobre los bytes
del fichero. Ni se acepta del cliente ni se inventa: vinculamos por hash (regla de implementacion de
`CLAUDE.md` §2), y un hash que trae quien sube el fichero no vincula nada.

Lo mismo al reves (`ADR-012` §1): los bytes se piden **por huella** (`bytes_de_documento`), y quien sabe
donde estan es este objeto. La ruta se apunta al registrar el fichero y no vuelve a salir; asi no hay
ninguna via por la que una peticion pueda elegir que fichero del servidor se lee.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from api.permisos import ErrorApi
from engine.capacidades import autorizador
from engine.eventos.log import LogEventos
from engine.ingesta import sha256_bytes


@dataclass
class Registro:
    """Todo lo que se sabe de una actuacion fuera del nucleo: de quien es y quien es parte en ella."""

    tenant_id: str
    actuacion: object | None = None
    log: LogEventos | None = None
    partes: tuple[str, ...] = ()
    requerimientos: dict[str, tuple[object, object]] = field(default_factory=dict)
    #: Huella → donde estan los bytes. Lo rellena el repositorio al registrar un documento; **nunca** lo
    #: rellena una peticion. Es lo que permite pedir un documento por huella y no por ruta.
    rutas: dict[str, Path] = field(default_factory=dict)
    #: Huella → los bytes, cuando se guardan en memoria en vez de en disco (desarrollo y pruebas).
    contenidos: dict[str, bytes] = field(default_factory=dict)


class RepositorioMemoria:
    """Implementacion en memoria del puerto de datos. Orden estable: el de insercion."""

    def __init__(self) -> None:
        self._registros: dict[str, Registro] = {}
        # A8: los logs que nacen aqui llevan puesto el control de perfiles de la matriz. Se instala en la
        # composicion, no en el nucleo: el log no conoce ningun perfil, solo pregunta.
        self._autorizador = autorizador()

    def log_nuevo(self, actuacion_id: str) -> LogEventos:
        """Un log vacio con el autorizador de la matriz puesto."""
        return LogEventos(actuacion_id, autorizador=self._autorizador)

    # -- alta y carga ----------------------------------------------------------------------------

    def anadir(
        self,
        actuacion_id: str,
        tenant_id: str,
        *,
        actuacion: object | None = None,
        log: LogEventos | None = None,
        partes: tuple[str, ...] = (),
    ) -> Registro:
        """Mete una actuacion ya conocida. Lo usan las pruebas y el arranque de desarrollo."""
        if not str(actuacion_id).strip():
            raise ErrorApi("una actuacion necesita identificador")
        registro = Registro(
            tenant_id=tenant_id,
            actuacion=actuacion,
            log=log if log is not None else self.log_nuevo(actuacion_id),
            partes=tuple(partes),
        )
        self._registros[actuacion_id] = registro
        return registro

    def anadir_requerimiento(
        self, actuacion_id: str, requerimiento_id: str, requerimiento: object, interpretacion: object
    ) -> None:
        """Deja un requerimiento con la interpretacion **propuesta** por un agente, sin confirmar."""
        self._registro(actuacion_id).requerimientos[requerimiento_id] = (requerimiento, interpretacion)

    def _registro(self, actuacion_id: str) -> Registro:
        registro = self._registros.get(actuacion_id)
        if registro is None:
            raise ErrorApi(f"la actuacion {actuacion_id!r} no existe en el repositorio")
        return registro

    # -- el puerto -------------------------------------------------------------------------------

    def actuacion(self, actuacion_id: str) -> object | None:
        return self._registro(actuacion_id).actuacion

    def log(self, actuacion_id: str) -> LogEventos | None:
        return self._registro(actuacion_id).log

    def abrir(self, actuacion_id: str, tenant_id: str) -> LogEventos:
        if actuacion_id in self._registros:
            raise ErrorApi(f"la actuacion {actuacion_id!r} ya existe: abrirla dos veces duplicaria el log")
        nuevo = self.log_nuevo(actuacion_id)
        self.anadir(actuacion_id, tenant_id, log=nuevo)
        return nuevo

    def tenant_de(self, actuacion_id: str) -> str | None:
        registro = self._registros.get(actuacion_id)
        return None if registro is None else registro.tenant_id

    def partes_de(self, actuacion_id: str) -> tuple[str, ...]:
        return self._registro(actuacion_id).partes

    def actuaciones_de(self, tenant_id: str) -> tuple[str, ...]:
        return tuple(i for i, r in self._registros.items() if r.tenant_id == tenant_id)

    def todas(self) -> tuple[str, ...]:
        return tuple(self._registros)

    def requerimiento(self, actuacion_id: str, requerimiento_id: str) -> tuple[object, object] | None:
        return self._registro(actuacion_id).requerimientos.get(requerimiento_id)

    def registrar_documento(self, actuacion_id: str, ruta: str) -> Mapping[str, object]:
        registro = self._registro(actuacion_id)
        fichero = Path(ruta)
        if not fichero.is_file():
            raise ErrorApi(f"no encuentro el fichero {ruta!r} que se quiere registrar")
        datos = fichero.read_bytes()
        huella = sha256_bytes(datos)
        # Se apunta donde quedo, indexado **por su huella**: es la unica forma de que luego se pueda pedir
        # por huella. La ruta entra aqui, al registrar, y no vuelve a salir de este objeto.
        registro.rutas[huella] = fichero
        return {"nombre": fichero.name, "sha256": huella, "bytes": len(datos)}

    def guardar_documento(self, actuacion_id: str, contenido: bytes) -> str:
        """Guarda unos bytes en memoria y devuelve su huella, calculada aqui sobre el contenido."""
        registro = self._registro(actuacion_id)
        huella = sha256_bytes(contenido)
        registro.contenidos[huella] = bytes(contenido)
        return huella

    def bytes_de_documento(self, actuacion_id: str, sha256: str) -> bytes | None:
        """Los bytes de esa huella **dentro de esa actuacion**, o `None`. Nunca resuelve una ruta ajena.

        Tres sitios donde mirar, todos del lado del servidor: lo guardado en memoria, lo registrado por
        `registrar_documento` y, por ultimo, la carpeta que ingesto el nucleo (`Documento.ruta`). Lo que
        no hay es una cuarta via en la que la ruta la ponga quien pregunta.
        """
        registro = self._registro(actuacion_id)
        contenido = registro.contenidos.get(sha256)
        if contenido is not None:
            return contenido
        ruta = registro.rutas.get(sha256) or self._ruta_ingestada(registro, sha256)
        if ruta is None or not ruta.is_file():
            return None
        return ruta.read_bytes()

    @staticmethod
    def _ruta_ingestada(registro: Registro, sha256: str) -> Path | None:
        """La ruta que la ingesta adjudico a esa huella en esta actuacion, si la actuacion esta cargada."""
        for documento in getattr(registro.actuacion, "documentos", ()) or ():
            if str(getattr(documento, "sha256", "")) != sha256:
                continue
            ruta = getattr(documento, "ruta", None)
            if ruta is not None:
                return Path(ruta)
        return None


__all__ = ["Registro", "RepositorioMemoria"]
