"""Adaptador handoff (C6 de `ADR-009` §4): la carpeta ordenada que el tenant abre, revisa y presenta.

Es el cauce que funciona **hoy**, sin sandbox, sin diccionario y sin API: nosotros preparamos el paquete y
el tenant lo presenta por el cauce vigente. Por eso es el unico sitio de `salida/` donde no hay riesgo de
inventar un campo de la plataforma: el handoff **no imita ningun formato oficial**. Lo que se escribe es
nuestro, y como se escribe lo dice `mapping/IND240.handoff.yaml` y `mapping/manifiesto.handoff.yaml`, no
este fichero (regla de oro 4: dar de alta una ficha en la salida es anadir un YAML).

El arbol de `ADR-009` §4:

    <destino>/
      00_LEEME.md                    que es esto, que hace el tenant, que NO hemos hecho
      01_manifiesto.json             el manifiesto de S3.3, tal cual, con sus cinco hashes
      02_payload.json                cabecera + detalle segun el mapeo (NUESTRO formato)
      03_informe_prevalidacion.md    engine.informe.a_markdown, sin cambios
      04_informe_prevalidacion.json  engine.informe.a_json
      05_log_eventos.jsonl           solo si se paso log
      documentos/<tipo>/<fichero>    los adjuntos, copiados byte a byte y agrupados por tipo documental
      99_verificacion.txt            como comprobar la integridad sin nuestro software

Seis decisiones de este modulo, todas comprobadas por `tests/test_handoff.py`:

1. **Los bytes se copian, no se regeneran.** Terminada la escritura, se vuelve a calcular la huella de cada
   adjunto **en la carpeta escrita** y se contrasta con la que declaro el manifiesto. Si una sola no
   coincide, el acuse es `aceptado: False` con el fichero por su nombre, y la entrega no se declara hecha.
   Eso comprueba lo que se acaba de escribir; para volver a mirar la misma carpeta mas tarde esta
   `verificar_entrega`, porque el simulador valida la raiz del paquete y no esta carpeta.
2. **Las partes de un PDF combinado no se copian**: no existen en disco (`ADR-008` §4 bis punto 1). Se
   listan en el `00_LEEME.md` bajo su combinado, que si viaja.
3. **Idempotente por contenido.** Entregar dos veces el mismo paquete en la misma carpeta da el mismo
   resultado. Una carpeta destino no vacia con contenido distinto es `ErrorSalida`: **nunca se borra nada
   del usuario**. La unica excepcion declarada es el log de eventos, que es solo-anadir: si lo que hay en
   disco es un prefijo de lo que hay ahora, es el mismo log mas tarde y se reescribe entero.
   Ojo a lo que "el mismo paquete" quiere decir: el manifiesto sella su `generado_en`, asi que **volver a
   construir** el paquete de la misma actuacion con el reloj corriendo da otro `hash_paquete` y otra
   carpeta. Para que dos construcciones sean identicas byte a byte hay que inyectar `instante` (ver
   `__init__`), igual que en `salida.constructor.construir`.
4. **El estado de ciclo lo mueve el log, no este adaptador** (`ADR-009` §2 punto 2). Con `log`, `construir`
   emite `PayloadConstruido` y `ManifiestoGenerado` y `entregar` emite `EntregadoADelegado` **solo si la
   entrega fue aceptada**; quien decide si eso vale es `engine.estados.proyectar`, que levanta `ErrorEstado`
   si la actuacion no es `PREVALIDADO` **y** revisada por un humano. Aqui no se duplica esa comprobacion, y
   el evento se ensaya sobre una copia del log antes de anadirlo: una actuacion rechazada no deja el log del
   llamante con un evento que su propia proyeccion no admite.
5. **La firma no aparece por ninguna parte.** El `00_LEEME.md` dice explicitamente que firmar es un acto
   humano del tenant con su certificado de representante y que nosotros no firmamos ni custodiamos nada
   (`CLAUDE.md` §2, `docs/02` §6.2). Ningun texto de esta carpeta promete un CAE.
6. **Este adaptador no consulta nada.** `consultar_estado` y `consultar_tareas` se niegan con `ErrorSalida`
   explicando que por la via handoff el estado lo trae el tenant. Devolver una lista vacia se confundiria
   con "no hay tareas" (`ADR-009` §2 punto 4).

El informe de prevalidacion se renderiza desde la `Actuacion` del motor (`engine.informe`), que el modelo
canonico no lleva: `construir` lo guarda junto al paquete que devuelve, indexado por `hash_paquete`. Si el
paquete se construyo desde una `ActuacionCanonica` suelta no hay informe que escribir y el `00_LEEME.md`
lo dice; no se inventa uno a partir del detalle. Y si quien entrega **no** es el adaptador que construyo el
paquete, tampoco hay informe, pero el motivo es otro y el `00_LEEME.md` dice ese: un documento que lee el
tenant no afirma una causa que quien lo escribe no conoce.

Nada de `eval`, `exec`, `compile` ni coma flotante. Importa de `engine/` y de `salida/`; `engine/` no
importa de `salida/`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from engine.estados import proyectar
from engine.eventos import ErrorEvento, ahora_utc, normalizar_instante
from engine.eventos.log import Actor, LogEventos
from engine.informe import a_json, a_markdown
from engine.ingesta import ficheros_de, sha256_bytes
from engine.modelo import ActuacionCanonica, desde_motor
from salida.constructor import ErrorManifiesto, Manifiesto
from salida.constructor import construir as construir_manifiesto
from salida.constructor.manifiesto import SEPARADOR_PARTE, hash_de_manifiesto
from salida.mapeo import Mapeo, RenderManifiesto, aplicar, cargar_manifiesto, resolver
from salida.puerto import Acuse, ErrorSalida, EstadoPlataforma, Paquete, TareaPendiente, adjuntos_de

#: Nombre de esta via. Coincide con el literal de `engine.estados.VIAS_ENTREGA["EntregadoADelegado"]`.
NOMBRE = "handoff"

#: Destino de mapeo que este adaptador sabe entregar.
DESTINO = "handoff"

#: Quien firma nuestros eventos aqui. Clase `motor`: no hay ningun humano en este camino, y el unico
#: evento que exige humano (`FirmaRegistrada`) no lo emite este adaptador ni ningun componente nuestro.
ACTOR = Actor(clase="motor", id="salida.handoff")

#: Eventos del catalogo P8 que emite este adaptador (`docs/03` §6.2).
EVENTO_PAYLOAD = "PayloadConstruido"
EVENTO_MANIFIESTO = "ManifiestoGenerado"
EVENTO_ENTREGA = "EntregadoADelegado"

#: Nombres del arbol que este adaptador pide al mapeo (`mapping/<FICHA>.handoff.yaml`, bloque `ficheros`).
#: El del manifiesto no esta: lo declara el render (`mapping/manifiesto.handoff.yaml`). Que falte uno se
#: descubre al **entrar**, no a mitad de una entrega: es lo que promete la cabecera de `salida/mapeo.py`, y
#: el cargador no puede comprobarlo porque no sabe a que destino se entregara.
CLAVES_ARBOL = ("leeme", "payload", "informe_markdown", "informe_json", "log_eventos", "verificacion")

#: Codificacion y forma de los JSON que se escriben: legibles por una persona, estables entre entregas.
CODIFICACION = "utf-8"
SANGRIA_JSON = 2

#: Texto obligatorio sobre la firma. Va literal al `00_LEEME.md` (`CLAUDE.md` §2, `docs/02` §6.2).
AVISO_FIRMA = (
    "La firma es un acto humano del tenant, con certificado de representante, en su propio entorno. "
    "Nosotros no firmamos actos administrativos, no custodiamos certificados de representante y no "
    "presentamos nada en su nombre: solo registramos que la firma ocurrio."
)


class AdaptadorHandoff:
    """`PuertoSalida` sobre una carpeta. Sin dependencias externas y sin hablar con ninguna plataforma."""

    nombre = NOMBRE

    def __init__(
        self,
        *,
        destino_carpeta: str | Path | None = None,
        render_manifiesto: RenderManifiesto | None = None,
        instante: datetime | None = None,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        """`destino_carpeta` es adonde escribe este adaptador; `render_manifiesto`, un render ya cargado.

        El destino va en el constructor y no en `entregar` **a proposito**: asi `entregar(paquete, log=...)`
        cumple la firma de `PuertoSalida` y un llamante generico del puerto (P9, la consola) puede entregar
        sin saber que la via es un handoff ni que un handoff escribe en una carpeta. Sigue admitiendose en
        la llamada para entregar el mismo paquete en dos sitios sin construir dos adaptadores.

        `instante` congela el reloj y `reloj` inyecta uno propio, como en `salida/simulador/`. No es un lujo
        de test: `salida.constructor.construir` documenta que pasando `generado_en` dos construcciones del
        mismo paquete dan el mismo JSON byte a byte, y `hash_paquete` **es** el del manifiesto; sin punto de
        inyeccion aqui esa propiedad se perdia y el mismo paquete cambiaba de huella en cada construccion.
        """
        if instante is not None and reloj is not None:
            raise ErrorSalida("se inyecta `instante` (fijo) o `reloj` (invocable), no los dos a la vez")
        if instante is not None:
            fijo = _instante(instante)
            self._reloj: Callable[[], datetime] = lambda: fijo
        else:
            self._reloj = reloj or ahora_utc
        self._destino = None if destino_carpeta is None else Path(destino_carpeta)
        self._render = render_manifiesto if render_manifiesto is not None else cargar_manifiesto(DESTINO)
        # El informe de prevalidacion no cabe en `Paquete` y no se puede derivar del modelo canonico: se
        # guarda aqui, indexado por la huella del paquete, que es exactamente su contenido (ver cabecera).
        self._informes: dict[str, tuple[str, dict[str, object]]] = {}
        # Y que paquetes ha construido, con informe o sin el: sin esto, entregar un paquete que construyo
        # OTRO adaptador escribia en el `00_LEEME.md` que se habia construido desde el modelo canonico, que
        # es un motivo distinto y podia ser falso. Un documento que lee el tenant no afirma lo que no sabe.
        self._construidos: set[str] = set()

    # -- construccion ----------------------------------------------------------------------------

    def construir(
        self,
        actuacion: object,
        mapeo: object,
        *,
        raiz: object | None = None,
        log: object | None = None,
    ) -> Paquete:
        """Modelo canonico + mapeo -> `Paquete`. No firma, no entrega, no calcula y no juzga el veredicto.

        `actuacion` puede ser una `ActuacionCanonica` o la `Actuacion` del motor; en el segundo caso se
        convierte con `engine.modelo.desde_motor`, se renderiza el informe de prevalidacion y, si no se dio
        `raiz`, se toma la carpeta de la que salio la actuacion.
        """
        mapeo = _mapeo(mapeo)
        canonica, del_motor = _canonica(actuacion)
        if mapeo.ficha != str(canonica.ficha.get("codigo")):
            raise ErrorSalida(
                f"el mapeo {mapeo.id} es de la ficha {mapeo.ficha} y la actuacion es de "
                f"{canonica.ficha.get('codigo')!r}: un mapeo no se aplica a otra ficha"
            )
        carpeta = _raiz(raiz, del_motor)
        instante = self._ahora()

        payload, carencias = aplicar(mapeo, canonica)
        _registrar(
            log,
            EVENTO_PAYLOAD,
            {
                "mapeo_id": mapeo.id,
                "mapeo_version": mapeo.version,
                "destino": mapeo.destino,
                "campos": len(payload["cabecera"]) + len(payload["detalle"]["actuacion"]),
                "unidades": len(payload["detalle"]["unidades"]),
                "carencias": list(carencias),
            },
            instante=instante,
        )

        try:
            manifiesto = construir_manifiesto(canonica, log=log, generado_en=instante, raiz=carpeta)
        except ErrorManifiesto as exc:  # el puerto tiene una sola familia de errores hacia fuera
            raise ErrorSalida(f"no se puede construir el manifiesto del paquete: {exc}") from exc
        _registrar(
            log,
            EVENTO_MANIFIESTO,
            {
                "hash_manifiesto": manifiesto.hash_manifiesto,
                "manifiesto_version": manifiesto.manifiesto_version,
                "ficheros": len(manifiesto.ficheros),
            },
            instante=instante,
        )

        paquete = Paquete(
            actuacion_id=canonica.id,
            codigo_identificativo_propio=canonica.codigo_identificativo_propio,
            destino=mapeo.destino,
            mapeo_id=mapeo.id,
            mapeo_version=mapeo.version,
            generado_en=instante,
            payload=payload,
            manifiesto=manifiesto,
            adjuntos=adjuntos_de(manifiesto),
            raiz=str(carpeta),
            veredicto=_veredicto(canonica),
            carencias=carencias,
        )
        self._construidos.add(paquete.hash_paquete)
        if del_motor is not None:
            self._informes[paquete.hash_paquete] = (a_markdown(del_motor), a_json(del_motor))
        return paquete

    # -- entrega ---------------------------------------------------------------------------------

    def entregar(
        self,
        paquete: Paquete,
        *,
        destino_carpeta: str | Path | None = None,
        mapeo: object | None = None,
        log: object | None = None,
    ) -> Acuse:
        """Escribe el arbol del handoff y verifica lo escrito antes de dar el acuse.

        `mapeo` es el mismo con el que se construyo el paquete: de el salen los nombres del arbol y las
        subcarpetas por tipo documental. Se puede omitir y entonces se recarga por la ficha y el destino
        que declara el propio mapeo del paquete. `destino_carpeta` cae al del constructor si no se da.
        """
        if not isinstance(paquete, Paquete):
            raise ErrorSalida(f"entregar espera un Paquete, no {type(paquete).__name__}")
        if paquete.destino != DESTINO:
            raise ErrorSalida(
                f"este adaptador entrega al destino {DESTINO!r} y el paquete va a {paquete.destino!r}"
            )
        arbol = _arbol(
            paquete,
            _mapeo_de(mapeo, paquete),
            self._render,
            self._informes.get(paquete.hash_paquete),
            log,
            construido_aqui=paquete.hash_paquete in self._construidos,
        )
        carpeta = self._carpeta(destino_carpeta)
        _comprobar_ocupacion(carpeta, arbol)
        _escribir(carpeta, arbol)

        motivos = _verificar_entrega(paquete, carpeta, arbol)
        aceptado = not motivos
        acuse = Acuse(
            referencia=_referencia(paquete),
            via=NOMBRE,
            instante=self._ahora(),
            aceptado=aceptado,
            hash_paquete=paquete.hash_paquete,
            estado_plataforma=None,  # el handoff no es una plataforma: no fija ningun estado oficial
            motivos=tuple(motivos),
            detalle={
                "carpeta": str(carpeta),
                "ficheros": sorted(arbol.ficheros),
                "adjuntos": len([a for a in paquete.adjuntos if not a.es_parte]),
                "partes_no_copiadas": len([a for a in paquete.adjuntos if a.es_parte]),
                "carencias": list(paquete.carencias),
                "veredicto": paquete.veredicto,
            },
        )
        if aceptado and not _ya_entregado(log, paquete):
            _registrar(
                log,
                EVENTO_ENTREGA,
                {
                    "referencia": acuse.referencia,
                    "hash_paquete": paquete.hash_paquete,
                    "carpeta": str(carpeta),
                    "mapeo_id": paquete.mapeo_id,
                    "mapeo_version": paquete.mapeo_version,
                },
                instante=acuse.instante,
            )
        return acuse

    def _ahora(self) -> datetime:
        """El reloj de este adaptador: el inyectado o el UTC del resto del repositorio."""
        return _instante(self._reloj())

    # -- comprobar mas tarde lo que se entrego ----------------------------------------------------

    def verificar_entrega(
        self,
        paquete: Paquete,
        destino_carpeta: str | Path | None = None,
        *,
        mapeo: object | None = None,
    ) -> tuple[str, ...]:
        """Relee una carpeta ya entregada y contrasta cada adjunto con la huella que declaro el manifiesto.

        `entregar` comprueba lo que acaba de escribir (`ADR-009` §4), pero **despues nadie vuelve a mirar**:
        el simulador valida la raiz del paquete, no esta carpeta, asi que un byte cambiado aqui mas tarde no
        lo veria nadie. Esto es lo que permite comprobarla en cualquier momento. No recalcula ninguna huella
        propia: contrasta los bytes que hay en disco con lo que declaro el manifiesto de S3.3.

        Devuelve los motivos, cada uno **con el nombre del fichero**; vacio significa que la carpeta sigue
        siendo la que se entrego. No es un veredicto ni mueve ningun estado: describe.
        """
        if not isinstance(paquete, Paquete):
            raise ErrorSalida(f"verificar_entrega espera un Paquete, no {type(paquete).__name__}")
        carpeta = self._carpeta(destino_carpeta)
        if not carpeta.is_dir():
            raise ErrorSalida(f"no hay ninguna carpeta entregada en {carpeta}")
        rutas = _rutas_de_adjuntos(paquete, _mapeo_de(mapeo, paquete))
        motivos: list[str] = []
        sellado = hash_de_manifiesto(paquete.manifiesto)
        if sellado != paquete.manifiesto.hash_manifiesto:
            motivos.append(
                f"el manifiesto no sella su propio contenido: calcula {sellado} y declara "
                f"{paquete.manifiesto.hash_manifiesto}"
            )
        for adjunto in sorted(paquete.adjuntos, key=lambda a: a.ruta):
            if adjunto.es_parte:  # una parte no es un fichero de la carpeta: viaja dentro de su combinado
                continue
            relativa = rutas[adjunto.ruta]
            fichero = carpeta / relativa
            if not fichero.is_file():
                motivos.append(f"falta en la carpeta entregada: {relativa}")
                continue
            if sha256_bytes(fichero.read_bytes()) != adjunto.sha256:
                motivos.append(
                    f"adjunto alterado: {relativa} no tiene la huella {adjunto.sha256} que declara el "
                    "manifiesto"
                )
        return tuple(motivos)

    def _carpeta(self, destino_carpeta: str | Path | None) -> Path:
        """Adonde se escribe: lo de la llamada manda sobre lo del constructor.

        Sin ninguno de los dos, `ErrorSalida`: un handoff sin carpeta no es una entrega.
        """
        if destino_carpeta is not None:
            return Path(destino_carpeta)
        if self._destino is not None:
            return self._destino
        raise ErrorSalida(
            "no hay adonde entregar: da `destino_carpeta` al construir el adaptador o al llamar a "
            "`entregar`. Un handoff sin carpeta no es una entrega"
        )

    # -- lo que esta via no hace -----------------------------------------------------------------

    def consultar_estado(self, referencia: str) -> EstadoPlataforma:
        """Se niega: por la via handoff el estado lo trae el tenant (`ADR-009` §2 punto 4)."""
        raise ErrorSalida(
            f"la via {NOMBRE} no consulta la plataforma: quien presenta la actuacion es el tenant y el "
            f"estado de {referencia!r} lo trae el, como `EstadoPlataformaRecibido`. Devolver un estado "
            "inventado o vacio seria peor que no responder. TODO(API-01): ver docs/HUECOS.md"
        )

    def consultar_tareas(self, tenant_id: str) -> Sequence[TareaPendiente]:
        """Se niega: una lista vacia se confundiria con 'no hay tareas' (`ADR-009` §2 punto 4)."""
        raise ErrorSalida(
            f"la via {NOMBRE} no tiene las tareas pendientes del tenant {tenant_id!r}: las ve el en la "
            "plataforma y nos las comunica. Una lista vacia se confundiria con 'no hay tareas'. "
            "TODO(API-01): ver docs/HUECOS.md"
        )


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


def _instante(valor: datetime) -> datetime:
    """Un instante siempre en UTC y siempre con zona: un `datetime` naive nunca entra."""
    try:
        return normalizar_instante(valor)
    except ErrorEvento as exc:
        raise ErrorSalida(f"instante invalido: {exc}") from exc


def _mapeo(mapeo: object) -> Mapeo:
    if not isinstance(mapeo, Mapeo):
        raise ErrorSalida(f"se esperaba un Mapeo de salida.mapeo, no {type(mapeo).__name__}")
    if mapeo.destino != DESTINO:
        raise ErrorSalida(
            f"el mapeo {mapeo.id} es del destino {mapeo.destino!r} y este adaptador es {DESTINO!r}"
        )
    faltan = [clave for clave in CLAVES_ARBOL if clave not in mapeo.ficheros]
    if faltan:
        raise ErrorSalida(
            f"el mapeo {mapeo.id} no declara los nombres del arbol del handoff {faltan}; declara "
            f"{sorted(mapeo.ficheros)}. Un mapeo incompleto se ve aqui, antes de tocar el disco"
        )
    return mapeo


def _mapeo_de(mapeo: object, paquete: Paquete) -> Mapeo:
    if mapeo is not None:
        dado = _mapeo(mapeo)
        if dado.id != paquete.mapeo_id or dado.version != paquete.mapeo_version:
            raise ErrorSalida(
                f"el paquete se construyo con {paquete.mapeo_id}@{paquete.mapeo_version} y se entrega con "
                f"{dado.id}@{dado.version}: dos mapeos distintos dan dos carpetas distintas"
            )
        return dado
    from salida.mapeo import cargar  # import local: solo hace falta cuando el llamante no pasa el mapeo

    ficha = str(paquete.manifiesto.ficha.get("codigo") or "")
    if not ficha:
        raise ErrorSalida("el paquete no dice de que ficha es: pasa el `mapeo` con el que se construyo")
    return _mapeo(cargar(ficha, paquete.destino))


def _canonica(actuacion: object) -> tuple[ActuacionCanonica, object | None]:
    """`(canonica, actuacion del motor o None)`. Acepta las dos entradas de `ADR-009` §4."""
    if isinstance(actuacion, ActuacionCanonica):
        return actuacion, None
    if hasattr(actuacion, "consolidada") and hasattr(actuacion, "evaluacion"):
        return desde_motor(actuacion), actuacion
    raise ErrorSalida(
        f"construir espera una ActuacionCanonica o la Actuacion del motor, no {type(actuacion).__name__}"
    )


def _raiz(raiz: object, del_motor: object | None) -> Path:
    """La carpeta de la que salen los bytes. Sin ella no hay paquete que manifestar."""
    if raiz is None and del_motor is not None:
        raiz = getattr(del_motor, "carpeta", None)
    if raiz is None:
        raise ErrorSalida(
            "construir necesita la `raiz` del paquete original: es de donde se copian los bytes de los "
            "adjuntos y contra ella se declara cada ruta del manifiesto"
        )
    carpeta = Path(str(raiz))
    if not carpeta.is_dir():
        raise ErrorSalida(f"la raiz del paquete no es una carpeta: {carpeta}")
    return carpeta


def _veredicto(canonica: ActuacionCanonica) -> str | None:
    """El veredicto se **transporta**, no se juzga (`ADR-009` §2 punto 1)."""
    valor = canonica.evaluacion.get("veredicto")
    return str(valor) if valor is not None else None


def _referencia(paquete: Paquete) -> str:
    """Referencia **nuestra**, marcada como tal: como son las oficiales es parte de API-01."""
    return f"{NOMBRE}:{paquete.codigo_identificativo_propio}:{paquete.hash_paquete[:12]}"


# ---------------------------------------------------------------------------
# Log: el estado lo mueve la maquina, no el adaptador
# ---------------------------------------------------------------------------


def _registrar(
    log: object, tipo: str, payload: Mapping[str, object], *, instante: datetime | None = None
) -> None:
    """Anade el evento P8 al log, si hay log, despues de ensayarlo sobre una copia (ver cabecera §4).

    El ensayo evita que una actuacion que la maquina de estados rechaza se quede con el evento pegado en el
    log del llamante: `engine.estados.proyectar` decide, y su `ErrorEstado` sale de aqui tal cual.
    """
    if log is None:
        return
    if not isinstance(log, LogEventos):
        raise ErrorSalida(f"`log` deberia ser un LogEventos, no {type(log).__name__}")
    momento = normalizar_instante(instante) if instante is not None else ahora_utc()
    ensayo = LogEventos(actuacion_id=log.actuacion_id, eventos=list(log.eventos))
    ensayo.anadir(tipo, payload, actor=ACTOR, ocurrido_en=momento)
    proyectar(ensayo)  # ErrorEstado si la actuacion no puede estar aqui todavia
    log.anadir(tipo, payload, actor=ACTOR, ocurrido_en=momento)


def _ya_entregado(log: object, paquete: Paquete) -> bool:
    """`True` si este mismo paquete ya consta entregado: entregar dos veces no son dos entregas."""
    if not isinstance(log, LogEventos):
        return False
    return any(
        evento.datos.get("hash_paquete") == paquete.hash_paquete for evento in log.por_tipo(EVENTO_ENTREGA)
    )


# ---------------------------------------------------------------------------
# El arbol: que fichero lleva que bytes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Arbol:
    """El handoff entero en memoria antes de tocar el disco.

    `ficheros` es `{ruta relativa: bytes}`; `adjuntos` es `{ruta en el manifiesto: ruta en el handoff}`, y
    es lo que permite verificar lo escrito contra lo que declaro el manifiesto pese a que aqui los
    documentos se reagrupan por tipo documental. `log` es el nombre del fichero del log, si se escribe.
    """

    ficheros: Mapping[str, bytes]
    adjuntos: Mapping[str, str]
    log: str | None


def _json(valor: object) -> bytes:
    """JSON legible y estable. `sort_keys` para que dos entregas del mismo paquete den los mismos bytes."""
    texto = json.dumps(valor, ensure_ascii=False, indent=SANGRIA_JSON, sort_keys=True)
    return f"{texto}\n".encode(CODIFICACION)


def _nombre_adjunto(ruta: str, usados: set[str], sha256: str) -> str:
    """Nombre del adjunto dentro de su subcarpeta: su nombre de siempre, salvo colision.

    Dos ficheros distintos con el mismo nombre en subcarpetas distintas del paquete original acabarian en
    el mismo sitio; el segundo lleva su huella corta para que ninguno se pierda (nunca se sobreescribe).
    """
    base = Path(ruta).name
    if base not in usados:
        return base
    return f"{Path(base).stem}-{sha256[:8]}{Path(base).suffix}"


def _rutas_de_adjuntos(paquete: Paquete, mapeo: Mapeo) -> dict[str, str]:
    """`{ruta en el manifiesto: ruta relativa en el handoff}`, solo para lo que existe en disco."""
    carpeta = str(mapeo.documentos.get("carpeta") or "documentos")
    rutas: dict[str, str] = {}
    usados: dict[str, set[str]] = {}
    for adjunto in sorted(paquete.adjuntos, key=lambda a: a.ruta):
        if adjunto.es_parte:  # una parte no es un fichero: se lista bajo su combinado, no se copia
            continue
        subcarpeta = mapeo.carpeta_de_tipo(adjunto.tipo)
        ocupados = usados.setdefault(subcarpeta, set())
        nombre = _nombre_adjunto(adjunto.ruta, ocupados, adjunto.sha256)
        ocupados.add(nombre)
        rutas[adjunto.ruta] = f"{carpeta}/{subcarpeta}/{nombre}"
    return rutas


def _arbol(
    paquete: Paquete,
    mapeo: Mapeo,
    render: RenderManifiesto,
    informe: tuple[str, dict[str, object]] | None,
    log: object,
    *,
    construido_aqui: bool = True,
) -> _Arbol:
    """Todo el handoff en memoria: los bytes de cada fichero y donde acabo cada adjunto."""
    rutas = _rutas_de_adjuntos(paquete, mapeo)
    raiz = Path(paquete.raiz)
    ficheros: dict[str, bytes] = {}
    for ruta_manifiesto, ruta_handoff in rutas.items():
        origen = raiz / ruta_manifiesto
        if not origen.is_file():
            raise ErrorSalida(
                f"el adjunto {ruta_manifiesto} ya no esta en {raiz}: no se puede entregar un paquete cuyos "
                "bytes han desaparecido"
            )
        ficheros[ruta_handoff] = origen.read_bytes()  # se copian los bytes, nunca se regeneran

    ficheros[render.fichero] = _json(paquete.manifiesto.a_dict())
    ficheros[mapeo.fichero("payload")] = _json(
        {
            "codigo_identificativo_propio": paquete.codigo_identificativo_propio,
            "mapeo": {"id": paquete.mapeo_id, "version": paquete.mapeo_version, "destino": paquete.destino},
            "generado_en": paquete.generado_en.isoformat(),
            "veredicto": paquete.veredicto,
            "carencias": list(paquete.carencias),
            **dict(paquete.payload),
        }
    )
    if informe is not None:
        ficheros[mapeo.fichero("informe_markdown")] = informe[0].encode(CODIFICACION)
        ficheros[mapeo.fichero("informe_json")] = _json(informe[1])
    nombre_log: str | None = None
    if isinstance(log, LogEventos):
        nombre_log = mapeo.fichero("log_eventos")
        ficheros[nombre_log] = log.a_jsonl().encode(CODIFICACION)

    nombre_verificacion = mapeo.fichero("verificacion")
    ficheros[nombre_verificacion] = _verificacion(paquete, rutas, nombre_verificacion).encode(CODIFICACION)
    nombre_leeme = mapeo.fichero("leeme")
    # El propio LEEME entra en la lista de lo que hay en la carpeta: se escribe el ultimo, pero esta.
    ficheros[nombre_leeme] = _leeme(
        paquete,
        mapeo,
        render,
        rutas,
        {*ficheros, nombre_leeme},
        informe is not None,
        construido_aqui=construido_aqui,
    ).encode(CODIFICACION)
    return _Arbol(ficheros=ficheros, adjuntos=rutas, log=nombre_log)


# ---------------------------------------------------------------------------
# Textos de la carpeta
# ---------------------------------------------------------------------------


def _tabla(cabecera: Sequence[str], filas: Sequence[Sequence[object]]) -> list[str]:
    lineas = [f"| {' | '.join(cabecera)} |", f"|{'|'.join(['---'] * len(cabecera))}|"]
    lineas.extend(f"| {' | '.join('' if c is None else str(c) for c in fila)} |" for fila in filas)
    return lineas


def _resumen_manifiesto(manifiesto: Manifiesto, render: RenderManifiesto) -> list[Sequence[object]]:
    """Los campos del manifiesto en el orden y con las etiquetas que declara el render (no se recalcula)."""
    documento = manifiesto.a_dict()
    return [
        [campo.etiqueta, resolver(documento, campo.origen) if campo.origen else None]
        for campo in render.campos
    ]


def _partes_de(paquete: Paquete, ruta_combinado: str) -> list[object]:
    return [a for a in paquete.adjuntos if a.es_parte and a.ruta.split(SEPARADOR_PARTE)[0] == ruta_combinado]


def _leeme(
    paquete: Paquete,
    mapeo: Mapeo,
    render: RenderManifiesto,
    rutas: Mapping[str, str],
    escritos: set[str],
    con_informe: bool,
    *,
    construido_aqui: bool = True,
) -> str:
    """El `00_LEEME.md`: que es la carpeta, que contiene, que falta y que tiene que hacer el tenant."""
    lineas: list[str] = [
        f"# Actuación {paquete.codigo_identificativo_propio}",
        "",
        "Carpeta de entrega (**handoff**) preparada por el motor de prevalidación CAE.",
        "",
        "## 1. Qué es esto y qué no es",
        "",
        "Esta carpeta reúne la actuación **prevalidada**: el detalle calculado de forma determinista, la",
        "documentación que la sostiene y la prueba de que nadie la ha alterado. Es material de trabajo para",
        "que una persona lo revise y lo presente; **no es una presentación hecha ni una resolución**.",
        "",
        f"- Veredicto de prevalidación: **{paquete.veredicto or 'sin veredicto'}**.",
        "- La prevalidación es nuestra lectura de la ficha y de la norma, no la de la Administración ni la",
        "  del organismo de verificación. Quien decide si la actuación se certifica no somos nosotros.",
        "",
        "## 2. La firma y la presentación son suyas",
        "",
        AVISO_FIRMA,
        "",
        "Tampoco hemos hablado con la plataforma oficial: por esta vía no consultamos estados ni tareas",
        "pendientes. Si la plataforma le comunica algo, es usted quien nos lo traslada.",
        "",
        "## 3. Qué hay en la carpeta",
        "",
    ]
    descripciones = {
        mapeo.fichero("leeme"): "este fichero",
        render.fichero: "manifiesto interno: qué se entrega y con qué huella SHA-256",
        mapeo.fichero("payload"): "cabecera y detalle de la actuación, en nuestro formato",
        mapeo.fichero("informe_markdown"): "informe de prevalidación para leer",
        mapeo.fichero("informe_json"): "el mismo informe, para procesar",
        mapeo.fichero("log_eventos"): "log de eventos encadenado de la actuación",
        mapeo.fichero("verificacion"): "cómo comprobar la integridad sin nuestro software",
    }
    lineas.extend(
        _tabla(
            ["Fichero", "Qué es"],
            [[nombre, descripciones[nombre]] for nombre in sorted(descripciones) if nombre in escritos],
        )
    )
    if not con_informe and construido_aqui:
        lineas.extend(
            [
                "",
                "> **Sin informe de prevalidación.** Este paquete se construyó desde el modelo canónico y no",
                "> desde la actuación procesada, así que no hay informe que adjuntar. No se ha reconstruido",
                "> uno a partir del detalle: sería un informe que nadie ha producido.",
            ]
        )
    elif not con_informe:
        # No se dice por qué no hay informe: quien entrega no construyó este paquete y no lo sabe.
        lineas.extend(
            [
                "",
                "> **Sin informe de prevalidación.** El paquete no lo construyó quien lo entrega, así que",
                "> el informe no ha viajado hasta aquí. No se ha reconstruido uno a partir del detalle:",
                "> sería un informe que nadie ha producido. Pídalo a quien preparó el paquete.",
            ]
        )

    lineas.extend(["", "## 4. Documentos", ""])
    filas: list[Sequence[object]] = []
    for adjunto in sorted(paquete.adjuntos, key=lambda a: a.ruta):
        if adjunto.es_parte:
            continue
        filas.append([rutas[adjunto.ruta], adjunto.tipo or "sin clasificar", adjunto.bytes, adjunto.sha256])
    lineas.extend(_tabla(["Fichero en esta carpeta", "Tipo documental", "Bytes", "SHA-256"], filas))

    combinados = [
        adjunto
        for adjunto in sorted(paquete.adjuntos, key=lambda a: a.ruta)
        if not adjunto.es_parte and _partes_de(paquete, adjunto.ruta)
    ]
    if combinados:
        lineas.extend(
            [
                "",
                "### 4.1 PDF con varios documentos dentro",
                "",
                "Estos ficheros llegaron con varios documentos en un solo PDF. Las partes **no son",
                "ficheros** y por eso no están copiadas: existen como lectura nuestra del combinado, y si",
                "el combinado cambia, dejan de estar demostradas.",
                "",
            ]
        )
        for combinado in combinados:
            lineas.append(f"- `{rutas[combinado.ruta]}` contiene:")
            for parte in sorted(_partes_de(paquete, combinado.ruta), key=lambda a: a.ruta):
                etiqueta = parte.tipo or "sin clasificar"
                doc_id = parte.ruta.split(SEPARADOR_PARTE)[1]
                lineas.append(f"  - {etiqueta} (`{doc_id}`, {parte.bytes} bytes)")

    lineas.extend(["", "## 5. Qué falta", ""])
    if paquete.carencias:
        lineas.append("Campos obligatorios del mapeo que no tienen valor. Declarado no es demostrado:")
        lineas.append("")
        lineas.extend(f"- `{clave}`" for clave in paquete.carencias)
    else:
        lineas.append("Ningún campo obligatorio del mapeo se ha quedado sin valor.")
    if not mapeo.cabecera:
        lineas.extend(
            [
                "",
                f"La cabecera común va vacía: el mapeo `{mapeo.id}` declara 0 campos de cabecera. Los datos",
                "de titularidad y localización que la plataforma pedirá en su formulario todavía no están",
                "definidos por nuestra parte y no se inventan aquí.",
            ]
        )

    lineas.extend(
        [
            "",
            "## 6. Integridad",
            "",
        ]
    )
    lineas.extend(_tabla(["Campo", "Valor"], _resumen_manifiesto(paquete.manifiesto, render)))
    lineas.extend(
        [
            "",
            f"Para comprobarlo sin nuestro software, siga `{mapeo.fichero('verificacion')}`.",
            "",
            "## 7. Qué hacer ahora",
            "",
            "1. Revise el informe de prevalidación y, en particular, las interpretaciones aplicadas: son",
            "   criterios propios ante lo que la norma no cierra, no verdad normativa.",
            "2. Complete lo que figure en «Qué falta».",
            "3. Presente la actuación por el cauce vigente y fírmela usted, con su certificado.",
            "4. Comuníquenos el estado que le devuelva la plataforma y cualquier requerimiento que reciba.",
            "",
            f"Paquete `{paquete.hash_paquete}`, generado el {paquete.generado_en.isoformat()}.",
            f"Mapeo `{paquete.mapeo_id}` versión `{paquete.mapeo_version}`.",
            "",
        ]
    )
    return "\n".join(lineas)


def _verificacion(paquete: Paquete, rutas: Mapping[str, str], nombre: str) -> str:
    """El `99_verificacion.txt`: comprobar la carpeta con `sha256sum`, sin nada nuestro instalado."""
    lineas = [
        f"VERIFICACION DE INTEGRIDAD - {paquete.codigo_identificativo_propio}",
        "",
        "Cada documento de esta carpeta viaja con la huella SHA-256 que se le calculo al entrar, antes de",
        "cualquier transformacion. Las huellas de abajo son las del manifiesto, no se han recalculado aqui.",
        "",
        "Comprobacion completa, desde esta misma carpeta, con herramientas del sistema:",
        "",
        f"    grep -E '^[0-9a-f]{{64}}  ' {nombre} | sha256sum -c -",
        "",
        "Comprobacion de un solo fichero:",
        "",
        "    sha256sum <ruta del fichero>",
        "",
        "HUELLAS (formato de sha256sum: huella, dos espacios, ruta relativa a esta carpeta)",
        "",
    ]
    for adjunto in sorted(paquete.adjuntos, key=lambda a: a.ruta):
        if adjunto.es_parte:
            continue
        lineas.append(f"{adjunto.sha256}  {rutas[adjunto.ruta]}")
    lineas.extend(
        [
            "",
            "PARTES DE UN PDF COMBINADO",
            "",
            "Una parte separada de un PDF con varios documentos no es un fichero de esta carpeta y no se",
            "puede comprobar por separado: se sostiene sobre su combinado, que si esta y si se comprueba.",
            "",
        ]
    )
    partes = [a for a in sorted(paquete.adjuntos, key=lambda a: a.ruta) if a.es_parte]
    if partes:
        for parte in partes:
            combinado = parte.ruta.split(SEPARADOR_PARTE)[0]
            lineas.append(f"  {parte.tipo or 'sin clasificar'} <- {rutas.get(combinado, combinado)}")
    else:
        lineas.append("  (ninguna)")
    lineas.extend(
        [
            "",
            "EL SELLO DEL MANIFIESTO",
            "",
            f"  hash_manifiesto: {paquete.manifiesto.hash_manifiesto}",
            "",
            "Ese sello se calcula sobre el JSON canonico del manifiesto sin ese campo, con nuestra propia",
            "canonicalizacion, asi que NO se reproduce con sha256sum. Lo que si se comprueba sin nosotros es",
            "todo lo de arriba: si cada documento es byte a byte el que se evaluo.",
            "",
        ]
    )
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Escritura, idempotencia y verificacion de lo escrito
# ---------------------------------------------------------------------------


def _existentes(carpeta: Path) -> dict[str, bytes]:
    if not carpeta.is_dir():
        return {}
    return {f.relative_to(carpeta).as_posix(): f.read_bytes() for f in ficheros_de(carpeta)}


def _comprobar_ocupacion(carpeta: Path, arbol: _Arbol) -> None:
    """Idempotencia por contenido. Nunca se borra nada del usuario (`ADR-009` §4).

    La unica diferencia tolerada es el fichero del log: el log es solo-anadir, asi que si lo que hay en
    disco es un **prefijo** de lo que hay ahora, es el mismo log mas tarde y se reescribe entero. La
    tolerancia va en una sola direccion a proposito: si en disco hay MAS log del que traemos, la carpeta
    sabe algo que nosotros no, y reescribirla seria borrar eventos del usuario. Eso es `ErrorSalida`.
    """
    existentes = _existentes(carpeta)
    if not existentes:
        return
    sobrantes = sorted(set(existentes) - set(arbol.ficheros))
    if sobrantes:
        raise ErrorSalida(
            f"la carpeta destino {carpeta} ya tiene contenido que este paquete no produce "
            f"({sobrantes[:5]}{' ...' if len(sobrantes) > 5 else ''}): no se entrega encima y no se borra "
            "nada; elige una carpeta vacia o la misma de una entrega anterior de este paquete"
        )
    distintos = []
    for ruta, contenido in sorted(arbol.ficheros.items()):
        previo = existentes.get(ruta)
        if previo is None or previo == contenido:
            continue
        if ruta == arbol.log and contenido.startswith(previo):
            continue  # el mismo log, mas tarde: solo-anadir. Al reves no: perderiamos eventos
        distintos.append(ruta)
    if distintos:
        raise ErrorSalida(
            f"la carpeta destino {carpeta} ya contiene una entrega distinta: {distintos[:5]}"
            f"{' ...' if len(distintos) > 5 else ''}. No se sobreescribe ni se borra; usa otra carpeta"
        )


def _escribir(carpeta: Path, arbol: _Arbol) -> None:
    for ruta, contenido in sorted(arbol.ficheros.items()):
        destino = carpeta / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.is_file() and destino.read_bytes() == contenido:
            continue  # idempotencia: lo identico no se reescribe
        destino.write_bytes(contenido)


def _verificar_entrega(paquete: Paquete, carpeta: Path, arbol: _Arbol) -> list[str]:
    """Relee la carpeta escrita y contrasta cada adjunto con la huella que declaro el manifiesto.

    No sirve `salida.constructor.verificar` tal cual: sus rutas son las del paquete original y aqui los
    adjuntos se han agrupado por tipo documental. Lo que se comprueba es lo mismo -- la huella de los bytes,
    fichero a fichero -- mas que el propio manifiesto siga sellando su contenido.
    """
    motivos: list[str] = []
    sellado = hash_de_manifiesto(paquete.manifiesto)
    if sellado != paquete.manifiesto.hash_manifiesto:
        motivos.append(
            f"el manifiesto no sella su propio contenido: calcula {sellado} y declara "
            f"{paquete.manifiesto.hash_manifiesto}"
        )
    declaradas = {
        arbol.adjuntos[adjunto.ruta]: adjunto.sha256
        for adjunto in paquete.adjuntos
        if not adjunto.es_parte and adjunto.ruta in arbol.adjuntos
    }
    for ruta in sorted(arbol.ficheros):
        destino = carpeta / ruta
        if not destino.is_file():
            motivos.append(f"no se escribio {ruta}")
            continue
        escrito = destino.read_bytes()
        esperada = declaradas.get(ruta)
        if esperada is not None and sha256_bytes(escrito) != esperada:
            motivos.append(
                f"adjunto alterado: {ruta} no tiene la huella {esperada} que declara el manifiesto"
            )
        elif escrito != arbol.ficheros[ruta]:
            motivos.append(f"lo escrito en {ruta} no es lo que se preparo")
    sobrantes = sorted(set(_existentes(carpeta)) - set(arbol.ficheros))
    motivos.extend(f"sobra en la carpeta entregada: {ruta}" for ruta in sobrantes)
    return motivos


__all__ = [
    "ACTOR",
    "AVISO_FIRMA",
    "CLAVES_ARBOL",
    "DESTINO",
    "EVENTO_ENTREGA",
    "EVENTO_MANIFIESTO",
    "EVENTO_PAYLOAD",
    "NOMBRE",
    "AdaptadorHandoff",
]
