import { RotuloPrevalidado, ValorMetrica } from "@cae/compartido";
import type { ReactElement, ReactNode } from "react";

import { fechaAbsoluta, textoAntiguedad } from "../fechas";
import { textos as textosDe } from "../json";
import {
  COLUMNA_AHORRO,
  COLUMNA_ANTIGUEDAD,
  COLUMNA_VEREDICTO,
  ESTIMACION_NO_ACREDITADA,
  ETIQUETA_CICLO,
  ETIQUETA_PLATAFORMA,
  ETIQUETA_ULTIMO_MOVIMIENTO,
  IR_A_REVISION,
  MOTIVO_AUSENTE,
  SOLO_LECTURA,
  SOLO_LECTURA_DESCRIPCION,
} from "../textos";
import type { CalculoCola, Carencia, DetalleFila, EstadosCola, FilaCola, Resultado } from "./datos";
import { rotuloDe } from "./motivos";

/** El estado de ciclo en el que la actuacion ya esta en manos de la plataforma (`engine/estados.py`). */
const ESTADO_EN_PLATAFORMA = "EN_PLATAFORMA";

export interface PropsFilaCola {
  readonly fila: FilaCola;
  /** Las tres lecturas de esta actuacion, o `undefined` si la fila no trajo identificador. */
  readonly detalle: DetalleFila | undefined;
  /** El reloj, inyectado para que "hace N días" sea comprobable. */
  readonly ahora: Date;
  /** A donde lleva la fila. Se compone **con el identificador que dio la lectura** (`R-UI-12`). */
  readonly enlaceRevision: (actuacionId: string) => string;
}

function SinDato({ etiqueta }: { readonly etiqueta: string }): ReactElement {
  return <ValorMetrica etiqueta={etiqueta} metrica={{ estado: "SIN_DATO" }} />;
}

function Porque({ children }: { readonly children: ReactNode }): ReactElement {
  return <span className="cae-cola__porque">{children}</span>;
}

/**
 * El ahorro de la fila. Tres finales posibles y ninguno es un cero ni una celda en blanco (`R-UI-07`).
 *
 * La cifra **se pinta tal y como llega**: `api/` sirve `total_exacto_presentable` ya legible en espanol
 * junto a la forma exacta (`GAP-COLA-04`, cerrado en `FR1.a`), y pasarla por `Number` seria convertir el
 * ahorro a coma flotante, que es justo lo que `CLAUDE.md` §2 prohibe. Aqui no hay ni una operacion
 * aritmetica sobre ella: entra cadena y sale cadena.
 */
function CeldaAhorro({ calculo }: { readonly calculo: Resultado<CalculoCola> | undefined }): ReactElement {
  if (calculo === undefined) {
    return <SinDato etiqueta={COLUMNA_AHORRO} />;
  }
  if (calculo.estado === "ERROR") {
    return (
      <>
        <SinDato etiqueta={COLUMNA_AHORRO} />
        <Porque>{calculo.fallo.mensaje}</Porque>
      </>
    );
  }
  const { presentable, exacto, unidad, provisional, motivoNoCalculo } = calculo.valor;
  if (presentable === null) {
    return (
      <>
        <SinDato etiqueta={COLUMNA_AHORRO} />
        {motivoNoCalculo === null ? null : <Porque>{motivoNoCalculo}</Porque>}
      </>
    );
  }
  return (
    <>
      <RotuloPrevalidado tipo="AHORRO_PREVALIDADO">
        <span className="cae-cola__cifra" data-exacto={exacto ?? undefined}>
          {presentable}
        </span>
        {/* La unidad la declara la ficha y la sirve `api/` (`GAP-COLA-05`). Una cifra de ahorro sin
            unidad no es una cifra: 305.829,6 no dice nada hasta que dice de que. Lo que no llega no se
            inventa, y entonces se pinta la cifra sola. */}
        {unidad === null ? null : <span className="cae-cola__unidad">{` ${unidad}`}</span>}
      </RotuloPrevalidado>
      {provisional === true ? (
        <span className="cae-cola__estimacion">{ESTIMACION_NO_ACREDITADA}</span>
      ) : null}
    </>
  );
}

