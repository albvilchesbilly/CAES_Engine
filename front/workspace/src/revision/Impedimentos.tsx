import type { ReactElement } from "react";

import {
  CARENCIA_DOCUMENTOS,
  CONFLICTO_EXPLICACION,
  ETIQUETA_POR_FUENTE,
  ETIQUETA_REFERENCIA,
  QUE_ES_ESTE_DATO,
  TITULO_CARENCIAS,
  TITULO_CONFLICTO,
  TITULO_IMPIDE,
} from "../textos";
import { TablaCitas } from "./Citas";
import { Correccion, type DatosCorreccion } from "./Correccion";
import type { Carencia, Cita, Conflicto as ConflictoDato, Dato } from "./datos";

/**
 * Lo unico accionable de la pantalla: los conflictos primero y las carencias despues.
 *
 * Es el nivel 2 de `T-REV-revision` §2 y va **por encima del bloque de ahorro** en el DOM, porque es la
 * respuesta a "que hago ahora". Lo que cumple no ocupa sitio.
 *
 * La tarjeta de conflicto se apoya en `evidencias` y no en `calculo` (§6, resuelto el 23/09/2026): en un
 * caso bloqueado el motor se salta la fase de calculo entera, `por_unidad` llega vacio y la traza
 * tambien. Que `PM` importe no es un resultado del calculo, es una verdad de la ficha, y la ficha esta
 * cargada aunque no se calcule nada. Lo que la tarjeta no puede decir es que salidas dependian del dato,
 * porque no hay salidas: para eso esta `motivo_no_calculo`, que llega con el texto exacto del servidor y
 * explica el hueco en vez de dejarlo en blanco (`R-UI-07`).
 */

export interface PropsImpedimentos {
  readonly conflictos: readonly ConflictoDato[];
  readonly carencias: readonly Carencia[];
  /** El dato de la ficha para una variable en conflicto: su descripcion, su referencia y sus fuentes. */
  readonly datoDe: (variable: string, numSerieMotor: string | null) => Dato | undefined;
  readonly nombreDocumento: (docId: string) => string;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
  /** El texto exacto con el que el servidor explica que no hay calculo. No se reescribe. */
  readonly motivoNoCalculo: string | null;
  /** La evidencia elegida para corregir, si hay uno abierto, y las acciones del formulario. */
  readonly correccion: { readonly variable: string; readonly cita: Cita } | null;
  readonly onUsarValor: (variable: string, numSerieMotor: string | null, cita: Cita) => void;
  readonly onCorregir: (datos: DatosCorreccion) => void | Promise<void>;
  readonly onCancelar: () => void;
  /** `R-UI-05`: si la escritura esta cerrada, los controles se ven y dicen por que no estan activos. */
  readonly motivoInactivo?: string | undefined;
}

function claveDe(conflicto: ConflictoDato): string {
  return `${conflicto.variable}@${conflicto.numSerieMotor ?? ""}`;
}

/** "Conflicto en PM · Potencia nominal del motor · motor MTR-SYN-0001", con lo que haya. */
function tituloDe(conflicto: ConflictoDato, dato: Dato | undefined): string {
  const partes = [
    `${TITULO_CONFLICTO} ${conflicto.variable}`,
    dato?.descripcion ?? null,
    conflicto.numSerieMotor,
  ].filter((parte): parte is string => parte !== null && parte !== undefined);
  return partes.join(" · ");
}

function Ficha({ dato }: { readonly dato: Dato | undefined }): ReactElement | null {
  if (dato === undefined) {
    return null;
  }
  const definicion = dato.definicion ?? dato.descripcion;
  return (
    <dl className="cae-revision__ficha-dato">
      {definicion === null ? null : (
        <>
          <dt>{QUE_ES_ESTE_DATO}</dt>
          <dd>{definicion}</dd>
        </>
      )}
      {dato.referencia === null ? null : (
        <>
          <dt>{ETIQUETA_REFERENCIA}</dt>
          <dd className="cae-revision__referencia">{dato.referencia}</dd>
        </>
      )}
      {dato.valoresPorFuente.length === 0 ? null : (
        <>
          <dt>{ETIQUETA_POR_FUENTE}</dt>
          <dd>
            <ul className="cae-revision__por-fuente">
              {dato.valoresPorFuente.map(([fuente, valor]) => (
                <li key={fuente} data-fuente={fuente}>
                  {`${fuente}: ${valor}`}
                </li>
              ))}
            </ul>
          </dd>
        </>
      )}
    </dl>
  );
}

