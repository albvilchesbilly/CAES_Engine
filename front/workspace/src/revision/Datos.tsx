import type { ReactElement } from "react";

import { fechaAbsoluta } from "../fechas";
import {
  COLUMNA_DATO,
  COLUMNA_TIPO_EVIDENCIA,
  COLUMNA_VALOR,
  COMPROBACIONES_CONFORMES,
  COMPROBACIONES_FALLAN,
  COMPROBACIONES_NO_EVALUABLES,
  CRITERIO_PROPIO,
  ETIQUETA_JUSTIFICACION_REGISTRADA,
  RESTO_DATOS_NOTA,
  TITULO_COMPROBACIONES,
  TITULO_DATOS_CALCULO,
  TITULO_HISTORIAL,
  TITULO_RESTO_DATOS,
} from "../textos";
import { Citas } from "./Citas";
import type { Calculo, Dato, Evento, Regla, Veredicto } from "./datos";

/**
 * Los datos con su cita, las comprobaciones y el historial: los niveles 4 y 5 de `T-REV-revision` §2.
 *
 * La regla dura de la pantalla es **lo que cumple no ocupa sitio**: las comprobaciones conformes se
 * resumen en un contador que se despliega, y los datos que no entran en el calculo van plegados. Lo que
 * falla, lo que no se pudo evaluar y lo que hay que creerse para creerse la cifra, arriba y visible.
 *
 * Aqui no se evalua ninguna regla (`R-UI-11`): `resultado`, `severidad` y `motivo` llegan decididos y se
 * leen. Contar cuantas cumplen es presentacion, igual que en el informe del nucleo.
 *
 * `R-UI-09` sin excepciones: **todos** los datos se pintan con sus citas, tambien los plegados. Un dato
 * que llegue sin ninguna se ensena diciendolo (ver `Citas`), no se esconde.
 */

export interface PropsDatos {
  readonly datos: readonly Dato[];
  readonly calculo: Calculo;
  readonly veredicto: Veredicto;
  readonly historial: readonly Evento[];
  readonly nombreDocumento: (docId: string) => string;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
}

/** Los nombres que el motor declaro como entrada del calculo. Si no hubo calculo, no hay ninguno. */
function entradasDelCalculo(calculo: Calculo): ReadonlySet<string> {
  const nombres = new Set<string>();
  for (const unidad of calculo.porUnidad) {
    for (const entrada of unidad.entradas) {
      nombres.add(entrada.nombre);
    }
  }
  return nombres;
}

function claveDe(dato: Dato): string {
  return `${dato.variable}@${dato.numSerieMotor ?? ""}`;
}

function FilaDato({
  dato,
  nombreDocumento,
  onVerDocumento,
}: {
  readonly dato: Dato;
  readonly nombreDocumento: (docId: string) => string;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
}): ReactElement {
  return (
    <tr
      className="cae-revision__dato"
      data-dato={dato.variable}
      data-unidad={dato.numSerieMotor ?? undefined}
    >
      <th scope="row">
        <span className="cae-revision__nombre">{dato.variable}</span>
        {dato.descripcion === null ? null : (
          <span className="cae-revision__descripcion">{dato.descripcion}</span>
        )}
        {dato.numSerieMotor === null ? null : (
          <span className="cae-revision__unidad-serie">{dato.numSerieMotor}</span>
        )}
      </th>
      <td className="cae-revision__dato-valor">
        {/* Las tres capas, y las tres se ven (`CLAUDE.md` §2, regla 3): lo que consumio el calculo aqui,
            la interpretacion al lado y la evidencia documental en la cita. Ninguna resume a otra. */}
        <span data-capa="consumido">{dato.valorConsumido}</span>
        {dato.valorNormalizado === null || dato.valorNormalizado === dato.valorConsumido ? null : (
          <span className="cae-revision__normalizado" data-capa="normalizado">
            {dato.valorNormalizado}
          </span>
        )}
        {dato.unidad === null ? null : <span className="cae-revision__unidad">{` ${dato.unidad}`}</span>}
      </td>
      <td className="cae-revision__dato-tipo">
        {dato.tipoEvidencia}
        {dato.interpretacion === null ? null : (
          <span className="cae-revision__criterio" data-criterio={dato.interpretacion}>
            {`${dato.interpretacion} · ${CRITERIO_PROPIO}`}
          </span>
        )}
      </td>
      <td className="cae-revision__dato-citas">
        <Citas citas={dato.citas} nombreDocumento={nombreDocumento} onVerDocumento={onVerDocumento} />
        {dato.avisos.map((aviso) => (
          <p key={aviso} className="cae-revision__aviso">
            {aviso}
          </p>
        ))}
      </td>
    </tr>
  );
}

