/**
 * Como se nombra en castellano cada uno de los cinco motivos de `T-REV-cola` §6.
 *
 * Es **presentacion y solo presentacion**. Quien decide que motivos tiene una fila, con que prioridad y
 * en que orden va la fila, es el servidor (`ADR-014` §2, contrato C22); aqui se traduce un identificador
 * a un rotulo y se le pega el detalle que ya venia en la respuesta. No se deduce ningun motivo, no se
 * calcula ninguna severidad y no se reordena nada (`R-UI-11`).
 *
 * Un identificador que no este en esta tabla **se pinta tal cual llego**. Un motivo que la pantalla no
 * reconoce es un motivo que alguien tiene que mirar, no una fila silenciosa.
 *
 * `R-UI-09`: el nombre de la variable en conflicto no es un valor extraido. Los dos valores enfrentados
 * y sus cuatro evidencias estan una pulsacion mas alla, en la vista de revision.
 */

import { lista, objeto, texto, textos } from "../json";
import {
  MOTIVO_CONFLICTO,
  MOTIVO_CORRECCION,
  MOTIVO_ESCALADO,
  MOTIVO_REQUERIMIENTO,
  MOTIVO_TAREA,
} from "../textos";
import type { MotivoCola } from "./datos";

/** Identificador que sirve `api/` → rotulo. Los identificadores son los de `api/proyeccion.py`. */
export const ROTULOS: Readonly<Record<string, string>> = {
  conflicto: MOTIVO_CONFLICTO,
  escalado: MOTIVO_ESCALADO,
  requerimiento_abierto: MOTIVO_REQUERIMIENTO,
  correccion_pendiente: MOTIVO_CORRECCION,
  tarea_plataforma: MOTIVO_TAREA,
};

function variablesEnConflicto(detalle: Readonly<Record<string, unknown>>): string {
  const nombres = lista(detalle["variables"]).map((cruda) => {
    const variable = objeto(cruda);
    const nombre = texto(variable?.["variable"]);
    const unidad = texto(variable?.["num_serie_motor"]);
    if (nombre === null) {
      return null;
    }
    return unidad === null ? nombre : `${nombre} (${unidad})`;
  });
  return nombres.filter((nombre): nombre is string => nombre !== null).join(", ");
}

/**
 * El rotulo de un motivo, con lo que el servidor conto de el.
 *
 * "Conflicto en PM (MTR-SYN-0001)", "Corrección pendiente (SUBSANABLE)", "Requerimiento abierto
 * REQ-2026-014". El detalle **no se inventa**: si el servidor no lo manda, el rotulo se queda en el
 * nombre del motivo.
 */
export function rotuloDe(motivo: MotivoCola): string {
  const rotulo = ROTULOS[motivo.motivo] ?? motivo.motivo;
  const detalle = motivo.detalle;

  if (motivo.motivo === "conflicto") {
    const variables = variablesEnConflicto(detalle);
    return variables === "" ? rotulo : `${rotulo} en ${variables}`;
  }
  if (motivo.motivo === "correccion_pendiente") {
    const severidad = texto(detalle["severidad"]);
    return severidad === null ? rotulo : `${rotulo} (${severidad})`;
  }
  if (motivo.motivo === "requerimiento_abierto") {
    const requerimiento = texto(detalle["requerimiento_abierto"]);
    return requerimiento === null ? rotulo : `${rotulo} ${requerimiento}`;
  }
  if (motivo.motivo === "escalado") {
    const estado = texto(detalle["estado_ciclo"]);
    const literales = textos(detalle["literales_desconocidos"]).join(", ");
    const detalles = [estado, literales === "" ? null : literales].filter(
      (parte): parte is string => parte !== null,
    );
    return detalles.length === 0 ? rotulo : `${rotulo} (${detalles.join(" · ")})`;
  }
  if (motivo.motivo === "tarea_plataforma") {
    const tareas = textos(detalle["tareas"]).join(", ");
    return tareas === "" ? rotulo : `${rotulo} · ${tareas}`;
  }
  return rotulo;
}
