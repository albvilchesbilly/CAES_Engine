/**
 * `T-REV-revision` §12: un test por criterio de aceptacion, contra lo que `api/` sirve de verdad.
 *
 * Los datos son los de `datos/generar.py`: los siete casos sinteticos cargados en un tenant, las tres
 * lecturas de cada uno, los documentos servidos por su huella, **la correccion del caso C ejecutada de
 * verdad** y las cuatro negativas del servidor con sus palabras exactas. Ningun payload esta escrito a
 * mano: probar la pantalla contra la idea que tenemos del contrato es probar la idea, no la pantalla.
 *
 * Lo que estos tests vigilan por encima de todo es lo que mas facil se rompe en esta pantalla:
 *
 * - que no aparezca **ningun control que cambie el veredicto** (`CA-REV-01`, `R-UI-02`),
 * - que la correccion **no se envie sin justificacion** y que la que se escribe llegue literal
 *   (`CA-REV-02`, `CA-REV-03`, `R-UI-04`),
 * - que despues de corregir no se presente como actualizado lo que no lo esta (`CA-REV-09`),
 * - que **ningun dato se pinte sin su cita** (`CA-REV-05`, `R-UI-09`),
 * - y que un hueco no se lea nunca como un cero (`CA-REV-06`, `R-UI-07`).
 */

import { textos } from "@cae/compartido";
import { cleanup, fireEvent } from "@testing-library/react";
import { createHash } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";

import * as propios from "../src/textos";
import {
  CASO_CARENCIAS,
  CASO_COMPLETO,
  CASO_CONFLICTO,
  CASO_EN_PLATAFORMA,
  CASO_FUERA_DE_AMBITO,
  CORRECCION,
  DETALLE,
  DOCUMENTOS,
  RECHAZOS,
  RECORTES,
  REQUERIMIENTO,
  accion,
  bloqueDe,
  botonDe,
  botones,
  pintarRevision,
  pintarRevisionEnVuelo,
  waitFor,
} from "./apoyoRevision";

afterEach(cleanup);

/** Los cuatro veredictos del motor. El front los recibe; no los escribe, no los fija y no los ofrece. */
const VEREDICTOS = ["NO_ELEGIBLE", "BLOQUEADO", "SUBSANABLE", "PREVALIDADO"] as const;

/** Lo que una celda de cifras nunca puede ensenar cuando no hay cifra (`R-UI-07`). */
const FALSOS_CEROS = [/(^|\s)0([.,]\d+)?(\s|$)/, /—/];

/** El certificado del instalador del caso C: el documento al que salta la cita de 90 kW. */
const CERTIFICADO = "05_certificado_instalador.pdf";

function texto(elemento: Element | null): string {
  return elemento?.textContent ?? "";
}

function tarjetaConflicto(contenedor: HTMLElement): HTMLElement {
  const tarjeta = contenedor.querySelector<HTMLElement>(".cae-revision__conflicto");
  if (tarjeta === null) {
    throw new Error("no hay tarjeta de conflicto");
  }
  return tarjeta;
}

function filaDeValor(contenedor: HTMLElement, valor: string): HTMLElement {
  const fila = contenedor.querySelector<HTMLElement>(`.cae-revision__evidencia[data-valor="${valor}"]`);
  if (fila === null) {
    throw new Error(`no hay evidencia con valor ${valor}`);
  }
  return fila;
}

/** Abre el formulario de correccion desde la evidencia que dice `valor`. */
function usarValor(contenedor: HTMLElement, valor: string): HTMLFormElement {
  const boton = filaDeValor(contenedor, valor).querySelector<HTMLButtonElement>(
    ".cae-revision__usar-valor",
  );
  fireEvent.click(boton as HTMLButtonElement);
  const formulario = contenedor.querySelector<HTMLFormElement>(".cae-revision__correccion");
  if (formulario === null) {
    throw new Error("el formulario de correccion no se ha abierto");
  }
  return formulario;
}

function campo(formulario: HTMLFormElement, nombre: string): HTMLInputElement | HTMLTextAreaElement {
  const encontrado = formulario.querySelector<HTMLInputElement | HTMLTextAreaElement>(
    `[name="${nombre}"]`,
  );
  if (encontrado === null) {
    throw new Error(`el formulario no tiene el campo ${nombre}`);
  }
  return encontrado;
}

function escribir(elemento: HTMLElement, valor: string): void {
  fireEvent.change(elemento, { target: { value: valor } });
}

// ---------------------------------------------------------------------------
// CA-REV-01 · ningun control fija, fuerza ni cambia un veredicto (`R-UI-02`)
// ---------------------------------------------------------------------------

describe("CA-REV-01 · `R-UI-02`: el veredicto es texto, nunca un control", () => {
  it("ningún control de la pantalla lleva un veredicto ni por valor, ni por nombre, ni por acción", async () => {
    // El recorrido del arbol entero vive en `arbol.test.ts` y cubre esta carpeta sola; esto es la otra
    // mitad: lo que de verdad queda pintado con la actuacion mas conflictiva delante.
    const { container } = await pintarRevision(CASO_CONFLICTO);
    usarValor(container, "90");

    const controles = Array.from(
      container.querySelectorAll<HTMLElement>(
        "button, select, input, textarea, [contenteditable], [role='button'], [role='radio'], [role='checkbox']",
      ),
    );
    expect(controles.length).toBeGreaterThan(3);

    for (const control of controles) {
      const rastro = [
        control.textContent ?? "",
        control.getAttribute("value") ?? "",
        control.getAttribute("aria-label") ?? "",
        control.getAttribute("name") ?? "",
        control.getAttribute("title") ?? "",
      ].join(" ");
      for (const veredicto of VEREDICTOS) {
        expect(rastro, `un control ofrece ${veredicto}`).not.toContain(veredicto);
      }
    }
  });

  it("los únicos campos editables son el valor y la justificación de la corrección", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);
    usarValor(container, "90");

    const editables = Array.from(
      container.querySelectorAll<HTMLElement>("input, textarea, select, [contenteditable]"),
    );
    expect(editables.map((campo) => campo.getAttribute("name"))).toEqual(["valor", "justificacion"]);
  });

  it("el veredicto que llega se pinta, y es el que sirvió el servidor", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const servido = (bloqueDe(CASO_CONFLICTO, "CAP-03", "veredicto") as { valor: string }).valor;

    const pintado = container.querySelector(".cae-revision__veredicto-valor");
    expect(texto(pintado)).toContain(servido);
    expect(pintado?.tagName).toBe("P");
  });
});

