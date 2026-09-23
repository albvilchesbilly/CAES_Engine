/**
 * Lo que la cola pide a `api/` y como queda lo que llega. **Ni una decision de negocio** (`R-UI-11`).
 *
 * Las cuatro lecturas de `T-REV-cola` §2, y el reparto de `T-REV-cola` §3:
 *
 * - `CAP-17` da **la lista y su orden**. Las filas llegan ya ordenadas por el servidor (`ADR-014` §2,
 *   contrato C22) y aqui se leen en el orden en que vienen. Si alguna vez aparece un `sort` en este
 *   fichero, es un defecto: el orden es verificable leyendo la respuesta, y un orden que cada cliente
 *   recalcula no se puede verificar.
 * - `CAP-03` da el **ahorro** de cada fila, que el bloque `cola` no trae a proposito.
 * - `CAP-04` da las carencias con su mensaje, y `CAP-14` el estado de ciclo y el de plataforma.
 *
 * Las tres lecturas por fila van por separado y **cada una falla por su cuenta**: una lectura caida deja
 * sus celdas en `SIN DATO` con el motivo y no tumba ni la fila ni la cola (`T-REV-cola` §7,
 * `CA-COLA-07`). Por eso hay un `Resultado` por bloque y no un objeto que exista o no exista.
 *
 * Ninguna cifra se convierte: `total_exacto_presentable` llega ya legible en espanol y se transporta
 * como cadena. Un `Number` sobre el ahorro seria pasar por coma flotante, que es lo que `CLAUDE.md` §2
 * prohibe en todo lo que lo toca.
 */

import { bloque, type Cliente, type Contexto, type Respuesta } from "@cae/compartido/api";
import type { OrigenDatos } from "@cae/compartido";

import { falloDe, type FalloServidor } from "../fallos";
import { booleano, campo, entero, lista, objeto, texto, textos } from "../json";
import { origenDeclarado } from "../origen";

/** La pantalla, tal y como la declara `engine/capacidades.yaml` (`superficies.workspace.pantallas`). */
export const PANTALLA = "cola_revision";

export const CAPACIDAD_COLA = "CAP-17";
export const CAPACIDAD_ACTUACION = "CAP-03";
export const CAPACIDAD_CARENCIAS = "CAP-04";
export const CAPACIDAD_ESTADOS = "CAP-14";

/** Un motivo de `T-REV-cola` §6, con la prioridad **que puso el servidor** y su detalle. */
export interface MotivoCola {
  readonly motivo: string;
  readonly prioridad: number | null;
  readonly detalle: Readonly<Record<string, unknown>>;
}

/** Una fila de la cola, tal y como la sirve el bloque `cola`. */
export interface FilaCola {
  readonly actuacionId: string | null;
  /** `codigo_identificativo_propio` y, si es nulo, el identificador (`T-REV-cola` §5). */
  readonly codigo: string | null;
  readonly ficha: string | null;
  readonly veredicto: string | null;
  readonly semaforo: string | null;
  readonly motivos: readonly MotivoCola[];
  readonly abiertaEn: string | null;
  readonly ultimoMovimientoEn: string | null;
  readonly estado: EstadosCola;
}

/** El estado de ciclo (nuestro) y el de plataforma (que solo se refleja). Son dos cosas distintas. */
export interface EstadosCola {
  readonly ciclo: string | null;
  readonly plataforma: string | null;
  readonly requerimientoAbierto: string | null;
  readonly literalesDesconocidos: readonly string[];
}

/** El ahorro de una fila. `presentable` se pinta tal cual; `exacto` es la forma canonica. */
export interface CalculoCola {
  readonly presentable: string | null;
  readonly exacto: string | null;
  readonly provisional: boolean | null;
  readonly motivoNoCalculo: string | null;
}

export interface Carencia {
  readonly id: string | null;
  readonly severidad: string | null;
  readonly mensaje: string | null;
}

/** Una lectura que salio bien, o el fallo del servidor tal cual. Nunca "no hay datos". */
export type Resultado<T> =
  | { readonly estado: "LISTO"; readonly valor: T }
  | { readonly estado: "ERROR"; readonly fallo: FalloServidor };

/** Las tres lecturas por actuacion, cada una con su suerte. */
export interface DetalleFila {
  readonly calculo: Resultado<CalculoCola>;
  readonly carencias: Resultado<readonly Carencia[]>;
  readonly estados: Resultado<EstadosCola>;
}

export interface Cola {
  /** `Respuesta.rol`: el rol resuelto **por el servidor**; la pantalla solo lo muestra. */
  readonly rol: string;
  readonly origen: OrigenDatos;
  readonly filas: readonly FilaCola[];
  readonly detalles: Readonly<Record<string, DetalleFila>>;
  readonly avisos: readonly string[];
}

