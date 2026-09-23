/**
 * Apoyo de los tests de la vista de revision. **No contiene ningun `test`.**
 *
 * Mismas dos decisiones que `apoyo.tsx`, y por las mismas razones:
 *
 * 1. **Todo lo que contesta este servidor lo contesto `api/` de verdad.** `datos/generar.py` carga los
 *    siete casos sinteticos, pide las tres lecturas, sirve los documentos por su huella, **ejecuta la
 *    correccion del caso C** y guarda tambien las tres negativas (sin justificacion, con coma flotante,
 *    de otro tenant) y el documento alterado. Aqui no se escribe ni un payload: se reparte lo que el
 *    servidor dijo.
 * 2. **El transporte se inyecta** (`ADR-014` §4): no hay capa HTTP, no se levanta ningun servidor y no
 *    se toca `fetch`.
 *
 * Lo unico que este doble anade por su cuenta es **memoria**: recuerda si ya se ejecuto la correccion,
 * para servir despues las lecturas de despues. Es lo que hace el lazo observable desde la pantalla.
 */

import { render, screen, waitFor, type RenderResult } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  crearCliente,
  type PeticionTransporte,
  type RespuestaTransporte,
  type Transporte,
} from "@cae/compartido/api";

import { VistaRevision, type PropsVistaRevision } from "../src/revision/VistaRevision";

const DIRECTORIO = join(import.meta.dirname, "datos");

function leerJson(nombre: string): unknown {
  return JSON.parse(readFileSync(join(DIRECTORIO, nombre), "utf8")) as unknown;
}

export interface RespuestaBruta {
  readonly capacidad: string;
  readonly rol: string;
  readonly rol_nombre: string;
  readonly eventos: readonly string[];
  readonly datos: Record<string, unknown>;
  readonly avisos: readonly string[];
}

type PorCapacidad = Record<string, RespuestaBruta>;

/** `actuacion_id` → (`CAP-03` | `CAP-04` | `CAP-14`) → respuesta, antes de tocar nada. */
export const DETALLE = leerJson("detalle.json") as Record<string, PorCapacidad>;

/** `actuacion_id` → `doc_id` → el documento servido por `leer_documento`, con sus bytes en base64. */
export const DOCUMENTOS = leerJson("documentos.json") as Record<
  string,
  Record<string, RespuestaBruta>
>;

/** El lazo del caso C: lo que se envio, lo que contesto `CAP-05` y las tres lecturas **de despues**. */
export const CORRECCION = leerJson("correccion.json") as {
  readonly actuacion_id: string;
  readonly datos_enviados: Record<string, string>;
  readonly respuesta: RespuestaBruta;
  readonly despues: PorCapacidad;
};

/** El caso G con un requerimiento oficial abierto, sellado por `engine.requerimientos`. */
export const REQUERIMIENTO = leerJson("requerimiento.json") as {
  readonly actuacion_id: string;
  readonly eventos: readonly string[];
  readonly lecturas: PorCapacidad;
};

/** Las cuatro negativas del servidor, con sus palabras exactas. */
export const RECHAZOS = leerJson("rechazos.json") as Record<
  string,
  { readonly estado: number; readonly cuerpo: unknown; readonly doc_id?: string }
>;

/** Lo que `generar.py` dejo fuera del fichero de pruebas, y con que limite. */
export const RECORTES = leerJson("recortes.json") as {
  readonly evidencia_maxima_bytes: number;
  readonly documento_maximo_bytes: number;
  readonly evidencias_omitidas: Record<string, readonly string[]>;
  readonly documentos_omitidos: readonly string[];
};

export const TENANT = "T-001";

/** Los casos, por lo que cada uno demuestra. No se nombran en el codigo de la pantalla (`CA-COLA-11`). */
export const CASO_COMPLETO = "A";
export const CASO_CARENCIAS = "B";
export const CASO_CONFLICTO = "C";
export const CASO_FUERA_DE_AMBITO = "D";
export const CASO_EN_PLATAFORMA = "G";

export interface Ajustes {
  /** Sustituye la respuesta de una capacidad. Devolver `null` deja la de siempre. */
  readonly respuesta?: (capacidad: string, cuerpo: unknown) => RespuestaTransporte | null;
  /** Sirve las lecturas del caso G con requerimiento abierto en lugar de las suyas. */
  readonly conRequerimiento?: boolean;
  /** Sirve la respuesta de `CAP-05` con el recalculo marcado como no hecho (`CA-REV-09`). */
  readonly sinRecalculo?: boolean;
}

export interface Servidor {
  readonly transporte: Transporte;
  /** Todo lo que la pantalla pidio, en orden. Sirve para comprobar que **no** pidio de mas. */
  readonly pedidas: PeticionTransporte[];
}

function capacidadDe(ruta: string): string {
  return decodeURIComponent(ruta.slice(ruta.lastIndexOf("/") + 1));
}

function cuerpoDe(peticion: PeticionTransporte): {
  contexto: { actuacion_id?: string | null };
  datos: Record<string, unknown>;
} {
  const sobre = peticion.cuerpo as {
    contexto?: { actuacion_id?: string | null };
    datos?: Record<string, unknown>;
  };
  return { contexto: sobre.contexto ?? {}, datos: sobre.datos ?? {} };
}

function error(motivo: string): RespuestaTransporte {
  return { estado: 500, cuerpo: { error: "api", motivo } };
}

