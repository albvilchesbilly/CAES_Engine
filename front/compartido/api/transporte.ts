/**
 * El transporte: lo unico de este paquete que sabe que por debajo hay HTTP.
 *
 * Esta separado del cliente por dos razones. La primera es de pruebas: los tests del cliente ensayan
 * denegaciones, respuestas mal formadas y documentos alterados con un transporte de mentira, sin levantar
 * ningun servidor. La segunda es mas de fondo: **hoy no existe la capa HTTP**. `api/` es un contrato en
 * proceso (`api.leer`, `api.ejecutar`, `api.lecturas.documentos.leer_documento`) y todavia no hay nada que
 * lo publique por red. Lo que hay aqui es la forma del sobre que se espera, escrita en un solo sitio para
 * que el dia que se escriba el servidor se lea de aqui y no se invente otra vez.
 *
 * El sobre:
 *
 * - `POST {base}/lecturas/{capacidad}` · `POST {base}/comandos/{capacidad}` · `POST {base}/documentos`
 * - cuerpo: `{ contexto, datos }`. **Ni el usuario ni el tenant real viajan en el cuerpo**: el principal
 *   sale de la sesion autenticada (`ADR-011` §3, regla 2). El `tenant_id` del contexto es el que declara
 *   la pantalla, y el servidor lo compara con el del principal; si no coinciden, deniega.
 * - respuesta 200: `{ capacidad, rol, eventos, datos, avisos }`
 * - respuesta 403: `{ error: "permiso", motivo, codigo? }`
 * - cualquier otra: `{ error: "api", motivo, codigo? }` (y si ni eso, el cliente lo dice)
 */

/** Lo que el cliente le pide al transporte. `ruta` es relativa a la base; nunca la compone quien llama. */
export interface PeticionTransporte {
  readonly ruta: string;
  readonly cuerpo: unknown;
}

/** Lo que el transporte devuelve: el codigo de estado y el cuerpo ya deserializado. */
export interface RespuestaTransporte {
  readonly estado: number;
  readonly cuerpo: unknown;
}

/** Un transporte es una funcion. Asi el cliente no depende de `fetch` ni de ninguna libreria. */
export type Transporte = (peticion: PeticionTransporte) => Promise<RespuestaTransporte>;

/** La firma de `fetch` que aqui se usa, reducida a lo que de verdad se le pide. */
export type Buscador = (
  entrada: string,
  inicio: { method: string; headers: Record<string, string>; body: string },
) => Promise<{ status: number; text(): Promise<string> }>;

/**
 * El transporte HTTP de verdad, sobre `fetch`.
 *
 * Un cuerpo que no es JSON no se adivina: se devuelve `null` y el cliente dira que la respuesta no cumple
 * el contrato. Preferimos un error claro a una pantalla que interpreta a medias lo que le llega.
 */
export function transporteHttp(base: string, buscador?: Buscador): Transporte {
  const raiz = base.replace(/\/+$/, "");
  return async ({ ruta, cuerpo }: PeticionTransporte): Promise<RespuestaTransporte> => {
    const buscar = buscador ?? (globalThis.fetch as unknown as Buscador | undefined);
    if (buscar === undefined) {
      throw new Error("no hay `fetch` disponible: pasa un transporte al crear el cliente");
    }
    const respuesta = await buscar(`${raiz}${ruta}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(cuerpo),
    });
    const texto = await respuesta.text();
    return { estado: respuesta.status, cuerpo: interpretarJson(texto) };
  };
}

function interpretarJson(texto: string): unknown {
  if (texto.trim() === "") {
    return null;
  }
  try {
    return JSON.parse(texto) as unknown;
  } catch {
    return null;
  }
}