function estadoDe(origen: unknown): EstadosCola {
  const estado = objeto(origen);
  return {
    ciclo: texto(estado?.["estado_ciclo"]),
    plataforma: texto(estado?.["estado_plataforma"]),
    requerimientoAbierto: texto(estado?.["requerimiento_abierto"]),
    literalesDesconocidos: textos(estado?.["literales_desconocidos"]),
  };
}

function motivoDe(origen: unknown): MotivoCola | null {
  const crudo = objeto(origen);
  const identificador = texto(crudo?.["motivo"]);
  if (identificador === null) {
    return null;
  }
  return {
    motivo: identificador,
    prioridad: entero(crudo?.["prioridad"]),
    detalle: objeto(crudo?.["detalle"]) ?? {},
  };
}

/** Una fila del bloque `cola`. Se lee entera; no se descarta ninguna y no se reordena nada. */
export function filaDe(origen: unknown): FilaCola {
  const fila = objeto(origen);
  const actuacionId = texto(campo(fila, "identificacion", "actuacion_id"));
  return {
    actuacionId,
    codigo: texto(campo(fila, "identificacion", "codigo_identificativo_propio")) ?? actuacionId,
    ficha: texto(campo(fila, "identificacion", "ficha")),
    veredicto: texto(campo(fila, "veredicto", "valor")),
    semaforo: texto(campo(fila, "veredicto", "semaforo")),
    motivos: lista(fila?.["motivos"])
      .map((motivo) => motivoDe(motivo))
      .filter((motivo): motivo is MotivoCola => motivo !== null),
    abiertaEn: texto(campo(fila, "antiguedad", "abierta_en")),
    ultimoMovimientoEn: texto(campo(fila, "antiguedad", "ultimo_movimiento_en")),
    estado: estadoDe(fila?.["estado"]),
  };
}

function calculoDe(respuesta: Respuesta): CalculoCola {
  const calculo = objeto(bloque(respuesta, "calculo"));
  return {
    presentable: texto(calculo?.["total_exacto_presentable"]),
    exacto: texto(calculo?.["total_exacto"]),
    provisional: booleano(calculo?.["provisional"]),
    motivoNoCalculo: texto(calculo?.["motivo_no_calculo"]),
  };
}

function carenciasDe(respuesta: Respuesta): readonly Carencia[] {
  return lista(campo(bloque(respuesta, "que_te_falta"), "carencias")).map((cruda) => {
    const carencia = objeto(cruda);
    return {
      id: texto(carencia?.["id"]),
      severidad: texto(carencia?.["severidad"]),
      mensaje: texto(carencia?.["mensaje"]),
    };
  });
}

/** Pide una lectura y devuelve lo que trajo **o el fallo**, que tambien es informacion. */
async function intentar<T>(
  cliente: Cliente,
  capacidad: "CAP-03" | "CAP-04" | "CAP-14",
  contexto: Contexto,
  extraer: (respuesta: Respuesta) => T,
): Promise<Resultado<T>> {
  try {
    return { estado: "LISTO", valor: extraer(await cliente.leer(capacidad, contexto)) };
  } catch (causa) {
    return { estado: "ERROR", fallo: falloDe(capacidad, causa) };
  }
}

async function detalleDe(cliente: Cliente, contexto: Contexto): Promise<DetalleFila> {
  const [calculo, carencias, estados] = await Promise.all([
    intentar(cliente, CAPACIDAD_ACTUACION, contexto, calculoDe),
    intentar(cliente, CAPACIDAD_CARENCIAS, contexto, carenciasDe),
    intentar(cliente, CAPACIDAD_ESTADOS, contexto, (respuesta) =>
      estadoDe(bloque(respuesta, "estados_plataforma")),
    ),
  ]);
  return { calculo, carencias, estados };
}

/**
 * La cola entera: la lista con su orden, y el detalle de cada fila.
 *
 * Si `CAP-17` falla, falla la pantalla —no hay lista que pintar— y el aviso sale con el motivo del
 * servidor. Si falla una lectura de una fila, falla esa celda y nada mas.
 */
export async function cargarCola(cliente: Cliente, tenantId: string): Promise<Cola> {
  const respuesta = await cliente.leer(CAPACIDAD_COLA, { superficie: PANTALLA, tenant_id: tenantId });
  const crudas = lista(bloque(respuesta, "cola"));
  const filas = crudas.map((fila) => filaDe(fila));

  const detalles = await Promise.all(
    filas.map(async (fila) =>
      fila.actuacionId === null
        ? null
        : ([
            fila.actuacionId,
            await detalleDe(cliente, {
              superficie: PANTALLA,
              tenant_id: tenantId,
              actuacion_id: fila.actuacionId,
            }),
          ] as const),
    ),
  );

  return {
    rol: respuesta.rol,
    // `GAP-COLA-03`: hoy ningun bloque lo declara y sale `ORIGEN DE DATOS SIN DECLARAR`.
    origen: origenDeclarado(...crudas.map((fila) => campo(fila, "identificacion"))),
    filas,
    detalles: Object.fromEntries(detalles.filter((par) => par !== null)),
    avisos: respuesta.avisos,
  };
}
