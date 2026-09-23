import { MarcaOrigen, ValorMetrica, type OrigenDatos } from "@cae/compartido";
import type { ReactElement, ReactNode } from "react";

import { ACTUANDO_COMO } from "./textos";

export interface PropsPantalla {
  readonly titulo: string;
  /**
   * `Respuesta.rol_nombre`: el **nombre** del rol con el que se actua, tal y como lo declara la matriz.
   *
   * No es el codigo del perfil y no se compone de el (`ADR-012` §3, regla 1): llevar aqui una tabla
   * perfil -> nombre seria una segunda copia de `engine/capacidades.yaml`, la misma fuente que decide
   * los permisos, y envejeceria sola. Lo que no llegue, no se pinta.
   */
  readonly rolNombre: string | null;
  readonly origen: OrigenDatos;
  /** `Respuesta.avisos`: lo que el servidor quiso decir ademas de los datos. No se filtra. */
  readonly avisos?: readonly string[] | undefined;
  readonly children: ReactNode;
}

/**
 * El marco de cualquier pantalla del workspace: titulo, rol con el que se actua y marca de origen.
 *
 * Las dos cosas de la cabecera son reglas, no adorno:
 *
 * - **`R-UI-08`**: todo panel declara si mira datos sinteticos o reales. `MarcaOrigen` no tiene valor por
 *   defecto y anuncia `ORIGEN DE DATOS SIN DECLARAR` mientras `api/` no lo diga (`GAP-COLA-03`).
 * - **El rol** sale de `Respuesta.rol_nombre`: lo resuelve el servidor, lo nombra la matriz y la pantalla
 *   lo muestra, nunca lo deduce ni lo compone (`ADR-050`, §"Inferencia del rol"; `ADR-012` §3, regla 1).
 *   Mientras la lectura esta en vuelo **no se pinta `SIN DATO`** en su lugar: un dato que todavia no ha
 *   llegado no es un dato que falta, y `T-REV-cola` §7 separa a proposito el hueco de carga del `SIN
 *   DATO`. Cuando llega la respuesta, el rol aparece; si el servidor deniega, lo que se ensena es su
 *   motivo. Y si la respuesta no trae nombre, no se pinta el codigo del perfil en su lugar.
 *
 * **`R-UI-10` no se pinta aqui, y es deliberado.** El aviso de registro de actividad depende de que
 * exista `O-EQU` (`CAP-36`), que hoy no esta implementado. Avisar de una monitorizacion que no ocurre
 * seria decir algo falso; ademas la revision juridica de esa monitorizacion sigue pendiente antes del
 * primer cliente (`ADR-005`). El dia que `CAP-36` exista, el aviso entra en esta cabecera.
 */
export function Pantalla({ titulo, rolNombre, origen, avisos, children }: PropsPantalla): ReactElement {
  return (
    <section className="cae-pantalla">
      <header className="cae-pantalla__cabecera">
        <h1 className="cae-pantalla__titulo">{titulo}</h1>
        {rolNombre === null ? null : (
          <ValorMetrica etiqueta={ACTUANDO_COMO} metrica={{ estado: "CON_DATO", valor: rolNombre }} />
        )}
        <MarcaOrigen origen={origen} />
      </header>
      {avisos !== undefined && avisos.length > 0 ? (
        <ul className="cae-pantalla__avisos">
          {avisos.map((aviso) => (
            <li key={aviso}>{aviso}</li>
          ))}
        </ul>
      ) : null}
      {children}
    </section>
  );
}
