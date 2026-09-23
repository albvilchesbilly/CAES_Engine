import type { ReactElement, ReactNode } from "react";

import {
  APROBAR_IMPEDIDO,
  APROBAR_NOTA,
  APROBAR_REVISION,
  CONFIRMAR_DESCARTE,
  CONFIRMAR_INTERPRETACION,
  ENVIAR_SUBSANACION,
  INACTIVO_INTERPRETACION,
  INACTIVO_SIN_TEXTO,
  INACTIVO_SUBIDA,
  INHABILITAR_NO_AUTORIZA,
  RESOLVER_DISCREPANCIA,
  REVISAR_OBSERVACION,
  SUBIR_DOCUMENTO,
} from "../textos";
import {
  CAPACIDAD_APROBAR,
  CAPACIDAD_DESCARTE,
  CAPACIDAD_DISCREPANCIA,
  CAPACIDAD_INTERPRETACION,
  CAPACIDAD_OBSERVACION,
  CAPACIDAD_SUBIR,
  CAPACIDAD_SUBSANACION,
  EVENTO_DISCREPANCIA,
  EVENTO_OBSERVACION,
  carenciasDeclaradas,
  escribiblePor,
  fueraDeAmbito,
  quedaAlgoAbierto,
  type Escritura,
  type Revision,
} from "./datos";

/**
 * Las acciones de `T-REV-revision` §8, y la regla que las gobierna a todas.
 *
 * **Ningun control fija, fuerza ni cambia un veredicto** (`R-UI-02`). "Aprobar" no aprueba un veredicto:
 * marca que una persona reviso, que es **la mitad** de la guarda de `LISTA_PARA_ENVIO`; la otra mitad es
 * el veredicto, y quien empaqueta es Operaciones. La pantalla lo dice al aprobar en vez de dejar creer
 * que aprobar es enviar.
 *
 * **Ningun control se llama "Firmar"** (`R-UI-03`). En esta pantalla no hay ninguna accion de firma: la
 * firma es un acto humano fuera de aqui y lo unico que hacemos es registrar que ocurrio, en otra
 * pantalla y con otro perfil.
 *
 * **Inhabilitar no es autorizar** (`R-UI-01`): el servidor valida cada comando igualmente. Un control
 * inhabilitado esta ahi para explicar **por que** no se puede, con la regla concreta al lado, no para
 * proteger nada. Por eso ninguno desaparece en silencio.
 *
 * Tres controles salen hoy inactivos, y cada uno dice su motivo:
 *
 * - **Subir documentacion** (`CAP-02`): el comando admite los bytes desde que se cerro `GAP-REV-03`; lo
 *   que falta es el canal del navegador (`GAP-HTTP-01`).
 * - **Confirmar la interpretacion** (`CAP-15`): `api/` no proyecta todavia la interpretacion propuesta
 *   (`GAP-REV-04`), y confirmar a ciegas lo que no se ha podido leer seria peor que esperar.
 * - **Enviar la subsanacion** (`CAP-09`) y **decidir ante la discrepancia** (`CAP-16`) y **confirmar el
 *   descarte** (`CAP-08`): los tres exigen un texto que escribe una persona o que redacta un agente —la
 *   subsanacion la redacta A5, que no existe—. Enviarlos vacios es un comando rechazado, y escribir ese
 *   texto aqui seria ponerle palabras a quien no las ha dicho. `GAP-REV-13`.
 */

export interface PropsAcciones {
  readonly revision: Revision;
  readonly escritura: Escritura;
  /** Por que la escritura esta cerrada, con las palabras de `R-UI-05`. Vacio si no lo esta. */
  readonly motivoEscritura?: string | undefined;
  readonly onAprobar: () => void | Promise<void>;
}

interface PropsAccion {
  readonly capacidad: string;
  readonly nombre: string;
  readonly activa: boolean;
  readonly motivo?: string | undefined;
  readonly onPulsar?: (() => void | Promise<void>) | undefined;
  readonly children?: ReactNode;
}

function Accion({ capacidad, nombre, activa, motivo, onPulsar, children }: PropsAccion): ReactElement {
  return (
    <div className="cae-revision__accion" data-capacidad={capacidad}>
      <button
        type="button"
        className="cae-revision__boton"
        disabled={!activa}
        title={activa ? undefined : motivo}
        onClick={() => {
          void onPulsar?.();
        }}
      >
        {nombre}
      </button>
      {activa || motivo === undefined ? null : (
        <span className="cae-revision__motivo-inactivo">{motivo}</span>
      )}
      {children}
    </div>
  );
}

