"""Comandos sobre una actuacion: lo que un operador o un revisor hacen con ella.

Cada manejador **valida la entrada, delega en `engine/` y traduce**. Ninguno calcula un ahorro, evalua una
regla ni decide una transicion: el estado lo mueve el log y lo proyecta `engine/estados.py`.

Todos escriben con `engine.seguimiento.anadir_una_vez`, y no con `log.anadir` a pelo, por dos razones que
no son de estilo: el evento se ensaya primero contra la maquina de estados, asi que un comando que el ciclo
no admite **no deja el log envenenado**; y repetir la misma peticion no duplica el hecho.

Que manejador atiende que capacidad lo dice `engine/capacidades.yaml`, en `manejador`. Aqui no hay ni un
`CAP-nn`: el despachador busca la funcion por su nombre.
"""

from __future__ import annotations

from collections.abc import Mapping

from api.contrato import Peticion, Salida, actor_de
from api.permisos import Capacidad, ErrorApi
from api.servicios import Servicios
from engine.eventos.canonico import ErrorEvento, ahora_utc
from engine.eventos.catalogo import ORIGENES_SUBSANACION
from engine.eventos.log import Evento, LogEventos
from engine.requerimientos import ErrorRequerimiento, confirmar, reabrir
from engine.seguimiento import ErrorSeguimiento, anadir_una_vez

#: Origen de una subsanacion que nace de nuestra propia revision (`ADR-006` CAP-09, `docs/03` §10.5).
ORIGEN_INTERNO = "interno"


def instante_de(servicios: Servicios):
    """El reloj de los eventos: el que inyectan los servicios o, si no, UTC. Nunca uno local."""
    return servicios.instante if servicios.instante is not None else ahora_utc()


def log_de(peticion: Peticion, servicios: Servicios) -> LogEventos:
    """El log de la actuacion sobre la que se actua, o `ErrorApi` si todavia no tiene."""
    log = servicios.repositorio.log(peticion.actuacion_id)
    if log is None:
        raise ErrorApi(f"la actuacion {peticion.actuacion_id!r} no tiene log: hay que abrirla antes")
    return log


def escribir(
    log: LogEventos,
    tipo: str,
    payload: Mapping[str, object],
    *,
    peticion: Peticion,
    servicios: Servicios,
    rol: str,
) -> Evento:
    """Sella un evento ensayandolo primero contra el ciclo. Traduce el error del nucleo a `ErrorApi`.

    Se traducen los dos que puede levantar el nucleo aqui: el del ciclo (`ErrorSeguimiento`) y el del log
    (`ErrorEvento`, que es donde vive el control de A8). Quien llama a la API recibe un error de la API.
    """
    try:
        evento, _ = anadir_una_vez(
            log,
            tipo,
            dict(payload),
            instante=instante_de(servicios),
            actor=actor_de(peticion.principal, rol),
        )
    except (ErrorSeguimiento, ErrorEvento) as exc:
        raise ErrorApi(f"{peticion.capacidad}: {exc}") from exc
    return evento


def _marca(capacidad: Capacidad) -> dict[str, object]:
    """Lo que todo evento escrito por esta API lleva: de que capacidad salio. Trazabilidad sin cablear."""
    return {"capacidad": capacidad.id}


# ---------------------------------------------------------------------------
# Manejadores
# ---------------------------------------------------------------------------