function TablaDatos({
  datos,
  nombreDocumento,
  onVerDocumento,
}: {
  readonly datos: readonly Dato[];
  readonly nombreDocumento: (docId: string) => string;
  readonly onVerDocumento: (docId: string, pagina: number | null, textoLiteral: string | null) => void;
}): ReactElement {
  return (
    <table className="cae-revision__datos">
      <thead>
        <tr>
          <th scope="col">{COLUMNA_DATO}</th>
          <th scope="col">{COLUMNA_VALOR}</th>
          <th scope="col">{COLUMNA_TIPO_EVIDENCIA}</th>
          <th scope="col">{TITULO_DATOS_CALCULO}</th>
        </tr>
      </thead>
      <tbody>
        {datos.map((dato) => (
          <FilaDato
            key={claveDe(dato)}
            dato={dato}
            nombreDocumento={nombreDocumento}
            onVerDocumento={onVerDocumento}
          />
        ))}
      </tbody>
    </table>
  );
}

function FilaRegla({ regla }: { readonly regla: Regla }): ReactElement {
  return (
    <li className="cae-revision__regla" data-regla={regla.id} data-resultado={regla.resultado ?? undefined}>
      <span className="cae-revision__regla-id">{regla.id}</span>
      {regla.severidad === null ? null : (
        <span className="cae-revision__severidad">{` (${regla.severidad})`}</span>
      )}
      {regla.descripcion === null ? null : (
        <span className="cae-revision__regla-descripcion">{` · ${regla.descripcion}`}</span>
      )}
      {regla.referencia === null ? null : (
        <span className="cae-revision__referencia">{` · ${regla.referencia}`}</span>
      )}
      {regla.motivo === null ? null : (
        <span className="cae-revision__regla-motivo">{` · ${regla.motivo}`}</span>
      )}
      {regla.interpretacion === null ? null : (
        <span className="cae-revision__criterio" data-criterio={regla.interpretacion}>
          {` · ${regla.interpretacion} · ${CRITERIO_PROPIO}`}
        </span>
      )}
    </li>
  );
}

const RESULTADO_CUMPLE = "CUMPLE";
const RESULTADO_FALLA = "FALLA";
const RESULTADO_NO_EVALUABLE = "NO_EVALUABLE";

