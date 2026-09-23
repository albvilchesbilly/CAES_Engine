/**
 * Contrato C18 (`ADR-012` §3): el cliente entre el front y `api/`.
 *
 * Cuatro reglas, y donde vive cada una:
 *
 * 1. **El cliente no decide permisos.** Aqui no hay ninguna tabla de perfiles ni de capacidades: `leer` y
 *    `ejecutar` mandan la peticion y el servidor concede o niega (`R-UI-01`; ocultar un control no es
 *    autorizar, y el corolario es que el front tampoco autoriza por su cuenta). Hay un test que recorre
 *    este fuente y comprueba que no aparece ningun perfil ni ninguna decision de permiso.
 * 2. **Un `ErrorPermiso` se muestra, no se traga.** La denegacion llega como excepcion tipada con el
 *    motivo del servidor dentro, y `mensaje` ya viene en castellano listo para pintar. Nada de devolver
 *    `null` y dejar la pantalla en blanco.
 * 3. **No reordena ni recalcula** (`R-UI-11`). `datos` se devuelve **tal cual llego**, sin copiar, sin
 *    ordenar y sin convertir: las cifras vienen ya decididas y ya formateadas por el servidor, y
 *    reformatearlas aqui obligaria a pasar por coma flotante.
 * 4. **Tipos derivados del contrato**: `Bloque`, `CapacidadLectura` y `CapacidadComando` salen de
 *    `contrato.generado.ts`, que produce `api/tipos_front.py`. Si `api/` cambia un bloque, esto deja de
 *    compilar donde se usaba.
 *
 * Lo que este modulo **no** hace: no guarda estado, no reintenta, no cachea y no conoce ninguna pantalla.
 */

import { ERROR_API, ERROR_PERMISO, ERROR_RESPUESTA, ERROR_TRANSPORTE } from "../src/textos";
import type { Bloque, CapacidadComando, CapacidadLectura, Datos } from "./contrato.generado";
import type { Transporte } from "./transporte";

/** De donde viene la accion. La pantalla desempata el rol cuando dos perfiles comparten capacidad. */
export interface Contexto {
  readonly superficie: string;
  readonly tenant_id?: string | null;
  readonly actuacion_id?: string | null;
}

/**
 * La respuesta del contrato, igual que en `api/contrato.py`.
 *
 * `rol` es el **codigo** del perfil con el que se ejercio la capacidad (el que se persiste en
 * `actor.rol`) y `rol_nombre` el nombre que de el declara `engine/capacidades.yaml`, que es la misma
 * fuente que decide los permisos. Los dos viajan porque la cabecera escribe "actuando como Revisor
 * tecnico" y componerlo en la pantalla exigiria una tabla perfil -> nombre en la interfaz, que es una
 * segunda copia de esa fuente y envejece sola (`ADR-012` §3, regla 1; `GAP-REV-11`/`GAP-COLA-06`).
 *
 * Es `string | null` y no `string` por una razon concreta: `api/` lo sirve siempre, pero **no hay capa
 * HTTP** (`ADR-014` §4, `GAP-HTTP-01`), asi que lo que hoy llega al cliente lo pone un transporte de
 * pruebas. Un sobre sin el campo no se completa con el codigo del perfil —eso es exactamente lo que la
 * regla prohibe— ni se rellena con una cadena vacia que se pintaria como un nombre: se declara ausente y
 * la pantalla no pinta nada en su lugar.
 */
export interface Respuesta {
  readonly capacidad: string;
  readonly rol: string;
  readonly rol_nombre: string | null;
  readonly eventos: readonly string[];
  readonly datos: Datos;
  readonly avisos: readonly string[];
}

/**
 * El documento servido por `CAP-03` (`ADR-012` §2), ya fuera del sobre base64.
 *
 * `contenido` son los bytes **tal y como entraron en ingesta**: el servidor no recorta, no rota y no
 * resalta. Resaltar la cita es cosa del navegador, y por eso llega el fichero entero.
 */
export interface DocumentoServido {
  readonly doc_id: string;
  readonly tipo: string | null;
  readonly medio: string;
  readonly bytes: number;
  readonly paginas: number;
  /** Huella del PDF combinado del que salio esta parte, o `null`. Si no es `null`, `contenido` es el suyo. */
  readonly origen: string | null;
  /** Paginas del original que forman la parte, en numeracion absoluta del original. */
  readonly rango_paginas: readonly [number, number] | null;
  readonly contenido: Uint8Array;
}

/** Denegacion del servidor. Se muestra siempre: es informacion, no un detalle interno. */
export class ErrorPermiso extends Error {
  readonly capacidad: string;
  readonly motivo: string;
  readonly codigo: string | null;
  readonly mensaje: string;

