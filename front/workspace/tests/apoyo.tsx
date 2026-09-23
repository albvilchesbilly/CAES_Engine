/**
 * Apoyo de los tests de `front/workspace/`. **No contiene ningun `test`.**
 *
 * Dos piezas y una decision detras de cada una:
 *
 * 1. **Los datos salen de `api/` de verdad.** `datos/cola.json` y `datos/detalle.json` los genera
 *    `datos/generar.py` llamando a `CAP-17`, `CAP-03`, `CAP-04` y `CAP-14` sobre los siete casos
 *    sinteticos. Un payload escrito a mano prueba la pantalla contra la idea que tenemos del contrato,
 *    que es justo lo que no queremos comprobar.
 * 2. **El transporte se inyecta.** No hay capa HTTP en el repositorio y eso esta decidido (`ADR-014`
 *    §4): `FR1` entrega pantallas verificadas contra el contrato con un transporte de pruebas, no una
 *    aplicacion que se abra en un navegador. Aqui no se levanta ningun servidor ni se toca `fetch`.
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

import { ColaRevision, type PropsColaRevision } from "../src/cola/ColaRevision";

const DIRECTORIO = join(import.meta.dirname, "datos");

function leerJson(nombre: string): unknown {
  return JSON.parse(readFileSync(join(DIRECTORIO, nombre), "utf8")) as unknown;
}

interface RespuestaBruta {
  readonly capacidad: string;
  readonly rol: string;
  readonly eventos: readonly string[];
  readonly datos: Record<string, unknown>;
  readonly avisos: readonly string[];
}

/** La respuesta de `CAP-17` tal cual la sirvio `api/`, con sus filas **ya ordenadas** por el servidor. */
export const COLA = leerJson("cola.json") as RespuestaBruta;

/** `actuacion_id` → (`CAP-03` | `CAP-04` | `CAP-14`) → respuesta, para las tres lecturas de cada fila. */
export const DETALLE = leerJson("detalle.json") as Record<string, Record<string, RespuestaBruta>>;

/** El orden en que el servidor sirvio las filas. Es el que la pantalla tiene que pintar, sin tocarlo. */
export const ORDEN_DEL_SERVIDOR: readonly string[] = (
  COLA.datos["cola"] as readonly { identificacion: { actuacion_id: string } }[]
).map((fila) => fila.identificacion.actuacion_id);

/** La denegacion de `CAP-17` a un perfil que no la tiene, con las palabras exactas del servidor. */
export const DENEGACION = leerJson("denegacion.json") as RespuestaTransporte;

export const TENANT = "T-001";

/** El instante desde el que se leen las antiguedades: el mismo que usa `datos/generar.py`. */
export const AHORA = new Date("2026-09-19T12:00:00Z");

export interface Ajustes {
  /** Cambia las filas que devuelve `CAP-17` (reordenarlas, vaciarlas). El servidor manda; esto lo finge. */
  readonly filas?: (filas: readonly unknown[]) => readonly unknown[];
  /** Respuesta preparada para una capacidad (y, si se quiere, una actuacion). `null` = la de siempre. */
  readonly respuesta?: (
    capacidad: string,
    actuacionId: string | null,
  ) => RespuestaTransporte | null;
}

export interface Servidor {
  readonly transporte: Transporte;
  /** Todo lo que la pantalla pidio, en orden. Sirve para comprobar que **no** pidio de mas. */
  readonly pedidas: PeticionTransporte[];
}

function capacidadDe(ruta: string): string {
  return decodeURIComponent(ruta.slice(ruta.lastIndexOf("/") + 1));
}

function contextoDe(cuerpo: unknown): { actuacion_id?: string | null } {
  const sobre = cuerpo as { contexto?: { actuacion_id?: string | null } };
  return sobre.contexto ?? {};
}

