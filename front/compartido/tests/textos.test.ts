import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { TEXTOS } from "../src/textos";

const DIRECTORIO_FUENTES = join(import.meta.dirname, "..", "src");

const FUENTES = readdirSync(DIRECTORIO_FUENTES)
  .filter((fichero) => /\.tsx?$/.test(fichero))
  .map((fichero) => [fichero, readFileSync(join(DIRECTORIO_FUENTES, fichero), "utf8")] as const);

/**
 * Formulas que `CLAUDE.md` §2 prohibe en cualquier texto de producto, y el porque de cada una.
 * No es una guia de estilo: es la lista de cosas que, dichas en una pantalla, serian falsas.
 */
const PROHIBIDO: ReadonlyArray<readonly [string, RegExp]> = [
  ["ningun texto dice 'CAE garantizado'", /cae\s+garantizad/i],
  ["nada se garantiza", /garantiz(?:o|a|amos|ado|ados|ada|adas)\b/i],
  // A8 no se llama "verificador" en ningun sitio. `compartido/` no tiene hoy ningun texto sobre el
  // organismo verificador; si FR1 necesita nombrarlo, la excepcion se razona alli y no aqui.
  ["A8 no se llama verificador", /verificador/i],
  ["un kWh prevalidado no es un CAE emitido suelto", /\bcae\s+(?:emitido|conseguido|cobrado)\b/i],
];

describe("textos de interfaz", () => {
  it.each(PROHIBIDO)("%s (catálogo de textos)", (_motivo, prohibido) => {
    for (const texto of Object.values(TEXTOS)) {
      expect(texto).not.toMatch(prohibido);
    }
  });

  it.each(PROHIBIDO)("%s (código fuente)", (_motivo, prohibido) => {
    for (const [fichero, contenido] of FUENTES) {
      expect(contenido, `${fichero} contiene una fórmula prohibida`).not.toMatch(prohibido);
    }
  });

  it("no hay ejecución dinámica ni inyección de HTML en ningún componente", () => {
    for (const [fichero, contenido] of FUENTES) {
      expect(contenido, `${fichero}: eval`).not.toMatch(/\beval\s*\(/);
      expect(contenido, `${fichero}: new Function`).not.toMatch(/new\s+Function\s*\(/);
      expect(contenido, `${fichero}: innerHTML`).not.toMatch(/innerHTML/);
      expect(contenido, `${fichero}: dangerouslySetInnerHTML`).not.toMatch(
        /dangerouslySetInnerHTML/,
      );
    }
  });

  it("compartido/ no habla con nada: ni red ni imports fuera del paquete (FR0)", () => {
    for (const [fichero, contenido] of FUENTES) {
      expect(contenido, `${fichero}: fetch`).not.toMatch(/\bfetch\s*\(/);
      expect(contenido, `${fichero}: XMLHttpRequest`).not.toMatch(/XMLHttpRequest/);
      // Nada de `../../api` ni `../../engine`: la dependencia va hacia dentro y se para en `api/`.
      expect(contenido, `${fichero}: import fuera del paquete`).not.toMatch(/from\s+"\.\.\/\.\./);
    }
  });

  it("los literales que ve la persona llevan sus tildes", () => {
    expect(TEXTOS.ORIGEN_SINTETICO).toContain("SINTÉTICOS");
  });
});
