/**
 * El test de humo de `GAP-HTTP-03`: **la aplicación entera montada**, no una pantalla suelta.
 *
 * Lo que comprueba, y por que estas cuatro cosas y no otras:
 *
 * 1. **Arranca sin una sola queja en la consola.** Un `console.error` de React —una clave repetida, un
 *    `act()` que falta, un atributo que el DOM no entiende— es un defecto que los tests de pantalla no
 *    ven porque montan un trozo. Aqui se monta el marco, el enrutador y la pantalla juntos.
 * 2. **La cabecera del principal viaja en cada peticion.** Es la pieza de `ADR-015` C29: si se pierde
 *    por el camino, el servidor deniega y la pantalla se llena de negativas que parecen otra cosa.
 * 3. **Se navega de la cola a la revision por el hash que la cola ya componia** (`#/revision/<id>`).
 * 4. **Sin principal no se pide nada.** La pagina no se autentica sola: lo dice y se queda quieta.
 *
 * Los datos son los que `api/` sirvio de verdad (`front/workspace/tests/datos/`, generados por
 * `generar.py`). Se leen del disco, no se importan: este paquete no entra en el proyecto de
 * TypeScript del workspace, y un payload escrito a mano probaria la pagina contra la idea que tenemos
 * del contrato. Que la pagina habla con el servidor **de verdad** lo comprueba `e2e/navegacion.mjs`,
 * que abre un navegador; esto es lo que cabe en la puerta de siempre.
 */

import { crearCliente, type Buscador } from "@cae/compartido/api";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Aplicacion } from "../src/Aplicacion";
import { BASE_API, CABECERA_PRINCIPAL, configuracionDe } from "../src/configuracion";
import { transporteConPrincipal } from "../src/transporte";

const DATOS = join(import.meta.dirname, "..", "..", "workspace", "tests", "datos");

function leer(nombre: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(DATOS, nombre), "utf8")) as Record<string, unknown>;
}

const COLA = leer("cola.json");
const DETALLE = leer("detalle.json") as Record<string, Record<string, unknown>>;

/** El principal que declara esta prueba. Va escrito **aqui**, como lo escribe quien arranca el front. */
const PRINCIPAL = '{"usuario_id":"u-humo","perfiles":["T-REV"],"tenant_id":"T-001"}';

/** El mismo instante que uso `generar.py`, para que "hace N días" no dependa del dia de la prueba. */
const AHORA = new Date("2026-09-19T12:00:00Z");

interface Pedida {
  readonly url: string;
  readonly principal: string | undefined;
  readonly actuacionId: string | null;
}

/** Un `fetch` de mentira que contesta con lo que `api/` contesto, y apunta lo que le pidieron. */
function buscadorDeFixtures(pedidas: Pedida[]): Buscador {
  return (entrada, inicio) => {
    const cuerpo = JSON.parse(inicio.body) as {
      contexto?: { actuacion_id?: string | null };
    };
    const actuacionId = cuerpo.contexto?.actuacion_id ?? null;
    pedidas.push({
      url: entrada,
      principal: inicio.headers[CABECERA_PRINCIPAL],
      actuacionId,
    });

    const capacidad = decodeURIComponent(entrada.slice(entrada.lastIndexOf("/") + 1));
    const respuesta =
      capacidad === "CAP-17" ? COLA : (actuacionId === null ? undefined : DETALLE[actuacionId]?.[capacidad]);
    if (respuesta === undefined) {
      // Una negativa bien formada: la pantalla la pinta, y eso tampoco puede ensuciar la consola.
      return Promise.resolve({
        status: 404,
        text: () =>
          Promise.resolve(
            JSON.stringify({ error: "api", motivo: `sin fixture de ${capacidad}`, codigo: "ruta" }),
          ),
      });
    }
    return Promise.resolve({
      status: 200,
      text: () => Promise.resolve(JSON.stringify(respuesta)),
    });
  };
}

function montar(pedidas: Pedida[] = []): void {
  const configuracion = configuracionDe(PRINCIPAL);
  expect(configuracion.estado).toBe("LISTA");
  const cabecera = configuracion.estado === "LISTA" ? configuracion.cabecera : "";
  const cliente = crearCliente(
    transporteConPrincipal(BASE_API, cabecera, buscadorDeFixtures(pedidas)),
  );
  render(<Aplicacion configuracion={configuracion} cliente={cliente} ahora={AHORA} />);
}