function Comprobaciones({ veredicto }: { readonly veredicto: Veredicto }): ReactElement | null {
  if (veredicto.reglas.length === 0) {
    return null;
  }
  const fallan = veredicto.reglas.filter((regla) => regla.resultado === RESULTADO_FALLA);
  const noEvaluables = veredicto.reglas.filter((regla) => regla.resultado === RESULTADO_NO_EVALUABLE);
  const conformes = veredicto.reglas.filter((regla) => regla.resultado === RESULTADO_CUMPLE);

  return (
    <section className="cae-revision__comprobaciones" aria-label={TITULO_COMPROBACIONES}>
      <h3 className="cae-revision__titulo-bloque">{TITULO_COMPROBACIONES}</h3>

      {fallan.length === 0 ? null : (
        <ul className="cae-revision__fallan" data-cuenta={fallan.length}>
          <li className="cae-revision__contador">{`${fallan.length} ${COMPROBACIONES_FALLAN}`}</li>
          {fallan.map((regla) => (
            <FilaRegla key={regla.id} regla={regla} />
          ))}
        </ul>
      )}

      {noEvaluables.length === 0 ? null : (
        <ul className="cae-revision__no-evaluables" data-cuenta={noEvaluables.length}>
          <li className="cae-revision__contador">
            {`${noEvaluables.length} ${COMPROBACIONES_NO_EVALUABLES}`}
          </li>
          {noEvaluables.map((regla) => (
            <FilaRegla key={regla.id} regla={regla} />
          ))}
        </ul>
      )}

      {/* Lo que cumple no ocupa sitio: un contador que se despliega, no 26 filas (`CA-REV-19`). */}
      <details className="cae-revision__conformes" data-cuenta={conformes.length}>
        <summary>{`${conformes.length} ${COMPROBACIONES_CONFORMES}`}</summary>
        <ul>
          {conformes.map((regla) => (
            <FilaRegla key={regla.id} regla={regla} />
          ))}
        </ul>
      </details>

      {veredicto.hashReglas === null ? null : (
        <p className="cae-revision__hash-reglas">{veredicto.hashReglas}</p>
      )}
    </section>
  );
}

/** El payload de un evento, tal cual llego. Una correccion trae aqui su justificacion (`R-UI-04`). */
function Payload({ evento }: { readonly evento: Evento }): ReactElement | null {
  const justificacion = evento.payload["justificacion"];
  if (typeof justificacion !== "string" || justificacion.trim() === "") {
    return null;
  }
  return (
    <span className="cae-revision__justificacion-registrada">
      {`${ETIQUETA_JUSTIFICACION_REGISTRADA}: ${justificacion}`}
    </span>
  );
}

function Historial({ historial }: { readonly historial: readonly Evento[] }): ReactElement | null {
  if (historial.length === 0) {
    return null;
  }
  return (
    <details className="cae-revision__historial" data-cuenta={historial.length}>
      <summary>{`${TITULO_HISTORIAL} (${historial.length})`}</summary>
      <ul>
        {/* En el orden en que los sirvio el servidor: el log tiene su secuencia y no se reordena. */}
        {historial.map((evento, posicion) => (
          <li key={`${evento.tipo}-${posicion}`} className="cae-revision__evento" data-evento={evento.tipo}>
            <span className="cae-revision__evento-tipo">{evento.tipo}</span>
            <span className="cae-revision__evento-fecha">{fechaAbsoluta(evento.ocurridoEn)}</span>
            <span className="cae-revision__evento-actor">
              {[evento.actor, evento.rol].filter((parte) => parte !== null).join(" · ")}
            </span>
            <Payload evento={evento} />
          </li>
        ))}
      </ul>
    </details>
  );
}

export function Datos({
  datos,
  calculo,
  veredicto,
  historial,
  nombreDocumento,
  onVerDocumento,
}: PropsDatos): ReactElement {
  const entradas = entradasDelCalculo(calculo);
  const delCalculo = datos.filter((dato) => entradas.has(dato.variable));
  const resto = datos.filter((dato) => !entradas.has(dato.variable));

  return (
    <>
      {delCalculo.length === 0 ? null : (
        <section className="cae-revision__datos-calculo" aria-label={TITULO_DATOS_CALCULO}>
          <h3 className="cae-revision__titulo-bloque">{TITULO_DATOS_CALCULO}</h3>
          <TablaDatos
            datos={delCalculo}
            nombreDocumento={nombreDocumento}
            onVerDocumento={onVerDocumento}
          />
        </section>
      )}

      {resto.length === 0 ? null : (
        <details className="cae-revision__resto-datos" data-cuenta={resto.length}>
          <summary>{`${TITULO_RESTO_DATOS} (${resto.length})`}</summary>
          <p className="cae-revision__nota">{RESTO_DATOS_NOTA}</p>
          <TablaDatos datos={resto} nombreDocumento={nombreDocumento} onVerDocumento={onVerDocumento} />
        </details>
      )}

      <Comprobaciones veredicto={veredicto} />
      <Historial historial={historial} />
    </>
  );
}
