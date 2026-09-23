/**
 * `T-REV-cola` §10: un test por criterio de aceptacion, contra lo que `api/` sirve de verdad.
 *
 * Los datos son los de `datos/generar.py`: los siete casos sinteticos cargados en un tenant y las cuatro
 * lecturas de la pantalla pedidas a `api/`. De los siete, **el servidor deja cinco en la cola**: E y F
 * estan `PREVALIDADO` y sin nada que esperar, y una cola que reparte trabajo no reparte lo que no lo es.
 *
 * Lo que estos tests vigilan por encima de todo es lo que mas facil se rompe en una pantalla asi:
 *
 * - que el orden siga siendo del servidor (`CA-COLA-06`, `CA-COLA-14`, `R-UI-11`),
 * - que ninguna cifra de ahorro pase por `Number` ni salga como cero (`CA-COLA-02`, `CA-COLA-03`),
 * - y que un error del servidor se vea en vez de desaparecer (`CA-COLA-07`, `CA-COLA-08`).
 */

import { textos } from "@cae/compartido";
import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import * as propios from "../src/textos";
import {
  AHORA,
  celda,
  COLA,
  DENEGACION,
  DETALLE,
  fila,
  filasPintadas,
  ordenPintado,
  ORDEN_DEL_SERVIDOR,
  pintarCola,
  pintarColaEnVuelo,
} from "./apoyo";

afterEach(cleanup);

/** Lo que una celda de cifras nunca puede ensenar cuando no hay cifra (`R-UI-07`, `CA-COLA-02`). */
const FALSOS_CEROS = [/(^|\s)0([.,]\d+)?(\s|$)/, /—/, /^\s*$/];

const AHORRO = "cae-cola__celda-ahorro";
const MOTIVOS = "cae-cola__celda-motivos";
const VEREDICTO = "cae-cola__celda-veredicto";
const ESTADO = "cae-cola__celda-estado";

// ---------------------------------------------------------------------------
// CA-COLA-01 · una fila por actuacion con cola pendiente, y ninguna sin motivo
// ---------------------------------------------------------------------------

