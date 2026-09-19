import type { ReactElement } from "react";

import { SIN_DATO, SIN_DATO_DESCRIPCION, SIN_DATO_DESDE } from "./textos";
import { resolverPresentacion, type MetricaPresentable } from "./valores";

export interface PropsValorMetrica {
  /** Nombre de la metrica tal y como la persona la reconoce ("Ahorro prevalidado"). */
  readonly etiqueta: string;
  /** Lo que respondio el servidor. El componente no decide si hay dato: lo presenta. */
  readonly metrica: MetricaPresentable;
}

/**
 * `R-UI-07`: un dato ausente se ve `SIN DATO` y un cero se ve `0`. Nunca al reves y nunca iguales.
 *
 * La diferencia no se confia al color: cambia el texto (`SIN DATO`), cambia el elemento y cambia
 * `data-estado`, que es lo que miran los tests y lo que puede mirar cualquier pantalla que reutilice
 * este componente.
 */
export function ValorMetrica({ etiqueta, metrica }: PropsValorMetrica): ReactElement {
  const presentacion = resolverPresentacion(metrica);

  return (
    <span className="cae-valor-metrica">
      <span className="cae-valor-metrica__etiqueta">{etiqueta}</span>
      {presentacion.clase === "CON_DATO" ? (
        <span className="cae-valor-metrica__valor" data-estado="CON_DATO">
          {presentacion.texto}
        </span>
      ) : (
        <span
          className="cae-valor-metrica__sin-dato"
          data-estado="SIN_DATO"
          title={SIN_DATO_DESCRIPCION}
        >
          {SIN_DATO}
          {presentacion.desde === null ? null : (
            <span className="cae-valor-metrica__desde">
              {`${SIN_DATO_DESDE} ${presentacion.desde}`}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
