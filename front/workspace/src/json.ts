/**
 * Lectores defensivos de lo que llega en `Respuesta.datos`.
 *
 * `Datos` es `{ [bloque]?: unknown }` a proposito (`ADR-012` §3, regla 4): un bloque fuera del ambito
 * del rol **no se construye**, asi que su ausencia es normal y significativa. TypeScript no ha visto
 * la respuesta, y estas funciones son la frontera entre "lo que llego" y "lo que la pantalla pinta".
 *
 * Aqui no hay ni una decision de negocio (`R-UI-11`): no se ordena, no se filtra por criterio, no se
 * convierte ninguna cifra y no se rellena nada por defecto. Lo que no se entiende sale `null`, y quien
 * lo reciba decide que ensena en su lugar — que en este workspace es siempre `SIN DATO`, nunca un cero.
 */

/** El objeto, o `null` si lo que llego no lo es. Una lista **no** es un objeto para este uso. */
export function objeto(valor: unknown): Readonly<Record<string, unknown>> | null {
  if (typeof valor !== "object" || valor === null || Array.isArray(valor)) {
    return null;
  }
  return valor as Readonly<Record<string, unknown>>;
}

/** La lista, o una vacia. Nunca se reordena: el orden que llega es el que vale (`R-UI-11`). */
export function lista(valor: unknown): readonly unknown[] {
  return Array.isArray(valor) ? (valor as readonly unknown[]) : [];
}

/** El texto con contenido, o `null`. Una cadena en blanco deja la celda muda y se trata como ausente. */
export function texto(valor: unknown): string | null {
  if (typeof valor !== "string") {
    return null;
  }
  const limpio = valor.trim();
  return limpio === "" ? null : limpio;
}

/** El entero, o `null`. No convierte cadenas: una cifra que llega como texto se pinta como texto. */
export function entero(valor: unknown): number | null {
  return typeof valor === "number" && Number.isInteger(valor) ? valor : null;
}

/** El booleano tal cual, o `null` si no lo es. `provisional` que no llega no es `false`. */
export function booleano(valor: unknown): boolean | null {
  return typeof valor === "boolean" ? valor : null;
}

/** Un campo anidado por su ruta (`campo(datos, "identificacion", "ficha")`), o `undefined`. */
export function campo(origen: unknown, ...ruta: readonly string[]): unknown {
  let actual: unknown = origen;
  for (const paso of ruta) {
    const contenedor = objeto(actual);
    if (contenedor === null) {
      return undefined;
    }
    actual = contenedor[paso];
  }
  return actual;
}

/** La lista de textos de un campo (`literales_desconocidos`, `carencias`), sin los que no lo son. */
export function textos(valor: unknown): readonly string[] {
  return lista(valor)
    .map((elemento) => texto(elemento))
    .filter((elemento): elemento is string => elemento !== null);
}
