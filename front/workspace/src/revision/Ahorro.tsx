import { RotuloPrevalidado, ValorMetrica } from "@cae/compartido";
import type { ReactElement } from "react";

import {
  CRITERIO_PROPIO,
  ESTIMACION_NO_ACREDITADA,
  ETIQUETA_CONTROLES,
  ETIQUETA_DERIVADAS,
  ETIQUETA_ENTRADAS,
  ETIQUETA_PRECONDICIONES,
  PARA_PRESENTAR,
  PENDIENTE_DE_RECALCULO,
  PENDIENTE_DE_RECALCULO_DESCRIPCION,
  TITULO_AHORRO,
  TITULO_INTERPRETACIONES,
  TITULO_PROCEDENCIA,
  TRAZA_NOTA,
  TRUNCADO_INT06,
  VER_FORMULA,
} from "../textos";
import { Citas } from "./Citas";
import type { Calculo, Dato, Magnitud, UnidadCalculo } from "./datos";

/**
 * El ahorro y su escalera de procedencia (`T-REV-revision` §7).
 *
 * **Aqui no se calcula nada** (`R-UI-11`): todos los numeros llegan servidos, cada uno dos veces —la
 * forma exacta y la presentable en español—, y se pintan tal cual. Ni un `Number`, ni un porcentaje
 * compuesto a mano, ni una formula recompuesta. Lo que esta seccion aporta es el orden y las palabras.
 *
 * Tres reglas que se ven en el codigo:
 *
 * - **Sin cifra, `SIN DATO` con el motivo del servidor. Nunca 0** (`R-UI-07`): un cero en una columna de
 *   ahorros se lee como "no ahorra", y lo que pasa es que no se ha podido calcular.
 * - **Ninguna cifra sale sin su rotulo** (`R-UI-06`), y el truncado, ademas, sin su etiqueta de INT-06.
 * - **Los `INT-xx` se nombran como lo que son**: criterio propio sin validar, nunca "segun la normativa"
 *   (`CLAUDE.md` §3).
 *
 * La unidad la declara la ficha y la sirve `api/` (`GAP-REV-10`): no esta escrita en ninguna parte del
 * front. Una ficha que no la declare sale sin unidad, no con una inventada.
 */

export interface PropsAhorro {
  readonly calculo: Calculo;
  /** El dato consolidado de una entrada del calculo, para arrastrar su cita (`R-UI-09`). */
  readonly datoDe: (variable: string, numSerieMotor: string | null) => Dato | undefined;
  readonly nombreDocumento: (docId: string) => string;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
  /** `CA-REV-09`: el ahorro de antes de la ultima correccion no se presenta como si fuera el de después. */
  readonly pendienteDeRecalculo: boolean;
}

function Unidad({ unidad }: { readonly unidad: string | null }): ReactElement | null {
  return unidad === null ? null : <span className="cae-revision__unidad">{` ${unidad}`}</span>;
}

/** Un `INT-xx` es un criterio propio y se dice en la misma linea, no en una nota al pie. */
function Criterios({ interpretaciones }: { readonly interpretaciones: readonly string[] }): ReactElement | null {
  if (interpretaciones.length === 0) {
    return null;
  }
  return (
    <span className="cae-revision__criterios">
      {interpretaciones.map((criterio) => (
        <span key={criterio} className="cae-revision__criterio" data-criterio={criterio}>
          {`${criterio} · ${CRITERIO_PROPIO}`}
        </span>
      ))}
    </span>
  );
}

