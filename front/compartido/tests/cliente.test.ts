/**
 * Contrato C18 (`ADR-012` §3): las cuatro reglas del cliente, una a una.
 *
 * 1. El cliente no decide permisos: pide siempre, y el servidor concede o niega.
 * 2. Un `ErrorPermiso` llega a quien mira la pantalla, con su motivo dentro.
 * 3. Lo que no viene en la respuesta no se inventa (un bloque fuera de ambito es `undefined`).
 * 4. No reordena ni recalcula: `datos` sale tal cual entro.
 *
 * Y el documento de `CAP-03`: los bytes que salen del cliente son los que puso el servidor.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it, vi } from "vitest";

import {
  bloque,
  crearCliente,
  ErrorApi,
  ErrorPermiso,
  transporteHttp,
  type Buscador,
  type PeticionTransporte,
  type RespuestaTransporte,
  type Transporte,
} from "../api";
import { BLOQUES, COMANDOS, LECTURAS } from "../api/contrato.generado";
import { ERROR_PERMISO } from "../src/textos";

const CONTEXTO = { superficie: "cola_revision", tenant_id: "T-001", actuacion_id: "A-1" } as const;

/** Un transporte de mentira: apunta lo que se le pide y devuelve lo que se le dijo. */
function transporteQueDevuelve(
  ...respuestas: readonly RespuestaTransporte[]
): { transporte: Transporte; pedidas: PeticionTransporte[] } {
  const pedidas: PeticionTransporte[] = [];
  let indice = 0;
  const transporte: Transporte = async (peticion) => {
    pedidas.push(peticion);
    const respuesta = respuestas[Math.min(indice, respuestas.length - 1)];
    indice += 1;
    if (respuesta === undefined) {
      throw new Error("el test no ha preparado ninguna respuesta");
    }
    return respuesta;
  };
  return { transporte, pedidas };
}

function respuestaDe(datos: Record<string, unknown>, resto: Record<string, unknown> = {}) {
  return {
    estado: 200,
    cuerpo: { capacidad: "CAP-03", rol: "T-REV", eventos: [], avisos: [], datos, ...resto },
  };
}

// ---------------------------------------------------------------------------
// Una lectura que va bien
// ---------------------------------------------------------------------------

describe("una lectura que va bien", () => {
  it("devuelve la respuesta del contrato entera", async () => {
    const { transporte, pedidas } = transporteQueDevuelve(
      respuestaDe({ identificacion: { actuacion_id: "A-1" } }, { avisos: ["ojo con la fecha"] }),
    );
    const cliente = crearCliente(transporte);

    const respuesta = await cliente.leer("CAP-03", CONTEXTO);

    expect(respuesta.capacidad).toBe("CAP-03");
    expect(respuesta.rol).toBe("T-REV");
    expect(respuesta.eventos).toEqual([]);
    expect(respuesta.avisos).toEqual(["ojo con la fecha"]);
    expect(bloque(respuesta, "identificacion")).toEqual({ actuacion_id: "A-1" });
    expect(pedidas).toEqual([
      { ruta: "/lecturas/CAP-03", cuerpo: { contexto: CONTEXTO, datos: {} } },
    ]);
  });

  it("un comando manda sus datos y devuelve los eventos que escribió el servidor", async () => {
    const { transporte, pedidas } = transporteQueDevuelve({
      estado: 200,
      cuerpo: {
        capacidad: "CAP-05",
        rol: "T-REV",
        eventos: ["ev-7"],
        avisos: [],
        datos: { variable: "potencia" },
      },
    });
    const cliente = crearCliente(transporte);

    const respuesta = await cliente.ejecutar("CAP-05", CONTEXTO, {
      variable: "potencia",
      valor: "110",
      justificacion: "placa del motor",
    });

    expect(respuesta.eventos).toEqual(["ev-7"]);
    expect(pedidas[0]?.ruta).toBe("/comandos/CAP-05");
    expect(pedidas[0]?.cuerpo).toEqual({
      contexto: CONTEXTO,
      datos: { variable: "potencia", valor: "110", justificacion: "placa del motor" },
    });
  });
});

// ---------------------------------------------------------------------------
// Regla 1: el cliente no decide permisos
// ---------------------------------------------------------------------------

