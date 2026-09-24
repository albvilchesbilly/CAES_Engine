/**
 * El enrutado, que ya estaba insinuado: `FilaCola` enlaza a `#/revision/<actuacion_id>`.
 *
 * Por hash y no por `history`: un servidor de desarrollo que sirve una sola pagina no tiene que saber
 * de rutas, y asi el enlace de la cola —que la pantalla ya componia sola— sigue siendo un `<a href>` de
 * verdad, navegable y copiable, en vez de un control que intercepta el clic.
 *
 * Aqui no se decide nada de negocio (`R-UI-11`): se lee el hash y se dice que pantalla toca.
 */

import { useEffect, useState } from "react";

export type Ruta =
  | { readonly vista: "COLA" }
  | { readonly vista: "REVISION"; readonly actuacionId: string };

const COLA: Ruta = { vista: "COLA" };

/** El prefijo que compone `ColaRevision` cuando nadie le pasa `enlaceRevision`. */
const PREFIJO_REVISION = "#/revision/";

/** La ruta que describe un hash. Lo que no se reconozca es la cola: no se inventa una pantalla. */
export function rutaDe(hash: string): Ruta {
  if (!hash.startsWith(PREFIJO_REVISION)) {
    return COLA;
  }
  const crudo = hash.slice(PREFIJO_REVISION.length);
  if (crudo === "") {
    return COLA;
  }
  let actuacionId: string;
  try {
    actuacionId = decodeURIComponent(crudo);
  } catch {
    // Un hash mal escrito a mano en la barra de direcciones no es una actuacion: se vuelve a la cola.
    return COLA;
  }
  return actuacionId === "" ? COLA : { vista: "REVISION", actuacionId };
}

/** La ruta actual, al dia con la barra de direcciones y con el boton de atras del navegador. */
export function useRuta(): Ruta {
  const [ruta, setRuta] = useState<Ruta>(() => rutaDe(globalThis.location?.hash ?? ""));
  useEffect(() => {
    const alCambiar = (): void => {
      setRuta(rutaDe(globalThis.location?.hash ?? ""));
    };
    alCambiar();
    globalThis.addEventListener("hashchange", alCambiar);
    return () => {
      globalThis.removeEventListener("hashchange", alCambiar);
    };
  }, []);
  return ruta;
}
