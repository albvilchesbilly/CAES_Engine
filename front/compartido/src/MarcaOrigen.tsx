import type { ReactElement } from "react";

import { ORIGEN_REAL, ORIGEN_SIN_DECLARAR, ORIGEN_SINTETICO } from "./textos";

/** De donde salen las cifras del panel. No hay tercera opcion ni valor por defecto. */
export type OrigenDatos = "SINTETICO" | "REAL";

export interface PropsMarcaOrigen {
  readonly origen: OrigenDatos;
}

/**
 * `R-UI-08`: todo panel declara si mira datos sinteticos o reales.
 *
 * No tiene valor por defecto a proposito. Un defecto razonable ("sintetico", que es lo que hay hoy)
 * convertiria el olvido en una afirmacion, y el riesgo que esta regla cubre es justo ese: ensenar
 * cifras sinteticas como si fueran reales en una demostracion. Un origen que no se entiende se
 * anuncia como no declarado, en voz alta, en lugar de desaparecer.
 */
export function MarcaOrigen({ origen }: PropsMarcaOrigen): ReactElement {
  if (origen === "SINTETICO" || origen === "REAL") {
    return (
      <span className="cae-marca-origen" data-origen={origen}>
        {origen === "SINTETICO" ? ORIGEN_SINTETICO : ORIGEN_REAL}
      </span>
    );
  }

  return (
    <span className="cae-marca-origen" data-origen="SIN_DECLARAR" role="alert">
      {ORIGEN_SIN_DECLARAR}
    </span>
  );
}
