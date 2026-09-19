import { describe, expect, it } from "vitest";

import { AUSENTES, CEROS } from "./casos";
import { resolverPresentacion, type MetricaPresentable } from "../src/valores";

describe("resolverPresentacion", () => {
  it.each(AUSENTES)("%s se resuelve como SIN_DATO", (_nombre, metrica) => {
    expect(resolverPresentacion(metrica).clase).toBe("SIN_DATO");
  });

  it.each(CEROS)("%s se resuelve como dato", (_nombre, metrica, esperado) => {
    expect(resolverPresentacion(metrica)).toEqual({ clase: "CON_DATO", texto: esperado });
  });

  it("no reformatea un Decimal: lo pinta tal y como lo envio el servidor", () => {
    const metrica: MetricaPresentable = {
      estado: "CON_DATO",
      valor: "305.829,6",
      unidad: "kWh/año",
    };
    expect(resolverPresentacion(metrica)).toEqual({
      clase: "CON_DATO",
      texto: "305.829,6 kWh/año",
    });
  });

  it("conserva el entregable del que depende una metrica sin fuente", () => {
    expect(resolverPresentacion({ estado: "SIN_DATO", desde: "S3.5" })).toEqual({
      clase: "SIN_DATO",
      desde: "S3.5",
    });
  });

  it("una unidad vacia no deja un espacio colgando detras de la cifra", () => {
    expect(resolverPresentacion({ estado: "CON_DATO", valor: 12, unidad: "  " })).toEqual({
      clase: "CON_DATO",
      texto: "12",
    });
  });
});
