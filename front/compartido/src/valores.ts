/**
 * El tipo de dato que viaja a los rotulos y la unica funcion que decide como se presenta.
 *
 * Aqui no hay logica de negocio (`R-UI-11`): no se suma, no se compara contra un umbral, no se
 * redondea y no se decide si un dato existe. Quien decide que una metrica no tiene fuente es
 * `metricas/` y lo dice en el `estado` que llega (`ADR-007` §Principios, 3). Lo que hay aqui es una
 * barrera de presentacion: pase lo que pase, un dato ausente no puede salir por pantalla como un cero.
 */

/** Lo que `api/` envia: o hay dato, o no lo hay y se sabe desde que entregable lo habra. */
export type MetricaPresentable =
  | {
      readonly estado: "CON_DATO";
      /**
       * Ya formateado por el servidor. Un `Decimal` llega como cadena ("305.829,6") y se pinta tal
       * cual: reformatear aqui obligaria a pasar por `float` y eso esta prohibido en todo lo que
       * toca el ahorro (`CLAUDE.md` §2).
       */
      readonly valor: string | number;
      readonly unidad?: string | undefined;
    }
  | {
      readonly estado: "SIN_DATO";
      /** Entregable del que depende la fuente, p. ej. "S3.5". */
      readonly desde?: string | undefined;
    };

/** Lo que el componente va a pintar. Solo dos formas posibles: un texto, o el hueco declarado. */
export type Presentacion =
  | { readonly clase: "CON_DATO"; readonly texto: string }
  | { readonly clase: "SIN_DATO"; readonly desde: string | null };

const SIN_DATO_SIN_ORIGEN: Presentacion = { clase: "SIN_DATO", desde: null };

/**
 * Traduce lo que llega a lo que se pinta.
 *
 * La regla dura (`R-UI-07`): cualquier valor que no sea un texto presentable se degrada a `SIN_DATO`.
 * Nunca a cero y nunca a un hueco en blanco, porque un hueco en blanco en una tabla de cifras se lee
 * como un cero. Un cero de verdad (`0`, `"0"`, `"0,00"`) sale como cero: es un dato.
 */
export function resolverPresentacion(metrica: MetricaPresentable): Presentacion {
  // Defensivo a proposito: `metrica` viene de una respuesta HTTP y TypeScript no la ha visto.
  if (metrica === null || typeof metrica !== "object") {
    return SIN_DATO_SIN_ORIGEN;
  }

  if (metrica.estado === "SIN_DATO") {
    return { clase: "SIN_DATO", desde: textoNoVacio(metrica.desde) };
  }

  // Un `estado` desconocido no se interpreta: un payload que no entendemos no autoriza a pintar cifras.
  if (metrica.estado !== "CON_DATO") {
    return SIN_DATO_SIN_ORIGEN;
  }

  const texto = textoDelValor(metrica.valor);
  if (texto === null) {
    return SIN_DATO_SIN_ORIGEN;
  }

  const unidad = textoNoVacio(metrica.unidad);
  return { clase: "CON_DATO", texto: unidad === null ? texto : `${texto} ${unidad}` };
}

/** `null` cuando el valor no se puede ensenar tal cual; el texto exacto cuando si. */
function textoDelValor(valor: unknown): string | null {
  if (typeof valor === "number") {
    // `NaN` e `Infinity` son sintomas de un calculo roto aguas arriba. Pintarlos seria ruido;
    // pintar un cero en su lugar seria mentir. Se declaran ausentes.
    return Number.isFinite(valor) ? String(valor) : null;
  }
  if (typeof valor === "string") {
    // Una cadena vacia o en blanco deja la celda muda y una celda muda se lee como un cero.
    return textoNoVacio(valor);
  }
  // `null`, `undefined`, booleanos, objetos: no son cifras y no se inventan.
  return null;
}

function textoNoVacio(valor: unknown): string | null {
  if (typeof valor !== "string") {
    return null;
  }
  const limpio = valor.trim();
  return limpio === "" ? null : limpio;
}
