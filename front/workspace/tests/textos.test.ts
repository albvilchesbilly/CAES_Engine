/**
 * `CA-COLA-10`: el catalogo de textos del workspace pasa **la misma lista de formulas prohibidas** que
 * `front/compartido/tests/textos.test.ts`.
 *
 * La lista no es una guia de estilo: es lo que, dicho en una pantalla, seria falso (`CLAUDE.md` §2).
 * Nada dice "CAE garantizado", nada garantiza, `A8` no se llama con ese nombre en ningun sitio y ningun
 * kWh prevalidado se presenta como un CAE ya emitido.
 *
 * Que la lista sea **la misma** no se deja a la buena fe: el ultimo test la contrasta contra el fichero
 * de `compartido/`. Si alli se anade una formula y aqui no, este banco de pruebas lo dice.
 *
 * Lo que el servidor escribe —el mensaje de un veredicto, su descargo, el motivo de un no-calculo, el
 * motivo de una denegacion— **no entra en este catalogo** y no es texto de producto nuestro: se pinta
 * literal porque lo decide la spec activa o `api/` (`T-REV-revision.md` §11 bis).
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { TEXTOS } from "../src/textos";
import { DETALLE } from "./apoyo";

const RAIZ = join(import.meta.dirname, "..");
const LISTA_DE_COMPARTIDO = join(RAIZ, "..", "compartido", "tests", "textos.test.ts");

/** Las mismas cuatro de `compartido/`, con el mismo `source`, y el porque de cada una. */
const PROHIBIDO: ReadonlyArray<readonly [string, RegExp]> = [
  ["ningun texto dice 'CAE garantizado'", /cae\s+garantizad/i],
  ["nada se garantiza", /garantiz(?:o|a|amos|ado|ados|ada|adas)\b/i],
  ["A8 no se llama verificador", /verificador/i],
  ["un kWh prevalidado no es un CAE emitido suelto", /\bcae\s+(?:emitido|conseguido|cobrado)\b/i],
];

/** El codigo que se entrega, con comentarios incluidos: aqui importa todo lo que se puede llegar a leer. */
function fuentes(directorio: string = RAIZ): readonly (readonly [string, string])[] {
  const encontradas: (readonly [string, string])[] = [];
  for (const entrada of readdirSync(directorio, { withFileTypes: true })) {
    const ruta = join(directorio, entrada.name);
    if (entrada.isDirectory()) {
      if (entrada.name === "tests" || entrada.name === "node_modules") {
        continue;
      }
      encontradas.push(...fuentes(ruta));
    } else if (/\.tsx?$/.test(entrada.name)) {
      encontradas.push([ruta.slice(RAIZ.length + 1), readFileSync(ruta, "utf8")] as const);
    }
  }
  return encontradas;
}

const FUENTES = fuentes();

describe("textos del workspace · CA-COLA-10", () => {
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

  it("es la misma lista que la de `compartido/`, no una copia que se ha quedado atrás", () => {
    const original = readFileSync(LISTA_DE_COMPARTIDO, "utf8");

    for (const [motivo, prohibido] of PROHIBIDO) {
      expect(original, `${motivo}: la expresión no está en compartido/`).toContain(prohibido.source);
    }
  });

  it("el texto que escribe el servidor no está en el catálogo", () => {
    const veredicto = DETALLE["C"]?.["CAP-03"]?.datos["veredicto"] as {
      mensaje: string;
      descargo: string;
    };
    const catalogo = Object.values(TEXTOS);

    expect(veredicto.descargo.length).toBeGreaterThan(0);
    expect(catalogo).not.toContain(veredicto.descargo);
    expect(catalogo).not.toContain(veredicto.mensaje);
  });

  it("los literales que ve una persona llevan sus tildes", () => {
    expect(TEXTOS.TITULO_COLA).toContain("revisión");
    expect(TEXTOS.ESTIMACION_NO_ACREDITADA).toContain("ESTIMACIÓN");
  });
});
