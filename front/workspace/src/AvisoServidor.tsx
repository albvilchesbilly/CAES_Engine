import type { ReactElement } from "react";

import type { FalloServidor } from "./fallos";
import { REINTENTAR } from "./textos";

export interface PropsAvisoServidor {
  readonly fallo: FalloServidor;
  /** Solo se ofrece cuando reintentar tiene sentido; una denegacion no se reintenta. */
  readonly onReintentar?: (() => void) | undefined;
}

/**
 * Lo que dijo el servidor, **literal**, con la capacidad que se estaba pidiendo.
 *
 * `ADR-012` §3, regla 2, y `R-UI-01`: un error se muestra, no se traga y **no se sustituye por "no hay
 * datos"**. Las dos cosas que este componente nunca hace son resumir el motivo y esconder la fila que lo
 * provoco: ocultar un control no es autorizacion, y un control que desaparece sin explicacion es un
 * control que nadie arregla.
 *
 * El boton de reintentar solo sale para un fallo de la API. Reintentar una denegacion no cambia nada en
 * el servidor y daria a entender que insistir sirve de algo.
 */
export function AvisoServidor({ fallo, onReintentar }: PropsAvisoServidor): ReactElement {
  return (
    <div className="cae-aviso-servidor" data-clase={fallo.clase} role="alert">
      <p className="cae-aviso-servidor__capacidad">{fallo.capacidad}</p>
      <p className="cae-aviso-servidor__mensaje">{fallo.mensaje}</p>
      {fallo.clase === "API" && onReintentar !== undefined ? (
        <button type="button" className="cae-aviso-servidor__reintentar" onClick={onReintentar}>
          {REINTENTAR}
        </button>
      ) : null}
    </div>
  );
}