function Linea({
  magnitud,
  numSerieMotor,
  datoDe,
  nombreDocumento,
  onVerDocumento,
}: {
  readonly magnitud: Magnitud;
  readonly numSerieMotor: string | null;
  readonly datoDe: (variable: string, numSerieMotor: string | null) => Dato | undefined;
  readonly nombreDocumento: (docId: string) => string;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
}): ReactElement {
  // Una entrada arrastra su cita; una derivada no sale de un papel y trae su origen (`fuentes`), que es
  // lo que la distingue: `tabla:REG1781_CUADRO6` no es un documento y no se puede enlazar a uno.
  const dato = magnitud.fuente === null ? datoDe(magnitud.nombre, numSerieMotor) : undefined;
  return (
    <li className="cae-revision__linea" data-magnitud={magnitud.nombre}>
      <span className="cae-revision__nombre">{magnitud.nombre}</span>
      {magnitud.descripcion === null ? null : (
        <span className="cae-revision__descripcion">{magnitud.descripcion}</span>
      )}
      <span className="cae-revision__valor" data-exacto={magnitud.exacto ?? undefined}>
        {magnitud.presentable ?? magnitud.exacto}
        <Unidad unidad={magnitud.unidad} />
      </span>
      {magnitud.fuente === null ? null : (
        <span className="cae-revision__fuente" data-fuente={magnitud.fuente}>
          {magnitud.fuente}
        </span>
      )}
      {dato === undefined ? null : (
        <>
          {dato.interpretacion === null ? null : (
            <Criterios interpretaciones={[dato.interpretacion]} />
          )}
          <Citas
            citas={dato.citas}
            nombreDocumento={nombreDocumento}
            onVerDocumento={onVerDocumento}
          />
        </>
      )}
    </li>
  );
}

function Estados({
  titulo,
  entradas,
}: {
  readonly titulo: string;
  readonly entradas: readonly (readonly [string, string])[];
}): ReactElement | null {
  if (entradas.length === 0) {
    return null;
  }
  return (
    <p className="cae-revision__controles">
      <span className="cae-revision__etiqueta">{titulo}</span>
      {entradas.map(([identificador, estado]) => (
        <span key={identificador} className="cae-revision__control" data-control={identificador}>
          {/* `true`, `false` o el centinela `"NO_EVALUABLE"`, tal y como lo escribe el motor. */}
          {`${identificador}: ${estado}`}
        </span>
      ))}
    </p>
  );
}

function Procedencia({
  unidad,
  datoDe,
  nombreDocumento,
  onVerDocumento,
}: {
  readonly unidad: UnidadCalculo;
  readonly datoDe: (variable: string, numSerieMotor: string | null) => Dato | undefined;
  readonly nombreDocumento: (docId: string) => string;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
}): ReactElement {
  return (
    <section className="cae-revision__procedencia-unidad" data-unidad={unidad.numSerieMotor ?? undefined}>
      <h4 className="cae-revision__titulo-unidad">
        {unidad.numSerieMotor}
        {unidad.salidaPresentable === null ? null : (
          <span className="cae-revision__salida" data-exacto={unidad.salida ?? undefined}>
            {unidad.salidaPresentable}
            <Unidad unidad={unidad.salidaUnidad} />
          </span>
        )}
      </h4>
      {unidad.motivoNoCalculo === null ? null : (
        <p className="cae-revision__motivo-no-calculo">{unidad.motivoNoCalculo}</p>
      )}

      <p className="cae-revision__etiqueta">{ETIQUETA_ENTRADAS}</p>
      <ul className="cae-revision__lineas">
        {unidad.entradas.map((magnitud) => (
          <Linea
            key={magnitud.nombre}
            magnitud={magnitud}
            numSerieMotor={unidad.numSerieMotor}
            datoDe={datoDe}
            nombreDocumento={nombreDocumento}
            onVerDocumento={onVerDocumento}
          />
        ))}
      </ul>

      {unidad.derivadas.length === 0 ? null : (
        <>
          <p className="cae-revision__etiqueta">{ETIQUETA_DERIVADAS}</p>
          <ul className="cae-revision__lineas">
            {unidad.derivadas.map((magnitud) => (
              <Linea
                key={magnitud.nombre}
                magnitud={magnitud}
                numSerieMotor={unidad.numSerieMotor}
                datoDe={datoDe}
                nombreDocumento={nombreDocumento}
                onVerDocumento={onVerDocumento}
              />
            ))}
          </ul>
        </>
      )}

      <Estados titulo={ETIQUETA_CONTROLES} entradas={unidad.controles} />
      <Estados titulo={ETIQUETA_PRECONDICIONES} entradas={unidad.precondiciones} />
      {unidad.interpretaciones.length === 0 ? null : (
        <p className="cae-revision__interpretaciones">
          <span className="cae-revision__etiqueta">{TITULO_INTERPRETACIONES}</span>
          <Criterios interpretaciones={unidad.interpretaciones} />
        </p>
      )}
      {unidad.avisos.map((aviso) => (
        <p key={aviso} className="cae-revision__aviso">
          {aviso}
        </p>
      ))}
    </section>
  );
}

