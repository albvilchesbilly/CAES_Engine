/**
 * Todos los textos de interfaz de `compartido/`, en un solo sitio.
 *
 * Estan centralizados por una razon de control, no de comodidad: `tests/textos.test.ts` recorre este
 * catalogo y comprueba que no aparece ninguna formula prohibida por `CLAUDE.md` §2. Si los textos
 * estuvieran repartidos por los .tsx, esa comprobacion seria una busqueda de cadenas por el arbol y
 * dejaria de ser fiable en cuanto alguien compusiera un texto sobre la marcha.
 *
 * Los identificadores van en espanol sin tildes (como en `engine/`); los textos que lee una persona
 * van en espanol con las tildes correctas.
 */

/** `R-UI-06`. Acompana a toda cifra prevalidada. No hay prop que lo quite. */
export const ROTULO_AHORRO_PREVALIDADO =
  "Cifra prevalidada por el motor: no son CAE emitidos.";

/** `R-UI-06`. Distintivo de un estado de expediente: nuestros nombres, no los de la plataforma. */
export const MARCA_NO_OFICIAL = "NO OFICIAL";

/** Aclaracion del distintivo anterior (`TODO(API-03)`: la plataforma no ha publicado estos estados). */
export const ROTULO_ESTADO_EXPEDIENTE =
  "Estado provisional propio: la plataforma oficial no ha publicado los estados de expediente.";

/** `R-UI-07`. El literal exacto que ve la persona cuando no hay dato. Nunca un cero, nunca un hueco. */
export const SIN_DATO = "SIN DATO";

/** Prefijo del entregable del que depende una metrica sin fuente (`ADR-007` §Principios, 3). */
export const SIN_DATO_DESDE = "Disponible desde";

/** Lectura alternativa para lector de pantalla: el hueco tiene que sonar distinto de un cero. */
export const SIN_DATO_DESCRIPCION = "Sin dato disponible; no es un valor cero.";

/** `R-UI-08`. Marca de origen de datos de un panel. */
export const ORIGEN_SINTETICO = "DATOS SINTÉTICOS — SOLO PRUEBAS";
export const ORIGEN_REAL = "DATOS REALES";

/**
 * `R-UI-08` cuando el panel no declara su origen. Se muestra, no se calla: un panel sin origen
 * declarado es un panel del que no sabemos si sus cifras son de verdad.
 */
export const ORIGEN_SIN_DECLARAR = "ORIGEN DE DATOS SIN DECLARAR";

/**
 * Lo que se le ensena a una persona cuando el servidor deniega una capacidad (`ADR-012` §3, regla 2).
 *
 * Se ensena, no se traga. Un control que desaparece sin explicacion es un control que nadie arregla; el
 * motivo que manda el servidor ("esta capacidad espera la decision A3") es informacion, y va detras de
 * este texto tal y como llego.
 */
export const ERROR_PERMISO = "El servidor no ha concedido esta acción:";

/** Cualquier otro fallo del servidor. Tampoco se calla: se dice lo que el servidor ha contestado. */
export const ERROR_API = "El servidor no ha podido atender la petición:";

/** El servidor ha contestado algo que no es una respuesta del contrato. No se interpreta a medias. */
export const ERROR_RESPUESTA =
  "La respuesta del servidor no cumple el contrato y no se va a interpretar.";

/** No hubo respuesta: red caída, servidor apagado. Se distingue de una denegación a propósito. */
export const ERROR_TRANSPORTE = "No se ha podido contactar con el servidor.";

/** Catalogo completo, para la comprobacion de `tests/textos.test.ts`. */
export const TEXTOS = {
  ROTULO_AHORRO_PREVALIDADO,
  MARCA_NO_OFICIAL,
  ROTULO_ESTADO_EXPEDIENTE,
  SIN_DATO,
  SIN_DATO_DESDE,
  SIN_DATO_DESCRIPCION,
  ORIGEN_SINTETICO,
  ORIGEN_REAL,
  ORIGEN_SIN_DECLARAR,
  ERROR_PERMISO,
  ERROR_API,
  ERROR_RESPUESTA,
  ERROR_TRANSPORTE,
} as const;
