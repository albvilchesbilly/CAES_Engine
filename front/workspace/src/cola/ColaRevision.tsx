import type { Cliente } from "@cae/compartido/api";
import type { ReactElement } from "react";

import { AvisoServidor } from "../AvisoServidor";
import { Pantalla } from "../Pantalla";
import { origenDeclarado } from "../origen";
import {
  CARGANDO,
  CARGANDO_DESCRIPCION,
  COLUMNA_ACCION,
  COLUMNA_ACTUACION,
  COLUMNA_AHORRO,
  COLUMNA_ANTIGUEDAD,
  COLUMNA_ESTADO,
  COLUMNA_MOTIVOS,
  COLUMNA_VEREDICTO,
  LEYENDA_COLA,
  TITULO_COLA,
  VACIO,
  VACIO_DESCRIPCION,
} from "../textos";
import { useLectura } from "../useLectura";
import { CAPACIDAD_COLA, cargarCola, type Cola } from "./datos";
import { Fila } from "./FilaCola";

/**
 * Las columnas de `T-REV-cola` §5, en el orden en que se leen.
 *
 * Son **rotulos y nada mas**: ningun encabezado ordena. El orden de la cola lo pone el servidor
 * (`ADR-014` §2) y la pantalla lo pinta como llega (`R-UI-11`). Si algun dia estos encabezados llevan un
 * control, hay que abrir un ADR antes, porque cambia quien decide la prioridad del trabajo.
 */
const COLUMNAS = [
  COLUMNA_ACTUACION,
  COLUMNA_VEREDICTO,
  COLUMNA_MOTIVOS,
  COLUMNA_AHORRO,
  COLUMNA_ANTIGUEDAD,
  COLUMNA_ESTADO,
  COLUMNA_ACCION,
] as const;

/** Filas del esqueleto de carga. No es una cifra ni un `SIN DATO`: es el hueco de una lectura en vuelo. */
const FILAS_ESQUELETO = [0, 1, 2];

export interface PropsColaRevision {
  /** El cliente de `api/`, con su transporte ya inyectado. La pantalla no crea ninguno. */
  readonly cliente: Cliente;
  readonly tenantId: string;
  /** El reloj. Se inyecta para que "hace N días" sea el mismo en un test que manana. */
  readonly ahora?: Date | undefined;
  readonly enlaceRevision?: ((actuacionId: string) => string) | undefined;
}

/** A donde lleva una fila mientras no haya enrutador: siempre con el identificador que dio la lectura. */
function enlacePorDefecto(actuacionId: string): string {
  return `#/revision/${encodeURIComponent(actuacionId)}`;
}

function Esqueleto(): ReactElement {
  return (
    <div className="cae-cola__esqueleto" role="status">
      <p>{CARGANDO}</p>
      <p className="cae-cola__esqueleto-nota">{CARGANDO_DESCRIPCION}</p>
      {FILAS_ESQUELETO.map((posicion) => (
        <span key={posicion} className="cae-cola__esqueleto-fila" aria-hidden="true" />
      ))}
    </div>
  );
}

function Vacio(): ReactElement {
  return (
    <div className="cae-cola__vacio">
      <p className="cae-cola__vacio-titulo">{VACIO}</p>
      <p className="cae-cola__vacio-nota">{VACIO_DESCRIPCION}</p>
    </div>
  );
}

function Tabla({
  cola,
  ahora,
  enlaceRevision,
}: {
  readonly cola: Cola;
  readonly ahora: Date;
  readonly enlaceRevision: (actuacionId: string) => string;
}): ReactElement {
  return (
    <table className="cae-cola">
      <caption className="cae-cola__leyenda">{LEYENDA_COLA}</caption>
      <thead>
        <tr>
          {COLUMNAS.map((columna) => (
            <th key={columna} scope="col">
              {columna}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {/* `map` sobre las filas **en el orden en que llegaron**: aqui no hay ni puede haber un `sort`. */}
        {cola.filas.map((fila, posicion) => (
          <Fila
            key={fila.actuacionId ?? `fila-${posicion}`}
            fila={fila}
            detalle={fila.actuacionId === null ? undefined : cola.detalles[fila.actuacionId]}
            ahora={ahora}
            enlaceRevision={enlaceRevision}
          />
        ))}
      </tbody>
    </table>
  );
}

/**
 * La cola de revision de `T-REV`: que actuaciones esperan, por que y desde cuando.
 *
 * Lo que esta pantalla **no** hace, y conviene que siga sin hacer:
 *
 * - **No ordena** (`R-UI-11`). Las filas llegan ordenadas por el motivo de mas prioridad y, a igualdad,
 *   por la que lleva mas tiempo abierta (`ADR-014` §2). Un orden que cada cliente recalcula no se puede
 *   verificar leyendo la respuesta, y este se puede.
 * - **No ejecuta ningun comando**. Ninguna accion de la cola escribe un evento en el log: aprobar,
 *   corregir, descartar y subsanar se hacen con la actuacion delante (`T-REV-cola` §4).
 * - **No decide permisos** (`R-UI-01`). Pide, y el servidor concede o niega; una denegacion se ensena
 *   con el motivo del servidor en vez de hacer desaparecer la fila.
 * - **No ensena ningun valor extraido** (`R-UI-09`). Nombra el conflicto; los valores estan una
 *   pulsacion mas alla.
 */
export function ColaRevision({
  cliente,
  tenantId,
  ahora,
  enlaceRevision,
}: PropsColaRevision): ReactElement {
  // La dependencia es el tenant y no el cliente: el cliente no guarda estado y se espera uno por
  // aplicacion. Si entrara en las dependencias, quien lo construyera dentro del render volveria a pedir
  // la cola en cada vuelta. Un cliente nuevo se usa igualmente en la siguiente carga.
  const { lectura, recargar } = useLectura(CAPACIDAD_COLA, () => cargarCola(cliente, tenantId), [
    tenantId,
  ]);
  const cola = lectura.estado === "LISTO" ? lectura.valor : null;

  return (
    <Pantalla
      titulo={TITULO_COLA}
      rolNombre={cola === null ? null : cola.rolNombre}
      origen={cola === null ? origenDeclarado() : cola.origen}
      avisos={cola === null ? undefined : cola.avisos}
    >
      {lectura.estado === "CARGANDO" ? <Esqueleto /> : null}
      {lectura.estado === "ERROR" ? (
        <AvisoServidor fallo={lectura.fallo} onReintentar={recargar} />
      ) : null}
      {cola === null ? null : cola.filas.length === 0 ? (
        <Vacio />
      ) : (
        <Tabla
          cola={cola}
          ahora={ahora ?? new Date()}
          enlaceRevision={enlaceRevision ?? enlacePorDefecto}
        />
      )}
    </Pantalla>
  );
}
