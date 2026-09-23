/**
 * Las dos formas en que se lee una marca de tiempo del servidor, y ninguna mas.
 *
 * `T-REV-cola` §5: **fecha absoluta siempre**, y "hace N días" como texto secundario. Sin marca de
 * tiempo se pinta `SIN DATO` (`R-UI-07`), nunca "0 días": un hueco no es un cero recien abierto.
 *
 * Dos decisiones que conviene leer antes de cambiar nada aqui:
 *
 * 1. **La fecha absoluta se compone del texto ISO que mando el servidor**, sin `Date` y sin cambiar de
 *    huso: lo que se ensena es lo que llego. Pasarla por el reloj del navegador la moveria de dia en
 *    cuanto alguien abriera la cola desde otro huso, y nadie habria decidido ese cambio.
 * 2. **Los dias se cuentan sobre las fechas de calendario en UTC**, con aritmetica entera. No es una
 *    magnitud del ahorro —eso jamas pasa por el front (`CLAUDE.md` §2)—, es cuanto lleva esperando una
 *    fila; aun asi se calcula sobre enteros, porque una resta de milisegundos partida a mano tiene la
 *    mala costumbre de devolver 0,9999 dias.
 */

import { ANTIGUEDAD_DIAS, ANTIGUEDAD_HOY, ANTIGUEDAD_UN_DIA } from "./textos";

const MARCA = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;
const MILISEGUNDOS_POR_DIA = 86_400_000;

interface MarcaLeida {
  readonly anio: number;
  readonly mes: number;
  readonly dia: number;
  readonly hora: string | null;
}

function leer(iso: unknown): MarcaLeida | null {
  if (typeof iso !== "string") {
    return null;
  }
  const trozos = MARCA.exec(iso.trim());
  if (trozos === null) {
    return null;
  }
  const [, anio, mes, dia, hora, minuto] = trozos;
  if (anio === undefined || mes === undefined || dia === undefined) {
    return null;
  }
  return {
    anio: Number.parseInt(anio, 10),
    mes: Number.parseInt(mes, 10),
    dia: Number.parseInt(dia, 10),
    hora: hora === undefined || minuto === undefined ? null : `${hora}:${minuto}`,
  };
}

/** `"2026-09-17T09:12:00+00:00"` → `"17/09/2026 09:12"`. `null` si no hay marca que leer. */
export function fechaAbsoluta(iso: unknown): string | null {
  const marca = leer(iso);
  if (marca === null) {
    return null;
  }
  const dia = String(marca.dia).padStart(2, "0");
  const mes = String(marca.mes).padStart(2, "0");
  const fecha = `${dia}/${mes}/${marca.anio}`;
  return marca.hora === null ? fecha : `${fecha} ${marca.hora}`;
}

/** Dias de calendario entre la marca y `ahora`, o `null` si no hay marca. Negativo si viene del futuro. */
export function diasDesde(iso: unknown, ahora: Date): number | null {
  const marca = leer(iso);
  if (marca === null || Number.isNaN(ahora.getTime())) {
    return null;
  }
  const entonces = Date.UTC(marca.anio, marca.mes - 1, marca.dia);
  const hoy = Date.UTC(ahora.getUTCFullYear(), ahora.getUTCMonth(), ahora.getUTCDate());
  return (hoy - entonces) / MILISEGUNDOS_POR_DIA;
}

/** El texto secundario de la antiguedad, o `null` si no hay marca (y entonces no se pinta nada). */
export function textoAntiguedad(iso: unknown, ahora: Date): string | null {
  const dias = diasDesde(iso, ahora);
  if (dias === null || dias < 0) {
    return null;
  }
  if (dias === 0) {
    return ANTIGUEDAD_HOY;
  }
  return dias === 1 ? ANTIGUEDAD_UN_DIA : ANTIGUEDAD_DIAS.replace("N", String(dias));
}
