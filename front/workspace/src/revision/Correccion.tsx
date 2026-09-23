import { useState, type FormEvent, type ReactElement } from "react";

import {
  CAMPO_JUSTIFICACION,
  CAMPO_UNIDAD,
  CAMPO_VALOR,
  CAMPO_VARIABLE,
  CANCELAR_CORRECCION,
  FALTA_LA_JUSTIFICACION,
  GUARDAR_CORRECCION,
  JUSTIFICACION_AYUDA,
  JUSTIFICACION_OBLIGATORIA,
  SE_DESCARTAN,
  SE_ELIGE,
  SIN_CONTROL_DE_VEREDICTO,
  TITULO_CORRECCION,
} from "../textos";

/** Lo que viaja a `CAP-05`/`CAP-06`, con los nombres con los que lo espera el contrato. */
export interface DatosCorreccion {
  readonly variable: string;
  readonly num_serie_motor: string | null;
  /**
   * **Cadena, siempre.** Un `number` en `datos` lo rechaza `api.contrato._sin_coma_flotante`, y con
   * razon: una magnitud que entra por la API como coma flotante ya ha perdido exactitud antes de llegar
   * al motor (`CLAUDE.md` §2). El campo es de texto por lo mismo; un `input type="number"` devuelve
   * `number` y empuja a convertir.
   */
  readonly valor: string;
  readonly justificacion: string;
}

export interface PropsCorreccion {
  readonly variable: string;
  readonly numSerieMotor: string | null;
  /** El valor de la evidencia elegida, **editable**. Es lo unico que la pantalla precarga. */
  readonly valorInicial: string;
  readonly unidad?: string | null | undefined;
  /** Lo que se elige y lo que se descarta, para que escribir el motivo cueste segundos y no minutos. */
  readonly descartados?: readonly string[] | undefined;
  readonly onCorregir: (datos: DatosCorreccion) => void | Promise<void>;
  readonly onCancelar?: (() => void) | undefined;
  /** `R-UI-05`: el formulario se ve, y dice por que no se puede enviar. */
  readonly motivoInactivo?: string | undefined;
}

/**
 * El formulario de `CAP-05` (`T-REV-revision` §6): el camino que sustituye al boton que no existe.
 *
 * **La justificacion nace vacia en todos los caminos de entrada y la pantalla no la rellena, no la
 * sugiere y no la copia de la evidencia** (`R-UI-04`, `CA-REV-03`). Es el unico paso del recorrido que
 * no se puede acelerar, y es deliberado: lo que se escribe aqui es lo que quedara en el log explicando
 * por que un humano cambio un dato que el motor no quiso elegir.
 *
 * Las dos barreras de `CA-REV-02`, y son dos a proposito: con la justificacion en blanco el boton esta
 * inhabilitado **y**, si aun asi se enviara, el servidor lo rechaza. Inhabilitar no es autorizar
 * (`R-UI-01`); la unica barrera que cuenta es la del servidor, y esta esta para explicar.
 *
 * Lo que este formulario **no** tiene: ningun campo de veredicto. No se fija, no se fuerza y no se
 * cambia (`R-UI-02`); se corrige el dato y el motor vuelve a calcular.
 */
export function Correccion({
  variable,
  numSerieMotor,
  valorInicial,
  unidad,
  descartados,
  onCorregir,
  onCancelar,
  motivoInactivo,
}: PropsCorreccion): ReactElement {
  const [valor, setValor] = useState(valorInicial);
  // Nace vacia. Y si el formulario se abre desde otra evidencia, el padre lo remonta con una `key`
  // distinta: asi no hay ningun camino por el que una justificacion escrita antes reaparezca sola.
  const [justificacion, setJustificacion] = useState("");
  const [enviando, setEnviando] = useState(false);

  const faltaJustificacion = justificacion.trim() === "";
  const inactivo = motivoInactivo !== undefined;

  function enviar(evento: FormEvent<HTMLFormElement>): void {
    evento.preventDefault();
    if (faltaJustificacion || inactivo || enviando) {
      return;
    }
    setEnviando(true);
    void Promise.resolve(
      onCorregir({
        variable,
        num_serie_motor: numSerieMotor,
        valor,
        justificacion,
      }),
    ).finally(() => {
      setEnviando(false);
    });
  }

  return (
    <form className="cae-revision__correccion" data-variable={variable} onSubmit={enviar}>
      <h4 className="cae-revision__correccion-titulo">{TITULO_CORRECCION}</h4>
      <p className="cae-revision__nota">{SIN_CONTROL_DE_VEREDICTO}</p>

      <p className="cae-revision__campo-fijo">
        <span className="cae-revision__etiqueta">{CAMPO_VARIABLE}</span>
        <span className="cae-revision__valor" data-campo="variable">
          {variable}
        </span>
      </p>
      {numSerieMotor === null ? null : (
        <p className="cae-revision__campo-fijo">
          <span className="cae-revision__etiqueta">{CAMPO_UNIDAD}</span>
          <span className="cae-revision__valor" data-campo="num_serie_motor">
            {numSerieMotor}
          </span>
        </p>
      )}

      <label className="cae-revision__campo">
        <span className="cae-revision__etiqueta">
          {CAMPO_VALOR}
          {unidad === null || unidad === undefined ? null : (
            <span className="cae-revision__unidad">{` (${unidad})`}</span>
          )}
        </span>
        <input
          type="text"
          name="valor"
          inputMode="decimal"
          className="cae-revision__entrada"
          value={valor}
          disabled={inactivo}
          onChange={(evento) => setValor(evento.target.value)}
        />
      </label>

      <label className="cae-revision__campo">
        <span className="cae-revision__etiqueta">
          {CAMPO_JUSTIFICACION}
          <span className="cae-revision__obligatorio"> — {JUSTIFICACION_OBLIGATORIA}</span>
        </span>
        <textarea
          name="justificacion"
          className="cae-revision__justificacion"
          rows={3}
          value={justificacion}
          disabled={inactivo}
          placeholder=""
          onChange={(evento) => setJustificacion(evento.target.value)}
        />
        <span className="cae-revision__ayuda">{JUSTIFICACION_AYUDA}</span>
      </label>

      <p className="cae-revision__eleccion">
        <span className="cae-revision__etiqueta">{SE_ELIGE}</span>
        <span className="cae-revision__valor">{valor}</span>
        {descartados === undefined || descartados.length === 0 ? null : (
          <span className="cae-revision__descartados">{` · ${SE_DESCARTAN}: ${descartados.join(", ")}`}</span>
        )}
      </p>

      <div className="cae-revision__acciones">
        <button
          type="submit"
          className="cae-revision__guardar"
          disabled={faltaJustificacion || inactivo || enviando}
          title={motivoInactivo ?? (faltaJustificacion ? FALTA_LA_JUSTIFICACION : undefined)}
        >
          {GUARDAR_CORRECCION}
        </button>
        {onCancelar === undefined ? null : (
          <button type="button" className="cae-revision__cancelar" onClick={onCancelar}>
            {CANCELAR_CORRECCION}
          </button>
        )}
        {faltaJustificacion && !inactivo ? (
          <span className="cae-revision__motivo-inactivo">{FALTA_LA_JUSTIFICACION}</span>
        ) : null}
        {inactivo ? <span className="cae-revision__motivo-inactivo">{motivoInactivo}</span> : null}
      </div>
    </form>
  );
}