describe("el cliente no decide permisos (regla 1)", () => {
  it("pide aunque la capacidad esté denegada para todo el mundo: decide el servidor", async () => {
    const { transporte, pedidas } = transporteQueDevuelve({
      estado: 403,
      cuerpo: {
        error: "permiso",
        motivo: "CAP-32 (Reasignar actuación): ['T-RES'] tienen la celda pendiente de decisión A3",
      },
    });
    const cliente = crearCliente(transporte);

    await expect(cliente.ejecutar("CAP-32", CONTEXTO, {})).rejects.toBeInstanceOf(ErrorPermiso);
    expect(pedidas).toHaveLength(1);
  });

  it("no hay ninguna tabla de perfiles ni de capacidades en el código del cliente", () => {
    // Se mira el código sin comentarios: nombrar `CAP-03` al explicar el contrato es documentación;
    // escribirlo en una condición sería el cliente decidiendo, y eso decide el servidor.
    for (const [fichero, contenido] of fuentesDelCliente()) {
      if (fichero === "contrato.generado.ts") {
        continue; // es la lista de capacidades del contrato, generada desde la matriz; no decide nada
      }
      const codigo = sinComentarios(contenido);
      expect(codigo, `${fichero}: nombra un perfil`).not.toMatch(
        /\b(T-RES|T-OPE|T-REV|EXT-INS|EXT-CLI|ADM-MOD|ADM-OPS|SYS-API)\b/,
      );
      expect(codigo, `${fichero}: cablea una capacidad`).not.toMatch(/CAP-\d\d/);
      expect(codigo, `${fichero}: decide permisos`).not.toMatch(/\bconcede\b|\bpuede(Ver|Hacer)/);
    }
  });
});

// ---------------------------------------------------------------------------
// Regla 2: un ErrorPermiso se muestra, no se traga
// ---------------------------------------------------------------------------

describe("un error de permiso se muestra (regla 2)", () => {
  it("llega al usuario con el motivo del servidor, listo para pintar", async () => {
    const motivo = "CAP-10 (Aprobar revisión): no concedida a ['T-OPE']; la tienen ['T-REV']";
    const { transporte } = transporteQueDevuelve({
      estado: 403,
      cuerpo: { error: "permiso", motivo, codigo: "no_concedida" },
    });
    const cliente = crearCliente(transporte);

    const fallo = await cliente.leer("CAP-03", CONTEXTO).catch((error: unknown) => error);

    expect(fallo).toBeInstanceOf(ErrorPermiso);
    const permiso = fallo as ErrorPermiso;
    expect(permiso.motivo).toBe(motivo);
    expect(permiso.codigo).toBe("no_concedida");
    expect(permiso.mensaje).toBe(`${ERROR_PERMISO} ${motivo}`);
    expect(permiso.mensaje).toContain("no concedida");
  });

  it("un 403 sin motivo no se queda mudo: dice que el servidor no lo dio", async () => {
    const { transporte } = transporteQueDevuelve({ estado: 403, cuerpo: null });
    const cliente = crearCliente(transporte);

    const fallo = (await cliente
      .leer("CAP-03", CONTEXTO)
      .catch((error: unknown) => error)) as ErrorPermiso;

    expect(fallo).toBeInstanceOf(ErrorPermiso);
    expect(fallo.mensaje).toContain("sin decir por qué");
  });

  it("un documento alterado llega como error con su motivo, no como documento vacío", async () => {
    const motivo =
      "CAP-03: el documento 'a1b2' fue alterado después de la ingesta: no se sirve";
    const { transporte } = transporteQueDevuelve({
      estado: 409,
      cuerpo: { error: "api", codigo: "integridad", motivo },
    });
    const cliente = crearCliente(transporte);

    const fallo = (await cliente
      .leerDocumento("CAP-03", CONTEXTO, "a".repeat(64))
      .catch((error: unknown) => error)) as ErrorApi;

    expect(fallo).toBeInstanceOf(ErrorApi);
    expect(fallo.codigo).toBe("integridad");
    expect(fallo.estado).toBe(409);
    expect(fallo.mensaje).toContain("fue alterado");
  });

  it("si no hay servidor, se dice que no se pudo preguntar y no que te lo han denegado", async () => {
    const transporte: Transporte = () => Promise.reject(new Error("ECONNREFUSED"));
    const cliente = crearCliente(transporte);

    const fallo = (await cliente
      .leer("CAP-03", CONTEXTO)
      .catch((error: unknown) => error)) as ErrorApi;

    expect(fallo).toBeInstanceOf(ErrorApi);
    expect(fallo).not.toBeInstanceOf(ErrorPermiso);
    expect(fallo.mensaje).toContain("No se ha podido contactar con el servidor.");
    expect(fallo.mensaje).toContain("ECONNREFUSED");
  });
});

// ---------------------------------------------------------------------------
// Regla 3 y R-UI-12: lo que no viene, no se inventa
// ---------------------------------------------------------------------------

