import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MarcaOrigen, type OrigenDatos } from "../src/MarcaOrigen";
import { ORIGEN_REAL, ORIGEN_SIN_DECLARAR, ORIGEN_SINTETICO } from "../src/textos";

afterEach(cleanup);

describe("MarcaOrigen · R-UI-08", () => {
  it("declara datos sintéticos", () => {
    const { container } = render(<MarcaOrigen origen="SINTETICO" />);

    expect(container.textContent).toBe(ORIGEN_SINTETICO);
    expect(container.textContent).toContain("SOLO PRUEBAS");
  });

  it("declara datos reales", () => {
    const { container } = render(<MarcaOrigen origen="REAL" />);

    expect(container.textContent).toBe(ORIGEN_REAL);
  });

  it.each([undefined, null, "", "sintetico", "PRODUCCION", 0])(
    "un origen que no se entiende (%s) se anuncia, no se calla",
    (origen) => {
      const { container } = render(<MarcaOrigen origen={origen as unknown as OrigenDatos} />);

      expect(container.textContent).toBe(ORIGEN_SIN_DECLARAR);
      expect(container.querySelector('[role="alert"]')).not.toBeNull();
      // Lo que nunca puede pasar: que el olvido se lea como "datos reales".
      expect(container.textContent).not.toContain(ORIGEN_REAL);
    },
  );

  it("el origen no tiene valor por defecto", () => {
    const { container } = render(<MarcaOrigen {...({} as { origen: OrigenDatos })} />);

    expect(container.textContent).toBe(ORIGEN_SIN_DECLARAR);
  });
});