/** Pone el hash y espera a que el enrutador se entere, como hace el navegador al pulsar un enlace. */
async function irA(hash: string): Promise<void> {
  await act(async () => {
    globalThis.location.hash = hash;
    await Promise.resolve();
  });
}

let quejas: string[];

beforeEach(() => {
  quejas = [];
  globalThis.location.hash = "";
  for (const canal of ["error", "warn"] as const) {
    vi.spyOn(console, canal).mockImplementation((...partes: readonly unknown[]) => {
      quejas.push(`${canal}: ${partes.map((parte) => String(parte)).join(" ")}`);
    });
  }
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  globalThis.location.hash = "";
});

describe("humo · la aplicación entera se monta y navega", () => {
  it("monta la cola, con su aviso de autenticación y sin una queja en la consola", async () => {
    const pedidas: Pedida[] = [];
    montar(pedidas);

    expect(screen.getByRole("note").textContent).toContain("AUTENTICACIÓN DE DESARROLLO");
    await waitFor(() => {
      expect(document.querySelectorAll("tbody tr").length).toBeGreaterThan(0);
    });
    expect(quejas, quejas.join("\n")).toEqual([]);
    expect(pedidas.length).toBeGreaterThan(0);
  });

  it("la cabecera del principal viaja en todas las peticiones (`ADR-015` C29)", async () => {
    const pedidas: Pedida[] = [];
    montar(pedidas);
    await waitFor(() => {
      expect(pedidas.length).toBeGreaterThan(1);
    });

    for (const pedida of pedidas) {
      expect(pedida.principal, `${pedida.url} sin principal`).toBe(PRINCIPAL);
    }
    expect(quejas, quejas.join("\n")).toEqual([]);
  });

  it("del `#/revision/<id>` que compone la cola se llega a la vista de revisión", async () => {
    const pedidas: Pedida[] = [];
    montar(pedidas);
    await waitFor(() => {
      expect(document.querySelectorAll("tbody tr").length).toBeGreaterThan(0);
    });

    const enlace = document.querySelector<HTMLAnchorElement>("tbody tr a[href^='#/revision/']");
    expect(enlace, "la cola no ha pintado ningún enlace a la revisión").not.toBeNull();
    await irA(enlace?.getAttribute("href") ?? "");

    await waitFor(() => {
      expect(document.querySelector(".cae-revision__identificacion")).not.toBeNull();
    });
    const actuacionId = decodeURIComponent((enlace?.getAttribute("href") ?? "").split("/").pop() ?? "");
    expect(pedidas.some((pedida) => pedida.actuacionId === actuacionId)).toBe(true);
    expect(screen.getByRole("note").textContent).toContain("AUTENTICACIÓN DE DESARROLLO");
    expect(quejas, quejas.join("\n")).toEqual([]);
  });

  it("y se vuelve a la cola desde la revisión", async () => {
    montar();
    await irA("#/revision/C");
    await waitFor(() => {
      expect(document.querySelector(".cae-revision__identificacion")).not.toBeNull();
    });

    await irA("#/");
    await waitFor(() => {
      expect(document.querySelectorAll("tbody tr").length).toBeGreaterThan(0);
    });
    expect(quejas, quejas.join("\n")).toEqual([]);
  });
});

describe("humo · sin principal declarado no se pide nada", () => {
  it("lo dice en pantalla y no llama al servidor", async () => {
    const pedidas: Pedida[] = [];
    const configuracion = configuracionDe(undefined);
    render(<Aplicacion configuracion={configuracion} cliente={null} />);

    expect(screen.getByRole("note").textContent).toContain("AUTENTICACIÓN DE DESARROLLO");
    expect(screen.getByRole("heading").textContent).toContain("principal");
    expect(document.body.textContent).toContain("VITE_CAE_PRINCIPAL");
    await waitFor(() => {
      expect(pedidas).toEqual([]);
    });
    expect(quejas, quejas.join("\n")).toEqual([]);
  });
});