export function Impedimentos({
  conflictos,
  carencias,
  datoDe,
  nombreDocumento,
  onVerDocumento,
  motivoNoCalculo,
  correccion,
  onUsarValor,
  onCorregir,
  onCancelar,
  motivoInactivo,
}: PropsImpedimentos): ReactElement | null {
  if (conflictos.length === 0 && carencias.length === 0) {
    return null;
  }

  return (
    <section className="cae-revision__impide" aria-label={TITULO_IMPIDE}>
      <h2 className="cae-revision__titulo-bloque">{TITULO_IMPIDE}</h2>

      {conflictos.map((conflicto) => {
        const dato = datoDe(conflicto.variable, conflicto.numSerieMotor);
        const abierta = correccion !== null && correccion.variable === conflicto.variable;
        const descartados = conflicto.citas
          .map((cita) => cita.valor)
          .filter(
            (valor): valor is string =>
              valor !== null && valor !== (abierta ? correccion.cita.valor : null),
          );
        return (
          <article
            key={claveDe(conflicto)}
            className="cae-revision__conflicto"
            data-variable={conflicto.variable}
            data-unidad={conflicto.numSerieMotor ?? undefined}
          >
            <h3 className="cae-revision__conflicto-titulo">{tituloDe(conflicto, dato)}</h3>
            <p className="cae-revision__conflicto-explicacion">{CONFLICTO_EXPLICACION}</p>
            {motivoNoCalculo === null ? null : (
              <p className="cae-revision__motivo-no-calculo">{motivoNoCalculo}</p>
            )}
            <Ficha dato={dato} />
            <TablaCitas
              citas={conflicto.citas}
              nombreDocumento={nombreDocumento}
              onVerDocumento={onVerDocumento}
              fuentePrimaria={dato?.fuentePrimaria}
              onUsarValor={(cita) => onUsarValor(conflicto.variable, conflicto.numSerieMotor, cita)}
              motivoInactivo={motivoInactivo}
            />
            {abierta ? (
              <Correccion
                // La `key` remonta el formulario cuando se elige otra evidencia: asi la justificacion
                // vuelve a nacer vacia en **todos** los caminos de entrada (`CA-REV-03`).
                key={`${correccion.cita.docId ?? ""}-${correccion.cita.valor ?? ""}`}
                variable={conflicto.variable}
                numSerieMotor={conflicto.numSerieMotor}
                valorInicial={correccion.cita.valor ?? ""}
                unidad={dato?.unidad}
                descartados={descartados}
                onCorregir={onCorregir}
                onCancelar={onCancelar}
                motivoInactivo={motivoInactivo}
              />
            ) : null}
          </article>
        );
      })}

      {carencias.length === 0 ? null : (
        <section className="cae-revision__carencias" aria-label={TITULO_CARENCIAS}>
          <h3 className="cae-revision__titulo-bloque">{TITULO_CARENCIAS}</h3>
          <ul>
            {carencias.map((carencia, posicion) => (
              <li
                key={carencia.id ?? posicion}
                className="cae-revision__carencia"
                data-carencia={carencia.id ?? undefined}
                data-severidad={carencia.severidad ?? undefined}
              >
                <span className="cae-revision__carencia-id">{carencia.id}</span>
                {carencia.severidad === null ? null : (
                  <span className="cae-revision__severidad">{` (${carencia.severidad})`}</span>
                )}
                {carencia.mensaje === null ? null : (
                  <span className="cae-revision__carencia-mensaje">{` · ${carencia.mensaje}`}</span>
                )}
                {carencia.documentos.length === 0 ? null : (
                  <span className="cae-revision__carencia-documentos">
                    {` · ${CARENCIA_DOCUMENTOS}: ${carencia.documentos.join(", ")}`}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
