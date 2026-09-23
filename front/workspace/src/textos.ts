/**
 * Todos los textos del workspace del tenant, en un solo sitio.
 *
 * Estan centralizados por la misma razon de control que en `compartido/` y no por comodidad:
 * `tests/textos.test.ts` recorre este catalogo con **la misma lista de formulas prohibidas** que
 * `front/compartido/tests/textos.test.ts` (`CLAUDE.md` §2, `CA-COLA-10`). Si los textos estuvieran
 * repartidos por los `.tsx`, esa comprobacion seria una busqueda de cadenas por el arbol y dejaria de
 * ser fiable en cuanto alguien compusiera una frase sobre la marcha.
 *
 * Los identificadores van en espanol sin tildes (como en `engine/`); lo que lee una persona, con ellas.
 *
 * **Lo que NO entra aqui**: el descargo, el mensaje de un veredicto, el motivo de un error y el motivo
 * de un no-calculo. Los escribe el servidor (la spec activa o `api/`), se pintan literales y no son
 * texto de producto nuestro (`T-REV-revision.md` §11 bis).
 *
 * La segunda pantalla del workspace anade su seccion al final; no reescribe las de arriba.
 */

// -- Marco de pantalla ------------------------------------------------------------------------

/** La cabecera dice siempre con que rol se esta actuando (`ADR-050`, §"Inferencia del rol"). */
export const ACTUANDO_COMO = "Actuando como";

/** Fallo que no es del contrato: tampoco se calla, aunque no se sepa mas. */
export const ERROR_DESCONOCIDO = "el fallo no trae ningún detalle";

/** Un error del servidor se puede volver a intentar; no se sustituye por "no hay datos". */
export const REINTENTAR = "Reintentar";

// -- Cola de revision (`T-REV-cola`) ----------------------------------------------------------

export const TITULO_COLA = "Cola de revisión";

/** Resumen de la tabla para quien la recorre con lector de pantalla. */
export const LEYENDA_COLA =
  "Actuaciones del tenant que esperan revisión, en el orden de prioridad que fija el servidor.";

export const COLUMNA_ACTUACION = "Actuación";
export const COLUMNA_VEREDICTO = "Veredicto";
export const COLUMNA_MOTIVOS = "Por qué está aquí";
export const COLUMNA_AHORRO = "Ahorro prevalidado";
export const COLUMNA_ANTIGUEDAD = "Esperando desde";
export const COLUMNA_ESTADO = "Estado";
export const COLUMNA_ACCION = "Ir a la revisión";

/** El enlace de la fila. La cola reparte trabajo: lo que se decide se decide con el expediente delante. */
export const IR_A_REVISION = "Revisar";

export const CARGANDO = "Cargando la cola de revisión…";
export const CARGANDO_DESCRIPCION =
  "Hueco de carga: la lectura está en vuelo y todavía no hay ninguna cifra que pintar.";

export const VACIO = "No hay nada esperando revisión.";
export const VACIO_DESCRIPCION =
  "La lectura ha respondido y no trae ninguna actuación. No es un error y no es un cero.";

/** `R-UI-05` anticipado: entrar y descubrir que no se puede tocar nada es descubrirlo tarde. */
export const SOLO_LECTURA = "Solo lectura";
export const SOLO_LECTURA_DESCRIPCION =
  "En la plataforma y sin requerimiento abierto: desde aquí no se cambia nada.";

/** `calculo.provisional`: la cifra existe, pero se apoya en algo declarado y no demostrado. */
export const ESTIMACION_NO_ACREDITADA = "ESTIMACIÓN NO ACREDITADA";

export const ETIQUETA_CICLO = "Ciclo";
export const ETIQUETA_ULTIMO_MOVIMIENTO = "Último movimiento";
export const ETIQUETA_PLATAFORMA = "Plataforma";

/** Antiguedad: la fecha absoluta manda y esto es el texto secundario (`T-REV-cola` §5). */
export const ANTIGUEDAD_HOY = "hoy";
export const ANTIGUEDAD_UN_DIA = "hace 1 día";
export const ANTIGUEDAD_DIAS = "hace N días";

/** Rotulos de los cinco motivos de `T-REV-cola` §6. El identificador lo decide `api/`; esto lo nombra. */
export const MOTIVO_CONFLICTO = "Conflicto";
export const MOTIVO_ESCALADO = "Escalado";
export const MOTIVO_REQUERIMIENTO = "Requerimiento abierto";
export const MOTIVO_CORRECCION = "Corrección pendiente";
export const MOTIVO_TAREA = "Tarea de la plataforma";

/**
 * Una fila que llega sin motivo no se esconde: el servidor promete que no las hay
 * (`T-REV-cola` §6), y el dia que llegue una, se ve que ha llegado.
 */
export const MOTIVO_AUSENTE = "El servidor no ha declarado ningún motivo para esta fila.";

/** Catalogo completo, para la comprobacion de `tests/textos.test.ts`. */
export const TEXTOS = {
  ACTUANDO_COMO,
  ERROR_DESCONOCIDO,
  REINTENTAR,
  TITULO_COLA,
  LEYENDA_COLA,
  COLUMNA_ACTUACION,
  COLUMNA_VEREDICTO,
  COLUMNA_MOTIVOS,
  COLUMNA_AHORRO,
  COLUMNA_ANTIGUEDAD,
  COLUMNA_ESTADO,
  COLUMNA_ACCION,
  IR_A_REVISION,
  CARGANDO,
  CARGANDO_DESCRIPCION,
  VACIO,
  VACIO_DESCRIPCION,
  SOLO_LECTURA,
  SOLO_LECTURA_DESCRIPCION,
  ESTIMACION_NO_ACREDITADA,
  ETIQUETA_CICLO,
  ETIQUETA_ULTIMO_MOVIMIENTO,
  ETIQUETA_PLATAFORMA,
  ANTIGUEDAD_HOY,
  ANTIGUEDAD_UN_DIA,
  ANTIGUEDAD_DIAS,
  MOTIVO_CONFLICTO,
  MOTIVO_ESCALADO,
  MOTIVO_REQUERIMIENTO,
  MOTIVO_CORRECCION,
  MOTIVO_TAREA,
  MOTIVO_AUSENTE,
} as const;