describe("un bloque que el ámbito no trae (R-UI-12)", () => {
  it("es `undefined`, y el cliente no lo rellena", async () => {
    // Un perfil externo: la respuesta trae identificación y estado, y nada de documentos ni veredicto.
    const { transporte } = transporteQueDevuelve(
      respuestaDe({
        identificacion: { actuacion_id: "A-1" },
        estado_simplificado: { semaforo: "ambar", mensaje: "Falta documentación" },
      }),
    );
    const cliente = crearCliente(transporte);

    const respuesta = await cliente.leer("CAP-40", CONTEXTO);

    expect(bloque(respuesta, "estado_simplificado")).toEqual({
      semaforo: "ambar",
      mensaje: "Falta documentación",
    });
    for (const ausente of ["veredicto", "calculo", "documentos", "historial"] as const) {
      expect(bloque(respuesta, ausente)).toBeUndefined();
    }
    expect(Object.keys(respuesta.datos)).toEqual(["identificacion", "estado_simplificado"]);
  });

  it("una respuesta que no cumple el contrato no se interpreta a medias", async () => {
    const { transporte } = transporteQueDevuelve({
      estado: 200,
      cuerpo: { capacidad: "CAP-03", datos: { veredicto: { valor: "PREVALIDADO" } } },
    });
    const cliente = crearCliente(transporte);

    const fallo = (await cliente
      .leer("CAP-03", CONTEXTO)
      .catch((error: unknown) => error)) as ErrorApi;

    expect(fallo).toBeInstanceOf(ErrorApi);
    expect(fallo.mensaje).toContain("no cumple el contrato");
  });
});

// ---------------------------------------------------------------------------
// Regla 3: no reordena ni recalcula
// ---------------------------------------------------------------------------

describe("el cliente no reordena ni recalcula (R-UI-11)", () => {
  it("devuelve `datos` tal cual llegó, sin copiar ni ordenar", async () => {
    const datos = {
      veredicto: { valor: "SUBSANABLE", reglas_falladas: ["R-DOC-01", "R-AMB-02"] },
      calculo: { total_exacto: "305829.6", total_cae: 305829, por_unidad: ["u2", "u1"] },
      identificacion: { actuacion_id: "A-1" },
    };
    const { transporte } = transporteQueDevuelve(respuestaDe(datos));
    const cliente = crearCliente(transporte);

    const respuesta = await cliente.leer("CAP-03", CONTEXTO);

    // La misma referencia: no hay copia intermedia en la que algo se pueda reordenar.
    expect(respuesta.datos).toBe(datos);
    expect(Object.keys(respuesta.datos)).toEqual(["veredicto", "calculo", "identificacion"]);
    const calculo = bloque(respuesta, "calculo") as Record<string, unknown>;
    // La cifra llega ya decidida y ya formateada: ni se convierte a número ni se vuelve a formatear.
    expect(calculo["total_exacto"]).toBe("305829.6");
    expect(calculo["por_unidad"]).toEqual(["u2", "u1"]);
    const veredicto = bloque(respuesta, "veredicto") as Record<string, unknown>;
    expect(veredicto["reglas_falladas"]).toEqual(["R-DOC-01", "R-AMB-02"]);
  });

  it("no hay ni aritmética de cifras ni ordenación en el código del cliente", () => {
    for (const [fichero, contenido] of fuentesDelCliente()) {
      const codigo = sinComentarios(contenido);
      expect(codigo, `${fichero}: ordena`).not.toMatch(/\.sort\s*\(/);
      expect(codigo, `${fichero}: convierte a número`).not.toMatch(/parseFloat|Number\s*\(/);
      expect(codigo, `${fichero}: redondea`).not.toMatch(/Math\.round|toFixed/);
    }
  });
});

// ---------------------------------------------------------------------------
// El documento: los bytes que puso el servidor
// ---------------------------------------------------------------------------

describe("el documento de CAP-03", () => {
  const PDF = "%PDF-1.7 documento sintético";
  const BYTES = new TextEncoder().encode(PDF);
  const base64 = Buffer.from(BYTES).toString("base64");

  function sobreDocumento(extra: Record<string, unknown> = {}) {
    return respuestaDe({
      documento: {
        doc_id: "b".repeat(64),
        tipo: "factura",
        medio: "application/pdf",
        bytes: BYTES.length,
        paginas: 3,
        origen: null,
        rango_paginas: null,
        contenido_base64: base64,
        ...extra,
      },
    });
  }

  it("se pide por huella y llegan los bytes exactos", async () => {
    const { transporte, pedidas } = transporteQueDevuelve(sobreDocumento());
    const cliente = crearCliente(transporte);

    const documento = await cliente.leerDocumento("CAP-03", CONTEXTO, "b".repeat(64));

    expect(pedidas[0]).toEqual({
      ruta: "/documentos",
      cuerpo: { contexto: CONTEXTO, datos: { doc_id: "b".repeat(64) } },
    });
    expect(documento.medio).toBe("application/pdf");
    expect(documento.paginas).toBe(3);
    expect(documento.bytes).toBe(BYTES.length);
    expect(Array.from(documento.contenido)).toEqual(Array.from(BYTES));
    expect(new TextDecoder().decode(documento.contenido)).toBe(PDF);
  });

  it("una parte de un PDF combinado dice de qué combinado sale y qué páginas es", async () => {
    const { transporte } = transporteQueDevuelve(
      sobreDocumento({ origen: "c".repeat(64), rango_paginas: [3, 5] }),
    );
    const cliente = crearCliente(transporte);

    const documento = await cliente.leerDocumento("CAP-03", CONTEXTO, "b".repeat(64));

    expect(documento.origen).toBe("c".repeat(64));
    expect(documento.rango_paginas).toEqual([3, 5]);
  });

  it("un documento truncado no se enseña a medias", async () => {
    const { transporte } = transporteQueDevuelve(sobreDocumento({ bytes: BYTES.length + 100 }));
    const cliente = crearCliente(transporte);

    const fallo = (await cliente
      .leerDocumento("CAP-03", CONTEXTO, "b".repeat(64))
      .catch((error: unknown) => error)) as ErrorApi;

    expect(fallo).toBeInstanceOf(ErrorApi);
    expect(fallo.mensaje).toContain("bytes");
  });

  it("una respuesta sin documento no se convierte en un documento vacío", async () => {
    const { transporte } = transporteQueDevuelve(respuestaDe({}));
    const cliente = crearCliente(transporte);

    await expect(cliente.leerDocumento("CAP-03", CONTEXTO, "b".repeat(64))).rejects.toBeInstanceOf(
      ErrorApi,
    );
  });
});

// ---------------------------------------------------------------------------
// El transporte HTTP y los tipos generados
// ---------------------------------------------------------------------------

describe("el transporte HTTP", () => {
  it("manda un POST con el sobre del contrato y no inventa la respuesta", async () => {
    const buscador = vi.fn<Buscador>(async () => ({
      status: 200,
      text: async () => JSON.stringify({ capacidad: "CAP-03" }),
    }));
    const transporte = transporteHttp("https://cae.example/api/", buscador);

    const respuesta = await transporte({ ruta: "/lecturas/CAP-03", cuerpo: { a: 1 } });

    expect(respuesta).toEqual({ estado: 200, cuerpo: { capacidad: "CAP-03" } });
    expect(buscador).toHaveBeenCalledWith("https://cae.example/api/lecturas/CAP-03", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ a: 1 }),
    });
  });

  it("un cuerpo que no es JSON no se adivina", async () => {
    const buscador: Buscador = async () => ({ status: 500, text: async () => "<html>vaya</html>" });
    const transporte = transporteHttp("https://cae.example/api", buscador);

    await expect(transporte({ ruta: "/lecturas/CAP-03", cuerpo: {} })).resolves.toEqual({
      estado: 500,
      cuerpo: null,
    });
  });
});

