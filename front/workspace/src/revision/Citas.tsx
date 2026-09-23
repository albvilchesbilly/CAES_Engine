import type { ReactElement } from "react";

import {
  CITA_CORRECCION_HUMANA,
  COLUMNA_CONFIANZA,
  COLUMNA_DOCUMENTO,
  COLUMNA_METODO,
  COLUMNA_TEXTO_LITERAL,
  COLUMNA_TIPO_EVIDENCIA,
  COLUMNA_VALOR,
  ETIQUETA_FUENTE_PRIMARIA,
  ETIQUETA_PAGINA,
  SIN_CITA,
  USAR_ESTE_VALOR,
  VER_EN_EL_DOCUMENTO,
} from "../textos";
import { METODO_CORRECCION_HUMANA, type Cita } from "./datos";

/**
 * La cita de un dato: **documento, pagina y texto literal**, y una pulsacion hasta el papel (`R-UI-09`).
 *
 * Las dos cosas que este modulo no hace:
 *
 * - **No resume el texto literal.** Un texto literal recortado es un texto literal falso; si ocupa, ocupa.
 * - **No inventa una cita.** Un dato que llega sin ninguna se ensena diciendolo, en voz alta, porque un
 *   dato sin cita es un defecto visible y no una celda mas.
 *
 * Una **correccion humana** llega por este mismo camino, con `metodo` = `correccion_humana`, el
 * identificador del evento donde iria el documento y la justificacion donde iria el texto literal. No
 * sale de un papel: se dice asi y no se ofrece "ver en el documento", que no llevaria a ninguna parte.
 */

export interface PropsCitas {
  readonly citas: readonly Cita[];
  /** `doc_id` → nombre, tal y como lo dio el bloque `documentos`. La pantalla no compone ninguno. */
  readonly nombreDocumento: (docId: string) => string;
  /**
   * Lleva el panel izquierdo a ese documento, a esa pagina y a ese texto (`ADR-012` §4).
   *
   * El texto literal viaja con la cita porque es lo que hay que ir a comprobar: el panel lo ensena al
   * lado del documento, que es lo que se puede hacer sin retocar los bytes (el resaltado es del
   * navegador y el servidor no transforma nada).
   */
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
  /** La fuente que el motor declaro primaria para el dato, para marcarla. */
  readonly fuentePrimaria?: string | null | undefined;
  /** Si hay accion de correccion, la que precarga el formulario con esa evidencia (`CAP-05`). */
  readonly onUsarValor?: ((cita: Cita) => void) | undefined;
  /** `R-UI-05`: con la escritura cerrada, "Usar este valor" sigue visible y explica por que no. */
  readonly motivoInactivo?: string | undefined;
}

export function esCorreccionHumana(cita: Cita): boolean {
  return cita.metodo === METODO_CORRECCION_HUMANA;
}

/** El documento y la pagina de una cita, en una linea, o lo que sea la cita cuando no es un papel. */
function Procedencia({
  cita,
  nombreDocumento,
}: {
  readonly cita: Cita;
  readonly nombreDocumento: (docId: string) => string;
}): ReactElement {
  if (esCorreccionHumana(cita)) {
    return (
      <span className="cae-revision__procedencia">
        {CITA_CORRECCION_HUMANA}
        {cita.extractorVersion === null ? null : (
          <span className="cae-revision__extractor"> · {cita.extractorVersion}</span>
        )}
      </span>
    );
  }
  return (
    <span className="cae-revision__procedencia">
      {cita.docId === null ? null : nombreDocumento(cita.docId)}
      {cita.pagina === null ? null : (
        <span className="cae-revision__pagina">{` · ${ETIQUETA_PAGINA} ${cita.pagina}`}</span>
      )}
    </span>
  );
}

function Literal({ cita }: { readonly cita: Cita }): ReactElement | null {
  if (cita.textoLiteral === null) {
    return null;
  }
  return <q className="cae-revision__literal">{cita.textoLiteral}</q>;
}

function Ir({
  cita,
  onVerDocumento,
}: {
  readonly cita: Cita;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
}): ReactElement | null {
  if (cita.docId === null || esCorreccionHumana(cita)) {
    return null;
  }
  const docId = cita.docId;
  return (
    <button
      type="button"
      className="cae-revision__ver-documento"
      data-doc={docId}
      data-pagina={cita.pagina ?? undefined}
      onClick={() => onVerDocumento(docId, cita.pagina, cita.textoLiteral)}
    >
      {VER_EN_EL_DOCUMENTO}
    </button>
  );
}