/**
 * Por que no se puede aprobar, **con la regla concreta y su severidad** (`CA-REV-13`).
 *
 * Sale de lo que el servidor declara abierto: sus carencias, con el mensaje que el propio motor escribio
 * ("R-CON-01 (BLOQUEANTE_DATOS): PM coincide en todas las fuentes"), y sus conflictos. Nunca un boton
 * gris y mudo.
 */
function motivoDeNoAprobar(revision: Revision): string | undefined {
  if (revision.carencias.estado === "ERROR") {
    return revision.carencias.fallo.mensaje;
  }
  if (revision.estados.estado === "ERROR") {
    return revision.estados.fallo.mensaje;
  }
  const carencias = carenciasDeclaradas(revision).map((carencia) =>
    [carencia.id, carencia.severidad === null ? null : `(${carencia.severidad})`, carencia.mensaje]
      .filter((parte) => parte !== null && parte !== undefined)
      .join(" "),
  );
  const conflictos = revision.conflictos.map(
    (conflicto) => `${conflicto.variable}${conflicto.numSerieMotor === null ? "" : ` · ${conflicto.numSerieMotor}`}`,
  );
  const abiertos = [...conflictos, ...carencias];
  return abiertos.length === 0 ? undefined : `${APROBAR_IMPEDIDO} ${abiertos.join(" · ")}`;
}

export function Acciones({
  revision,
  escritura,
  motivoEscritura,
  onAprobar,
}: PropsAcciones): ReactElement {
  const abierto = quedaAlgoAbierto(revision);
  const hayObservaciones = revision.historial.some((evento) => evento.tipo === EVENTO_OBSERVACION);
  const hayDiscrepancia = revision.historial.some((evento) => evento.tipo === EVENTO_DISCREPANCIA);
  const requerimiento =
    revision.estados.estado === "LISTO" ? revision.estados.valor.requerimientoAbierto : null;

  const puede = (capacidad: string) => escribiblePor(escritura, capacidad);
  // El orden importa: si la escritura esta cerrada, el motivo es ese; si no, el que declare el servidor.
  const motivoDe = (capacidad: string, propio?: string) =>
    puede(capacidad) ? propio : (motivoEscritura ?? propio);

  return (
    <section className="cae-revision__acciones-bloque" aria-label={APROBAR_REVISION}>
      <Accion
        capacidad={CAPACIDAD_APROBAR}
        nombre={APROBAR_REVISION}
        activa={puede(CAPACIDAD_APROBAR) && !abierto}
        motivo={motivoDe(CAPACIDAD_APROBAR, motivoDeNoAprobar(revision))}
        onPulsar={onAprobar}
      >
        <span className="cae-revision__nota">{APROBAR_NOTA}</span>
      </Accion>

      {carenciasDeclaradas(revision).length === 0 ? null : (
        <Accion
          capacidad={CAPACIDAD_SUBSANACION}
          nombre={ENVIAR_SUBSANACION}
          activa={false}
          motivo={motivoDe(CAPACIDAD_SUBSANACION, INACTIVO_SIN_TEXTO)}
        />
      )}

      {fueraDeAmbito(revision) ? (
        <Accion
          capacidad={CAPACIDAD_DESCARTE}
          nombre={CONFIRMAR_DESCARTE}
          activa={false}
          motivo={motivoDe(CAPACIDAD_DESCARTE, INACTIVO_SIN_TEXTO)}
        />
      ) : null}

      {hayObservaciones ? (
        <Accion
          capacidad={CAPACIDAD_OBSERVACION}
          nombre={REVISAR_OBSERVACION}
          activa={puede(CAPACIDAD_OBSERVACION)}
          motivo={motivoDe(CAPACIDAD_OBSERVACION)}
        />
      ) : null}

      {hayDiscrepancia ? (
        <Accion
          capacidad={CAPACIDAD_DISCREPANCIA}
          nombre={RESOLVER_DISCREPANCIA}
          activa={false}
          motivo={motivoDe(CAPACIDAD_DISCREPANCIA, INACTIVO_SIN_TEXTO)}
        />
      ) : null}

      {requerimiento === null ? null : (
        <Accion
          capacidad={CAPACIDAD_INTERPRETACION}
          nombre={CONFIRMAR_INTERPRETACION}
          activa={false}
          motivo={INACTIVO_INTERPRETACION}
        />
      )}

      <Accion
        capacidad={CAPACIDAD_SUBIR}
        nombre={SUBIR_DOCUMENTO}
        activa={false}
        motivo={motivoDe(CAPACIDAD_SUBIR, INACTIVO_SUBIDA)}
      />

      <p className="cae-revision__nota">{INHABILITAR_NO_AUTORIZA}</p>
    </section>
  );
}