/** Las carencias con su mensaje (`CAP-04`); si esa lectura no llego, al menos sus identificadores. */
function Carencias({
  carencias,
  identificadores,
}: {
  readonly carencias: Resultado<readonly Carencia[]> | undefined;
  readonly identificadores: readonly string[];
}): ReactElement | null {
  if (carencias !== undefined && carencias.estado === "LISTO" && carencias.valor.length > 0) {
    return (
      <ul className="cae-cola__carencias">
        {carencias.valor.map((carencia, posicion) => (
          <li key={carencia.id ?? posicion}>
            <span className="cae-cola__carencia-id">{carencia.id}</span>
            {carencia.mensaje === null ? null : ` · ${carencia.mensaje}`}
          </li>
        ))}
      </ul>
    );
  }
  if (identificadores.length === 0) {
    return null;
  }
  return (
    <ul className="cae-cola__carencias">
      {identificadores.map((identificador) => (
        <li key={identificador}>
          <span className="cae-cola__carencia-id">{identificador}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Una fila de la cola: por que esta aqui, cuanto lleva esperando y a donde se va desde ella.
 *
 * `R-UI-02`: el veredicto es **texto**. No hay aqui ningun boton, ningun desplegable y ningun campo que
 * lo fije, lo fuerce o lo cambie; el veredicto se cambia corrigiendo un dato y dejando que el motor
 * recalcule, y eso ocurre en la vista de revision.
 *
 * `R-UI-09`: la fila **nombra** el conflicto y no ensena los dos valores enfrentados. Un valor extraido
 * arrastra su cita, y una lista que se lee de un vistazo no es sitio para cuatro evidencias.
 */
export function Fila({ fila, detalle, ahora, enlaceRevision }: PropsFilaCola): ReactElement {
  // Cuando `CAP-14` no llega se pinta lo que si vino con la lista, y se dice que esa lectura fallo:
  // esconder un estado que tenemos delante no es mas honesto que ensenarlo (`T-REV-cola` §7).
  const estados: EstadosCola =
    detalle?.estados.estado === "LISTO" ? detalle.estados.valor : fila.estado;
  const soloLectura = estados.ciclo === ESTADO_EN_PLATAFORMA && estados.requerimientoAbierto === null;
  const abierta = fechaAbsoluta(fila.abiertaEn);
  const relativa = textoAntiguedad(fila.abiertaEn, ahora);
  const movimiento = fechaAbsoluta(fila.ultimoMovimientoEn);

  return (
    <tr className="cae-cola__fila" data-actuacion={fila.actuacionId ?? undefined}>
      <th scope="row" className="cae-cola__actuacion">
        <span className="cae-cola__codigo">{fila.codigo}</span>
        {fila.ficha === null ? null : <span className="cae-cola__ficha">{fila.ficha}</span>}
      </th>

      <td className="cae-cola__celda-veredicto">
        {fila.veredicto === null ? (
          <SinDato etiqueta={COLUMNA_VEREDICTO} />
        ) : (
          <span className="cae-cola__veredicto">
            {fila.semaforo === null ? null : (
              <span className="cae-cola__semaforo" aria-hidden="true">
                {fila.semaforo}
              </span>
            )}
            {fila.veredicto}
          </span>
        )}
      </td>

      <td className="cae-cola__celda-motivos">
        {fila.motivos.length === 0 ? (
          <span className="cae-cola__sin-motivo">{MOTIVO_AUSENTE}</span>
        ) : (
          <ul className="cae-cola__motivos">
            {fila.motivos.map((motivo) => (
              <li key={motivo.motivo} className="cae-cola__motivo" data-motivo={motivo.motivo}>
                {rotuloDe(motivo)}
                {motivo.motivo === "correccion_pendiente" ? (
                  <Carencias
                    carencias={detalle?.carencias}
                    identificadores={textosDe(motivo.detalle["carencias"])}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </td>

      <td className="cae-cola__celda-ahorro">
        <CeldaAhorro calculo={detalle?.calculo} />
      </td>

      <td className="cae-cola__celda-antiguedad">
        {abierta === null ? (
          <SinDato etiqueta={COLUMNA_ANTIGUEDAD} />
        ) : (
          <>
            <span className="cae-cola__fecha">{abierta}</span>
            {relativa === null ? null : <span className="cae-cola__relativa">{relativa}</span>}
          </>
        )}
        {movimiento === null ? null : (
          <span className="cae-cola__movimiento">{`${ETIQUETA_ULTIMO_MOVIMIENTO}: ${movimiento}`}</span>
        )}
      </td>

      <td className="cae-cola__celda-estado">
        <span className="cae-cola__ciclo">
          {estados.ciclo === null ? (
            <SinDato etiqueta={ETIQUETA_CICLO} />
          ) : (
            `${ETIQUETA_CICLO}: ${estados.ciclo}`
          )}
        </span>
        <span className="cae-cola__plataforma">
          {estados.plataforma === null ? (
            <SinDato etiqueta={ETIQUETA_PLATAFORMA} />
          ) : (
            `${ETIQUETA_PLATAFORMA}: ${estados.plataforma}`
          )}
        </span>
        {soloLectura ? (
          <span className="cae-cola__solo-lectura" title={SOLO_LECTURA_DESCRIPCION}>
            {SOLO_LECTURA}
          </span>
        ) : null}
        {detalle?.estados.estado === "ERROR" ? <Porque>{detalle.estados.fallo.mensaje}</Porque> : null}
      </td>

      <td className="cae-cola__celda-accion">
        {fila.actuacionId === null ? null : (
          <a className="cae-cola__ir" href={enlaceRevision(fila.actuacionId)}>
            {IR_A_REVISION}
          </a>
        )}
      </td>
    </tr>
  );
}
