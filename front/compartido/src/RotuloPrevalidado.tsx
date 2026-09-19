import type { ReactElement, ReactNode } from "react";

import {
  MARCA_NO_OFICIAL,
  ROTULO_AHORRO_PREVALIDADO,
  ROTULO_ESTADO_EXPEDIENTE,
} from "./textos";

/** Las dos cosas que nunca pueden salir "a pelo" (`ADR-007` §Principios, 7). */
export type TipoRotulo = "AHORRO_PREVALIDADO" | "ESTADO_EXPEDIENTE";

export interface PropsRotuloPrevalidado {
  readonly tipo: TipoRotulo;
  /** La cifra o el estado que se rotula. Llega ya resuelto: aqui no se calcula nada. */
  readonly children: ReactNode;
}

/**
 * `R-UI-06`: envuelve una cifra prevalidada o un estado de expediente y le pega su aviso.
 *
 * No hay prop para quitar el aviso, y no la habra: el dia que haya una, la interfaz podra presentar
 * un kWh prevalidado como si ya fuera un certificado en mano, que es lo que esta regla impide.
 * Un estado de expediente sale ademas marcado `NO OFICIAL` porque los nombres son nuestros: la
 * plataforma no los ha publicado (`TODO(API-03)`).
 */
export function RotuloPrevalidado({ tipo, children }: PropsRotuloPrevalidado): ReactElement {
  const esExpediente = tipo === "ESTADO_EXPEDIENTE";

  return (
    <span className="cae-rotulo-prevalidado" data-tipo={tipo}>
      {esExpediente ? (
        <span className="cae-rotulo-prevalidado__marca">{MARCA_NO_OFICIAL}</span>
      ) : null}
      <span className="cae-rotulo-prevalidado__contenido">{children}</span>
      <span className="cae-rotulo-prevalidado__aviso">
        {esExpediente ? ROTULO_ESTADO_EXPEDIENTE : ROTULO_AHORRO_PREVALIDADO}
      </span>
    </span>
  );
}
