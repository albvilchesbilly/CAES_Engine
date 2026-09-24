/**
 * Lo que garantiza que esta pagina **no se autentica sola**, y el enrutado por hash.
 *
 * La primera mitad es la importante: el principal de desarrollo es la pieza que, olvidada, regala el
 * sistema (`ADR-015` C29). Que haya que escribirlo se comprueba de las dos maneras —interpretando lo
 * que llega y recorriendo el arbol de `src/`, por si alguien lo cablea manana—, igual que `api/` lo
 * comprueba de sus dos maneras del lado de Python.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { VARIABLE_PRINCIPAL, configuracionDe } from "../src/configuracion";
import { rutaDe } from "../src/enrutador";

const FUENTES = join(import.meta.dirname, "..", "src");

function codigo(directorio: string = FUENTES): readonly (readonly [string, string])[] {
  const encontradas: (readonly [string, string])[] = [];
  for (const entrada of readdirSync(directorio, { withFileTypes: true })) {
    const ruta = join(directorio, entrada.name);
    if (entrada.isDirectory()) {
      encontradas.push(...codigo(ruta));
    } else if (/\.tsx?$/.test(entrada.name)) {
      encontradas.push([ruta.slice(FUENTES.length + 1), readFileSync(ruta, "utf8")] as const);
    }
  }
  return encontradas;
}

describe("el principal no tiene valor por defecto (`ADR-015` C29)", () => {
  it("sin variable no hay configuración, y se dice cómo se declara", () => {
    const sin = configuracionDe(undefined);
    expect(sin.estado).toBe("SIN_PRINCIPAL");
    expect(sin.estado === "SIN_PRINCIPAL" && sin.motivo).toContain(VARIABLE_PRINCIPAL);
  });

  it("una variable vacía tampoco vale", () => {
    expect(configuracionDe("   ").estado).toBe("SIN_PRINCIPAL");
  });

  it("lo que no es JSON se rechaza diciéndolo", () => {
    expect(configuracionDe("u-rev").estado).toBe("SIN_PRINCIPAL");
  });

  it("un principal incompleto no se completa: sin perfiles no hay principal", () => {
    expect(configuracionDe('{"usuario_id":"u","tenant_id":"T"}').estado).toBe("SIN_PRINCIPAL");
    expect(configuracionDe('{"usuario_id":"u","perfiles":[],"tenant_id":"T"}').estado).toBe(
      "SIN_PRINCIPAL",
    );
  });

  it("sin `tenant_id` no hay pantalla que abrir (`ADR-015` C30)", () => {
    expect(configuracionDe('{"usuario_id":"u","perfiles":["P"]}').estado).toBe("SIN_PRINCIPAL");
  });

  it("lo que no cabe en una cabecera HTTP se dice aquí y no en `fetch`", () => {
    expect(configuracionDe('{"usuario_id":"ú","perfiles":["P"],"tenant_id":"T"}').estado).toBe(
      "SIN_PRINCIPAL",
    );
  });

  it("un principal completo pasa, y la cabecera es exactamente lo declarado", () => {
    const configuracion = configuracionDe('{"usuario_id":"u-1","perfiles":["P-1"],"tenant_id":"T-9"}');
    expect(configuracion.estado).toBe("LISTA");
    if (configuracion.estado !== "LISTA") {
      return;
    }
    expect(configuracion.principal.tenant_id).toBe("T-9");
    expect(JSON.parse(configuracion.cabecera)).toEqual({
      usuario_id: "u-1",
      perfiles: ["P-1"],
      tenant_id: "T-9",
    });
  });

  it("no hay ningún principal escrito en el código de la página", () => {
    for (const [ruta, contenido] of codigo()) {
      expect(contenido, `${ruta}: un perfil cableado`).not.toMatch(/["'`][TOAE]-[A-Z]{3}["'`]/);
      expect(contenido, `${ruta}: un usuario cableado`).not.toMatch(/usuario_id\s*[:=]\s*["'`][^"'`]/);
      expect(contenido, `${ruta}: un tenant cableado`).not.toMatch(/tenant_id\s*[:=]\s*["'`][^"'`]/);
    }
  });

  it("ni un valor por defecto para la variable que lo trae", () => {
    for (const [ruta, contenido] of codigo()) {
      expect(contenido, `${ruta}: ${VARIABLE_PRINCIPAL} con defecto`).not.toMatch(
        new RegExp(`${VARIABLE_PRINCIPAL}[^\\n]*(\\?\\?|\\|\\|)\\s*["'\`]`),
      );
    }
  });
});

describe("el enrutado por hash", () => {
  it("lo que no se reconoce es la cola: no se inventa una pantalla", () => {
    expect(rutaDe("")).toEqual({ vista: "COLA" });
    expect(rutaDe("#/")).toEqual({ vista: "COLA" });
    expect(rutaDe("#/revision/")).toEqual({ vista: "COLA" });
    expect(rutaDe("#/otra-cosa")).toEqual({ vista: "COLA" });
  });

  it("`#/revision/<id>` lleva a la revisión con el identificador tal cual lo dio la lectura", () => {
    expect(rutaDe("#/revision/EXP001-C_contradictorio")).toEqual({
      vista: "REVISION",
      actuacionId: "EXP001-C_contradictorio",
    });
    expect(rutaDe("#/revision/a%2Fb")).toEqual({ vista: "REVISION", actuacionId: "a/b" });
  });

  it("un hash mal escrito a mano no rompe la página", () => {
    expect(rutaDe("#/revision/%E0%A4%A")).toEqual({ vista: "COLA" });
  });
});