describe("CA-COLA-01 · toda fila declara por qué está ahí", () => {
  it("pinta una fila por actuación que el servidor puso en la cola, y ni una más", async () => {
    const { container } = await pintarCola();

    expect(ordenPintado(container)).toEqual(ORDEN_DEL_SERVIDOR);
    // Los siete casos estan cargados en el tenant; quien decide cuales esperan revision es el servidor.
    expect(ORDEN_DEL_SERVIDOR).not.toContain("E");
    expect(ORDEN_DEL_SERVIDOR).not.toContain("F");
  });

  it("ninguna fila se queda sin motivo", async () => {
    const { container } = await pintarCola();

    for (const pintada of filasPintadas(container)) {
      expect(pintada.querySelectorAll("li[data-motivo]").length).toBeGreaterThan(0);
      expect(pintada.querySelector(".cae-cola__sin-motivo")).toBeNull();
    }
  });

  it("una fila que llegara sin motivo se vería, no se escondería", async () => {
    const sinMotivos = (filas: readonly unknown[]) =>
      filas.map((cruda) => ({ ...(cruda as Record<string, unknown>), motivos: [] }));
    const { container } = await pintarCola({ filas: sinMotivos });

    expect(filasPintadas(container)).toHaveLength(ORDEN_DEL_SERVIDOR.length);
    expect(container.textContent).toContain(propios.MOTIVO_AUSENTE);
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-02 · el caso C: conflicto, BLOQUEADO y un ahorro que no existe
// ---------------------------------------------------------------------------

describe("CA-COLA-02 · el caso C dice su conflicto y no inventa un ahorro", () => {
  it("muestra el conflicto en PM, el veredicto BLOQUEADO y SIN DATO con el motivo del motor", async () => {
    const { container } = await pintarCola();
    const pintada = fila(container, "C");
    const motivo = (DETALLE["C"]?.["CAP-03"]?.datos["calculo"] as { motivo_no_calculo: string })
      .motivo_no_calculo;

    expect(celda(pintada, MOTIVOS)).toContain("Conflicto en PM");
    expect(celda(pintada, VEREDICTO)).toContain("BLOQUEADO");
    expect(celda(pintada, AHORRO)).toContain(textos.SIN_DATO);
    expect(celda(pintada, AHORRO)).toContain(motivo);
  });

  it("la columna de ahorro no queda vacía, ni a cero, ni con una raya", async () => {
    const { container } = await pintarCola();
    const texto = celda(fila(container, "C"), AHORRO);

    for (const falso of FALSOS_CEROS) {
      expect(texto).not.toMatch(falso);
    }
  });

  it("el conflicto se nombra sin enseñar ningún valor ni ninguna cita (`R-UI-09`)", async () => {
    const { container } = await pintarCola();
    const evidencias = DETALLE["C"]?.["CAP-03"]?.datos["evidencias"] as readonly {
      evidencias: readonly { texto_literal: string; doc_id: string }[];
    }[];
    const citas = evidencias.flatMap((dato) => dato.evidencias);
    expect(citas.length).toBeGreaterThan(0);

    // El bloque llega (no se filtra en el cliente: el filtrado es del servidor, `R-UI-12`) y no se pinta.
    for (const cita of citas) {
      expect(container.textContent).not.toContain(cita.texto_literal);
      expect(container.textContent).not.toContain(cita.doc_id);
    }
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-03 · el caso A: la cifra tal cual llega, con su rotulo
// ---------------------------------------------------------------------------

describe("CA-COLA-03 · la cifra se pinta tal cual la sirve `api/`", () => {
  it("muestra 305.829,6 envuelto en `RotuloPrevalidado`, con el aviso en el DOM", async () => {
    const { container } = await pintarCola();
    const pintada = fila(container, "A");
    const presentable = (
      DETALLE["A"]?.["CAP-03"]?.datos["calculo"] as { total_exacto_presentable: string }
    ).total_exacto_presentable;

    expect(presentable).toBe("305.829,6");
    const rotulo = pintada.querySelector(".cae-rotulo-prevalidado");
    expect(rotulo).not.toBeNull();
    expect(rotulo?.getAttribute("data-tipo")).toBe("AHORRO_PREVALIDADO");
    expect(rotulo?.textContent).toContain(presentable);
    expect(container.textContent).toContain(textos.ROTULO_AHORRO_PREVALIDADO);
  });

  it("la cadena del servidor se pinta entera y sin reformatear", async () => {
    const { container } = await pintarCola();
    const cifra = fila(container, "A").querySelector(".cae-cola__cifra");

    // Ni `305829.6`, ni `305829,6`, ni `305.830`: lo que llego. Convertirla a `Number` para volver a
    // darle formato seria pasar el ahorro por coma flotante (`CLAUDE.md` §2).
    expect(cifra?.textContent).toBe("305.829,6");
    expect(cifra?.getAttribute("data-exacto")).toBe("305829.6");
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-04 · el caso B: correccion pendiente y cifra provisional
// ---------------------------------------------------------------------------

describe("CA-COLA-04 · el caso B marca su corrección pendiente y su estimación", () => {
  it("muestra el motivo con su severidad y las dos carencias", async () => {
    const { container } = await pintarCola();
    const pintada = fila(container, "B");

    expect(celda(pintada, MOTIVOS)).toContain(`${propios.MOTIVO_CORRECCION} (SUBSANABLE)`);
    expect(celda(pintada, MOTIVOS)).toContain("R-DOC-01");
    expect(celda(pintada, MOTIVOS)).toContain("R-EVD-04");
  });

  it("marca la cifra como estimación no acreditada porque `calculo.provisional` es cierto", async () => {
    const { container } = await pintarCola();
    const calculo = DETALLE["B"]?.["CAP-03"]?.datos["calculo"] as { provisional: boolean };

    expect(calculo.provisional).toBe(true);
    expect(celda(fila(container, "B"), AHORRO)).toContain(propios.ESTIMACION_NO_ACREDITADA);
  });

  it("una cifra que no es provisional no sale marcada", async () => {
    const { container } = await pintarCola();

    expect(celda(fila(container, "A"), AHORRO)).not.toContain(propios.ESTIMACION_NO_ACREDITADA);
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-06 y CA-COLA-14 · el orden es del servidor
// ---------------------------------------------------------------------------

describe("CA-COLA-06 y CA-COLA-14 · la cola no ordena", () => {
  it("el orden del DOM es el orden en que llegan las filas", async () => {
    const { container } = await pintarCola();

    expect(ordenPintado(container)).toEqual(ORDEN_DEL_SERVIDOR);
  });

  it("las filas al revés se pintan al revés", async () => {
    const { container } = await pintarCola({ filas: (filas) => [...filas].reverse() });

    expect(ordenPintado(container)).toEqual([...ORDEN_DEL_SERVIDOR].reverse());
  });

  it("un orden cualquiera se pinta tal cual, aunque rompa la prioridad de los motivos", async () => {
    // A (tarea, prioridad 4) delante de C (conflicto, prioridad 1). Si la pantalla ordenara por
    // prioridad —que es lo que haria quien creyera estar ayudando— esto saldria al reves.
    const desordenar = (filas: readonly unknown[]) => [filas[4], filas[0], filas[2], filas[1], filas[3]];
    const { container } = await pintarCola({ filas: desordenar });

    expect(ordenPintado(container)).toEqual(["A", "C", "B", "D", "G"]);
  });

  it("ningún encabezado es un control de ordenación", async () => {
    const { container } = await pintarCola();
    const cabecera = container.querySelector("thead");

    expect(cabecera).not.toBeNull();
    expect(cabecera?.querySelectorAll("button, select, input, a, [aria-sort], [role='button']")).toHaveLength(
      0,
    );
    for (const encabezado of Array.from(cabecera?.querySelectorAll("th") ?? [])) {
      expect(encabezado.getAttribute("aria-sort")).toBeNull();
      expect(encabezado.getAttribute("tabindex")).toBeNull();
    }
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-07 · una lectura caida no tumba la cola
// ---------------------------------------------------------------------------

describe("CA-COLA-07 · una lectura de una actuación que falla deja su celda, no la cola", () => {
  const MOTIVO = "el repositorio no tiene esa actuación procesada";
  const soloC = (capacidad: string, actuacionId: string | null) =>
    capacidad === "CAP-03" && actuacionId === "C"
      ? { estado: 500, cuerpo: { error: "api", motivo: MOTIVO } }
      : null;

  it("la fila afectada se pinta con SIN DATO y el motivo del servidor", async () => {
    const { container } = await pintarCola({ respuesta: soloC });
    const texto = celda(fila(container, "C"), AHORRO);

    expect(texto).toContain(textos.SIN_DATO);
    expect(texto).toContain(MOTIVO);
  });

  it("las demás filas siguen completas", async () => {
    const { container } = await pintarCola({ respuesta: soloC });

    expect(ordenPintado(container)).toEqual(ORDEN_DEL_SERVIDOR);
    expect(celda(fila(container, "A"), AHORRO)).toContain("305.829,6");
    expect(celda(fila(container, "B"), AHORRO)).toContain("305.829,6");
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-08 · una denegacion se ensena
// ---------------------------------------------------------------------------

describe("CA-COLA-08 · un `ErrorPermiso` se muestra literal", () => {
  const denegar = (capacidad: string) => (capacidad === "CAP-17" ? DENEGACION : null);

  it("el mensaje del servidor aparece con su capacidad y su motivo", async () => {
    const { container } = await pintarCola({ respuesta: denegar });
    const motivo = (DENEGACION.cuerpo as { motivo: string }).motivo;

    expect(container.textContent).toContain(motivo);
    expect(container.textContent).toContain("CAP-17");
    expect(container.textContent).toContain(textos.ERROR_PERMISO);
    expect(container.querySelector('[role="alert"][data-clase="PERMISO"]')).not.toBeNull();
  });

  it("no se traga ni se disfraza de cola vacía", async () => {
    const { container } = await pintarCola({ respuesta: denegar });

    expect(container.textContent).not.toContain(propios.VACIO);
    expect(container.querySelector("table")).toBeNull();
    // Reintentar una denegacion no cambia nada en el servidor: no se ofrece.
    expect(container.querySelector("button")).toBeNull();
  });

  it("una denegación de una sola actuación deja la fila, con el motivo dentro", async () => {
    const soloD = (capacidad: string, actuacionId: string | null) =>
      capacidad === "CAP-03" && actuacionId === "D" ? DENEGACION : null;
    const { container } = await pintarCola({ respuesta: soloD });
    const motivo = (DENEGACION.cuerpo as { motivo: string }).motivo;

    expect(ordenPintado(container)).toEqual(ORDEN_DEL_SERVIDOR);
    expect(celda(fila(container, "D"), AHORRO)).toContain(motivo);
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-09 · vacio no es error y no es cero
// ---------------------------------------------------------------------------

describe("CA-COLA-09 · la cola vacía se distingue del error y de la carga", () => {
  it("con cero filas se ve el estado vacío con su texto", async () => {
    const { container } = await pintarCola({ filas: () => [] });

    expect(container.textContent).toContain(propios.VACIO);
    expect(container.textContent).toContain(propios.VACIO_DESCRIPCION);
    expect(container.querySelector("table")).toBeNull();
    // El aviso de origen sin declarar tambien es un `alert`: aqui se mira el del servidor.
    expect(container.querySelector(".cae-aviso-servidor")).toBeNull();
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it("el hueco de carga existe, es distinto del vacío y no pinta ninguna cifra", async () => {
    // Un transporte que no contesta nunca: la pantalla se queda en el estado de carga.
    const { container } = pintarColaEnVuelo();

    expect(container.querySelector('[role="status"]')).not.toBeNull();
    expect(container.textContent).toContain(propios.CARGANDO);
    expect(container.textContent).not.toContain(propios.VACIO);
    expect(container.querySelector(".cae-aviso-servidor")).toBeNull();
    expect(container.querySelector("table")).toBeNull();
    // Ninguna celda numerica aparece: el hueco de carga no es `SIN DATO` y no es un cero.
    expect(container.textContent).not.toContain(textos.SIN_DATO);
    expect(container.textContent).not.toMatch(/\d/);
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-12 · solo lectura tras `EN_PLATAFORMA`
// ---------------------------------------------------------------------------

describe("CA-COLA-12 · `R-UI-05` anticipado", () => {
  it("una actuación en EN_PLATAFORMA sin requerimiento abierto sale marcada solo lectura", async () => {
    const { container } = await pintarCola();
    const estados = DETALLE["G"]?.["CAP-14"]?.datos["estados_plataforma"] as {
      estado_ciclo: string;
      requerimiento_abierto: string | null;
    };

    expect(estados.estado_ciclo).toBe("EN_PLATAFORMA");
    expect(estados.requerimiento_abierto).toBeNull();
    expect(celda(fila(container, "G"), ESTADO)).toContain(propios.SOLO_LECTURA);
  });

  it("las que no están en la plataforma no salen marcadas", async () => {
    const { container } = await pintarCola();

    for (const actuacionId of ["A", "B", "C", "D"]) {
      expect(celda(fila(container, actuacionId), ESTADO)).not.toContain(propios.SOLO_LECTURA);
    }
  });
});

// ---------------------------------------------------------------------------
// CA-COLA-13 · la cabecera dice con qué rol se actúa y de dónde salen los datos
// ---------------------------------------------------------------------------

describe("CA-COLA-13 · rol y marca de origen", () => {
  it("muestra el nombre que devuelve `Respuesta.rol_nombre`, sin deducirlo ni componerlo", async () => {
    // Hasta el 23/09/2026 la cabecera pintaba el **codigo** del perfil ("actuando como T-REV") porque el
    // cliente ignoraba `rol_nombre`. Ahora `api/` lo sirve, leido de `engine/capacidades.yaml`, que es la
    // misma fuente que decide los permisos: se pinta tal cual llega (`GAP-COLA-06`, `ADR-012` §3 regla 1).
    const nombre = COLA.rol_nombre;
    const { container } = await pintarCola();
    const cabecera = container.querySelector(".cae-pantalla__cabecera");

    expect(nombre).toBeTruthy();
    expect(cabecera?.textContent).toContain(propios.ACTUANDO_COMO);
    expect(cabecera?.textContent).toContain(nombre);
    // Y no el codigo: componer el nombre a partir de el exigiria una tabla perfil -> nombre en el front.
    expect(cabecera?.textContent).not.toContain(COLA.rol);
  });

  it("una respuesta sin `rol_nombre` no pinta el código del perfil en su lugar", async () => {
    const sinNombre = () => ({ estado: 200, cuerpo: { ...COLA, rol_nombre: undefined } });
    const { container } = await pintarCola({
      respuesta: (capacidad) => (capacidad === "CAP-17" ? sinNombre() : null),
    });
    const cabecera = container.querySelector(".cae-pantalla__cabecera");

    expect(cabecera?.textContent).not.toContain(propios.ACTUANDO_COMO);
    expect(cabecera?.textContent).not.toContain(COLA.rol);
  });

  it("sin `origen_datos` (`GAP-COLA-03`) se lee ORIGEN DE DATOS SIN DECLARAR", async () => {
    const { container } = await pintarCola();
    const marca = container.querySelector(".cae-marca-origen");

    expect(marca?.textContent).toBe(textos.ORIGEN_SIN_DECLARAR);
    expect(marca?.getAttribute("data-origen")).toBe("SIN_DECLARAR");
  });

  it("el día que `api/` declare el origen, la cabecera lo dice", async () => {
    const conOrigen = (filas: readonly unknown[]) =>
      filas.map((cruda) => {
        const sobre = cruda as { identificacion: Record<string, unknown> };
        return { ...sobre, identificacion: { ...sobre.identificacion, origen_datos: "SINTETICO" } };
      });
    const { container } = await pintarCola({ filas: conOrigen });

    expect(container.querySelector(".cae-marca-origen")?.textContent).toBe(textos.ORIGEN_SINTETICO);
  });
});

// ---------------------------------------------------------------------------
// La cola no dispara comandos (`T-REV-cola` §4)
// ---------------------------------------------------------------------------

describe("la cola reparte trabajo: no ejerce ninguna capacidad que escriba", () => {
  it("solo pide lecturas, y solo las cuatro de la spec", async () => {
    const { pedidas } = await pintarCola();
    const capacidades = new Set(pedidas.map((peticion) => peticion.ruta));

    for (const ruta of capacidades) {
      expect(ruta.startsWith("/lecturas/")).toBe(true);
    }
    expect([...capacidades].sort()).toEqual([
      "/lecturas/CAP-03",
      "/lecturas/CAP-04",
      "/lecturas/CAP-14",
      "/lecturas/CAP-17",
    ]);
  });

  it("navega con los identificadores que le dio la lectura (`R-UI-12`)", async () => {
    const { container } = await pintarCola();

    for (const actuacionId of ORDEN_DEL_SERVIDOR) {
      const enlace = fila(container, actuacionId).querySelector("a");
      expect(enlace?.getAttribute("href")).toBe(`#/revision/${actuacionId}`);
    }
  });

  it("la antigüedad es la fecha que llegó, y sin historial sería SIN DATO", async () => {
    const { container } = await pintarCola();
    const pintada = fila(container, "G");

    expect(celda(pintada, "cae-cola__celda-antiguedad")).toContain("12/09/2026 08:30");
    expect(AHORA.toISOString()).toBe("2026-09-19T12:00:00.000Z");
    expect(celda(pintada, "cae-cola__celda-antiguedad")).toContain("hace 7 días");
  });

  it("una fila sin antigüedad dice SIN DATO y no 0 días", async () => {
    const sinFechas = (filas: readonly unknown[]) =>
      filas.map((cruda) => ({
        ...(cruda as Record<string, unknown>),
        antiguedad: { abierta_en: null, ultimo_movimiento_en: null },
      }));
    const { container } = await pintarCola({ filas: sinFechas });
    const texto = celda(fila(container, "A"), "cae-cola__celda-antiguedad");

    expect(texto).toContain(textos.SIN_DATO);
    expect(texto).not.toMatch(/0\s*d/i);
  });
});