/** Un servidor de pruebas que contesta con lo que `api/` contesto de verdad. */
export function servidorDePruebas(ajustes: Ajustes = {}): Servidor {
  const pedidas: PeticionTransporte[] = [];

  const transporte: Transporte = async (peticion) => {
    pedidas.push(peticion);
    const capacidad = capacidadDe(peticion.ruta);
    const actuacionId = contextoDe(peticion.cuerpo).actuacion_id ?? null;

    const preparada = ajustes.respuesta?.(capacidad, actuacionId) ?? null;
    if (preparada !== null) {
      return preparada;
    }

    if (capacidad === "CAP-17") {
      const filas = COLA.datos["cola"] as readonly unknown[];
      return {
        estado: 200,
        cuerpo: { ...COLA, datos: { cola: ajustes.filas === undefined ? filas : ajustes.filas(filas) } },
      };
    }

    const respuesta = actuacionId === null ? undefined : DETALLE[actuacionId]?.[capacidad];
    if (respuesta === undefined) {
      return {
        estado: 500,
        cuerpo: { error: "api", motivo: `el servidor de pruebas no tiene ${capacidad} de ${actuacionId}` },
      };
    }
    return { estado: 200, cuerpo: respuesta };
  };

  return { transporte, pedidas };
}

export interface Pintada extends RenderResult {
  readonly pedidas: PeticionTransporte[];
}

/** Pinta la cola y espera a que la lectura deje de estar en vuelo (el esqueleto desaparece). */
export async function pintarCola(
  ajustes: Ajustes = {},
  props: Partial<PropsColaRevision> = {},
): Promise<Pintada> {
  const servidor = servidorDePruebas(ajustes);
  const resultado = render(
    <ColaRevision
      cliente={crearCliente(servidor.transporte)}
      tenantId={TENANT}
      ahora={AHORA}
      {...props}
    />,
  );
  await waitFor(() => {
    expect(resultado.container.querySelector('[role="status"]')).toBeNull();
  });
  return { ...resultado, pedidas: servidor.pedidas };
}

/**
 * Pinta la cola y **no espera**: devuelve lo que se ve mientras la lectura sigue en vuelo.
 *
 * Con un transporte que no resuelve nunca, esto es el estado de carga de `T-REV-cola` §7, que tiene que
 * ser distinto del vacio y del error.
 */
export function pintarColaEnVuelo(props: Partial<PropsColaRevision> = {}): RenderResult {
  const transporte: Transporte = () => new Promise<RespuestaTransporte>(() => {});
  return render(
    <ColaRevision cliente={crearCliente(transporte)} tenantId={TENANT} ahora={AHORA} {...props} />,
  );
}

/** Las filas pintadas, en el orden del DOM. Nunca se ordenan aqui: son las que hay, como estan. */
export function filasPintadas(contenedor: HTMLElement): HTMLElement[] {
  return Array.from(contenedor.querySelectorAll<HTMLElement>("tbody tr"));
}

/** El identificador de cada fila pintada, en el orden del DOM. */
export function ordenPintado(contenedor: HTMLElement): (string | null)[] {
  return filasPintadas(contenedor).map((fila) => fila.getAttribute("data-actuacion"));
}

/** La fila de una actuacion concreta. Falla en el sitio si no esta pintada. */
export function fila(contenedor: HTMLElement, actuacionId: string): HTMLElement {
  const encontrada = contenedor.querySelector<HTMLElement>(`tbody tr[data-actuacion="${actuacionId}"]`);
  if (encontrada === null) {
    throw new Error(`la fila ${actuacionId} no esta pintada; hay ${ordenPintado(contenedor).join(", ")}`);
  }
  return encontrada;
}

/** El texto de una celda de la fila, por su clase. */
export function celda(filaPintada: HTMLElement, clase: string): string {
  const encontrada = filaPintada.querySelector<HTMLElement>(`.${clase}`);
  return encontrada?.textContent ?? "";
}

export { screen };