/** Las citas de un dato, en lista. La forma compacta: la de la tabla esta mas abajo. */
export function Citas({ citas, nombreDocumento, onVerDocumento }: PropsCitas): ReactElement {
  if (citas.length === 0) {
    return (
      <p className="cae-revision__sin-cita" role="alert">
        {SIN_CITA}
      </p>
    );
  }
  return (
    <ul className="cae-revision__citas">
      {citas.map((cita, posicion) => (
        <li
          key={`${cita.docId ?? "sin-doc"}-${posicion}`}
          className="cae-revision__cita"
          data-cita=""
          data-doc={cita.docId ?? undefined}
          data-pagina={cita.pagina ?? undefined}
          data-metodo={cita.metodo ?? undefined}
        >
          <Procedencia cita={cita} nombreDocumento={nombreDocumento} />
          <Literal cita={cita} />
          <Ir cita={cita} onVerDocumento={onVerDocumento} />
        </li>
      ))}
    </ul>
  );
}

/**
 * Las mismas citas, comparables de un vistazo: una fila por evidencia con todo lo que la distingue.
 *
 * Es lo que la tarjeta de conflicto necesita (`T-REV-revision` §6): valor, documento, pagina, texto
 * literal, metodo, confianza y tipo de evidencia, **las que haya**, sin elegir ninguna y sin ordenarlas.
 */
export function TablaCitas({
  citas,
  nombreDocumento,
  onVerDocumento,
  fuentePrimaria,
  onUsarValor,
  motivoInactivo,
}: PropsCitas): ReactElement {
  if (citas.length === 0) {
    return (
      <p className="cae-revision__sin-cita" role="alert">
        {SIN_CITA}
      </p>
    );
  }
  return (
    <table className="cae-revision__evidencias">
      <thead>
        <tr>
          <th scope="col">{COLUMNA_VALOR}</th>
          <th scope="col">{COLUMNA_DOCUMENTO}</th>
          <th scope="col">{COLUMNA_TEXTO_LITERAL}</th>
          <th scope="col">{COLUMNA_METODO}</th>
          <th scope="col">{COLUMNA_CONFIANZA}</th>
          <th scope="col">{COLUMNA_TIPO_EVIDENCIA}</th>
          <th scope="col" />
        </tr>
      </thead>
      <tbody>
        {/* En el orden en que llegaron: aqui no se ordena ni se destaca una por encima de otra. */}
        {citas.map((cita, posicion) => (
          <tr
            key={`${cita.docId ?? "sin-doc"}-${posicion}`}
            className="cae-revision__evidencia"
            data-cita=""
            data-doc={cita.docId ?? undefined}
            data-pagina={cita.pagina ?? undefined}
            data-valor={cita.valor ?? undefined}
          >
            <td className="cae-revision__evidencia-valor">
              {cita.valor}
              {cita.unidad === null ? null : <span className="cae-revision__unidad">{` ${cita.unidad}`}</span>}
            </td>
            <td>
              <Procedencia cita={cita} nombreDocumento={nombreDocumento} />
              {fuentePrimaria !== null &&
              fuentePrimaria !== undefined &&
              cita.tipoDoc === fuentePrimaria ? (
                <span className="cae-revision__primaria">{ETIQUETA_FUENTE_PRIMARIA}</span>
              ) : null}
            </td>
            <td>
              <Literal cita={cita} />
            </td>
            <td>{cita.metodo}</td>
            <td>{cita.confianza}</td>
            <td>{cita.tipoEvidencia}</td>
            <td className="cae-revision__evidencia-acciones">
              <Ir cita={cita} onVerDocumento={onVerDocumento} />
              {onUsarValor === undefined ? null : (
                <button
                  type="button"
                  className="cae-revision__usar-valor"
                  data-valor={cita.valor ?? undefined}
                  disabled={motivoInactivo !== undefined}
                  title={motivoInactivo}
                  onClick={() => onUsarValor(cita)}
                >
                  {USAR_ESTE_VALOR}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