/**
 * Un servidor de pruebas que contesta con lo que `api/` contesto de verdad.
 *
 * La correccion se comporta como el servidor: sin `justificacion` o con un `float`, devuelve **su**
 * negativa —la que `api.contrato` levanta de verdad— y no escribe nada; con la correccion buena,
 * devuelve la salida de `CAP-05` y a partir de ahi las lecturas son las de despues.
 */
export function servidorDeRevision(caso: string, ajustes: Ajustes = {}): Servidor {
  const pedidas: PeticionTransporte[] = [];
  let corregida = false;

  const transporte: Transporte = async (peticion) => {
    pedidas.push(peticion);
    const capacidad = capacidadDe(peticion.ruta);
    const { datos } = cuerpoDe(peticion);

    const preparada = ajustes.respuesta?.(capacidad, peticion.cuerpo) ?? null;
    if (preparada !== null) {
      return preparada;
    }

    if (peticion.ruta.startsWith("/comandos/")) {
      if (capacidad !== "CAP-05") {
        return error(`el servidor de pruebas no atiende el comando ${capacidad}`);
      }
      const justificacion = datos["justificacion"];
      if (typeof justificacion !== "string" || justificacion.trim() === "") {
        return RECHAZOS["sin_justificacion"] as RespuestaTransporte;
      }
      if (typeof datos["valor"] === "number") {
        return RECHAZOS["coma_flotante"] as RespuestaTransporte;
      }
      corregida = true;
      const respuesta = CORRECCION.respuesta;
      return {
        estado: 200,
        cuerpo: ajustes.sinRecalculo
          ? // La otra mitad de `CA-REV-09`: el servidor sella la correccion y avisa de que el motor no
            // pudo recalcular (`ADR-014` C24). El aviso es el que escribe `api/` en ese caso.
            {
              ...respuesta,
              datos: { ...respuesta.datos, recalculada: false },
              avisos: [
                "correccion registrada y pendiente de recalculo: el motor no ha podido reprocesar 'C'",
              ],
            }
          : respuesta,
      };
    }

    if (peticion.ruta === "/documentos") {
      const docId = String(datos["doc_id"] ?? "");
      const servido = DOCUMENTOS[caso]?.[docId];
      if (servido === undefined) {
        return error(
          `el servidor de pruebas no tiene el documento ${docId} de ${caso} (ver recortes.json)`,
        );
      }
      return { estado: 200, cuerpo: servido };
    }

    const fuente =
      corregida && caso === CASO_CONFLICTO
        ? CORRECCION.despues
        : ajustes.conRequerimiento && caso === CASO_EN_PLATAFORMA
          ? REQUERIMIENTO.lecturas
          : DETALLE[caso];
    const respuesta = fuente?.[capacidad];
    if (respuesta === undefined) {
      return error(`el servidor de pruebas no tiene ${capacidad} de ${caso}`);
    }
    return { estado: 200, cuerpo: respuesta };
  };

  return { transporte, pedidas };
}

export interface Pintada extends RenderResult {
  readonly pedidas: PeticionTransporte[];
}

/** Pinta la revision de un caso y espera a que las lecturas dejen de estar en vuelo. */
export async function pintarRevision(
  caso: string,
  ajustes: Ajustes = {},
  props: Partial<PropsVistaRevision> = {},
): Promise<Pintada> {
  const servidor = servidorDeRevision(caso, ajustes);
  const resultado = render(
    <VistaRevision
      cliente={crearCliente(servidor.transporte)}
      tenantId={TENANT}
      actuacionId={caso}
      {...props}
    />,
  );
  // La pantalla esta lista cuando hay revision **o** cuando el servidor ha dicho que no: las dos cosas
  // son un final, y esperar solo la primera dejaria los tests de error colgados hasta el tiempo limite.
  await waitFor(() => {
    const pintada =
      resultado.container.querySelector(".cae-revision") ??
      resultado.container.querySelector(".cae-aviso-servidor");
    expect(pintada).not.toBeNull();
  });
  return { ...resultado, pedidas: servidor.pedidas };
}

/** Pinta y **no espera**: lo que se ve mientras las lecturas siguen en vuelo. */
export function pintarRevisionEnVuelo(caso: string = CASO_COMPLETO): RenderResult {
  const transporte: Transporte = () => new Promise<RespuestaTransporte>(() => {});
  return render(
    <VistaRevision cliente={crearCliente(transporte)} tenantId={TENANT} actuacionId={caso} />,
  );
}

/** El bloque `datos` de una lectura del fichero de pruebas. Falla en el sitio si no esta. */
export function bloqueDe(caso: string, capacidad: string, nombre: string): unknown {
  const respuesta = DETALLE[caso]?.[capacidad];
  if (respuesta === undefined) {
    throw new Error(`no hay ${capacidad} de ${caso} en los datos de prueba`);
  }
  return respuesta.datos[nombre];
}

/** Todos los botones pintados, que es donde se mira si algo se puede hacer o no. */
export function botones(contenedor: HTMLElement): HTMLButtonElement[] {
  return Array.from(contenedor.querySelectorAll<HTMLButtonElement>("button"));
}

/** El bloque de una accion por su capacidad (`data-capacidad`). */
export function accion(contenedor: HTMLElement, capacidad: string): HTMLElement | null {
  return contenedor.querySelector<HTMLElement>(`[data-capacidad="${capacidad}"]`);
}

/** El boton de una accion por su capacidad. */
export function botonDe(contenedor: HTMLElement, capacidad: string): HTMLButtonElement {
  const boton = accion(contenedor, capacidad)?.querySelector("button") ?? null;
  if (boton === null) {
    throw new Error(`no hay control para ${capacidad}`);
  }
  return boton as HTMLButtonElement;
}

export { screen, waitFor };
