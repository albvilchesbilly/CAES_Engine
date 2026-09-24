/**
 * El transporte de esta pagina: `transporteHttp` de `@cae/compartido/api` con la cabecera del principal.
 *
 * El sobre no se toca (`ADR-015` §1): lo escribe `front/compartido/api/transporte.ts` y aqui solo se le
 * envuelve el `fetch` para anadir `x-cae-principal-desarrollo`. La cabecera **no se compone aqui**: llega
 * ya validada desde `configuracion.ts`, que es el unico sitio que decide si hay principal o no.
 */

import { transporteHttp, type Buscador, type Transporte } from "@cae/compartido/api";

import { CABECERA_PRINCIPAL } from "./configuracion";

/**
 * Un transporte HTTP que declara el principal en cada peticion.
 *
 * `buscador` se puede inyectar para probar sin red; si no se da, se usa el `fetch` del navegador.
 */
export function transporteConPrincipal(
  base: string,
  cabecera: string,
  buscador?: Buscador,
): Transporte {
  const conPrincipal: Buscador = (entrada, inicio) => {
    const buscar = buscador ?? (globalThis.fetch as unknown as Buscador | undefined);
    if (buscar === undefined) {
      throw new Error("este entorno no tiene `fetch`");
    }
    return buscar(entrada, {
      ...inicio,
      headers: { ...inicio.headers, [CABECERA_PRINCIPAL]: cabecera },
    });
  };
  return transporteHttp(base, conPrincipal);
}
