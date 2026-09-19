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
from decimal import Decimal

from api.permisos import ErrorApi
from engine.estados import proyectar
from engine.informe import (
    datos_consolidados,
    datos_en_conflicto,
    descargo_de,
    mensaje_de,
    motivo_sin_calculo,
    semaforo_de,
    texto_decimal,
)


@dataclass(frozen=True)
class Vista:
    """El material que la lectura ya trajo de `engine/`. Los bloques se construyen de aqui y de nada mas."""

    actuacion: object | None = None
    log: object | None = None
    logs: tuple[object, ...] = ()
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
    """Un `Decimal` sale como cadena canonica; el resto, tal cual. Nunca se convierte a coma flotante."""
    return texto_decimal(valor) if isinstance(valor, Decimal) else valor


# ---------------------------------------------------------------------------
# Los bloques
# ---------------------------------------------------------------------------


def _identificacion(vista: Vista) -> Mapping[str, object]:
    actuacion = vista.exige_actuacion("identificacion")
    return {
        "actuacion_id": getattr(actuacion, "id", None),
        "codigo_identificativo_propio": getattr(actuacion, "codigo_identificativo_propio", None),
        "ficha": getattr(getattr(actuacion, "spec", None), "codigo", None),
        "fecha_evaluacion": str(getattr(actuacion, "fecha_evaluacion", "")) or None,
    }


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
    return [{"num_serie_motor": serie, **dato.a_dict()} for serie, dato in datos_consolidados(actuacion)]


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


def _calculo(vista: Vista) -> Mapping[str, object]:
    actuacion = vista.exige_actuacion("calculo")
    calculo = getattr(actuacion, "calculo", None)
    if calculo is None or calculo.total is None:
        return {
            "total_exacto": None,
            "total_cae": None,
            "provisional": False if calculo is None else bool(calculo.provisional),
            "motivo_no_calculo": motivo_sin_calculo(actuacion),
            "por_unidad": [],
        }
    return {
        "total_exacto": texto_decimal(calculo.total),
        "total_cae": calculo.total_cae,
        "provisional": bool(calculo.provisional),
        "motivo_no_calculo": None,
        "por_unidad": [
            {
                "num_serie_motor": unidad.num_serie_motor,
                "salida": None if unidad.salida is None else texto_decimal(unidad.salida),
                "motivo_no_calculo": unidad.motivo_no_calculo,
                "entradas": {k: _texto(v) for k, v in unidad.entradas.items()},
                "derivadas": {k: _texto(v) for k, v in unidad.derivadas.items()},
                "fuentes": dict(unidad.fuentes),
            }
            for unidad in calculo.por_unidad
        ],
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


def _estados_plataforma(vista: Vista) -> Mapping[str, object]:
    """Lo que el log dice del ciclo y del estado de plataforma. `api/` no decide ninguna transicion."""
    log = vista.exige_log("estados_plataforma")
    return proyectar(log).a_dict()


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


__all__ = ["CONSTRUCTORES", "Vista", "bloques_a_construir", "proyectar_vista"]
