"""Proyeccion de una lectura: **construir solo lo que el ambito del rol admite** (`R-UI-12`).

La regla, literal de `ADR-011` §4: *el filtrado es de serializacion, no de pintado*. Una lectura de un
perfil externo **no construye** los campos que estan fuera de su ambito; no basta con que el front no los
muestre. Aqui eso es una sola linea, `bloques_a_construir`, y todo lo demas se apoya en ella: si un bloque
no esta en la interseccion entre lo que la capacidad proyecta y lo que el ambito admite, su constructor no
se llama. No se construye y se borra: no se construye.

Que bloques existen lo dice `CONSTRUCTORES`; quien puede ver cada uno, `engine/capacidades.yaml`. Los dos
lados se contrastan en un test: un bloque declarado en la matriz sin constructor es configuracion muerta, y
un constructor que ningun ambito admite no lo veria nadie.

Ningun bloque calcula nada (`R-UI-11` aguas arriba): todos leen lo que `engine/` ya decidio — el veredicto,
el ahorro, las carencias, las tres capas de cada dato — y lo ordenan para el transporte. Los `Decimal` se
serializan como cadena con el mismo criterio del nucleo (`engine.informe.texto_decimal`), nunca como
coma flotante.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from api.permisos import ErrorApi
from engine.calculo import a_dict as calculo_a_dict
from engine.estados import proyectar
from engine.informe import (
    datos_consolidados,
    datos_en_conflicto,
    descargo_de,
    mensaje_de,
    motivo_sin_calculo,
    semaforo_de,
    texto_decimal,
    texto_es,
)
from engine.seguimiento import TIPO_TAREA
from engine.spec_registry import CALCULO_POR_UNIDAD, CALCULO_TOTAL, SEVERIDADES

#: El estado de ciclo que significa "aqui tiene que mirar una persona" (`T-REV-cola` §6, motivo escalado).
#: Es vocabulario de `engine.estados`, no una decision de `api/`: un test comprueba que sigue existiendo.
ESTADO_ESCALADO = "EN_REVISION_HUMANA"

#: Los cinco motivos por los que una actuacion esta en la cola, y su prioridad (`T-REV-cola` §6).
#: **La prioridad la aplica el servidor**: la pantalla no ordena (`R-UI-11`).
MOTIVO_CONFLICTO = "conflicto"
MOTIVO_ESCALADO = "escalado"
MOTIVO_REQUERIMIENTO = "requerimiento_abierto"
MOTIVO_CORRECCION = "correccion_pendiente"
MOTIVO_TAREA = "tarea_plataforma"
PRIORIDAD_MOTIVO: Mapping[str, int] = {
    MOTIVO_CONFLICTO: 1,
    MOTIVO_ESCALADO: 2,
    MOTIVO_REQUERIMIENTO: 2,
    MOTIVO_CORRECCION: 3,
    MOTIVO_TAREA: 4,
}

#: Lo que la spec declara de una variable y que la pantalla necesita para **nombrarla** (`GAP-REV-05`).
#: Sale de `spec.variables[...]`, que es configuracion: no hay ningun diccionario de etiquetas por ficha
#: en ninguna parte, porque seria un `if ficha == ...` disfrazado (regla de oro 4).
CAMPOS_VARIABLE = ("descripcion", "definicion", "referencia", "unidad")

#: Antes de cualquier evento: el lugar de las actuaciones sin historial al ordenar la cola (van al final).
_SIN_FECHA = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Caso:
    """Una actuacion del tenant con lo que una lectura de lista necesita de ella: la procesada y su log.

    `actuacion` es `None` cuando el repositorio la conoce y el motor todavia no la ha procesado: la cola
    la sigue enumerando con lo que el log si dice, en vez de esconderla.
    """

    actuacion_id: str
    actuacion: object | None = None
    log: object | None = None


@dataclass(frozen=True)
class Vista:
    """El material que la lectura ya trajo de `engine/`. Los bloques se construyen de aqui y de nada mas."""

    actuacion: object | None = None
    log: object | None = None
    logs: tuple[object, ...] = ()
    #: Varias actuaciones del tenant, para las lecturas de lista (`ADR-014` §2, C22).
    casos: tuple[Caso, ...] = ()
    #: Tipos de evento a los que se limitan los bloques que resumen o auditan. Vacio = todos.
    tipos: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()

    def eventos(self):
        """Los eventos de todos los logs de la vista, filtrados por `tipos` si la lectura los acota."""
        for log in self.logs:
            for evento in log:
                if not self.tipos or evento.tipo in self.tipos:
                    yield evento

    def exige_actuacion(self, bloque: str) -> object:
        if self.actuacion is None:
            raise ErrorApi(f"el bloque {bloque!r} necesita una actuacion procesada y la vista no la trae")
        return self.actuacion

    def exige_log(self, bloque: str) -> object:
        if self.log is None:
            raise ErrorApi(f"el bloque {bloque!r} necesita el log de la actuacion y la vista no lo trae")
        return self.log


def _texto(valor: object) -> object:
    """Un `Decimal` sale como cadena canonica y una fecha en ISO; el resto, tal cual. Nunca como `float`."""
    if isinstance(valor, Decimal):
        return texto_decimal(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Mapping):
        return {str(clave): _texto(v) for clave, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_texto(v) for v in valor]
    return valor


def _presentable(canonico: object) -> str | None:
    """La misma cifra en español, **junto a la exacta y nunca en su lugar** (`GAP-COLA-04`/`GAP-REV-08`).

    Entra la forma canonica que ya sirve el bloque (una cadena) y sale la que lee una persona. El paso
    intermedio es `Decimal`, nunca `float`: el ahorro no pasa por coma flotante (`CLAUDE.md` §2).
    """
    if not isinstance(canonico, str):
        return None
    try:
        return texto_es(Decimal(canonico))
    except InvalidOperation:
        return None


def _declaracion(actuacion: object, variable: str) -> dict[str, object]:
    """Lo que la spec dice de una variable: su nombre legible, su definicion, su referencia y su unidad.

    `GAP-REV-05`. Se lee de `spec.variables[...]` —configuracion— igual que hace `engine/correcciones.py`.
    Una variable que la spec no declara sale con todo a `None`: no se inventa un nombre.
    """
    variables = getattr(getattr(actuacion, "spec", None), "variables", None)
    declarada = variables.get(variable) if isinstance(variables, Mapping) else None
    if not isinstance(declarada, Mapping):
        return dict.fromkeys(CAMPOS_VARIABLE)
    return {campo: declarada.get(campo) for campo in CAMPOS_VARIABLE}


def _unidad_declarada(actuacion: object, bloque: str) -> str | None:
    """En que unidad expresa la spec una salida del calculo: `spec.calculo.<bloque>.unidad`.

    Mismo criterio que `_declaracion`, y por la misma razon (`GAP-REV-05`, regla de oro 4): la unidad es
    configuracion de la ficha. Que la escribiera la pantalla seria una etiqueta por ficha cableada en la
    interfaz —un `if ficha == ...` disfrazado— y la segunda ficha, con otra unidad, la desmentiria.

    Es un rotulo, no una cifra: no participa en ninguna aritmetica y no convierte nada. El ahorro sigue
    viajando en `total_exacto`/`salida` tal y como lo dejo el nucleo, sin pasar por coma flotante.

    Una spec que no declare la unidad de ese bloque sale a `None`, que es lo que la pantalla pinta como
    `SIN DATO`: no se inventa una unidad ni se hereda la de otra ficha.
    """
    calculo = getattr(getattr(actuacion, "spec", None), "calculo", None)
    declarado = calculo.get(bloque) if isinstance(calculo, Mapping) else None
    if not isinstance(declarado, Mapping):
        return None
    unidad = declarado.get("unidad")
    return None if unidad is None else str(unidad)


# ---------------------------------------------------------------------------
# Los bloques
# ---------------------------------------------------------------------------


def _identidad(actuacion: object | None, actuacion_id: str | None = None) -> Mapping[str, object]:
    """La identificacion de una actuacion, tambien cuando el motor no la ha procesado todavia.

    En una lista manda el identificador con el que la pidio el repositorio, que es con el que la pantalla
    va a poder volver a pedirla: navegar con los identificadores que dio la lectura, y no componerlos, es
    `R-UI-12`. Con una sola actuacion no hay tal identificador y se usa el que trae la procesada.
    """
    return {
        "actuacion_id": actuacion_id or getattr(actuacion, "id", None),
        "codigo_identificativo_propio": getattr(actuacion, "codigo_identificativo_propio", None),
        "ficha": getattr(getattr(actuacion, "spec", None), "codigo", None),
        "fecha_evaluacion": str(getattr(actuacion, "fecha_evaluacion", "")) or None,
    }


def _identificacion(vista: Vista) -> Mapping[str, object]:
    return _identidad(vista.exige_actuacion("identificacion"))


def _estado_simplificado(vista: Vista) -> Mapping[str, object]:
    """Lo que se le puede decir a quien no es tecnico: el semaforo y el mensaje que declara la spec.

    Ni el veredicto ni las reglas falladas: los textos son los de `spec.estados`, no unos nuestros.
    """
    actuacion = vista.exige_actuacion("estado_simplificado")
    return {"semaforo": semaforo_de(actuacion), "mensaje": mensaje_de(actuacion)}


def _que_te_falta(vista: Vista) -> Mapping[str, object]:
    actuacion = vista.exige_actuacion("que_te_falta")
    evaluacion = getattr(actuacion, "evaluacion", None)
    carencias = list(getattr(evaluacion, "carencias", []) or [])
    return {"carencias": [dict(c) for c in carencias], "hay_carencias": bool(carencias)}


def _documentos(vista: Vista) -> Sequence[Mapping[str, object]]:
    actuacion = vista.exige_actuacion("documentos")
    return [documento.a_dict() for documento in getattr(actuacion, "documentos", [])]


def _evidencias(vista: Vista) -> Sequence[Mapping[str, object]]:
    """Las tres capas de cada dato, con su cita (`R-UI-09`): documento, pagina y texto literal."""
    actuacion = vista.exige_actuacion("evidencias")
    return [
        {**_declaracion(actuacion, dato.variable), "num_serie_motor": serie, **dato.a_dict()}
        for serie, dato in datos_consolidados(actuacion)
    ]


def _conflictos(vista: Vista) -> Sequence[Mapping[str, object]]:
    """Conflicto = las dos evidencias enfrentadas y `valor_consumido` nulo. El motor no elige (regla 6)."""
    actuacion = vista.exige_actuacion("conflictos")
    return [
        {
            "variable": dato.variable,
            "num_serie_motor": dato.num_serie_motor,
            "valor_consumido": None,
            "evidencias": [evidencia.a_dict() for evidencia in dato.evidencias],
        }
        for dato in datos_en_conflicto(actuacion)
    ]


def _unidad(unidad: Mapping[str, object], *, unidad_salida: str | None) -> Mapping[str, object]:
    """Una unidad del calculo, ya serializada por el nucleo, con su traza de controles (`GAP-REV-09`).

    `controles` y `precondiciones` traen `true`, `false` o `"NO_EVALUABLE"`: ese ultimo es el centinela de
    `engine.expresiones`, no un booleano, y se serializa como lo hace el informe del nucleo.

    `unidad_salida` es la unidad en que la spec expresa el ahorro por unidad (`calculo.motor.unidad`), y
    rotula por igual `salida` y `salida_presentable`: la cifra exacta y la misma cifra en español.
    """
    entradas = dict(unidad.get("entradas") or {})
    derivadas = dict(unidad.get("derivadas") or {})
    salida = unidad.get("salida")
    return {
        "num_serie_motor": unidad.get("num_serie_motor"),
        "salida": salida,
        "salida_presentable": _presentable(salida),
        "salida_unidad": unidad_salida,
        "motivo_no_calculo": unidad.get("motivo_no_calculo"),
        "entradas": entradas,
        "entradas_presentables": {k: _presentable(v) for k, v in entradas.items()},
        "derivadas": derivadas,
        "derivadas_presentables": {k: _presentable(v) for k, v in derivadas.items()},
        "fuentes": dict(unidad.get("fuentes") or {}),
        "controles": dict(unidad.get("controles") or {}),
        "precondiciones": dict(unidad.get("precondiciones") or {}),
        "interpretaciones": list(unidad.get("interpretaciones") or []),
        "avisos": list(unidad.get("avisos") or []),
    }


def _variables_del_calculo(
    actuacion: object, unidades: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    """Como se llama cada entrada y cada derivada del calculo, segun la spec (`GAP-REV-05`).

    Va al lado de `por_unidad` y no dentro de `entradas` para no cambiar la forma de lo que ya se sirve:
    la pantalla busca aqui el nombre legible de `PM` en vez de llevar una tabla de etiquetas por ficha.
    """
    nombres: set[str] = set()
    for unidad in unidades:
        nombres |= set(unidad.get("entradas") or {})
        nombres |= set(unidad.get("derivadas") or {})
    return {nombre: _declaracion(actuacion, nombre) for nombre in sorted(nombres)}


def _calculo(vista: Vista) -> Mapping[str, object]:
    actuacion = vista.exige_actuacion("calculo")
    calculo = getattr(actuacion, "calculo", None)
    serializado = calculo_a_dict(calculo) if calculo is not None else {}
    unidades = list(serializado.get("por_unidad") or [])
    hay_total = calculo is not None and calculo.total is not None
    cae = calculo.total_cae if hay_total else None
    unidad_salida = _unidad_declarada(actuacion, CALCULO_POR_UNIDAD)
    return {
        "total_exacto": texto_decimal(calculo.total) if hay_total else None,
        "total_exacto_presentable": texto_es(calculo.total) if hay_total else None,
        "total_cae": cae,
        "total_cae_presentable": None if cae is None else texto_es(cae),
        # La unidad de las cuatro cifras de arriba, leida de `spec.calculo.total.unidad`. Rotula igual la
        # forma canonica y la presentable, porque son la misma magnitud. El valor truncado a entero
        # (`total_cae`) tambien: la spec no declara para el una unidad distinta y no se le inventa una.
        "total_unidad": _unidad_declarada(actuacion, CALCULO_TOTAL),
        "provisional": False if calculo is None else bool(calculo.provisional),
        "motivo_no_calculo": None if hay_total else motivo_sin_calculo(actuacion),
        "traza": list(serializado.get("traza") or []),
        "variables": _variables_del_calculo(actuacion, unidades),
        "por_unidad": [_unidad(unidad, unidad_salida=unidad_salida) for unidad in unidades],
    }


def _veredicto(vista: Vista) -> Mapping[str, object]:
    actuacion = vista.exige_actuacion("veredicto")
    evaluacion = getattr(actuacion, "evaluacion", None)
    return {
        "valor": getattr(actuacion, "veredicto", None),
        "semaforo": semaforo_de(actuacion),
        "mensaje": mensaje_de(actuacion),
        "descargo": descargo_de(actuacion),
        "reglas_falladas": list(getattr(evaluacion, "falladas", []) or []),
        "reglas_no_evaluables": list(getattr(evaluacion, "no_evaluables", []) or []),
        # `GAP-REV-02`: las 24 comprobaciones con lo que cada una dice de si misma (severidad, fase,
        # nivel, descripcion, referencia, interpretacion, motivo y el detalle por unidad). Los
        # identificadores de arriba se quedan porque son el indice; esto es lo que se lee.
        "reglas": [r.a_dict() for r in getattr(evaluacion, "resultados", []) or []],
        "interpretaciones_aplicadas": list(getattr(evaluacion, "interpretaciones_aplicadas", []) or []),
        "hash_reglas": getattr(evaluacion, "hash_reglas", None),
    }


def _fila_evento(evento: object, *, con_payload: bool) -> Mapping[str, object]:
    fila: dict[str, object] = {
        "evento_id": evento.evento_id,
        "actuacion_id": evento.actuacion_id,
        "secuencia": evento.secuencia,
        "tipo": evento.tipo,
        "ocurrido_en": evento.ocurrido_en.isoformat(),
        "actor": evento.actor.a_dict(),
    }
    if con_payload:
        fila["payload"] = dict(evento.payload)
    return fila


def _historial(vista: Vista) -> Sequence[Mapping[str, object]]:
    log = vista.exige_log("historial")
    return [_fila_evento(evento, con_payload=True) for evento in log]


def _tarea(evento: object) -> Mapping[str, object]:
    """Una tarea pendiente del tenant tal y como la anoto la plataforma. Se refleja, no se interpreta."""
    datos = dict(evento.datos)
    return {
        "tarea_id": datos.get("tarea_id"),
        "asunto": datos.get("asunto"),
        "referencia": datos.get("referencia"),
        "vence_en": _texto(datos.get("vence_en")),
        "recibida_en": evento.ocurrido_en.isoformat(),
    }


def _estado_del_log(log: object) -> dict[str, object]:
    """La proyeccion del ciclo, mas las tareas y las dos marcas de tiempo del log (`GAP-COLA-02`).

    Es **proyeccion, no calculo**: `engine.estados` sigue decidiendo las transiciones y aqui solo se leen
    eventos que ya estan sellados. `abierta_en` y `ultimo_movimiento_en` son el primero y el ultimo del
    log por secuencia; sin eventos son `None`, que es lo que la pantalla pinta como `SIN DATO`, nunca 0.
    """
    datos = dict(proyectar(log).a_dict())
    eventos = sorted(log, key=lambda evento: evento.secuencia)
    datos["tareas_pendientes"] = [_tarea(evento) for evento in log.por_tipo(TIPO_TAREA)]
    datos["abierta_en"] = eventos[0].ocurrido_en.isoformat() if eventos else None
    datos["ultimo_movimiento_en"] = eventos[-1].ocurrido_en.isoformat() if eventos else None
    return datos


def _estados_plataforma(vista: Vista) -> Mapping[str, object]:
    """Lo que el log dice del ciclo y del estado de plataforma. `api/` no decide ninguna transicion."""
    return _estado_del_log(vista.exige_log("estados_plataforma"))


# ---------------------------------------------------------------------------
# La cola de revision (`ADR-014` §2, C22)
# ---------------------------------------------------------------------------


def _motivo(identificador: str, **detalle: object) -> dict[str, object]:
    return {
        "motivo": identificador,
        "prioridad": PRIORIDAD_MOTIVO[identificador],
        "detalle": dict(detalle),
    }


def _severidad_mayor(carencias: Sequence[Mapping[str, object]]) -> str | None:
    """La severidad mas alta de las carencias, en el orden que declara la spec. No se ordena a mano."""
    orden = {severidad: posicion for posicion, severidad in enumerate(SEVERIDADES)}
    presentes = [str(c.get("severidad")) for c in carencias if str(c.get("severidad")) in orden]
    return min(presentes, key=lambda severidad: orden[severidad]) if presentes else None


def _motivos(actuacion: object | None, estado: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Por que esta esta actuacion en la cola. Los cinco de `T-REV-cola` §6, ni uno mas.

    Una fila sin ningun motivo **no entra en la cola**: la cola reparte trabajo, y una actuacion sin nada
    que hacer no es trabajo. Nada de esto se calcula: se lee del veredicto, de las carencias y del log.
    """
    motivos: list[Mapping[str, object]] = []
    conflictos = [] if actuacion is None else datos_en_conflicto(actuacion)
    if conflictos:
        motivos.append(
            _motivo(
                MOTIVO_CONFLICTO,
                # El nombre de la variable en conflicto **no es un valor**: los dos valores enfrentados y
                # sus citas viven una pulsacion mas alla, en la vista de revision (`R-UI-09`).
                variables=[
                    {"variable": dato.variable, "num_serie_motor": dato.num_serie_motor}
                    for dato in conflictos
                ],
            )
        )
    literales = list(estado.get("literales_desconocidos") or ())
    if estado.get("estado_ciclo") == ESTADO_ESCALADO or literales:
        motivos.append(
            _motivo(
                MOTIVO_ESCALADO,
                estado_ciclo=estado.get("estado_ciclo"),
                literales_desconocidos=literales,
            )
        )
    if estado.get("requerimiento_abierto") is not None:
        motivos.append(
            _motivo(
                MOTIVO_REQUERIMIENTO,
                requerimiento_abierto=estado.get("requerimiento_abierto"),
                afectada_directamente=estado.get("afectada_directamente"),
                origen_subsanacion=estado.get("origen_subsanacion"),
            )
        )
    evaluacion = getattr(actuacion, "evaluacion", None)
    carencias = list(getattr(evaluacion, "carencias", []) or [])
    if carencias:
        motivos.append(
            _motivo(
                MOTIVO_CORRECCION,
                severidad=_severidad_mayor(carencias),
                carencias=[str(c.get("id")) for c in carencias],
            )
        )
    tareas = list(estado.get("tareas_pendientes") or ())
    if tareas:
        motivos.append(_motivo(MOTIVO_TAREA, tareas=[tarea.get("tarea_id") for tarea in tareas]))
    return sorted(motivos, key=lambda motivo: motivo["prioridad"])