// ---------------------------------------------------------------------------
// CA-REV-02 · la corrección exige justificación, y las dos barreras se comprueban
// ---------------------------------------------------------------------------

describe("CA-REV-02 · `R-UI-04`: sin justificación no se envía, y el servidor tampoco lo admite", () => {
  it("con la justificación vacía el control no envía nada", async () => {
    const { container, pedidas } = await pintarRevision(CASO_CONFLICTO);
    const formulario = usarValor(container, "90");
    const guardar = formulario.querySelector<HTMLButtonElement>(".cae-revision__guardar");

    expect(guardar?.disabled).toBe(true);
    fireEvent.click(guardar as HTMLButtonElement);
    fireEvent.submit(formulario);

    expect(pedidas.filter((peticion) => peticion.ruta.startsWith("/comandos/"))).toHaveLength(0);
    expect(container.textContent).toContain(propios.FALTA_LA_JUSTIFICACION);
  });

  it("una justificación en blanco tampoco cuenta", async () => {
    const { container, pedidas } = await pintarRevision(CASO_CONFLICTO);
    const formulario = usarValor(container, "90");
    escribir(campo(formulario, "justificacion"), "    ");
    fireEvent.submit(formulario);

    expect(pedidas.filter((peticion) => peticion.ruta.startsWith("/comandos/"))).toHaveLength(0);
  });

  it("una petición forzada sin justificación la rechaza `api/`, con sus palabras", async () => {
    // La segunda barrera, y es la que cuenta: el front inhabilita para explicar (`R-UI-01`). El motivo
    // es el que `api.contrato._comprobar_justificacion` levanto de verdad al generar los datos.
    const rechazo = RECHAZOS["sin_justificacion"] as {
      estado: number;
      cuerpo: { motivo: string };
    };
    let enviada = false;
    const { container } = await pintarRevision(CASO_CONFLICTO, {
      respuesta: (capacidad, cuerpo) => {
        if (capacidad !== "CAP-05") {
          return null;
        }
        const datos = (cuerpo as { datos: Record<string, unknown> }).datos;
        enviada = true;
        // Se le quita la justificacion por el camino, que es lo que "forzar la peticion" significa.
        return typeof datos["justificacion"] === "string"
          ? (rechazo as unknown as { estado: number; cuerpo: unknown })
          : null;
      },
    });
    const formulario = usarValor(container, "90");
    escribir(campo(formulario, "justificacion"), "da igual: el transporte la quita");
    fireEvent.submit(formulario);

    await waitFor(() => {
      expect(container.querySelector(".cae-aviso-servidor")).not.toBeNull();
    });
    expect(enviada).toBe(true);
    expect(container.textContent).toContain(rechazo.cuerpo.motivo);
    expect(rechazo.cuerpo.motivo).toContain("R-UI-04");
  });
});

// ---------------------------------------------------------------------------
// CA-REV-03 · la justificación la escribe la persona y viaja literal
// ---------------------------------------------------------------------------

describe("CA-REV-03 · `R-UI-04`: el campo nace vacío y lo que se escribe llega literal", () => {
  it("el campo nace vacío en todos los caminos de entrada al formulario", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);

    const primero = usarValor(container, "90");
    expect(campo(primero, "justificacion").value).toBe("");
    escribir(campo(primero, "justificacion"), "algo que se escribió y no se envió");

    // Otro camino de entrada: se elige otra evidencia. La justificacion **no** se arrastra.
    const segundo = usarValor(container, "110");
    expect(campo(segundo, "justificacion").value).toBe("");
    expect(campo(segundo, "valor").value).toBe("110");
  });

  it("la justificación que escribe la persona aparece literal en el payload de `CAP-05`", async () => {
    const escrita = CORRECCION.datos_enviados["justificacion"] as string;
    const { container, pedidas } = await pintarRevision(CASO_CONFLICTO);
    const formulario = usarValor(container, "90");
    escribir(campo(formulario, "justificacion"), escrita);
    fireEvent.submit(formulario);

    await waitFor(() => {
      expect(pedidas.some((peticion) => peticion.ruta === "/comandos/CAP-05")).toBe(true);
    });
    const enviada = pedidas.find((peticion) => peticion.ruta === "/comandos/CAP-05");
    const datos = (enviada?.cuerpo as { datos: Record<string, unknown> }).datos;

    expect(datos["justificacion"]).toBe(escrita);
    expect(datos["variable"]).toBe("PM");
    expect(datos["num_serie_motor"]).toBe("MTR-SYN-0001");
  });
});

// ---------------------------------------------------------------------------
// CA-REV-04 · R-UI-05: tras la firma, solo lectura salvo requerimiento oficial
// ---------------------------------------------------------------------------

