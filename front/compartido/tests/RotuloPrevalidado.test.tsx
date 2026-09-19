import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RotuloPrevalidado, type PropsRotuloPrevalidado } from "../src/RotuloPrevalidado";
import { MARCA_NO_OFICIAL, ROTULO_AHORRO_PREVALIDADO } from "../src/textos";

afterEach(cleanup);

describe("RotuloPrevalidado · R-UI-06", () => {
  it("una cifra prevalidada sale siempre con 'no son CAE emitidos'", () => {
    const { container } = render(
      <RotuloPrevalidado tipo="AHORRO_PREVALIDADO">305.829,6 kWh/año</RotuloPrevalidado>,
    );

    expect(container.textContent).toContain("305.829,6 kWh/año");
    expect(container.textContent).toContain("no son CAE emitidos");
    expect(ROTULO_AHORRO_PREVALIDADO).toContain("no son CAE emitidos");
  });

  it("un estado de expediente sale marcado NO OFICIAL", () => {
    const { container } = render(
      <RotuloPrevalidado tipo="ESTADO_EXPEDIENTE">En verificación</RotuloPrevalidado>,
    );

    expect(container.querySelector(".cae-rotulo-prevalidado__marca")?.textContent).toBe(
      MARCA_NO_OFICIAL,
    );
    expect(container.textContent).toContain("En verificación");
  });

  it("no hay forma de quitar el aviso", () => {
    // Se intenta desde fuera, con props que el tipo no admite: si algun dia alguien anade una
    // salida de escape, este test cae antes de que llegue a una pantalla.
    const propsHostiles = {
      tipo: "AHORRO_PREVALIDADO",
      sinAviso: true,
      aviso: "",
      children: "12 kWh/año",
    } as unknown as PropsRotuloPrevalidado;
    const { container } = render(<RotuloPrevalidado {...propsHostiles} />);

    expect(container.querySelector(".cae-rotulo-prevalidado__aviso")?.textContent).toBe(
      ROTULO_AHORRO_PREVALIDADO,
    );
  });

  it("una cifra prevalidada nunca se presenta como CAE emitido ni garantizado", () => {
    const { container } = render(
      <RotuloPrevalidado tipo="AHORRO_PREVALIDADO">1.000 kWh/año</RotuloPrevalidado>,
    );
    const texto = container.textContent ?? "";

    expect(texto).not.toMatch(/cae\s+garantizad/i);
    // Fuera del aviso obligatorio, la palabra CAE no aparece: la cifra no se presenta como un CAE.
    expect(texto.replace(ROTULO_AHORRO_PREVALIDADO, "")).not.toMatch(/cae/i);
  });
});
