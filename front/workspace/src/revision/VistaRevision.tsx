import { ValorMetrica } from "@cae/compartido";
import type { Cliente, Contexto } from "@cae/compartido/api";
import { useCallback, useState, type ReactElement } from "react";

import { AvisoServidor } from "../AvisoServidor";
import { Pantalla } from "../Pantalla";
import { falloDe, type FalloServidor } from "../fallos";
import { booleano } from "../json";
import { origenDeclarado } from "../origen";
import {
  APROBACION_REGISTRADA,
  CARGANDO_REVISION,
  CARGANDO_REVISION_DESCRIPCION,
  CONTAGIADA,
  CORRECCION_RECALCULADA,
  CORRECCION_REGISTRADA,
  ESCRITURA_SIN_ESTADO,
  ETIQUETA_CICLO,
  ETIQUETA_EVALUACION,
  ETIQUETA_FICHA,
  ETIQUETA_PLATAFORMA,
  ETIQUETA_REQUERIMIENTO,
  ETIQUETA_VEREDICTO,
  PENDIENTE_DE_RECALCULO,
  PENDIENTE_DE_RECALCULO_DESCRIPCION,
  SIN_CONTROL_DE_VEREDICTO,
  SOLO_LECTURA_FIRMADA,
  SOLO_LECTURA_REQUERIMIENTO,
  TITULO_RECHAZOS,
  TITULO_REVISION,
} from "../textos";
import { useLectura } from "../useLectura";
import { Acciones } from "./Acciones";
import { Ahorro } from "./Ahorro";
import { Datos } from "./Datos";
import { Impedimentos } from "./Impedimentos";
import { PanelDocumento } from "./PanelDocumento";
import type { DatosCorreccion } from "./Correccion";
import {
  CAPACIDAD_ACTUACION,
  CAPACIDAD_APROBAR,
  CAPACIDAD_CORREGIR,
  CLAVE_RECALCULADA,
  PANTALLA,
  cargarRevision,
  carenciasDeclaradas,
  datoDeVariable,
  escrituraPermitida,
  type Cita,
  type Documento,
  type Revision,
} from "./datos";

/**
 * La vista de revision de `T-REV`: la pantalla donde se mide el valor del producto.
 *
 * Tres preguntas, en este orden (`T-REV-revision` §1): **¿esto esta bien?** (el veredicto y su
 * descargo), **¿me lo creo?** (cada dato con su cita y el papel al lado) y **¿que hago ahora?** (una
 * sola accion evidente).
 *
 * ### La regla que le da forma
 *
 * **No hay ningun control para cambiar el veredicto** (`R-UI-02`). El veredicto no es un campo: es el
 * resultado de aplicar la ficha a los datos. Si esta mal, es que un dato esta mal, y el camino —corregir
 * el dato— no esta escondido en un menu: es la accion principal al lado de cada dato que falla. Y desde
 * el 23/09/2026 el lazo esta cerrado de verdad: `CAP-05` corrige **y recalcula en el acto**
 * (`ADR-014` §3). Lo que esta pantalla hace con eso es no mentir sobre el resultado: si el servidor dice
 * que no pudo recalcular, el veredicto y el ahorro salen marcados **pendiente de recalculo** en vez de
 * pasar por actualizados (`CA-REV-09`).
 *
 * ### Lo que esta pantalla no hace
 *
 * - **No calcula, no evalua ninguna regla y no decide ninguna transicion** (`R-UI-11`). Ni una cifra pasa
 *   por `Number`: cada magnitud llega exacta y presentable, y se pinta la presentable tal cual.
 * - **No autoriza nada** (`R-UI-01`). Inhabilita para explicar; quien concede o deniega es el servidor.
 * - **No firma** (`R-UI-03`). Aqui no hay ninguna accion de firma, y ningun control se llama asi.
 * - **No inventa lo que `api/` no sirve.** Lo que falta se dice con su hueco declarado y su motivo.
 */

export interface PropsVistaRevision {
  /** El cliente de `api/`, con su transporte ya inyectado. La pantalla no crea ninguno. */
  readonly cliente: Cliente;
  readonly tenantId: string;
  readonly actuacionId: string;
}