  constructor(capacidad: string, motivo: string, codigo: string | null) {
    super(`${capacidad}: ${motivo}`);
    this.name = "ErrorPermiso";
    this.capacidad = capacidad;
    this.motivo = motivo;
    this.codigo = codigo;
    this.mensaje = `${ERROR_PERMISO} ${motivo}`;
  }
}

/** Cualquier otro fallo: peticion mal formada, respuesta fuera de contrato, red caida, documento alterado. */
export class ErrorApi extends Error {
  readonly capacidad: string;
  readonly motivo: string;
  readonly codigo: string | null;
  readonly estado: number | null;
  readonly mensaje: string;

  constructor(
    capacidad: string,
    motivo: string,
    { codigo = null, estado = null, prefijo = ERROR_API }: OpcionesErrorApi = {},
  ) {
    super(`${capacidad}: ${motivo}`);
    this.name = "ErrorApi";
    this.capacidad = capacidad;
    this.motivo = motivo;
    this.codigo = codigo;
    this.estado = estado;
    this.mensaje = prefijo === "" ? motivo : `${prefijo} ${motivo}`;
  }
}

interface OpcionesErrorApi {
  readonly codigo?: string | null;
  readonly estado?: number | null;
  readonly prefijo?: string;
}

/** Lo que el front usa. Tres operaciones y ninguna mas. */
export interface Cliente {
  leer(
    capacidad: CapacidadLectura,
    contexto: Contexto,
    datos?: Readonly<Record<string, unknown>>,
  ): Promise<Respuesta>;
  ejecutar(
    capacidad: CapacidadComando,
    contexto: Contexto,
    datos: Readonly<Record<string, unknown>>,
  ): Promise<Respuesta>;
  leerDocumento(
    capacidad: CapacidadLectura,
    contexto: Contexto,
    docId: string,
  ): Promise<DocumentoServido>;
}

const ESTADO_PERMISO = 403;

/** El cliente. Se le da un transporte; no se busca uno global. */
export function crearCliente(transporte: Transporte): Cliente {
  async function pedir(
    ruta: string,
    capacidad: string,
    contexto: Contexto,
    datos: Readonly<Record<string, unknown>>,
  ): Promise<Respuesta> {
    let bruta;
    try {
      bruta = await transporte({ ruta, cuerpo: { contexto, datos } });
    } catch (fallo) {
      // Ni se traga ni se disfraza de denegacion: no poder preguntar no es que te digan que no.
      throw new ErrorApi(capacidad, motivoDe(fallo), { prefijo: ERROR_TRANSPORTE });
    }
    return interpretar(capacidad, bruta.estado, bruta.cuerpo);
  }

  return {
    leer: (capacidad, contexto, datos = {}) =>
      pedir(`/lecturas/${encodeURIComponent(capacidad)}`, capacidad, contexto, datos),

    ejecutar: (capacidad, contexto, datos) =>
      pedir(`/comandos/${encodeURIComponent(capacidad)}`, capacidad, contexto, datos),

    leerDocumento: async (capacidad, contexto, docId) => {
      const respuesta = await pedir("/documentos", capacidad, contexto, { doc_id: docId });
      return documentoDe(capacidad, respuesta);
    },
  };
}

/**
 * Del cuerpo que llega a una `Respuesta`, o a una excepcion. Nunca a medias.
 *
 * Lo que no cumple el contrato no se completa con valores por defecto: una respuesta a la que le falta
 * `rol` no es una respuesta con el rol vacio, es un servidor que no esta hablando nuestro idioma.
 */
function interpretar(capacidad: string, estado: number, cuerpo: unknown): Respuesta {
  const sobre = esObjeto(cuerpo) ? cuerpo : {};

  if (sobre["error"] === "permiso" || estado === ESTADO_PERMISO) {
    throw new ErrorPermiso(capacidad, motivoDelSobre(sobre, estado), textoONulo(sobre["codigo"]));
  }
  if (estado !== 200 || sobre["error"] !== undefined) {
    throw new ErrorApi(capacidad, motivoDelSobre(sobre, estado), {
      codigo: textoONulo(sobre["codigo"]),
      estado,
    });
  }

  const datos = sobre["datos"];
  if (
    typeof sobre["capacidad"] !== "string" ||
    typeof sobre["rol"] !== "string" ||
    !esListaDeTextos(sobre["eventos"]) ||
    !esListaDeTextos(sobre["avisos"]) ||
    !esObjeto(datos)
  ) {
    throw new ErrorApi(capacidad, ERROR_RESPUESTA, { estado, prefijo: "" });
  }

  return {
    capacidad: sobre["capacidad"],
    rol: sobre["rol"],
    // Ausente = ausente (ver `Respuesta`): ni se compone del codigo del perfil ni se da por vacio.
    rol_nombre: textoONulo(sobre["rol_nombre"]),
    eventos: sobre["eventos"],
    avisos: sobre["avisos"],
    // Tal cual llego, sin copiar ni ordenar: `R-UI-11`. Lo que el servidor decidio, decidido esta.
    datos: datos as Datos,
  };
}