def _veredicto_en_cola(actuacion: object | None) -> Mapping[str, object]:
    """El veredicto como rotulo (`R-UI-02`), sin las reglas: la cola no explica, reparte."""
    if actuacion is None:
        return {"valor": None, "semaforo": None, "mensaje": None}
    return {
        "valor": getattr(actuacion, "veredicto", None),
        "semaforo": semaforo_de(actuacion),
        "mensaje": mensaje_de(actuacion),
    }


def _fila_cola(caso: Caso) -> tuple[tuple[object, ...], Mapping[str, object]] | None:
    """Una fila de la cola con su clave de orden, o `None` si esa actuacion no tiene nada que esperar."""
    estado = _estado_del_log(caso.log) if caso.log is not None else {}
    motivos = _motivos(caso.actuacion, estado)
    if not motivos:
        return None
    eventos = sorted(caso.log, key=lambda evento: evento.secuencia) if caso.log is not None else []
    abierta = eventos[0].ocurrido_en if eventos else None
    fila = {
        "identificacion": _identidad(caso.actuacion, caso.actuacion_id),
        "veredicto": _veredicto_en_cola(caso.actuacion),
        "motivos": motivos,
        "antiguedad": {
            "abierta_en": estado.get("abierta_en"),
            "ultimo_movimiento_en": estado.get("ultimo_movimiento_en"),
        },
        "estado": {
            clave: estado.get(clave)
            for clave in (
                "estado_ciclo",
                "estado_plataforma",
                "requerimiento_abierto",
                "afectada_directamente",
                "literales_desconocidos",
                "secuencia",
            )
        },
    }
    clave = (
        min(int(motivo["prioridad"]) for motivo in motivos),
        abierta is None,
        abierta or _SIN_FECHA,
        str(caso.actuacion_id),
    )
    return clave, fila