def abrir_actuacion(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Da de alta la actuacion y la adscribe al tenant del principal (P0)."""
    identificador = peticion.actuacion_id
    tenant = peticion.principal.tenant_id
    if tenant is None:  # pragma: no cover - el ambito de tenant ya lo exige en `exigir`
        raise ErrorApi(f"{capacidad.id}: abrir una actuacion exige un principal con tenant")
    log = servicios.repositorio.abrir(identificador, tenant)
    apertura = escribir(
        log,
        "ActuacionAbierta",
        {
            **_marca(capacidad),
            "codigo_identificativo_propio": peticion.texto("codigo_identificativo_propio"),
            "grupo_id": peticion.texto("grupo_id"),
            "expediente_id": peticion.texto("expediente_id"),
        },
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    asignacion = escribir(
        log,
        "TenantAsignado",
        {**_marca(capacidad), "tenant_id": tenant},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"actuacion_id": identificador}, eventos=(apertura, asignacion))


#: Claves que **no** se admiten al registrar un documento: nombran un fichero del servidor.
CLAVES_DE_SERVIDOR = ("ruta", "nombre_fichero", "path")


def registrar_documento(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Registra un documento aportado (P1). La huella la calcula el nucleo sobre los bytes, no el cliente.

    **El documento llega como contenido, nunca como ruta del servidor** (cerrado el 20/09/2026). Aceptar una
    ruta de quien pregunta convertia esta capacidad en un oraculo: cualquiera con `CAP-02` podia hacer que el
    servidor leyera un fichero alcanzable y le devolviera su huella, su tamano y si existia. Es el espejo
    exacto del agujero que `ADR-012` §1 cierra en la lectura, y lo encontro el agente que cerro aquel.

    Hoy no hay canal de subida desde el navegador (`GAP-REV-03`), asi que esta capacidad no se puede ejercer
    de extremo a extremo: **falla diciendo que falta el canal**, que es lo que hace el resto del contrato de
    `FR0` con lo que todavia no existe. Lo que no hace es funcionar por una via que no debe existir.
    """
    coladas = [clave for clave in CLAVES_DE_SERVIDOR if clave in peticion.datos]
    if coladas:
        raise ErrorApi(
            f"{capacidad.id}: un documento se aporta por su contenido, nunca nombrando un fichero del "
            f"servidor; sobra {coladas}. Una ruta en la peticion es un camino para leer ficheros ajenos"
        )
    contenido = peticion.exige("contenido")
    if not isinstance(contenido, bytes | bytearray):
        raise ErrorApi(
            f"{capacidad.id}: `contenido` son los bytes del documento. Llego {type(contenido).__name__}"
        )
    guardar = getattr(servicios.repositorio, "guardar_documento", None)
    if not callable(guardar):
        raise ErrorApi(
            f"{capacidad.id}: falta el canal de subida (`GAP-REV-03`): el repositorio no sabe guardar el "
            "contenido de un documento aportado"
        )
    sha256 = str(guardar(peticion.actuacion_id, bytes(contenido)))
    huella: Mapping[str, object] = {"sha256": sha256, "bytes": len(contenido)}
    if "sha256" not in huella:  # pragma: no cover - contrato del repositorio
        raise ErrorApi(f"{capacidad.id}: el repositorio no ha devuelto la huella del documento")
    evento = escribir(
        log_de(peticion, servicios),
        "DocumentoRegistrado",
        {**_marca(capacidad), **huella, "aportado_por": peticion.principal.usuario_id},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"sha256": huella["sha256"], "nombre": huella.get("nombre")}, eventos=(evento,))


def _correccion(
    peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str, motivo: str
) -> Salida:
    """Lo comun a corregir un dato y a resolver un desacuerdo: las dos son la misma correccion humana."""
    variable = str(peticion.exige("variable"))
    evento = escribir(
        log_de(peticion, servicios),
        "DatoCorregidoPorHumano",
        {
            **_marca(capacidad),
            "variable": variable,
            "num_serie_motor": peticion.texto("num_serie_motor"),
            "valor": peticion.datos.get("valor"),
            "justificacion": str(peticion.exige("justificacion")),
            "motivo": motivo,
        },
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"variable": variable}, eventos=(evento,))


