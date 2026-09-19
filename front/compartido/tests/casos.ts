import type { MetricaPresentable } from "../src/valores";

/**
 * Entradas que NO son un dato. Se prueban de forma adversarial: el servidor puede estar roto, el
 * payload puede venir de una version vieja de `api/` y TypeScript no mira nada en tiempo de ejecucion,
 * asi que todas entran por un `as unknown as` deliberado.
 */
export const AUSENTES: ReadonlyArray<readonly [string, MetricaPresentable]> = [
  ["estado SIN_DATO", { estado: "SIN_DATO" }],
  ["valor null", { estado: "CON_DATO", valor: null } as unknown as MetricaPresentable],
  ["valor undefined", { estado: "CON_DATO", valor: undefined } as unknown as MetricaPresentable],
  ["valor ausente", { estado: "CON_DATO" } as unknown as MetricaPresentable],
  ["cadena vacia", { estado: "CON_DATO", valor: "" }],
  ["cadena en blanco", { estado: "CON_DATO", valor: "   " }],
  ["NaN", { estado: "CON_DATO", valor: Number.NaN }],
  ["Infinity", { estado: "CON_DATO", valor: Number.POSITIVE_INFINITY }],
  ["-Infinity", { estado: "CON_DATO", valor: Number.NEGATIVE_INFINITY }],
  ["booleano", { estado: "CON_DATO", valor: false } as unknown as MetricaPresentable],
  ["objeto", { estado: "CON_DATO", valor: {} } as unknown as MetricaPresentable],
  ["lista vacia", { estado: "CON_DATO", valor: [] } as unknown as MetricaPresentable],
  ["estado desconocido", { estado: "PENDIENTE", valor: 7 } as unknown as MetricaPresentable],
  ["metrica null", null as unknown as MetricaPresentable],
  ["metrica undefined", undefined as unknown as MetricaPresentable],
  ["metrica que es un numero", 0 as unknown as MetricaPresentable],
];

/** Ceros de verdad y cifras que empiezan por cero: son datos y salen como datos. */
export const CEROS: ReadonlyArray<readonly [string, MetricaPresentable, string]> = [
  ["cero numerico", { estado: "CON_DATO", valor: 0 }, "0"],
  ["cero negativo", { estado: "CON_DATO", valor: -0 }, "0"],
  ["cero como cadena", { estado: "CON_DATO", valor: "0" }, "0"],
  ["cero con decimales", { estado: "CON_DATO", valor: "0,00" }, "0,00"],
  ["cero con unidad", { estado: "CON_DATO", valor: 0, unidad: "kWh/año" }, "0 kWh/año"],
];
