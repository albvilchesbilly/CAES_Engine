/**
 * Lo que la pantalla ensena cuando el servidor dice que no, o cuando no puede contestar.
 *
 * `R-UI-01` y la regla 2 del contrato C18 (`ADR-012` §3): **un error se muestra, no se traga**. Ocultar
 * la fila para no tener que ensenar un `ErrorPermiso` seria exactamente lo contrario de lo que esa regla
 * protege — un control que desaparece sin explicacion es un control que nadie arregla.
 *
 * Aqui no se interpreta el motivo del servidor: se transporta. La pantalla no sabe por que se deniega una
 * capacidad ni tiene ninguna tabla de permisos con la que adivinarlo (`R-UI-01`).
 */

import { ErrorApi, ErrorPermiso } from "@cae/compartido/api";

import { ERROR_DESCONOCIDO } from "./textos";

/** Denegacion del servidor o cualquier otro fallo. Se distinguen porque no significan lo mismo. */
export type ClaseFallo = "PERMISO" | "API";

export interface FalloServidor {
  readonly clase: ClaseFallo;
  /** La capacidad que se pidio, para que quien lea el aviso sepa que falta exactamente. */
  readonly capacidad: string;
  /** El motivo **literal** del servidor. No se resume ni se traduce. */
  readonly motivo: string;
  /** El mensaje ya compuesto en castellano por el cliente (`ERROR_PERMISO` / `ERROR_API` + motivo). */
  readonly mensaje: string;
}

/**
 * Traduce lo que levanto el cliente a lo que se pinta. Nunca devuelve `null`: todo fallo se ensena.
 *
 * Un fallo que no es ninguno de los dos tipados (un error de programacion del propio front, por ejemplo)
 * tampoco se calla: sale como `API` con lo que se sepa de el.
 */
export function falloDe(capacidad: string, causa: unknown): FalloServidor {
  if (causa instanceof ErrorPermiso) {
    return {
      clase: "PERMISO",
      capacidad: causa.capacidad,
      motivo: causa.motivo,
      mensaje: causa.mensaje,
    };
  }
  if (causa instanceof ErrorApi) {
    return { clase: "API", capacidad: causa.capacidad, motivo: causa.motivo, mensaje: causa.mensaje };
  }
  const motivo = causa instanceof Error && causa.message.trim() !== "" ? causa.message : ERROR_DESCONOCIDO;
  return { clase: "API", capacidad, motivo, mensaje: motivo };
}
