"""Simulador de la plataforma oficial (S5, contrato C7 de `ADR-009` §5).

Reproduce **solo lo publicado** (presentacion OMIE/MIBGAS 30/06/2026, `docs/02` §5 y §6.1): los estados de
actuacion de la fase 1, la validacion de esquema, el manifiesto de ficheros con hash, la firma humana y las
tareas pendientes. Todo lo demas es un hueco enumerado, nunca una suposicion.
# TODO(API-01): endpoints, autenticacion, peticiones y respuestas reales; ver docs/HUECOS.md

Existe para que P8 y P9 se puedan escribir **sin sandbox**: contra este adaptador hoy y contra el conector
real (S3.7) cuando haya diccionario, sin reescribir nada aguas arriba.

Las ocho reglas de `ADR-009` §5, y donde viven en este modulo:

1. **Ni un literal de plataforma en este fichero.** Los estados salen de `engine.estados.tabla_plataforma()`
   (`engine/estados_plataforma.yaml`). Este modulo los **deriva por sus atributos**, nunca por su nombre:
   `estado_creacion()`, `estado_validado()` y `estado_firmado()` son las filas que la tabla marca
   `inicial`, `validacion_automatica` y `exige_firma`. Son marcas explicitas a proposito: derivarlas del
   **orden** de las filas haria que reordenar el YAML cambiara el comportamiento en silencio, y la tabla
   garantiza al cargar que hay exactamente una de cada. Si el diccionario renombra manana cualquiera de
   ellos, cambia el YAML y este fichero no se toca (`docs/03` §7.1). Hay un test que recorre este fuente y
   lo comprueba.
2. **La firma es lo unico que abre el paso al estado que `exige_firma`**, y exige dos cosas a la vez: un
   `FirmaRegistrada` (o un `Actor`) de clase `humano` **y** credencial de perfil `Firma`. Un actor `motor`,
   `agente` o `plataforma` es `ErrorSimulador` (`docs/02` §5.6, `CLAUDE.md` §2). **El simulador no firma**:
   comprueba que alguien firmo. Ningun componente nuestro firma actos administrativos.
3. **La automatizacion termina en el estado validado** (`docs/02` §6.2). El simulador nunca avanza solo mas
   alla: lo que viene despues lo mueve `avanzar()`, que es el verificador, el GA o la CN, no nosotros.
4. **Validacion**: esquema del modelo canonico con `engine.modelo.validar` — **es el nuestro**; el esquema
   oficial de la plataforma no esta publicado (TODO(API-01): ver docs/HUECOS.md) —, recalculo del
   `hash_manifiesto` e integridad del manifiesto contra la carpeta entregada
   (`salida.constructor.verificar`). Un paquete con un hash alterado se rechaza **nombrando el fichero**.
5. **Permisos por perfil** (`docs/02` §2.2, confirmados): `Consulta` ni crea ni firma; `Modificacion` crea y
   carga pero no firma; `Firma` todo. Si el usuario de `Modificacion` puede ser ajeno al agente y desde que
   infraestructura opera su certificado es TODO(API-09): este modulo **no lo modela**, solo mira el perfil.
6. **Los estados de fases 2-4 se sirven con `oficial: False`** tal y como los marca la tabla: son nombres
   nuestros y ningun test afirma que la plataforma devuelva esos literales.
   # TODO(API-03): ver docs/HUECOS.md
7. **No se inventan identificadores de la plataforma.** La `referencia` se deriva del
   `codigo_identificativo_propio` y del `hash_paquete` y lleva delante `PREFIJO_REFERENCIA` para que se vea
   que es NUESTRA. Como son las referencias oficiales es parte de TODO(API-01).
8. **Transiciones**: se acepta lo que la presentacion enumera y se rechaza un literal que la tabla no
   conoce. Las transiciones exactas entre los 8 estados son `NO DOCUMENTADO` (`docs/02` §5.1), asi que aqui
   solo se exige lo que esta escrito (la firma antes del estado que la exige, y la validacion antes de la
   firma) y el resto se registra **sin inventar un grafo que nadie ha publicado**.

Determinismo: reloj inyectable (`instante=` fijo o `reloj=` invocable), sin identificadores aleatorios y
sin reloj escondido. Dos corridas con el mismo instante dan el mismo acuse byte a byte, referencia
incluida.

`salida/` importa de `engine/`; `engine/` nunca de `salida/`. Nada de `eval`, `exec`, `compile` ni `float`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

from engine.estados import ProyeccionPlataforma, tabla_plataforma
from engine.eventos import (
    Actor,
    ErrorEvento,
    Evento,
    LogEventos,
    ahora_utc,
    normalizar_instante,
    texto_instante,
)
from engine.modelo import ActuacionCanonica, ErrorModelo
from engine.modelo import validar as validar_modelo
from salida.constructor import verificar
from salida.constructor.manifiesto import ErrorManifiesto, hash_de_manifiesto
from salida.puerto import (
    NIVELES,
    Acuse,
    ErrorSalida,
    EstadoPlataforma,
    Paquete,
    TareaPendiente,
)


class ErrorSimulador(ErrorSalida):
    """La plataforma simulada se niega: falta credencial, falta un paso previo o el literal no existe."""


#: Nombre de este adaptador (`PuertoSalida.nombre`).
NOMBRE = "simulador"

#: Via de entrega de sus acuses (`salida.puerto.VIAS`). Es NUESTRA: no se escribe nunca en un evento de
#: entrega del log, porque el simulador no entrega a nadie real.
VIA_SIMULADOR = "simulador"

#: Marca de que la referencia es nuestra, no de la plataforma (regla 7).
#: TODO(API-01): ver docs/HUECOS.md
PREFIJO_REFERENCIA = "SIM"

#: Cuantos caracteres del `hash_paquete` entran en la referencia: suficientes para distinguir paquetes de
#: una misma actuacion sin convertir la referencia en un hash ilegible.
LONGITUD_HUELLA_REFERENCIA = 12

#: Perfiles de usuario dentro de un agente (`docs/02` §2.2, **confirmados**). No son estados: son quien
#: puede hacer que, y el simulador no modela de quien es la infraestructura (TODO(API-09)).
PERFIL_FIRMA = "Firma"
PERFIL_MODIFICACION = "Modificacion"
PERFIL_CONSULTA = "Consulta"
PERFILES = (PERFIL_FIRMA, PERFIL_MODIFICACION, PERFIL_CONSULTA)

#: Perfiles que pueden crear y cargar (`docs/02` §2.2). `Consulta` no esta.
PERFILES_QUE_CARGAN = (PERFIL_FIRMA, PERFIL_MODIFICACION)

#: Nivel de los estados de actuacion en la tabla (`salida.puerto.NIVELES`); no es un literal de estado.
NIVEL_ACTUACION = NIVELES[0]

#: Tipos del catalogo cerrado (`engine.eventos.catalogo`) que este adaptador lee o escribe. Son **nuestros**
#: nombres de evento, no campos de la API.
TIPO_FIRMA = "FirmaRegistrada"
TIPO_DESISTIMIENTO = "DesistimientoRegistrado"
TIPO_ESTADO_RECIBIDO = "EstadoPlataformaRecibido"
TIPO_TAREA_RECIBIDA = "TareaPendienteRecibida"

#: Clases de actor (`engine.eventos.catalogo.CLASES_ACTOR`) que usa este modulo.
CLASE_HUMANO = "humano"
CLASE_PLATAFORMA = "plataforma"


# ---------------------------------------------------------------------------
# Regla 1: los estados se derivan de la tabla por sus atributos, nunca por su nombre
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def filas_de_actuacion() -> tuple[ProyeccionPlataforma, ...]:
    """Los estados de nivel actuacion (fase 1, los confirmados), en el orden de la tabla."""
    filas = tuple(f for f in tabla_plataforma().values() if f.nivel == NIVEL_ACTUACION)
    if not filas:
        raise ErrorSimulador(
            "la tabla de estados de plataforma no declara ningun estado de nivel "
            f"{NIVEL_ACTUACION!r}: sin ellos el simulador no tiene nada que reproducir"
        )
    return filas


def estado_creacion() -> ProyeccionPlataforma:
    """El estado en el que nace una actuacion en la plataforma: la fila marcada `inicial` (regla 1)."""
    return _unica("inicial")


def estado_validado() -> ProyeccionPlataforma:
    """El estado tras la validacion automatica. **Aqui termina la automatizacion** (regla 3).

    Es la fila marcada `validacion_automatica`, no "la segunda de la tabla": la marca es explicita para que
    reordenar `estados_plataforma.yaml` no cambie el comportamiento del simulador en silencio.
    """
    return _unica("validacion_automatica")


def estado_firmado() -> ProyeccionPlataforma:
    """El estado al que solo se llega firmando: la fila marcada `exige_firma` (regla 2)."""
    return _unica("exige_firma")


def _unica(marca: str) -> ProyeccionPlataforma:
    """La fila de nivel actuacion que declara esa marca.

    `engine.estados.tabla_plataforma` ya garantiza **al cargar** que hay exactamente una de cada y que es de
    nivel actuacion, asi que aqui no se repite la comprobacion: se traduce el fallo a `ErrorSimulador` por si
    alguien llama con una tabla propia.
    """
    marcadas = [f for f in filas_de_actuacion() if getattr(f, marca, False)]
    if len(marcadas) != 1:
        raise ErrorSimulador(
            f"la tabla de estados de plataforma debe declarar exactamente una fila de nivel "
            f"{NIVEL_ACTUACION!r} con `{marca}` (`docs/02` §5.1) y declara {len(marcadas)}"
        )
    return marcadas[0]


# ---------------------------------------------------------------------------
# Credencial
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Credencial:
    """Un usuario del agente en la plataforma simulada (`docs/02` §2.2).

    No hay aqui certificado ninguno: el simulador mira **el perfil** y nada mas. Donde vive el certificado
    de usuario y quien puede tenerlo es TODO(API-09): ver docs/HUECOS.md.
    """

    usuario_id: str
    perfil: str
    tenant_id: str

    def __post_init__(self) -> None:
        if self.perfil not in PERFILES:
            raise ErrorSimulador(f"perfil desconocido: {self.perfil!r}; los de `docs/02` §2.2 son {PERFILES}")
        for campo, valor in (("usuario_id", self.usuario_id), ("tenant_id", self.tenant_id)):
            if not isinstance(valor, str) or not valor.strip():
                raise ErrorSimulador(f"la credencial necesita `{campo}` no vacio")

    @property
    def puede_cargar(self) -> bool:
        """Crear el paquete y cargar adjuntos: `Firma` y `Modificacion`, nunca `Consulta`."""
        return self.perfil in PERFILES_QUE_CARGAN

    @property
    def puede_firmar(self) -> bool:
        """Solo el perfil `Firma`. Y aun asi la firma la hace una persona, no el simulador (regla 2)."""
        return self.perfil == PERFIL_FIRMA

    def a_dict(self) -> dict[str, str]:
        return {"usuario_id": self.usuario_id, "perfil": self.perfil, "tenant_id": self.tenant_id}


# ---------------------------------------------------------------------------
# Estado interno: que sabe el simulador de cada referencia
# ---------------------------------------------------------------------------


@dataclass
class _Registro:
    """Lo que la plataforma simulada guarda de una referencia.

    Privado: desde fuera solo se ve por los tipos del puerto (`Acuse`, `EstadoPlataforma`, `TareaPendiente`).
    """

    referencia: str
    paquete: Paquete
    tenant_id: str
    fila: ProyeccionPlataforma
    canonica: ActuacionCanonica | None = None
    firmada: bool = False
    motivos: tuple[str, ...] = ()
    historia: list[EstadoPlataforma] = field(default_factory=list)
    tareas: list[TareaPendiente] = field(default_factory=list)

    @property
    def validado(self) -> bool:
        return self.fila.literal == estado_validado().literal


def referencia_de(paquete: Paquete) -> str:
    """La referencia **nuestra** de un paquete: codigo propio + huella del paquete (regla 7).

    Determinista por construccion: el mismo paquete da siempre la misma referencia, y dos paquetes
    distintos de la misma actuacion se distinguen por la huella.
    # TODO(API-01): las referencias oficiales de la plataforma; ver docs/HUECOS.md
    """
    if not isinstance(paquete, Paquete):
        raise ErrorSimulador(f"se esperaba un Paquete y llego {type(paquete).__name__}")
    huella = paquete.hash_paquete[:LONGITUD_HUELLA_REFERENCIA]
    return f"{PREFIJO_REFERENCIA}-{paquete.codigo_identificativo_propio}-{huella}"


# ---------------------------------------------------------------------------
# El simulador
# ---------------------------------------------------------------------------


class Simulador:
    """La plataforma simulada. Implementa `PuertoSalida` y se niega a lo que no le toca.

    Uso tipico en un test o en desarrollo de P9:

        simulador = Simulador(instante=datetime(2026, 9, 19, 10, 40, tzinfo=UTC))
        acuse = simulador.entregar(paquete, credencial=credencial, canonica=canonica)
        simulador.registrar_firma(acuse.referencia, Actor("humano", "responsable"), credencial=credencial)
        estado = simulador.avanzar(acuse.referencia, literal)      # verificador / GA / CN
        simulador.eventos_en(log, acuse.referencia)                # P9, actor de clase plataforma
    """

    nombre = NOMBRE

    def __init__(
        self,
        *,
        instante: datetime | None = None,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        """`instante` congela el reloj (lo determinista); `reloj` inyecta uno propio. Nunca los dos."""
        if instante is not None and reloj is not None:
            raise ErrorSimulador("se inyecta `instante` (fijo) o `reloj` (invocable), no los dos a la vez")
        if instante is not None:
            fijo = self._instante(instante)
            self._reloj: Callable[[], datetime] = lambda: fijo
        else:
            # Sin inyeccion, el mismo reloj UTC del resto del repositorio (`engine.eventos.ahora_utc`, que
            # exige zona). Para comparar dos corridas byte a byte hay que pasar `instante`: aqui no hay
            # ningun reloj escondido, y no se mira mas que por esta linea.
            self._reloj = reloj or ahora_utc
        self._registros: dict[str, _Registro] = {}

    # -- utilidades internas ---------------------------------------------------------------------

    @staticmethod
    def _instante(valor: datetime) -> datetime:
        try:
            return normalizar_instante(valor)
        except ErrorEvento as exc:  # un `datetime` sin zona: nunca se acepta
            raise ErrorSimulador(f"instante invalido: {exc}") from exc

    def _ahora(self) -> datetime:
        return self._instante(self._reloj())

    def _registro(self, referencia: str) -> _Registro:
        registro = self._registros.get(str(referencia))
        if registro is None:
            raise ErrorSimulador(
                f"la plataforma simulada no conoce la referencia {referencia!r}: no se ha creado el paquete"
            )
        return registro

    def _anotar(
        self,
        registro: _Registro,
        fila: ProyeccionPlataforma,
        instante: datetime,
        motivos: Sequence[str] = (),
    ) -> EstadoPlataforma:
        """Mueve la referencia a `fila` y lo apunta en su historia (lo que despues lee `eventos_en`)."""
        registro.fila = fila
        registro.motivos = tuple(motivos)
        estado = EstadoPlataforma(
            referencia=registro.referencia,
            literal=fila.literal,
            nivel=fila.nivel,
            oficial=fila.oficial,  # regla 6: los de fases 2-4 salen en False, tal cual los marca la tabla
            instante=instante,
            motivos=tuple(motivos),
        )
        registro.historia.append(estado)
        return estado

    def _acuse(
        self,
        registro: _Registro,
        instante: datetime,
        *,
        aceptado: bool,
        motivos: Sequence[str] = (),
        detalle: Mapping[str, object] | None = None,
    ) -> Acuse:
        return Acuse(
            referencia=registro.referencia,
            via=VIA_SIMULADOR,
            instante=instante,
            aceptado=aceptado,
            hash_paquete=registro.paquete.hash_paquete,
            estado_plataforma=registro.fila.literal,
            motivos=tuple(motivos),
            detalle=dict(detalle or {}),
        )

    # -- operaciones del puerto que este adaptador no hace ---------------------------------------

    def construir(
        self,
        actuacion: object,
        mapeo: object,
        *,
        raiz: object | None = None,
        log: object | None = None,
    ) -> Paquete:
        """Se niega: construir es del mapeo declarativo (`salida/mapeo.py`), no de la plataforma.

        `ADR-009` §2 punto 4: una operacion se niega diciendolo, nunca con un vacio ambiguo.
        """
        raise ErrorSalida(
            "el simulador no construye paquetes: eso lo hace el mapeo declarativo (`salida/mapeo.py`, "
            "`ADR-009` §3). El simulador recibe el paquete ya construido"
        )

    # -- fase 1A: crear y validar ----------------------------------------------------------------

    def crear_borrador(
        self,
        paquete: Paquete,
        credencial: Credencial,
        *,
        canonica: ActuacionCanonica | None = None,
    ) -> Acuse:
        """Registra el paquete y lo deja en el estado de creacion. No valida nada todavia (regla 8).

        `canonica` es el modelo canonico del que salio el paquete: la validacion de esquema lo necesita y
        el paquete no lo lleva (el payload es el del mapeo, no el modelo). Sin el, `validar` no puede
        demostrar el esquema y lo dice; declarado no es demostrado.

        Idempotente por contenido: crear dos veces el mismo paquete devuelve el mismo acuse.
        """
        if not isinstance(paquete, Paquete):
            raise ErrorSimulador(f"se esperaba un Paquete y llego {type(paquete).__name__}")
        credencial = self._credencial(credencial)
        if not credencial.puede_cargar:
            raise ErrorSimulador(
                f"el perfil {credencial.perfil!r} no crea ni carga paquetes (`docs/02` §2.2); "
                f"lo hacen {PERFILES_QUE_CARGAN}"
            )
        if canonica is not None and not isinstance(canonica, ActuacionCanonica):
            raise ErrorSimulador(f"`canonica` debe ser una ActuacionCanonica, no {type(canonica).__name__}")

        instante = self._ahora()
        referencia = referencia_de(paquete)
        existente = self._registros.get(referencia)
        if existente is not None:
            if existente.firmada:
                raise ErrorSimulador(
                    f"{referencia}: la actuacion esta firmada y no se vuelve a cargar "
                    "(inalterabilidad, `docs/02` §5.4)"
                )
            return self._acuse(existente, instante, aceptado=True, detalle={"idempotente": True})

        registro = _Registro(
            referencia=referencia,
            paquete=paquete,
            tenant_id=credencial.tenant_id,
            fila=estado_creacion(),
            canonica=canonica,
        )
        self._registros[referencia] = registro
        self._anotar(registro, estado_creacion(), instante)
        return self._acuse(
            registro,
            instante,
            aceptado=True,
            detalle={"usuario_id": credencial.usuario_id, "perfil": credencial.perfil},
        )

    def validar(self, referencia: str) -> Acuse:
        """La validacion automatica de la plataforma, con **lo unico que la presentacion documenta**.

        Tres comprobaciones (regla 4):

        1. **Esquema del modelo canonico**, con `engine.modelo.validar`. Es **EL NUESTRO**: el esquema
           oficial de la plataforma no esta publicado. TODO(API-01): ver docs/HUECOS.md.
        2. **Recalculo del `hash_manifiesto`**: si el manifiesto se altero despues de sellarse, no cuadra.
        3. **Integridad del manifiesto contra la carpeta** (`salida.constructor.verificar`): un adjunto
           alterado, ausente o sobrante se rechaza **nombrando el fichero**.

        Un rechazo es un `Acuse` con `aceptado=False` y motivos, no una excepcion: la plataforma responde.
        Superarla deja la referencia en el estado validado, y **ahi termina la automatizacion** (regla 3).
        """
        registro = self._registro(referencia)
        instante = self._ahora()
        if registro.firmada:
            raise ErrorSimulador(
                f"{registro.referencia}: la actuacion ya esta firmada; no se revalida "
                "(inalterabilidad, `docs/02` §5.4)"
            )
        motivos = self._motivos_de_validacion(registro)
        if motivos:
            # Un rechazo no mueve el estado: la referencia se queda donde estaba, con sus motivos.
            self._anotar(registro, estado_creacion(), instante, motivos)
            return self._acuse(
                registro,
                instante,
                aceptado=False,
                motivos=motivos,
                detalle={"comprobaciones": "esquema propio, hash del manifiesto e integridad de adjuntos"},
            )
        self._anotar(registro, estado_validado(), instante)
        return self._acuse(registro, instante, aceptado=True)

    def _motivos_de_validacion(self, registro: _Registro) -> tuple[str, ...]:
        """Los motivos de rechazo, en el orden de las tres comprobaciones. Vacio = validacion superada."""
        paquete = registro.paquete
        motivos: list[str] = []

        if registro.canonica is None:
            motivos.append(
                "no se puede comprobar el esquema: no se aporto el modelo canonico de la actuacion "
                "(el simulador no lo reconstruye desde el payload del mapeo)"
            )
        else:
            try:
                validar_modelo(registro.canonica)
            except ErrorModelo as exc:
                motivos.append(f"esquema del modelo canonico (el nuestro, TODO(API-01)): {exc}")

        sellado = hash_de_manifiesto(paquete.manifiesto)
        if sellado != paquete.manifiesto.hash_manifiesto:
            motivos.append(
                f"el manifiesto se altero despues de sellarse: su contenido tiene hash {sellado} y "
                f"declara {paquete.manifiesto.hash_manifiesto}"
            )

        try:
            resultado = verificar(paquete.manifiesto, raiz=paquete.raiz)
        except ErrorManifiesto as exc:
            motivos.append(f"no se puede verificar el paquete en {paquete.raiz}: {exc}")
        else:
            motivos.extend(f"adjunto alterado: {ruta}" for ruta in resultado.alterados)
            motivos.extend(f"adjunto declarado y ausente: {ruta}" for ruta in resultado.ausentes)
            motivos.extend(f"fichero no declarado en el manifiesto: {ruta}" for ruta in resultado.sobrantes)

        return tuple(motivos)

    def entregar(
        self,
        paquete: Paquete,
        *,
        credencial: Credencial | None = None,
        canonica: ActuacionCanonica | None = None,
        log: LogEventos | None = None,
    ) -> Acuse:
        """Crear el paquete y pasarlo por la validacion automatica, en una sola llamada.

        Con `log`, deja en el los eventos P9 de lo que la plataforma dijo (`eventos_en`). **No** escribe
        eventos de entrega: el simulador no entrega a nadie real y su via no es una de `VIAS_ENTREGA`.
        """
        if credencial is None:
            raise ErrorSimulador("la plataforma simulada exige credencial: `entregar(..., credencial=...)`")
        acuse_creacion = self.crear_borrador(paquete, credencial, canonica=canonica)
        registro = self._registro(acuse_creacion.referencia)
        if registro.canonica is None and canonica is not None:
            registro.canonica = canonica
        acuse = self.validar(acuse_creacion.referencia)
        if log is not None:
            self.eventos_en(log, acuse.referencia)
        return acuse

    # -- fase 1A: la firma, que es humana --------------------------------------------------------

    def registrar_firma(
        self,
        referencia: str,
        evento_o_actor: Evento | Actor | Mapping[str, object] | tuple[str, str],
        *,
        credencial: Credencial,
    ) -> Acuse:
        """Comprueba que **alguien firmo** y mueve la referencia al estado que exige firma (regla 2).

        El simulador **no firma**: recibe la prueba de que una persona lo hizo, y la prueba es un evento
        `FirmaRegistrada` del log (que ya exige actor humano) o directamente el `Actor`. Un actor `motor`,
        `agente` o `plataforma` es `ErrorSimulador`: ningun componente nuestro firma actos administrativos
        (`CLAUDE.md` §2, `docs/02` §6.2).

        Ademas, la credencial con la que se opera tiene que ser de perfil `Firma` (`docs/02` §2.2), y la
        actuacion tiene que haber superado antes la validacion automatica (`docs/02` §6.2).
        """
        registro = self._registro(referencia)
        credencial = self._credencial(credencial)
        if not credencial.puede_firmar:
            raise ErrorSimulador(
                f"el perfil {credencial.perfil!r} no firma (`docs/02` §2.2): la firma y el cierre de la "
                f"actuacion son del perfil {PERFIL_FIRMA!r}"
            )
        if not registro.validado:
            raise ErrorSimulador(
                f"{registro.referencia}: la firma llega despues de la validacion automatica "
                f"(`docs/02` §6.2); la referencia esta en {registro.fila.literal!r}"
            )
        actor = self._actor_que_firma(evento_o_actor)
        instante = self._ahora()
        registro.firmada = True
        self._anotar(registro, estado_firmado(), instante)
        return self._acuse(
            registro,
            instante,
            aceptado=True,
            detalle={
                "firmado_por": actor.a_dict(),
                "usuario_id": credencial.usuario_id,
                "perfil": credencial.perfil,
                "nota": "el simulador no firma: registra que una persona firmo",
            },
        )

    @staticmethod
    def _actor_que_firma(evento_o_actor: object) -> Actor:
        """El actor humano que firmo, venga como evento del log o como `Actor` suelto."""
        if isinstance(evento_o_actor, Evento):
            if evento_o_actor.tipo != TIPO_FIRMA:
                raise ErrorSimulador(
                    f"la prueba de la firma es un evento {TIPO_FIRMA}, no {evento_o_actor.tipo!r}"
                )
            actor = evento_o_actor.actor
        else:
            try:
                actor = Actor.de(evento_o_actor)
            except ErrorEvento as exc:
                raise ErrorSimulador(f"no es una prueba de firma: {exc}") from exc
        if actor.clase != CLASE_HUMANO:
            raise ErrorSimulador(
                f"la firma es un acto humano con certificado de representante (`docs/02` §6.2): llego un "
                f"actor de clase {actor.clase!r}. Ningun componente nuestro firma actos administrativos"
            )
        return actor

    # -- fases 1B y siguientes: lo que hacen el verificador, el GA y la CN -----------------------

    def avanzar(
        self,
        referencia: str,
        literal: str,
        *,
        motivos: Sequence[str] = (),
        evidencia: Evento | Actor | Mapping[str, object] | tuple[str, str] | None = None,
    ) -> EstadoPlataforma:
        """Mueve la referencia al literal que diga la tabla: es el verificador, el GA o la CN, no nosotros.

        Un literal que la tabla no conoce se rechaza (regla 8): un estado nuevo es un hueco en
        `docs/HUECOS.md`, no un campo que se inventa aqui. Se exige **solo lo que esta escrito**: la firma
        previa cuando la fila la exige (`docs/02` §5.6) y el desistimiento humano cuando la fila lo exige
        (`docs/02` §5.5). El resto del grafo es `NO DOCUMENTADO` y no se inventa.

        Cuando el literal abre un requerimiento (`origen_subsanacion`), la plataforma simulada crea ademas
        la tarea pendiente correspondiente (`docs/02` §6.1).
        """
        registro = self._registro(referencia)
        fila = tabla_plataforma().get(str(literal))
        if fila is None:
            raise ErrorSimulador(
                f"la tabla de estados de plataforma no conoce el literal {literal!r}: el simulador no "
                "inventa estados (`docs/02` §5.1; un literal nuevo es un hueco en docs/HUECOS.md)"
            )
        if fila.exige_firma and not registro.firmada:
            raise ErrorSimulador(
                f"{fila.literal} exige un {TIPO_FIRMA} previo de actor humano (`docs/02` §5.6); "
                f"{registro.referencia} no esta firmada"
            )
        if fila.exige_desistimiento:
            self._actor_que_desiste(evidencia, fila.literal)
        instante = self._ahora()
        estado = self._anotar(registro, fila, instante, motivos)
        if fila.origen_subsanacion is not None:
            self._abrir_tarea(registro, fila, instante)
        return estado

    @staticmethod
    def _actor_que_desiste(evidencia: object, literal: str) -> Actor:
        """El desistimiento es del sujeto (`docs/02` §5.5): tambien humano, tambien comprobado, no hecho."""
        if evidencia is None:
            raise ErrorSimulador(
                f"{literal} exige un {TIPO_DESISTIMIENTO} de actor humano (`docs/02` §5.5): pasalo en "
                "`evidencia=`; el simulador no desiste por nadie"
            )
        if isinstance(evidencia, Evento):
            if evidencia.tipo != TIPO_DESISTIMIENTO:
                raise ErrorSimulador(
                    f"la prueba del desistimiento es un evento {TIPO_DESISTIMIENTO}, no {evidencia.tipo!r}"
                )
            actor = evidencia.actor
        else:
            try:
                actor = Actor.de(evidencia)
            except ErrorEvento as exc:
                raise ErrorSimulador(f"no es una prueba de desistimiento: {exc}") from exc
        if actor.clase != CLASE_HUMANO:
            raise ErrorSimulador(
                f"{literal} exige un desistimiento de actor humano (`docs/02` §5.5); llego un actor de "
                f"clase {actor.clase!r}"
            )
        return actor

    def _abrir_tarea(
        self, registro: _Registro, fila: ProyeccionPlataforma, instante: datetime
    ) -> TareaPendiente:
        """La tarea pendiente que deja un requerimiento. `vence_en` queda a `None`: TODO(API-10)."""
        tarea = TareaPendiente(
            id=f"{registro.referencia}-T{len(registro.tareas) + 1:02d}",
            tenant_id=registro.tenant_id,
            asunto=f"{fila.literal}: requerimiento de origen {fila.origen_subsanacion}",
            instante=instante,
            referencia=registro.referencia,
            vence_en=None,  # TODO(API-10): la plataforma no publica plazos; ver docs/HUECOS.md
        )
        registro.tareas.append(tarea)
        return tarea

    # -- consulta ---------------------------------------------------------------------------------

    def consultar_estado(self, referencia: str) -> EstadoPlataforma:
        """El ultimo estado que la plataforma simulada tiene de esa referencia."""
        registro = self._registro(referencia)
        if not registro.historia:  # pragma: no cover - crear_borrador siempre anota el primero
            raise ErrorSimulador(f"{registro.referencia}: sin historia de estados")
        return registro.historia[-1]

    def consultar_tareas(self, tenant_id: str) -> tuple[TareaPendiente, ...]:
        """Las tareas pendientes del tenant (`docs/02` §6.1), ordenadas y sin plazos (TODO(API-10))."""
        tareas = [
            tarea
            for registro in self._registros.values()
            if registro.tenant_id == str(tenant_id)
            for tarea in registro.tareas
        ]
        return tuple(sorted(tareas, key=lambda t: (t.instante, t.id)))

    def historia(self, referencia: str) -> tuple[EstadoPlataforma, ...]:
        """Todos los estados por los que paso la referencia, en orden. Es lo que lee `eventos_en`."""
        return tuple(self._registro(referencia).historia)

    # -- P9: lo que la plataforma dijo, como eventos del log --------------------------------------

    def eventos_en(self, log: LogEventos, referencia: str) -> tuple[Evento, ...]:
        """Escribe en el log los eventos P9 de esa referencia, con actor de clase `plataforma`.

        `EstadoPlataformaRecibido` por cada estado de la historia y `TareaPendienteRecibida` por cada tarea
        (`docs/03` §10.5). Es idempotente: lo que ya esta en el log no se repite, porque el log es
        solo-anadir y un estado no se recibe dos veces por consultarlo dos veces.

        Quien decide que le pasa a NUESTRO ciclo con cada literal es `engine.estados`, no este modulo.
        """
        if not isinstance(log, LogEventos):
            raise ErrorSimulador(f"se esperaba un LogEventos y llego {type(log).__name__}")
        registro = self._registro(referencia)
        if log.actuacion_id != registro.paquete.actuacion_id:
            raise ErrorSimulador(
                f"el log es de la actuacion {log.actuacion_id!r} y la referencia {registro.referencia} es "
                f"de {registro.paquete.actuacion_id!r}: no se mezclan"
            )
        actor = Actor(clase=CLASE_PLATAFORMA, id=self.nombre)
        nuevos: list[Evento] = []

        escritos = {
            (str(e.payload.get("referencia")), str(e.payload.get("literal")), texto_instante(e.ocurrido_en))
            for e in log.por_tipo(TIPO_ESTADO_RECIBIDO)
        }
        for estado in registro.historia:
            clave = (estado.referencia, estado.literal, texto_instante(estado.instante))
            if clave in escritos:
                continue
            escritos.add(clave)
            nuevos.append(
                log.anadir(
                    TIPO_ESTADO_RECIBIDO,
                    {
                        "referencia": estado.referencia,
                        "literal": estado.literal,
                        "nivel": estado.nivel,
                        "oficial": estado.oficial,
                        "motivos": list(estado.motivos),
                        "via": VIA_SIMULADOR,
                    },
                    actor=actor,
                    ocurrido_en=estado.instante,
                )
            )

        ya_escritas = {str(e.payload.get("id")) for e in log.por_tipo(TIPO_TAREA_RECIBIDA)}
        for tarea in registro.tareas:
            if tarea.id in ya_escritas:
                continue
            ya_escritas.add(tarea.id)
            nuevos.append(
                log.anadir(
                    TIPO_TAREA_RECIBIDA,
                    # El instante y la fecha van como objetos: los tipa `engine.eventos.codificar`, que es
                    # la unica forma textual de una fecha en el log.
                    {
                        **tarea.a_dict(),
                        "instante": tarea.instante,
                        "vence_en": tarea.vence_en,
                        "via": VIA_SIMULADOR,
                    },
                    actor=actor,
                    ocurrido_en=tarea.instante,
                )
            )
        return tuple(nuevos)

    # -- credencial ------------------------------------------------------------------------------

    @staticmethod
    def _credencial(credencial: object) -> Credencial:
        if not isinstance(credencial, Credencial):
            raise ErrorSimulador(
                f"se esperaba una Credencial (`docs/02` §2.2) y llego {type(credencial).__name__}"
            )
        return credencial


__all__ = [
    "CLASE_HUMANO",
    "CLASE_PLATAFORMA",
    "NOMBRE",
    "PERFILES",
    "PERFILES_QUE_CARGAN",
    "PERFIL_CONSULTA",
    "PERFIL_FIRMA",
    "PERFIL_MODIFICACION",
    "PREFIJO_REFERENCIA",
    "TIPO_DESISTIMIENTO",
    "TIPO_ESTADO_RECIBIDO",
    "TIPO_FIRMA",
    "TIPO_TAREA_RECIBIDA",
    "VIA_SIMULADOR",
    "Credencial",
    "ErrorSimulador",
    "Simulador",
    "estado_creacion",
    "estado_firmado",
    "estado_validado",
    "filas_de_actuacion",
    "referencia_de",
]