describe("CA-REV-04 · `R-UI-05`: solo lectura tras la plataforma", () => {
  it("sin requerimiento abierto, ningún control de escritura está activo", async () => {
    const estados = bloqueDe(CASO_EN_PLATAFORMA, "CAP-14", "estados_plataforma") as {
      estado_ciclo: string;
      firmada: boolean;
      requerimiento_abierto: string | null;
    };
    expect(estados.estado_ciclo).toBe("EN_PLATAFORMA");
    expect(estados.requerimiento_abierto).toBeNull();

    const { container } = await pintarRevision(CASO_EN_PLATAFORMA);

    expect(container.textContent).toContain(propios.SOLO_LECTURA_FIRMADA);
    for (const bloque of Array.from(container.querySelectorAll<HTMLElement>("[data-capacidad]"))) {
      const boton = bloque.querySelector<HTMLButtonElement>("button");
      expect(boton?.disabled, `${bloque.getAttribute("data-capacidad")} está activo`).toBe(true);
    }
  });

  it("la lectura sigue entera: el documento se sigue pudiendo consultar", async () => {
    const { container } = await pintarRevision(CASO_EN_PLATAFORMA);
    const verDocumento = container.querySelectorAll(".cae-revision__ver-documento");

    expect(verDocumento.length).toBeGreaterThan(0);
    for (const boton of Array.from(verDocumento)) {
      expect((boton as HTMLButtonElement).disabled).toBe(false);
    }
  });

  it("si `CAP-14` no contesta, se cierra la escritura y se dice que no se sabe, no que esté firmada", async () => {
    const { container } = await pintarRevision(CASO_COMPLETO, {
      respuesta: (capacidad) =>
        capacidad === "CAP-14"
          ? { estado: 500, cuerpo: { error: "api", motivo: "el estado no ha contestado" } }
          : null,
    });

    expect(container.textContent).toContain(propios.ESCRITURA_SIN_ESTADO);
    expect(container.textContent).not.toContain(propios.SOLO_LECTURA_FIRMADA);
    expect(container.textContent).toContain("el estado no ha contestado");
    for (const bloque of Array.from(container.querySelectorAll<HTMLElement>("[data-capacidad]"))) {
      expect(bloque.querySelector("button")?.disabled).toBe(true);
    }
  });

  it("con requerimiento abierto, el candado se levanta solo para su flujo", async () => {
    const estados = REQUERIMIENTO.lecturas["CAP-14"]?.datos["estados_plataforma"] as {
      estado_ciclo: string;
      requerimiento_abierto: string | null;
    };
    // Lo que destapó generar.py: al reabrir, el ciclo **deja** de ser `EN_PLATAFORMA`. La condición
    // literal de la spec §9 (`EN_PLATAFORMA` y requerimiento abierto) no puede darse nunca.
    expect(estados.estado_ciclo).not.toBe("EN_PLATAFORMA");
    expect(estados.requerimiento_abierto).not.toBeNull();

    const { container } = await pintarRevision(CASO_EN_PLATAFORMA, { conRequerimiento: true });

    expect(container.textContent).toContain(propios.SOLO_LECTURA_REQUERIMIENTO);
    // El control del flujo de requerimiento ya no dice "solo lectura": dice su propio hueco.
    expect(texto(accion(container, "CAP-15"))).toContain(propios.INACTIVO_INTERPRETACION);
    expect(texto(accion(container, "CAP-15"))).not.toContain(propios.SOLO_LECTURA_REQUERIMIENTO);
    // Y el resto sigue cerrado.
    expect(texto(accion(container, "CAP-02"))).toContain(propios.SOLO_LECTURA_REQUERIMIENTO);
    expect(botonDe(container, "CAP-10").disabled).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// CA-REV-05 · ningún dato extraído se pinta sin su cita (`R-UI-09`)
// ---------------------------------------------------------------------------

describe("CA-REV-05 · `R-UI-09`: todo dato lleva documento, página y texto literal", () => {
  it("todos los datos del caso A se pintan, y cada uno con su cita", async () => {
    const servidos = bloqueDe(CASO_COMPLETO, "CAP-03", "evidencias") as readonly {
      variable: string;
      evidencias: readonly { doc_id: string; pagina: number; texto_literal: string }[];
    }[];
    const { container } = await pintarRevision(CASO_COMPLETO);
    const filas = Array.from(container.querySelectorAll<HTMLElement>("[data-dato]"));

    expect(filas).toHaveLength(servidos.length);
    for (const fila of filas) {
      const citas = Array.from(fila.querySelectorAll<HTMLElement>("[data-cita]"));
      expect(citas.length, `${fila.getAttribute("data-dato")} sin cita`).toBeGreaterThan(0);
      for (const cita of citas) {
        expect(cita.getAttribute("data-doc")).toBeTruthy();
        expect(cita.getAttribute("data-pagina")).not.toBeNull();
        expect(texto(cita.querySelector(".cae-revision__literal")).length).toBeGreaterThan(0);
      }
    }
  });

  it("el recorte del fichero de pruebas está declarado, no escondido", () => {
    // `generar.py` deja fuera las evidencias que no caben (hoy una: el CSV entero del registro). Se
    // declara aqui para que "todos los datos" signifique lo mismo en el test y en el servidor.
    expect(RECORTES.evidencias_omitidas[CASO_COMPLETO]).toEqual(["registro.datos_canonicos"]);
    expect(RECORTES.evidencia_maxima_bytes).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// CA-REV-06 · el caso C: la tarjeta de conflicto por encima del ahorro
// ---------------------------------------------------------------------------

describe("CA-REV-06 · caso C: el conflicto arriba y el ahorro SIN DATO", () => {
  it("la tarjeta de conflicto va antes que el bloque de ahorro en el DOM", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const tarjeta = tarjetaConflicto(container);
    const ahorro = container.querySelector(".cae-revision__ahorro");

    expect(ahorro).not.toBeNull();
    expect(tarjeta.compareDocumentPosition(ahorro as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("muestra todas las evidencias que llegaron, con valor, documento, página, texto, método y confianza", async () => {
    const conflictos = bloqueDe(CASO_CONFLICTO, "CAP-03", "conflictos") as readonly {
      variable: string;
      evidencias: readonly {
        valor: string;
        pagina: number;
        texto_literal: string;
        metodo: string;
        confianza: string;
      }[];
    }[];
    const evidencias = conflictos[0]?.evidencias ?? [];
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const tarjeta = tarjetaConflicto(container);

    // Por posicion y no por valor: dos fuentes distintas dicen 110, y las dos tienen que estar.
    const filas = Array.from(tarjeta.querySelectorAll<HTMLElement>(".cae-revision__evidencia"));
    expect(filas).toHaveLength(evidencias.length);
    evidencias.forEach((evidencia, posicion) => {
      const fila = filas[posicion] as HTMLElement;
      expect(fila.getAttribute("data-valor")).toBe(evidencia.valor);
      expect(texto(fila)).toContain(evidencia.texto_literal);
      expect(texto(fila)).toContain(evidencia.metodo);
      expect(texto(fila)).toContain(evidencia.confianza);
      expect(fila.querySelector("[data-pagina]")).not.toBeNull();
    });
    expect(texto(tarjeta)).toContain(propios.CONFLICTO_EXPLICACION);
    // La tarjeta se apoya en la ficha, no en el calculo (§6): descripcion, referencia y valores por
    // fuente existen con calculo y sin el, y aqui no hay ninguno.
    expect(texto(tarjeta)).toContain("Potencia nominal de salida del motor sin variador");
    expect(texto(tarjeta)).toContain("SRC-FICHA");
    expect((bloqueDe(CASO_CONFLICTO, "CAP-03", "calculo") as { por_unidad: [] }).por_unidad).toEqual([]);
  });

  it("el ahorro se lee SIN DATO con el motivo del motor, y nunca 0", async () => {
    const calculo = bloqueDe(CASO_CONFLICTO, "CAP-03", "calculo") as { motivo_no_calculo: string };
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const ahorro = texto(container.querySelector(".cae-revision__ahorro"));

    expect(ahorro).toContain(textos.SIN_DATO);
    expect(ahorro).toContain(calculo.motivo_no_calculo);
    for (const falso of FALSOS_CEROS) {
      expect(ahorro).not.toMatch(falso);
    }
  });
});

// ---------------------------------------------------------------------------
// CA-REV-07 · el caso C en dos pulsaciones
// ---------------------------------------------------------------------------

describe("CA-REV-07 · caso C: ver la cita y precargar la corrección", () => {
  it("«Ver en el documento» lleva el panel izquierdo al certificado, página 1", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const fila = filaDeValor(tarjetaConflicto(container), "90");
    const ir = fila.querySelector<HTMLButtonElement>(".cae-revision__ver-documento");

    expect(ir?.getAttribute("data-pagina")).toBe("1");
    fireEvent.click(ir as HTMLButtonElement);

    const panel = container.querySelector(".cae-revision__panel-documento");
    await waitFor(() => {
      expect(texto(panel)).toContain(CERTIFICADO);
    });
    expect(texto(panel)).toContain(`${propios.ETIQUETA_PAGINA} 1`);
    expect(texto(panel)).toContain("a) Potencia nominal del motor PM (según ficha técnica) 90 kW");
  });

  it("«Usar este valor» abre el formulario precargado y con la justificación vacía", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const formulario = usarValor(container, "90");

    expect(texto(formulario.querySelector('[data-campo="variable"]'))).toBe("PM");
    expect(texto(formulario.querySelector('[data-campo="num_serie_motor"]'))).toBe("MTR-SYN-0001");
    expect(campo(formulario, "valor").value).toBe("90");
    expect(campo(formulario, "justificacion").value).toBe("");
  });
});

// ---------------------------------------------------------------------------
// CA-REV-08 · nada de coma flotante
// ---------------------------------------------------------------------------

describe("CA-REV-08 · el valor viaja como cadena", () => {
  it("el campo del valor es de texto y lo que se envía es una cadena", async () => {
    const { container, pedidas } = await pintarRevision(CASO_CONFLICTO);
    const formulario = usarValor(container, "90");
    expect(campo(formulario, "valor").getAttribute("type")).toBe("text");

    escribir(campo(formulario, "justificacion"), "el certificado arrastra una errata");
    fireEvent.submit(formulario);

    await waitFor(() => {
      expect(pedidas.some((peticion) => peticion.ruta === "/comandos/CAP-05")).toBe(true);
    });
    const enviada = pedidas.find((peticion) => peticion.ruta === "/comandos/CAP-05");
    const datos = (enviada?.cuerpo as { datos: Record<string, unknown> }).datos;

    expect(typeof datos["valor"]).toBe("string");
  });

  it("un `number` lo rechaza `api/`, con el motivo de `_sin_coma_flotante`", async () => {
    const rechazo = RECHAZOS["coma_flotante"] as { cuerpo: { motivo: string } };
    const { container } = await pintarRevision(CASO_CONFLICTO, {
      respuesta: (capacidad) =>
        capacidad === "CAP-05" ? (rechazo as unknown as { estado: number; cuerpo: unknown }) : null,
    });
    const formulario = usarValor(container, "90");
    escribir(campo(formulario, "justificacion"), "un cliente que mandara un número recibiría esto");
    fireEvent.submit(formulario);

    await waitFor(() => {
      expect(container.querySelector(".cae-aviso-servidor")).not.toBeNull();
    });
    expect(container.textContent).toContain(rechazo.cuerpo.motivo);
    expect(rechazo.cuerpo.motivo).toContain("coma flotante");
  });
});

// ---------------------------------------------------------------------------
// CA-REV-09 · lo que no se ha recalculado no se presenta como actualizado
// ---------------------------------------------------------------------------

describe("CA-REV-09 · el recálculo se dice, no se supone", () => {
  it("cuando el servidor dice que no recalculó, el veredicto y el ahorro salen marcados", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO, { sinRecalculo: true });
    const formulario = usarValor(container, "110");
    escribir(campo(formulario, "justificacion"), "la ficha técnica del motor es la fuente primaria");
    fireEvent.submit(formulario);

    await waitFor(() => {
      expect(container.querySelectorAll(".cae-revision__pendiente").length).toBeGreaterThan(0);
    });
    const pendientes = Array.from(container.querySelectorAll(".cae-revision__pendiente"));
    expect(pendientes).toHaveLength(2);
    expect(texto(container.querySelector(".cae-revision__veredicto"))).toContain(
      propios.PENDIENTE_DE_RECALCULO,
    );
    expect(texto(container.querySelector(".cae-revision__ahorro"))).toContain(
      propios.PENDIENTE_DE_RECALCULO,
    );
    // Y el aviso del servidor se ensena tal cual, en vez de dejarlo en un detalle de implementacion.
    expect(container.textContent).toContain("pendiente de recalculo");
  });

  it("cuando sí recalculó, no se marca nada pendiente y se dice que el motor volvió a calcular", async () => {
    expect(CORRECCION.respuesta.datos["recalculada"]).toBe(true);
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const formulario = usarValor(container, "110");
    escribir(campo(formulario, "justificacion"), "la ficha técnica del motor es la fuente primaria");
    fireEvent.submit(formulario);

    await waitFor(() => {
      expect(container.textContent).toContain(propios.CORRECCION_RECALCULADA);
    });
    expect(container.querySelectorAll(".cae-revision__pendiente")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// El caso C de punta a punta: el conflicto resuelto en menos de un minuto (§6)
// ---------------------------------------------------------------------------

describe("El caso C de punta a punta: ver, comprobar, corregir y volver a calcular", () => {
  it("de BLOQUEADO sin ahorro a PREVALIDADO con 305.829,6, sin tocar ningún veredicto", async () => {
    const antes = bloqueDe(CASO_CONFLICTO, "CAP-03", "veredicto") as { valor: string };
    const despues = CORRECCION.despues["CAP-03"]?.datos["veredicto"] as { valor: string };
    const calculo = CORRECCION.despues["CAP-03"]?.datos["calculo"] as {
      total_exacto_presentable: string;
      total_unidad: string;
    };
    const { container, pedidas } = await pintarRevision(CASO_CONFLICTO);

    // 1. Se ve el conflicto, con las evidencias enfrentadas y su cita.
    const tarjeta = tarjetaConflicto(container);
    expect(texto(container.querySelector(".cae-revision__veredicto"))).toContain(antes.valor);
    expect(filaDeValor(tarjeta, "90")).toBeTruthy();
    expect(filaDeValor(tarjeta, "110")).toBeTruthy();

    // 2. Se comprueba en el papel: el panel izquierdo salta al certificado.
    fireEvent.click(
      filaDeValor(tarjeta, "90").querySelector(".cae-revision__ver-documento") as HTMLButtonElement,
    );
    await waitFor(() => {
      expect(texto(container.querySelector(".cae-revision__panel-documento"))).toContain(CERTIFICADO);
    });

    // 3. Se elige el valor de la fuente primaria y se escribe la justificacion (obligatoria).
    const formulario = usarValor(container, "110");
    expect(campo(formulario, "justificacion").value).toBe("");
    escribir(campo(formulario, "justificacion"), CORRECCION.datos_enviados["justificacion"] as string);
    fireEvent.submit(formulario);

    // 4. El motor recalcula y la pantalla ensena el veredicto nuevo con su ahorro.
    await waitFor(() => {
      expect(texto(container.querySelector(".cae-revision__veredicto"))).toContain(despues.valor);
    });
    expect(despues.valor).not.toBe(antes.valor);
    expect(container.querySelector(".cae-revision__conflicto")).toBeNull();
    expect(texto(container.querySelector(".cae-revision__ahorro"))).toContain("305.829,6");
    expect(texto(container.querySelector(".cae-revision__ahorro"))).toContain(calculo.total_unidad);
    expect(calculo.total_exacto_presentable).toBe("305.829,6");

    // 5. La correccion queda en el historial con su justificacion, y "Aprobar" ya no está impedido.
    expect(container.textContent).toContain(propios.ETIQUETA_JUSTIFICACION_REGISTRADA);
    expect(botonDe(container, "CAP-10").disabled).toBe(false);

    // Y en todo el recorrido no se ha pedido nada que no sea del contrato.
    for (const peticion of pedidas) {
      expect(peticion.ruta).toMatch(/^\/(lecturas\/CAP-(03|04|14)|comandos\/CAP-05|documentos)$/);
    }
  });
});

// ---------------------------------------------------------------------------
// CA-REV-10 y CA-REV-11 · el caso A: la cifra y su procedencia
// ---------------------------------------------------------------------------

describe("CA-REV-10 · caso A: 305.829,6 con su rótulo y su truncado", () => {
  it("la cifra sale con su unidad, su rótulo y el truncado con la etiqueta de INT-06", async () => {
    const calculo = bloqueDe(CASO_COMPLETO, "CAP-03", "calculo") as {
      total_exacto_presentable: string;
      total_cae_presentable: string;
      total_unidad: string;
    };
    const { container } = await pintarRevision(CASO_COMPLETO);
    const ahorro = container.querySelector<HTMLElement>(".cae-revision__ahorro");

    expect(calculo.total_exacto_presentable).toBe("305.829,6");
    expect(texto(ahorro?.querySelector(".cae-revision__cifra") ?? null)).toBe(
      `${calculo.total_exacto_presentable} ${calculo.total_unidad}`,
    );
    expect(texto(ahorro)).toContain(textos.ROTULO_AHORRO_PREVALIDADO);
    expect(texto(ahorro?.querySelector(".cae-revision__cifra-cae") ?? null)).toBe(
      `${calculo.total_cae_presentable} ${calculo.total_unidad}`,
    );
    expect(texto(ahorro)).toContain(propios.TRUNCADO_INT06);
  });

  it("las líneas de procedencia llevan su cita o su origen de tabla", async () => {
    const { container } = await pintarRevision(CASO_COMPLETO);
    const lineas = Array.from(container.querySelectorAll<HTMLElement>("[data-magnitud]"));

    // Seis entradas y tres derivadas en `IND240`, y ninguna se queda sin decir de donde sale.
    expect(lineas.length).toBeGreaterThanOrEqual(6);
    for (const linea of lineas) {
      const tieneCita = linea.querySelector("[data-cita]") !== null;
      const tieneFuente = linea.querySelector("[data-fuente]") !== null;
      expect(tieneCita || tieneFuente, `${linea.getAttribute("data-magnitud")} sin origen`).toBe(true);
    }
  });
});

describe("CA-REV-11 · caso A: los INT-xx son criterio propio y el cuadro 6 se declara", () => {
  it("cada criterio aplicado se nombra como criterio propio, nunca como norma", async () => {
    const calculo = bloqueDe(CASO_COMPLETO, "CAP-03", "calculo") as {
      por_unidad: readonly { interpretaciones: readonly string[] }[];
    };
    const aplicados = calculo.por_unidad[0]?.interpretaciones ?? [];
    const { container } = await pintarRevision(CASO_COMPLETO);

    expect(aplicados.length).toBeGreaterThan(0);
    for (const criterio of aplicados) {
      const pintado = container.querySelector(`[data-criterio="${criterio}"]`);
      expect(pintado, `${criterio} no se pinta`).not.toBeNull();
      expect(texto(pintado)).toContain(propios.CRITERIO_PROPIO);
    }
    expect(container.textContent).not.toContain("según la normativa");
  });

  it("la fila del cuadro 6 (110 kW → 5,55) se muestra con su tabla de origen", async () => {
    const { container } = await pintarRevision(CASO_COMPLETO);
    const perdidas = container.querySelector<HTMLElement>('[data-magnitud="perdidas_ref_kw"]');

    expect(texto(perdidas)).toContain("5,55");
    expect(perdidas?.querySelector("[data-fuente]")?.getAttribute("data-fuente")).toBe(
      "tabla:REG1781_CUADRO6",
    );
    // La fila exacta la dice la traza del motor, tal y como la escribe el motor.
    const traza = texto(container.querySelector(".cae-revision__traza"));
    expect(traza).toContain("fila exacta kw_motor = 110");
  });
});

// ---------------------------------------------------------------------------
// CA-REV-12 y CA-REV-13 · carencias, estimación y el botón de aprobar
// ---------------------------------------------------------------------------

describe("CA-REV-12 · caso B: dos carencias, estimación no acreditada y aprobar impedido", () => {
  it("las dos carencias se ven con su severidad y el documento que las subsana", async () => {
    const carencias = (
      bloqueDe(CASO_CARENCIAS, "CAP-04", "que_te_falta") as {
        carencias: readonly { id: string; severidad: string; documentos: readonly string[] }[];
      }
    ).carencias;
    const { container } = await pintarRevision(CASO_CARENCIAS);

    expect(carencias).toHaveLength(2);
    for (const carencia of carencias) {
      const pintada = container.querySelector<HTMLElement>(`[data-carencia="${carencia.id}"]`);
      expect(pintada, `${carencia.id} no se pinta`).not.toBeNull();
      expect(texto(pintada)).toContain(carencia.severidad);
      expect(texto(pintada)).toContain(carencia.documentos[0] as string);
    }
  });

  it("la cifra sale marcada estimación no acreditada", async () => {
    const calculo = bloqueDe(CASO_CARENCIAS, "CAP-03", "calculo") as { provisional: boolean };
    const { container } = await pintarRevision(CASO_CARENCIAS);

    expect(calculo.provisional).toBe(true);
    expect(texto(container.querySelector(".cae-revision__ahorro"))).toContain(
      propios.ESTIMACION_NO_ACREDITADA,
    );
  });

  it("«Aprobar» está inhabilitado con el motivo al lado", async () => {
    const { container } = await pintarRevision(CASO_CARENCIAS);

    expect(botonDe(container, "CAP-10").disabled).toBe(true);
    expect(texto(accion(container, "CAP-10"))).toContain("R-DOC-01");
    expect(texto(accion(container, "CAP-10"))).toContain("SUBSANABLE");
  });
});

describe("CA-REV-13 · «Aprobar» solo sin bloqueantes abiertos", () => {
  it("con el caso A está activo, y dice que aprobar no es enviar", async () => {
    const { container } = await pintarRevision(CASO_COMPLETO);

    expect(botonDe(container, "CAP-10").disabled).toBe(false);
    expect(texto(accion(container, "CAP-10"))).toContain(propios.APROBAR_NOTA);
  });

  it("con el caso C está inhabilitado y muestra la regla concreta que lo impide", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);
    const bloque = accion(container, "CAP-10");

    expect(botonDe(container, "CAP-10").disabled).toBe(true);
    expect(texto(bloque)).toContain("R-CON-01");
    expect(texto(bloque)).toContain("BLOQUEANTE_DATOS");
    expect(texto(bloque)).toContain("PM coincide en todas las fuentes");
  });

  it("si no se ha podido saber qué falta, no se aprueba", async () => {
    // `CAP-04` caida: no saber si falta algo no es saber que no falta nada.
    const { container } = await pintarRevision(CASO_COMPLETO, {
      respuesta: (capacidad) =>
        capacidad === "CAP-04"
          ? { estado: 500, cuerpo: { error: "api", motivo: "la lectura no ha contestado" } }
          : null,
    });

    expect(botonDe(container, "CAP-10").disabled).toBe(true);
    expect(container.textContent).toContain("la lectura no ha contestado");
  });

  it("con el caso D, fuera de ámbito, aparece el control de descarte y dice por qué no está activo", async () => {
    const { container } = await pintarRevision(CASO_FUERA_DE_AMBITO);

    expect(botonDe(container, "CAP-08").disabled).toBe(true);
    expect(texto(accion(container, "CAP-08"))).toContain(propios.INACTIVO_SIN_TEXTO);
  });
});

// ---------------------------------------------------------------------------
// CA-REV-14 y CA-REV-15 · los textos
// ---------------------------------------------------------------------------

describe("CA-REV-14 · `R-UI-03`: ningún control se llama «Firmar»", () => {
  it("ningún botón de la pantalla contiene «Firmar» como acción", async () => {
    const { container } = await pintarRevision(CASO_EN_PLATAFORMA);

    for (const boton of botones(container)) {
      expect(texto(boton)).not.toMatch(/firmar/i);
    }
  });

  it("tampoco lo contiene el catálogo de textos de la pantalla", () => {
    for (const literal of Object.values(propios.TEXTOS)) {
      expect(literal).not.toMatch(/\bfirmar\b/i);
    }
  });
});

describe("CA-REV-15 · el descargo del servidor se muestra literal y no entra en el catálogo", () => {
  it("se pinta entero, sin recortar", async () => {
    const veredicto = bloqueDe(CASO_COMPLETO, "CAP-03", "veredicto") as { descargo: string };
    const { container } = await pintarRevision(CASO_COMPLETO);

    expect(veredicto.descargo.length).toBeGreaterThan(0);
    expect(texto(container.querySelector(".cae-revision__descargo"))).toBe(veredicto.descargo);
  });

  it("y no está en el catálogo de textos del front (§11 bis)", () => {
    const veredicto = bloqueDe(CASO_COMPLETO, "CAP-03", "veredicto") as { descargo: string };

    expect(Object.values(propios.TEXTOS)).not.toContain(veredicto.descargo);
    // La lista completa de formulas prohibidas la recorre `textos.test.ts` sobre este mismo catalogo.
    for (const literal of Object.values(propios.TEXTOS)) {
      expect(literal).not.toMatch(/verificador/i);
      expect(literal).not.toMatch(/garantiz/i);
    }
  });
});

// ---------------------------------------------------------------------------
// CA-REV-16 y CA-REV-17 · el documento
// ---------------------------------------------------------------------------

describe("CA-REV-16 · el documento se sirve sin transformar y con su huella comprobada", () => {
  it("lo que decodifica el cliente suma exactamente el `doc_id`", () => {
    const servidos = DOCUMENTOS[CASO_CONFLICTO] ?? {};
    const entradas = Object.entries(servidos);
    expect(entradas.length).toBeGreaterThan(0);

    for (const [docId, respuesta] of entradas) {
      const documento = respuesta.datos["documento"] as { contenido_base64: string; bytes: number };
      const bytes = Buffer.from(documento.contenido_base64, "base64");
      expect(createHash("sha256").update(bytes).digest("hex"), `${docId} no casa`).toBe(docId);
      expect(bytes.length).toBe(documento.bytes);
    }
  });

  it("con un documento alterado no se enseña nada en su lugar, y se avisa", async () => {
    const alterado = RECHAZOS["documento_alterado"] as {
      doc_id: string;
      cuerpo: { motivo: string };
    };
    const { container } = await pintarRevision(CASO_CONFLICTO, {
      respuesta: (capacidad, cuerpo) => {
        const datos = (cuerpo as { datos?: Record<string, unknown> }).datos ?? {};
        return datos["doc_id"] === alterado.doc_id
          ? (alterado as unknown as { estado: number; cuerpo: unknown })
          : null;
      },
    });
    const panel = container.querySelector<HTMLElement>(".cae-revision__panel-documento");

    await waitFor(() => {
      expect(panel?.querySelector(".cae-aviso-servidor")).not.toBeNull();
    });
    expect(texto(panel)).toContain("fue alterado despues de la ingesta");
    expect(panel?.querySelector(".cae-revision__visor")).toBeNull();
    // Y el panel derecho sigue funcionando: revisar el veredicto no espera a un PDF.
    expect(container.querySelector(".cae-revision__veredicto")).not.toBeNull();
    expect(container.querySelector(".cae-revision__conflicto")).not.toBeNull();
  });

  it("este entorno no tiene visor, y se dice en vez de fingir uno", async () => {
    const { container } = await pintarRevision(CASO_CONFLICTO);

    await waitFor(() => {
      expect(container.querySelector(".cae-revision__sin-visor")).not.toBeNull();
    });
    expect(texto(container.querySelector(".cae-revision__panel-documento"))).toContain(
      propios.DOCUMENTO_INTACTO,
    );
  });
});

describe("CA-REV-17 · una parte de un PDF combinado se dice, con su rango de páginas", () => {
  it("el panel avisa de que es una parte y da las páginas del original", async () => {
    const documentos = bloqueDe(CASO_EN_PLATAFORMA, "CAP-03", "documentos") as readonly {
      doc_id: string;
      origen: string | null;
      rango_paginas: readonly number[] | null;
    }[];
    const parte = documentos.find((documento) => documento.origen !== null);
    expect(parte).toBeDefined();

    const { container } = await pintarRevision(CASO_EN_PLATAFORMA);
    const cita = container.querySelector<HTMLButtonElement>(
      `.cae-revision__ver-documento[data-doc="${parte?.doc_id}"]`,
    );
    expect(cita).not.toBeNull();
    fireEvent.click(cita as HTMLButtonElement);

    const panel = container.querySelector(".cae-revision__panel-documento");
    await waitFor(() => {
      expect(texto(panel)).toContain(propios.DOCUMENTO_ES_PARTE);
    });
    const [desde, hasta] = parte?.rango_paginas ?? [];
    expect(texto(panel)).toContain(`${desde}-${hasta}`);
  });

  it("el aviso que escribe `api/` no llega al cliente: lo pierde `leerDocumento`", () => {
    // Hallazgo de `FR1.c`. `api.lecturas.documentos.leer_documento` devuelve el aviso del combinado en
    // `Respuesta.avisos`, y `crearCliente(...).leerDocumento` construye el `DocumentoServido` y se deja
    // los avisos por el camino (`front/compartido/api/cliente.ts`, `documentoDe`). La pantalla dice que
    // es una parte con `origen` y `rango_paginas`, que si llegan, y **no** se inventa el texto.
    const servidos = DOCUMENTOS[CASO_EN_PLATAFORMA] ?? {};
    const conAviso = Object.values(servidos).filter((respuesta) => respuesta.avisos.length > 0);

    expect(conAviso.length).toBeGreaterThan(0);
    expect(conAviso[0]?.avisos[0]).toContain("es una parte del PDF combinado");
  });
});

// ---------------------------------------------------------------------------
// CA-REV-18 · los errores se muestran literales
// ---------------------------------------------------------------------------

describe("CA-REV-18 · un error se muestra, no se traga", () => {
  it("un `ErrorPermiso` sale con el motivo del servidor", async () => {
    const denegacion = RECHAZOS["otro_tenant"] as { cuerpo: { motivo: string } };
    const { container } = await pintarRevision(CASO_COMPLETO, {
      respuesta: (capacidad) =>
        capacidad === "CAP-03"
          ? (denegacion as unknown as { estado: number; cuerpo: unknown })
          : null,
    });

    await waitFor(() => {
      expect(container.querySelector(".cae-aviso-servidor")).not.toBeNull();
    });
    expect(container.textContent).toContain(denegacion.cuerpo.motivo);
    expect(container.textContent).toContain(textos.ERROR_PERMISO);
    expect(container.textContent).not.toContain("no hay datos");
  });

  it("un `ErrorApi` sale literal y con «Reintentar»", async () => {
    const motivo = "la actuacion 'A' no esta procesada todavia; no hay nada que leer";
    const { container } = await pintarRevision(CASO_COMPLETO, {
      respuesta: (capacidad) =>
        capacidad === "CAP-03" ? { estado: 500, cuerpo: { error: "api", motivo } } : null,
    });

    await waitFor(() => {
      expect(container.querySelector(".cae-aviso-servidor")).not.toBeNull();
    });
    expect(container.textContent).toContain(motivo);
    expect(container.textContent).toContain(propios.REINTENTAR);
  });

  it("mientras las lecturas están en vuelo no se pinta ninguna cifra", () => {
    const { container } = pintarRevisionEnVuelo();

    expect(container.querySelector('[role="status"]')).not.toBeNull();
    expect(container.textContent).toContain(propios.CARGANDO_REVISION);
    expect(container.querySelector(".cae-revision__cifra")).toBeNull();
    expect(container.textContent).not.toContain(textos.SIN_DATO);
  });
});

// ---------------------------------------------------------------------------
// CA-REV-19 y CA-REV-20 · el ruido, y el caso A entero
// ---------------------------------------------------------------------------

describe("CA-REV-19 · lo que cumple no ocupa sitio", () => {
  it("las comprobaciones conformes van plegadas tras un contador", async () => {
    const veredicto = bloqueDe(CASO_COMPLETO, "CAP-03", "veredicto") as {
      reglas: readonly { resultado: string }[];
    };
    const conformes = veredicto.reglas.filter((regla) => regla.resultado === "CUMPLE");
    const { container } = await pintarRevision(CASO_COMPLETO);
    const plegado = container.querySelector<HTMLDetailsElement>(".cae-revision__conformes");

    expect(conformes.length).toBeGreaterThan(0);
    expect(plegado?.open).toBe(false);
    expect(texto(plegado?.querySelector("summary") ?? null)).toBe(
      `${conformes.length} ${propios.COMPROBACIONES_CONFORMES}`,
    );
  });

  it("los datos que no entran en el cálculo también van plegados", async () => {
    const calculo = bloqueDe(CASO_COMPLETO, "CAP-03", "calculo") as {
      por_unidad: readonly { entradas: Record<string, string> }[];
    };
    const servidos = bloqueDe(CASO_COMPLETO, "CAP-03", "evidencias") as readonly { variable: string }[];
    const entradas = Object.keys(calculo.por_unidad[0]?.entradas ?? {});
    const { container } = await pintarRevision(CASO_COMPLETO);
    const plegado = container.querySelector<HTMLDetailsElement>(".cae-revision__resto-datos");
    const visibles = container.querySelectorAll(".cae-revision__datos-calculo [data-dato]");

    expect(entradas).toHaveLength(6);
    expect(visibles).toHaveLength(6);
    expect(plegado?.open).toBe(false);
    expect(plegado?.getAttribute("data-cuenta")).toBe(String(servidos.length - 6));
  });
});

describe("CA-REV-20 · el caso A recorre la pantalla entera, sin datos inventados", () => {
  it("pide las tres lecturas y el documento, y nada más", async () => {
    const { pedidas } = await pintarRevision(CASO_COMPLETO);
    const rutas = pedidas.map((peticion) => peticion.ruta);

    expect(rutas).toContain("/lecturas/CAP-03");
    expect(rutas).toContain("/lecturas/CAP-04");
    expect(rutas).toContain("/lecturas/CAP-14");
    for (const ruta of rutas) {
      expect(ruta).toMatch(/^\/(lecturas\/CAP-(03|04|14)|documentos)$/);
    }
  });

  it("la cabecera dice con qué rol se actúa, con el nombre que da la matriz", async () => {
    const nombre = DETALLE[CASO_COMPLETO]?.["CAP-03"]?.rol_nombre as string;
    const { container } = await pintarRevision(CASO_COMPLETO);
    const cabecera = container.querySelector(".cae-pantalla__cabecera");

    expect(nombre).toBeTruthy();
    expect(texto(cabecera)).toContain(propios.ACTUANDO_COMO);
    expect(texto(cabecera)).toContain(nombre);
    expect(texto(cabecera)).toContain(textos.ORIGEN_SIN_DECLARAR);
  });

  it("los cuatro bloques del recorrido están, y con lo que sirvió el servidor", async () => {
    const identificacion = bloqueDe(CASO_COMPLETO, "CAP-03", "identificacion") as { ficha: string };
    const { container } = await pintarRevision(CASO_COMPLETO);

    expect(container.textContent).toContain(identificacion.ficha);
    expect(container.querySelector(".cae-revision__veredicto")).not.toBeNull();
    expect(container.querySelector(".cae-revision__ahorro")).not.toBeNull();
    expect(container.querySelector(".cae-revision__datos-calculo")).not.toBeNull();
    expect(container.querySelector(".cae-revision__comprobaciones")).not.toBeNull();
    expect(container.querySelector(".cae-revision__historial")).not.toBeNull();
    // Nada que impida: ni conflicto ni carencias, y por eso se puede aprobar.
    expect(container.querySelector(".cae-revision__impide")).toBeNull();
  });
});