describe("los tipos salen del contrato y no de la cabeza de nadie (regla 4)", () => {
  it("los bloques generados son los que construye `api/proyeccion.py`", () => {
    expect(BLOQUES).toContain("documentos");
    expect(BLOQUES).toContain("veredicto");
    expect(new Set(BLOQUES).size).toBe(BLOQUES.length);
  });

  it("CAP-03 proyecta el contenido documental y CAP-40 no", () => {
    expect(LECTURAS["CAP-03"]).toContain("documentos");
    expect(LECTURAS["CAP-40"]).not.toContain("documentos");
  });

  it("lo que es comando no es lectura", () => {
    const lecturas = new Set(Object.keys(LECTURAS));
    for (const comando of COMANDOS) {
      expect(lecturas.has(comando)).toBe(false);
    }
  });
});

// ---------------------------------------------------------------------------
// Lo de siempre: nada de ejecución dinámica ni de HTML inyectado
// ---------------------------------------------------------------------------

describe("el cliente no ejecuta nada dinámico", () => {
  it.each(fuentesDelCliente())("%s", (_fichero, contenido) => {
    expect(contenido).not.toMatch(/\beval\s*\(/);
    expect(contenido).not.toMatch(/new\s+Function\s*\(/);
    expect(contenido).not.toMatch(/innerHTML/);
    expect(contenido).not.toMatch(/dangerouslySetInnerHTML/);
  });
});

/** El fuente sin comentarios: lo que de verdad se ejecuta. */
function sinComentarios(contenido: string): string {
  return contenido.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
}

function fuentesDelCliente(): ReadonlyArray<readonly [string, string]> {
  const directorio = join(import.meta.dirname, "..", "api");
  return readdirSync(directorio)
    .filter((fichero) => fichero.endsWith(".ts"))
    .map((fichero) => [fichero, readFileSync(join(directorio, fichero), "utf8")] as const);
}
