"""Contratos C28 y C29 (`ADR-015` §4): de donde sale el `Principal`, y por que eso es lo importante.

Todo el aislamiento por tenant y toda la matriz de capacidades descansan en que el `Principal` sea
verdadero. `api.permisos.Principal(usuario_id, perfiles, tenant_id)` es un objeto que construye quien
llama: en proceso, quien llama somos nosotros; por red, cualquiera. Un fallo del stack se nota; un
principal mal construido **no se nota**, porque sirve datos de otro tenant con toda naturalidad y el log
registra una accion legitima de un usuario legitimo.

De ahi las tres piezas de este modulo:

- **`Autenticador`** (C28): el puerto. `principal(peticion) -> Principal`, y **nunca** devuelve `None` ni
  un principal anonimo: o hay principal, o levanta `ErrorAutenticacion`. Un principal «vacio» es la forma
  en que se cuelan las peticiones sin autenticar. El servidor no sabe como se autentica: recibe el puerto
  construido y lo usa. Quien lo implemente de verdad (OIDC del cliente, y sobre todo el mapeo de sus
  grupos a los ocho perfiles) es una decision que espera a tener cliente delante.
- **`AutenticadorAusente`**: el valor por defecto del servidor, con el mismo patron que
  `api.servicios.RepositorioAusente`. **Deniega todo** citando el ADR. Por defecto el sistema no autentica
  a nadie, en vez de autenticar a cualquiera.
- **`AutenticadorDeDesarrollo`** (C29): lee el principal de una cabecera para poder abrir las pantallas
  contra datos de prueba. Es **exactamente la pieza que, olvidada en produccion, regala el sistema
  entero**, asi que se niega a existir fuera de local: falla al construirse sin una senal explicita (que
  no es un valor por defecto), falla si se le da un anfitrion que no es el bucle local, deniega la
  peticion que no venga del bucle local, y **lo dice en `avisos` de cada respuesta**. Hay tests de que no
  se instancia sin la senal y de que ninguna ruta de arranque la elige sola.

`avisos` es parte del puerto y no un extra del de desarrollo: es lo que obliga a que una autenticacion
que no es de verdad lo diga en la pantalla, en vez de parecer una sesion normal.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol

from api.permisos import ErrorApi, ErrorPermiso, Principal

#: La senal de que esto es desarrollo. **No es un valor por defecto de nada**: hay que escribirla, y por
#: eso dice lo que se esta aceptando. Un booleano `desarrollo=True` se pone sin leerlo; esto no.
CONFIRMACION_DESARROLLO = "acepto-autenticacion-de-desarrollo-sin-datos-reales"

#: Las unicas direcciones en las que el autenticador de desarrollo admite estar escuchando.
ANFITRIONES_LOCALES = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

#: La cabecera de la que el autenticador de desarrollo lee el principal. Se llama asi, y no
#: `authorization`, para que nadie la confunda con una credencial: no lo es, y no comprueba nada.
CABECERA_PRINCIPAL = "x-cae-principal-desarrollo"

#: Lo que va en `avisos` de **todas** las respuestas servidas con autenticacion de desarrollo.
AVISO_DESARROLLO = (
    f"autenticacion de desarrollo: el principal lo declara la cabecera {CABECERA_PRINCIPAL!r} y el "
    "servidor no comprueba ninguna credencial. Cualquiera que alcance este puerto es quien diga ser "
    "(`ADR-015` C29); solo vale contra datos sinteticos"
)


class ErrorAutenticacion(ErrorPermiso):
    """No se puede establecer quien pide. Es una denegacion, y se traduce como tal en el sobre.

    Hereda de `ErrorPermiso` a proposito: el sobre de `front/compartido/api/transporte.ts` declara dos
    salidas, `403 {error: "permiso"}` y todo lo demas como `{error: "api"}`. Separar "no se quien eres"
    de "no puedes" en un tercer codigo de estado seria inventar un caso que el contrato no tiene, y el
    cliente lo pintaria como un fallo de la aplicacion en vez de como lo que es: una negativa.
    """


class ErrorArranque(Exception):
    """El servidor no se puede componer asi. Es un error de arranque del proceso, no de una peticion."""


class Autenticador(Protocol):
    """Contrato C28. Lo implementa quien sepa autenticar; el servidor solo lo usa."""

    #: Lo que hay que decir en **cada** respuesta servida con este autenticador. Vacio si no hay nada
    #: que advertir. No es decorativo: es lo que impide que una autenticacion de mentira pase por buena.
    avisos: tuple[str, ...]

    def principal(self, peticion: object) -> Principal:
        """El principal de esta peticion, o `ErrorAutenticacion` si no se puede establecer.

        **Nunca `None` y nunca un principal anonimo.** Devolver un principal «vacio» convierte cada
        peticion sin autenticar en una peticion autenticada como nadie, que es justo lo que autoriza sin
        querer: `Principal` exige al menos un perfil, y a partir de ahi la matriz concede.
        """
        ...


class AutenticadorAusente:
    """El autenticador por defecto del servidor: **deniega todo** y dice por que (C28, `ADR-015` §4)."""

    avisos: tuple[str, ...] = ()

    _MOTIVO = (
        "no hay autenticador configurado: este servidor no autentica a nadie por defecto, en vez de "
        "autenticar a cualquiera. Se pasa uno en `crear_app(autenticador=...)`; el proveedor de "
        "identidad real y el mapeo de sus grupos a los ocho perfiles es la decision que espera cliente "
        "(`ADR-015` §4, C28)"
    )

    def principal(self, peticion: object) -> Principal:
        raise ErrorAutenticacion(self._MOTIVO)


class AutenticadorDeDesarrollo:
    """C29: el principal lo declara una cabecera. Se niega a existir fuera del bucle local.

    Existe para una sola cosa: abrir las pantallas de `FR1` contra los casos sinteticos en el portatil de
    alguien. No comprueba ninguna credencial, asi que en cuanto escucha en una direccion alcanzable
    equivale a no tener control de acceso ninguno.
    """

    def __init__(self, *, confirmacion: str, anfitrion: str) -> None:
        if confirmacion != CONFIRMACION_DESARROLLO:
            raise ErrorArranque(
                "el autenticador de desarrollo no se construye sin decir explicitamente que esto es "
                f"desarrollo: `confirmacion={CONFIRMACION_DESARROLLO!r}`. No hay valor por defecto, y no "
                "lo hay a proposito: es la pieza que, olvidada en produccion, regala el sistema entero "
                "(`ADR-015` C29)"
            )
        direccion = str(anfitrion).strip().lower()
        if direccion not in ANFITRIONES_LOCALES:
            raise ErrorArranque(
                f"el autenticador de desarrollo solo sirve en el bucle local y se le ha dado "
                f"{anfitrion!r}. Lo que admite: {sorted(ANFITRIONES_LOCALES)}. Un servidor que lee el "
                "principal de una cabecera y escucha en una direccion alcanzable no tiene control de "
                "acceso: lo tiene quien llegue antes"
            )
        self.anfitrion = direccion
        self.avisos: tuple[str, ...] = (AVISO_DESARROLLO,)

    def principal(self, peticion: object) -> Principal:
        """El principal que declara la cabecera. Ni `None` ni anonimo: o esta bien escrito, o se deniega."""
        self._exigir_cliente_local(peticion)
        crudo = self._cabecera(peticion)
        if crudo is None or not crudo.strip():
            raise ErrorAutenticacion(
                f"esta peticion no dice quien la hace: falta la cabecera {CABECERA_PRINCIPAL!r} con "
                '{"usuario_id": ..., "perfiles": [...], "tenant_id": ...}. Sin principal no se atiende '
                "nada (`ADR-015` C28)"
            )
        try:
            declarado = json.loads(crudo)
        except ValueError as exc:
            raise ErrorAutenticacion(f"la cabecera {CABECERA_PRINCIPAL!r} no es JSON valido: {exc}") from exc
        if not isinstance(declarado, Mapping):
            raise ErrorAutenticacion(
                f"la cabecera {CABECERA_PRINCIPAL!r} tiene que ser un objeto con `usuario_id`, "
                f"`perfiles` y `tenant_id`; ha llegado {type(declarado).__name__}"
            )
        perfiles = declarado.get("perfiles")
        if not isinstance(perfiles, list) or not all(isinstance(p, str) for p in perfiles):
            raise ErrorAutenticacion(
                f"la cabecera {CABECERA_PRINCIPAL!r} tiene que traer `perfiles` como lista de codigos de "
                "perfil de la matriz"
            )
        tenant = declarado.get("tenant_id")
        if tenant is not None and not isinstance(tenant, str):
            raise ErrorAutenticacion(
                f"la cabecera {CABECERA_PRINCIPAL!r} trae un `tenant_id` que no es texto: {tenant!r}"
            )
        try:
            # `Principal` valida lo suyo (usuario, perfiles no vacios, sin repetir) y los perfiles se
            # contrastan contra la matriz al usarse, en `api.permisos`. Aqui no se valida por segunda vez.
            return Principal(
                usuario_id=str(declarado.get("usuario_id") or ""),
                perfiles=tuple(perfiles),
                tenant_id=tenant,
            )
        except ErrorApi as exc:
            raise ErrorAutenticacion(
                f"la cabecera {CABECERA_PRINCIPAL!r} no describe un principal: {exc}"
            ) from exc

    @staticmethod
    def _cabecera(peticion: object) -> str | None:
        cabeceras = getattr(peticion, "headers", None)
        return None if cabeceras is None else cabeceras.get(CABECERA_PRINCIPAL)

    @staticmethod
    def _exigir_cliente_local(peticion: object) -> None:
        """Segunda barrera: aunque alguien lo haya montado detras de algo, solo atiende al bucle local."""
        cliente = getattr(peticion, "client", None)
        origen = getattr(cliente, "host", None)
        if origen is not None and str(origen) not in ANFITRIONES_LOCALES:
            raise ErrorAutenticacion(
                f"la autenticacion de desarrollo solo atiende al bucle local y esta peticion viene de "
                f"{origen!r}. Aqui el principal lo declara quien pregunta: fuera de local eso no es "
                "autenticacion (`ADR-015` C29)"
            )


__all__ = [
    "ANFITRIONES_LOCALES",
    "AVISO_DESARROLLO",
    "CABECERA_PRINCIPAL",
    "CONFIRMACION_DESARROLLO",
    "Autenticador",
    "AutenticadorAusente",
    "AutenticadorDeDesarrollo",
    "ErrorArranque",
    "ErrorAutenticacion",
]
