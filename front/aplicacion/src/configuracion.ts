/**
 * De donde sale el principal de desarrollo, y por que no hay ninguno por defecto.
 *
 * El servidor de desarrollo (`ADR-015` C29) lee quien pide de la cabecera `x-cae-principal-desarrollo`
 * y **no comprueba ninguna credencial**: quien alcance el puerto es quien diga ser. Esa cabecera es
 * exactamente la pieza que, olvidada, regala el sistema, asi que esta pagina la trata igual que el
 * servidor trata su `--desarrollo`: **hay que escribirla a mano**.
 *
 * Por eso aqui no hay ningun `usuario_id`, ningun perfil y ningun tenant escritos. El principal llega
 * por la variable de entorno `VITE_CAE_PRINCIPAL` al arrancar el empaquetador, y si no llega —o llega
 * mal— la pagina **no pide nada** y lo dice en pantalla. Una pagina que se autentica sola contra un
 * servidor que cree lo que le digan es una pagina que no avisa de nada.
 */

/** La variable de la que sale el principal. No tiene valor por defecto, y no lo tiene a proposito. */
export const VARIABLE_PRINCIPAL = "VITE_CAE_PRINCIPAL";

/** La cabecera que lee `api/http/autenticacion.py`. Se llama asi para que nadie la tome por credencial. */
export const CABECERA_PRINCIPAL = "x-cae-principal-desarrollo";

/** Raiz de las rutas del sobre. El empaquetador la reenvia al servidor de desarrollo (`vite.config.ts`). */
export const BASE_API = "/api";

/** Lo que la cabecera declara. Es lo que **dice** la pagina, no lo que el servidor haya comprobado. */
export interface PrincipalDeclarado {
  readonly usuario_id: string;
  readonly perfiles: readonly string[];
  readonly tenant_id: string;
}

export type Configuracion =
  | {
      readonly estado: "LISTA";
      readonly principal: PrincipalDeclarado;
      /** El JSON exacto que viaja en la cabecera. Se compone aqui una vez y no se recompone despues. */
      readonly cabecera: string;
    }
  | { readonly estado: "SIN_PRINCIPAL"; readonly motivo: string };

function falta(motivo: string): Configuracion {
  return { estado: "SIN_PRINCIPAL", motivo };
}

function esObjeto(valor: unknown): valor is Readonly<Record<string, unknown>> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

/**
 * Interpreta el contenido de `VITE_CAE_PRINCIPAL`.
 *
 * Lo que no este completo no se completa: sin `tenant_id` no hay pantalla que abrir, porque el
 * `tenant_id` del contexto lo declara la pantalla y el servidor lo compara con el del principal
 * (`ADR-015` C30). Rellenarlo aqui seria inventarse la mitad de esa comparacion.
 */
export function configuracionDe(crudo: string | undefined): Configuracion {
  if (crudo === undefined || crudo.trim() === "") {
    return falta(
      `no se ha declarado ningún principal: arranca el empaquetador con ${VARIABLE_PRINCIPAL}` +
        '=\'{"usuario_id": …, "perfiles": [ … ], "tenant_id": …}\'. No hay valor por defecto,' +
        " y no lo hay a propósito (`ADR-015` C29).",
    );
  }

  let declarado: unknown;
  try {
    declarado = JSON.parse(crudo) as unknown;
  } catch (fallo) {
    return falta(
      `${VARIABLE_PRINCIPAL} no es JSON válido: ${fallo instanceof Error ? fallo.message : "sin detalle"}`,
    );
  }
  if (!esObjeto(declarado)) {
    return falta(`${VARIABLE_PRINCIPAL} tiene que ser un objeto con usuario_id, perfiles y tenant_id`);
  }

  const usuario = declarado["usuario_id"];
  const perfiles = declarado["perfiles"];
  const tenant = declarado["tenant_id"];
  if (typeof usuario !== "string" || usuario.trim() === "") {
    return falta(`${VARIABLE_PRINCIPAL} no trae un \`usuario_id\``);
  }
  if (!Array.isArray(perfiles) || perfiles.length === 0 || !perfiles.every((p) => typeof p === "string")) {
    return falta(
      `${VARIABLE_PRINCIPAL} tiene que traer \`perfiles\` como lista no vacía de códigos de la matriz`,
    );
  }
  if (typeof tenant !== "string" || tenant.trim() === "") {
    return falta(
      `${VARIABLE_PRINCIPAL} no trae un \`tenant_id\`: sin él no hay pantalla que abrir, porque el` +
        " tenant lo declara la pantalla y el servidor lo compara con el del principal (`ADR-015` C30)",
    );
  }

  const principal: PrincipalDeclarado = {
    usuario_id: usuario,
    perfiles: perfiles as readonly string[],
    tenant_id: tenant,
  };
  const cabecera = JSON.stringify(principal);
  // Una cabecera HTTP no lleva mas que ASCII: si el principal trae algo que no cabe, se dice aqui en
  // vez de dejar que `fetch` lo rechace con un mensaje que no explica nada.
  if (!/^[\t\x20-\x7e]*$/.test(cabecera)) {
    return falta(
      `${VARIABLE_PRINCIPAL} lleva caracteres que no caben en una cabecera HTTP (solo ASCII imprimible)`,
    );
  }
  return { estado: "LISTA", principal, cabecera };
}