/**
 * Un bloque de la respuesta, o `undefined` si el ambito del rol no lo trajo.
 *
 * Es la unica forma correcta de mirar `datos`: `R-UI-12` dice que un bloque fuera de ambito **no se
 * construye**, asi que su ausencia es normal y significativa. Quien la lea tiene que decidir que ensena
 * en su lugar; lo que no puede es inventarse el contenido. El parametro es del tipo generado, asi que un
 * bloque que `api/` deje de construir deja de compilar aqui.
 */
export function bloque(respuesta: Respuesta, nombre: Bloque): unknown {
  return (respuesta.datos as Readonly<Record<string, unknown>>)[nombre];
}

/** El documento de una respuesta de `leerDocumento`, con los bytes ya fuera del base64. */
function documentoDe(capacidad: string, respuesta: Respuesta): DocumentoServido {
  const sobre = (respuesta.datos as Readonly<Record<string, unknown>>)["documento"];
  if (!esObjeto(sobre)) {
    throw new ErrorApi(capacidad, ERROR_RESPUESTA, { prefijo: "" });
  }
  const contenido = decodificar(capacidad, sobre["contenido_base64"]);
  const bytes = sobre["bytes"];
  if (typeof bytes === "number" && bytes !== contenido.length) {
    // Lo que llega y lo que dice que llega no cuadran: el fichero viene incompleto. No se ensena a medias.
    throw new ErrorApi(
      capacidad,
      `el documento dice tener ${bytes} bytes y han llegado ${contenido.length}`,
    );
  }
  return {
    doc_id: textoOVacio(sobre["doc_id"]),
    tipo: textoONulo(sobre["tipo"]),
    medio: textoOVacio(sobre["medio"]),
    bytes: contenido.length,
    paginas: typeof sobre["paginas"] === "number" ? sobre["paginas"] : 0,
    origen: textoONulo(sobre["origen"]),
    rango_paginas: rangoDe(sobre["rango_paginas"]),
    contenido,
  };
}

function decodificar(capacidad: string, valor: unknown): Uint8Array {
  if (typeof valor !== "string") {
    throw new ErrorApi(capacidad, ERROR_RESPUESTA, { prefijo: "" });
  }
  const decodificador = globalThis.atob;
  if (typeof decodificador !== "function") {
    throw new ErrorApi(capacidad, "este entorno no sabe decodificar base64 (`atob`)");
  }
  let binario: string;
  try {
    binario = decodificador(valor);
  } catch {
    throw new ErrorApi(capacidad, "el contenido del documento no es base64 valido");
  }
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i += 1) {
    bytes[i] = binario.charCodeAt(i);
  }
  return bytes;
}

function rangoDe(valor: unknown): readonly [number, number] | null {
  if (!Array.isArray(valor) || valor.length !== 2) {
    return null;
  }
  const [inicio, fin] = valor as readonly unknown[];
  return typeof inicio === "number" && typeof fin === "number" ? [inicio, fin] : null;
}

function motivoDelSobre(sobre: Readonly<Record<string, unknown>>, estado: number): string {
  const motivo = sobre["motivo"];
  if (typeof motivo === "string" && motivo.trim() !== "") {
    return motivo;
  }
  // Un error sin motivo es exactamente lo que la regla 2 prohibe. Se dice que el servidor no lo dio.
  return `el servidor ha respondido ${estado} sin decir por qué`;
}

function motivoDe(fallo: unknown): string {
  return fallo instanceof Error && fallo.message.trim() !== "" ? fallo.message : "sin detalle";
}

function esObjeto(valor: unknown): valor is Readonly<Record<string, unknown>> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function esListaDeTextos(valor: unknown): valor is readonly string[] {
  return Array.isArray(valor) && valor.every((elemento) => typeof elemento === "string");
}

function textoONulo(valor: unknown): string | null {
  return typeof valor === "string" ? valor : null;
}

function textoOVacio(valor: unknown): string {
  return typeof valor === "string" ? valor : "";
}
