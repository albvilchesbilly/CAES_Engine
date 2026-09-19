import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AUSENTES, CEROS } from "./casos";
import { ValorMetrica } from "../src/ValorMetrica";
import { SIN_DATO } from "../src/textos";
import type { MetricaPresentable } from "../src/valores";

afterEach(cleanup);

/** Lo que lee la persona en el hueco del valor, sin la etiqueta de la metrica. */
function textoDelValor(metrica: MetricaPresentable): string {
  const { container } = render(<ValorMetrica etiqueta="Ahorro prevalidado" metrica={metrica} />);
  const nodo = container.querySelector("[data-estado]");
  expect(nodo, "el componente siempre marca el estado del valor").not.toBeNull();
  return nodo?.textContent ?? "";
}

describe("ValorMetrica · R-UI-07", () => {
  it.each(AUSENTES)("%s se ensena SIN DATO y nunca como cero", (_nombre, metrica) => {
    const { container } = render(<ValorMetrica etiqueta="Ahorro" metrica={metrica} />);

    const hueco = container.querySelector('[data-estado="SIN_DATO"]');
    expect(hueco).not.toBeNull();
    expect(container.querySelector('[data-estado="CON_DATO"]')).toBeNull();
    expect(hueco?.textContent).toBe(SIN_DATO);
    // Lo que de verdad importa: en todo el componente no aparece ni una cifra.
    expect(container.textContent ?? "").not.toMatch(/\d/);
  });

  it.each(CEROS)("%s se ensena como cifra, no como hueco", (_nombre, metrica, esperado) => {
    const { container } = render(<ValorMetrica etiqueta="Ahorro" metrica={metrica} />);

    expect(container.querySelector('[data-estado="CON_DATO"]')?.textContent).toBe(esperado);
    expect(container.querySelector('[data-estado="SIN_DATO"]')).toBeNull();
    expect(container.textContent ?? "").not.toContain(SIN_DATO);
  });

  it("ningun dato ausente se ve igual que ningun cero", () => {
    // La garantia en su forma mas dura: los dos conjuntos de textos son disjuntos. Mientras este
    // test pase, no existe un par (ausente, cero) que la persona vea igual.
    const textosAusentes = new Set(AUSENTES.map(([, metrica]) => textoDelValor(metrica)));
    const textosCero = new Set(CEROS.map(([, metrica]) => textoDelValor(metrica)));

    for (const texto of textosAusentes) {
      expect(textosCero.has(texto)).toBe(false);
    }
    expect(textosAusentes).toEqual(new Set([SIN_DATO]));
  });

  it("el hueco dice desde que entregable habra dato", () => {
    const { container } = render(
      <ValorMetrica etiqueta="Minutos de revisión" metrica={{ estado: "SIN_DATO", desde: "S3.5" }} />,
    );

    expect(container.textContent).toContain(SIN_DATO);
    expect(container.textContent).toContain("Disponible desde S3.5");
  });

  it("un cero con unidad se distingue de un hueco con la misma unidad ausente", () => {
    expect(textoDelValor({ estado: "CON_DATO", valor: 0, unidad: "kWh/año" })).toBe("0 kWh/año");
    expect(textoDelValor({ estado: "SIN_DATO" })).toBe(SIN_DATO);
  });

  it("no pinta HTML que le llegue dentro de un valor", () => {
    // Sin `dangerouslySetInnerHTML` en ninguna parte: una cadena con marcado sale como texto.
    const { container } = render(
      <ValorMetrica etiqueta="Ahorro" metrica={{ estado: "CON_DATO", valor: "<b>7</b>" }} />,
    );

    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>7</b>");
  });
});
