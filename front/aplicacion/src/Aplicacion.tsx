/**
 * La pagina: el marco que monta el workspace y navega entre la cola y la vista de revision.
 *
 * Cierra `GAP-HTTP-03` (`ADR-015` §7.2): hasta hoy `front/` se consumia como codigo fuente y las
 * pantallas de `FR1`, verificadas contra el contrato, no se abrian en ningun navegador.
 *
 * Lo que hace, y nada mas:
 *
 * - Enrutar por hash entre `ColaRevision` y `VistaRevision`, con el enlace que la cola ya componia.
 * - Pasarles el `Cliente` ya construido. **No construye ninguno**: se lo dan (`main.tsx`).
 * - Decir en pantalla que la autenticacion es de mentira, y quien dice ser esta pagina.
 *
 * Lo que no hace: no calcula, no evalua ninguna regla, no decide ninguna transicion y no oculta nada
 * por perfil (`R-UI-11`, `R-UI-01`). Tampoco toca las pantallas: las usa tal y como `FR1` las entrego.
 */

import type { Cliente } from "@cae/compartido/api";
import { ColaRevision, VistaRevision } from "@cae/workspace";
import type { ReactElement } from "react";

import type { Configuracion } from "./configuracion";
import { useRuta } from "./enrutador";
import {
  AVISO_AUTENTICACION,
  ETIQUETA_DECLARADO,
  SIN_PRINCIPAL_DESCRIPCION,
  TITULO_APLICACION,
  TITULO_SIN_PRINCIPAL,
  VOLVER_A_LA_COLA,
} from "./textos";

export interface PropsAplicacion {
  readonly configuracion: Configuracion;
  /** El cliente de `api/`, con su transporte y su cabecera ya puestos. `null` si no hay principal. */
  readonly cliente: Cliente | null;
  /** El reloj de la cola. Se inyecta para que "hace N días" sea el mismo en una prueba que mañana. */
  readonly ahora?: Date | undefined;
}

/**
 * El aviso de que esto no autentica a nadie.
 *
 * Va fuera de las pantallas y encima de todo, en todos los estados: tambien cuando no hay principal y
 * cuando el servidor deniega. `Pantalla` ya ensena ademas los `avisos` que manda el servidor en cada
 * respuesta —donde viaja el mismo aviso desde `api/http/autenticacion.py`—, pero esos solo se ven si
 * hubo respuesta; este se ve siempre.
 */
function AvisoDeAutenticacion({
  configuracion,
}: {
  readonly configuracion: Configuracion;
}): ReactElement {
  return (
    <div className="cae-app__aviso" role="note">
      <p className="cae-app__aviso-texto">{AVISO_AUTENTICACION}</p>
      {configuracion.estado === "LISTA" ? (
        <p className="cae-app__aviso-principal">
          {`${ETIQUETA_DECLARADO}: ${configuracion.principal.usuario_id} · ` +
            `${configuracion.principal.perfiles.join(", ")} · ${configuracion.principal.tenant_id}`}
        </p>
      ) : null}
    </div>
  );
}

/** Lo que se ve cuando nadie ha declarado un principal. No se pide nada al servidor. */
function SinPrincipal({ motivo }: { readonly motivo: string }): ReactElement {
  return (
    <section className="cae-app__sin-principal">
      <h1>{TITULO_SIN_PRINCIPAL}</h1>
      <p>{motivo}</p>
      <p className="cae-app__nota">{SIN_PRINCIPAL_DESCRIPCION}</p>
    </section>
  );
}

export function Aplicacion({ configuracion, cliente, ahora }: PropsAplicacion): ReactElement {
  const ruta = useRuta();
  const listo = configuracion.estado === "LISTA" && cliente !== null;
  return (
    <div className="cae-app">
      <header className="cae-app__marco">
        <span className="cae-app__nombre">{TITULO_APLICACION}</span>
        {listo && ruta.vista === "REVISION" ? (
          <a className="cae-app__volver" href="#/">
            {VOLVER_A_LA_COLA}
          </a>
        ) : null}
      </header>
      <AvisoDeAutenticacion configuracion={configuracion} />
      <main className="cae-app__lienzo">
        {!listo || configuracion.estado !== "LISTA" || cliente === null ? (
          <SinPrincipal
            motivo={configuracion.estado === "LISTA" ? "no hay cliente construido" : configuracion.motivo}
          />
        ) : ruta.vista === "REVISION" ? (
          <VistaRevision
            cliente={cliente}
            tenantId={configuracion.principal.tenant_id}
            actuacionId={ruta.actuacionId}
          />
        ) : (
          <ColaRevision
            cliente={cliente}
            tenantId={configuracion.principal.tenant_id}
            ahora={ahora}
          />
        )}
      </main>
    </div>
  );
}