def _cola(vista: Vista) -> Sequence[Mapping[str, object]]:
    """Las actuaciones del tenant que esperan revision, **ya ordenadas** (`T-REV-cola` §6).

    Primero el motivo de mas prioridad de cada fila, despues la que lleva mas tiempo abierta, y el
    identificador para que dos iguales no bailen entre peticiones. El orden lo pone el servidor porque la
    pantalla no ordena (`R-UI-11`), y porque un orden que cada cliente calcula no se puede verificar.

    Cada fila lleva identificacion, veredicto, motivos, antiguedad y estado. **Nada mas**: ni un valor de
    variable, ni su cita, ni el ahorro. Arrastrar la cita (`R-UI-09`) a una lista que se lee de un vistazo
    es justo lo que la spec de la pantalla evita a proposito.
    """
    filas = [preparada for caso in vista.casos if (preparada := _fila_cola(caso)) is not None]
    return [fila for _, fila in sorted(filas, key=lambda preparada: preparada[0])]


def _actividad_usuarios(vista: Vista) -> Sequence[Mapping[str, object]]:
    """Quien hizo que y cuando en el tenant, sin payloads. `R-UI-10`: el tenant avisa a los suyos."""
    return [_fila_evento(evento, con_payload=False) for evento in vista.eventos()]