export function Ahorro({
  calculo,
  datoDe,
  nombreDocumento,
  onVerDocumento,
  pendienteDeRecalculo,
}: PropsAhorro): ReactElement {
  const hayCifra = calculo.totalPresentable !== null;

  return (
    <section className="cae-revision__ahorro" aria-label={TITULO_AHORRO}>
      <h2 className="cae-revision__titulo-bloque">{TITULO_AHORRO}</h2>

      {pendienteDeRecalculo ? (
        <p className="cae-revision__pendiente" role="alert" title={PENDIENTE_DE_RECALCULO_DESCRIPCION}>
          {PENDIENTE_DE_RECALCULO}
        </p>
      ) : null}

      {hayCifra ? (
        <>
          <RotuloPrevalidado tipo="AHORRO_PREVALIDADO">
            <span className="cae-revision__cifra" data-exacto={calculo.totalExacto ?? undefined}>
              {calculo.totalPresentable}
              <Unidad unidad={calculo.unidad} />
            </span>
          </RotuloPrevalidado>
          {calculo.totalCaePresentable === null ? null : (
            <p className="cae-revision__cae">
              <span className="cae-revision__etiqueta">{PARA_PRESENTAR}</span>
              <span className="cae-revision__cifra-cae" data-exacto={calculo.totalCae ?? undefined}>
                {calculo.totalCaePresentable}
                <Unidad unidad={calculo.unidad} />
              </span>
              <span className="cae-revision__truncado">{TRUNCADO_INT06}</span>
            </p>
          )}
          {calculo.provisional === true ? (
            <p className="cae-revision__estimacion">{ESTIMACION_NO_ACREDITADA}</p>
          ) : null}
        </>
      ) : (
        <>
          {/* `R-UI-07`: el hueco se anuncia y se explica con el texto del servidor. Nunca un cero. */}
          <ValorMetrica etiqueta={TITULO_AHORRO} metrica={{ estado: "SIN_DATO" }} />
          {calculo.motivoNoCalculo === null ? null : (
            <p className="cae-revision__motivo-no-calculo">{calculo.motivoNoCalculo}</p>
          )}
        </>
      )}

      {calculo.porUnidad.length === 0 ? null : (
        <>
          <h3 className="cae-revision__titulo-bloque">{TITULO_PROCEDENCIA}</h3>
          {calculo.porUnidad.map((unidad, posicion) => (
            <Procedencia
              key={unidad.numSerieMotor ?? posicion}
              unidad={unidad}
              datoDe={datoDe}
              nombreDocumento={nombreDocumento}
              onVerDocumento={onVerDocumento}
            />
          ))}
        </>
      )}

      {calculo.traza.length === 0 ? null : (
        <details className="cae-revision__traza">
          <summary>{VER_FORMULA}</summary>
          {/* Tal cual la escribe el motor: traducirla seria interpretarla (`T-REV-revision` §7). */}
          <ol>
            {calculo.traza.map((linea) => (
              <li key={linea}>{linea}</li>
            ))}
          </ol>
          <p className="cae-revision__nota">{TRAZA_NOTA}</p>
        </details>
      )}
    </section>
  );
}