def corregir_dato(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Resuelve un conflicto o corrige un dato, con justificacion obligatoria (P4, `R-UI-04`)."""
    return _correccion(peticion, servicios, capacidad, rol, motivo="conflicto o correccion")


def resolver_desacuerdo(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Resuelve un desacuerdo entre extractores (P2). Misma correccion humana, otro motivo."""
    return _correccion(peticion, servicios, capacidad, rol, motivo="desacuerdo entre extractores")


def enviar_subsanacion(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Envia al cliente la subsanacion redactada por un agente, despues de que un humano la revise (P7)."""
    if ORIGEN_INTERNO not in ORIGENES_SUBSANACION:  # pragma: no cover - guarda del catalogo
        raise ErrorApi(f"{capacidad.id}: origen de subsanacion desconocido")
    evento = escribir(
        log_de(peticion, servicios),
        "SubsanacionSolicitada",
        {
            **_marca(capacidad),
            "origen": ORIGEN_INTERNO,
            "texto": str(peticion.exige("texto")),
            "destinatario": peticion.texto("destinatario"),
        },
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"origen": ORIGEN_INTERNO}, eventos=(evento,))


def confirmar_interpretacion(
    peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str
) -> Salida:
    """Un humano hace suya la interpretacion de un requerimiento; solo entonces reabre (P9, `R-REQ-02`).

    Delega entera en `engine.requerimientos`: `confirmar` marca la propuesta y `reabrir` sella los dos
    eventos (la confirmacion y el hecho que mueve el ciclo a `PENDIENTE_SUBSANACION`). Aqui no se decide
    nada de eso.
    """
    requerimiento_id = str(peticion.exige("requerimiento_id"))
    par = servicios.repositorio.requerimiento(peticion.actuacion_id, requerimiento_id)
    if par is None:
        raise ErrorApi(
            f"{capacidad.id}: no hay requerimiento {requerimiento_id!r} con interpretacion propuesta en "
            f"la actuacion {peticion.actuacion_id!r}"
        )
    requerimiento, propuesta = par
    actor = actor_de(peticion.principal, rol)
    try:
        confirmada = confirmar(propuesta, actor=actor)
        eventos = reabrir(
            log_de(peticion, servicios),
            requerimiento,
            confirmada,
            actor=actor,
            confirmado_en=instante_de(servicios),
        )
    except ErrorRequerimiento as exc:
        raise ErrorApi(f"{capacidad.id}: {exc}") from exc
    return Salida(
        datos={"requerimiento_id": requerimiento_id, "reglas": list(confirmada.reglas)},
        eventos=tuple(eventos),
    )


def revisar_observacion(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Da por revisada una observacion de pre-revision (P6). No mueve el ciclo: deja constancia."""
    observacion = str(peticion.exige("observacion_id"))
    evento = escribir(
        log_de(peticion, servicios),
        "ObservacionRevisada",
        {**_marca(capacidad), "observacion_id": observacion, "comentario": peticion.texto("comentario")},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"observacion_id": observacion}, eventos=(evento,))


def confirmar_descarte(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Confirma el descarte de una actuacion no elegible.

    Las dos condiciones (veredicto no elegible y acto humano) las comprueba la maquina de estados, que es
    donde tienen que estar: aqui no se decide si se puede descartar.
    """
    evento = escribir(
        log_de(peticion, servicios),
        "ActuacionDescartada",
        {**_marca(capacidad), "motivo": str(peticion.exige("motivo"))},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"estado": "descartada"}, eventos=(evento,))


def aprobar_revision(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Aprueba la revision humana, que es la mitad de la guarda de `LISTA_PARA_ENVIO` (`docs/03` §7.3).

    No aprueba el envio ni fija un veredicto: marca que una persona reviso. Si quedan bloqueantes, la
    guarda del empaquetado se encarga.
    """
    evento = escribir(
        log_de(peticion, servicios),
        "RevisionAprobada",
        {**_marca(capacidad), "comentario": peticion.texto("comentario")},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"revisada_por_humano": True}, eventos=(evento,))


def resolver_discrepancia(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Decide ante una discrepancia entre nuestro calculo y el de la plataforma, con justificacion.

    La decision es de la persona y queda escrita con su motivo; `api/` no compara cifras ni recalcula.
    """
    decision = str(peticion.exige("decision"))
    evento = escribir(
        log_de(peticion, servicios),
        "DiscrepanciaResuelta",
        {
            **_marca(capacidad),
            "decision": decision,
            "justificacion": str(peticion.exige("justificacion")),
        },
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"decision": decision}, eventos=(evento,))


def aprobar_expediente(peticion: Peticion, servicios: Servicios, capacidad: Capacidad, rol: str) -> Salida:
    """Aprueba la composicion del expediente antes de firmar. Se anota en cada actuacion que lo compone."""
    expediente = str(peticion.exige("expediente_id"))
    evento = escribir(
        log_de(peticion, servicios),
        "ExpedienteAprobado",
        {**_marca(capacidad), "expediente_id": expediente},
        peticion=peticion,
        servicios=servicios,
        rol=rol,
    )
    return Salida(datos={"expediente_id": expediente}, eventos=(evento,))


#: Nombre declarado en `engine/capacidades.yaml` → funcion que lo atiende.
MANEJADORES = {
    "abrir_actuacion": abrir_actuacion,
    "registrar_documento": registrar_documento,
    "corregir_dato": corregir_dato,
    "resolver_desacuerdo": resolver_desacuerdo,
    "enviar_subsanacion": enviar_subsanacion,
    "confirmar_interpretacion": confirmar_interpretacion,
    "revisar_observacion": revisar_observacion,
    "confirmar_descarte": confirmar_descarte,
    "aprobar_revision": aprobar_revision,
    "resolver_discrepancia": resolver_discrepancia,
    "aprobar_expediente": aprobar_expediente,
}

__all__ = ["MANEJADORES", "escribir", "instante_de", "log_de"]
