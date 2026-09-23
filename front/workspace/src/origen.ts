/**
 * De donde salen las cifras de un panel (`R-UI-08`), **mientras `api/` no lo diga**.
 *
 * `GAP-COLA-03` sigue abierto (`ADR-014` §6): ningun bloque declara si los datos son sinteticos o
 * reales, y no por falta de un campo —eso es trivial— sino porque en el sistema no existe todavia de
 * donde sacar el valor: no hay noción de tenant sintético ni bandera de despliegue. Billy tiene la
 * decision (`ADR-014` §7).
 *
 * Hasta entonces **no se elige un valor por defecto**. Asumir `SINTETICO` (que es lo que hay hoy) o
 * `REAL` (que es lo que habra) convierte un olvido en una afirmacion, y el riesgo que `R-UI-08` cubre es
 * justo ese. `MarcaOrigen` ya sabe anunciar `ORIGEN DE DATOS SIN DECLARAR` cuando el origen no se
 * entiende, y eso es lo que se le da: el comportamiento honesto, no un defecto.
 *
 * El dia que `identificacion.origen_datos` exista, esta funcion lo encuentra y no hay nada mas que tocar.
 */

import type { OrigenDatos } from "@cae/compartido";

import { objeto, texto } from "./json";

/** El nombre del campo que `GAP-COLA-03` pide en `identificacion`. Hoy no lo sirve nadie. */
export const CAMPO_ORIGEN = "origen_datos";

/**
 * El centinela de "no declarado".
 *
 * No es un `OrigenDatos` valido y por eso hay una conversion: el tipo tiene **dos** valores a proposito
 * (`MarcaOrigen` no admite un tercero ni un defecto), y lo que se le entrega cuando nadie lo ha
 * declarado es precisamente algo que no reconoce, para que lo anuncie en voz alta.
 */
const SIN_DECLARAR = "SIN_DECLARAR" as unknown as OrigenDatos;

/** El origen que declare alguno de los bloques `identificacion` recibidos, o el centinela. */
export function origenDeclarado(...candidatos: readonly unknown[]): OrigenDatos {
  for (const candidato of candidatos) {
    const identificacion = objeto(candidato);
    const declarado = texto(identificacion?.[CAMPO_ORIGEN]);
    if (declarado === "SINTETICO" || declarado === "REAL") {
      return declarado;
    }
  }
  return SIN_DECLARAR;
}