/** La cita abierta en el panel izquierdo: que documento, que pagina y que texto se esta comprobando. */
interface Seleccion {
  readonly docId: string;
  readonly pagina: number | null;
  readonly textoLiteral: string | null;
}

/** Lo que contesto el ultimo comando. Se ensena entero: tambien cuando fue que no. */
interface Resultado {
  readonly mensaje: string;
  readonly avisos: readonly string[];
}

function Esqueleto(): ReactElement {
  return (
    <div className="cae-revision__esqueleto" role="status">
      <p>{CARGANDO_REVISION}</p>
      <p className="cae-revision__nota">{CARGANDO_REVISION_DESCRIPCION}</p>
    </div>
  );
}

function Cabecera({ revision }: { readonly revision: Revision }): ReactElement {
  const identificacion = revision.identificacion;
  const estados = revision.estados.estado === "LISTO" ? revision.estados.valor : null;
  return (
    <div className="cae-revision__identificacion">
      <span className="cae-revision__codigo">
        {identificacion.codigo ?? identificacion.actuacionId}
      </span>
      {identificacion.ficha === null ? null : (
        <span className="cae-revision__ficha">{`${ETIQUETA_FICHA}: ${identificacion.ficha}`}</span>
      )}
      {identificacion.fechaEvaluacion === null ? null : (
        <span className="cae-revision__fecha">
          {`${ETIQUETA_EVALUACION} ${identificacion.fechaEvaluacion}`}
        </span>
      )}
      <span className="cae-revision__ciclo">
        {estados?.ciclo === undefined || estados?.ciclo === null ? (
          <ValorMetrica etiqueta={ETIQUETA_CICLO} metrica={{ estado: "SIN_DATO" }} />
        ) : (
          `${ETIQUETA_CICLO}: ${estados.ciclo}`
        )}
      </span>
      <span className="cae-revision__plataforma">
        {estados?.plataforma === undefined || estados?.plataforma === null ? (
          <ValorMetrica etiqueta={ETIQUETA_PLATAFORMA} metrica={{ estado: "SIN_DATO" }} />
        ) : (
          `${ETIQUETA_PLATAFORMA}: ${estados.plataforma}`
        )}
      </span>
      {estados?.requerimientoAbierto === undefined || estados?.requerimientoAbierto === null ? null : (
        <span className="cae-revision__requerimiento">
          {`${ETIQUETA_REQUERIMIENTO}: ${estados.requerimientoAbierto}`}
        </span>
      )}
      {estados?.afectadaDirectamente === false ? (
        <span className="cae-revision__contagiada">{CONTAGIADA}</span>
      ) : null}
    </div>
  );
}

function Veredicto({
  revision,
  pendienteDeRecalculo,
}: {
  readonly revision: Revision;
  readonly pendienteDeRecalculo: boolean;
}): ReactElement {
  const veredicto = revision.veredicto;
  return (
    <section className="cae-revision__veredicto" aria-label={ETIQUETA_VEREDICTO}>
      <p className="cae-revision__veredicto-valor" data-veredicto-servido={veredicto.valor ?? undefined}>
        {veredicto.semaforo === null ? null : (
          <span className="cae-revision__semaforo" aria-hidden="true">
            {veredicto.semaforo}
          </span>
        )}
        {/* Texto, no control (`R-UI-02`): llega decidido por el motor y aqui solo se lee. */}
        {veredicto.valor}
      </p>
      {pendienteDeRecalculo ? (
        <p className="cae-revision__pendiente" role="alert" title={PENDIENTE_DE_RECALCULO_DESCRIPCION}>
          {PENDIENTE_DE_RECALCULO}
        </p>
      ) : null}
      {veredicto.mensaje === null ? null : (
        <p className="cae-revision__veredicto-mensaje">{veredicto.mensaje}</p>
      )}
      {/* El descargo del servidor, **literal y entero**: no es texto de producto nuestro (§11 bis). */}
      {veredicto.descargo === null ? null : (
        <p className="cae-revision__descargo">{veredicto.descargo}</p>
      )}
      <p className="cae-revision__nota">{SIN_CONTROL_DE_VEREDICTO}</p>
    </section>
  );
}

