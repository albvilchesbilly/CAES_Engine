"""Repositorio en memoria: el `Repositorio` de `api/servicios.py` sin persistencia (desarrollo y pruebas).

Es el equivalente de `salida/simulador/` para el puerto de datos: una implementacion honesta y completa
contra la que se puede probar el contrato entero **hoy**, sin esperar a que S3.1 decida como se guardan las
actuaciones. No guarda en disco, no tiene reloj y no calcula nada: lo que le dan es lo que devuelve.

La huella de un documento (`registrar_documento`) la calcula `engine.ingesta.sha256_bytes` sobre los bytes
del fichero. Ni se acepta del cliente ni se inventa: vinculamos por hash (regla de implementacion de
`CLAUDE.md` §2), y un hash que trae quien sube el fichero no vincula nada.
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
        self._registro(actuacion_id)
        fichero = Path(ruta)
        if not fichero.is_file():
            raise ErrorApi(f"no encuentro el fichero {ruta!r} que se quiere registrar")
        datos = fichero.read_bytes()
        return {"nombre": fichero.name, "sha256": sha256_bytes(datos), "bytes": len(datos)}


__all__ = ["Registro", "RepositorioMemoria"]