def _metadatos_auditoria(vista: Vista) -> Sequence[Mapping[str, object]]:
    """Auditoria global: metadatos, nunca contenido documental de un tenant (`ADR-006`, ambito global)."""
    return [_fila_evento(evento, con_payload=False) for evento in vista.eventos()]


def _agregados(vista: Vista) -> Mapping[str, object]:
    """Cuentas, no contenido. Lo unico que el ambito global admite ver de todos los tenants a la vez."""
    por_tipo: dict[str, int] = {}
    for evento in vista.eventos():
        por_tipo[evento.tipo] = por_tipo.get(evento.tipo, 0) + 1
    return {
        "actuaciones": len(vista.logs),
        "tipos_observados": list(vista.tipos),
        "eventos_por_tipo": dict(sorted(por_tipo.items())),
    }


#: Bloque → como se construye. Las claves son las mismas que declara `engine/capacidades.yaml`; un test
#: contrasta los dos lados, igual que el simulador contrasta los literales de la tabla de plataforma.
CONSTRUCTORES: Mapping[str, Callable[[Vista], object]] = {
    "identificacion": _identificacion,
    "estado_simplificado": _estado_simplificado,
    "que_te_falta": _que_te_falta,
    "documentos": _documentos,
    "evidencias": _evidencias,
    "conflictos": _conflictos,
    "calculo": _calculo,
    "veredicto": _veredicto,
    "historial": _historial,
    "estados_plataforma": _estados_plataforma,
    "cola": _cola,
    "actividad_usuarios": _actividad_usuarios,
    "metadatos_auditoria": _metadatos_auditoria,
    "agregados": _agregados,
}


def bloques_a_construir(declarados: Sequence[str], admitidos: frozenset[str]) -> tuple[str, ...]:
    """Los bloques que la capacidad proyecta **y** el ambito del rol admite, en el orden declarado."""
    return tuple(bloque for bloque in declarados if bloque in admitidos)


def proyectar_vista(declarados: Sequence[str], admitidos: frozenset[str], vista: Vista) -> dict[str, object]:
    """Construye la respuesta de una lectura. Lo que no esta en la interseccion **no se construye**."""
    datos: dict[str, object] = {}
    for bloque in bloques_a_construir(declarados, admitidos):
        constructor = CONSTRUCTORES.get(bloque)
        if constructor is None:
            raise ErrorApi(f"el bloque {bloque!r} esta declarado en la matriz y no tiene constructor")
        datos[bloque] = constructor(vista)
    return datos


__all__ = ["CONSTRUCTORES", "Caso", "Vista", "bloques_a_construir", "proyectar_vista"]