export function VistaRevision({ cliente, tenantId, actuacionId }: PropsVistaRevision): ReactElement {
  const { lectura, recargar } = useLectura(
    CAPACIDAD_ACTUACION,
    () => cargarRevision(cliente, tenantId, actuacionId),
    [tenantId, actuacionId],
  );
  const [seleccion, setSeleccion] = useState<Seleccion | null>(null);
  const [correccion, setCorreccion] = useState<{ variable: string; cita: Cita } | null>(null);
  const [pendienteDeRecalculo, setPendiente] = useState(false);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [fallo, setFallo] = useState<FalloServidor | null>(null);

  const contexto: Contexto = {
    superficie: PANTALLA,
    tenant_id: tenantId,
    actuacion_id: actuacionId,
  };

  const verDocumento = useCallback(
    (docId: string, pagina: number | null, textoLiteral: string | null) => {
      setSeleccion({ docId, pagina, textoLiteral });
    },
    [],
  );

  const revision = lectura.estado === "LISTO" ? lectura.valor : null;

  /**
   * Ejecuta un comando y cuenta lo que paso, **tambien cuando fue que no**.
   *
   * Un comando que falla no deja la pantalla como estaba y en silencio: el motivo del servidor se ensena
   * literal (`ADR-012` §3, regla 2). Y uno que sale bien vuelve a pedir las tres lecturas, porque lo que
   * habia en pantalla ya no es lo ultimo que sabe el servidor.
   */
  const ejecutar = useCallback(
    async (capacidad: "CAP-05" | "CAP-10", datos: Readonly<Record<string, unknown>>, mensaje: string) => {
      setFallo(null);
      try {
        const salida = await cliente.ejecutar(capacidad, contexto, datos);
        // `recalculada` lo decide el servidor (`ADR-014` C24) y aqui solo se lee: si el motor no pudo
        // rehacer el calculo, lo que se lea despues sigue siendo el veredicto anterior (`CA-REV-09`).
        // Un comando devuelve lo que devuelve, y no son bloques de proyeccion: se mira por su nombre.
        const devueltos = salida.datos as Readonly<Record<string, unknown>>;
        const hayRecalculo = CLAVE_RECALCULADA in devueltos;
        const recalculada = booleano(devueltos[CLAVE_RECALCULADA]) === true;
        if (hayRecalculo) {
          setPendiente(!recalculada);
        }
        setResultado({
          mensaje: hayRecalculo && recalculada ? `${mensaje} ${CORRECCION_RECALCULADA}` : mensaje,
          avisos: salida.avisos,
        });
        setCorreccion(null);
        recargar();
      } catch (causa) {
        setFallo(falloDe(capacidad, causa));
      }
    },
    [cliente, contexto.actuacion_id, contexto.tenant_id, recargar],
  );

  const corregir = useCallback(
    (datos: DatosCorreccion) => ejecutar(CAPACIDAD_CORREGIR, { ...datos }, CORRECCION_REGISTRADA),
    [ejecutar],
  );

  const escritura = revision === null ? "NADA" : escrituraPermitida(revision);
  // El motivo tiene que ser **el de verdad**: si `CAP-14` no contestó, los controles quedan inactivos
  // igual, pero decir "está firmada" sería afirmar algo que no consta.
  const sinEstado = revision !== null && revision.estados.estado === "ERROR";
  const motivoEscritura =
    escritura === "TODO"
      ? undefined
      : sinEstado
        ? ESCRITURA_SIN_ESTADO
        : escritura === "REQUERIMIENTO"
          ? SOLO_LECTURA_REQUERIMIENTO
          : SOLO_LECTURA_FIRMADA;

  // El documento abierto: el que se haya pulsado o, mientras no se haya pulsado ninguno, el primero que
  // dio la lectura. La pantalla no elige por criterio propio ni ordena la lista (`R-UI-11`).
  const documentos: readonly Documento[] = revision?.documentos ?? [];
  const elegido: Documento | null =
    documentos.find((documento) => documento.docId === seleccion?.docId) ?? documentos[0] ?? null;

  const nombreDocumento = useCallback(
    (docId: string) => documentos.find((documento) => documento.docId === docId)?.nombre ?? docId,
    [documentos],
  );

  const rechazos = revision?.estados.estado === "LISTO" ? revision.estados.valor.rechazos : [];

  return (
    <Pantalla
      titulo={TITULO_REVISION}
      rolNombre={revision === null ? null : revision.rolNombre}
      origen={revision === null ? origenDeclarado() : revision.origen}
      avisos={revision === null ? undefined : revision.avisos}
    >
      {lectura.estado === "CARGANDO" ? <Esqueleto /> : null}
      {lectura.estado === "ERROR" ? (
        <AvisoServidor fallo={lectura.fallo} onReintentar={recargar} />
      ) : null}

      {revision === null ? null : (
        <div className="cae-revision">
          <Cabecera revision={revision} />
          {motivoEscritura === undefined ? null : (
            <p className="cae-revision__candado" role="alert">
              {motivoEscritura}
            </p>
          )}

          <div className="cae-revision__partida">
            <PanelDocumento
              cliente={cliente}
              contexto={contexto}
              documento={elegido}
              pagina={seleccion?.pagina ?? null}
              textoLiteral={seleccion?.textoLiteral ?? null}
            />

            <div className="cae-revision__panel-datos">
              <Veredicto revision={revision} pendienteDeRecalculo={pendienteDeRecalculo} />

              {fallo === null ? null : <AvisoServidor fallo={fallo} />}
              {resultado === null ? null : (
                <div className="cae-revision__resultado" role="status">
                  <p>{resultado.mensaje}</p>
                  {resultado.avisos.map((aviso) => (
                    <p key={aviso} className="cae-revision__aviso">
                      {aviso}
                    </p>
                  ))}
                </div>
              )}
              {rechazos.length === 0 ? null : (
                <section className="cae-revision__rechazos" aria-label={TITULO_RECHAZOS}>
                  <h3 className="cae-revision__titulo-bloque">{TITULO_RECHAZOS}</h3>
                  <ul>
                    {rechazos.map((rechazo) => (
                      <li key={rechazo}>{rechazo}</li>
                    ))}
                  </ul>
                </section>
              )}

              {revision.carencias.estado === "ERROR" ? (
                <AvisoServidor fallo={revision.carencias.fallo} onReintentar={recargar} />
              ) : null}
              {revision.estados.estado === "ERROR" ? (
                <AvisoServidor fallo={revision.estados.fallo} onReintentar={recargar} />
              ) : null}

              <Impedimentos
                conflictos={revision.conflictos}
                carencias={carenciasDeclaradas(revision)}
                datoDe={(variable, numSerieMotor) => datoDeVariable(revision, variable, numSerieMotor)}
                nombreDocumento={nombreDocumento}
                onVerDocumento={verDocumento}
                motivoNoCalculo={revision.calculo.motivoNoCalculo}
                correccion={correccion}
                onUsarValor={(variable, _numSerieMotor, cita) => {
                  setCorreccion({ variable, cita });
                  if (cita.docId !== null) {
                    setSeleccion({
                      docId: cita.docId,
                      pagina: cita.pagina,
                      textoLiteral: cita.textoLiteral,
                    });
                  }
                }}
                onCorregir={corregir}
                onCancelar={() => setCorreccion(null)}
                motivoInactivo={escritura === "TODO" ? undefined : motivoEscritura}
              />

              <Ahorro
                calculo={revision.calculo}
                datoDe={(variable, numSerieMotor) => datoDeVariable(revision, variable, numSerieMotor)}
                nombreDocumento={nombreDocumento}
                onVerDocumento={verDocumento}
                pendienteDeRecalculo={pendienteDeRecalculo}
              />

              <Datos
                datos={revision.datos}
                calculo={revision.calculo}
                veredicto={revision.veredicto}
                historial={revision.historial}
                nombreDocumento={nombreDocumento}
                onVerDocumento={verDocumento}
              />

              <Acciones
                revision={revision}
                escritura={escritura}
                motivoEscritura={motivoEscritura}
                onAprobar={() => ejecutar(CAPACIDAD_APROBAR, {}, APROBACION_REGISTRADA)}
              />
            </div>
          </div>
        </div>
      )}
    </Pantalla>
  );
}
