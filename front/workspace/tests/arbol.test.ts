/**
 * Lo que se comprueba **recorriendo el arbol** de `front/workspace/`, y no pintando nada.
 *
 * Son las reglas que no se ven en una pantalla concreta porque son ausencias: no existe ningun control
 * que fije un veredicto, no hay ningun identificador de actuacion escrito a mano, no se ordena nada y no
 * hay ejecucion dinamica. Una ausencia solo se comprueba mirando todo el arbol, y por eso **este fichero
 * cubre tambien la segunda pantalla del workspace** en cuanto exista: no hay que tocarlo para ampliarlo.
 *
 * `CA-COLA-05` y `CA-COLA-11` de `T-REV-cola` §10.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { pintarCola } from "./apoyo";

afterEach(cleanup);

const RAIZ = join(import.meta.dirname, "..");

/** Los cuatro veredictos del motor (`engine/`). El front los recibe; no los escribe y no los fija. */
const VEREDICTOS = ["NO_ELEGIBLE", "BLOQUEADO", "SUBSANABLE", "PREVALIDADO"] as const;

/**
 * El mismo veredicto, para buscarlo en el codigo sin confundirlo con `AHORRO_PREVALIDADO`, que es el
 * tipo de rotulo de `R-UI-06` y no un veredicto. El guion bajo delante es lo que los separa.
 */
const ESCRITO = (veredicto: string) => new RegExp(`(^|[^A-Z_])${veredicto}\\b`);

/**
 * Todo lo que no son tests: el codigo y la documentacion que se entregan. Los datos de prueba viven
 * bajo `tests/`, que es justo lo que `CA-COLA-11` excluye de su busqueda.
 */
function fuentes(directorio: string = RAIZ): readonly (readonly [string, string])[] {
  const encontradas: (readonly [string, string])[] = [];
  for (const entrada of readdirSync(directorio, { withFileTypes: true })) {
    const ruta = join(directorio, entrada.name);
    if (entrada.isDirectory()) {
      if (entrada.name === "tests" || entrada.name === "node_modules") {
        continue;
      }
      encontradas.push(...fuentes(ruta));
    } else if (/\.(tsx?|css|json|md)$/.test(entrada.name)) {
      encontradas.push([ruta.slice(RAIZ.length + 1), readFileSync(ruta, "utf8")] as const);
    }
  }
  return encontradas;
}

const FUENTES = fuentes();

/**
 * El codigo sin sus comentarios.
 *
 * Hace falta porque estas comprobaciones son sobre lo que el programa **hace**, y un comentario que
 * explica por que no se escribe un veredicto no es escribirlo: `motivos.ts` cita la severidad
 * `SUBSANABLE` —que ademas no es un veredicto, aunque se llamen igual— y `ColaRevision.tsx` dice de
 * quien es la pantalla. La lista de formulas prohibidas de `textos.test.ts` si mira el fichero entero,
 * porque alli lo que importa es lo que se puede llegar a leer.
 */
function sinComentarios(contenido: string): string {
  return contenido.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|\s)\/\/[^\n]*/g, " ");
}

function codigo(): readonly (readonly [string, string])[] {
  return FUENTES.filter(([ruta]) => /\.tsx?$/.test(ruta)).map(
    ([ruta, contenido]) => [ruta, sinComentarios(contenido)] as const,
  );
}

// ---------------------------------------------------------------------------
// CA-COLA-05 · ningun control fija, fuerza ni cambia un veredicto (`R-UI-02`)
// ---------------------------------------------------------------------------

describe("CA-COLA-05 · `R-UI-02`: el veredicto es texto, nunca un control", () => {
  it("hay algo que recorrer", () => {
    expect(codigo().length).toBeGreaterThan(5);
  });

  it("ningún componente escribe un veredicto: llegan del servidor y se pintan", () => {
    for (const [ruta, contenido] of codigo()) {
      for (const veredicto of VEREDICTOS) {
        expect(contenido, `${ruta} escribe el veredicto ${veredicto}`).not.toMatch(ESCRITO(veredicto));
      }
    }
  });

  it("no hay ningún campo editable en todo el workspace", () => {
    for (const [ruta, contenido] of codigo()) {
      expect(contenido, `${ruta}: <select`).not.toMatch(/<select\b/);
      expect(contenido, `${ruta}: <input`).not.toMatch(/<input\b/);
      expect(contenido, `${ruta}: <textarea`).not.toMatch(/<textarea\b/);
      expect(contenido, `${ruta}: contentEditable`).not.toMatch(/contentEditable/i);
    }
  });

  it("ningún control de la pantalla pintada lleva un veredicto ni por valor ni por acción", async () => {
    const { container } = await pintarCola();
    const controles = Array.from(
      container.querySelectorAll<HTMLElement>(
        "button, select, input, textarea, [contenteditable], [role='button'], [role='radio'], [role='checkbox']",
      ),
    );

    for (const control of controles) {
      const rastro = [
        control.textContent ?? "",
        control.getAttribute("value") ?? "",
        control.getAttribute("aria-label") ?? "",
        control.getAttribute("name") ?? "",
        control.getAttribute("data-veredicto") ?? "",
      ].join(" ");
      for (const veredicto of VEREDICTOS) {
        expect(rastro, `un control ofrece ${veredicto}`).not.toContain(veredicto);
      }
    }
  });

  it("los enlaces de fila llevan a la revisión, y no a fijar nada", async () => {
    const { container } = await pintarCola();

    for (const enlace of Array.from(container.querySelectorAll("a"))) {
      expect(enlace.getAttribute("href")).toMatch(/^#\/revision\//);
    }
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-11 · ningun identificador de actuacion escrito a mano (`R-UI-12`)
// ---------------------------------------------------------------------------

describe("CA-COLA-11 · la pantalla navega con lo que le dio la lectura", () => {
  it("no aparece ningún identificador de los casos sintéticos en el código", () => {
    for (const [ruta, contenido] of FUENTES) {
      expect(contenido, `${ruta} lleva un identificador de actuación escrito a mano`).not.toContain(
        "EXP001-",
      );
    }
  });

  it("tampoco se compone ninguna ruta de actuación a partir de un texto fijo", () => {
    for (const [ruta, contenido] of codigo()) {
      expect(contenido, `${ruta}: actuacion_id fijado a mano`).not.toMatch(
        /actuacion_id\s*[:=]\s*["'`][^"'`]/,
      );
    }
  });
});

// ---------------------------------------------------------------------------
// `R-UI-11` · el front no contiene logica de negocio
// ---------------------------------------------------------------------------

describe("`R-UI-11` · ni se ordena, ni se calcula, ni se convierte una cifra", () => {
  it("no hay ningún `sort` ni ningún `reverse`: el orden es del servidor", () => {
    for (const [ruta, contenido] of codigo()) {
      expect(contenido, `${ruta}: .sort(`).not.toMatch(/\.sort\s*\(/);
      expect(contenido, `${ruta}: .reverse(`).not.toMatch(/\.reverse\s*\(/);
    }
  });

  it("ninguna cifra pasa por coma flotante", () => {
    // La unica excepcion es `fechas.ts`, que cuenta dias de calendario con aritmetica entera y **no
    // toca ninguna magnitud**: el ahorro entra como cadena y sale como cadena (`CLAUDE.md` §2).
    const sinCifras = codigo().filter(([ruta]) => !ruta.endsWith("fechas.ts"));
    expect(sinCifras.length).toBeGreaterThan(5);

    for (const [ruta, contenido] of sinCifras) {
      expect(contenido, `${ruta}: Number(`).not.toMatch(/\bNumber\s*\(/);
      expect(contenido, `${ruta}: parseFloat`).not.toMatch(/parseFloat\s*\(/);
      expect(contenido, `${ruta}: parseInt`).not.toMatch(/parseInt\s*\(/);
      expect(contenido, `${ruta}: toFixed`).not.toMatch(/\.toFixed\s*\(/);
      expect(contenido, `${ruta}: toLocaleString`).not.toMatch(/\.toLocaleString\s*\(/);
    }
  });

  it("no hay ejecución dinámica ni inyección de HTML", () => {
    for (const [ruta, contenido] of codigo()) {
      expect(contenido, `${ruta}: eval`).not.toMatch(/\beval\s*\(/);
      expect(contenido, `${ruta}: new Function`).not.toMatch(/new\s+Function\s*\(/);
      expect(contenido, `${ruta}: innerHTML`).not.toMatch(/innerHTML/);
      expect(contenido, `${ruta}: dangerouslySetInnerHTML`).not.toMatch(/dangerouslySetInnerHTML/);
    }
  });

  it("el workspace habla con `api/` y con nadie más", () => {
    for (const [ruta, contenido] of codigo()) {
      expect(contenido, `${ruta}: fetch`).not.toMatch(/\bfetch\s*\(/);
      expect(contenido, `${ruta}: XMLHttpRequest`).not.toMatch(/XMLHttpRequest/);
      // Nada de subir a `api/` ni a `engine/` por el sistema de ficheros: se importa el contrato.
      expect(contenido, `${ruta}: import fuera del paquete`).not.toMatch(/from\s+"\.\.\/\.\.\//);
    }
  });

  it("no hay ninguna tabla de perfiles ni de capacidades concedidas (`R-UI-01`)", () => {
    for (const [ruta, contenido] of codigo()) {
      // Nombrar la capacidad que se pide es obligatorio; decidir quien la tiene, no es del front.
      expect(contenido, `${ruta}: perfiles`).not.toMatch(/\bperfiles\s*[:=]/);
      expect(contenido, `${ruta}: T-RES/T-OPE/T-REV cableados`).not.toMatch(/["'`]T-(RES|OPE|REV)["'`]/);
    }
  });
});
